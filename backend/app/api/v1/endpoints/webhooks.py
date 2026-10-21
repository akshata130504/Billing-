"""/webhooks — inbound Razorpay events (raw body, HMAC verified, idempotent on event id).

Signature verification
    The platform webhook secret (env) is tried first. An organization that connected
    its own Razorpay account configures that account's webhook with its own secret,
    so when the platform secret does not match, the event is attributed to an
    organization (payload notes.organization_id, else the payment/order it refers to)
    and verified against that organization's secret. An event verified with an
    organization's secret may only touch that organization's records.

Retries
    Transient problems — the referenced payment/refund is not (yet) in our database
    (LookupError), a lock/DB error — answer 503 and are NOT stored, so Razorpay
    redelivers. Permanent problems (malformed payload, amount mismatch: ValueError /
    domain validation errors) are stored with the error and acknowledged with 200 so
    Razorpay stops retrying an event we will never accept. A LookupError for an event
    older than RETRY_WINDOW is treated as permanent so an unrelated event (e.g. a
    payment made outside this app on the same account) cannot make Razorpay disable
    the webhook after a day of failures.
"""
import hashlib
import json
import time
import uuid
from typing import Any, Dict, Optional

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.core.alerts import send_alert
from backend.app.core.exceptions import AppException
from backend.app.core.logging import logger
from backend.app.core.rate_limit import limiter, webhook_rate_limit
from backend.app.models import (
    AuditStatus,
    GatewaySubscription,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    RefundStatus,
    WebhookEvent,
    utcnow,
)
from backend.app.schemas.public import WebhookAck
from backend.app.services import audit, dunning_service, payment_service, razorpay_gateway

router = APIRouter()

SIGNATURE_HEADER = "X-Razorpay-Signature"
EVENT_ID_HEADER = "X-Razorpay-Event-Id"

# How long a "record not found" is considered a race worth retrying (seconds).
RETRY_WINDOW_SECONDS = 30 * 60

# Alert when this many signature failures arrive within the window (a burst
# usually means a rotated/mis-configured secret or someone probing the endpoint).
SIGNATURE_FAILURE_ALERT_THRESHOLD = 5
SIGNATURE_FAILURE_WINDOW_SECONDS = 5 * 60


def mask_identifier(value: Optional[str]) -> str:
    """Keep only enough of a gateway/event id to correlate logs (``evt_…a1b2``)."""
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "…" + text[-2:]
    return f"{text[:4]}…{text[-4:]}"


def _duplicate_ack() -> JSONResponse:
    """Deterministic answer for an event id we already stored (or a concurrent
    delivery of it that won the race): acknowledged, not re-processed."""
    return JSONResponse(status_code=200, content={"received": True, "status": "duplicate"})


def _alert_signature_burst(db: Session, event_type: str) -> None:
    try:
        since = utcnow() - timedelta(seconds=SIGNATURE_FAILURE_WINDOW_SECONDS)
        count = db.scalar(
            select(func.count(WebhookEvent.id)).where(
                WebhookEvent.signature_valid.is_(False),
                WebhookEvent.received_at >= since,
            )
        ) or 0
    except Exception:  # alerting must never break the webhook
        return
    if count >= SIGNATURE_FAILURE_ALERT_THRESHOLD:
        send_alert(
            "payment.webhook_signature_failures",
            f"{count} Razorpay webhook signature failures in the last {SIGNATURE_FAILURE_WINDOW_SECONDS // 60} minutes",
            {"count": int(count), "window_seconds": SIGNATURE_FAILURE_WINDOW_SECONDS, "last_event_type": event_type},
            severity="critical",
            dedup_key="payment.webhook_signature_failures",
        )


def _alert_processing_failure(event_id: str, event_type: str, error: str, *, retryable: bool) -> None:
    send_alert(
        "payment.webhook_failed",
        f"Razorpay webhook {event_type} {'deferred for retry' if retryable else 'processing failed'}",
        {
            "event_id": mask_identifier(event_id),
            "event_type": event_type,
            "error": str(error)[:300],
            "retryable": retryable,
        },
        severity="warning" if retryable else "error",
        dedup_key=f"payment.webhook_failed:{event_type}:{'retry' if retryable else 'permanent'}",
    )


class RetryableWebhookError(Exception):
    """Raise from a handler to make Razorpay redeliver the event."""


