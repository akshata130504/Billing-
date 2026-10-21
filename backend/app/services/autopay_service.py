"""UPI AutoPay / e-mandate through Razorpay Subscriptions (BUSINESS-217).

Flow
----
1. Staff enable AutoPay on a plan (``Plan.autopay_enabled``) and, for a subscription to it, call
   ``setup_autopay``. That creates a Razorpay plan for exactly the subscription's per-period total
   (tax included) and a Razorpay subscription starting on the next billing date, and returns a
   one-time link to ``/autopay/<token>``.
2. The customer opens that page; Razorpay Checkout (``subscription_id``) shows the eligible mandate
   methods of the merchant account (UPI AutoPay, card, e-mandate) and takes the authorisation.
   ``confirm_authorization`` checks the Checkout signature *and* re-reads the subscription from
   Razorpay; the browser's word alone never marks a mandate authorised.
3. Razorpay charges every cycle and retries a failed charge itself (T+1..T+3, then ``halted``).
   ``handle_subscription_event`` applies the ``subscription.*`` webhooks: state (newest event wins),
   each charge recorded once (unique gateway payment id) against the renewal invoice, and one
   customer notification per authorisation / charge / failed cycle / halt.

This app never charges an AutoPay subscription itself (dunning only charges saved card tokens), so
there is no second retry loop that could double-charge. Cancelling or pausing the local subscription
cancels the mandate first, so nothing is charged afterwards.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import (
    ConflictError,
    EntityNotFoundError,
    GatewayNotConfiguredError,
    InvalidStateError,
    ValidationAppError,
)
from backend.app.core.logging import logger
from backend.app.models import (
    OPEN_INVOICE_STATUSES,
    AutopayStatus,
    BillingInterval,
    Customer,
    GatewaySubscription,
    Invoice,
    NotificationChannel,
    Organization,
    Payment,
    PaymentGateway,
    PaymentMethod,
    Plan,
    Subscription,
    SubscriptionStatus,
    utcnow,
)
from backend.app.services import audit, payment_service, razorpay_gateway, timezones
from backend.app.services.email import frontend_url
from backend.app.services.money import q2

# BillingInterval -> (Razorpay plan period, intervals per local interval). Razorpay has no
# quarterly/semiannual period in every API version, so those are expressed in months.
_PERIODS = {
    BillingInterval.MONTHLY: ("monthly", 1),
    BillingInterval.QUARTERLY: ("monthly", 3),
    BillingInterval.SEMIANNUAL: ("monthly", 6),
    BillingInterval.YEARLY: ("yearly", 1),
}
# A mandate covers at most 10 years of cycles (Razorpay requires a finite total_count).
_MAX_MONTHS = 120
# The authorisation link (and the unused Razorpay subscription behind it) expires after this.
LINK_VALIDITY = timedelta(days=7)
# Local subscription states a mandate can be set up for.
_SETUP_STATUSES = (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE)
# Local subscription states in which a mandate must not stay live.
_ENDED_LOCAL = (SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED, SubscriptionStatus.TRIAL_EXPIRED)
# Hour (organization time) of the billing date at which Razorpay charges: after the daily renewal
# run has issued the period invoice, so the charge normally finds it.
_CHARGE_HOUR = 10


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _plan_period(plan: Plan) -> Optional[Tuple[str, int]]:
    mapped = _PERIODS.get(plan.billing_interval)
    if mapped is None:
        return None
    period, factor = mapped
    return period, factor * int(plan.interval_count or 1)


def _total_count(period: str, interval: int) -> int:
    months = interval * (12 if period == "yearly" else 1)
    return max(1, _MAX_MONTHS // months)


def _ts(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None
    except (TypeError, ValueError, OverflowError):
        return None


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes; everything here is UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def _paise(amount: Decimal) -> int:
    return int((q2(amount) * 100).to_integral_value())


def ineligibility_reason(db: Session, subscription: Subscription, *, today=None) -> Optional[str]:
    """Why AutoPay cannot be set up for `subscription` now, or None when it can."""
    plan = subscription.plan
    if plan is None or not plan.autopay_enabled:
        return "AutoPay is not enabled for this subscription's plan."
    if _plan_period(plan) is None:
        return "AutoPay needs a recurring plan (monthly, quarterly, half-yearly or yearly)."
    if subscription.status not in _SETUP_STATUSES:
        return f"AutoPay cannot be set up for a {subscription.status.value} subscription."
    if (subscription.currency or "INR").upper() != "INR":
        return "UPI AutoPay and e-mandates are available for INR subscriptions only."
    if q2(subscription.total_amount or 0) < Decimal("1.00"):
        return "The subscription's per-period amount must be at least INR 1.00."
    if not subscription.auto_renewal or subscription.cancel_at_period_end:
        return "The subscription does not renew, so there is nothing to collect automatically."
    organization = db.get(Organization, subscription.organization_id)
    today = today or timezones.org_today(organization)
    if subscription.next_billing_date is None or subscription.next_billing_date <= today:
        return "The next billing date must be in the future; collect the current period first."
    if not razorpay_gateway.is_configured(razorpay_gateway.credentials_for(db, subscription.organization_id)):
        return "Razorpay is not configured for this organization."
    return None


def _live_mandate(db: Session, organization_id: str, subscription_id: str) -> Optional[GatewaySubscription]:
    return db.scalars(
        select(GatewaySubscription)
        .where(
            GatewaySubscription.organization_id == organization_id,
            GatewaySubscription.subscription_id == subscription_id,
            GatewaySubscription.status.in_(AutopayStatus.LIVE),
        )
        .order_by(GatewaySubscription.created_at.desc())
    ).first()


def get_mandate(db: Session, organization_id: str, subscription_id: str) -> Optional[GatewaySubscription]:
    """The live mandate of a subscription, else its most recent ended one (or None)."""
    live = _live_mandate(db, organization_id, subscription_id)
    if live is not None:
        return live
    return db.scalars(
        select(GatewaySubscription)
        .where(GatewaySubscription.organization_id == organization_id, GatewaySubscription.subscription_id == subscription_id)
        .order_by(GatewaySubscription.created_at.desc())
    ).first()


def _apply_entity(row: GatewaySubscription, entity: Dict[str, Any]) -> None:
    """Copy Razorpay's subscription fields onto the row (state is never moved out of an ended one)."""
    status = str(entity.get("status") or "").lower()
    if status in AutopayStatus.ALL and row.status not in AutopayStatus.ENDED:
        row.status = status
    if entity.get("paid_count") is not None:
        row.paid_count = max(int(row.paid_count or 0), int(entity.get("paid_count") or 0))
    row.charge_at = _ts(entity.get("charge_at")) or row.charge_at
    row.current_end = _ts(entity.get("current_end")) or row.current_end
    row.short_url = entity.get("short_url") or row.short_url
    if row.status in (AutopayStatus.AUTHENTICATED, AutopayStatus.ACTIVE) and row.authorized_at is None:
        row.authorized_at = utcnow()
    if row.status in AutopayStatus.ENDED and row.ended_at is None:
        row.ended_at = _ts(entity.get("ended_at")) or utcnow()


