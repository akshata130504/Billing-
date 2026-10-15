"""Razorpay calls made with ROOMAN's own account (PLATFORM_RAZORPAY_*), for plan checkout only.

Never used for a tenant's payments, and never given tenant credentials: every call here takes its
keys from `razorpay_gateway.rooman_account_credentials()`. Plans and Subscriptions APIs:
https://razorpay.com/docs/api/payments/subscriptions/

Creating plans and subscriptions is not idempotent at Razorpay (no idempotency key), so:
- the SDK's own retry is never enabled and every request has a timeout;
- every failure is classified: `ProviderRejected` (Razorpay answered with a 4xx error - nothing was
  created) or `ProviderUnavailable` (timeout, connection failure, 5xx, unreadable answer - the object
  MAY exist). Callers record the latter as 'unknown' and look the object up by its notes before ever
  creating it again.
Messages never include keys, and Razorpay's error text is truncated before it is stored.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Dict, List, Optional

from backend.app.core.config import settings
from backend.app.core.exceptions import AppException, GatewayNotConfiguredError
from backend.app.services import razorpay_gateway

# Catalog interval -> Razorpay plan `period`.
PERIODS = {"month": "monthly", "year": "yearly"}
MAX_PAGES = 10  # reconciliation lookups read at most 10 x 100 records


class ProviderRejected(Exception):
    """Razorpay refused the request (4xx): nothing was created."""


class ProviderUnavailable(Exception):
    """The outcome is unknown (timeout, connection error, 5xx, unreadable response)."""


class LiveCheckoutDisabledError(AppException):
    def __init__(self):
        super().__init__("Plan checkout is not enabled for live payments yet.", code="LIVE_CHECKOUT_DISABLED",
                         status_code=503)


def credentials() -> razorpay_gateway.RazorpayCredentials:
    creds = razorpay_gateway.rooman_account_credentials()
    if not creds.configured:
        raise GatewayNotConfiguredError("razorpay")
    return creds


def mode() -> str:
    """'test' or 'live', from Rooman's key id (settings guarantee rzp_test_ / rzp_live_)."""
    key_id = credentials().key_id or ""
    return "live" if key_id.startswith("rzp_live_") else "test"


def require_allowed_mode() -> str:
    current = mode()
    if current == "live" and not settings.PLATFORM_CHECKOUT_ALLOW_LIVE:
        raise LiveCheckoutDisabledError()
    return current


class CheckoutNotReadyError(AppException):
    def __init__(self):
        super().__init__("Plan checkout is not available yet.", code="CHECKOUT_NOT_READY", status_code=503)


def checkout_readiness() -> Optional[str]:
    """None when a customer can safely buy a plan right now, else why not (a code, never a secret):
    Rooman's keys configured, the mode allowed, and the platform webhook configured - it activates a
    purchase whose browser never came back and keeps renewals, failures and cancellations in sync."""
    if not razorpay_gateway.rooman_account_credentials().configured:
        return "PAYMENTS_NOT_CONFIGURED"
    if mode() == "live" and not settings.PLATFORM_CHECKOUT_ALLOW_LIVE:
        return "LIVE_CHECKOUT_DISABLED"
    if not webhook_secret():
        return "WEBHOOK_NOT_CONFIGURED"
    return None


def require_checkout_ready() -> str:
    """The current mode when checkout may run; raises the matching 503 otherwise."""
    reason = checkout_readiness()
    if reason == "PAYMENTS_NOT_CONFIGURED":
        raise GatewayNotConfiguredError("razorpay")
    if reason == "LIVE_CHECKOUT_DISABLED":
        raise LiveCheckoutDisabledError()
    if reason is not None:
        raise CheckoutNotReadyError()
    return mode()


# Where sandbox test plans may ever run: local development and automated tests, nothing else.
SANDBOX_ENVIRONMENTS = ("development", "test")