def _entity(payload: Dict[str, Any], kind: str) -> Dict[str, Any]:
    return ((payload.get("payload") or {}).get(kind) or {}).get("entity") or {}


def _check_org(event: WebhookEvent, payment: Payment) -> None:
    """An event verified with an organization's own secret may only act on that organization's payments."""
    verified_org = getattr(event, "_verified_org_id", None)
    if verified_org and payment.organization_id != verified_org:
        raise ValueError("event signed by a different organization than the referenced payment")


def _is_subscription_charge(entity: Dict[str, Any]) -> bool:
    """A payment Razorpay made itself for a Razorpay Subscription (UPI AutoPay / e-mandate): it carries
    the Razorpay invoice of the subscription cycle, and this app never creates Razorpay invoices."""
    return str(entity.get("invoice_id") or "").startswith("inv_")


def _handle_subscription_event(db: Session, event: WebhookEvent, payload: Dict[str, Any]) -> None:
    from backend.app.services import autopay_service

    autopay_service.handle_subscription_event(db, event, payload, verified_org_id=getattr(event, "_verified_org_id", None))


def _invoice_for_payment(db: Session, payment, entity: Dict[str, Any]) -> Optional[Invoice]:
    notes: Dict[str, Any] = {}
    if isinstance(entity.get("notes"), dict):
        notes.update(entity["notes"])
    # Notes we stored when creating the order win over whatever the entity carries.
    notes.update(dict((payment.gateway_payload or {}).get("notes") or {}))
    invoice_id = notes.get("invoice_id")
    if invoice_id:
        inv = db.scalars(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.organization_id == payment.organization_id)
        ).first()
        if inv is not None:
            return inv
    # Fall back to an existing allocation (re-delivered capture after a verify).
    if payment.allocations:
        return payment.allocations[0].invoice
    return None


def _handle_payment_captured(db: Session, event: WebhookEvent, payload: Dict[str, Any]) -> None:
    entity = _entity(payload, "payment")
    order_id = entity.get("order_id")
    if not order_id:
        raise ValueError("payment.captured without order_id")
    from backend.app.core.tenant_context import set_tenant_context, system_context
    with system_context():
        payment = payment_service.find_by_order_id(db, order_id)
    if payment is None:
        if _is_subscription_charge(entity):
            return  # recorded by the subscription.charged event of the same charge
        raise LookupError(f"no payment with gateway_order_id {order_id}")
    _check_org(event, payment)
    event.organization_id = payment.organization_id
    set_tenant_context(payment.organization_id)
    payment = payment_service.lock_payment(db, payment)
    if payment.status not in (PaymentStatus.PENDING, PaymentStatus.FAILED):
        return  # already captured via razorpay-verify / checkout confirm or an earlier delivery

    # Verify amount and currency from webhook entity against expected payment record
    # A capture without an amount is never applied (fail closed): Razorpay always sends it.
    entity_amount_paise = entity.get("amount")
    if entity_amount_paise is None:
        raise ValueError("Captured payment amount mismatch: the event carries no amount")
    entity_amount = payment_service.from_paise(entity_amount_paise)
    if entity_amount != payment.amount:
        raise ValueError(f"Captured payment amount mismatch: expected {payment.amount}, got {entity_amount}")

    entity_currency = entity.get("currency")
    if entity_currency and entity_currency.upper() != payment.currency.upper():
        raise ValueError(f"Captured payment currency mismatch: expected {payment.currency}, got {entity_currency}")

    invoice = _invoice_for_payment(db, payment, entity)
    stored_notes = dict((payment.gateway_payload or {}).get("notes") or {})
    checkout_session_id = stored_notes.get("checkout_session_id")
    if invoice is None and not checkout_session_id:
        raise LookupError(f"no invoice linked to payment {payment.payment_number}")
    payment_service.capture_gateway_payment(
        db,
        payment,
        invoice,
        gateway_payment_id=entity.get("id") or "",
        payload={"source": "webhook", "event_id": event.event_id, "entity": entity},
        signature_verified=True,
        actor_label=audit.WEBHOOK_ACTOR,
        lock=False,
    )
    if checkout_session_id:
        # The customer may have closed the browser before /confirm: finish the
        # checkout (subscription activation, saved card) from the webhook instead.
        from backend.app.services import checkout_service

        checkout_service.complete_session_from_capture(db, payment, entity)


