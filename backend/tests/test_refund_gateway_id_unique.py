"""A Razorpay refund can be booked only once (refunds.gateway_refund_id is unique, NULLs allowed)."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.models import Payment, PaymentGateway, PaymentMethod, PaymentStatus, Refund, RefundStatus


def _payment(db, tenant):
    inv = tenant.invoice(tenant.customer(), amount="100.00")
    payment = Payment(
        organization_id=tenant.organization.id, payment_number=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        customer_id=inv.customer_id, amount=Decimal("100.00"), currency="INR", method=PaymentMethod.RAZORPAY,
        gateway=PaymentGateway.RAZORPAY, status=PaymentStatus.SUCCEEDED,
    )
    db.add(payment)
    db.commit()
    return payment


def _refund(payment, gateway_refund_id):
    return Refund(organization_id=payment.organization_id, payment_id=payment.id, amount=Decimal("10.00"),
                  status=RefundStatus.PROCESSED, gateway_refund_id=gateway_refund_id)


def test_the_same_gateway_refund_cannot_be_recorded_twice(db, tenant):
    payment = _payment(db, tenant)
    refund_id = f"rfnd_{uuid.uuid4().hex[:12]}"
    db.add(_refund(payment, refund_id))
    db.commit()
    db.add(_refund(payment, refund_id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_manual_refunds_without_a_gateway_id_are_unaffected(db, tenant):
    payment = _payment(db, tenant)
    db.add_all([_refund(payment, None), _refund(payment, None)])
    db.commit()
