"""An organization's Owner starts buying a Rooman plan: Razorpay Plan + Subscription with Rooman's account.

What this does:
1. Takes a plan CODE and resolves everything else (price, interval, seats, tax treatment) from the
   catalog; only a published plan can be bought (platform_subscription_service.sellable_plan), or a
   sandbox test plan in a local environment with Test Mode keys and the sandbox flag on.
2. Finds or creates the Razorpay Plan for exactly those billing terms in the current mode
   (platform_provider_plans, keyed by a fingerprint of the terms).
3. Creates a Razorpay Subscription for the organization and records a platform_checkout_attempts row.
4. Returns what Standard Checkout needs: the PUBLIC key id and the subscription id.

What it never does: mark anything paid, grant modules or seats, or lift the expired-trial read-only
mode. The browser's Checkout callback is not proof of payment; a later stage verifies the payment
with Razorpay and only then calls platform_subscription_service.activate.

Creating plans and subscriptions at Razorpay is not idempotent, so every create follows the same
protocol: under a row lock, write a durable claim (attempts / last_attempt_at, status pending) and
commit BEFORE calling Razorpay. While a claim is fresh, other requests answer "retry shortly" instead
of creating a second object. A claim that went stale (crash) or ended 'unknown' (timeout, 5xx) is
reconciled first: the object is looked up at Razorpay by the reference written into its notes, and
created again only when it is not found.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.config import settings
from backend.app.core.exceptions import AppException, ConflictError, GatewayError
from backend.app.core.logging import logger
from backend.app.core.plan_catalog import CatalogPlan, catalog
from backend.app.models import Organization, PlatformCheckoutAttempt, PlatformProviderPlan
from backend.app.models.platform_billing import OPEN_CHECKOUT_STATUSES
from backend.app.services import org_access, platform_razorpay as provider, platform_subscription_service

PROVIDER = "razorpay"
RECONCILE_LOOKBACK = timedelta(minutes=10)  # Razorpay `from` filter: a little before our own row


class CheckoutUnavailableError(AppException):
    """503: Razorpay could not be reached or the outcome is unknown. Nothing was granted; retry."""

    def __init__(self, message: str = "Payments are temporarily unavailable. Nothing was charged; please try again."):
        super().__init__(message, code="CHECKOUT_UNAVAILABLE", status_code=503)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _unix(value: datetime) -> int:
    return int(_aware(value).timestamp())


def claim_window() -> timedelta:
    """How long an in-flight create blocks other requests: longer than one provider call can take."""
    return timedelta(seconds=2 * int(settings.PLATFORM_RAZORPAY_TIMEOUT_SECONDS) + 5)


def billing_fingerprint(plan: CatalogPlan) -> str:
    """Everything that defines the charge. Any change -> a different provider plan."""
    terms = {"code": plan.code, "amount_minor": plan.price.amount_minor, "currency": plan.price.currency,
             "interval": plan.price.interval, "interval_count": plan.price.interval_count,
             "tax_treatment": plan.tax_treatment}
    return hashlib.sha256(json.dumps(terms, sort_keys=True).encode("utf-8")).hexdigest()


def _plan_matches(found: Dict[str, Any], row: PlatformProviderPlan) -> bool:
    item = found.get("item") if isinstance(found.get("item"), dict) else {}
    return (found.get("period") == provider.PERIODS.get(row.billing_interval)
            and int(found.get("interval") or 0) == row.billing_interval_count
            and int(item.get("amount") or -1) == row.amount_minor
            and str(item.get("currency") or "").upper() == row.currency)


def _in_flight(last_attempt_at: Optional[datetime], status: str, now: datetime) -> bool:
    return status == "pending" and last_attempt_at is not None and now - _aware(last_attempt_at) < claim_window()


# --- provider plan ---------------------------------------------------------------------------------------


def _provider_plan_row(db: Session, mode: str, fingerprint: str, lock: bool = False) -> Optional[PlatformProviderPlan]:
    stmt = select(PlatformProviderPlan).where(PlatformProviderPlan.provider == PROVIDER, PlatformProviderPlan.mode == mode,
                                              PlatformProviderPlan.fingerprint == fingerprint)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalars(stmt).first()


def _require_sandbox_test_mode(plan: CatalogPlan, mode: str) -> None:
    """A sandbox test plan exists only in Razorpay Test Mode: never a Live Mode provider plan or subscription.
    (sellable_plan already refuses it outside the sandbox; this keeps the provider records separate even if a
    caller got the mode from somewhere else.)"""
    if plan.is_sandbox and mode != "test":
        raise ConflictError("This plan is not available.", {"code": "PLAN_NOT_AVAILABLE", "plan_code": plan.code})


def _sandbox_notes(plan: CatalogPlan) -> Dict[str, str]:
    # Visible on the Razorpay dashboard as well: a sandbox object can never be mistaken for a commercial one.
    return {"rooman_sandbox": "true"} if plan.is_sandbox else {}


def resolve_provider_plan(db: Session, plan: CatalogPlan, mode: str, now: Optional[datetime] = None) -> str:
    """The Razorpay plan id for `plan`'s billing terms in `mode`, created once. Commits its own steps.
    Rows are keyed by mode and by a fingerprint that includes the plan code, so a sandbox plan and a
    commercial plan (or test and live) never share a provider plan."""
    _require_sandbox_test_mode(plan, mode)
    now = _aware(now) or _utcnow()
    fingerprint = billing_fingerprint(plan)
    row = _provider_plan_row(db, mode, fingerprint)
    if row is None:
        row = PlatformProviderPlan(
            provider=PROVIDER, mode=mode, plan_code=plan.code, fingerprint=fingerprint,
            amount_minor=plan.price.amount_minor, currency=plan.price.currency, billing_interval=plan.price.interval,
            billing_interval_count=plan.price.interval_count, status="pending", reconcile_ref=uuid.uuid4().hex, attempts=0,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:  # another request inserted it first
            db.rollback()
    row = _provider_plan_row(db, mode, fingerprint, lock=True)
    if row.status == "created":
        plan_id = row.provider_plan_id
        db.commit()
        return plan_id
    if _in_flight(row.last_attempt_at, row.status, now):
        db.rollback()
        raise CheckoutUnavailableError("This plan is being prepared for checkout. Please try again in a moment.")

    if row.attempts > 0:  # an earlier create may have succeeded at Razorpay: look before creating again
        try:
            found = provider.find_plan(row.reconcile_ref, _unix(_aware(row.created_at) - RECONCILE_LOOKBACK))
        except provider.ProviderUnavailable:
            db.rollback()
            raise CheckoutUnavailableError()
        except provider.ProviderRejected as exc:
            db.rollback()
            raise GatewayError("Razorpay refused the plan lookup.", {"reason": str(exc)[:200]})
        if found is not None:
            if not _plan_matches(found, row):
                db.rollback()
                logger.error("Provider plan %s does not match its catalog terms (ref %s)", found.get("id"), row.reconcile_ref)
                raise GatewayError("The payment plan at Razorpay does not match this plan; contact support.")
            row.status, row.provider_plan_id, row.last_error = "created", found["id"], None
            db.commit()
            return row.provider_plan_id

    # Durable claim, then the (non-idempotent) create.
    row.status, row.attempts, row.last_attempt_at = "pending", row.attempts + 1, now
    reconcile_ref, row_id = row.reconcile_ref, row.id
    db.commit()
    try:
        created = provider.create_plan(
            name=plan.name, description=plan.description, amount_minor=plan.price.amount_minor,
            currency=plan.price.currency, interval=plan.price.interval, interval_count=plan.price.interval_count,
            notes={"rooman_plan_ref": reconcile_ref, "catalog_plan": plan.code, "terms": fingerprint, **_sandbox_notes(plan)},
        )
    except provider.ProviderRejected as exc:
        _finish_plan(db, row_id, status="failed", error=str(exc))
        raise GatewayError("Razorpay refused to create the payment plan.", {"reason": str(exc)[:200]})
    except provider.ProviderUnavailable as exc:
        _finish_plan(db, row_id, status="unknown", error=str(exc))
        raise CheckoutUnavailableError()
    _finish_plan(db, row_id, status="created", plan_id=created["id"])
    return created["id"]


def _finish_plan(db: Session, row_id: str, *, status: str, plan_id: Optional[str] = None, error: Optional[str] = None) -> None:
    row = db.scalars(select(PlatformProviderPlan).where(PlatformProviderPlan.id == row_id).with_for_update()
                     .execution_options(populate_existing=True)).one()
    row.status, row.last_error = status, (error or None) and error[:300]
    if plan_id:
        row.provider_plan_id = plan_id
    db.commit()


# --- checkout ----------------------------------------------------------------------------------------------


def _checkout_out(attempt: PlatformCheckoutAttempt, plan: CatalogPlan, ctx: CurrentContext, reused: bool) -> Dict[str, Any]:
    return {
        "checkout_attempt_id": attempt.id,
        "razorpay_key_id": provider.public_key_id(),
        "razorpay_subscription_id": attempt.provider_subscription_id,
        "expires_at": _aware(attempt.expires_at),
        "reused": reused,
        "plan": {
            "code": plan.code, "name": plan.name, "description": plan.description,
            "amount_minor": attempt.amount_minor, "currency": attempt.currency, "interval": attempt.billing_interval,
            "interval_count": attempt.billing_interval_count, "tax_treatment": attempt.tax_treatment,
            "seat_limit": attempt.seat_limit, "sandbox": plan.is_sandbox,
        },
        "prefill": {"name": ctx.user.full_name or "", "email": ctx.user.email},
        "organization_name": ctx.organization.name,
    }


def _open_attempt(db: Session, organization_id: str) -> Optional[PlatformCheckoutAttempt]:
    return db.scalars(select(PlatformCheckoutAttempt).where(
        PlatformCheckoutAttempt.organization_id == organization_id,
        PlatformCheckoutAttempt.status.in_(OPEN_CHECKOUT_STATUSES),
    ).with_for_update().execution_options(populate_existing=True)).first()


def _settle_open_attempt(db: Session, attempt: PlatformCheckoutAttempt, now: datetime) -> PlatformCheckoutAttempt:
    """Bring an open attempt up to date (caller holds the lock and commits): expire it, or reconcile an
    attempt whose create call never answered. An 'authorized' attempt (Razorpay holds the customer's
    authorization, the first charge is not confirmed) never expires here; the caller re-checks it."""
    if attempt.status == "authorized":
        return attempt
    if attempt.status == "created":
        if now >= _aware(attempt.expires_at):
            attempt.status = "expired"
        return attempt
    if _in_flight(attempt.updated_at, attempt.status, now):
        raise CheckoutUnavailableError("A checkout is already being started. Please try again in a moment.")
    try:  # pending (stale claim) or unknown: did Razorpay create it?
        found = provider.find_subscription(attempt.provider_plan_id or "", attempt.id,
                                           _unix(_aware(attempt.created_at) - RECONCILE_LOOKBACK))
    except provider.ProviderUnavailable:
        raise CheckoutUnavailableError()
    except provider.ProviderRejected as exc:
        raise GatewayError("Razorpay refused the checkout lookup.", {"reason": str(exc)[:200]})
    if found is None:
        attempt.status, attempt.last_error = "failed", "not created at Razorpay"
    else:
        attempt.provider_subscription_id = found["id"]
        attempt.status = "expired" if now >= _aware(attempt.expires_at) else "created"
    return attempt


def _recheck_authorized(db: Session, attempt: PlatformCheckoutAttempt, now: datetime) -> PlatformCheckoutAttempt:
    """An earlier checkout is authorized at Razorpay: ask Razorpay before allowing another purchase. It may
    have been charged since (-> activated, nothing new to buy) or have failed (-> a new checkout is fine)."""
    from backend.app.services import platform_payment_service as payments

    try:
        result = payments.sync_provider_subscription(db, attempt.provider_subscription_id, now=now)
    except payments.RetryLater:
        raise CheckoutUnavailableError()
    if result.outcome == "activated":
        db.commit()
        raise ConflictError("Your payment has been confirmed and your plan is active.", {"code": "SUBSCRIPTION_ALREADY_ACTIVE"})
    if attempt.status == "authorized":
        db.commit()
        raise ConflictError(
            "A payment for this organization is being confirmed by Razorpay. Please wait for it to finish.",
            {"code": "PAYMENT_IN_PROGRESS", "plan_code": attempt.plan_code},
        )
    return attempt


def start_checkout(db: Session, ctx: CurrentContext, plan_code: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Owner-initiated purchase of `plan_code` for ctx's organization (the route enforces Owner)."""
    now = _aware(now) or _utcnow()
    # Published plans; a sandbox test plan only while sandbox_readiness() allows it (flag, local, Test Mode keys).
    plan = platform_subscription_service.sellable_plan(plan_code)
    mode = provider.require_checkout_ready()  # keys, allowed mode and webhook - never trusts the catalog flag
    _require_sandbox_test_mode(plan, mode)
    org_id = ctx.organization_id
    fingerprint = billing_fingerprint(plan)

    org = db.scalars(select(Organization).where(Organization.id == org_id).with_for_update()).first()
    if platform_subscription_service.access_for(db, org_id, now).paid:
        raise ConflictError("Your organization already has a paid plan.", {"code": "SUBSCRIPTION_ALREADY_ACTIVE"})
    used = org_access.seats_used(db, org.id)
    if used > plan.seat_limit:
        raise ConflictError(
            f"The {plan.name} plan allows {plan.seat_limit} user seat(s); your organization has {used} members and invitations.",
            {"code": "SEATS_EXCEED_PLAN", "seat_limit": plan.seat_limit, "seats_used": used},
        )
    attempt = _open_attempt(db, org_id)
    if attempt is not None:
        try:
            attempt = _settle_open_attempt(db, attempt, now)
            if attempt.status == "authorized":
                attempt = _recheck_authorized(db, attempt, now)
        except Exception:
            db.rollback()
            raise
        if attempt.status == "created":
            if attempt.fingerprint == fingerprint and attempt.mode == mode:
                db.commit()
                return _checkout_out(attempt, plan, ctx, reused=True)  # the same checkout, not a second one
            expires = _aware(attempt.expires_at)
            db.commit()
            raise ConflictError(
                "A checkout for another plan is still open. Complete it, or try again after it expires.",
                {"code": "CHECKOUT_IN_PROGRESS", "plan_code": attempt.plan_code, "expires_at": expires.isoformat()},
            )
    db.commit()  # releases the organization lock before any provider call

    provider_plan_id = resolve_provider_plan(db, plan, mode, now)

    attempt = PlatformCheckoutAttempt(
        organization_id=org_id, created_by_user_id=ctx.user.id, plan_code=plan.code, catalog_version=catalog().version,
        fingerprint=fingerprint, amount_minor=plan.price.amount_minor, currency=plan.price.currency,
        billing_interval=plan.price.interval, billing_interval_count=plan.price.interval_count, seat_limit=plan.seat_limit,
        tax_treatment=plan.tax_treatment, provider=PROVIDER, mode=mode, provider_plan_id=provider_plan_id,
        status="pending", expires_at=now + timedelta(minutes=int(settings.PLATFORM_CHECKOUT_EXPIRY_MINUTES)),
    )
    db.add(attempt)
    try:
        db.commit()  # the durable claim: at most one open attempt per organization (unique index)
    except IntegrityError:
        db.rollback()
        raise CheckoutUnavailableError("A checkout is already being started. Please try again in a moment.")
    attempt_id, expire_by = attempt.id, _unix(attempt.expires_at)

    try:
        created = provider.create_subscription(
            plan_id=provider_plan_id, total_count=int(settings.PLATFORM_SUBSCRIPTION_TOTAL_COUNT), expire_by=expire_by,
            notes={"checkout_attempt_id": attempt_id, "organization_id": org_id, "plan_code": plan.code,
                   "catalog_version": str(catalog().version), **_sandbox_notes(plan)},
        )
    except provider.ProviderRejected as exc:
        _finish_attempt(db, attempt_id, status="failed", error=str(exc))
        raise GatewayError("Razorpay refused to start the checkout.", {"reason": str(exc)[:200]})
    except provider.ProviderUnavailable as exc:
        _finish_attempt(db, attempt_id, status="unknown", error=str(exc))
        raise CheckoutUnavailableError()
    attempt = _finish_attempt(db, attempt_id, status="created", subscription_id=created["id"])
    return _checkout_out(attempt, plan, ctx, reused=False)


def _finish_attempt(db: Session, attempt_id: str, *, status: str, subscription_id: Optional[str] = None,
                    error: Optional[str] = None) -> PlatformCheckoutAttempt:
    attempt = db.scalars(select(PlatformCheckoutAttempt).where(PlatformCheckoutAttempt.id == attempt_id)
                         .with_for_update().execution_options(populate_existing=True)).one()
    attempt.status, attempt.last_error = status, (error or None) and error[:300]
    if subscription_id:
        attempt.provider_subscription_id = subscription_id
    db.commit()
    db.refresh(attempt)
    return attempt
