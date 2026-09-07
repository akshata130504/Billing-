"""Thin wrapper around the Razorpay SDK.

Everything the rest of the application needs from the gateway goes through
these module-level functions so tests can monkeypatch them
(`monkeypatch.setattr(razorpay_gateway, "create_order", fake)`). The SDK client
is constructed lazily from settings; signature checks are implemented here with
hmac so they do not depend on SDK internals.
"""
import hashlib
import hmac
from typing import Any, Dict, Optional

from backend.app.core.config import settings
from backend.app.core.exceptions import GatewayError, GatewayNotConfiguredError
from backend.app.core.logging import logger

_client = None


def is_configured() -> bool:
    return settings.razorpay_enabled


def public_key_id() -> Optional[str]:
    return settings.RAZORPAY_KEY_ID or None


def _get_client():
    """Build (once) and return the SDK client. Raises GatewayNotConfiguredError when keys are missing."""
    global _client
    if not is_configured():
        raise GatewayNotConfiguredError("razorpay")
    if _client is None:
        import razorpay  # imported lazily so the app works without the SDK during tests

        _client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        _client.set_app_details({"title": settings.PROJECT_NAME, "version": "1.0"})
    return _client


def reset_client() -> None:
    """Drop the cached client (used when settings change at runtime, e.g. in tests)."""
    global _client
    _client = None


def _hmac_hex(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def create_order(amount_paise: int, currency: str, receipt: str, notes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create a Razorpay order. `amount_paise` is an integer in the smallest currency unit."""
    client = _get_client()
    payload = {
        "amount": int(amount_paise),
        "currency": currency,
        "receipt": receipt[:40],
        "notes": {k: str(v) for k, v in (notes or {}).items()},
        "payment_capture": 1,
    }
    try:
        order = client.order.create(data=payload)
    except Exception as exc:  # the SDK raises several BadRequestError/ServerError subclasses
        logger.warning("Razorpay order creation failed: %s", exc)
        raise GatewayError(f"Razorpay could not create the order: {exc}") from exc
    if not isinstance(order, dict) or not order.get("id"):
        raise GatewayError("Razorpay returned an unexpected order response.")
    return order


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """HMAC-SHA256(order_id|payment_id, key_secret) compared in constant time."""
    if not settings.RAZORPAY_KEY_SECRET or not signature:
        return False
    expected = _hmac_hex(settings.RAZORPAY_KEY_SECRET, f"{order_id}|{payment_id}")
    return hmac.compare_digest(expected.encode("utf-8"), signature.strip().lower().encode("utf-8"))


def verify_webhook_signature(raw_body: bytes, signature: Optional[str]) -> bool:
    """HMAC-SHA256(raw body, webhook secret) compared in constant time."""
    if not settings.RAZORPAY_WEBHOOK_SECRET or not signature:
        return False
    expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode("utf-8"), signature.strip().lower().encode("utf-8"))


def refund_payment(gateway_payment_id: str, amount_paise: int, notes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Refund (part of) a captured payment. Returns the gateway refund entity."""
    client = _get_client()
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


def fetch_payment(gateway_payment_id: str) -> Dict[str, Any]:
    client = _get_client()
    try:
        return client.payment.fetch(gateway_payment_id)
    except Exception as exc:
        raise GatewayError(f"Razorpay could not fetch payment {gateway_payment_id}: {exc}") from exc


__all__ = [
    "is_configured",
    "public_key_id",
    "create_order",
    "verify_payment_signature",
    "verify_webhook_signature",
    "refund_payment",
    "fetch_payment",
    "reset_client",
]
