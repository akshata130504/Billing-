"""Invoice domain logic (contract §8).

Exports the reusable `serialize_invoice(invoice, include_payments=True)` and
`recompute_invoice(db, invoice)` used by the payments, subscriptions, quotes
and scheduler modules. Every public mutation commits exactly once.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, object_session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.config import settings
from backend.app.core.exceptions import EntityNotFoundError, InvalidStateError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.core.security import generate_opaque_token
from backend.app.models import (
    OPEN_INVOICE_STATUSES,
    ApprovalRequest,
    Customer,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Organization,
    Payment,
    PaymentAllocation,
    PaymentStatus,
    Product,
    Subscription,
    SubscriptionStatus,
    User,
    utcnow,
)
from backend.app.schemas.common_refs import customer_ref, iso_dt, line_item_out, money_str, user_ref
from backend.app.schemas.invoices import InvoiceCreate, InvoiceUpdate
from backend.app.services import audit, currency_totals
from backend.app.services.email import frontend_url, send_email
from backend.app.services.money import D, LineInput, compute_totals, q2
from backend.app.services import gst
from backend.app.services import timezones
from backend.app.services.numbering import next_number, release_number_if_latest
from backend.app.services.pagination import PageParams, apply_sort, paginate

INVOICE_SNAPSHOT_FIELDS = (
    "invoice_number",
    "status",
    "customer_id",
    "issue_date",
    "due_date",
    "subtotal",
    "discount_pct",
    "total",
    "amount_paid",
    "amount_due",
    "sent_at",
    "paid_at",
    "voided_at",
    "void_reason",
    "reminder_count",
    "last_reminder_at",
)

# Payments whose allocations count as money received against an invoice.
SETTLED_PAYMENT_STATUSES = (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED)

INVOICE_SORT_FIELDS = ("created_at", "issue_date", "due_date", "total", "amount_due", "invoice_number", "status", "updated_at")


# --- small helpers ----------------------------------------------------------------------


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes; treat them as UTC so comparisons work everywhere."""
    return iso_dt(value)


def snapshot(invoice: Invoice) -> Dict[str, Any]:
    return audit.snapshot(invoice, INVOICE_SNAPSHOT_FIELDS)


def days_overdue(invoice: Invoice, today: Optional[date] = None) -> int:
    if invoice.status not in OPEN_INVOICE_STATUSES or invoice.due_date is None:
        return 0
    if today is None:
        # The organization's business day, not the server's (UTC in production).
        session = object_session(invoice)
        today = (
            timezones.org_today_for_id(session, invoice.organization_id)
            if session is not None
            else timezones.utc_today()
        )
    return max(0, (today - invoice.due_date).days)


def pdf_url_for(invoice: Invoice) -> str:
    return f"{settings.API_V1_STR}/public/invoices/{invoice.public_token}/pdf"


def public_url_for(invoice: Invoice) -> str:
    return frontend_url(f"pay/{invoice.public_token}")


def line_inputs(items: Iterable) -> List[LineInput]:
    return [
        LineInput(
            description=i.description,
            quantity=D(i.quantity),
            unit_price=D(i.unit_price),
            tax_rate_pct=D(i.tax_rate_pct),
            offering_id=getattr(i, "offering_id", None),
            product_id=getattr(i, "product_id", None),
            plan_id=getattr(i, "plan_id", None),
            pricing_explanation=getattr(i, "pricing_explanation", None),
            hsn_sac_code=getattr(i, "hsn_sac_code", None),
        )
        for i in items
    ]


def validate_line_references(
    db: Session,
    organization_id: str,
    items: Iterable,
    retained_lines: Optional[Mapping[str, Optional[str]]] = None,
) -> None:
    """Reject catalog references on posted lines that are certainly invalid: an id that does
    not exist in THIS organization (cross-tenant and unknown ids look identical, so nothing
    about other tenants leaks), a line carrying both product_id and plan_id, or a plan/product
    that belongs to a different offering than the line's offering_id. Custom lines (no ids)
    are always fine.

    An ARCHIVED offering (is_active = false) is accepted only on a line that is already on this
    invoice and is being kept: ``retained_lines`` maps each stored line id of the invoice to its
    offering id. A posted archived line is retained only when it names a stored line of this
    invoice, that stored line has the same offering, and no earlier posted line already claimed
    it; anything else (no id, another invoice's id, another offering's id, a second claim, a
    removed and re-added line) is a NEW use and is rejected. Only the user-facing create/update
    path calls this; system-generated invoices (renewals, proration, ...) are not restricted."""
    from backend.app.models.catalog import Plan, Product
    from backend.app.models.catalog_cpq import Offering

    rows = list(items)
    wanted = {"offering_id": set(), "product_id": set(), "plan_id": set()}
    for item in rows:
        for field, bucket in wanted.items():
            value = getattr(item, field, None)
            if value:
                bucket.add(value)

    def _existing(model, ids):
        if not ids:
            return {}
        found = db.execute(
            select(model).where(model.organization_id == organization_id, model.id.in_(list(ids)))
        ).scalars()
        return {row.id: row for row in found}

    offerings = _existing(Offering, wanted["offering_id"])
    products = _existing(Product, wanted["product_id"])
    plans = _existing(Plan, wanted["plan_id"])

    fields: Dict[str, str] = {}
    for idx, item in enumerate(rows):
        offering_id = getattr(item, "offering_id", None)
        product_id = getattr(item, "product_id", None)
        plan_id = getattr(item, "plan_id", None)
        if offering_id and offering_id not in offerings:
            fields[f"items[{idx}].offering_id"] = "unknown reference"
        if product_id and product_id not in products:
            fields[f"items[{idx}].product_id"] = "unknown reference"
        if plan_id and plan_id not in plans:
            fields[f"items[{idx}].plan_id"] = "unknown reference"
        if product_id and plan_id:
            fields[f"items[{idx}].plan_id"] = "a line cannot reference both a product and a plan"
        if offering_id and offering_id in offerings:
            plan = plans.get(plan_id) if plan_id else None
            if plan is not None and plan.offering_id and plan.offering_id != offering_id:
                fields[f"items[{idx}].plan_id"] = "plan does not belong to the line's offering"
            product = products.get(product_id) if product_id else None
            if product is not None and product.offering_id and product.offering_id != offering_id:
                fields[f"items[{idx}].product_id"] = "product does not belong to the line's offering"
    if fields:
        raise ValidationAppError("One or more line items reference an invalid catalog item.", {"fields": fields})

    retained = retained_lines or {}
    claimed: set = set()
    archived_fields: Dict[str, str] = {}
    for idx, item in enumerate(rows):
        offering_id = getattr(item, "offering_id", None)
        offering = offerings.get(offering_id) if offering_id else None
        if offering is None or offering.is_active:
            continue
        line_id = getattr(item, "id", None)
        if not line_id:
            reason = "archived offering cannot be added to an invoice line"
        elif line_id not in retained:
            reason = "line id does not belong to this invoice"
        elif retained[line_id] != offering_id:
            reason = "line id belongs to a different offering"
        elif line_id in claimed:
            reason = "line id is already used by another line"
        else:
            claimed.add(line_id)
            continue
        archived_fields[f"items[{idx}].offering_id"] = reason
    if archived_fields:
        raise ValidationAppError(
            "An archived offering cannot be used on a new invoice line; it can only stay on a line "
            "that is already on this invoice.",
            {"fields": archived_fields},
        )


