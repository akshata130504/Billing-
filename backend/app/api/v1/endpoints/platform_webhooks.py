"""Razorpay webhook for ROOMAN's own account (organizations paying for Rooman plans). Mounted at
/webhooks/razorpay-platform - separate from the tenant webhook (/webhooks/razorpay, webhooks.py), with its
own secret (PLATFORM_RAZORPAY_WEBHOOK_SECRET) and its own ledger (platform_webhook_events).

Not under /api/v1/platform/...: that prefix only accepts the platform console's own browser origin, and
Razorpay's servers are not a browser.

    secret not configured     503, nothing read or stored (Razorpay retries later)
    invalid signature         400, nothing stored
    known event id            200 "duplicate", effects not repeated
    supported event           the subscription's CURRENT state is fetched from Razorpay and applied
                              (services/platform_payment_service.py); ledger row + effects in ONE commit
    Razorpay unreachable      503, nothing stored -> Razorpay redelivers and it is processed then
    anything else            200, recorded as ignored / needs_review (never retried forever)

Signatures are checked over the exact raw request bytes, before the body is parsed. Only normalized
fields are stored, never the payload.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.core.exceptions import GatewayNotConfiguredError
from backend.app.core.logging import logger
from backend.app.core.rate_limit import limiter, webhook_rate_limit
from backend.app.models import PlatformWebhookEvent
from backend.app.services import platform_payment_service as payments, platform_razorpay as provider

router = APIRouter()

SIGNATURE_HEADER = "X-Razorpay-Signature"
EVENT_ID_HEADER = "X-Razorpay-Event-Id"
# Subscription events this lifecycle acts on (https://razorpay.com/docs/payments/subscriptions/subscribe-to-webhooks/).
# Each only triggers a re-read of the subscription at Razorpay; the event name itself decides nothing.
SUPPORTED_EVENTS = frozenset({
    "subscription.authenticated", "subscription.activated", "subscription.charged", "subscription.pending",
    "subscription.halted", "subscription.cancelled", "subscription.completed",
})


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": {}}})


def _entity(payload: Dict[str, Any], kind: str) -> Dict[str, Any]:
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    block = body.get(kind) if isinstance(body.get(kind), dict) else {}
    return block.get("entity") if isinstance(block.get("entity"), dict) else {}


def _mode() -> Optional[str]:
    try:
        return provider.mode()
    except GatewayNotConfiguredError:
        return None


def _created_at(payload: Dict[str, Any]) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(payload.get("created_at")), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


@router.post("/razorpay-platform", summary="Razorpay webhook for Rooman plan subscriptions")
@limiter.limit(webhook_rate_limit)
async def razorpay_platform_webhook(request: Request, db: Session = Depends(get_db)):
    if not provider.webhook_secret():
        return _error(503, "WEBHOOK_NOT_CONFIGURED", "This webhook is not configured.")
    raw = await request.body()
    if not provider.verify_webhook_signature(raw, request.headers.get(SIGNATURE_HEADER)):
        logger.warning("Platform Razorpay webhook rejected: invalid signature")
        return _error(400, "UNAUTHORIZED", "Webhook signature verification failed.")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        payload = None
    if not isinstance(payload, dict):
        return _error(400, "BAD_REQUEST", "Malformed webhook body.")
    event_id = (request.headers.get(EVENT_ID_HEADER) or "").strip()[:128] or "sha256:" + hashlib.sha256(raw).hexdigest()
    if db.scalar(select(PlatformWebhookEvent.id).where(PlatformWebhookEvent.event_id == event_id)):
        return {"received": True, "status": "duplicate"}

    event_type = str(payload.get("event") or "unknown")[:64]
    subscription_id = str(_entity(payload, "subscription").get("id") or "")[:64] or None
    payment_id = str(_entity(payload, "payment").get("id") or "")[:64] or None
    status, outcome, org_id = "ignored", "unsupported_event", None
    if event_type in SUPPORTED_EVENTS and subscription_id:
        try:
            result = payments.sync_provider_subscription(db, subscription_id, payment_id=payment_id)
        except (payments.RetryLater, GatewayNotConfiguredError):
            db.rollback()
            logger.warning("Platform webhook %s (%s) deferred: Razorpay unavailable", event_id, event_type)
            return _error(503, "RETRY_LATER", "Event could not be processed yet; please retry.")
        outcome, org_id = result.outcome, result.organization_id
        status = ("needs_review" if outcome in payments.REVIEW_OUTCOMES
                  else "ignored" if outcome in payments.IGNORED_OUTCOMES else "processed")

    db.add(PlatformWebhookEvent(
        provider="razorpay", event_id=event_id, event_type=event_type, mode=_mode(),
        provider_subscription_id=subscription_id, provider_payment_id=payment_id, organization_id=org_id,
        status=status, outcome=outcome[:40], event_created_at=_created_at(payload), received_at=datetime.now(timezone.utc),
    ))
    try:
        db.commit()  # the ledger row and the subscription changes together
    except IntegrityError:
        db.rollback()  # a concurrent delivery of the same event committed first: its effects stand
        return {"received": True, "status": "duplicate"}
    return {"received": True, "status": status}
