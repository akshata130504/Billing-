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
from backend.app.services import audit
from backend.app.services.unit_of_work import UnitOfWork


def _next_credit_note_number(db: Session, organization_id: str) -> str:
    """Generate the next credit note number for the organization."""
    count = db.scalar(
        select(func.count(CreditNote.id)).where(CreditNote.organization_id == organization_id)
    ) or 0
    return f"CN-{(count + 1):06d}"


def create_credit_note(
    db: Session,
    ctx: CurrentContext,
    customer_id: str,
    lines: List[Dict[str, Any]],
    reason: Optional[str] = None,
    invoice_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    issue_date: Optional[date] = None,
    currency: str = "INR",
    status: CreditNoteStatus = CreditNoteStatus.ISSUED,
) -> CreditNote:
    """Create a new credit note for a customer."""
    customer = db.scalars(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.organization_id == ctx.organization_id,
        )
    ).first()
    if customer is None:
        raise NotFoundAppError("Customer not found.")

    if not lines:
        raise ValidationAppError("At least one credit note line is required.")

    cn_number = _next_credit_note_number(db, ctx.organization_id)
    credit_note = CreditNote(
        organization_id=ctx.organization_id,
        credit_note_number=cn_number,
        customer_id=customer.id,
        invoice_id=invoice_id,
        subscription_id=subscription_id,
        status=status,
        reason=reason,
        issue_date=issue_date or date.today(),
        currency=currency,
        created_by_id=ctx.user_id,
    )

    subtotal = Decimal("0")
    total_tax = Decimal("0")

    for idx, item in enumerate(lines):
        qty = Decimal(str(item.get("quantity", 1)))
        price = Decimal(str(item.get("unit_price", 0)))
        tax_pct = Decimal(str(item.get("tax_rate_pct", 0)))
        if "amount" in item and price == Decimal("0"):
            line_amount = Decimal(str(item["amount"])).quantize(Decimal("0.01"))
            price = (line_amount / qty).quantize(Decimal("0.01"))
        else:
            line_amount = (qty * price).quantize(Decimal("0.01"))
        line_tax = (line_amount * tax_pct / Decimal("100")).quantize(Decimal("0.01"))

        subtotal += line_amount
        total_tax += line_tax

        cn_line = CreditNoteLine(
            organization_id=ctx.organization_id,
            description=item.get("description", "Credit adjustment"),
            quantity=qty,
            unit_price=price,
            tax_rate_pct=tax_pct,
            amount=line_amount,
            position=idx,
        )
        credit_note.lines.append(cn_line)

    total = subtotal + total_tax
    credit_note.subtotal = subtotal
    credit_note.tax_amount = total_tax
    credit_note.total = total
    credit_note.balance_remaining = total

    db.add(credit_note)
    db.flush()

    uow = UnitOfWork(db)
    uow.register_event(
        organization_id=ctx.organization_id,
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
        ctx=ctx,
        after={"total": str(credit_note.total), "customer_id": credit_note.customer_id},
    )

    db.commit()
    db.refresh(credit_note)
    return credit_note


def apply_credit_note_to_invoice(
    db: Session,
    ctx: CurrentContext,
    credit_note_id: str,
    invoice_id: str,
    amount: Decimal,
    notes: Optional[str] = None,
) -> CreditApplication:
    """Apply an available credit note amount toward an unpaid invoice balance."""
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
            Invoice.organization_id == ctx.organization_id,
        )
    ).first()
    if invoice is None:
        raise NotFoundAppError("Invoice not found.")

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

    invoice.amount_paid = (invoice.amount_paid + amount).quantize(Decimal("0.01"))
    invoice.amount_due = (invoice.amount_due - amount).quantize(Decimal("0.01"))

    if invoice.amount_due == Decimal("0"):
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = audit.utcnow()
    else:
        invoice.status = InvoiceStatus.PARTIALLY_PAID

    application = CreditApplication(
        organization_id=ctx.organization_id,
        credit_note_id=credit_note.id,
        invoice_id=invoice.id,
        amount=amount,
        notes=notes,
    )
    db.add(application)
    db.flush()

    uow = UnitOfWork(db)
    uow.register_event(
        organization_id=ctx.organization_id,
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
            organization_id=ctx.organization_id,
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
        ctx=ctx,
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


def list_credit_notes(
    db: Session,
    organization_id: str,
    customer_id: Optional[str] = None,
    status_: Optional[CreditNoteStatus] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[CreditNote]:
    query = (
        select(CreditNote)
        .options(selectinload(CreditNote.customer), selectinload(CreditNote.lines))
        .where(CreditNote.organization_id == organization_id)
        .order_by(desc(CreditNote.created_at))
        .limit(limit)
        .offset(offset)
    )
    if customer_id:
        query = query.where(CreditNote.customer_id == customer_id)
    if status_:
        query = query.where(CreditNote.status == status_)
    return list(db.scalars(query).all())


def serialize_credit_note(cn: CreditNote) -> Dict[str, Any]:
    from backend.app.schemas.common_refs import customer_ref, money_str

    return {
        "id": cn.id,
        "credit_note_number": cn.credit_note_number,
        "customer_id": cn.customer_id,
        "customer": customer_ref(cn.customer) if cn.customer else None,
        "status": cn.status,
        "currency": cn.currency,
        "subtotal": money_str(cn.subtotal),
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
