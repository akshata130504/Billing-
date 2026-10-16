"""Approval requests: listing, approve/reject and the side effects per type."""
import importlib
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import EntityNotFoundError, ForbiddenError, InvalidStateError
from backend.app.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
    Invoice,
    MemberRole,
    Payment,
    Quote,
    QuoteStatus,
    utcnow,
)
from backend.app.schemas.common_refs import enum_value, iso_dt, user_ref
from backend.app.services import audit, quote_service
from backend.app.services.pagination import Page, PageParams, apply_sort, paginate

APPROVAL_SORT_FIELDS = ("created_at", "status", "type", "reviewed_at")
APPROVAL_DEFAULT_SORT = "-created_at"

APPROVAL_SNAPSHOT_FIELDS = ("type", "status", "entity_type", "entity_id", "title", "reviewed_by_id", "reviewed_at", "decision_note")


def _query() -> Select:
    return select(ApprovalRequest).options(
        selectinload(ApprovalRequest.requested_by), selectinload(ApprovalRequest.reviewed_by)
    )


def get_approval_or_404(db: Session, organization_id: str, approval_id: str) -> ApprovalRequest:
    stmt = _query().where(ApprovalRequest.id == approval_id, ApprovalRequest.organization_id == organization_id)
    approval = db.scalars(stmt).first()
    if approval is None:
        raise EntityNotFoundError("ApprovalRequest", approval_id)
    return approval


def list_approvals(
    db: Session,
    ctx: CurrentContext,
    params: PageParams,
    status: Optional[str] = None,
    type_: Optional[str] = None,
) -> Page:
    stmt = _query().where(ApprovalRequest.organization_id == ctx.organization_id)
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    if type_:
        stmt = stmt.where(ApprovalRequest.type == type_)
    stmt = apply_sort(stmt, ApprovalRequest, params.sort, APPROVAL_SORT_FIELDS, APPROVAL_DEFAULT_SORT)
    return paginate(db, stmt, params)


def _guard_decision(ctx: CurrentContext, approval: ApprovalRequest) -> None:
    # Enforced here as well as on the route so every entry point (e.g. /quotes/{id}/approve)
    # gets the same rules: admins decide, never on their own request, and only once.
    if not ctx.has_role(MemberRole.ADMIN):
        raise ForbiddenError("Only an admin or owner can decide approval requests.")
    if approval.status != ApprovalStatus.PENDING:
        raise InvalidStateError(f"Approval request is already {enum_value(approval.status)}.")
    if approval.requested_by_id and approval.requested_by_id == ctx.user.id:
        raise ForbiddenError("You cannot approve or reject your own request.")


def _call_hook(module_name: str, func_name: str, db: Session, approval: ApprovalRequest, ctx: CurrentContext) -> bool:
    """Lazily call another module's effect function if it exists.

    Expected signature: func(db, *, approval, ctx) -> None. Returns True when it ran.
    """
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return False
    hook = getattr(module, func_name, None)
    if hook is None:
        return False
    hook(db, approval=approval, ctx=ctx)
    return True


