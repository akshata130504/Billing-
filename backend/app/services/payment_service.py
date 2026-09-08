"""Payments, allocations, refunds and reconciliation (contract §9).

Also hosts the gateway capture/fail/refund primitives shared by the hosted
payment page (razorpay-verify) and the Razorpay webhook handler.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, object_session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import (
    EntityNotFoundError,
    GatewayNotConfiguredError,
    InvalidStateError,
    ValidationAppError,
)
from backend.app.models import (
    OPEN_INVOICE_STATUSES,
    Customer,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentAllocation,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    ReconciliationStatus,
    Refund,
    RefundStatus,
    User,
    utcnow,
)
from backend.app.schemas.common_refs import customer_ref, iso_dt, money_str, user_ref
from backend.app.schemas.invoices import RecordPaymentIn
from backend.app.schemas.payments import AllocationIn, PaymentCreate, PaymentUpdate
from backend.app.services import audit, razorpay_gateway
from backend.app.services.invoice_service import (
    SETTLED_PAYMENT_STATUSES,
    get_customer,
    get_invoice,
    recompute_invoice,
)
from backend.app.services.money import D, q2
from backend.app.services.numbering import next_number
from backend.app.services.pagination import PageParams, apply_sort, paginate

PAYMENT_SNAPSHOT_FIELDS = (
    "payment_number",
    "status",
    "amount",
    "amount_refunded",
    "method",
    "gateway",
    "reconciliation_status",
    "gateway_order_id",
    "gateway_payment_id",
    "gateway_signature_verified",
    "paid_at",
    "failure_reason",
    "reference",
)
PAYMENT_SORT_FIELDS = ("created_at", "paid_at", "amount", "payment_number", "status", "reconciliation_status", "updated_at")


def snapshot(payment: Payment) -> Dict[str, Any]:
    return audit.snapshot(payment, PAYMENT_SNAPSHOT_FIELDS)


def to_paise(amount) -> int:
    return int((q2(amount) * 100).to_integral_value())


def from_paise(paise) -> Decimal:
    return q2(D(paise) / 100)


# --- serialisation ------------------------------------------------------------------------------


def allocated_amount(payment: Payment) -> Decimal:
    return q2(sum((D(a.amount) for a in payment.allocations), Decimal("0")))


def effective_amount(payment: Payment) -> Decimal:
    """Money that is still ours after refunds."""
    return q2(D(payment.amount) - D(payment.amount_refunded))


def serialize_payment(payment: Payment) -> Dict[str, Any]:
    session = object_session(payment)
    recorded_by = session.get(User, payment.recorded_by_id) if (session is not None and payment.recorded_by_id) else None
    allocated = allocated_amount(payment)
    unallocated = max(Decimal("0"), effective_amount(payment) - allocated)
    return {
        "id": payment.id,
        "payment_number": payment.payment_number,
        "customer": customer_ref(payment.customer),
        "amount": money_str(payment.amount),
        "currency": payment.currency,
        "method": payment.method,
        "gateway": payment.gateway,
        "status": payment.status,
        "reconciliation_status": payment.reconciliation_status,
        "gateway_order_id": payment.gateway_order_id,
        "gateway_payment_id": payment.gateway_payment_id,
        "gateway_signature_verified": bool(payment.gateway_signature_verified),
        "reference": payment.reference,
        "paid_at": iso_dt(payment.paid_at),
        "failure_reason": payment.failure_reason,
        "notes": payment.notes,
        "amount_refunded": money_str(payment.amount_refunded),
        "amount_allocated": money_str(allocated),
        "amount_unallocated": money_str(unallocated),
        "allocations": [
            {
                "id": a.id,
                "invoice_id": a.invoice_id,
                "invoice_number": a.invoice.invoice_number if a.invoice else "",
                "amount": money_str(a.amount),
            }
            for a in payment.allocations
        ],
        "refunds": [
            {
                "id": r.id,
                "amount": money_str(r.amount),
                "status": r.status,
                "gateway_refund_id": r.gateway_refund_id,
                "reason": r.reason,
                "created_at": iso_dt(r.created_at),
            }
            for r in sorted(payment.refunds, key=lambda r: iso_dt(r.created_at) or datetime.min.replace(tzinfo=timezone.utc))
        ],
        "recorded_by": user_ref(recorded_by),
        "created_at": iso_dt(payment.created_at),
        "updated_at": iso_dt(payment.updated_at),
    }


# --- queries -------------------------------------------------------------------------------------------


def _base_query() -> Select:
    return select(Payment).options(
        selectinload(Payment.customer),
        selectinload(Payment.allocations).selectinload(PaymentAllocation.invoice),
        selectinload(Payment.refunds),
    )


def get_payment(db: Session, organization_id: str, payment_id: str) -> Payment:
    payment = db.scalars(_base_query().where(Payment.id == payment_id, Payment.organization_id == organization_id)).first()
    if payment is None:
        raise EntityNotFoundError("Payment", payment_id)
    return payment


def find_by_order_id(db: Session, gateway_order_id: str, organization_id: Optional[str] = None) -> Optional[Payment]:
    stmt = _base_query().where(Payment.gateway_order_id == gateway_order_id)
    if organization_id:
        stmt = stmt.where(Payment.organization_id == organization_id)
    return db.scalars(stmt).first()


def find_by_gateway_payment_id(db: Session, gateway_payment_id: str) -> Optional[Payment]:
    return db.scalars(_base_query().where(Payment.gateway_payment_id == gateway_payment_id)).first()


def _day_bounds(date_from: Optional[date], date_to: Optional[date]):
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc) if date_to else None
    return start, end


def list_payments(
    db: Session,
    organization_id: str,
    params: PageParams,
    *,
    search: Optional[str] = None,
    status: Optional[str] = None,
    method: Optional[str] = None,
    gateway: Optional[str] = None,
    reconciliation_status: Optional[str] = None,
    customer_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
):
    stmt = _base_query().where(Payment.organization_id == organization_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.outerjoin(Customer, Customer.id == Payment.customer_id).where(
            or_(
                Payment.payment_number.ilike(like),
                Payment.reference.ilike(like),
                Payment.gateway_payment_id.ilike(like),
                Payment.gateway_order_id.ilike(like),
                Customer.display_name.ilike(like),
            )
        )
    fields: Dict[str, str] = {}
    try:
        if status:
            stmt = stmt.where(Payment.status == PaymentStatus(status))
    except ValueError:
        fields["status"] = "invalid"
    try:
        if method:
            stmt = stmt.where(Payment.method == PaymentMethod(method))
    except ValueError:
        fields["method"] = "invalid"
    try:
        if gateway:
            stmt = stmt.where(Payment.gateway == PaymentGateway(gateway))
    except ValueError:
        fields["gateway"] = "invalid"
    try:
        if reconciliation_status:
            stmt = stmt.where(Payment.reconciliation_status == ReconciliationStatus(reconciliation_status))
    except ValueError:
        fields["reconciliation_status"] = "invalid"
    if fields:
        raise ValidationAppError("Unknown filter value.", {"fields": fields})
    if customer_id:
        stmt = stmt.where(Payment.customer_id == customer_id)
    start, end = _day_bounds(date_from, date_to)
    if start:
        stmt = stmt.where(func.coalesce(Payment.paid_at, Payment.created_at) >= start)
    if end:
        stmt = stmt.where(func.coalesce(Payment.paid_at, Payment.created_at) < end)
    stmt = apply_sort(stmt, Payment, params.sort, PAYMENT_SORT_FIELDS, "-created_at")
    return paginate(db, stmt, params)


# --- reconciliation -----------------------------------------------------------------------------------------


def refresh_reconciliation(payment: Payment, *, auto: bool = False) -> None:
    """matched/auto_matched when fully allocated, unmatched when nothing is, exception otherwise."""
    if payment.status in (PaymentStatus.PENDING, PaymentStatus.FAILED):
        payment.reconciliation_status = ReconciliationStatus.UNMATCHED
        return
    allocated = allocated_amount(payment)
    effective = effective_amount(payment)
    if allocated == 0 and effective > 0:
        payment.reconciliation_status = ReconciliationStatus.UNMATCHED
    elif allocated == effective:
        payment.reconciliation_status = ReconciliationStatus.AUTO_MATCHED if auto else ReconciliationStatus.MATCHED
    else:
        payment.reconciliation_status = ReconciliationStatus.EXCEPTION


def reconciliation_summary(db: Session, organization_id: str) -> Dict[str, Any]:
    base = select(Payment.reconciliation_status, func.count()).where(
        Payment.organization_id == organization_id, Payment.status.in_(SETTLED_PAYMENT_STATUSES)
    )
    counts = {s.value: 0 for s in ReconciliationStatus}
    for status_value, count in db.execute(base.group_by(Payment.reconciliation_status)).all():
        key = status_value.value if hasattr(status_value, "value") else str(status_value)
        counts[key] = int(count)
    received = db.scalar(
        select(func.coalesce(func.sum(Payment.amount - Payment.amount_refunded), 0)).where(
            Payment.organization_id == organization_id, Payment.status.in_(SETTLED_PAYMENT_STATUSES)
        )
    )
    allocated = db.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(Payment.organization_id == organization_id, Payment.status.in_(SETTLED_PAYMENT_STATUSES))
    )
    return {
        **counts,
        "total": sum(counts.values()),
        "unallocated_amount": money_str(max(Decimal("0"), D(received) - D(allocated))),
    }


# --- allocation validation ---------------------------------------------------------------------------------------------


def _validate_allocations(
    db: Session,
    organization_id: str,
    payment_amount: Decimal,
    allocations: Sequence[AllocationIn],
    *,
    own_existing: Optional[Dict[str, Decimal]] = None,
) -> List[tuple[Invoice, Decimal]]:
    """Return (invoice, amount) pairs or raise 422. `own_existing` = this payment's current allocation per invoice."""
    own_existing = own_existing or {}
    seen: Set[str] = set()
    total = Decimal("0")
    result: List[tuple[Invoice, Decimal]] = []
    fields: Dict[str, str] = {}
    for idx, alloc in enumerate(allocations):
        if alloc.invoice_id in seen:
            fields[f"allocations.{idx}.invoice_id"] = "duplicate invoice"
            continue
        seen.add(alloc.invoice_id)
        invoice = get_invoice(db, organization_id, alloc.invoice_id)  # 404 for other tenants
        amount = q2(alloc.amount)
        if invoice.status not in OPEN_INVOICE_STATUSES:
            fields[f"allocations.{idx}.invoice_id"] = f"invoice {invoice.invoice_number} is {invoice.status.value}, not open"
            continue
        headroom = q2(D(invoice.amount_due) + own_existing.get(invoice.id, Decimal("0")))
        if amount > headroom:
            fields[f"allocations.{idx}.amount"] = f"exceeds amount due on {invoice.invoice_number} ({headroom})"
            continue
        total += amount
        result.append((invoice, amount))
    if total > q2(payment_amount):
        fields["allocations"] = f"allocated total {total} exceeds the payment amount {q2(payment_amount)}"
    if fields:
        raise ValidationAppError("Allocations are invalid.", {"fields": fields})
    return result