def sandbox_readiness() -> Optional[str]:
    """None when sandbox test plans (plan_catalog status "sandbox") may be listed, bought, activated and
    renewed right now; otherwise why not. Every condition must hold, checked on every call:
    - PLATFORM_SANDBOX_PLANS_ENABLED is explicitly on (off by default);
    - the environment is local (development / test) - production and staging refuse whatever the flag says;
    - Rooman's platform keys are configured and are Test Mode keys (rzp_test_...); Live Mode keys never.
    This only opens the sandbox exception; checkout still needs checkout_readiness() (webhook included)."""
    if not settings.PLATFORM_SANDBOX_PLANS_ENABLED:
        return "SANDBOX_DISABLED"
    environment = (settings.ENVIRONMENT or "").strip().lower()
    if settings.is_production or environment not in SANDBOX_ENVIRONMENTS:
        return "SANDBOX_NOT_ALLOWED_IN_THIS_ENVIRONMENT"
    if not razorpay_gateway.rooman_account_credentials().configured:
        return "PAYMENTS_NOT_CONFIGURED"
    if mode() != "test":
        return "SANDBOX_NEEDS_TEST_KEYS"
    return None


def public_key_id() -> str:
    """The public Key ID Checkout needs. Never the secret."""
    return credentials().key_id or ""


def _client():
    client = razorpay_gateway._get_client(credentials())
    client.retry_enabled = False  # a retried create could make a second plan / subscription
    return client


def _call(fn, *args):
    try:
        import razorpay

        bad_request = razorpay.errors.BadRequestError
    except Exception:  # pragma: no cover - SDK always present in this app
        bad_request = ()
    try:
        result = fn(*args, timeout=int(settings.PLATFORM_RAZORPAY_TIMEOUT_SECONDS))
    except bad_request as exc:  # type: ignore[misc]
        raise ProviderRejected(str(exc)[:200]) from exc
    except Exception as exc:  # noqa: BLE001 - timeouts, connection errors, 5xx, JSON errors: outcome unknown
        raise ProviderUnavailable(type(exc).__name__) from exc
    if not isinstance(result, dict):
        raise ProviderUnavailable("unexpected response")
    return result


def create_plan(*, name: str, description: str, amount_minor: int, currency: str, interval: str,
                interval_count: int, notes: Dict[str, str]) -> Dict[str, Any]:
    body = {
        "period": PERIODS[interval],
        "interval": int(interval_count),
        "item": {"name": name, "amount": int(amount_minor), "currency": currency, "description": description},
        "notes": notes,
    }
    plan = _call(_client().plan.create, body)
    if not str(plan.get("id", "")).startswith("plan_"):
        raise ProviderUnavailable("plan response without an id")
    return plan


def create_subscription(*, plan_id: str, total_count: int, expire_by: int, notes: Dict[str, str]) -> Dict[str, Any]:
    body = {
        "plan_id": plan_id,
        "total_count": int(total_count),
        "quantity": 1,
        "customer_notify": True,
        "expire_by": int(expire_by),
        "notes": notes,
    }
    sub = _call(_client().subscription.create, body)
    if not str(sub.get("id", "")).startswith("sub_"):
        raise ProviderUnavailable("subscription response without an id")
    return sub


def _find(list_fn, params: Dict[str, Any], note_key: str, note_value: str) -> Optional[Dict[str, Any]]:
    for page in range(MAX_PAGES):
        batch = _call(list_fn, {**params, "count": 100, "skip": page * 100})
        items: List[Dict[str, Any]] = batch.get("items") or []
        for item in items:
            notes = item.get("notes") if isinstance(item.get("notes"), dict) else {}
            if notes.get(note_key) == note_value:
                return item
        if len(items) < 100:
            return None
    return None


def find_plan(reconcile_ref: str, created_after: int) -> Optional[Dict[str, Any]]:
    """The plan whose notes carry `reconcile_ref`, among plans created since `created_after` (unix)."""
    return _find(_client().plan.all, {"from": int(created_after)}, "rooman_plan_ref", reconcile_ref)


def find_subscription(plan_id: str, attempt_id: str, created_after: int) -> Optional[Dict[str, Any]]:
    """The subscription created for checkout attempt `attempt_id` (its notes), if any."""
    return _find(_client().subscription.all, {"plan_id": plan_id, "from": int(created_after)},
                 "checkout_attempt_id", attempt_id)


def fetch_subscription(subscription_id: str) -> Dict[str, Any]:
    sub = _call(_client().subscription.fetch, subscription_id)
    if sub.get("id") != subscription_id:
        raise ProviderUnavailable("subscription response does not match the request")
    return sub


