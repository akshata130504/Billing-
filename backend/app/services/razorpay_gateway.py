"""Thin wrapper around the Razorpay SDK.

Everything the rest of the application needs from the gateway goes through
these module-level functions so tests can monkeypatch them
(`monkeypatch.setattr(razorpay_gateway, "create_order", fake)`). Signature
checks are implemented here with hmac so they do not depend on SDK internals.

Multi-tenant credentials
------------------------
Every function accepts an optional `creds` (`RazorpayCredentials`). Callers that
know the organization resolve them with `credentials_for(db, organization_id)`,
which honours the organization's own connected Razorpay account (Settings ->
Integrations) and falls back to the deployment-wide RAZORPAY_* keys
(`default_tenant_credentials`). When `creds` is omitted those default tenant keys
are used, which keeps single-tenant deployments and older call sites working.

Rooman's own account
--------------------
Rooman Billing's own merchant account (PLATFORM_RAZORPAY_*, used when an
organization buys a Rooman plan) is returned ONLY by `rooman_account_credentials()`
and must be passed explicitly. No tenant path resolves it: neither
`credentials_for` nor the `creds=None` default ever reads PLATFORM_RAZORPAY_*,
and settings refuse a configuration where it equals the RAZORPAY_* keys.
"""
import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Dict, Optional

from backend.app.core.config import settings
from backend.app.core.exceptions import GatewayError, GatewayNotConfiguredError
from backend.app.core.logging import logger

_clients: Dict[tuple, Any] = {}


@dataclass(frozen=True)
class RazorpayCredentials:
    key_id: Optional[str]
    key_secret: Optional[str]
    webhook_secret: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.key_id and self.key_secret)


def default_tenant_credentials() -> RazorpayCredentials:
    """The deployment-wide RAZORPAY_* keys tenant payments fall back to. Never Rooman's own account."""
    return RazorpayCredentials(
        key_id=settings.RAZORPAY_KEY_ID or None,
        key_secret=settings.RAZORPAY_KEY_SECRET or None,
        webhook_secret=settings.RAZORPAY_WEBHOOK_SECRET or None,
    )


def rooman_account_credentials() -> RazorpayCredentials:
    """Rooman Billing's own merchant account (PLATFORM_RAZORPAY_*), for platform plan payments only.

    Not configured: both fields are None (`configured` is False). There is no webhook secret for
    this account yet.
    """
    return RazorpayCredentials(
        key_id=settings.PLATFORM_RAZORPAY_KEY_ID.strip() or None,
        key_secret=settings.PLATFORM_RAZORPAY_KEY_SECRET.strip() or None,
    )


def credentials_for(db, organization_id: Optional[str]) -> RazorpayCredentials:
    """Tenant keys when the organization connected its own account, else the default tenant keys
    (RAZORPAY_*). Never Rooman's own account (`rooman_account_credentials`)."""
    if db is not None and organization_id:
        try:
            from backend.app.services.integrations_service import get_active_razorpay_credentials

            key_id, key_secret, webhook_secret = get_active_razorpay_credentials(db, organization_id)
            if key_id and key_secret:
                return RazorpayCredentials(key_id, key_secret, webhook_secret or None)
        except Exception as exc:  # a broken integration row must not take payments down
            logger.warning("Could not resolve Razorpay credentials for org %s: %s", organization_id, exc)
    return default_tenant_credentials()


def _resolve(creds: Optional[RazorpayCredentials]) -> RazorpayCredentials:
    return creds if creds is not None else default_tenant_credentials()


def is_configured(creds: Optional[RazorpayCredentials] = None) -> bool:
    if creds is not None:
        return creds.configured
    return settings.razorpay_enabled


def public_key_id(creds: Optional[RazorpayCredentials] = None) -> Optional[str]:
    return _resolve(creds).key_id or None