def _reload(db: Session, payment: Payment) -> Payment:
    db.expire(payment)
    return get_payment(db, payment.organization_id, payment.id)


# --- create / update -----------------------------------------------------------------------------------------------------


def create_payment(db: Session, ctx: CurrentContext, data: PaymentCreate) -> Payment:
    customer = get_customer(db, ctx.organization_id, data.customer_id)
    amount = q2(data.amount)
    pairs = _validate_allocations(db, ctx.organization_id, amount, data.allocations or [])
    payment = Payment(
        organization_id=ctx.organization_id,
        payment_number=next_number(db, ctx.organization_id, "payment"),
        customer_id=customer.id,
        amount=amount,
        currency=customer.currency or ctx.organization.default_currency or "INR",
        method=data.method,
        gateway=PaymentGateway.MANUAL,
        status=PaymentStatus.SUCCEEDED,
        reconciliation_status=ReconciliationStatus.UNMATCHED,
        reference=data.reference,
        paid_at=data.paid_at or utcnow(),
        notes=data.notes,
        amount_refunded=Decimal("0.00"),
        recorded_by_id=ctx.user.id,
    )
    db.add(payment)
    db.flush()
    for invoice, alloc_amount in pairs:
        db.add(PaymentAllocation(organization_id=ctx.organization_id, payment_id=payment.id, invoice_id=invoice.id, amount=alloc_amount))
    db.flush()
    db.refresh(payment)
    refresh_reconciliation(payment)
    for invoice, _ in pairs:
        recompute_invoice(db, invoice, ctx=ctx)
    audit.record(
        db,
        action="PAYMENT_RECORDED",
        entity_type="payment",
        entity_id=payment.id,
        entity_label=payment.payment_number,
        ctx=ctx,
        after={**snapshot(payment), "allocations": [{"invoice_id": i.id, "amount": a} for i, a in pairs]},
    )
    if pairs:
        audit.record(
            db,
            action="PAYMENT_ALLOCATED",
            entity_type="payment",
            entity_id=payment.id,
            entity_label=payment.payment_number,
            ctx=ctx,
            after={"allocations": [{"invoice_id": i.id, "invoice_number": i.invoice_number, "amount": a} for i, a in pairs]},
        )
    db.commit()
    return _reload(db, payment)


