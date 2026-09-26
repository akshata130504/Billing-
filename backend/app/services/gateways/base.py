"""Payment Gateway Adapter protocol / interface."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional, Protocol

from backend.app.models.payments import PaymentGateway


@dataclass
class GatewayChargeResult:
    success: bool
    gateway_payment_id: Optional[str] = None
    gateway_order_id: Optional[str] = None
    error_message: Optional[str] = None
    error_category: Optional[str] = None  # e.g., "insufficient_funds", "card_expired", "authentication_failed"
    raw_payload: Optional[Dict[str, Any]] = None
    # True when the gateway accepted the charge but has not confirmed capture yet
    # (e.g. a Razorpay recurring token charge). `success` is True as well - the
    # charge was not declined - but callers must NOT settle the invoice; the
    # payment.captured webhook does that. Defaults to False so older adapters and
    # test doubles keep their meaning.
    pending: bool = False


@dataclass
class GatewayRefundResult:
    success: bool
    gateway_refund_id: Optional[str] = None
    error_message: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None


class PaymentGatewayAdapter(Protocol):
    """Uniform gateway abstraction decoupling business logic from provider SDKs."""

    gateway_type: PaymentGateway

    def charge(
        self,
        amount: Decimal,
        currency: str,
        customer_id: str,
        payment_method_token: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> GatewayChargeResult:
        ...

    def refund(
        self,
        gateway_payment_id: str,
        amount: Decimal,
        reason: Optional[str] = None,
    ) -> GatewayRefundResult:
        ...

    def verify_webhook(
        self,
        raw_body: bytes,
        signature: Optional[str],
    ) -> bool:
        ...

    def verify_payment_signature(
        self,
        payment_id: str,
        order_id: str,
        signature: str,
    ) -> bool:
        ...