def serialize_mandate(row: Optional[GatewaySubscription], *, link: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {
        "id": row.id,
        "subscription_id": row.subscription_id,
        "status": row.status,
        "gateway_subscription_id": row.gateway_subscription_id,
        "amount": str(q2(row.amount)),
        "currency": row.currency,
        "period": row.period,
        "interval": row.interval,
        "total_count": row.total_count,
        "paid_count": row.paid_count,
        "start_at": row.start_at.isoformat() if row.start_at else None,
        "charge_at": row.charge_at.isoformat() if row.charge_at else None,
        "authorized_at": row.authorized_at.isoformat() if row.authorized_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "last_error": row.last_error,
        "authorization_link": link,
    }


def _start_at(organization: Organization, subscription: Subscription) -> datetime:
    tz = timezones.tz_for(organization)
    local = datetime.combine(subscription.next_billing_date, time(_CHARGE_HOUR), tzinfo=tz)
    return local.astimezone(timezone.utc)


def setup_autopay(db: Session, ctx: CurrentContext, subscription: Subscription) -> Tuple[GatewaySubscription, str]:
    """Create (or reuse the still-unauthorised) Razorpay subscription for `subscription` and return
    it with a fresh authorisation link (a repeated call rotates the link, never the mandate). Commits."""
    from backend.app.services.subscription_service import lock_subscription_row

    from backend.app.services import org_lifecycle

    org_lifecycle.assert_payment_collection_allowed(db, subscription.organization_id)
    lock_subscription_row(db, subscription.id)  # serialise concurrent setups: one mandate per subscription
    db.refresh(subscription)
    reason = ineligibility_reason(db, subscription)
    if reason:
        raise InvalidStateError(reason)
    creds = razorpay_gateway.credentials_for(db, subscription.organization_id)
    token = secrets.token_urlsafe(32)

    existing = _live_mandate(db, subscription.organization_id, subscription.id)
    if existing is not None:
        if existing.status != AutopayStatus.CREATED:
            raise ConflictError(f"AutoPay is already set up for this subscription (mandate {existing.status}).")
        if existing.gateway_key_id == creds.key_id and q2(existing.amount) == q2(subscription.total_amount):
            remote = razorpay_gateway.fetch_subscription(existing.gateway_subscription_id, creds=creds)
            _apply_entity(existing, remote)
            if existing.status == AutopayStatus.CREATED:
                existing.public_token_hash = _hash(token)
                existing.updated_at = utcnow()
                audit.record(db, ctx=ctx, action="AUTOPAY_LINK_REISSUED", entity_type="subscription",
                             entity_id=subscription.id, entity_label=subscription.subscription_number,
                             after={"gateway_subscription_id": existing.gateway_subscription_id})
                db.commit()
                return existing, token
            if existing.status not in AutopayStatus.ENDED:
                db.commit()
                raise ConflictError(f"AutoPay is already set up for this subscription (mandate {existing.status}).")
        else:
            # Another Razorpay account or a changed price: retire the unused authorisation request.
            try:
                razorpay_gateway.cancel_subscription(existing.gateway_subscription_id, creds=creds)
            except Exception as exc:  # an unused `created` subscription also just expires
                logger.info("AutoPay: could not cancel superseded %s: %s", existing.gateway_subscription_id, exc)
            existing.status = AutopayStatus.CANCELLED
            existing.ended_at = utcnow()
        db.flush()

    plan = subscription.plan
    period, interval = _plan_period(plan)
    organization = db.get(Organization, subscription.organization_id)
    amount = q2(subscription.total_amount)
    notes = {"organization_id": subscription.organization_id, "subscription_id": subscription.id,
             "subscription_number": subscription.subscription_number}
    gw_plan = razorpay_gateway.create_plan(
        period=period, interval=interval, name=f"{plan.name} ({subscription.subscription_number})",
        amount_paise=_paise(amount), currency="INR", notes=notes, creds=creds,
    )
    total_count = _total_count(period, interval)
    start_at = _start_at(organization, subscription)
    gw_sub = razorpay_gateway.create_subscription(
        plan_id=gw_plan["id"], total_count=total_count, start_at=int(start_at.timestamp()),
        expire_by=int((utcnow() + LINK_VALIDITY).timestamp()), notes=notes, creds=creds,
    )
    row = GatewaySubscription(
        organization_id=subscription.organization_id,
        subscription_id=subscription.id,
        customer_id=subscription.customer_id,
        gateway="razorpay",
        gateway_key_id=creds.key_id,
        gateway_plan_id=gw_plan["id"],
        gateway_subscription_id=gw_sub["id"],
        status=AutopayStatus.CREATED,
        amount=amount,
        currency="INR",
        period=period,
        interval=interval,
        total_count=total_count,
        paid_count=0,
        short_url=gw_sub.get("short_url"),
        public_token_hash=_hash(token),
        start_at=start_at,
    )
    _apply_entity(row, gw_sub)
    db.add(row)
    db.flush()
    audit.record(db, ctx=ctx, action="AUTOPAY_REQUESTED", entity_type="subscription", entity_id=subscription.id,
                 entity_label=subscription.subscription_number,
                 after={"gateway_subscription_id": row.gateway_subscription_id, "amount": str(amount),
                        "period": period, "interval": interval, "total_count": total_count,
                        "start_at": start_at.isoformat()})
    db.commit()
    return row, token


def authorization_link(token: str) -> str:
    return frontend_url(f"autopay/{token}")


def stop_for_subscription(db: Session, subscription: Subscription, *, reason: str, ctx: Optional[CurrentContext] = None) -> None:
    """Cancel the live mandate at Razorpay (immediately) before the local subscription is cancelled
    or paused, so nothing is charged afterwards. Raises GatewayError if Razorpay refuses: the caller's
    change must then not go ahead while the mandate could still charge. No commit."""
    row = _live_mandate(db, subscription.organization_id, subscription.id)
    if row is None:
        return
    creds = razorpay_gateway.credentials_for(db, subscription.organization_id)
    try:
        remote = razorpay_gateway.cancel_subscription(row.gateway_subscription_id, creds=creds)
        _apply_entity(row, remote)
    except Exception as exc:
        if row.status != AutopayStatus.CREATED:
            raise  # an authorised mandate could still charge: do not pretend it stopped
        # Never authorised: it cannot charge and its link expires on its own (expire_by).
        logger.info("AutoPay: unauthorised %s not cancelled at Razorpay (%s); retired locally", row.gateway_subscription_id, exc)
    row.status = AutopayStatus.CANCELLED
    row.ended_at = row.ended_at or utcnow()
    row.updated_at = utcnow()
    db.flush()
    audit.record(db, ctx=ctx, actor_label=None if ctx else audit.SYSTEM_ACTOR, action="AUTOPAY_CANCELLED",
                 entity_type="subscription", entity_id=subscription.id, entity_label=subscription.subscription_number,
                 organization_id=subscription.organization_id,
                 after={"gateway_subscription_id": row.gateway_subscription_id, "reason": reason})


def stop_quietly(db: Session, subscription: Subscription, *, reason: str) -> None:
    """Best-effort stop for automatic paths (renewal expiry, dunning cancellation): a Razorpay outage
    must not abort a whole batch. A mandate left live is cancelled by the next webhook it sends
    (handle_subscription_event checks the local subscription), and the failure is logged."""
    try:
        with db.begin_nested():
            stop_for_subscription(db, subscription, reason=reason)
    except Exception as exc:
        logger.error("AutoPay: could not cancel the mandate of ended subscription %s: %s", subscription.id, exc)


def cancel_autopay(db: Session, ctx: CurrentContext, subscription: Subscription) -> GatewaySubscription:
    """Staff: stop AutoPay for a subscription (the subscription itself stays as it is). Commits."""
    from backend.app.services.subscription_service import lock_subscription_row

    lock_subscription_row(db, subscription.id)
    row = _live_mandate(db, subscription.organization_id, subscription.id)
    if row is None:
        raise InvalidStateError("This subscription has no active AutoPay mandate.")
    stop_for_subscription(db, subscription, reason="cancelled by staff", ctx=ctx)
    db.commit()
    return row


# --- the customer's authorisation page ----------------------------------------------------------------------------


def get_by_token(db: Session, token: str) -> GatewaySubscription:
    from backend.app.core.tenant_context import set_tenant_context, system_context

    if not token or len(token) > 128:
        raise EntityNotFoundError("AutoPay request", "token")
    with system_context():
        row = db.scalars(select(GatewaySubscription).where(GatewaySubscription.public_token_hash == _hash(token))).first()
    if row is None:
        raise EntityNotFoundError("AutoPay request", "token")
    set_tenant_context(row.organization_id)
    return row


def public_view(db: Session, row: GatewaySubscription) -> Dict[str, Any]:
    """What the authorisation page needs: never a secret, never the customer's other data."""
    subscription = db.get(Subscription, row.subscription_id)
    customer = db.get(Customer, row.customer_id)
    organization = db.get(Organization, row.organization_id)
    creds = razorpay_gateway.credentials_for(db, row.organization_id)
    can_authorize = row.status == AutopayStatus.CREATED and creds.key_id == row.gateway_key_id and razorpay_gateway.is_configured(creds)
    return {
        "status": row.status,
        "can_authorize": can_authorize,
        "organization_name": organization.legal_name or organization.name if organization else "",
        "plan_name": subscription.plan.name if subscription and subscription.plan else "",
        "subscription_number": subscription.subscription_number if subscription else "",
        "amount": str(q2(row.amount)),
        "currency": row.currency,
        "period": row.period,
        "interval": row.interval,
        "total_count": row.total_count,
        "start_at": row.start_at.isoformat() if row.start_at else None,
        "authorized_at": row.authorized_at.isoformat() if row.authorized_at else None,
        "gateway_subscription_id": row.gateway_subscription_id if can_authorize else None,
        "key_id": razorpay_gateway.public_key_id(creds) if can_authorize else None,
        "prefill": {
            "name": customer.display_name if customer else None,
            "email": customer.email if customer else None,
            "contact": customer.phone if customer else None,
        },
    }


def confirm_authorization(db: Session, row: GatewaySubscription, *, payment_id: str, subscription_id: str, signature: str) -> GatewaySubscription:
    """Checkout returned: verify the signature against the subscription id WE stored, then re-read the
    subscription from Razorpay. Only Razorpay's own state can mark it authorised. Commits."""
    if subscription_id != row.gateway_subscription_id:
        raise ValidationAppError("This authorisation belongs to a different subscription.")
    creds = razorpay_gateway.credentials_for(db, row.organization_id)
    if creds.key_id != row.gateway_key_id:
        raise GatewayNotConfiguredError("The organization's Razorpay account changed; ask for a new AutoPay link.")
    if not razorpay_gateway.verify_subscription_signature(payment_id, row.gateway_subscription_id, signature, creds=creds):
        raise ValidationAppError("The authorisation could not be verified.")
    db.execute(select(GatewaySubscription.id).where(GatewaySubscription.id == row.id).with_for_update())
    db.refresh(row)
    remote = razorpay_gateway.fetch_subscription(row.gateway_subscription_id, creds=creds)
    was_authorized = row.authorized_at is not None
    _apply_entity(row, remote)
    row.updated_at = utcnow()
    audit.record(db, actor_label=audit.CUSTOMER_ACTOR, action="AUTOPAY_AUTHORIZATION_RETURNED",
                 entity_type="subscription", entity_id=row.subscription_id, organization_id=row.organization_id,
                 after={"gateway_subscription_id": row.gateway_subscription_id, "gateway_status": remote.get("status"),
                        "payment_id": payment_id})
    if row.authorized_at is not None and not was_authorized:
        _notify(db, row, "authorized")
    db.commit()
    return row


# --- webhooks ---------------------------------------------------------------------------------------------------------


def find_by_gateway_id(db: Session, gateway_subscription_id: str) -> Optional[GatewaySubscription]:
    from backend.app.core.tenant_context import system_context

    with system_context():
        return db.scalars(
            select(GatewaySubscription).where(GatewaySubscription.gateway_subscription_id == gateway_subscription_id)
        ).first()


def _open_invoice(db: Session, subscription: Subscription) -> Optional[Invoice]:
    return db.scalars(
        select(Invoice)
        .where(
            Invoice.organization_id == subscription.organization_id,
            Invoice.subscription_id == subscription.id,
            Invoice.status.in_(OPEN_INVOICE_STATUSES),
        )
        .order_by(Invoice.due_date.asc(), Invoice.created_at.asc())
    ).first()


def _record_charge(db: Session, row: GatewaySubscription, payment_entity: Dict[str, Any], event_id: str) -> Optional[Payment]:
    """One Razorpay charge -> one local payment, allocated to the subscription's oldest open invoice.
    Idempotent on the gateway payment id (redelivered or out-of-order events record nothing new)."""
    from backend.app.services import subscription_service

    gateway_payment_id = payment_entity.get("id")
    if not gateway_payment_id:
        raise ValueError("subscription.charged without a payment entity")
    if db.scalars(select(Payment.id).where(Payment.gateway_payment_id == gateway_payment_id)).first():
        return None
    currency = str(payment_entity.get("currency") or "INR").upper()
    if currency != (row.currency or "INR").upper():
        raise ValueError(f"AutoPay charge currency {currency} does not match the mandate's {row.currency}")
    amount = payment_service.from_paise(payment_entity.get("amount"))
    subscription = db.get(Subscription, row.subscription_id)
    invoice = _open_invoice(db, subscription)
    organization = db.get(Organization, row.organization_id)
    if invoice is None and subscription.next_billing_date and subscription.next_billing_date <= timezones.org_today(organization):
        # Razorpay charged before the daily renewal run issued this period's invoice: issue it now.
        subscription_service.renew_subscription(db, subscription, actor_label=audit.WEBHOOK_ACTOR, only_if_due=True)
        invoice = _open_invoice(db, subscription)
    method = PaymentMethod.UPI if str(payment_entity.get("method") or "").lower() == "upi" else PaymentMethod.RAZORPAY
    payload = {"source": "webhook", "event_id": event_id, "autopay": row.gateway_subscription_id,
               "entity": {k: payment_entity.get(k) for k in ("id", "order_id", "invoice_id", "method", "amount", "currency", "status", "created_at")}}
    if invoice is not None:
        return payment_service.record_gateway_charge(
            db, invoice=invoice, amount=amount, gateway=PaymentGateway.RAZORPAY, gateway_payment_id=gateway_payment_id,
            gateway_order_id=payment_entity.get("order_id"), method=method, payload=payload,
            notes=f"UPI AutoPay / e-mandate charge ({row.gateway_subscription_id})", actor_label=audit.WEBHOOK_ACTOR,
        )
    # Money arrived but there is nothing open to settle: keep it as an unallocated payment for staff.
    logger.warning("AutoPay charge %s for %s has no open invoice; recorded unallocated", gateway_payment_id, row.subscription_id)
    payment = payment_service.create_pending_gateway_payment(
        db, organization_id=row.organization_id, customer_id=row.customer_id, amount=amount, currency=currency,
        gateway_order_id=payment_entity.get("order_id"), method=method, gateway=PaymentGateway.RAZORPAY,
        notes=f"UPI AutoPay / e-mandate charge ({row.gateway_subscription_id}); no open invoice to allocate",
        gateway_payload={"notes": {"organization_id": row.organization_id, "subscription_id": row.subscription_id}},
    )
    return payment_service.capture_gateway_payment(
        db, payment, None, gateway_payment_id=gateway_payment_id, payload=payload,
        signature_verified=True, actor_label=audit.WEBHOOK_ACTOR, lock=False,
    )


def handle_subscription_event(db: Session, event, payload: Dict[str, Any], *, verified_org_id: Optional[str]) -> None:
    """Apply one verified `subscription.*` webhook. Raises LookupError (retried) when the mandate
    is not visible yet, ValueError when the event contradicts what we stored. No commit."""
    from backend.app.core.tenant_context import set_tenant_context

    body = payload.get("payload") or {}
    entity = (body.get("subscription") or {}).get("entity") or {}
    gateway_subscription_id = entity.get("id")
    if not gateway_subscription_id:
        raise ValueError("subscription event without a subscription entity")
    row = find_by_gateway_id(db, gateway_subscription_id)
    if row is None:
        raise LookupError(f"no AutoPay mandate {gateway_subscription_id}")
    if verified_org_id and row.organization_id != verified_org_id:
        raise ValueError("event signed by a different organization than the mandate's")
    notes = entity.get("notes") if isinstance(entity.get("notes"), dict) else {}
    if notes.get("organization_id") and notes["organization_id"] != row.organization_id:
        raise ValueError("subscription notes name a different organization than the mandate's")
    event.organization_id = row.organization_id
    set_tenant_context(row.organization_id)
    db.execute(select(GatewaySubscription.id).where(GatewaySubscription.id == row.id).with_for_update())
    db.refresh(row)

    event_type = str(payload.get("event") or "")
    event_at = _ts(payload.get("created_at")) or utcnow()
    was_authorized = row.authorized_at is not None
    previous_status = row.status
    newest = row.last_event_at is None or event_at >= _aware(row.last_event_at)
    if newest:
        _apply_entity(row, entity)
        row.last_event_at = event_at
    elif row.authorized_at is None and str(entity.get("status") or "") in (AutopayStatus.AUTHENTICATED, AutopayStatus.ACTIVE):
        row.authorized_at = event_at  # a late "authenticated" still proves the mandate was authorised

    payment_entity = (body.get("payment") or {}).get("entity") or {}
    if event_type == "subscription.charged":
        payment = _record_charge(db, row, payment_entity, event.event_id)
        if payment is not None:
            row.failure_notified_cycle = None
            row.last_error = None
            _notify(db, row, "charged", amount=payment.amount, payment_number=payment.payment_number)
    elif event_type in ("subscription.pending", "subscription.halted"):
        reason = payment_entity.get("error_description") or payment_entity.get("error_reason")
        row.last_error = str(reason)[:500] if reason else row.last_error
        cycle = f"{'halted' if event_type.endswith('halted') else 'pending'}:{entity.get('charge_at') or entity.get('current_start') or ''}"
        if row.failure_notified_cycle != cycle:
            row.failure_notified_cycle = cycle
            _notify(db, row, "halted" if event_type.endswith("halted") else "failed", reason=reason)
    if row.authorized_at is not None and not was_authorized:
        _notify(db, row, "authorized")
    row.updated_at = utcnow()
    db.flush()
    subscription = db.get(Subscription, row.subscription_id)
    if subscription is not None and subscription.status in _ENDED_LOCAL and row.status in AutopayStatus.LIVE:
        stop_quietly(db, subscription, reason=f"local subscription is {subscription.status.value}")
    if row.status != previous_status:
        audit.record(db, actor_label=audit.WEBHOOK_ACTOR, action="AUTOPAY_STATUS_CHANGED", entity_type="subscription",
                     entity_id=row.subscription_id, organization_id=row.organization_id,
                     before={"status": previous_status},
                     after={"status": row.status, "event": event_type, "event_id": event.event_id,
                            "gateway_subscription_id": row.gateway_subscription_id})


# --- customer notifications -------------------------------------------------------------------------------------------


def _notify(db: Session, row: GatewaySubscription, kind: str, **info: Any) -> None:
    """One email per state change; callers guard against repeats (authorized_at, payment id, cycle key)."""
    from backend.app.services.notification_service import dispatch_notification

    customer = db.get(Customer, row.customer_id)
    if customer is None or not customer.email:
        return
    organization = db.get(Organization, row.organization_id)
    subscription = db.get(Subscription, row.subscription_id)
    org_name = (organization.legal_name or organization.name) if organization else "Rooman Billing"
    ref = subscription.subscription_number if subscription else row.gateway_subscription_id
    amount = f"{row.currency} {q2(info.get('amount') or row.amount):,.2f}"
    messages = {
        "authorized": (f"AutoPay set up for {ref}",
                       f"Hello {customer.display_name},\n\nYour AutoPay mandate for subscription {ref} with {org_name} is active. "
                       f"{amount} will be collected automatically every billing cycle. You will be notified before and after each charge.\n"),
        "charged": (f"Payment received for {ref}",
                    f"Hello {customer.display_name},\n\nWe received {amount} for subscription {ref} through AutoPay"
                    f"{' (payment ' + info['payment_number'] + ')' if info.get('payment_number') else ''}. Thank you.\n"),
        "failed": (f"AutoPay payment failed for {ref}",
                   f"Hello {customer.display_name},\n\nThe automatic payment of {amount} for subscription {ref} did not go through"
                   f"{' (' + str(info['reason']) + ')' if info.get('reason') else ''}. It will be retried automatically over the next "
                   "few days; please make sure your UPI account or bank account has sufficient balance.\n"),
        "halted": (f"Action needed: AutoPay stopped for {ref}",
                   f"Hello {customer.display_name},\n\nWe could not collect {amount} for subscription {ref} after several attempts, "
                   "so automatic payments are on hold. "
                   + (f"Please update your payment method here: {row.short_url}\n" if row.short_url else
                      f"Please contact {org_name} to set up payment again.\n")),
    }
    subject, body = messages[kind]
    try:
        dispatch_notification(db, organization_id=row.organization_id, channel=NotificationChannel.EMAIL,
                              recipient=customer.email, subject=subject, body=body)
    except Exception as exc:  # a mail problem must never undo a recorded payment or state change
        logger.warning("AutoPay %s notification for %s failed: %s", kind, row.subscription_id, exc)


__all__ = [
    "ineligibility_reason",
    "setup_autopay",
    "authorization_link",
    "cancel_autopay",
    "stop_for_subscription",
    "stop_quietly",
    "get_mandate",
    "serialize_mandate",
    "get_by_token",
    "public_view",
    "confirm_authorization",
    "find_by_gateway_id",
    "handle_subscription_event",
    "LINK_VALIDITY",
]
