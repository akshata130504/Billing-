"""/webhooks — inbound Razorpay events (raw body, HMAC verified, idempotent on event id)."""
import hashlib
import json
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.core.logging import logger
from backend.app.models import AuditStatus, Invoice, PaymentStatus, Refund, RefundStatus, WebhookEvent, utcnow
from backend.app.schemas.public import WebhookAck
from backend.app.services import audit, invoice_service, payment_service, razorpay_gateway

router = APIRouter()

SIGNATURE_HEADER = "X-Razorpay-Signature"
EVENT_ID_HEADER = "X-Razorpay-Event-Id"


def _entity(payload: Dict[str, Any], kind: str) -> Dict[str, Any]:
    return ((payload.get("payload") or {}).get(kind) or {}).get("entity") or {}


def _invoice_for_payment(db: Session, payment, entity: Dict[str, Any]) -> Optional[Invoice]:
    notes = dict((payment.gateway_payload or {}).get("notes") or {})
    if isinstance(entity.get("notes"), dict):
        notes.update(entity["notes"])
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
    payment = payment_service.find_by_order_id(db, order_id)
    if payment is None:
        raise LookupError(f"no payment with gateway_order_id {order_id}")
    event.organization_id = payment.organization_id
    if payment.status != PaymentStatus.PENDING:
        return  # already captured via razorpay-verify or an earlier delivery
    invoice = _invoice_for_payment(db, payment, entity)
    if invoice is None:
        raise LookupError(f"no invoice linked to payment {payment.payment_number}")
    payment_service.capture_gateway_payment(
        db,
        payment,
        invoice,
        gateway_payment_id=entity.get("id") or "",
        payload={"source": "webhook", "event_id": event.event_id, "entity": entity},
        signature_verified=True,
        actor_label=audit.WEBHOOK_ACTOR,
    )


def _handle_payment_failed(db: Session, event: WebhookEvent, payload: Dict[str, Any]) -> None:
    entity = _entity(payload, "payment")
    order_id = entity.get("order_id")
    payment = payment_service.find_by_order_id(db, order_id) if order_id else None
    if payment is None:
        raise LookupError(f"no payment with gateway_order_id {order_id}")
    event.organization_id = payment.organization_id
    reason = entity.get("error_description") or entity.get("error_reason") or entity.get("error_code")
    payment_service.fail_gateway_payment(
        db,
        payment,
        reason=reason,
        payload={"source": "webhook", "event_id": event.event_id, "entity": entity},
        actor_label=audit.WEBHOOK_ACTOR,
    )


def _handle_refund_processed(db: Session, event: WebhookEvent, payload: Dict[str, Any]) -> None:
    entity = _entity(payload, "refund")
    refund_id = entity.get("id")
    gateway_payment_id = entity.get("payment_id")
    existing = db.scalars(select(Refund).where(Refund.gateway_refund_id == refund_id)).first() if refund_id else None
    if existing is not None:
        event.organization_id = existing.organization_id
        if existing.status != RefundStatus.PROCESSED:
            existing.status = RefundStatus.PROCESSED
            existing.updated_at = utcnow()
        return
    payment = payment_service.find_by_gateway_payment_id(db, gateway_payment_id) if gateway_payment_id else None
    if payment is None:
        raise LookupError(f"no payment with gateway_payment_id {gateway_payment_id}")
    event.organization_id = payment.organization_id
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


HANDLERS = {
    "payment.captured": _handle_payment_captured,
    "payment.failed": _handle_payment_failed,
    "refund.processed": _handle_refund_processed,
}


@router.post("/razorpay", response_model=WebhookAck, summary="Razorpay webhook receiver")
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

    if not razorpay_gateway.verify_webhook_signature(raw, signature):
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
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "UNAUTHORIZED", "message": "Webhook signature verification failed.", "details": {}}},
        )

    # Idempotency: a verified event we have already stored is acknowledged without re-processing.
    existing = db.scalars(select(WebhookEvent).where(WebhookEvent.event_id == event_id)).first()
    if existing is not None:
        return {"received": True}

    event = WebhookEvent(provider="razorpay", event_id=event_id, event_type=event_type, payload=payload, signature_valid=True)
    db.add(event)
    db.flush()

    handler = HANDLERS.get(event_type)
    try:
        if handler is not None:
            handler(db, event, payload)
        event.processed_at = utcnow()
        if handler is None:
            event.error = "ignored: unhandled event type"
    except Exception as exc:  # store the failure, still acknowledge so Razorpay stops retrying a bad event
        logger.warning("Razorpay webhook %s (%s) could not be processed: %s", event_id, event_type, exc)
        db.rollback()
        event = WebhookEvent(
            provider="razorpay",
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            signature_valid=True,
            processed_at=utcnow(),
            error=str(exc)[:2000],
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
    db.commit()
    return {"received": True}