def _handle_payment_failed(db: Session, event: WebhookEvent, payload: Dict[str, Any]) -> None:
    entity = _entity(payload, "payment")
    order_id = entity.get("order_id")
    from backend.app.core.tenant_context import set_tenant_context, system_context
    with system_context():
        payment = payment_service.find_by_order_id(db, order_id) if order_id else None
    if payment is None:
        if _is_subscription_charge(entity):
            return  # an AutoPay charge attempt: Razorpay retries it; subscription.pending/halted inform us
        raise LookupError(f"no payment with gateway_order_id {order_id}")
    _check_org(event, payment)
    event.organization_id = payment.organization_id
    set_tenant_context(payment.organization_id)
    payment = payment_service.lock_payment(db, payment)
    reason = entity.get("error_description") or entity.get("error_reason") or entity.get("error_code")
    payment_service.fail_gateway_payment(
        db,
        payment,
        reason=reason,
        payload={"source": "webhook", "event_id": event.event_id, "entity": entity},
        actor_label=audit.WEBHOOK_ACTOR,
    )

    # Subscription renewal invoices get the existing Dunning recovery flow (retry
    # schedule, past_due status, follow-up emails); one-time invoices don't.
    # trigger_dunning_for_failed_payment already de-dupes on invoice_id, so a
    # redelivered event or a second distinct failed attempt for the same invoice
    # never opens a second case.
    invoice = _invoice_for_payment(db, payment, entity)
    if invoice is not None and invoice.subscription_id and invoice.status not in (InvoiceStatus.PAID, InvoiceStatus.VOID):
        dunning_service.trigger_dunning_for_failed_payment(
            db,
            organization_id=payment.organization_id,
            invoice_id=invoice.id,
            customer_id=invoice.customer_id,
            subscription_id=invoice.subscription_id,
            reason=reason or "payment_failed",
            payment_method_type=entity.get("method") or "card",
        )


def _handle_refund_processed(db: Session, event: WebhookEvent, payload: Dict[str, Any]) -> None:
    entity = _entity(payload, "refund")
    refund_id = entity.get("id")
    if not refund_id:
        raise ValueError("refund.processed without refund id")
    gateway_payment_id = entity.get("payment_id")
    from backend.app.core.tenant_context import set_tenant_context, system_context
    with system_context():
        payment = payment_service.find_by_gateway_payment_id(db, gateway_payment_id) if gateway_payment_id else None
        if payment is None:
            existing = payment_service.find_refund_by_gateway_id(db, refund_id)
            if existing is None:
                raise LookupError(f"no payment with gateway_payment_id {gateway_payment_id}")
            payment = existing.payment
    _check_org(event, payment)
    event.organization_id = payment.organization_id
    set_tenant_context(payment.organization_id)
    # Lock the payment first so two deliveries of the same refund serialise here and
    # the second one sees the refund row the first one wrote.
    payment = payment_service.lock_payment(db, payment)
    existing = payment_service.find_refund_by_gateway_id(db, refund_id)
    if existing is not None:
        if existing.status == RefundStatus.PENDING:
            payment_service.settle_pending_refund(db, existing, actor_label=audit.WEBHOOK_ACTOR)
        elif existing.status == RefundStatus.FAILED:
            logger.warning("refund.processed received for refund %s previously marked failed", refund_id)
        return
    amount = payment_service.from_paise(entity.get("amount") or 0)
    notes = entity.get("notes") if isinstance(entity.get("notes"), dict) else {}
    payment_service.apply_refund(
        db,
        payment,
        amount,
        reason=(notes or {}).get("reason") or "Refund processed by Razorpay",
        gateway_refund_id=refund_id,
        refund_status=RefundStatus.PROCESSED,
        actor_label=audit.WEBHOOK_ACTOR,
    )