def _get_client(creds: Optional[RazorpayCredentials] = None):
    """Build (once per key pair) and return the SDK client. Raises GatewayNotConfiguredError when keys are missing."""
    resolved = _resolve(creds)
    if not is_configured(creds):
        raise GatewayNotConfiguredError("razorpay")
    cache_key = (resolved.key_id, hashlib.sha256((resolved.key_secret or "").encode("utf-8")).hexdigest())
    client = _clients.get(cache_key)
    if client is None:
        import razorpay  # imported lazily so the app works without the SDK during tests

        client = razorpay.Client(auth=(resolved.key_id, resolved.key_secret))
        client.set_app_details({"title": settings.PROJECT_NAME, "version": "1.0"})
        _clients[cache_key] = client
    return client


def reset_client() -> None:
    """Drop cached clients (used when settings change at runtime, e.g. in tests)."""
    _clients.clear()


def _hmac_hex(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def create_order(
    amount_paise: int,
    currency: str,
    receipt: str,
    notes: Optional[Dict[str, Any]] = None,
    *,
    creds: Optional[RazorpayCredentials] = None,
    customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a Razorpay order. `amount_paise` is an integer in the smallest currency unit.

    `customer_id` (a Razorpay `cust_...` id) lets Checkout offer "save this card",
    which is what yields a reusable token for recurring charges.
    """
    client = _get_client(creds)
    payload: Dict[str, Any] = {
        "amount": int(amount_paise),
        "currency": currency,
        "receipt": receipt[:40],
        "notes": {k: str(v) for k, v in (notes or {}).items()},
        "payment_capture": 1,
    }
    if customer_id:
        payload["customer_id"] = customer_id
    try:
        order = client.order.create(data=payload)
    except Exception as exc:  # the SDK raises several BadRequestError/ServerError subclasses
        logger.warning("Razorpay order creation failed: %s", exc)
        raise GatewayError(f"Razorpay could not create the order: {exc}") from exc
    if not isinstance(order, dict) or not order.get("id"):
        raise GatewayError("Razorpay returned an unexpected order response.")
    return order


def verify_payment_signature(
    order_id: str,
    payment_id: str,
    signature: str,
    *,
    creds: Optional[RazorpayCredentials] = None,
) -> bool:
    """HMAC-SHA256(order_id|payment_id, key_secret) compared in constant time."""
    secret = _resolve(creds).key_secret
    if not secret or not signature or not order_id or not payment_id:
        return False
    expected = _hmac_hex(secret, f"{order_id}|{payment_id}")
    return hmac.compare_digest(expected.encode("utf-8"), signature.strip().lower().encode("utf-8"))


def verify_webhook_signature(raw_body: bytes, signature: Optional[str], *, secret: Optional[str] = None) -> bool:
    """HMAC-SHA256(raw body, webhook secret) compared in constant time.

    `secret` defaults to the platform webhook secret.
    """
    secret = secret if secret is not None else settings.RAZORPAY_WEBHOOK_SECRET
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode("utf-8"), signature.strip().lower().encode("utf-8"))


def refund_payment(
    gateway_payment_id: str,
    amount_paise: int,
    notes: Optional[Dict[str, Any]] = None,
    *,
    creds: Optional[RazorpayCredentials] = None,
) -> Dict[str, Any]:
    """Refund (part of) a captured payment. Returns the gateway refund entity."""
    client = _get_client(creds)
    payload: Dict[str, Any] = {"amount": int(amount_paise)}
    if notes:
        payload["notes"] = {k: str(v) for k, v in notes.items()}
    try:
        refund = client.payment.refund(gateway_payment_id, payload)
    except Exception as exc:
        logger.warning("Razorpay refund failed for %s: %s", gateway_payment_id, exc)
        raise GatewayError(f"Razorpay could not process the refund: {exc}") from exc
    if not isinstance(refund, dict) or not refund.get("id"):
        raise GatewayError("Razorpay returned an unexpected refund response.")
    return refund


def fetch_payment(gateway_payment_id: str, *, creds: Optional[RazorpayCredentials] = None) -> Dict[str, Any]:
    client = _get_client(creds)
    try:
        payment = client.payment.fetch(gateway_payment_id)
    except Exception as exc:
        raise GatewayError(f"Razorpay could not fetch payment {gateway_payment_id}: {exc}") from exc
    if not isinstance(payment, dict) or not payment.get("id"):
        raise GatewayError("Razorpay returned an unexpected payment response.")
    return payment


def fetch_card(gateway_payment_id: str, *, creds: Optional[RazorpayCredentials] = None) -> Dict[str, Any]:
    """Card entity (network, last4, expiry) used for a payment. Empty dict when unavailable."""
    client = _get_client(creds)
    try:
        card = client.payment.fetchCardDetails(gateway_payment_id)
    except Exception as exc:
        logger.info("Razorpay card details unavailable for %s: %s", gateway_payment_id, exc)
        return {}
    return card if isinstance(card, dict) else {}


def create_customer(
    name: str,
    email: Optional[str] = None,
    contact: Optional[str] = None,
    notes: Optional[Dict[str, Any]] = None,
    *,
    creds: Optional[RazorpayCredentials] = None,
) -> Dict[str, Any]:
    """Create (or, with fail_existing=0, return the existing) Razorpay customer.

    Orders created with this `cust_...` id let Checkout save the card as a token
    that `create_recurring_payment` can later charge.
    """
    client = _get_client(creds)
    payload: Dict[str, Any] = {"name": (name or "Customer")[:50], "fail_existing": "0"}
    if email:
        payload["email"] = email
    if contact:
        payload["contact"] = contact
    if notes:
        payload["notes"] = {k: str(v) for k, v in notes.items()}
    try:
        customer = client.customer.create(data=payload)
    except Exception as exc:
        raise GatewayError(f"Razorpay could not create the customer: {exc}") from exc
    if not isinstance(customer, dict) or not customer.get("id"):
        raise GatewayError("Razorpay returned an unexpected customer response.")
    return customer


def create_recurring_payment(payload: Dict[str, Any], *, creds: Optional[RazorpayCredentials] = None) -> Dict[str, Any]:
    """POST /payments/create/recurring - charge a saved token against an order."""
    client = _get_client(creds)
    try:
        res = client.payment.createRecurring(payload)
    except Exception as exc:
        logger.warning("Razorpay recurring charge failed: %s", exc)
        raise GatewayError(f"Razorpay could not create the recurring payment: {exc}") from exc
    if not isinstance(res, dict):
        raise GatewayError("Razorpay returned an unexpected recurring payment response.")
    return res


# Razorpay payment states that mean the money is (or will automatically be) ours:
# orders are created with payment_capture=1, so "authorized" is captured shortly.
SETTLED_GATEWAY_STATES = ("captured", "authorized")


def verify_fetched_payment(
    fetched: Dict[str, Any],
    *,
    expected_order_id: str,
    expected_amount_paise: int,
    expected_currency: Optional[str] = None,
) -> Optional[str]:
    """Return None when the fetched payment entity matches what we ordered, else a reason string."""
    status = str(fetched.get("status") or "").lower()
    if status not in SETTLED_GATEWAY_STATES:
        return f"payment status is '{status or 'unknown'}', not captured"
    if (fetched.get("order_id") or "") != expected_order_id:
        return "payment does not belong to this order"
    try:
        amount = int(fetched.get("amount"))
    except (TypeError, ValueError):
        return "payment amount missing"
    if amount != int(expected_amount_paise):
        return f"amount mismatch: expected {int(expected_amount_paise)} paise, got {amount}"
    currency = fetched.get("currency")
    if expected_currency and currency and str(currency).upper() != str(expected_currency).upper():
        return "currency mismatch"
    return None


__all__ = [
    "RazorpayCredentials",
    "credentials_for",
    "default_tenant_credentials",
    "rooman_account_credentials",
    "is_configured",
    "public_key_id",
    "create_order",
    "verify_payment_signature",
    "verify_webhook_signature",
    "refund_payment",
    "fetch_payment",
    "fetch_card",
    "create_recurring_payment",
    "create_customer",
    "verify_fetched_payment",
    "SETTLED_GATEWAY_STATES",
    "reset_client",
]