def _user(session: Optional[Session], user_id: Optional[str]) -> Optional[User]:
    if session is None or not user_id:
        return None
    return session.get(User, user_id)


# --- serialisation -------------------------------------------------------------------------


def invoice_payment_refs(invoice: Invoice) -> List[Dict[str, Any]]:
    refs = []
    for alloc in sorted(invoice.allocations, key=lambda a: (as_utc(a.created_at) or datetime.min.replace(tzinfo=timezone.utc))):
        payment = alloc.payment
        if payment is None:
            continue
        refs.append(
            {
                "id": payment.id,
                "payment_number": payment.payment_number,
                "amount": money_str(alloc.amount),
                "method": payment.method,
                "paid_at": iso_dt(payment.paid_at),
                "status": payment.status,
            }
        )
    return refs


def serialize_invoice(invoice: Invoice, include_payments: bool = True) -> Dict[str, Any]:
    """Build the InvoiceOut dict. Reused by the quotes builder for /quotes/{id}/convert."""
    session = object_session(invoice)
    data = {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "customer": customer_ref(invoice.customer),
        "subscription_id": invoice.subscription_id,
        "quote_id": invoice.quote_id,
        "status": invoice.status,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "currency": invoice.currency,
        "subtotal": money_str(invoice.subtotal),
        "discount_pct": money_str(invoice.discount_pct),
        "discount_amount": money_str(invoice.discount_amount),
        "tax_amount": money_str(invoice.tax_amount),
        "cgst_amount": money_str(invoice.cgst_amount),
        "sgst_amount": money_str(invoice.sgst_amount),
        "igst_amount": money_str(invoice.igst_amount),
        "supply_type": invoice.supply_type,
        "place_of_supply_code": invoice.place_of_supply_code,
        "place_of_supply_name": invoice.place_of_supply_name,
        "customer_gstin": invoice.customer_gstin,
        "supplier_gstin": invoice.supplier_gstin,
        "total": money_str(invoice.total),
        "amount_paid": money_str(invoice.amount_paid),
        "amount_due": money_str(invoice.amount_due),
        "notes": invoice.notes,
        "terms": invoice.terms,
        "items": [line_item_out(i) for i in sorted(invoice.items, key=lambda x: x.position or 0)],
        "public_url": public_url_for(invoice),
        "pdf_url": pdf_url_for(invoice),
        "sent_at": iso_dt(invoice.sent_at),
        "paid_at": iso_dt(invoice.paid_at),
        "voided_at": iso_dt(invoice.voided_at),
        "void_reason": invoice.void_reason,
        "last_reminder_at": iso_dt(invoice.last_reminder_at),
        "reminder_count": int(invoice.reminder_count or 0),
        "period_start": invoice.period_start,
        "period_end": invoice.period_end,
        "days_overdue": days_overdue(invoice),
        "email_delivery_failed": getattr(invoice, "_email_delivery_failed", None),
        "payments": invoice_payment_refs(invoice) if include_payments else [],
        "approval_request_id": None,
        "is_pending_approval": False,
        "created_by": user_ref(_user(session, invoice.created_by_id)),
        "created_at": iso_dt(invoice.created_at),
        "updated_at": iso_dt(invoice.updated_at),
    }

    if session is not None:
        try:
            from backend.app.models.governance import ApprovalRequest, ApprovalStatus, ApprovalType
            pending_req = (
                session.query(ApprovalRequest)
                .filter(
                    ApprovalRequest.organization_id == invoice.organization_id,
                    ApprovalRequest.type == ApprovalType.INVOICE_DISCOUNT,
                    ApprovalRequest.entity_id == invoice.id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                )
                .first()
            )
            if pending_req:
                data["approval_request_id"] = pending_req.id
                data["is_pending_approval"] = True
        except Exception:
            # Serialization must not fail over this optional flag; fall back to "no pending
            # approval" but leave a trace so a broken query is noticed.
            logger.warning(
                "Pending-approval lookup failed for invoice %s; serializing without it",
                invoice.id,
                exc_info=True,
            )

    return data


# --- queries -----------------------------------------------------------------------------------


def _base_query() -> Select:
    return select(Invoice).options(
        selectinload(Invoice.items),
        selectinload(Invoice.customer),
        selectinload(Invoice.allocations).selectinload(PaymentAllocation.payment),
    )


def get_invoice(db: Session, organization_id: str, invoice_id: str) -> Invoice:
    invoice = db.scalars(_base_query().where(Invoice.id == invoice_id, Invoice.organization_id == organization_id)).first()
    if invoice is None:
        raise EntityNotFoundError("Invoice", invoice_id)
    return invoice


def get_invoice_by_token(db: Session, token: str) -> Invoice:
    from backend.app.core.tenant_context import set_tenant_context, system_context
    with system_context():
        invoice = db.scalars(_base_query().where(Invoice.public_token == token)).first()
    if invoice is None or invoice.status == InvoiceStatus.DRAFT:
        raise EntityNotFoundError("Invoice", token)
    set_tenant_context(invoice.organization_id)
    return invoice


def get_customer(db: Session, organization_id: str, customer_id: str) -> Customer:
    customer = db.scalars(select(Customer).where(Customer.id == customer_id, Customer.organization_id == organization_id)).first()
    if customer is None:
        raise EntityNotFoundError("Customer", customer_id)
    return customer