def _apply_approved_effect(db: Session, ctx: CurrentContext, approval: ApprovalRequest) -> None:
    if approval.type == ApprovalType.QUOTE_DISCOUNT:
        quote = db.scalars(
            select(Quote)
            .where(Quote.id == approval.entity_id, Quote.organization_id == ctx.organization_id)
            .options(selectinload(Quote.customer), selectinload(Quote.items))
        ).first()
        if quote is None:
            raise EntityNotFoundError("Quote", approval.entity_id)
        payload = dict(approval.payload or {})
        requested = payload.get("discount_pct")
        if requested is not None and Decimal(str(quote.discount_pct)) > Decimal(str(requested)):
            # The quote changed after the request was raised; never approve unseen terms.
            raise InvalidStateError("The quote's discount changed after this request was raised; it needs a new approval.")
        # Record exactly what was approved: send_quote only honours discounts up to this value.
        payload["approved_discount_pct"] = str(requested if requested is not None else quote.discount_pct)
        approval.payload = payload
        if quote.status == QuoteStatus.PENDING_APPROVAL:
            # Internal authorisation only: the quote becomes `approved` and staff send it next.
            quote_service.mark_approved(db, quote, ctx)
        return
    if approval.type == ApprovalType.REFUND:
        # Money moves here. If the effect cannot run, fail the approval rather than
        # recording it as approved — a refund that is "approved" but never executed
        # tells finance the customer was paid when they were not.
        if not _call_hook("backend.app.services.payment_service", "execute_refund", db, approval, ctx):
            raise InvalidStateError(
                "Refunds cannot be executed right now: the payments module is unavailable. "
                "The approval has not been recorded; retry once the service is back."
            )
        return
    if approval.type == ApprovalType.INVOICE_VOID:
        if not _call_hook("backend.app.services.invoice_service", "void_invoice", db, approval, ctx):
            raise InvalidStateError(
                "This invoice cannot be voided right now: the invoicing module is unavailable. "
                "The approval has not been recorded; retry once the service is back."
            )
        return
    if approval.type == ApprovalType.INVOICE_DISCOUNT:
        from backend.app.models.invoices import Invoice, InvoiceStatus
        from backend.app.services import gst
        from backend.app.services.invoice_service import compute_totals, line_inputs, attach_hsn_codes

        invoice = db.scalars(
            select(Invoice)
            .where(Invoice.id == approval.entity_id, Invoice.organization_id == ctx.organization_id)
            .options(selectinload(Invoice.customer), selectinload(Invoice.items))
        ).first()
        if invoice is None:
            raise EntityNotFoundError("Invoice", approval.entity_id)
        if invoice.status != InvoiceStatus.DRAFT:
            # Preserving accounting integrity: Never modify already-issued/paid invoices directly
            return

        discount_to_apply = (
            Decimal(str(approval.payload.get("discount_pct", invoice.discount_pct)))
            if approval.payload
            else invoice.discount_pct
        )
        organization = ctx.organization
        customer = invoice.customer
        supply = gst.resolve_supply(organization, customer)
        lines = line_inputs(invoice.items)
        attach_hsn_codes(db, ctx.organization_id, lines)
        totals = compute_totals(lines, discount_to_apply, supply=supply)

        invoice.subtotal = totals.subtotal
        invoice.discount_pct = totals.discount_pct
        invoice.discount_amount = totals.discount_amount
        invoice.tax_amount = totals.tax_amount
        invoice.cgst_amount = totals.cgst_amount
        invoice.sgst_amount = totals.sgst_amount
        invoice.igst_amount = totals.igst_amount
        invoice.total = totals.total
        invoice.amount_due = totals.total
        invoice.updated_at = utcnow()
        db.flush()
        return


def approve(db: Session, ctx: CurrentContext, approval_id: str, note: Optional[str]) -> ApprovalRequest:
    approval = get_approval_or_404(db, ctx.organization_id, approval_id)
    _guard_decision(ctx, approval)
    before = audit.snapshot(approval, APPROVAL_SNAPSHOT_FIELDS)
    _apply_approved_effect(db, ctx, approval)
    approval.status = ApprovalStatus.APPROVED
    approval.reviewed_by_id = ctx.user.id
    approval.reviewed_at = utcnow()
    approval.decision_note = note
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="APPROVAL_APPROVED",
        entity_type="approval",
        entity_id=approval.id,
        entity_label=approval.title,
        before=before,
        after=audit.snapshot(approval, APPROVAL_SNAPSHOT_FIELDS),
    )
    db.commit()
    return get_approval_or_404(db, ctx.organization_id, approval.id)