def record_invoice_payment(db: Session, ctx: CurrentContext, invoice: Invoice, data: RecordPaymentIn) -> Payment:
    """POST /invoices/{id}/record-payment: manual payment fully allocated to one invoice."""
    if invoice.status == InvoiceStatus.DRAFT:
        invoice.status = InvoiceStatus.SENT
        invoice.sent_at = utcnow()
        db.flush()
    elif invoice.status not in OPEN_INVOICE_STATUSES:
        raise InvalidStateError(f"Payments can only be recorded against open invoices; this invoice is {invoice.status.value}.")
    amount = q2(data.amount)
    if amount > q2(invoice.amount_due):
        raise ValidationAppError(
            f"Amount {amount} exceeds the amount due ({q2(invoice.amount_due)}).",
            {"fields": {"amount": "exceeds amount due"}},
        )
    payment = Payment(
        organization_id=ctx.organization_id,
        payment_number=next_number(db, ctx.organization_id, "payment"),
        customer_id=invoice.customer_id,
        amount=amount,
        currency=invoice.currency,
        method=data.method,
        gateway=PaymentGateway.MANUAL,
        status=PaymentStatus.SUCCEEDED,
        reconciliation_status=ReconciliationStatus.MATCHED,
        reference=data.reference,
        paid_at=data.paid_at or utcnow(),
        notes=data.notes,
        amount_refunded=Decimal("0.00"),
        recorded_by_id=ctx.user.id,
    )
    db.add(payment)
    db.flush()
    db.add(PaymentAllocation(organization_id=ctx.organization_id, payment_id=payment.id, invoice_id=invoice.id, amount=amount))
    db.flush()
    recompute_invoice(db, invoice, ctx=ctx)
    audit.record(
        db,
        action="PAYMENT_RECORDED",
        entity_type="payment",
        entity_id=payment.id,
        entity_label=payment.payment_number,
        ctx=ctx,
        after={**snapshot(payment), "invoice_id": invoice.id, "invoice_number": invoice.invoice_number},
    )
    db.commit()
    return _reload(db, payment)


