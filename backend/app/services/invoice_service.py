"""Invoice domain logic (contract §8).

Exports the reusable `serialize_invoice(invoice, include_payments=True)` and
`recompute_invoice(db, invoice)` used by the payments, subscriptions, quotes
and scheduler modules. Every public mutation commits exactly once.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, object_session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.config import settings
from backend.app.core.exceptions import EntityNotFoundError, InvalidStateError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.core.security import generate_opaque_token
from backend.app.models import (
    OPEN_INVOICE_STATUSES,
    Customer,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Organization,
    Payment,
    PaymentAllocation,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    User,
    utcnow,
)
from backend.app.schemas.common_refs import customer_ref, iso_dt, line_item_out, money_str, user_ref
from backend.app.schemas.invoices import InvoiceCreate, InvoiceUpdate
from backend.app.services import audit
from backend.app.services.email import frontend_url, send_email
from backend.app.services.money import D, LineInput, compute_totals, q2
from backend.app.services.numbering import next_number
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
    today = today or date.today()
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
        )
        for i in items
    ]


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
        "payments": invoice_payment_refs(invoice) if include_payments else [],
        "created_by": user_ref(_user(session, invoice.created_by_id)),
        "created_at": iso_dt(invoice.created_at),
        "updated_at": iso_dt(invoice.updated_at),
    }
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
    invoice = db.scalars(_base_query().where(Invoice.public_token == token)).first()
    if invoice is None or invoice.status == InvoiceStatus.DRAFT:
        raise EntityNotFoundError("Invoice", token)
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
            stmt = stmt.where(Invoice.status == InvoiceStatus(status))
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
        today = date.today()
        stmt = stmt.where(
            or_(
                Invoice.status == InvoiceStatus.OVERDUE,
                (Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]) & (Invoice.due_date < today)),
            )
        )
    stmt = apply_sort(stmt, Invoice, params.sort, INVOICE_SORT_FIELDS, "-created_at")
    return paginate(db, stmt, params)


# --- creation ----------------------------------------------------------------------------------------


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
    try:
        totals = compute_totals(lines, discount_pct)
    except ValueError as exc:
        raise ValidationAppError(str(exc), {"fields": {"items": str(exc)}})
    issue_date = issue_date or date.today()
    if due_date is None:
        due_date = issue_date + timedelta(days=int(customer.payment_terms_days or 0))
    if due_date < issue_date:
        raise ValidationAppError("due_date cannot be before issue_date.", {"fields": {"due_date": "before issue_date"}})
    organization = db.get(Organization, organization_id)
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
                position=line.position,
                pricing_explanation=line.pricing_explanation,
            )
        )
    db.add(invoice)
    db.flush()
    return invoice


def create_invoice(db: Session, ctx: CurrentContext, data: InvoiceCreate) -> Invoice:
    customer = get_customer(db, ctx.organization_id, data.customer_id)
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
    audit.record(
        db,
        action="INVOICE_CREATED",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        ctx=ctx,
        after=snapshot(invoice),
    )
    from backend.app.models import AutomationTrigger
    from backend.app.services import automation_service

    automation_service.dispatch(db, AutomationTrigger.INVOICE_CREATED, ctx.organization_id, {"invoice": invoice, "customer": invoice.customer})
    db.commit()
    return get_invoice(db, ctx.organization_id, invoice.id)


# --- draft edits ----------------------------------------------------------------------------------------------


def _ensure_draft(invoice: Invoice, verb: str) -> None:
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvalidStateError(f"Only draft invoices can be {verb}; this invoice is {invoice.status.value}.")


def update_invoice(db: Session, ctx: CurrentContext, invoice: Invoice, data: InvoiceUpdate) -> Invoice:
    _ensure_draft(invoice, "edited")
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
        try:
            totals = compute_totals(lines, discount)
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
                        product_id=line.product_id,
                        plan_id=line.plan_id,
                        description=line.description,
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                        tax_rate_pct=line.tax_rate_pct,
                        amount=line.amount,
                        position=line.position,
                    )
                )
        invoice.subtotal = totals.subtotal
        invoice.discount_pct = totals.discount_pct
        invoice.discount_amount = totals.discount_amount
        invoice.tax_amount = totals.tax_amount
        invoice.total = totals.total
        invoice.amount_due = q2(totals.total - D(invoice.amount_paid))

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
    _ensure_draft(invoice, "deleted")
    audit.record(
        db,
        action="INVOICE_DELETED",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        ctx=ctx,
        before=snapshot(invoice),
    )
    db.delete(invoice)
    db.commit()


# --- lifecycle -------------------------------------------------------------------------------------------------------


def _invoice_email(invoice: Invoice, organization: Organization, *, reminder: bool = False) -> tuple[str, str]:
    pay_url = public_url_for(invoice)
    org_name = organization.legal_name or organization.name
    due = invoice.due_date.strftime("%d %b %Y")
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
        f"Dear {invoice.customer.display_name},\n\n{intro}\n\n"
        f"You can view and pay the invoice online here:\n{pay_url}\n\n"
        f"Thank you,\n{org_name}"
    )
    return subject, body


def _render_pdf_safe(invoice: Invoice, organization: Organization) -> Optional[bytes]:
    try:
        from backend.app.services.invoice_pdf import render_invoice_pdf

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
    subject, body = _invoice_email(invoice, organization, reminder=reminder)
    attachments = []
    if attach_pdf and settings.email_enabled:
        pdf = _render_pdf_safe(invoice, organization)
        if pdf:
            attachments.append((f"{invoice.invoice_number}.pdf", pdf, "application/pdf"))
    try:
        return send_email(recipient, subject, body, attachments=attachments, reply_to=organization.email)
    except Exception:  # SMTP trouble must not fail the state change
        logger.exception("Email delivery failed for invoice %s", invoice.invoice_number)
        return False


def send_invoice(db: Session, ctx: CurrentContext, invoice: Invoice) -> Invoice:
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvalidStateError(f"Only draft invoices can be sent; this invoice is {invoice.status.value}.")
    before = snapshot(invoice)
    invoice.status = InvoiceStatus.SENT
    invoice.sent_at = utcnow()
    invoice.updated_at = utcnow()
    db.flush()
    email_invoice(db, invoice)
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
    return get_invoice(db, ctx.organization_id, invoice.id)


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
    email_invoice(db, invoice, reminder=True)
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
        return get_invoice(db, invoice.organization_id, invoice.id)
    return invoice


def void_invoice(db: Session, ctx: CurrentContext, invoice: Invoice, reason: str) -> Invoice:
    if invoice.status == InvoiceStatus.VOID:
        raise InvalidStateError("This invoice is already void.")
    if D(invoice.amount_paid) > 0:
        raise InvalidStateError("An invoice with recorded payments cannot be voided. Refund the payments first.")
    before = snapshot(invoice)
    invoice.status = InvoiceStatus.VOID
    invoice.voided_at = utcnow()
    invoice.void_reason = reason.strip()
    invoice.amount_due = Decimal("0.00")
    invoice.updated_at = utcnow()
    db.flush()
    audit.record(
        db,
        action="INVOICE_VOIDED",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        ctx=ctx,
        before=before,
        after=snapshot(invoice),
    )
    db.commit()
    return get_invoice(db, ctx.organization_id, invoice.id)


def mark_overdue(db: Session, invoice: Invoice, *, actor_label: str = audit.SYSTEM_ACTOR) -> bool:
    """Scheduler step (c): flip an open invoice past its due date to overdue. No commit."""
    if invoice.status not in (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID) or invoice.due_date >= date.today():
        return False
    before = snapshot(invoice)
    invoice.status = InvoiceStatus.OVERDUE
    invoice.updated_at = utcnow()
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


def recompute_invoice(
    db: Session,
    invoice: Invoice,
    *,
    ctx: Optional[CurrentContext] = None,
    actor_label: Optional[str] = None,
) -> Invoice:
    """Re-derive amount_paid/amount_due/status from allocations. Writes INVOICE_PAID when it becomes paid. No commit."""
    if invoice.status in (InvoiceStatus.DRAFT, InvoiceStatus.VOID):
        return invoice
    before = snapshot(invoice)
    previous_status = invoice.status
    paid = allocated_total(db, invoice.id)
    total = q2(invoice.total)
    invoice.amount_paid = paid
    invoice.amount_due = q2(max(Decimal("0"), total - paid))
    today = date.today()

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


__all__ = [
    "serialize_invoice",
    "recompute_invoice",
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
    "line_inputs",
    "days_overdue",
    "as_utc",
    "SETTLED_PAYMENT_STATUSES",
]