def list_invoices(
    db: Session,
    organization_id: str,
    params: PageParams,
    *,
    search: Optional[str] = None,
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    overdue_only: bool = False,
):
    stmt = _base_query().where(Invoice.organization_id == organization_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.join(Customer, Customer.id == Invoice.customer_id).where(
            or_(Invoice.invoice_number.ilike(like), Customer.display_name.ilike(like), Customer.company_name.ilike(like))
        )
    if status:
        try:
            stmt = stmt.where(Invoice.status == InvoiceStatus(status.strip().lower()))
        except ValueError:
            raise ValidationAppError("Unknown invoice status.", {"fields": {"status": "invalid"}})
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if subscription_id:
        stmt = stmt.where(Invoice.subscription_id == subscription_id)
    if date_from:
        stmt = stmt.where(Invoice.issue_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.issue_date <= date_to)
    if overdue_only:
        today = timezones.org_today_for_id(db, organization_id)
        stmt = stmt.where(
            or_(
                Invoice.status == InvoiceStatus.OVERDUE,
                (Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]) & (Invoice.due_date < today)),
            )
        )
    stmt = apply_sort(stmt, Invoice, params.sort, INVOICE_SORT_FIELDS, "-created_at")
    return paginate(db, stmt, params)


# --- creation ----------------------------------------------------------------------------------------


def attach_hsn_codes(db: Session, organization_id: str, lines: Sequence[LineInput]) -> None:
    """Fill each line's HSN/SAC from its product.

    HSN/SAC is a mandatory field on a GST tax invoice and belongs to the product,
    so it is resolved server-side rather than trusted from the request. Lines that
    already carry a code (e.g. copied from a quote) keep it.
    """
    missing = {l.product_id for l in lines if l.product_id and not l.hsn_sac_code}
    if not missing:
        return
    codes = dict(
        db.execute(
            select(Product.id, Product.hsn_sac_code).where(
                Product.organization_id == organization_id, Product.id.in_(missing)
            )
        ).all()
    )
    for line in lines:
        if line.product_id and not line.hsn_sac_code:
            line.hsn_sac_code = codes.get(line.product_id)


def create_invoice_record(
    db: Session,
    *,
    organization_id: str,
    customer: Customer,
    lines: Sequence[LineInput],
    issue_date: Optional[date] = None,
    due_date: Optional[date] = None,
    currency: Optional[str] = None,
    discount_pct=0,
    notes: Optional[str] = None,
    terms: Optional[str] = None,
    subscription_id: Optional[str] = None,
    quote_id: Optional[str] = None,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    created_by_id: Optional[str] = None,
    status: InvoiceStatus = InvoiceStatus.DRAFT,
) -> Invoice:
    """Low-level: build and flush a numbered invoice. No audit, no commit (callers do both)."""
    organization = db.get(Organization, organization_id)
    # Place of supply and the CGST/SGST/IGST split are resolved once, here, and
    # frozen onto the invoice: a later edit to the customer's address must not
    # silently restate an issued tax invoice.
    supply = gst.resolve_supply(organization, customer)
    attach_hsn_codes(db, organization_id, list(lines))
    try:
        totals = compute_totals(lines, discount_pct, supply=supply)
    except ValueError as exc:
        raise ValidationAppError(str(exc), {"fields": {"items": str(exc)}})
    issue_date = issue_date or timezones.org_today(organization)
    if due_date is None:
        due_date = issue_date + timedelta(days=int(customer.payment_terms_days or 0))
    if due_date < issue_date:
        raise ValidationAppError("due_date cannot be before issue_date.", {"fields": {"due_date": "before issue_date"}})
    invoice = Invoice(
        organization_id=organization_id,
        invoice_number=next_number(db, organization_id, "invoice"),
        customer_id=customer.id,
        subscription_id=subscription_id,
        quote_id=quote_id,
        status=status,
        issue_date=issue_date,
        due_date=due_date,
        currency=(currency or customer.currency or (organization.default_currency if organization else None) or "INR").upper(),
        subtotal=totals.subtotal,
        discount_pct=totals.discount_pct,
        discount_amount=totals.discount_amount,
        tax_amount=totals.tax_amount,
        cgst_amount=totals.cgst_amount,
        sgst_amount=totals.sgst_amount,
        igst_amount=totals.igst_amount,
        supply_type=supply.supply_type,
        place_of_supply_code=supply.place_of_supply_code,
        place_of_supply_name=supply.place_of_supply_name,
        customer_gstin=supply.customer_gstin,
        supplier_gstin=(organization.gstin if organization else None),
        total=totals.total,
        amount_paid=Decimal("0.00"),
        amount_due=totals.total,
        notes=notes if notes is not None else (organization.invoice_notes if organization else None),
        terms=terms if terms is not None else (organization.invoice_terms if organization else None),
        public_token=generate_opaque_token(),
        period_start=period_start,
        period_end=period_end,
        created_by_id=created_by_id,
        sent_at=utcnow() if status == InvoiceStatus.SENT else None,
    )
    for line in totals.lines:
        invoice.items.append(
            InvoiceItem(
                organization_id=organization_id,
                offering_id=line.offering_id,
                product_id=line.product_id,
                plan_id=line.plan_id,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_rate_pct=line.tax_rate_pct,
                amount=line.amount,
                cgst_amount=line.cgst_amount,
                sgst_amount=line.sgst_amount,
                igst_amount=line.igst_amount,
                cgst_rate_pct=line.cgst_rate_pct,
                sgst_rate_pct=line.sgst_rate_pct,
                igst_rate_pct=line.igst_rate_pct,
                hsn_sac_code=line.hsn_sac_code,
                position=line.position,
                pricing_explanation=line.pricing_explanation,
            )
        )
    db.add(invoice)
    db.flush()
    if status == InvoiceStatus.SENT:
        _emit_invoice_event(db, invoice, "invoice.issued")
    return invoice


def _approved_invoice_discount_request_exists(db: Session, invoice: Invoice) -> bool:
    from backend.app.models.governance import ApprovalRequest, ApprovalStatus, ApprovalType

    stmt = select(ApprovalRequest.id).where(
        ApprovalRequest.organization_id == invoice.organization_id,
        ApprovalRequest.type == ApprovalType.INVOICE_DISCOUNT,
        ApprovalRequest.entity_id == invoice.id,
        ApprovalRequest.status == ApprovalStatus.APPROVED,
    )
    return db.scalars(stmt).first() is not None