def update_payment(db: Session, ctx: CurrentContext, payment: Payment, data: PaymentUpdate) -> Payment:
    before = snapshot(payment)
    changes = data.model_dump(exclude_unset=True)
    if "reference" in changes:
        payment.reference = changes["reference"]
    if "notes" in changes:
        payment.notes = changes["notes"]
    payment.updated_at = utcnow()
    db.flush()
    audit.record(
        db,
        action="PAYMENT_UPDATED",
        entity_type="payment",
        entity_id=payment.id,
        entity_label=payment.payment_number,
        ctx=ctx,
        before=before,
        after=snapshot(payment),
    )
    db.commit()
    return _reload(db, payment)


def set_allocations(db: Session, ctx: CurrentContext, payment: Payment, allocations: Sequence[AllocationIn]) -> Payment:
    if payment.status not in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED):
        raise InvalidStateError(f"Allocations can only be changed on settled payments; this payment is {payment.status.value}.")
    own_existing: Dict[str, Decimal] = {}
    for a in payment.allocations:
        own_existing[a.invoice_id] = own_existing.get(a.invoice_id, Decimal("0")) + D(a.amount)
    pairs = _validate_allocations(db, ctx.organization_id, effective_amount(payment), allocations, own_existing=own_existing)
    before = {**snapshot(payment), "allocations": [{"invoice_id": a.invoice_id, "amount": a.amount} for a in payment.allocations]}

    affected: Dict[str, Invoice] = {}
    for old in list(payment.allocations):
        affected[old.invoice_id] = get_invoice(db, ctx.organization_id, old.invoice_id)
        db.delete(old)
    payment.allocations = []
    db.flush()
    for invoice, amount in pairs:
        db.add(PaymentAllocation(organization_id=ctx.organization_id, payment_id=payment.id, invoice_id=invoice.id, amount=amount))
        affected[invoice.id] = invoice
    db.flush()
    db.refresh(payment)
    refresh_reconciliation(payment)
    payment.updated_at = utcnow()
    for invoice in affected.values():
        recompute_invoice(db, invoice, ctx=ctx)
    audit.record(
        db,
        action="PAYMENT_ALLOCATED",
        entity_type="payment",
        entity_id=payment.id,
        entity_label=payment.payment_number,
        ctx=ctx,
        before=before,
        after={**snapshot(payment), "allocations": [{"invoice_id": i.id, "invoice_number": i.invoice_number, "amount": a} for i, a in pairs]},
    )
    db.commit()
    return _reload(db, payment)


