"""Credit note and credit application service."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
from backend.app.models.credits import (
    CreditApplication,
    CreditNote,
    CreditNoteLine,
    CreditNoteStatus,
)
from backend.app.models.events import DomainEventType
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.customers import Customer
from backend.app.models.base import utcnow
from backend.app.models.identity import Organization
from backend.app.services import audit, gst, timezones
from backend.app.services.numbering import next_number
from backend.app.services.unit_of_work import UnitOfWork


def _next_credit_note_number(db: Session, organization_id: str) -> str:
    """Next credit note number from the locked per-organization series (never count+1,
    which hands out duplicates under concurrency and after any gap)."""
    return next_number(db, organization_id, "credit_note")


def _supply_for(db: Session, organization_id: str, customer: Customer, invoice: Optional[Invoice]) -> gst.SupplyContext:
    """A credit note follows the tax treatment of the invoice it corrects (frozen at
    that invoice's issue); a standalone credit note uses the current org/customer."""
    if invoice is not None and invoice.supply_type:
        return gst.SupplyContext(
            supply_type=invoice.supply_type,
            supplier_state_code=gst.state_code_from_gstin(invoice.supplier_gstin),
            place_of_supply_code=invoice.place_of_supply_code,
            place_of_supply_name=invoice.place_of_supply_name,
            customer_gstin=invoice.customer_gstin,
            is_gst_registered=bool(invoice.customer_gstin),
        )
    organization = db.get(Organization, organization_id)
    return gst.resolve_supply(organization, customer)


def create_credit_note(
    db: Session,
    ctx: Optional[CurrentContext] = None,
    *,
    customer_id: str,
    lines: List[Dict[str, Any]],
    reason: Optional[str] = None,
    invoice_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    issue_date: Optional[date] = None,
    currency: str = "INR",
    status: CreditNoteStatus = CreditNoteStatus.ISSUED,
    organization_id: Optional[str] = None,
    created_by_id: Optional[str] = None,
    actor_label: Optional[str] = None,
) -> CreditNote:
    """Create a new credit note for a customer.

    Pass `ctx` for an interactive request. Background/system callers (no logged-in
    user) pass `organization_id` and, optionally, `actor_label` instead - mirrors
    the ctx-or-organization_id+actor_label convention `audit.record` already uses.
    """
    org_id = organization_id or (ctx.organization_id if ctx else None)
    if not org_id:
        raise ValidationAppError("organization_id or ctx is required.")

    customer = db.scalars(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.organization_id == org_id,
        )
    ).first()
    if customer is None:
        raise NotFoundAppError("Customer not found.")

    if not lines:
        raise ValidationAppError("At least one credit note line is required.")

    invoice = None
    if invoice_id:
        invoice = db.scalars(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.organization_id == org_id)
        ).first()
        if invoice is None:
            raise NotFoundAppError("Invoice not found.")
        if invoice.customer_id != customer.id:
            raise ConflictAppError("The linked invoice belongs to a different customer.")
        if invoice.status == InvoiceStatus.DRAFT:
            raise ConflictAppError("A credit note cannot reference a draft invoice.")
        currency = invoice.currency or currency
    supply = _supply_for(db, org_id, customer, invoice)

    cn_number = _next_credit_note_number(db, org_id)
    credit_note = CreditNote(
        organization_id=org_id,
        credit_note_number=cn_number,
        customer_id=customer.id,
        invoice_id=invoice_id,
        subscription_id=subscription_id,
        status=status,
        reason=reason,
        issue_date=issue_date or timezones.org_today_for_id(db, org_id),
        currency=currency,
        created_by_id=created_by_id if created_by_id is not None else (ctx.user_id if ctx else None),
        supply_type=supply.supply_type,
        place_of_supply_code=supply.place_of_supply_code,
        place_of_supply_name=supply.place_of_supply_name,
        customer_gstin=supply.customer_gstin,
        supplier_gstin=(invoice.supplier_gstin if invoice is not None else getattr(db.get(Organization, org_id), "gstin", None)),
    )

    subtotal = Decimal("0")
    total_tax = Decimal("0")
    cgst_total = sgst_total = igst_total = Decimal("0")

    for idx, item in enumerate(lines):
        qty = Decimal(str(item.get("quantity", 1)))
        price = Decimal(str(item.get("unit_price", 0)))
        tax_pct = Decimal(str(item.get("tax_rate_pct", 0)))
        if "amount" in item and price == Decimal("0"):
            line_amount = Decimal(str(item["amount"])).quantize(Decimal("0.01"))
            price = (line_amount / qty).quantize(Decimal("0.01"))
        else:
            line_amount = (qty * price).quantize(Decimal("0.01"))
        if supply.is_export:
            tax_pct = Decimal("0")  # zero-rated export, same as the invoice side
        line_tax = (line_amount * tax_pct / Decimal("100")).quantize(Decimal("0.01"))
        split = gst.split_tax(line_tax, supply)

        subtotal += line_amount
        total_tax += line_tax
        cgst_total += split.cgst
        sgst_total += split.sgst
        igst_total += split.igst

        cn_line = CreditNoteLine(
            organization_id=org_id,
            description=item.get("description", "Credit adjustment"),
            quantity=qty,
            unit_price=price,
            tax_rate_pct=tax_pct,
            amount=line_amount,
            cgst_amount=split.cgst,
            sgst_amount=split.sgst,
            igst_amount=split.igst,
            position=idx,
        )
        credit_note.lines.append(cn_line)

    total = subtotal + total_tax
    credit_note.subtotal = subtotal
    credit_note.tax_amount = total_tax
    credit_note.cgst_amount = cgst_total
    credit_note.sgst_amount = sgst_total
    credit_note.igst_amount = igst_total
    credit_note.total = total
    credit_note.balance_remaining = total

    db.add(credit_note)
    db.flush()

    uow = UnitOfWork(db)
    uow.register_event(
        organization_id=org_id,
        event_type=DomainEventType.CREDIT_NOTE_ISSUED,
        aggregate_type="credit_note",
        aggregate_id=credit_note.id,
        payload={
            "credit_note_number": credit_note.credit_note_number,
            "customer_id": credit_note.customer_id,
            "total": str(credit_note.total),
            "currency": credit_note.currency,
        },
    )

    audit.record(
        db,
        action="CREDIT_NOTE_CREATED",
        entity_type="credit_note",
        entity_id=credit_note.id,
        entity_label=credit_note.credit_note_number,
        organization_id=org_id,
        ctx=ctx,
        actor_label=actor_label,
        after={"total": str(credit_note.total), "customer_id": credit_note.customer_id},
    )

    db.commit()
    db.refresh(credit_note)
    return credit_note


