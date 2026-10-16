"""Settle Razorpay payments whose outcome never reached us.

A hosted-page or checkout payment is created PENDING when its Razorpay order is made, and is
normally settled by the browser's verify call or by the payment.captured / payment.failed webhook.
If the customer closes the browser and the webhook is lost (endpoint down, secret rotated,
retries exhausted), the payment stays PENDING forever although the money may have been taken.

The scheduler calls `reconcile_stale_gateway_payments` to ask Razorpay, server to server with the
organization's own keys, what happened to each such order. It then applies exactly the checks
and settlement path the webhook uses:
- a captured attempt whose amount and currency match is captured and allocated (idempotent, row
  locked, so a late webhook or browser verify cannot settle it twice);
- an order whose attempts all failed is marked failed;
- anything else (no attempt yet, or authorized and not captured) is left alone.
Nothing is created or refunded here, and an unconfigured gateway is skipped.
"""
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.base import utcnow
from backend.app.models import Invoice
from backend.app.models.payments import Payment, PaymentGateway, PaymentStatus
from backend.app.services import audit, payment_service, razorpay_gateway

logger = logging.getLogger("rooman_billing")

# Long enough that the browser verify and the first webhook deliveries have had their chance.
MIN_AGE = timedelta(minutes=30)
# Razorpay orders older than this are not worth polling.
MAX_AGE = timedelta(days=7)
BATCH_LIMIT = 100

RECONCILE_ACTOR = "System (gateway reconciliation)"


def _invoice_for(db: Session, payment: Payment, entity: Dict[str, Any]) -> Optional[Invoice]:
    """The invoice the order was raised for; same resolution as the webhook handler."""
    notes: Dict[str, Any] = {}
    if isinstance(entity.get("notes"), dict):
        notes.update(entity["notes"])
    notes.update(dict((payment.gateway_payload or {}).get("notes") or {}))
    invoice_id = notes.get("invoice_id")
    if invoice_id:
        inv = db.scalars(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.organization_id == payment.organization_id)
        ).first()
        if inv is not None:
            return inv
    if payment.allocations:
        return payment.allocations[0].invoice
    return None


def _stale_pending(db: Session, now) -> List[Payment]:
    return list(
        db.scalars(
            select(Payment)
            .where(
                Payment.gateway == PaymentGateway.RAZORPAY,
                Payment.status == PaymentStatus.PENDING,
                Payment.gateway_order_id.is_not(None),
                Payment.created_at <= now - MIN_AGE,
                Payment.created_at >= now - MAX_AGE,
            )
            .order_by(Payment.created_at)
            .limit(BATCH_LIMIT)
        ).all()
    )


def _settle(db: Session, payment: Payment, attempts: List[Dict[str, Any]]) -> str:
    """Apply Razorpay's answer to one locked payment. Returns 'captured', 'failed' or 'unchanged'."""
    captured = [a for a in attempts if a.get("status") == "captured"]
    if captured:
        entity = captured[0]
        if entity.get("amount") is None or payment_service.from_paise(entity["amount"]) != payment.amount:
            raise ValueError(
                f"captured amount {entity.get('amount')!r} (paise) does not match payment {payment.payment_number}"
            )
        currency = entity.get("currency")
        if currency and currency.upper() != (payment.currency or "").upper():
            raise ValueError(f"captured currency {currency} does not match payment {payment.payment_number}")
        invoice = _invoice_for(db, payment, entity)
        checkout_session_id = dict((payment.gateway_payload or {}).get("notes") or {}).get("checkout_session_id")
        if invoice is None and not checkout_session_id:
            raise LookupError(f"no invoice linked to payment {payment.payment_number}")
        payment_service.capture_gateway_payment(
            db,
            payment,
            invoice,
            gateway_payment_id=entity.get("id") or "",
            payload={"source": "reconciliation", "entity": entity},
            # Fetched from Razorpay with our keys rather than signed by the browser.
            signature_verified=False,
            actor_label=RECONCILE_ACTOR,
            lock=False,
        )
        if checkout_session_id:
            from backend.app.services import checkout_service

            checkout_service.complete_session_from_capture(db, payment, entity)
        return "captured"
    if attempts and all(a.get("status") == "failed" for a in attempts):
        last = attempts[-1]
        payment_service.fail_gateway_payment(
            db,
            payment,
            reason=last.get("error_description") or last.get("error_reason") or "Payment failed at the gateway",
            payload={"source": "reconciliation", "entity": last},
            actor_label=RECONCILE_ACTOR,
            status=audit.AuditStatus.WARNING,
        )
        return "failed"
    return "unchanged"


def reconcile_stale_gateway_payments(db: Session, *, now=None) -> Dict[str, int]:
    """Ask Razorpay about every stale PENDING order and settle it. Commits per payment."""
    now = now or utcnow()
    counts = {"checked": 0, "captured": 0, "failed": 0, "unchanged": 0, "errors": 0}
    for candidate in _stale_pending(db, now):
        payment_id, order_id = candidate.id, candidate.gateway_order_id
        try:
            creds = razorpay_gateway.credentials_for(db, candidate.organization_id)
            if not razorpay_gateway.is_configured(creds):
                continue
            attempts = razorpay_gateway.fetch_order_payments(order_id, creds=creds)
            payment = payment_service.lock_payment(db, candidate)
            if payment.status != PaymentStatus.PENDING:  # settled meanwhile by webhook or verify
                db.rollback()
                continue
            counts["checked"] += 1
            counts[_settle(db, payment, attempts)] += 1
            db.commit()
        except Exception:
            db.rollback()
            counts["errors"] += 1
            # Ids only: never gateway payloads or credentials.
            logger.exception("Gateway reconciliation failed for payment %s (order %s)", payment_id, order_id)
    return counts
