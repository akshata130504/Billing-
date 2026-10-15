"""Verified Rooman plan payments and their payment receipts (models/platform_billing.PlatformPayment).

Called only from platform_payment_service.sync_provider_subscription - the one place the Checkout callback, the
platform webhook and the scheduled reconciliation all verify Razorpay state - so there is no second payment
verification here, only a defensive re-check before a row is written:

- First payment: recorded from the payment the shared verification has just accepted for activation (captured,
  exactly the checkout's amount and currency).
- Renewals: when the subscription's paid-cycle count is ahead of the recorded payments, the subscription's PAID
  invoices are read from Razorpay and each unrecorded payment is fetched and must again be captured for exactly the
  checkout's amount and currency. Anything else is not recorded and is returned as a problem for review.

Idempotent: one row per Razorpay payment id (unique constraint, and checked first); callers hold the checkout
attempt's row lock, so the callback, a webhook and reconciliation never record the same payment concurrently. Rows
are never updated or deleted. Never an authorization, a pending or failed charge, or an unverified result; never a
tenant payment. A payment RECEIPT, not a tax invoice.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.plan_catalog import catalog
from backend.app.models import Organization, PlatformCheckoutAttempt, PlatformPayment
from backend.app.services import platform_razorpay as provider

RECEIPT_NOTE = "This is a payment receipt, not a tax invoice."


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _from_unix(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def receipt_number(paid_at: datetime) -> str:
    """Stable, unique, non-guessable: RCPT-<yyyymm>-<8 hex>. Uniqueness is enforced by the database."""
    return f"RCPT-{paid_at:%Y%m}-{secrets.token_hex(4).upper()}"


def payment_problem(attempt: PlatformCheckoutAttempt, payment: Optional[Dict[str, Any]]) -> Optional[str]:
    """Why this Razorpay payment must not become a receipt for `attempt`, or None when it may."""
    if not payment or not str(payment.get("id") or "").startswith("pay_"):
        return "payment not found"
    if payment.get("status") != "captured":
        return f"payment status {payment.get('status') or 'unknown'}"
    if int(payment.get("amount") or -1) != attempt.amount_minor or str(payment.get("currency") or "").upper() != attempt.currency:
        return "payment amount or currency differs from the checkout"
    return None


def find_by_payment_id(db: Session, payment_id: str) -> Optional[PlatformPayment]:
    return db.scalars(select(PlatformPayment).where(PlatformPayment.provider == "razorpay",
                                                    PlatformPayment.provider_payment_id == payment_id)).first()


def record_verified_payment(db: Session, attempt: PlatformCheckoutAttempt, payment: Dict[str, Any], *, kind: str,
                            cycle_number: Optional[int] = None, invoice_id: Optional[str] = None,
                            paid_at: Optional[datetime] = None, period_start: Optional[datetime] = None,
                            period_end: Optional[datetime] = None) -> Optional[PlatformPayment]:
    """Record a verified payment (flush only; the caller commits). Returns the existing row for a payment already
    recorded, and None - recording nothing - when the payment does not pass the re-check."""
    payment_id = str(payment.get("id") or "")
    existing = find_by_payment_id(db, payment_id) if payment_id else None
    if existing is not None:
        return existing
    if payment_problem(attempt, payment) is not None:
        return None
    org = db.get(Organization, attempt.organization_id)
    plan = catalog().plan(attempt.plan_code)
    paid = paid_at or _from_unix(payment.get("created_at")) or _utcnow()
    row = PlatformPayment(
        organization_id=attempt.organization_id, checkout_attempt_id=attempt.id, provider="razorpay", mode=attempt.mode,
        provider_payment_id=payment_id, provider_subscription_id=attempt.provider_subscription_id,
        provider_invoice_id=invoice_id or (str(payment.get("invoice_id")) if payment.get("invoice_id") else None),
        kind=kind, cycle_number=cycle_number, status="paid",
        amount_minor=attempt.amount_minor, currency=attempt.currency,  # what the checkout fixed, verified equal above
        method=(str(payment.get("method"))[:32] if payment.get("method") else None),
        paid_at=paid, period_start=period_start, period_end=period_end,
        plan_code=attempt.plan_code, plan_name=plan.name if plan else None,
        billing_interval=attempt.billing_interval, billing_interval_count=attempt.billing_interval_count,
        sandbox=bool(plan and plan.is_sandbox), receipt_number=receipt_number(paid),
        billed_name=org.name, billed_legal_name=org.legal_name, billed_email=org.email,
        billed_address_line1=org.address_line1, billed_address_line2=org.address_line2, billed_city=org.city,
        billed_state=org.state, billed_postal_code=org.postal_code, billed_country=org.country, billed_gstin=org.gstin,
    )
    db.add(row)
    db.flush()
    if kind == "renewal":
        # The only source of the "renewal payment received" email: a NEW receipt for a payment that passed the
        # re-check above (captured, exact amount and currency). The initial payment's email is sent on activation.
        from backend.app.services import platform_notification_service as notifications

        notifications.renewal_payment_received(db, row)
    return row


def recorded_count(db: Session, provider_subscription_id: str) -> int:
    return int(db.scalar(select(func.count()).select_from(PlatformPayment).where(
        PlatformPayment.provider_subscription_id == provider_subscription_id)) or 0)


def record_missing_cycles(db: Session, attempt: PlatformCheckoutAttempt, remote: Dict[str, Any]) -> List[str]:
    """Record every paid cycle of this checkout's Razorpay subscription that has no receipt yet. Returns problems
    (application text) for cycles whose payment could not be verified; those are not recorded. Raises the provider's
    ProviderUnavailable / ProviderRejected - the caller defers the receipts, never the lifecycle."""
    if attempt.status != "completed" or not attempt.provider_subscription_id:
        return []
    subscription_id = attempt.provider_subscription_id
    if recorded_count(db, subscription_id) >= int(remote.get("paid_count") or 0):
        return []
    have = set(db.scalars(select(PlatformPayment.provider_payment_id).where(
        PlatformPayment.provider_subscription_id == subscription_id)))
    problems: List[str] = []
    for cycle, invoice in enumerate(provider.list_paid_subscription_invoices(subscription_id), start=1):
        if invoice["payment_id"] in have:
            continue
        payment = provider.fetch_payment(invoice["payment_id"])
        problem = payment_problem(attempt, payment)
        if problem is not None:
            problems.append(f"receipt not recorded for paid cycle {cycle}: {problem}")
            continue
        record_verified_payment(
            db, attempt, payment, kind="initial" if cycle == 1 else "renewal", cycle_number=cycle,
            invoice_id=invoice["invoice_id"], paid_at=_from_unix(invoice.get("paid_at")),
            period_start=_from_unix(invoice.get("billing_start")), period_end=_from_unix(invoice.get("billing_end")))
    return problems


# --- reading receipts ---------------------------------------------------------------------------------------------


def receipt_out(row: PlatformPayment) -> Dict[str, Any]:
    def aware(v):
        return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)

    return {
        "id": row.id, "receipt_number": row.receipt_number, "document_type": "payment_receipt", "note": RECEIPT_NOTE,
        "status": row.status, "kind": row.kind, "cycle_number": row.cycle_number,
        "amount_minor": row.amount_minor, "currency": row.currency, "method": row.method, "paid_at": aware(row.paid_at),
        "issued_at": aware(row.created_at), "period_start": aware(row.period_start), "period_end": aware(row.period_end),
        "plan_code": row.plan_code, "plan_name": row.plan_name, "billing_interval": row.billing_interval,
        "billing_interval_count": row.billing_interval_count, "sandbox": row.sandbox, "mode": row.mode,
        "provider_payment_id": row.provider_payment_id, "provider_invoice_id": row.provider_invoice_id,
        "billed_to": {
            "name": row.billed_name, "legal_name": row.billed_legal_name, "email": row.billed_email,
            "address_line1": row.billed_address_line1, "address_line2": row.billed_address_line2, "city": row.billed_city,
            "state": row.billed_state, "postal_code": row.billed_postal_code, "country": row.billed_country,
            "gstin": row.billed_gstin,
        },
    }


def list_receipts(db: Session, organization_id: str, *, page: int = 1, page_size: int = 25) -> Dict[str, Any]:
    page_size = max(1, min(page_size, 100))
    where = PlatformPayment.organization_id == organization_id
    total = int(db.scalar(select(func.count()).select_from(PlatformPayment).where(where)) or 0)
    rows = db.scalars(select(PlatformPayment).where(where).order_by(PlatformPayment.paid_at.desc(), PlatformPayment.id)
                      .limit(page_size).offset((page - 1) * page_size)).all()
    return {"items": [receipt_out(r) for r in rows], "total": total, "page": page, "page_size": page_size,
            "total_pages": -(-total // page_size) if total else 0}


def get_receipt(db: Session, organization_id: str, receipt_id: str) -> Optional[PlatformPayment]:
    """Only the organization's own receipt (another organization's id answers as not found)."""
    return db.scalars(select(PlatformPayment).where(PlatformPayment.id == receipt_id,
                                                    PlatformPayment.organization_id == organization_id)).first()
