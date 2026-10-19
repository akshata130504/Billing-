"""Manual / offline payment gateway adapter."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from backend.app.models.payments import PaymentGateway
from backend.app.services.gateways.base import GatewayChargeResult, GatewayRefundResult


class ManualGatewayAdapter:
    gateway_type: PaymentGateway = PaymentGateway.MANUAL

    def charge(
        self,
        amount: Decimal,
        currency: str,
        customer_id: str,
        payment_method_token: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        **_: Any,
    ) -> GatewayChargeResult:
        # Manual payments succeed immediately upon user recording. This adapter is
        # only reachable from authenticated staff flows (recording an offline
        # payment); public/unauthenticated checkout never selects it.
        return GatewayChargeResult(
            success=True,
            gateway_payment_id=f"manual_{uuid.uuid4().hex[:12]}",
            raw_payload={"type": "manual", "notes": notes},
        )

    def refund(
        self,
        gateway_payment_id: str,
        amount: Decimal,
        reason: Optional[str] = None,
        **_: Any,
    ) -> GatewayRefundResult:
        return GatewayRefundResult(
            success=True,
            gateway_refund_id=f"manual_rf_{uuid.uuid4().hex[:12]}",
            raw_payload={"type": "manual_refund", "reason": reason},
        )

    def verify_webhook(
        self,
        raw_body: bytes,
        signature: Optional[str],
        **_: Any,
    ) -> bool:
        return True

    def verify_payment_signature(
        self,
        payment_id: str,
        order_id: str,
        signature: str,
        **_: Any,
    ) -> bool:
        return False
