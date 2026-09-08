"""Customer payment methods and invoice payment attempts endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.schemas.common_refs import money_str
from backend.app.schemas.payment_methods import (
    CustomerPaymentMethodCreateIn,
    CustomerPaymentMethodOut,
    PaymentAttemptOut,
)
from backend.app.services import payment_method_service

router = APIRouter()


@router.get(
    "/customers/{customer_id}/payment-methods",
    response_model=List[CustomerPaymentMethodOut],
    summary="List customer saved payment methods",
)
def list_customer_payment_methods(
    customer_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return payment_method_service.list_customer_payment_methods(
        db, organization_id=ctx.organization_id, customer_id=customer_id
    )


@router.post(
    "/customers/{customer_id}/payment-methods",
    response_model=CustomerPaymentMethodOut,
    status_code=status.HTTP_201_CREATED,
    summary="Save a vaulted payment method for customer",
)
def add_customer_payment_method(
    customer_id: str,
    body: CustomerPaymentMethodCreateIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    pm = payment_method_service.create_customer_payment_method(
        db,
        organization_id=ctx.organization_id,
        customer_id=customer_id,
        gateway_token=body.gateway_token,
        gateway=body.gateway,
        gateway_customer_id=body.gateway_customer_id,
        method_type=body.type,
        card_brand=body.card_brand,
        last4=body.last4,
        exp_month=body.exp_month,
        exp_year=body.exp_year,
        is_default=body.is_default,
        is_autocharge_eligible=body.is_autocharge_eligible,
    )
    db.commit()
    db.refresh(pm)
    return pm


@router.post(
    "/customers/{customer_id}/payment-methods/{payment_method_id}/set-default",
    response_model=CustomerPaymentMethodOut,
    summary="Set customer payment method as default",
)
def set_default_payment_method(
    customer_id: str,
    payment_method_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    pm = payment_method_service.set_default_payment_method(
        db,
        organization_id=ctx.organization_id,
        customer_id=customer_id,
        payment_method_id=payment_method_id,
    )
    db.commit()
    db.refresh(pm)
    return pm


@router.delete(
    "/customers/{customer_id}/payment-methods/{payment_method_id}",
    response_model=CustomerPaymentMethodOut,
    summary="Revoke customer payment method",
)
def revoke_payment_method(
    customer_id: str,
    payment_method_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    pm = payment_method_service.revoke_payment_method(
        db,
        organization_id=ctx.organization_id,
        payment_method_id=payment_method_id,
    )
    db.commit()
    db.refresh(pm)
    return pm


@router.get(
    "/invoices/{invoice_id}/payment-attempts",
    response_model=List[PaymentAttemptOut],
    summary="List payment attempts for invoice",
)
def list_invoice_payment_attempts(
    invoice_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    attempts = payment_method_service.list_invoice_payment_attempts(
        db, organization_id=ctx.organization_id, invoice_id=invoice_id
    )
    return [
        {
            "id": a.id,
            "invoice_id": a.invoice_id,
            "customer_id": a.customer_id,
            "customer_payment_method_id": a.customer_payment_method_id,
            "payment_id": a.payment_id,
            "gateway": a.gateway,
            "amount": money_str(a.amount),
            "currency": a.currency,
            "status": a.status,
            "attempt_number": a.attempt_number,
            "gateway_attempt_reference": a.gateway_attempt_reference,
            "failure_reason": a.failure_reason,
            "failure_category": a.failure_category,
            "payload": a.payload,
            "created_at": a.created_at,
        }
        for a in attempts
    ]