# --- refunds -------------------------------------------------------------------------------------------------------------


def _reverse_allocations(db: Session, payment: Payment, refund_amount: Decimal, remaining_before: Decimal) -> List[Invoice]:
    """Reduce each allocation proportionally to the refunded share; drop allocations that reach zero."""
    affected: List[Invoice] = []
    if remaining_before <= 0:
        return affected
    full = refund_amount >= remaining_before
    for alloc in list(payment.allocations):
        invoice = alloc.invoice or db.get(Invoice, alloc.invoice_id)
        current = D(alloc.amount)
        reduction = current if full else min(current, q2(current * refund_amount / remaining_before))
        if reduction <= 0:
            continue
        if reduction >= current:
            db.delete(alloc)
        else:
            alloc.amount = q2(current - reduction)
        if invoice is not None:
            affected.append(invoice)
    db.flush()
    return affected


def apply_refund(
    db: Session,
    payment: Payment,
    amount: Decimal,
    *,
    reason: Optional[str] = None,
    gateway_refund_id: Optional[str] = None,
    refund_status: RefundStatus = RefundStatus.PROCESSED,
    ctx: Optional[CurrentContext] = None,
    actor_label: Optional[str] = None,
) -> Refund:
    """Persist a refund, update the payment, reverse allocations and re-open invoices. No commit."""
    amount = q2(amount)
    remaining = effective_amount(payment)
    if amount <= 0 or amount > remaining:
        raise ValidationAppError(
            f"Refund amount must be between 0.01 and {remaining} (amount not yet refunded).",
            {"fields": {"amount": "exceeds refundable amount"}},
        )
    before = snapshot(payment)
    refund = Refund(
        organization_id=payment.organization_id,
        payment_id=payment.id,
        amount=amount,
        status=refund_status,
        gateway_refund_id=gateway_refund_id,
        reason=reason,
        created_by_id=ctx.user.id if ctx else None,
    )
    db.add(refund)
    payment.amount_refunded = q2(D(payment.amount_refunded) + amount)
    payment.status = PaymentStatus.REFUNDED if q2(payment.amount_refunded) >= q2(payment.amount) else PaymentStatus.PARTIALLY_REFUNDED
    payment.updated_at = utcnow()
    affected = _reverse_allocations(db, payment, amount, remaining)
    db.flush()
    db.refresh(payment)
    refresh_reconciliation(payment, auto=before.get("reconciliation_status") == ReconciliationStatus.AUTO_MATCHED.value)
    seen: Set[str] = set()
    for invoice in affected:
        if invoice.id in seen:
            continue
        seen.add(invoice.id)
        recompute_invoice(db, invoice, ctx=ctx, actor_label=actor_label)
    audit.record(
        db,
        action="PAYMENT_REFUNDED",
        entity_type="payment",
        entity_id=payment.id,
        entity_label=payment.payment_number,
        organization_id=payment.organization_id,
        ctx=ctx,
        actor_label=actor_label,
        before=before,
        after={**snapshot(payment), "refund": {"id": refund.id, "amount": amount, "reason": reason, "gateway_refund_id": gateway_refund_id}},
    )
    return refund