def apply_credit_note_to_invoice(
    db: Session,
    ctx: Optional[CurrentContext] = None,
    *,
    credit_note_id: str,
    invoice_id: str,
    amount: Decimal,
    notes: Optional[str] = None,
    organization_id: Optional[str] = None,
    actor_label: Optional[str] = None,
) -> CreditApplication:
    """Apply an available credit note amount toward an unpaid invoice balance.

    Pass `ctx` for an interactive request, or `organization_id` (+ optional
    `actor_label`) for a background/system caller - same convention as
    create_credit_note above.
    """
    org_id = organization_id or (ctx.organization_id if ctx else None)
    if not org_id:
        raise ValidationAppError("organization_id or ctx is required.")

    # Lock the credit note row: two concurrent applications must not both spend the
    # same balance_remaining.
    cn_stmt = (
        select(CreditNote)
        .where(
            CreditNote.id == credit_note_id,
            CreditNote.organization_id == org_id,
        )
        .execution_options(populate_existing=True)
    )
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        cn_stmt = cn_stmt.with_for_update()
    credit_note = db.scalars(cn_stmt).first()
    if credit_note is None:
        raise NotFoundAppError("Credit note not found.")

    if credit_note.status in (CreditNoteStatus.VOID, CreditNoteStatus.DRAFT):
        raise ConflictAppError(f"Cannot apply a credit note in '{credit_note.status.value}' status.")

    if amount <= Decimal("0"):
        raise ValidationAppError("Application amount must be greater than zero.")

    if amount > credit_note.balance_remaining:
        raise ConflictAppError(
            f"Requested amount ({amount}) exceeds available credit note balance ({credit_note.balance_remaining})."
        )

    invoice = db.scalars(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.organization_id == org_id,
        )
    ).first()
    if invoice is None:
        raise NotFoundAppError("Invoice not found.")
    # Lock the invoice too (after the credit note): two different credit notes applied
    # to the same invoice at once must not both consume its full amount_due.
    from backend.app.services.invoice_service import lock_invoice

    lock_invoice(db, invoice)

    if invoice.customer_id != credit_note.customer_id:
        raise ConflictAppError("Credit note customer does not match the invoice customer.")

    if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.VOID, InvoiceStatus.DRAFT):
        raise ConflictAppError(f"Cannot apply credit to an invoice in '{invoice.status.value}' status.")

    if amount > invoice.amount_due:
        raise ConflictAppError(
            f"Requested amount ({amount}) exceeds outstanding invoice balance ({invoice.amount_due})."
        )

    # Apply amounts
    credit_note.balance_remaining = (credit_note.balance_remaining - amount).quantize(Decimal("0.01"))
    if credit_note.balance_remaining == Decimal("0"):
        credit_note.status = CreditNoteStatus.APPLIED
    else:
        credit_note.status = CreditNoteStatus.PARTIALLY_APPLIED

    application = CreditApplication(
        organization_id=org_id,
        credit_note_id=credit_note.id,
        invoice_id=invoice.id,
        amount=amount,
        notes=notes,
    )
    db.add(application)
    db.flush()
    # The invoice's paid/due/status are derived (payments + credit applications) so a
    # later payment recompute can never erase the credit.
    from backend.app.services.invoice_service import recompute_invoice

    recompute_invoice(db, invoice, ctx=ctx, actor_label=actor_label)

    uow = UnitOfWork(db)
    uow.register_event(
        organization_id=org_id,
        event_type=DomainEventType.CREDIT_NOTE_APPLIED,
        aggregate_type="credit_note",
        aggregate_id=credit_note.id,
        payload={
            "credit_note_id": credit_note.id,
            "invoice_id": invoice.id,
            "amount": str(amount),
            "remaining_balance": str(credit_note.balance_remaining),
        },
    )
    if invoice.status == InvoiceStatus.PAID:
        uow.register_event(
            organization_id=org_id,
            event_type=DomainEventType.INVOICE_PAID,
            aggregate_type="invoice",
            aggregate_id=invoice.id,
            payload={"invoice_number": invoice.invoice_number, "paid_via": "credit_note"},
        )

    audit.record(
        db,
        action="CREDIT_NOTE_APPLIED",
        entity_type="credit_note",
        entity_id=credit_note.id,
        entity_label=credit_note.credit_note_number,
        organization_id=org_id,
        ctx=ctx,
        actor_label=actor_label,
        after={"amount": str(amount), "invoice_id": invoice.id},
    )

    db.commit()
    db.refresh(application)
    return application