def _pending_invoice_discount_request_exists(db: Session, invoice: Invoice) -> bool:
    from backend.app.models.governance import ApprovalRequest, ApprovalStatus, ApprovalType

    stmt = select(ApprovalRequest.id).where(
        ApprovalRequest.organization_id == invoice.organization_id,
        ApprovalRequest.type == ApprovalType.INVOICE_DISCOUNT,
        ApprovalRequest.entity_id == invoice.id,
        ApprovalRequest.status == ApprovalStatus.PENDING,
    )
    return db.scalars(stmt).first() is not None


def create_invoice(db: Session, ctx: CurrentContext, data: InvoiceCreate) -> Invoice:
    customer = get_customer(db, ctx.organization_id, data.customer_id)
    validate_line_references(db, ctx.organization_id, data.items)
    invoice = create_invoice_record(
        db,
        organization_id=ctx.organization_id,
        customer=customer,
        lines=line_inputs(data.items),
        issue_date=data.issue_date,
        due_date=data.due_date,
        currency=data.currency,
        discount_pct=data.discount_pct,
        notes=data.notes,
        terms=data.terms,
        created_by_id=ctx.user.id,
    )

    threshold = D(ctx.organization.discount_approval_threshold_pct or Decimal("20"))
    if D(data.discount_pct or 0) > threshold:
        from backend.app.models.governance import ApprovalRequest, ApprovalStatus, ApprovalType

        customer_name = customer.display_name if customer else ""
        discount = money_str(data.discount_pct)
        req = ApprovalRequest(
            organization_id=ctx.organization_id,
            type=ApprovalType.INVOICE_DISCOUNT,
            status=ApprovalStatus.PENDING,
            entity_type="invoice",
            entity_id=invoice.id,
            title=f"{discount}% discount on {invoice.invoice_number} for {customer_name}",
            payload={
                "invoice_number": invoice.invoice_number,
                "customer_name": customer_name,
                "discount_pct": discount,
                "threshold_pct": money_str(threshold),
                "subtotal": money_str(invoice.subtotal),
                "total": money_str(invoice.total),
            },
            requested_by_id=ctx.user.id,
        )
        db.add(req)
        db.flush()

    audit.record(
        db,
        action="INVOICE_CREATED",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        ctx=ctx,
        after=snapshot(invoice),
    )
    db.commit()
    return get_invoice(db, ctx.organization_id, invoice.id)


# --- draft edits ----------------------------------------------------------------------------------------------


def _ensure_draft(invoice: Invoice, verb: str) -> None:
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvalidStateError(f"Only draft invoices can be {verb}; this invoice is {invoice.status.value}.")


def update_invoice(db: Session, ctx: CurrentContext, invoice: Invoice, data: InvoiceUpdate) -> Invoice:
    _ensure_draft(invoice, "edited")
    if data.items is not None:
        # The stored lines (read before they are rebuilt) are the only lines of this invoice that
        # may keep an archived offering.
        retained_lines = {line.id: line.offering_id for line in invoice.items}
        validate_line_references(db, ctx.organization_id, data.items, retained_lines)
    before = snapshot(invoice)
    changes = data.model_dump(exclude_unset=True)

    if "customer_id" in changes and changes["customer_id"]:
        invoice.customer_id = get_customer(db, ctx.organization_id, changes["customer_id"]).id
    if "issue_date" in changes and changes["issue_date"]:
        invoice.issue_date = changes["issue_date"]
    if "due_date" in changes and changes["due_date"]:
        invoice.due_date = changes["due_date"]
    if invoice.due_date < invoice.issue_date:
        raise ValidationAppError("due_date cannot be before issue_date.", {"fields": {"due_date": "before issue_date"}})
    if "currency" in changes and changes["currency"]:
        invoice.currency = changes["currency"]
    if "notes" in changes:
        invoice.notes = changes["notes"]
    if "terms" in changes:
        invoice.terms = changes["terms"]

    if data.items is not None or data.discount_pct is not None:
        lines = line_inputs(data.items) if data.items is not None else line_inputs(invoice.items)
        discount = data.discount_pct if data.discount_pct is not None else invoice.discount_pct
        # A draft can change customer, so re-resolve the supply rather than reusing
        # whatever was stored when the draft was first created.
        organization = db.get(Organization, ctx.organization_id)
        customer = get_customer(db, ctx.organization_id, invoice.customer_id)
        supply = gst.resolve_supply(organization, customer)
        attach_hsn_codes(db, ctx.organization_id, lines)
        try:
            totals = compute_totals(lines, discount, supply=supply)
        except ValueError as exc:
            raise ValidationAppError(str(exc), {"fields": {"items": str(exc)}})
        if data.items is not None:
            for old in list(invoice.items):
                db.delete(old)
            invoice.items = []
            for line in totals.lines:
                invoice.items.append(
                    InvoiceItem(
                        organization_id=ctx.organization_id,
                        offering_id=line.offering_id,
                        product_id=line.product_id,
                        plan_id=line.plan_id,
                        description=line.description,
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                        tax_rate_pct=line.tax_rate_pct,
                        amount=line.amount,
                        cgst_amount=line.cgst_amount,
                        sgst_amount=line.sgst_amount,
                        igst_amount=line.igst_amount,
                        cgst_rate_pct=line.cgst_rate_pct,
                        sgst_rate_pct=line.sgst_rate_pct,
                        igst_rate_pct=line.igst_rate_pct,
                        hsn_sac_code=line.hsn_sac_code,
                        position=line.position,
                    )
                )
        invoice.subtotal = totals.subtotal
        invoice.discount_pct = totals.discount_pct
        invoice.discount_amount = totals.discount_amount
        invoice.tax_amount = totals.tax_amount
        invoice.cgst_amount = totals.cgst_amount
        invoice.sgst_amount = totals.sgst_amount
        invoice.igst_amount = totals.igst_amount
        invoice.supply_type = supply.supply_type
        invoice.place_of_supply_code = supply.place_of_supply_code
        invoice.place_of_supply_name = supply.place_of_supply_name
        invoice.customer_gstin = supply.customer_gstin
        invoice.total = totals.total
        invoice.amount_due = q2(totals.total - D(invoice.amount_paid))

        threshold = D(ctx.organization.discount_approval_threshold_pct or Decimal("20"))
        if D(invoice.discount_pct or 0) > threshold and not _approved_invoice_discount_request_exists(db, invoice):
            if not _pending_invoice_discount_request_exists(db, invoice):
                from backend.app.models.governance import ApprovalRequest, ApprovalStatus, ApprovalType

                cust = db.get(Customer, invoice.customer_id)
                cust_name = cust.display_name if cust else ""
                disc = money_str(invoice.discount_pct)
                req = ApprovalRequest(
                    organization_id=ctx.organization_id,
                    type=ApprovalType.INVOICE_DISCOUNT,
                    status=ApprovalStatus.PENDING,
                    entity_type="invoice",
                    entity_id=invoice.id,
                    title=f"{disc}% discount on {invoice.invoice_number} for {cust_name}",
                    payload={
                        "invoice_number": invoice.invoice_number,
                        "customer_name": cust_name,
                        "discount_pct": disc,
                        "threshold_pct": money_str(threshold),
                        "subtotal": money_str(invoice.subtotal),
                        "total": money_str(invoice.total),
                    },
                    requested_by_id=ctx.user.id,
                )
                db.add(req)
                db.flush()

    invoice.updated_at = utcnow()
    db.flush()
    audit.record(
        db,
        action="INVOICE_UPDATED",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        ctx=ctx,
        before=before,
        after=snapshot(invoice),
    )
    db.commit()
    return get_invoice(db, ctx.organization_id, invoice.id)


