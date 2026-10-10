"""/public/invoices — the hosted payment page (no authentication; the opaque token is the credential)."""
from decimal import Decimal
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response as RawResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.core.exceptions import GatewayNotConfiguredError, InvalidStateError, UnauthorizedError, ValidationAppError
from backend.app.core.rate_limit import limiter, public_action_rate_limit, public_rate_limit
from backend.app.models import (
    OPEN_INVOICE_STATUSES,
    AuditStatus,
    Organization,
    Payment,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    ReconciliationStatus,
    utcnow,
)
from backend.app.schemas.common_refs import money_str
from backend.app.schemas.public import PublicInvoice, RazorpayOrderIn, RazorpayOrderOut, RazorpayVerifyIn, RazorpayVerifyOut
from backend.app.services import audit, invoice_service, org_lifecycle, payment_service, razorpay_gateway
from backend.app.services.invoice_pdf import render_invoice_pdf
from backend.app.services.money import q2
from backend.app.services.numbering import next_number

router = APIRouter()

# Smallest partial payment accepted online (INR). An invoice with less than this
# outstanding must be paid in full.
MIN_PARTIAL_PAYMENT = Decimal("1.00")


def _razorpay_public_config(db: Session, organization_id: str) -> Dict[str, Any]:
    unavailable_reason = org_lifecycle.payment_unavailable_reason(db, organization_id)
    if unavailable_reason is not None:
        return {"enabled": False, "key_id": None, "unavailable_reason": unavailable_reason}
    creds = razorpay_gateway.credentials_for(db, organization_id)
    enabled = razorpay_gateway.is_configured(creds)
    return {"enabled": enabled, "key_id": razorpay_gateway.public_key_id(creds) if enabled else None}


def _public_invoice(db: Session, invoice) -> Dict[str, Any]:
    organization = db.get(Organization, invoice.organization_id)
    customer = invoice.customer
    data = invoice_service.serialize_invoice(invoice, include_payments=True)
    return {
        "invoice_number": data["invoice_number"],
        "status": data["status"],
        "issue_date": data["issue_date"],
        "due_date": data["due_date"],
        "currency": data["currency"],
        "subtotal": data["subtotal"],
        "discount_pct": data["discount_pct"],
        "discount_amount": data["discount_amount"],
        "tax_amount": data["tax_amount"],
        "cgst_amount": data.get("cgst_amount", "0.00"),
        "sgst_amount": data.get("sgst_amount", "0.00"),
        "igst_amount": data.get("igst_amount", "0.00"),
        "supply_type": data.get("supply_type"),
        "place_of_supply_name": data.get("place_of_supply_name"),
        "total": data["total"],
        "amount_paid": data["amount_paid"],
        "amount_due": data["amount_due"],
        "items": data["items"],
        "notes": data["notes"],
        "terms": data["terms"],
        "period_start": data["period_start"],
        "period_end": data["period_end"],
        "days_overdue": data["days_overdue"],
        "pdf_url": data["pdf_url"],
        "organization": {
            "name": organization.name,
            "legal_name": organization.legal_name,
            "email": organization.email,
            "phone": organization.phone,
            "website": organization.website,
            "address_line1": organization.address_line1,
            "address_line2": organization.address_line2,
            "city": organization.city,
            "state": organization.state,
            "postal_code": organization.postal_code,
            "country": organization.country,
            "gstin": organization.gstin,
            "pan": organization.pan,
            "logo_url": organization.logo_url,
        },
        "customer": {
            "display_name": customer.display_name,
            "company_name": customer.company_name,
            "email": customer.email,
            "phone": customer.phone,
            "gstin": customer.gstin,
            "billing_address_line1": customer.billing_address_line1,
            "billing_address_line2": customer.billing_address_line2,
            "billing_city": customer.billing_city,
            "billing_state": customer.billing_state,
            "billing_postal_code": customer.billing_postal_code,
            "billing_country": customer.billing_country,
        },
        "payments": data["payments"],
        "razorpay": _razorpay_public_config(db, invoice.organization_id),
    }