def void_credit_note(
    db: Session,
    ctx: CurrentContext,
    credit_note_id: str,
    reason: Optional[str] = None,
) -> CreditNote:
    """Void an unapplied credit note."""
    credit_note = db.scalars(
        select(CreditNote)
        .options(selectinload(CreditNote.applications))
        .where(
            CreditNote.id == credit_note_id,
            CreditNote.organization_id == ctx.organization_id,
        )
    ).first()
    if credit_note is None:
        raise NotFoundAppError("Credit note not found.")

    if credit_note.status == CreditNoteStatus.VOID:
        return credit_note

    if credit_note.applications:
        raise ConflictAppError("Cannot void a credit note that has already been applied to invoices.")

    credit_note.status = CreditNoteStatus.VOID
    credit_note.voided_at = utcnow()
    credit_note.void_reason = reason
    credit_note.balance_remaining = Decimal("0")

    uow = UnitOfWork(db)
    uow.register_event(
        organization_id=ctx.organization_id,
        event_type=DomainEventType.CREDIT_NOTE_VOIDED,
        aggregate_type="credit_note",
        aggregate_id=credit_note.id,
        payload={"credit_note_number": credit_note.credit_note_number, "reason": reason},
    )

    audit.record(
        db,
        action="CREDIT_NOTE_VOIDED",
        entity_type="credit_note",
        entity_id=credit_note.id,
        entity_label=credit_note.credit_note_number,
        ctx=ctx,
        after={"reason": reason},
    )

    db.commit()
    db.refresh(credit_note)
    return credit_note


