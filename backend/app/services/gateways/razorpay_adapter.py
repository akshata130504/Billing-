"""Razorpay Gateway Adapter wrapping existing razorpay service."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from backend.app.models.payments import PaymentGateway
from backend.app.services import razorpay_gateway
from backend.app.services.gateways.base import GatewayChargeResult, GatewayRefundResult, PaymentGatewayAdapter


class RazorpayGatewayAdapter:
    gateway_type: PaymentGateway = PaymentGateway.RAZORPAY

    def charge(
        self,
        amount: Decimal,
        currency: str,
        customer_id: str,
        payment_method_token: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> GatewayChargeResult:
        if not razorpay_gateway.is_configured():
            return GatewayChargeResult(
                success=False,
                error_message="Razorpay gateway credentials are not configured.",
                error_category="gateway_not_configured",
            )

        amount_paise = int((amount * 100).to_integral_value())
        try:
            # If customer has a vaulted recurring token, charge it
            if payment_method_token:
                client = razorpay_gateway._get_client()
                # Recurring direct debit / charge token
                charge_payload = {
                    "amount": amount_paise,
                    "currency": currency,
                    "token": payment_method_token,
                    "notes": notes or {},
                }
                res = client.payment.createRecurringPayment(charge_payload)
                return GatewayChargeResult(
                    success=True,
                    gateway_payment_id=res.get("razorpay_payment_id") or res.get("id"),
                    raw_payload=res,
                )
            else:
                # Create standard order
                order = razorpay_gateway.create_order(
                    amount_paise=amount_paise,
                    currency=currency,
                    receipt=idempotency_key or f"rcpt_{customer_id[:8]}",
                    notes=notes,
                )
                return GatewayChargeResult(
                    success=True,
                    gateway_order_id=order.get("id"),
                    raw_payload=order,
                )
        except Exception as exc:
            return GatewayChargeResult(
                success=False,
                error_message=str(exc),
                error_category="gateway_error",
                raw_payload={"error": str(exc)},
            )

    def refund(
        self,
        gateway_payment_id: str,
        amount: Decimal,
        reason: Optional[str] = None,
    ) -> GatewayRefundResult:
        if not razorpay_gateway.is_configured():
            return GatewayRefundResult(
                success=False,
                error_message="Razorpay gateway credentials are not configured.",
            )

        amount_paise = int((amount * 100).to_integral_value())
        try:
            notes = {"reason": reason} if reason else None
            res = razorpay_gateway.refund_payment(gateway_payment_id, amount_paise, notes=notes)
            return GatewayRefundResult(
                success=True,
                gateway_refund_id=res.get("id"),
                raw_payload=res,
            )
        except Exception as exc:
            return GatewayRefundResult(
                success=False,
                error_message=str(exc),
                raw_payload={"error": str(exc)},
            )

    def verify_webhook(
        self,
        raw_body: bytes,
        signature: Optional[str],
    ) -> bool:
        return razorpay_gateway.verify_webhook_signature(raw_body, signature)

    def verify_payment_signature(
        self,
        payment_id: str,
        order_id: str,
        signature: str,
    ) -> bool:
        return razorpay_gateway.verify_payment_signature(order_id, payment_id, signature)