def reject(db: Session, ctx: CurrentContext, approval_id: str, note: str) -> ApprovalRequest:
    approval = get_approval_or_404(db, ctx.organization_id, approval_id)
    _guard_decision(ctx, approval)
    before = audit.snapshot(approval, APPROVAL_SNAPSHOT_FIELDS)
    if approval.type == ApprovalType.QUOTE_DISCOUNT:
        quote = db.scalars(
            select(Quote).where(Quote.id == approval.entity_id, Quote.organization_id == ctx.organization_id)
        ).first()
        if quote is not None and quote.status == QuoteStatus.PENDING_APPROVAL:
            quote_before = audit.snapshot(quote, quote_service.QUOTE_SNAPSHOT_FIELDS)
            quote.status = QuoteStatus.DRAFT
            db.flush()
            audit.record(
                db,
                ctx=ctx,
                action="QUOTE_UPDATED",
                entity_type="quote",
                entity_id=quote.id,
                entity_label=quote.quote_number,
                before=quote_before,
                after={**audit.snapshot(quote, quote_service.QUOTE_SNAPSHOT_FIELDS), "reason": "discount approval rejected"},
            )
    elif approval.type == ApprovalType.INVOICE_DISCOUNT:
        from backend.app.models.invoices import Invoice, InvoiceStatus
        from backend.app.services import gst
        from backend.app.services.invoice_service import compute_totals, line_inputs, attach_hsn_codes

        invoice = db.scalars(
            select(Invoice)
            .where(Invoice.id == approval.entity_id, Invoice.organization_id == ctx.organization_id)
            .options(selectinload(Invoice.customer), selectinload(Invoice.items))
        ).first()
        if invoice is not None and invoice.status == InvoiceStatus.DRAFT:
            organization = ctx.organization
            customer = invoice.customer
            supply = gst.resolve_supply(organization, customer)
            lines = line_inputs(invoice.items)
            attach_hsn_codes(db, ctx.organization_id, lines)
            totals = compute_totals(lines, Decimal("0.00"), supply=supply)

            invoice.subtotal = totals.subtotal
            invoice.discount_pct = Decimal("0.00")
            invoice.discount_amount = Decimal("0.00")
            invoice.tax_amount = totals.tax_amount
            invoice.cgst_amount = totals.cgst_amount
            invoice.sgst_amount = totals.sgst_amount
            invoice.igst_amount = totals.igst_amount
            invoice.total = totals.total
            invoice.amount_due = totals.total
            invoice.updated_at = utcnow()
            db.flush()
    approval.status = ApprovalStatus.REJECTED
    approval.reviewed_by_id = ctx.user.id
    approval.reviewed_at = utcnow()
    approval.decision_note = note
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="APPROVAL_REJECTED",
        entity_type="approval",
        entity_id=approval.id,
        entity_label=approval.title,
        before=before,
        after=audit.snapshot(approval, APPROVAL_SNAPSHOT_FIELDS),
    )
    db.commit()
    return get_approval_or_404(db, ctx.organization_id, approval.id)


# --- serialisers ---------------------------------------------------------------------------------


def entity_labels(db: Session, organization_id: str, approvals: List[ApprovalRequest]) -> Dict[str, str]:
    """Resolve entity_id -> human label (quote/invoice/payment number) in three batched queries."""
    labels: Dict[str, str] = {}
    by_type: Dict[str, List[str]] = {}
    for a in approvals:
        by_type.setdefault(a.entity_type, []).append(a.entity_id)
    lookups = {
        "quote": (Quote, Quote.quote_number),
        "invoice": (Invoice, Invoice.invoice_number),
        "payment": (Payment, Payment.payment_number),
    }
    for entity_type, ids in by_type.items():
        spec = lookups.get(entity_type)
        if not spec or not ids:
            continue
        model, column = spec
        rows = db.execute(select(model.id, column).where(model.organization_id == organization_id, model.id.in_(ids))).all()
        for entity_id, number in rows:
            labels[entity_id] = number
    return labels


def serialize_approval(approval: ApprovalRequest, entity_label: Optional[str] = None) -> Dict[str, Any]:
    payload = approval.payload or {}
    label = entity_label or payload.get("quote_number") or payload.get("invoice_number") or payload.get("payment_number")
    return {
        "id": approval.id,
        "type": enum_value(approval.type),
        "status": enum_value(approval.status),
        "entity_type": approval.entity_type,
        "entity_id": approval.entity_id,
        "entity_label": label or approval.title,
        "title": approval.title,
        "justification": approval.justification,
        "payload": payload,
        "requested_by": user_ref(approval.requested_by),
        "reviewed_by": user_ref(approval.reviewed_by),
        "reviewed_at": iso_dt(approval.reviewed_at),
        "decision_note": approval.decision_note,
        "created_at": iso_dt(approval.created_at),
    }


def serialize_approvals(db: Session, organization_id: str, approvals: List[ApprovalRequest]) -> List[Dict[str, Any]]:
    labels = entity_labels(db, organization_id, approvals)
    return [serialize_approval(a, labels.get(a.entity_id)) for a in approvals]