@router.get("/{token}", response_model=PublicInvoice, summary="Hosted invoice view")
@limiter.limit(public_rate_limit)
def public_invoice(request: Request, token: str, db: Session = Depends(get_db)):
    invoice = invoice_service.get_invoice_by_token(db, token)
    org_lifecycle.assert_customer_pages_visible(db, invoice.organization_id)
    return _public_invoice(db, invoice)


@router.get("/{token}/pdf", response_class=RawResponse, summary="Invoice PDF", responses={200: {"content": {"application/pdf": {}}}})
@limiter.limit(public_rate_limit)
def public_invoice_pdf(request: Request, token: str, db: Session = Depends(get_db)):
    invoice = invoice_service.get_invoice_by_token(db, token)
    org_lifecycle.assert_customer_pages_visible(db, invoice.organization_id)
    organization = db.get(Organization, invoice.organization_id)
    pdf = render_invoice_pdf(invoice, organization)
    return RawResponse(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.invoice_number}.pdf"'},
    )


@router.post("/{token}/razorpay-order", response_model=RazorpayOrderOut, summary="Create a Razorpay order for the invoice")
@limiter.limit(public_action_rate_limit)
def create_razorpay_order(request: Request, token: str, body: RazorpayOrderIn, db: Session = Depends(get_db)):
    invoice = invoice_service.get_invoice_by_token(db, token)
    org_lifecycle.assert_payment_collection_allowed(db, invoice.organization_id)
    creds = razorpay_gateway.credentials_for(db, invoice.organization_id)
    if not razorpay_gateway.is_configured(creds):
        raise GatewayNotConfiguredError("razorpay")
    if invoice.status not in OPEN_INVOICE_STATUSES:
        raise InvalidStateError(f"Invoice {invoice.invoice_number} is {invoice.status.value} and cannot be paid online.")
    amount_due = q2(invoice.amount_due)
    amount = q2(body.amount) if body.amount is not None else amount_due
    minimum = amount_due if amount_due < MIN_PARTIAL_PAYMENT else MIN_PARTIAL_PAYMENT
    if amount < minimum or amount <= 0 or amount > amount_due:
        raise ValidationAppError(
            f"Amount must be between {minimum} and the amount due ({amount_due}).", {"fields": {"amount": "out of range"}}
        )
    organization = db.get(Organization, invoice.organization_id)
    customer = invoice.customer

    payment = Payment(
        organization_id=invoice.organization_id,
        payment_number=next_number(db, invoice.organization_id, "payment"),
        customer_id=invoice.customer_id,
        amount=amount,
        currency=invoice.currency,
        method=PaymentMethod.RAZORPAY,
        gateway=PaymentGateway.RAZORPAY,
        status=PaymentStatus.PENDING,
        reconciliation_status=ReconciliationStatus.UNMATCHED,
        gateway_signature_verified=False,
        notes=f"Hosted payment page order for {invoice.invoice_number}",
    )
    db.add(payment)
    db.flush()

    order = razorpay_gateway.create_order(
        payment_service.to_paise(amount),
        invoice.currency,
        invoice.invoice_number,
        {"invoice_id": invoice.id, "payment_id": payment.id, "organization_id": invoice.organization_id},
        creds=creds,
    )
    payment.gateway_order_id = order["id"]
    payment.gateway_payload = {
        "order": order,
        "notes": {"invoice_id": invoice.id, "payment_id": payment.id, "organization_id": invoice.organization_id},
        "client_ip": request.client.host if request.client else None,
    }
    audit.record(
        db,
        action="PAYMENT_ORDER_CREATED",
        entity_type="payment",
        entity_id=payment.id,
        entity_label=payment.payment_number,
        organization_id=invoice.organization_id,
        actor_label=audit.CUSTOMER_ACTOR,
        after={"gateway_order_id": order["id"], "amount": amount, "invoice_id": invoice.id, "invoice_number": invoice.invoice_number},
    )
    db.commit()
    return {
        "order_id": order["id"],
        "amount": int(order.get("amount") or payment_service.to_paise(amount)),
        "currency": order.get("currency") or invoice.currency,
        "key_id": razorpay_gateway.public_key_id(creds),
        "payment_id": payment.id,
        "invoice_number": invoice.invoice_number,
        "organization_name": organization.legal_name or organization.name,
        "prefill": {"name": customer.display_name, "email": customer.email, "contact": customer.phone},
    }