def _handle_refund_failed(db: Session, event: WebhookEvent, payload: Dict[str, Any]) -> None:
    entity = _entity(payload, "refund")
    refund_id = entity.get("id")
    if not refund_id:
        raise ValueError("refund.failed without refund id")
    from backend.app.core.tenant_context import set_tenant_context, system_context
    # The refund's organization is not known yet: look it up explicitly as the system, then
    # continue in that organization's tenant context (as the other handlers do).
    with system_context():
        existing = payment_service.find_refund_by_gateway_id(db, refund_id)
        payment = existing.payment if existing is not None else None
    if existing is None:
        # A refund we never booked (e.g. started and failed in the Razorpay
        # dashboard) leaves nothing to undo.
        event.error = "ignored: refund not recorded here"
        return
    _check_org(event, payment)
    event.organization_id = existing.organization_id
    set_tenant_context(existing.organization_id)
    reason = entity.get("error_description") or entity.get("status_details") or "Refund failed at Razorpay"
    payment_service.fail_refund(db, existing, reason=str(reason)[:500], actor_label=audit.WEBHOOK_ACTOR)


HANDLERS = {
    "payment.captured": _handle_payment_captured,
    "payment.failed": _handle_payment_failed,
    "refund.processed": _handle_refund_processed,
    "refund.failed": _handle_refund_failed,
    # UPI AutoPay / e-mandate (Razorpay Subscriptions); see services/autopay_service.py.
    **{
        f"subscription.{name}": _handle_subscription_event
        for name in ("authenticated", "activated", "charged", "pending", "halted", "cancelled", "completed",
                     "paused", "resumed", "updated")
    },
}


def _attributed_organization_id(db: Session, payload: Dict[str, Any]) -> Optional[str]:
    """Best-effort: which organization's Razorpay account sent this (unverified) event."""
    from backend.app.core.tenant_context import system_context

    body = payload.get("payload") or {}
    for kind in ("payment", "refund", "order", "subscription"):
        entity = (body.get(kind) or {}).get("entity") or {}
        notes = entity.get("notes") if isinstance(entity.get("notes"), dict) else {}
        if notes.get("organization_id"):
            return str(notes["organization_id"])
    payment_entity = (body.get("payment") or {}).get("entity") or {}
    order_id = payment_entity.get("order_id")
    with system_context():
        if order_id:
            org = db.scalars(select(Payment.organization_id).where(Payment.gateway_order_id == order_id)).first()
            if org:
                return org
        subscription_entity = (body.get("subscription") or {}).get("entity") or {}
        if subscription_entity.get("id"):
            org = db.scalars(
                select(GatewaySubscription.organization_id).where(
                    GatewaySubscription.gateway_subscription_id == subscription_entity["id"]
                )
            ).first()
            if org:
                return org
        refund_entity = (body.get("refund") or {}).get("entity") or {}
        pay_id = refund_entity.get("payment_id") or payment_entity.get("id")
        if pay_id:
            org = db.scalars(select(Payment.organization_id).where(Payment.gateway_payment_id == pay_id)).first()
            if org:
                return org
    return None