def refund_payment(db: Session, ctx: CurrentContext, payment: Payment, amount: Decimal, reason: Optional[str]) -> Payment:
    if payment.status not in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED):
        raise InvalidStateError(f"Only succeeded payments can be refunded; this payment is {payment.status.value}.")
    amount = q2(amount)
    remaining = effective_amount(payment)
    if amount > remaining:
        raise ValidationAppError(
            f"Refund amount {amount} exceeds the refundable amount ({remaining}).",
            {"fields": {"amount": "exceeds refundable amount"}},
        )
    gateway_refund_id = None
    refund_status = RefundStatus.PROCESSED
    if payment.gateway == PaymentGateway.RAZORPAY:
        if not razorpay_gateway.is_configured():
            raise GatewayNotConfiguredError("razorpay")
        if not payment.gateway_payment_id:
            raise InvalidStateError("This online payment has no gateway payment id and cannot be refunded through Razorpay.")
        result = razorpay_gateway.refund_payment(
            payment.gateway_payment_id,
            to_paise(amount),
            {"payment_number": payment.payment_number, "reason": reason or "", "organization_id": payment.organization_id},
        )
        gateway_refund_id = result.get("id")
        gw_status = str(result.get("status") or "processed").lower()
        refund_status = {"pending": RefundStatus.PENDING, "failed": RefundStatus.FAILED}.get(gw_status, RefundStatus.PROCESSED)
    apply_refund(db, payment, amount, reason=reason, gateway_refund_id=gateway_refund_id, refund_status=refund_status, ctx=ctx)
    db.commit()
    return _reload(db, payment)


# --- gateway capture / failure (hosted page + webhook) -------------------------------------------------------------------


def capture_gateway_payment(
    db: Session,
    payment: Payment,
    invoice: Invoice,
    *,
    gateway_payment_id: str,
    payload: Optional[Dict[str, Any]] = None,
    signature_verified: bool = True,
    actor_label: str = audit.CUSTOMER_ACTOR,
) -> Payment:
    """Mark a pending gateway payment as captured and allocate it to `invoice`. Idempotent. No commit."""
    if payment.status == PaymentStatus.SUCCEEDED or payment.status in (PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED):
        return payment
    before = snapshot(payment)
    payment.status = PaymentStatus.SUCCEEDED
    payment.gateway_payment_id = gateway_payment_id
    payment.gateway_signature_verified = bool(signature_verified)
    payment.paid_at = utcnow()
    payment.failure_reason = None
    if payload:
        merged = dict(payment.gateway_payload or {})
        merged["capture"] = payload
        payment.gateway_payload = merged
    payment.updated_at = utcnow()
    db.flush()
    if invoice.status in OPEN_INVOICE_STATUSES:
        alloc_amount = min(q2(payment.amount), q2(invoice.amount_due))
        if alloc_amount > 0:
            db.add(PaymentAllocation(organization_id=payment.organization_id, payment_id=payment.id, invoice_id=invoice.id, amount=alloc_amount))
            db.flush()
    db.refresh(payment)
    refresh_reconciliation(payment, auto=True)
    recompute_invoice(db, invoice, actor_label=actor_label)
    audit.record(
        db,
        action="PAYMENT_CAPTURED",
        entity_type="payment",
        entity_id=payment.id,
        entity_label=payment.payment_number,
        organization_id=payment.organization_id,
        actor_label=actor_label,
        before=before,
        after={**snapshot(payment), "invoice_id": invoice.id, "invoice_number": invoice.invoice_number},
    )
    return payment


def fail_gateway_payment(
    db: Session,
    payment: Payment,
    *,
    reason: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
    actor_label: str = audit.WEBHOOK_ACTOR,
    status: audit.AuditStatus = audit.AuditStatus.WARNING,
) -> Payment:
    """Mark a pending gateway payment as failed. No commit."""
    if payment.status != PaymentStatus.PENDING:
        return payment
    before = snapshot(payment)
    payment.status = PaymentStatus.FAILED
    payment.failure_reason = (reason or "Payment failed at the gateway")[:500]
    payment.reconciliation_status = ReconciliationStatus.UNMATCHED
    if payload:
        merged = dict(payment.gateway_payload or {})
        merged["failure"] = payload
        payment.gateway_payload = merged
    payment.updated_at = utcnow()
    db.flush()
    audit.record(
        db,
        action="PAYMENT_FAILED",
        entity_type="payment",
        entity_id=payment.id,
        entity_label=payment.payment_number,
        organization_id=payment.organization_id,
        actor_label=actor_label,
        before=before,
        after=snapshot(payment),
        status=status,
    )
    return payment


__all__ = [
    "serialize_payment",
    "get_payment",
    "list_payments",
    "create_payment",
    "record_invoice_payment",
    "update_payment",
    "set_allocations",
    "refund_payment",
    "apply_refund",
    "reconciliation_summary",
    "capture_gateway_payment",
    "fail_gateway_payment",
    "find_by_order_id",
    "find_by_gateway_payment_id",
    "refresh_reconciliation",
    "to_paise",
    "from_paise",
]