@router.post("/{token}/razorpay-verify", response_model=RazorpayVerifyOut, summary="Verify the checkout signature and capture")
@limiter.limit(public_action_rate_limit)
def verify_razorpay_payment(request: Request, token: str, body: RazorpayVerifyIn, db: Session = Depends(get_db)):
    invoice = invoice_service.get_invoice_by_token(db, token)
    payment = payment_service.find_by_order_id(db, body.razorpay_order_id, invoice.organization_id)
    if payment is None:
        raise ValidationAppError("Unknown order for this invoice.", {"fields": {"razorpay_order_id": "unknown"}})

    notes = dict((payment.gateway_payload or {}).get("notes") or {})
    payment_invoice_id = notes.get("invoice_id")
    if (payment_invoice_id and payment_invoice_id != invoice.id) or payment.customer_id != invoice.customer_id:
        raise ValidationAppError("The submitted payment order does not belong to this invoice.", {"fields": {"razorpay_order_id": "mismatch"}})

    if payment.status == PaymentStatus.SUCCEEDED or payment.status in (PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED):
        # Idempotent: the capture already happened (verify called twice, or the webhook got there first).
        return {
            "status": "succeeded",
            "payment_number": payment.payment_number,
            "invoice_status": invoice.status,
            "amount_due": money_str(invoice.amount_due),
        }

    creds = razorpay_gateway.credentials_for(db, invoice.organization_id)
    if not razorpay_gateway.verify_payment_signature(
        body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature, creds=creds
    ):
        audit.record(
            db,
            action="PAYMENT_FAILED",
            entity_type="payment",
            entity_id=payment.id,
            entity_label=payment.payment_number,
            organization_id=invoice.organization_id,
            actor_label=audit.CUSTOMER_ACTOR,
            after={"reason": "signature verification failed", "razorpay_payment_id": body.razorpay_payment_id, "razorpay_order_id": body.razorpay_order_id},
            status=AuditStatus.DENIED,
        )
        db.commit()
        raise UnauthorizedError("Payment signature verification failed")

    # A valid signature only proves the pair (order, payment) came from Razorpay. Ask
    # Razorpay what actually happened: the payment must be captured/authorized, for
    # this order, for exactly the ordered amount. (A GatewayError here leaves the
    # payment pending; the payment.captured webhook settles it.)
    fetched = razorpay_gateway.fetch_payment(body.razorpay_payment_id, creds=creds)
    problem = razorpay_gateway.verify_fetched_payment(
        fetched,
        expected_order_id=payment.gateway_order_id,
        expected_amount_paise=payment_service.to_paise(payment.amount),
        expected_currency=payment.currency,
    )
    if problem:
        audit.record(
            db,
            action="PAYMENT_FAILED",
            entity_type="payment",
            entity_id=payment.id,
            entity_label=payment.payment_number,
            organization_id=invoice.organization_id,
            actor_label=audit.CUSTOMER_ACTOR,
            after={"reason": f"gateway verification failed: {problem}", "razorpay_payment_id": body.razorpay_payment_id},
            status=AuditStatus.DENIED,
        )
        db.commit()
        raise ValidationAppError(f"Payment could not be verified with Razorpay: {problem}.", {"fields": {"razorpay_payment_id": "unverified"}})

    payment_service.capture_gateway_payment(
        db,
        payment,
        invoice,
        gateway_payment_id=body.razorpay_payment_id,
        payload={
            "razorpay_order_id": body.razorpay_order_id,
            "razorpay_payment_id": body.razorpay_payment_id,
            "gateway_status": fetched.get("status"),
            "verified_at": utcnow().isoformat(),
            "source": "hosted_page",
        },
        signature_verified=True,
        actor_label=audit.CUSTOMER_ACTOR,
    )
    db.commit()
    db.refresh(invoice)
    return {
        "status": "succeeded",
        "payment_number": payment.payment_number,
        "invoice_status": invoice.status,
        "amount_due": money_str(invoice.amount_due),
    }