def delete_invoice(db: Session, ctx: CurrentContext, invoice: Invoice) -> None:
    """Delete a draft invoice without leaving a hole in the GST invoice series.

    Invoice numbers are reserved when the document is created (drafts included), and
    GST requires a continuous series. So a draft may only be deleted when its number
    is the most recently issued one - the counter is then rolled back and the number
    re-used by the next invoice. Any other draft must be voided instead (a void keeps
    its number and is reported as cancelled).
    """
    _ensure_draft(invoice, "deleted")
    if not release_number_if_latest(db, invoice.organization_id, "invoice", invoice.invoice_number):
        raise InvalidStateError(
            f"Draft {invoice.invoice_number} cannot be deleted because later invoice numbers have already "
            "been issued; deleting it would leave a gap in the GST invoice series. Void it instead."
        )
    audit.record(
        db,
        action="INVOICE_DELETED",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        ctx=ctx,
        before=snapshot(invoice),
    )
    _release_billed_sources(db, invoice)
    db.delete(invoice)
    db.commit()


def _release_billed_sources(db: Session, invoice: Invoice) -> None:
    """Hand time entries and expenses billed on this invoice back so they can be re-billed.
    No commit - runs inside the caller's void/delete transaction."""
    from backend.app.services import expense_service, timesheet_service

    timesheet_service.release_time_entries_for_invoice(db, invoice.id, invoice.organization_id)
    expense_service.release_expenses_for_invoice(db, invoice.id, invoice.organization_id)


def _emit_invoice_event(db: Session, invoice: Invoice, event_type: str) -> None:
    """Queue a domain event (automation rules + outbound webhooks) in the caller's transaction."""
    from backend.app.services.outbox_processor import emit_event

    emit_event(
        db,
        invoice.organization_id,
        event_type,
        {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "customer_id": invoice.customer_id,
            "status": invoice.status.value if hasattr(invoice.status, "value") else str(invoice.status),
            "total": str(invoice.total),
            "amount_due": str(invoice.amount_due),
            "currency": invoice.currency,
        },
    )


# --- lifecycle -------------------------------------------------------------------------------------------------------