def get_credit_note(db: Session, organization_id: str, credit_note_id: str) -> CreditNote:
    cn = db.scalars(
        select(CreditNote)
        .options(
            selectinload(CreditNote.customer),
            selectinload(CreditNote.lines),
            selectinload(CreditNote.applications).selectinload(CreditApplication.invoice),
        )
        .where(
            CreditNote.id == credit_note_id,
            CreditNote.organization_id == organization_id,
        )
    ).first()
    if cn is None:
        raise NotFoundAppError("Credit note not found.")
    return cn


def _credit_note_filters(
    organization_id: str,
    customer_id: Optional[str] = None,
    status_: Optional[CreditNoteStatus] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list:
    conds = [CreditNote.organization_id == organization_id]
    if customer_id:
        conds.append(CreditNote.customer_id == customer_id)
    if status_:
        conds.append(CreditNote.status == status_)
    if date_from:
        conds.append(CreditNote.issue_date >= date_from)
    if date_to:
        conds.append(CreditNote.issue_date <= date_to)
    return conds


def list_credit_notes(
    db: Session,
    organization_id: str,
    customer_id: Optional[str] = None,
    status_: Optional[CreditNoteStatus] = None,
    limit: int = 50,
    offset: int = 0,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> List[CreditNote]:
    conds = _credit_note_filters(organization_id, customer_id, status_, date_from, date_to)
    query = (
        select(CreditNote)
        .options(selectinload(CreditNote.customer), selectinload(CreditNote.lines))
        .where(*conds)
        .order_by(desc(CreditNote.created_at), desc(CreditNote.id))
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(query).all())


def count_credit_notes(
    db: Session,
    organization_id: str,
    customer_id: Optional[str] = None,
    status_: Optional[CreditNoteStatus] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> int:
    """Total rows matching the list filters (independent of limit/offset)."""
    conds = _credit_note_filters(organization_id, customer_id, status_, date_from, date_to)
    return int(db.scalar(select(func.count(CreditNote.id)).where(*conds)) or 0)


def credit_notes_summary(
    db: Session,
    organization_id: str,
    customer_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> Dict[str, Any]:
    """Money totals for credit notes, grouped by currency (amounts in different
    currencies are never added together).

    Business rules (mirroring create/apply/void above):
      * issued      = total of every non-draft, non-void note (ISSUED, PARTIALLY_APPLIED, APPLIED);
      * applied     = sum of credit applications of those notes;
      * remaining   = sum of balance_remaining of those notes (spendable credit);
      * voided      = total of VOID notes (they never count as issued or remaining);
      * draft       = total of DRAFT notes (not yet issued).
    Filters: customer, issue_date between date_from and date_to (inclusive).
    Two aggregate queries regardless of the number of notes.
    """
    conds = _credit_note_filters(organization_id, customer_id, None, date_from, date_to)
    zero = Decimal("0.00")

    rows = db.execute(
        select(
            CreditNote.currency,
            CreditNote.status,
            func.count(CreditNote.id),
            func.coalesce(func.sum(CreditNote.total), 0),
            func.coalesce(func.sum(CreditNote.balance_remaining), 0),
        )
        .where(*conds)
        .group_by(CreditNote.currency, CreditNote.status)
    ).all()

    applied_rows = db.execute(
        select(CreditNote.currency, func.coalesce(func.sum(CreditApplication.amount), 0))
        .join(CreditApplication, CreditApplication.credit_note_id == CreditNote.id)
        .where(
            *conds,
            CreditApplication.organization_id == organization_id,
            CreditNote.status.notin_([CreditNoteStatus.VOID, CreditNoteStatus.DRAFT]),
        )
        .group_by(CreditNote.currency)
    ).all()

    def _money(v: Any) -> Decimal:
        return Decimal(str(v or 0)).quantize(Decimal("0.01"))

    count_by_status: Dict[str, int] = {s.value: 0 for s in CreditNoteStatus}
    per_currency: Dict[str, Dict[str, Any]] = {}
    for currency, status, count, total, remaining in rows:
        cur = (currency or "INR").upper()
        status_value = status.value if hasattr(status, "value") else str(status)
        bucket = per_currency.setdefault(
            cur,
            {
                "currency": cur,
                "count": 0,
                "issued_total": zero,
                "applied_total": zero,
                "remaining_balance": zero,
                "voided_total": zero,
                "draft_total": zero,
                "count_by_status": {s.value: 0 for s in CreditNoteStatus},
            },
        )
        bucket["count"] += int(count)
        bucket["count_by_status"][status_value] += int(count)
        count_by_status[status_value] += int(count)
        if status_value == CreditNoteStatus.VOID.value:
            bucket["voided_total"] += _money(total)
        elif status_value == CreditNoteStatus.DRAFT.value:
            bucket["draft_total"] += _money(total)
        else:
            bucket["issued_total"] += _money(total)
            bucket["remaining_balance"] += _money(remaining)
    for currency, applied in applied_rows:
        cur = (currency or "INR").upper()
        if cur in per_currency:
            per_currency[cur]["applied_total"] += _money(applied)

    currencies = []
    for cur in sorted(per_currency):
        b = per_currency[cur]
        currencies.append({k: (str(v) if isinstance(v, Decimal) else v) for k, v in b.items()})

    return {
        "total_count": sum(count_by_status.values()),
        "count_by_status": count_by_status,
        "currencies": currencies,
        "filters": {
            "customer_id": customer_id,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    }


def serialize_credit_note(cn: CreditNote) -> Dict[str, Any]:
    from backend.app.schemas.common_refs import customer_ref, money_str

    return {
        "id": cn.id,
        "credit_note_number": cn.credit_note_number,
        "customer_id": cn.customer_id,
        "customer": customer_ref(cn.customer) if cn.customer else None,
        "status": cn.status,
        "currency": cn.currency,
        "invoice_id": cn.invoice_id,
        "subtotal": money_str(cn.subtotal),
        "tax_amount": money_str(cn.tax_amount),
        "cgst_amount": money_str(cn.cgst_amount),
        "sgst_amount": money_str(cn.sgst_amount),
        "igst_amount": money_str(cn.igst_amount),
        "supply_type": cn.supply_type,
        "place_of_supply_name": cn.place_of_supply_name,
        "total": money_str(cn.total),
        "balance_remaining": money_str(cn.balance_remaining),
        "reason": cn.reason,
        "notes": cn.notes,
        "reference": getattr(cn, "reference", None),
        "created_at": cn.created_at,
        "lines": [
            {
                "id": line.id,
                "description": line.description,
                "amount": money_str(line.amount),
                "quantity": str(line.quantity),
                "unit_price": money_str(line.unit_price),
                "tax_rate_pct": str(line.tax_rate_pct),
            }
            for line in (cn.lines or [])
        ],
        "applications": [
            {
                "id": app.id,
                "invoice_id": app.invoice_id,
                "amount": money_str(app.amount),
                "applied_at": app.applied_at,
            }
            for app in (cn.applications or [])
        ],
    }