def fetch_payment(payment_id: str) -> Dict[str, Any]:
    payment = _call(_client().payment.fetch, payment_id)
    if payment.get("id") != payment_id:
        raise ProviderUnavailable("payment response does not match the request")
    return payment


def cancel_subscription(subscription_id: str, *, at_cycle_end: bool) -> Dict[str, Any]:
    """POST /v1/subscriptions/{id}/cancel with Rooman's keys. Razorpay allows ONE cancel per subscription
    (a second answers 400, `ProviderRejected`), only while it is active / authenticated; there is no API to
    undo a cancellation. `at_cycle_end`: the subscription stays active until its current cycle ends, else
    it is cancelled now. Returns the subscription entity Razorpay answered with; the caller checks it."""
    sub = _call(_client().subscription.cancel, subscription_id, {"cancel_at_cycle_end": 1 if at_cycle_end else 0})
    if sub.get("id") != subscription_id:
        raise ProviderUnavailable("cancel response does not match the request")
    return sub


def find_subscription_payment(subscription_id: str) -> Optional[str]:
    """The payment id of `subscription_id`'s earliest PAID invoice at Razorpay, or None. Read-only.

    Used by reconciliation when neither a Checkout callback nor a webhook ever named the payment. Finding a
    payment here proves nothing: platform_payment_service still fetches it and requires it to be captured
    for exactly the checkout's amount and currency before anything is granted."""
    paid = list_paid_subscription_invoices(subscription_id)
    return paid[0]["payment_id"] if paid else None


def list_paid_subscription_invoices(subscription_id: str) -> List[Dict[str, Any]]:
    """`subscription_id`'s PAID invoices at Razorpay, oldest cycle first: invoice_id, payment_id, paid_at,
    billing_start, billing_end (unix seconds or None). Read-only. An invoice proves nothing on its own: each payment
    is still fetched and verified (captured, exact amount and currency) before it is recorded or applied."""
    paid: List[Dict[str, Any]] = []
    for page in range(MAX_PAGES):
        batch = _call(_client().invoice.all, {"subscription_id": subscription_id, "count": 100, "skip": page * 100})
        items = batch.get("items") or []
        for inv in items:
            if (isinstance(inv, dict) and inv.get("subscription_id") == subscription_id and inv.get("status") == "paid"
                    and str(inv.get("payment_id") or "").startswith("pay_") and str(inv.get("id") or "").startswith("inv_")):
                paid.append({"invoice_id": inv["id"], "payment_id": inv["payment_id"], "paid_at": inv.get("paid_at"),
                             "billing_start": inv.get("billing_start"), "billing_end": inv.get("billing_end")})
        if len(items) < 100:
            break
    paid.sort(key=lambda inv: (int(inv.get("billing_start") or 0), int(inv.get("paid_at") or 0)))
    return paid


def _matches(expected_hex: str, given: Optional[str]) -> bool:
    return bool(given) and hmac.compare_digest(expected_hex.encode("utf-8"), given.strip().lower().encode("utf-8"))


def verify_checkout_signature(payment_id: str, stored_subscription_id: str, signature: Optional[str]) -> bool:
    """Subscription Checkout signature: HMAC-SHA256(payment_id + "|" + subscription_id, API key secret).
    `stored_subscription_id` must be OUR stored id, never the one the browser sent. Constant time."""
    secret = credentials().key_secret or ""
    if not (secret and payment_id and stored_subscription_id and signature):
        return False
    expected = hmac.new(secret.encode("utf-8"), f"{payment_id}|{stored_subscription_id}".encode("utf-8"),
                        hashlib.sha256).hexdigest()
    return _matches(expected, signature)


def webhook_secret() -> str:
    return (settings.PLATFORM_RAZORPAY_WEBHOOK_SECRET or "").strip()


def verify_webhook_signature(raw_body: bytes, signature: Optional[str]) -> bool:
    """HMAC-SHA256 of the exact raw request body with PLATFORM_RAZORPAY_WEBHOOK_SECRET (never the API
    secret, never a tenant secret). Constant time. False when the secret is not configured."""
    secret = webhook_secret()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return _matches(expected, signature)
