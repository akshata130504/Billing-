"""Razorpay Gateway Adapter wrapping existing razorpay service."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from backend.app.models.payments import PaymentGateway
from backend.app.services import razorpay_gateway
from backend.app.services.gateways.base import GatewayChargeResult, GatewayRefundResult


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
        *,
        credentials: Optional[razorpay_gateway.RazorpayCredentials] = None,
        gateway_customer_id: Optional[str] = None,
        email: Optional[str] = None,
        contact: Optional[str] = None,
        description: Optional[str] = None,
    ) -> GatewayChargeResult:
        """Charge a saved token (recurring) or, without a token, create a Checkout order.

        A recurring charge is asynchronous at Razorpay: the API accepts it and the
        outcome arrives later as payment.captured / payment.failed. The result is
        therefore `success=True, pending=True` - the caller records a PENDING
        payment keyed on the order id and lets the webhook settle it.
        """
        if not razorpay_gateway.is_configured(credentials):
            return GatewayChargeResult(
                success=False,
                error_message="Razorpay gateway credentials are not configured.",
                error_category="gateway_not_configured",
            )

        amount_paise = int((Decimal(amount) * 100).to_integral_value())
        clean_notes = {k: str(v) for k, v in (notes or {}).items()}
        receipt = (idempotency_key or f"rcpt_{(customer_id or '')[:8]}")[:40]
        try:
            if payment_method_token:
                if not gateway_customer_id:
                    return GatewayChargeResult(
                        success=False,
                        error_message="Saved payment method has no Razorpay customer id; it cannot be charged automatically.",
                        error_category="payment_method_not_chargeable",
                    )
                order = razorpay_gateway.create_order(
                    amount_paise=amount_paise,
                    currency=currency,
                    receipt=receipt,
                    notes=clean_notes,
                    creds=credentials,
                    customer_id=gateway_customer_id,
                )
                payload: Dict[str, Any] = {
                    "amount": amount_paise,
                    "currency": currency,
                    "order_id": order["id"],
                    "customer_id": gateway_customer_id,
                    "token": payment_method_token,
                    "recurring": "1",
                    "description": (description or "Recurring charge")[:255],
                    "notes": clean_notes,
                }
                if email:
                    payload["email"] = email
                if contact:
                    payload["contact"] = contact
                res = razorpay_gateway.create_recurring_payment(payload, creds=credentials)
                payment_id = res.get("razorpay_payment_id") or res.get("id")
                if not payment_id:
                    return GatewayChargeResult(
                        success=False,
                        gateway_order_id=order["id"],
                        error_message=str((res.get("error") or {}).get("description") or "Razorpay did not accept the recurring charge."),
                        error_category="gateway_error",
                        raw_payload={"order": order, "recurring": res},
                    )
                return GatewayChargeResult(
                    success=True,
                    pending=True,
                    gateway_payment_id=payment_id,
                    gateway_order_id=res.get("razorpay_order_id") or order["id"],
                    raw_payload={"order": order, "recurring": res},
                )
            order = razorpay_gateway.create_order(
                amount_paise=amount_paise,
                currency=currency,
                receipt=receipt,
                notes=clean_notes,
                creds=credentials,
                customer_id=gateway_customer_id,
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
        *,
        credentials: Optional[razorpay_gateway.RazorpayCredentials] = None,
    ) -> GatewayRefundResult:
        if not razorpay_gateway.is_configured(credentials):
            return GatewayRefundResult(
                success=False,
                error_message="Razorpay gateway credentials are not configured.",
            )

        amount_paise = int((amount * 100).to_integral_value())
        try:
            notes = {"reason": reason} if reason else None
            res = razorpay_gateway.refund_payment(gateway_payment_id, amount_paise, notes=notes, creds=credentials)
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
        *,
        secret: Optional[str] = None,
    ) -> bool:
        return razorpay_gateway.verify_webhook_signature(raw_body, signature, secret=secret)

    def verify_payment_signature(
        self,
        payment_id: str,
        order_id: str,
        signature: str,
        *,
        credentials: Optional[razorpay_gateway.RazorpayCredentials] = None,
    ) -> bool:
        return razorpay_gateway.verify_payment_signature(order_id, payment_id, signature, creds=credentials)
