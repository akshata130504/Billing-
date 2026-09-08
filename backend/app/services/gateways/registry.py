"""Payment gateway adapter registry."""
from __future__ import annotations

from typing import Dict
from backend.app.models.payments import PaymentGateway
from backend.app.services.gateways.base import PaymentGatewayAdapter
from backend.app.services.gateways.manual_adapter import ManualGatewayAdapter
from backend.app.services.gateways.razorpay_adapter import RazorpayGatewayAdapter

_REGISTRY: Dict[PaymentGateway, PaymentGatewayAdapter] = {
    PaymentGateway.MANUAL: ManualGatewayAdapter(),
    PaymentGateway.RAZORPAY: RazorpayGatewayAdapter(),
}


def get_gateway_adapter(gateway: PaymentGateway | str) -> PaymentGatewayAdapter:
    """Retrieve the registered adapter for a gateway type."""
    gw_enum = PaymentGateway(gateway) if isinstance(gateway, str) else gateway
    adapter = _REGISTRY.get(gw_enum)
    if adapter is None:
        raise ValueError(f"No payment gateway adapter registered for '{gw_enum}'")
    return adapter


def register_gateway_adapter(gateway: PaymentGateway, adapter: PaymentGatewayAdapter) -> None:
    """Register or override an adapter (useful for testing/mocking)."""
    _REGISTRY[gateway] = adapter