def _verify_signature(db: Session, raw: bytes, signature: Optional[str], payload: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """(valid, organization_id the signature was verified for, or None for the platform secret)."""
    if razorpay_gateway.verify_webhook_signature(raw, signature):
        return True, None
    org_id = _attributed_organization_id(db, payload)
    if org_id:
        creds = razorpay_gateway.credentials_for(db, org_id)
        platform_secret = razorpay_gateway.platform_credentials().webhook_secret
        if creds.webhook_secret and creds.webhook_secret != platform_secret:
            if razorpay_gateway.verify_webhook_signature(raw, signature, secret=creds.webhook_secret):
                return True, org_id
    return False, None


def _is_retryable(exc: Exception, payload: Dict[str, Any]) -> bool:
    if isinstance(exc, (RetryableWebhookError, OperationalError)):
        return True
    if isinstance(exc, LookupError):
        created = payload.get("created_at")
        try:
            age = time.time() - float(created) if created is not None else 0.0
        except (TypeError, ValueError):
            age = 0.0
        return age <= RETRY_WINDOW_SECONDS
    return False


@router.post("/razorpay", response_model=WebhookAck, summary="Razorpay webhook receiver")
@limiter.limit(webhook_rate_limit)
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    signature = request.headers.get(SIGNATURE_HEADER)
    body_hash = hashlib.sha256(raw).hexdigest()
    event_id = (request.headers.get(EVENT_ID_HEADER) or "").strip() or body_hash

    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(payload, dict):
            payload = {"raw": payload}
    except (ValueError, UnicodeDecodeError):
        payload = {"raw": raw.decode("utf-8", errors="replace")}
    event_type = str(payload.get("event") or "unknown")

    valid, verified_org_id = _verify_signature(db, raw, signature, payload)
    if not valid:
        rejected = WebhookEvent(
            provider="razorpay",
            event_id=f"rejected:{uuid.uuid4().hex}",
            event_type=event_type,
            payload=payload,
            signature_valid=False,
            error="invalid signature",
            processed_at=utcnow(),
        )
        db.add(rejected)
        audit.record(
            db,
            action="WEBHOOK_REJECTED",
            entity_type="webhook",
            entity_id=rejected.id,
            entity_label=f"razorpay {event_type}",
            actor_label=audit.WEBHOOK_ACTOR,
            after={"event_id": event_id, "event_type": event_type, "reason": "invalid signature"},
            status=AuditStatus.DENIED,
        )
        db.commit()
        _alert_signature_burst(db, event_type)
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "UNAUTHORIZED", "message": "Webhook signature verification failed.", "details": {}}},
        )

    # Idempotency: a verified event we have already stored is acknowledged without re-processing.
    existing = db.scalars(select(WebhookEvent).where(WebhookEvent.event_id == event_id)).first()
    if existing is not None:
        return _duplicate_ack()

    event = WebhookEvent(
        provider="razorpay",
        event_id=event_id,
        event_type=event_type,
        payload=payload,
        signature_valid=True,
        organization_id=verified_org_id,
    )
    event._verified_org_id = verified_org_id
    try:
        # A concurrent delivery of the same event id that inserted first makes
        # this INSERT fail on the unique event_id (on PostgreSQL it waits for
        # the winner's commit). That loser is a duplicate, not a 500.
        # PostgreSQL: inside a SAVEPOINT. SQLite (pysqlite) cannot nest one in
        # an un-begun transaction - RELEASE would COMMIT the row, so a later
        # retryable 503 rollback could not remove it - and it serialises
        # writers anyway, so a plain flush is used there.
        if db.get_bind().dialect.name == "sqlite":
            db.add(event)
            db.flush()
        else:
            with db.begin_nested():
                db.add(event)
                db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("Razorpay webhook %s (%s) duplicate delivery lost the insert race", event_id, event_type)
        return _duplicate_ack()

    handler = HANDLERS.get(event_type)
    try:
        if handler is not None:
            handler(db, event, payload)
        event.processed_at = utcnow()
        if handler is None:
            event.error = "ignored: unhandled event type"
    except Exception as exc:
        db.rollback()
        if _is_retryable(exc, payload):
            # Not stored: the redelivery must be processed, not short-circuited as a duplicate.
            logger.warning("Razorpay webhook %s (%s) deferred for retry: %s", event_id, event_type, exc)
            if not isinstance(exc, LookupError):  # a not-yet-visible record is routine; DB/lock errors are not
                _alert_processing_failure(event_id, event_type, type(exc).__name__, retryable=True)
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "RETRY_LATER", "message": "Event could not be processed yet; please retry.", "details": {}}},
            )
        # Permanent: store the failure and acknowledge so Razorpay stops retrying.
        logger.warning("Razorpay webhook %s (%s) rejected: %s", event_id, event_type, exc)
        message = exc.message if isinstance(exc, AppException) and getattr(exc, "message", None) else str(exc)
        _alert_processing_failure(event_id, event_type, message, retryable=False)
        event = WebhookEvent(
            provider="razorpay",
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            signature_valid=True,
            organization_id=verified_org_id,
            processed_at=utcnow(),
            error=str(message)[:2000],
        )
        db.add(event)

    audit.record(
        db,
        action="WEBHOOK_RECEIVED",
        entity_type="webhook",
        entity_id=event.id,
        entity_label=f"razorpay {event_type}",
        organization_id=event.organization_id,
        actor_label=audit.WEBHOOK_ACTOR,
        after={"event_id": event_id, "event_type": event_type, "error": event.error},
        status=AuditStatus.WARNING if event.error and not event.error.startswith("ignored") else AuditStatus.SUCCESS,
    )
    try:
        db.commit()
    except IntegrityError:
        # Only reachable on the permanent-failure path: our first insert was
        # rolled back and a concurrent delivery stored the same event id meanwhile.
        db.rollback()
        if db.scalars(select(WebhookEvent.id).where(WebhookEvent.event_id == event_id)).first():
            return _duplicate_ack()
        raise
    return {"received": True}