def _invoice_email(
    invoice: Invoice,
    organization: Organization,
    *,
    reminder: bool = False,
    db: Optional[Session] = None,
) -> tuple[str, str, Optional[str]]:
    pay_url = public_url_for(invoice)
    org_name = organization.legal_name or organization.name
    due = invoice.due_date.strftime("%d %b %Y") if invoice.due_date else ""
    cust_name = invoice.customer.display_name if invoice.customer else "Valued Customer"

    if db is not None:
        try:
            from backend.app.services.notification_service import (
                get_active_template,
                html_to_plain_text,
                render_template_string,
            )

            code = "payment_reminder" if reminder else "invoice_sent"
            tmpl = get_active_template(db, invoice.organization_id, code)
            if tmpl and tmpl.is_active:
                ctx = {
                    "customer_name": cust_name,
                    "company_name": org_name,
                    "invoice_number": invoice.invoice_number,
                    "invoice_date": invoice.issue_date.strftime("%d %b %Y") if invoice.issue_date else "",
                    "due_date": due,
                    "invoice_total": f"{invoice.currency} {q2(invoice.total):,.2f}",
                    "amount_due": f"{invoice.currency} {q2(invoice.amount_due):,.2f}",
                    "payment_link": pay_url,
                }
                subject = render_template_string(tmpl.subject_template or "", ctx)
                body_raw = render_template_string(tmpl.body_template, ctx)
                if "<" in body_raw:
                    return subject, html_to_plain_text(body_raw), body_raw
                return subject, body_raw, None
        except Exception as exc:
            logger.warning("Failed rendering notification template for invoice %s: %s", invoice.invoice_number, exc)

    if reminder:
        subject = f"Payment reminder: invoice {invoice.invoice_number} from {org_name}"
        intro = (
            f"This is a friendly reminder that invoice {invoice.invoice_number} for "
            f"{invoice.currency} {q2(invoice.amount_due):,.2f} was due on {due}."
        )
    else:
        subject = f"Invoice {invoice.invoice_number} from {org_name}"
        intro = (
            f"Please find attached invoice {invoice.invoice_number} for "
            f"{invoice.currency} {q2(invoice.total):,.2f}, due on {due}."
        )
    body = (
        f"Dear {cust_name},\n\n{intro}\n\n"
        f"You can view and pay the invoice online here:\n{pay_url}\n\n"
        f"Thank you,\n{org_name}"
    )

    amount_str = f"{invoice.currency} {q2(invoice.amount_due):,.2f}"
    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
    .card {{ max-width: 540px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 32px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
    .header {{ border-bottom: 1px solid #f1f5f9; padding-bottom: 16px; margin-bottom: 20px; }}
    .title {{ font-size: 20px; font-weight: 700; color: #0f172a; margin: 0 0 4px 0; }}
    .org-name {{ font-size: 14px; font-weight: 600; color: #4f46e5; }}
    .amount-box {{ text-align: center; margin: 24px 0; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }}
    .amount-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }}
    .amount-val {{ font-size: 28px; font-weight: 800; color: #0f172a; margin-top: 4px; }}
    .details {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }}
    .details td {{ padding: 8px 0; border-bottom: 1px solid #f1f5f9; }}
    .details td:last-child {{ text-align: right; font-weight: 600; color: #0f172a; }}
    .details td:first-child {{ color: #64748b; }}
    .btn {{ display: inline-block; background-color: #4f46e5; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600; font-size: 14px; text-align: center; }}
    .btn-container {{ text-align: center; margin: 24px 0; }}
    .footer {{ font-size: 12px; color: #94a3b8; text-align: center; margin-top: 24px; border-top: 1px solid #f1f5f9; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="org-name">{org_name}</div>
      <h1 class="title">Invoice {invoice.invoice_number}</h1>
    </div>
    <p>Dear {cust_name},</p>
    <p>{intro}</p>
    <div class="amount-box">
      <div class="amount-label">Amount Due</div>
      <div class="amount-val">{amount_str}</div>
    </div>
    <table class="details">
      <tr><td>Invoice Number</td><td>{invoice.invoice_number}</td></tr>
      <tr><td>Due Date</td><td>{due}</td></tr>
      <tr><td>Status</td><td>Pending Payment</td></tr>
    </table>
    <div class="btn-container">
      <a href="{pay_url}" class="btn" style="color: #ffffff;">View & Pay Invoice</a>
    </div>
    <p style="font-size: 13px; color: #64748b; text-align: center;">The official tax invoice PDF has been attached to this email for your records.</p>
    <div class="footer">
      &copy; {org_name}. All rights reserved.
    </div>
  </div>
</body>
</html>"""
    return subject, body, html_body


def _render_pdf_safe(invoice: Invoice, organization: Organization) -> Optional[bytes]:
    try:
        from backend.app.modules.invoices.invoice_pdf import render_invoice_pdf

        return render_invoice_pdf(invoice, organization)
    except Exception:  # pragma: no cover - never let PDF trouble block sending
        logger.exception("Could not render PDF for invoice %s", invoice.invoice_number)
        return None


def email_invoice(db: Session, invoice: Invoice, *, reminder: bool = False, attach_pdf: bool = True) -> bool:
    """Send the invoice (or a reminder) to the customer. Returns False when email is disabled/no address."""
    organization = db.get(Organization, invoice.organization_id)
    recipient = invoice.customer.email if invoice.customer else None
    if not recipient or organization is None:
        return False
    subject, body, html_body = _invoice_email(invoice, organization, reminder=reminder, db=db)

    smtp_cfg = None
    try:
        from backend.app.services.integrations_service import get_active_smtp_credentials
        smtp_cfg = get_active_smtp_credentials(db, invoice.organization_id)
    except Exception:
        logger.warning(
            "Tenant SMTP lookup failed for organization %s; using platform SMTP for invoice %s",
            invoice.organization_id,
            invoice.invoice_number,
            exc_info=True,
        )

    email_active = bool(smtp_cfg.get("host")) if smtp_cfg else settings.email_enabled
    attachments = []
    if attach_pdf and email_active:
        pdf = _render_pdf_safe(invoice, organization)
        if pdf:
            attachments.append((f"{invoice.invoice_number}.pdf", pdf, "application/pdf"))
    try:
        return send_email(
            recipient,
            subject,
            body,
            html_body=html_body,
            attachments=attachments,
            reply_to=organization.email,
            smtp_config=smtp_cfg,
        )
    except Exception:  # SMTP trouble must not fail the state change
        logger.exception("Email delivery failed for invoice %s", invoice.invoice_number)
        return False


def _email_and_flag_failure(db: Session, invoice: Invoice, *, reminder: bool = False) -> bool:
    """Sends the invoice email; returns True only if the org has SMTP configured
    but the send still didn't go out (a real failure worth surfacing), as
    opposed to orgs that run without email configured by choice."""
    if email_invoice(db, invoice, reminder=reminder):
        return False
    try:
        from backend.app.services.integrations_service import get_active_smtp_credentials
        cfg = get_active_smtp_credentials(db, invoice.organization_id)
    except Exception:
        logger.warning(
            "Tenant SMTP lookup failed for organization %s after invoice %s email was not sent",
            invoice.organization_id, invoice.invoice_number, exc_info=True,
        )
        cfg = None
    return bool(cfg and cfg.get("host"))


def send_invoice(db: Session, ctx: CurrentContext, invoice: Invoice) -> Invoice:
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvalidStateError(f"Only draft invoices can be sent; this invoice is {invoice.status.value}.")

    threshold = D(ctx.organization.discount_approval_threshold_pct or Decimal("20"))
    if _pending_invoice_discount_request_exists(db, invoice):
        raise InvalidStateError("Invoice is awaiting discount approval and cannot be issued.")

    if D(invoice.discount_pct or 0) > threshold and not _approved_invoice_discount_request_exists(db, invoice):
        customer = db.get(Customer, invoice.customer_id)
        customer_name = customer.display_name if customer else ""
        discount = money_str(invoice.discount_pct)
        from backend.app.models.governance import ApprovalRequest, ApprovalStatus, ApprovalType

        req = ApprovalRequest(
            organization_id=ctx.organization_id,
            type=ApprovalType.INVOICE_DISCOUNT,
            status=ApprovalStatus.PENDING,
            entity_type="invoice",
            entity_id=invoice.id,
            title=f"{discount}% discount on {invoice.invoice_number} for {customer_name}",
            payload={
                "invoice_number": invoice.invoice_number,
                "customer_name": customer_name,
                "discount_pct": discount,
                "threshold_pct": money_str(threshold),
                "subtotal": money_str(invoice.subtotal),
                "total": money_str(invoice.total),
            },
            requested_by_id=ctx.user.id,
        )
        db.add(req)
        db.flush()
        db.commit()
        raise InvalidStateError(
            f"Invoice discount of {discount}% exceeds organization threshold ({threshold}%). Approval requested."
        )

    before = snapshot(invoice)
    invoice.status = InvoiceStatus.SENT
    invoice.sent_at = utcnow()
    invoice.updated_at = utcnow()
    db.flush()
    _emit_invoice_event(db, invoice, "invoice.issued")
    email_delivery_failed = _email_and_flag_failure(db, invoice)
    audit.record(
        db,
        action="INVOICE_SENT",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        ctx=ctx,
        before=before,
        after=snapshot(invoice),
    )
    db.commit()
    result = get_invoice(db, ctx.organization_id, invoice.id)
    result._email_delivery_failed = email_delivery_failed
    return result


def send_reminder(
    db: Session,
    invoice: Invoice,
    *,
    ctx: Optional[CurrentContext] = None,
    actor_label: Optional[str] = None,
    commit: bool = True,
) -> Invoice:
    if invoice.status not in OPEN_INVOICE_STATUSES:
        raise InvalidStateError(f"Reminders can only be sent for open invoices; this invoice is {invoice.status.value}.")
    before = snapshot(invoice)
    invoice.reminder_count = int(invoice.reminder_count or 0) + 1
    invoice.last_reminder_at = utcnow()
    invoice.updated_at = utcnow()
    db.flush()
    email_delivery_failed = _email_and_flag_failure(db, invoice, reminder=True)
    audit.record(
        db,
        action="INVOICE_REMINDER_SENT",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        organization_id=invoice.organization_id,
        ctx=ctx,
        actor_label=actor_label,
        before=before,
        after=snapshot(invoice),
    )
    if commit:
        db.commit()
        result = get_invoice(db, invoice.organization_id, invoice.id)
        result._email_delivery_failed = email_delivery_failed
        return result
    invoice._email_delivery_failed = email_delivery_failed
    return invoice


def void_invoice(
    db: Session,
    ctx: Optional[CurrentContext] = None,
    invoice: Optional[Invoice] = None,
    reason: Optional[str] = None,
    *,
    approval: Optional[ApprovalRequest] = None,
    actor_label: Optional[str] = None,
    commit: bool = True,
) -> Invoice:
    """Void an unpaid invoice. `commit=False` lets background callers (dunning) void
    inside their own transaction; the invoice is returned without re-loading."""
    if approval is not None:
        invoice = db.get(Invoice, approval.entity_id)
        if invoice is None:
            raise EntityNotFoundError("Invoice", approval.entity_id)
        reason = approval.justification or (approval.decision_note if hasattr(approval, "decision_note") else None) or "Approved invoice void request"

    if invoice is None:
        raise InvalidStateError("Invoice is required to void.")
    if invoice.status == InvoiceStatus.VOID:
        raise InvalidStateError("This invoice is already void.")
    if D(invoice.amount_paid) > 0:
        raise InvalidStateError("An invoice with recorded payments or applied credits cannot be voided. Refund the payments first.")

    before = snapshot(invoice)
    invoice.status = InvoiceStatus.VOID
    invoice.voided_at = utcnow()
    invoice.void_reason = (reason or "Voided").strip()
    invoice.amount_due = Decimal("0.00")
    invoice.updated_at = utcnow()
    _release_billed_sources(db, invoice)
    db.flush()
    _emit_invoice_event(db, invoice, "invoice.voided")

    actor_label = actor_label or (ctx.user.full_name if ctx and ctx.user else audit.SYSTEM_ACTOR)
    audit.record(
        db,
        action="INVOICE_VOIDED",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        ctx=ctx,
        actor_label=actor_label,
        organization_id=invoice.organization_id,
        before=before,
        after=snapshot(invoice),
    )
    if not commit:
        return invoice
    db.commit()
    org_id = ctx.organization_id if ctx else invoice.organization_id
    return get_invoice(db, org_id, invoice.id)


def mark_overdue(
    db: Session,
    invoice: Invoice,
    *,
    actor_label: str = audit.SYSTEM_ACTOR,
    today: Optional[date] = None,
) -> bool:
    """Scheduler step (c): flip an open invoice past its due date to overdue. No commit.

    "Past due" is judged against the organization's local business day (the same day the
    scheduler uses), never the server's UTC date."""
    today = today or timezones.org_today_for_id(db, invoice.organization_id)
    if invoice.status not in (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID) or invoice.due_date >= today:
        return False
    before = snapshot(invoice)
    invoice.status = InvoiceStatus.OVERDUE
    invoice.updated_at = utcnow()
    _emit_invoice_event(db, invoice, "invoice.overdue")
    audit.record(
        db,
        action="INVOICE_MARKED_OVERDUE",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        organization_id=invoice.organization_id,
        actor_label=actor_label,
        before=before,
        after=snapshot(invoice),
        status=audit.AuditStatus.WARNING,
    )
    if invoice.subscription_id:
        subscription = db.get(Subscription, invoice.subscription_id)
        if subscription is not None and subscription.status == SubscriptionStatus.ACTIVE:
            sub_before = audit.snapshot(subscription, ("subscription_number", "status"))
            subscription.status = SubscriptionStatus.PAST_DUE
            subscription.updated_at = utcnow()
            audit.record(
                db,
                action="SUBSCRIPTION_UPDATED",
                entity_type="subscription",
                entity_id=subscription.id,
                entity_label=subscription.subscription_number,
                organization_id=invoice.organization_id,
                actor_label=actor_label,
                before=sub_before,
                after=audit.snapshot(subscription, ("subscription_number", "status")),
                status=audit.AuditStatus.WARNING,
            )
    return True


# --- amounts / status recomputation ---------------------------------------------------------------------------------


def allocated_total(db: Session, invoice_id: str) -> Decimal:
    db.flush()
    value = db.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(PaymentAllocation.invoice_id == invoice_id, Payment.status.in_(SETTLED_PAYMENT_STATUSES))
    )
    return q2(value or 0)


def credited_total(db: Session, invoice_id: str) -> Decimal:
    """Credit-note amounts applied to the invoice (they settle it just like payments)."""
    from backend.app.models.credits import CreditApplication

    db.flush()
    value = db.scalar(
        select(func.coalesce(func.sum(CreditApplication.amount), 0)).where(CreditApplication.invoice_id == invoice_id)
    )
    return q2(value or 0)


def lock_invoice(db: Session, invoice: Invoice) -> Invoice:
    """SELECT ... FOR UPDATE on the invoice row, then reload it (no-op locking on SQLite).

    Every path that allocates money or credit to an invoice takes this lock before it
    reads amount_due, so two different payments / credit notes settling the same
    invoice at once serialise and the second sees the first's allocation instead of
    over-applying. Lock order: organization (numbering) -> payment / credit note /
    checkout session -> invoice.
    """
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        db.execute(select(Invoice.id).where(Invoice.id == invoice.id).with_for_update())
    if db.is_modified(invoice):
        db.flush()  # never let the reload discard this transaction's pending changes
    db.refresh(invoice)
    return invoice


def recompute_invoice(
    db: Session,
    invoice: Invoice,
    *,
    ctx: Optional[CurrentContext] = None,
    actor_label: Optional[str] = None,
) -> Invoice:
    """Re-derive amount_paid/amount_due/status from payment allocations plus applied
    credit notes. Writes INVOICE_PAID when it becomes paid. No commit."""
    if invoice.status in (InvoiceStatus.DRAFT, InvoiceStatus.VOID):
        return invoice
    before = snapshot(invoice)
    previous_status = invoice.status
    paid = q2(allocated_total(db, invoice.id) + credited_total(db, invoice.id))
    total = q2(invoice.total)
    invoice.amount_paid = paid
    invoice.amount_due = q2(max(Decimal("0"), total - paid))
    today = timezones.org_today_for_id(db, invoice.organization_id)

    if invoice.amount_due == 0:
        invoice.status = InvoiceStatus.PAID
        if invoice.paid_at is None:
            invoice.paid_at = utcnow()
    elif paid > 0:
        invoice.paid_at = None
        invoice.status = InvoiceStatus.PARTIALLY_PAID
    else:
        invoice.paid_at = None
        invoice.status = InvoiceStatus.OVERDUE if invoice.due_date < today else InvoiceStatus.SENT
    invoice.updated_at = utcnow()
    db.flush()

    if invoice.status != previous_status and invoice.status in (InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID):
        _emit_invoice_event(
            db, invoice, "invoice.paid" if invoice.status == InvoiceStatus.PAID else "invoice.partially_paid"
        )
    if invoice.status == InvoiceStatus.PAID and previous_status != InvoiceStatus.PAID:
        audit.record(
            db,
            action="INVOICE_PAID",
            entity_type="invoice",
            entity_id=invoice.id,
            entity_label=invoice.invoice_number,
            organization_id=invoice.organization_id,
            ctx=ctx,
            actor_label=actor_label,
            before=before,
            after=snapshot(invoice),
        )
        _reactivate_subscription_if_clear(db, invoice, ctx=ctx, actor_label=actor_label)
    return invoice


def _reactivate_subscription_if_clear(
    db: Session, invoice: Invoice, *, ctx: Optional[CurrentContext], actor_label: Optional[str]
) -> None:
    """A past_due subscription goes back to active once none of its invoices are overdue."""
    if not invoice.subscription_id:
        return
    subscription = db.get(Subscription, invoice.subscription_id)
    if subscription is None or subscription.status != SubscriptionStatus.PAST_DUE:
        return
    still_overdue = db.scalar(
        select(func.count()).select_from(Invoice).where(
            Invoice.subscription_id == subscription.id,
            Invoice.status == InvoiceStatus.OVERDUE,
        )
    )
    if still_overdue:
        return
    before = audit.snapshot(subscription, ("subscription_number", "status"))
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.updated_at = utcnow()
    audit.record(
        db,
        action="SUBSCRIPTION_UPDATED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        organization_id=invoice.organization_id,
        ctx=ctx,
        actor_label=actor_label,
        before=before,
        after=audit.snapshot(subscription, ("subscription_number", "status")),
    )


def get_invoices_summary(db: Session, organization_id: str) -> Dict[str, Any]:
    """Calculate summary KPIs and status counts for invoices.

    Counts cover every invoice. Money is never summed across currencies:
    `total_outstanding` / `total_revenue` are in `currency` (the organization's base
    currency) and `by_currency` lists the same figures for every currency.
    """
    rows = db.execute(
        select(
            Invoice.status,
            Invoice.currency,
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.total), Decimal("0")),
            func.coalesce(func.sum(Invoice.amount_paid), Decimal("0")),
            func.coalesce(func.sum(Invoice.amount_due), Decimal("0")),
        )
        .where(Invoice.organization_id == organization_id)
        .group_by(Invoice.status, Invoice.currency)
    ).all()

    counts = {s.value: 0 for s in InvoiceStatus}
    money: Dict[str, Dict[str, Any]] = {}

    for status_val, currency, count, total, amount_paid, amount_due in rows:
        s = status_val.value if hasattr(status_val, "value") else str(status_val)
        counts[s] = counts.get(s, 0) + count
        cur = money.setdefault(
            currency_totals.norm(currency), {"count": 0, "total_revenue": Decimal("0"), "total_outstanding": Decimal("0")}
        )
        cur["count"] += count
        if s in ("partially_paid", "paid", "overdue"):
            cur["total_revenue"] += amount_paid
        if s in ("sent", "partially_paid", "overdue"):
            cur["total_outstanding"] += amount_due

    base = currency_totals.org_base_currency(db, organization_id)
    by_currency = [
        {
            "currency": cur,
            "count": money[cur]["count"],
            "total_outstanding": str(q2(money[cur]["total_outstanding"])),
            "total_revenue": str(q2(money[cur]["total_revenue"])),
        }
        for cur in currency_totals.order_currencies(money, base)
    ]
    base_row = next((row for row in by_currency if row["currency"] == base), None)
    return {
        "total_invoices": sum(counts.values()),
        "draft_count": counts["draft"],
        "sent_count": counts["sent"],
        "partially_paid_count": counts["partially_paid"],
        "paid_count": counts["paid"],
        "overdue_count": counts["overdue"],
        "void_count": counts["void"],
        "currency": base,
        "total_outstanding": base_row["total_outstanding"] if base_row else "0.00",
        "total_revenue": base_row["total_revenue"] if base_row else "0.00",
        "by_currency": by_currency,
    }


__all__ = [
    "serialize_invoice",
    "recompute_invoice",
    "credited_total",
    "create_invoice_record",
    "create_invoice",
    "update_invoice",
    "delete_invoice",
    "send_invoice",
    "send_reminder",
    "void_invoice",
    "mark_overdue",
    "get_invoice",
    "get_invoice_by_token",
    "list_invoices",
    "get_invoices_summary",
    "line_inputs",
    "days_overdue",
    "as_utc",
    "SETTLED_PAYMENT_STATUSES",
]
