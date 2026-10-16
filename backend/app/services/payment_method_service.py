"""Customer payment method vault and payment attempt tracking service."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.core.exceptions import NotFoundAppError, ValidationAppError
from backend.app.models.customers import Customer
from backend.app.models.invoices import Invoice
from backend.app.models.payments import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    PaymentAttempt,
    PaymentAttemptStatus,
    PaymentGateway,
)


def create_customer_payment_method(
    db: Session,
    organization_id: str,
    customer_id: str,
    gateway_token: str,
    gateway: PaymentGateway = PaymentGateway.RAZORPAY,
    gateway_customer_id: Optional[str] = None,
    method_type: str = "card",
    card_brand: Optional[str] = None,
    last4: Optional[str] = None,
    exp_month: Optional[int] = None,
    exp_year: Optional[int] = None,
    is_default: bool = False,
    is_autocharge_eligible: bool = True,
) -> CustomerPaymentMethod:
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.organization_id == organization_id)
        .first()
    )
    if not customer:
        raise NotFoundAppError(f"Customer {customer_id} not found.")

    if not gateway_token or not gateway_token.strip():
        raise ValidationAppError("Gateway token is required.", {"fields": {"gateway_token": "required"}})

    # If this is set to default, or if the customer has no active methods yet, make default
    existing_count = (
        db.query(CustomerPaymentMethod)
        .filter(
            CustomerPaymentMethod.customer_id == customer_id,
            CustomerPaymentMethod.organization_id == organization_id,
            CustomerPaymentMethod.status == CustomerPaymentMethodStatus.ACTIVE,
        )
        .count()
    )
    if existing_count == 0:
        is_default = True

    if is_default:
        db.query(CustomerPaymentMethod).filter(
            CustomerPaymentMethod.customer_id == customer_id,
            CustomerPaymentMethod.organization_id == organization_id,
            CustomerPaymentMethod.is_default.is_(True),
        ).update({"is_default": False})

    pm = CustomerPaymentMethod(
        organization_id=organization_id,
        customer_id=customer_id,
        gateway=gateway,
        gateway_customer_id=gateway_customer_id,
        gateway_token=gateway_token.strip(),
        type=method_type,
        card_brand=card_brand,
        last4=last4,
        exp_month=exp_month,
        exp_year=exp_year,
        is_default=is_default,
        is_autocharge_eligible=is_autocharge_eligible,
        status=CustomerPaymentMethodStatus.ACTIVE,
    )
    db.add(pm)
    db.flush()
    return pm


def list_customer_payment_methods(
    db: Session,
    organization_id: str,
    customer_id: str,
    active_only: bool = True,
) -> List[CustomerPaymentMethod]:
    query = db.query(CustomerPaymentMethod).filter(
        CustomerPaymentMethod.customer_id == customer_id,
        CustomerPaymentMethod.organization_id == organization_id,
    )
    if active_only:
        query = query.filter(CustomerPaymentMethod.status == CustomerPaymentMethodStatus.ACTIVE)
    return query.order_by(desc(CustomerPaymentMethod.is_default), desc(CustomerPaymentMethod.created_at)).all()


def get_customer_payment_method(
    db: Session,
    organization_id: str,
    payment_method_id: str,
) -> CustomerPaymentMethod:
    pm = (
        db.query(CustomerPaymentMethod)
        .filter(
            CustomerPaymentMethod.id == payment_method_id,
            CustomerPaymentMethod.organization_id == organization_id,
        )
        .first()
    )
    if not pm:
        raise NotFoundAppError(f"Payment method {payment_method_id} not found.")
    return pm


def set_default_payment_method(
    db: Session,
    organization_id: str,
    customer_id: str,
    payment_method_id: str,
) -> CustomerPaymentMethod:
    target = get_customer_payment_method(db, organization_id, payment_method_id)
    if target.customer_id != customer_id:
        raise ValidationAppError("Payment method does not belong to this customer.")

    if target.status != CustomerPaymentMethodStatus.ACTIVE:
        raise ValidationAppError("Cannot set inactive payment method as default.")

    db.query(CustomerPaymentMethod).filter(
        CustomerPaymentMethod.customer_id == customer_id,
        CustomerPaymentMethod.organization_id == organization_id,
        CustomerPaymentMethod.is_default.is_(True),
    ).update({"is_default": False})

    target.is_default = True
    db.flush()
    return target


def revoke_payment_method(
    db: Session,
    organization_id: str,
    payment_method_id: str,
) -> CustomerPaymentMethod:
    pm = get_customer_payment_method(db, organization_id, payment_method_id)
    pm.status = CustomerPaymentMethodStatus.REVOKED
    pm.is_default = False
    db.flush()
    return pm


def record_payment_attempt(
    db: Session,
    organization_id: str,
    invoice_id: str,
    amount: Decimal,
    customer_payment_method_id: Optional[str] = None,
    gateway: PaymentGateway = PaymentGateway.RAZORPAY,
    currency: str = "INR",
    gateway_attempt_reference: Optional[str] = None,
) -> PaymentAttempt:
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.organization_id == organization_id)
        .first()
    )
    if not invoice:
        raise NotFoundAppError(f"Invoice {invoice_id} not found.")

    # Count existing attempts to set attempt_number
    prior_attempts = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.invoice_id == invoice_id, PaymentAttempt.organization_id == organization_id)
        .count()
    )

    attempt = PaymentAttempt(
        organization_id=organization_id,
        invoice_id=invoice_id,
        customer_id=invoice.customer_id,
        customer_payment_method_id=customer_payment_method_id,
        gateway=gateway,
        amount=amount,
        currency=currency,
        status=PaymentAttemptStatus.CREATED,
        attempt_number=prior_attempts + 1,
        gateway_attempt_reference=gateway_attempt_reference,
    )
    db.add(attempt)
    db.flush()
    return attempt


def update_payment_attempt(
    db: Session,
    organization_id: str,
    attempt_id: str,
    status: PaymentAttemptStatus,
    payment_id: Optional[str] = None,
    gateway_attempt_reference: Optional[str] = None,
    failure_reason: Optional[str] = None,
    failure_category: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> PaymentAttempt:
    attempt = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.id == attempt_id, PaymentAttempt.organization_id == organization_id)
        .first()
    )
    if not attempt:
        raise NotFoundAppError(f"Payment attempt {attempt_id} not found.")

    attempt.status = status
    if payment_id:
        attempt.payment_id = payment_id
    if gateway_attempt_reference:
        attempt.gateway_attempt_reference = gateway_attempt_reference
    if failure_reason:
        attempt.failure_reason = failure_reason
    if failure_category:
        attempt.failure_category = failure_category
    if payload:
        attempt.payload = payload

    db.flush()
    return attempt


def list_invoice_payment_attempts(
    db: Session,
    organization_id: str,
    invoice_id: str,
) -> List[PaymentAttempt]:
    return (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.invoice_id == invoice_id, PaymentAttempt.organization_id == organization_id)
        .order_by(PaymentAttempt.attempt_number.asc())
        .all()
    )
