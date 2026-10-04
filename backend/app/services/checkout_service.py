"""Hosted payment pages and checkout session domain service.

Provides tokenized public payment flows for invoices, new subscriptions and
one-time add-ons. Money is only ever recorded after Razorpay confirms it:

1. Viewing the page creates the Razorpay order *and* a PENDING Payment keyed on it
   (so a payment is never lost if the browser closes - the webhook settles it).
2. /confirm (browser) and the payment.captured webhook both settle through
   `payment_service.capture_gateway_payment` under row locks, then
   `_fulfill_session` runs exactly once per session.
3. Subscriptions and add-ons are billed on a real GST tax invoice built from the
   price snapshot taken when the session was created.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.app.core.exceptions import AppException, ConflictAppError, NotFoundAppError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.catalog import Plan
from backend.app.models.checkout import (
    CheckoutSession,
    CheckoutSessionPurpose,
    CheckoutSessionStatus,
    CheckoutTemplate,
    CheckoutTemplateType,
)
from backend.app.models.customers import Customer
from backend.app.models.events import DomainEventType, OutboxEvent, OutboxStatus
from backend.app.models.identity import Organization
from backend.app.models.invoices import OPEN_INVOICE_STATUSES, Invoice, InvoiceStatus
from backend.app.models.payments import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    Payment,
    PaymentAttempt,
    PaymentAttemptStatus,
    PaymentGateway,
    PaymentStatus,
)
from backend.app.models.portal import CustomerPortalSettings
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.schemas.checkout import (
    CheckoutConfirmIn,
    CheckoutConfirmOut,
    CheckoutSessionCreate,
    PublicCheckoutView,
)
from backend.app.services import audit, gst, invoice_service, org_lifecycle, payment_service, razorpay_gateway, timezones
from backend.app.services.gateways.registry import get_gateway_adapter
from backend.app.services.money import D, LineInput, compute_totals, q2
from backend.app.services.numbering import next_number
from backend.app.services.subscription_service import apply_plan_terms, interval_months, period_end_for, plan_tax_rate


class BadRequestAppError(AppException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="BAD_REQUEST", status_code=http_status.HTTP_400_BAD_REQUEST, details=details or {})


# Keys the server owns inside CheckoutSession.metadata_snapshot. Client-supplied
# metadata can never set them (e.g. a pre-chosen gateway order id).
_RESERVED_META_KEYS = ("gateway_order_id", "pending_payment_id", "pricing", "gateway_customer_id", "fulfilled")

# Purposes a public checkout can actually settle. Card-only purposes need a
# zero-amount mandate flow Razorpay orders do not offer, and a plan change must go
# through the proration engine (subscription_change_service), which requires an
# authenticated staff context - so those are refused at creation instead of
# pretending to work.
_UNSUPPORTED_PURPOSES = {
    CheckoutSessionPurpose.UPDATE_SUBSCRIPTION: (
        "Plan changes cannot be paid through a hosted checkout link; apply the change from the "
        "subscription (it prorates and issues the invoice), then send an invoice payment link."
    ),
    CheckoutSessionPurpose.UPDATE_CARD: (
        "Saving a card without a payment is not supported by the gateway; the card is saved when the "
        "customer pays an invoice checkout with 'save payment method' enabled."
    ),
    CheckoutSessionPurpose.ADD_PAYMENT_METHOD: (
        "Saving a card without a payment is not supported by the gateway; the card is saved when the "
        "customer pays an invoice checkout with 'save payment method' enabled."
    ),
}


def _hash_token(raw_token: str) -> str:
    """Compute SHA-256 hex digest of a bearer checkout token."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def masked_reference(token_hash: str) -> str:
    """Non-secret display reference for a stored session (never usable as a link)."""
    return f"ref_{(token_hash or '')[:12]}"


def _is_safe_redirect_url(url: Optional[str]) -> bool:
    """Ensure redirect URL does not use javascript:, data:, vbscript: schemes or protocol-relative slashes."""
    if not url:
        return True
    cleaned = url.strip()
    # Block protocol-relative URLs like //evil.com or /\evil.com
    if cleaned.startswith(("//", "/\\")):
        return False
    lower = cleaned.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        return False
    parsed = urlparse(cleaned)
    if parsed.scheme and parsed.scheme.lower() not in ("http", "https"):
        return False
    return True


def _lookup_session(db: Session, token: str) -> Optional[CheckoutSession]:
    """Lookup a session by the SHA-256 hash of the bearer token.

    Only the hash is stored, and only the hash is matched: the stored value itself is
    never accepted as a token, so a leaked hash (logs, DB read access, an old list
    response) cannot be replayed as a checkout link.
    """
    token_hash = _hash_token(token or "")
    from backend.app.core.tenant_context import set_tenant_context, system_context
    with system_context():
        session = db.scalars(
            select(CheckoutSession)
            .options(
                joinedload(CheckoutSession.customer),
                joinedload(CheckoutSession.invoice),
                joinedload(CheckoutSession.plan),
                joinedload(CheckoutSession.template),
                joinedload(CheckoutSession.subscription),
            )
            .where(CheckoutSession.token == token_hash)
        ).first()
    if session is not None:
        set_tenant_context(session.organization_id)
    return session


def _lock_session(db: Session, session: CheckoutSession) -> CheckoutSession:
    """SELECT ... FOR UPDATE on the session row, then reload it, so two confirms (double
    click, confirm vs. webhook) serialise and the second sees the first's outcome."""
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        db.execute(select(CheckoutSession.id).where(CheckoutSession.id == session.id).with_for_update())
    db.refresh(session)
    return session


def get_or_create_default_template(db: Session, organization_id: str) -> CheckoutTemplate:
    """Gets existing default template or creates a clean fallback one."""
    tmpl = db.scalars(
        select(CheckoutTemplate).where(
            CheckoutTemplate.organization_id == organization_id,
            CheckoutTemplate.is_default.is_(True),
        )
    ).first()
    if tmpl:
        return tmpl

    tmpl = CheckoutTemplate(
        organization_id=organization_id,
        name="Standard Checkout",
        template_type=CheckoutTemplateType.SINGLE_PAGE,
        primary_color="#2563eb",
        accent_color="#1e40af",
        button_text="Pay Now",
        allow_quantity_edit=False,
        show_order_summary=True,
        is_default=True,
        is_active=True,
    )
    db.add(tmpl)
    db.flush()
    return tmpl


def _customer_for(db: Session, organization_id: str, customer_id: Optional[str]) -> Customer:
    if not customer_id:
        raise ValidationAppError("customer_id is required for this checkout purpose.", {"fields": {"customer_id": "required"}})
    customer = db.scalars(
        select(Customer).where(Customer.organization_id == organization_id, Customer.id == customer_id)
    ).first()
    if customer is None:
        raise NotFoundAppError(f"Customer {customer_id} not found.")
    return customer


def _price_lines(db: Session, organization_id: str, customer: Customer, lines: List[LineInput]) -> Tuple[Dict[str, Any], Decimal]:
    """GST-price `lines` for `customer` exactly as the tax invoice will, and return
    (snapshot, total). The snapshot is what the invoice is later built from, so the
    customer pays precisely the invoice total."""
    organization = db.get(Organization, organization_id)
    supply = gst.resolve_supply(organization, customer)
    invoice_service.attach_hsn_codes(db, organization_id, lines)
    try:
        totals = compute_totals(lines, 0, supply=supply)
    except ValueError as exc:
        raise ValidationAppError(str(exc), {"fields": {"items": str(exc)}})
    snapshot = {
        "lines": [
            {
                "description": l.description,
                "quantity": str(l.quantity),
                "unit_price": str(l.unit_price),
                "tax_rate_pct": str(l.tax_rate_pct),
                "product_id": l.product_id,
                "plan_id": l.plan_id,
                "hsn_sac_code": l.hsn_sac_code,
            }
            for l in lines
        ],
        "subtotal": str(totals.subtotal),
        "tax_amount": str(totals.tax_amount),
        "total": str(totals.total),
    }
    return snapshot, totals.total


def _lines_from_snapshot(pricing: Dict[str, Any]) -> List[LineInput]:
    return [
        LineInput(
            description=l.get("description") or "Item",
            quantity=D(l.get("quantity") or 1),
            unit_price=D(l.get("unit_price") or 0),
            tax_rate_pct=D(l.get("tax_rate_pct") or 0),
            product_id=l.get("product_id"),
            plan_id=l.get("plan_id"),
            hsn_sac_code=l.get("hsn_sac_code"),
        )
        for l in (pricing.get("lines") or [])
    ]


def create_checkout_session(
    db: Session,
    organization_id: str,
    data: CheckoutSessionCreate,
) -> CheckoutSession:
    """Generates an expiring, token-hashed hosted checkout session."""
    template_id = data.template_id
    if template_id:
        tmpl = db.scalars(
            select(CheckoutTemplate).where(
                CheckoutTemplate.organization_id == organization_id,
                CheckoutTemplate.id == template_id,
            )
        ).first()
        if not tmpl:
            raise NotFoundAppError(f"Checkout template '{template_id}' not found.")
    else:
        tmpl = get_or_create_default_template(db, organization_id)
        template_id = tmpl.id

    if tmpl.redirect_url and not _is_safe_redirect_url(tmpl.redirect_url):
        raise ValidationAppError("Template redirect URL contains an unsafe destination.")

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = utcnow() + timedelta(hours=data.expires_in_hours or 1)

    try:
        purpose = CheckoutSessionPurpose(data.purpose)
    except ValueError:
        raise ValidationAppError(f"Unsupported checkout purpose: {data.purpose}")
    if purpose in _UNSUPPORTED_PURPOSES:
        raise ValidationAppError(_UNSUPPORTED_PURPOSES[purpose], {"fields": {"purpose": "unsupported"}})

    amount = Decimal("0.00")
    currency = (data.currency or "INR").upper()
    customer_id = data.customer_id
    invoice_id = data.invoice_id
    subscription_id = data.subscription_id
    plan_id = data.plan_id
    meta: Dict[str, Any] = {k: v for k, v in (data.metadata_snapshot or {}).items() if k not in _RESERVED_META_KEYS}

    if purpose == CheckoutSessionPurpose.INVOICE_PAYMENT:
        if not invoice_id:
            raise ValidationAppError("invoice_id is required for invoice_payment checkout session.")
        invoice = db.scalars(
            select(Invoice).where(
                Invoice.organization_id == organization_id,
                Invoice.id == invoice_id,
            )
        ).first()
        if not invoice:
            raise NotFoundAppError(f"Invoice {invoice_id} not found.")
        if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.VOID):
            raise ConflictAppError(f"Invoice {invoice.invoice_number} is already {invoice.status.value}.")
        if invoice.status == InvoiceStatus.DRAFT:
            raise ConflictAppError(f"Invoice {invoice.invoice_number} is a draft; send it before collecting payment.")
        if invoice.amount_due <= Decimal("0.00"):
            raise ConflictAppError(f"Invoice {invoice.invoice_number} has no outstanding balance.")

        # Check portal duplicate prevention setting
        portal_settings = db.scalars(
            select(CustomerPortalSettings).where(CustomerPortalSettings.organization_id == organization_id)
        ).first()
        if portal_settings and portal_settings.prevent_duplicate_payments:
            pending_attempt = db.scalars(
                select(PaymentAttempt).where(
                    PaymentAttempt.invoice_id == invoice.id,
                    PaymentAttempt.status.in_([PaymentAttemptStatus.PENDING, PaymentAttemptStatus.SUBMITTED]),
                )
            ).first()
            if pending_attempt:
                raise ConflictAppError(
                    "A payment attempt is currently processing for this invoice. Please wait before retrying."
                )

        amount = invoice.amount_due
        currency = invoice.currency or "INR"
        customer_id = invoice.customer_id
        subscription_id = invoice.subscription_id

    elif purpose == CheckoutSessionPurpose.NEW_SUBSCRIPTION:
        if not plan_id:
            raise ValidationAppError("plan_id is required for new_subscription checkout session.")
        customer = _customer_for(db, organization_id, customer_id)
        plan = db.scalars(
            select(Plan).where(Plan.organization_id == organization_id, Plan.id == plan_id)
        ).first()
        if not plan:
            raise NotFoundAppError(f"Plan {plan_id} not found.")
        if not plan.is_active:
            raise ValidationAppError("Plan is inactive.")
        interval_months(plan)  # 422 for one-time plans, which are not subscriptions
        lines = [
            LineInput(
                description=f"{plan.name} subscription",
                quantity=Decimal("1"),
                unit_price=D(plan.unit_amount),
                tax_rate_pct=plan_tax_rate(plan, customer),
                product_id=plan.product_id,
                plan_id=plan.id,
            )
        ]
        pricing, amount = _price_lines(db, organization_id, customer, lines)
        meta["pricing"] = pricing
        currency = plan.currency or currency
        customer_id = customer.id

    elif purpose == CheckoutSessionPurpose.ONE_TIME_ADDON:
        customer = _customer_for(db, organization_id, customer_id)
        base = D(data.amount)
        if base <= Decimal("0.00"):
            raise ValidationAppError("Amount must be greater than 0 for one_time_addon checkout.")
        tax_rate = D(meta.get("tax_rate_pct") or 0) if not customer.tax_exempt else Decimal("0")
        lines = [
            LineInput(
                description=str(meta.get("description") or "One-time add-on")[:500],
                quantity=Decimal("1"),
                unit_price=q2(base),
                tax_rate_pct=tax_rate,
                product_id=meta.get("product_id"),
                hsn_sac_code=meta.get("hsn_sac_code"),
            )
        ]
        pricing, amount = _price_lines(db, organization_id, customer, lines)
        meta["pricing"] = pricing
        customer_id = customer.id

    session = CheckoutSession(
        organization_id=organization_id,
        template_id=template_id,
        token=token_hash,  # Store SHA-256 hash only
        purpose=purpose,
        status=CheckoutSessionStatus.CREATED,
        customer_id=customer_id,
        invoice_id=invoice_id,
        subscription_id=subscription_id,
        plan_id=plan_id,
        amount=amount,
        currency=currency,
        expires_at=expires_at,
        save_payment_method=data.save_payment_method,
        metadata_snapshot=meta,
    )
    db.add(session)
    db.flush()

    # Attach ephemeral raw token for caller response (the only time it exists).
    setattr(session, "raw_token", raw_token)
    return session


def _gateway_customer_id(db: Session, session: CheckoutSession, creds) -> Optional[str]:
    """Razorpay customer id for card saving, only when the merchant enabled saving."""
    if not session.save_payment_method or not session.customer:
        return None
    existing = db.scalars(
        select(CustomerPaymentMethod.gateway_customer_id).where(
            CustomerPaymentMethod.organization_id == session.organization_id,
            CustomerPaymentMethod.customer_id == session.customer_id,
            CustomerPaymentMethod.gateway == PaymentGateway.RAZORPAY,
            CustomerPaymentMethod.gateway_customer_id.isnot(None),
        )
    ).first()
    if existing:
        return existing
    customer = session.customer
    if not (customer.email or customer.phone):
        return None
    try:
        created = razorpay_gateway.create_customer(
            customer.display_name,
            email=customer.email,
            contact=customer.phone,
            notes={"customer_id": customer.id, "organization_id": session.organization_id},
            creds=creds,
        )
        return created.get("id")
    except Exception as exc:  # saving a card is optional; never block the payment
        logger.info("Razorpay customer could not be created for checkout %s: %s", session.id, exc)
        return None


def _ensure_gateway_order(db: Session, session: CheckoutSession) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Create (once) the Razorpay order and the PENDING Payment it settles.

    The Payment row is what makes the checkout durable: if the customer pays and
    closes the browser before /confirm, the payment.captured webhook finds it by
    order id and completes the session. Returns (order_id, key_id, gateway_customer_id).
    """
    creds = razorpay_gateway.credentials_for(db, session.organization_id)
    if not razorpay_gateway.is_configured(creds):
        return None, None, None
    meta = dict(session.metadata_snapshot or {})
    order_id = meta.get("gateway_order_id")
    if order_id:
        return order_id, razorpay_gateway.public_key_id(creds), meta.get("gateway_customer_id")
    if D(session.amount) <= 0:
        return None, razorpay_gateway.public_key_id(creds), None

    amount = q2(session.amount)
    if session.purpose == CheckoutSessionPurpose.INVOICE_PAYMENT and session.invoice is not None:
        amount = q2(session.invoice.amount_due)
        if amount <= 0 or session.invoice.status not in OPEN_INVOICE_STATUSES:
            return None, razorpay_gateway.public_key_id(creds), None

    notes = {"checkout_session_id": session.id, "organization_id": session.organization_id, "purpose": session.purpose.value}
    if session.invoice_id:
        notes["invoice_id"] = session.invoice_id
    gateway_customer_id = _gateway_customer_id(db, session, creds)
    payment = payment_service.create_pending_gateway_payment(
        db,
        organization_id=session.organization_id,
        customer_id=session.customer_id,
        amount=amount,
        currency=session.currency,
        notes=f"Hosted checkout ({session.purpose.value})",
    )
    notes["payment_id"] = payment.id
    try:
        order = razorpay_gateway.create_order(
            payment_service.to_paise(amount),
            session.currency,
            f"hpp_{session.id[:32]}",
            notes,
            creds=creds,
            customer_id=gateway_customer_id,
        )
    except Exception as exc:
        logger.warning("Checkout %s: Razorpay order could not be created: %s", session.id, exc)
        db.delete(payment)
        db.flush()
        return None, razorpay_gateway.public_key_id(creds), None
    payment.gateway_order_id = order["id"]
    payment.gateway_payload = {"order": order, "notes": notes}
    meta.update({"gateway_order_id": order["id"], "pending_payment_id": payment.id, "gateway_customer_id": gateway_customer_id})
    session.metadata_snapshot = meta
    session.payment_id = payment.id
    db.flush()
    return order["id"], razorpay_gateway.public_key_id(creds), gateway_customer_id


def get_public_checkout_view(db: Session, token: str) -> PublicCheckoutView:
    """Returns safe, public view representation of a checkout session for customer browsers."""
    session = _lookup_session(db, token)
    if not session:
        raise NotFoundAppError("Checkout page not found or link is invalid.")
    org_lifecycle.assert_customer_pages_visible(db, session.organization_id)

    now = utcnow()
    expires_at = session.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    is_expired = expires_at < now if expires_at else False
    if is_expired and session.status in (CheckoutSessionStatus.CREATED, CheckoutSessionStatus.PENDING):
        session.status = CheckoutSessionStatus.EXPIRED
        db.flush()

    if not is_expired and session.status == CheckoutSessionStatus.CREATED:
        session.status = CheckoutSessionStatus.PENDING
        db.flush()

    org = db.scalars(select(Organization).where(Organization.id == session.organization_id)).first()
    portal_settings = db.scalars(
        select(CustomerPortalSettings).where(CustomerPortalSettings.organization_id == session.organization_id)
    ).first()

    desc_text = f"Payment for {session.purpose.value}"
    if session.invoice:
        desc_text = f"Invoice {session.invoice.invoice_number}"
    elif session.plan:
        desc_text = f"Subscription to {session.plan.name}"

    branding = {}
    if session.template:
        branding = {
            "name": session.template.name,
            "primary_color": session.template.primary_color,
            "accent_color": session.template.accent_color,
            "logo_url": session.template.logo_url,
            "button_text": session.template.button_text,
            "show_order_summary": session.template.show_order_summary,
            "thank_you_message": session.template.thank_you_message,
        }

    gateway_order_id = None
    gateway_key_id = None
    gateway_customer_id = None
    amount = session.amount
    if session.purpose == CheckoutSessionPurpose.INVOICE_PAYMENT and session.invoice is not None and session.status != CheckoutSessionStatus.SUCCESSFUL:
        amount = session.invoice.amount_due
    merchant_available = org_lifecycle.customer_actions_allowed(db, session.organization_id)
    if merchant_available and not is_expired and session.status not in (
        CheckoutSessionStatus.EXPIRED,
        CheckoutSessionStatus.SUCCESSFUL,
        CheckoutSessionStatus.CANCELLED,
    ):
        gateway_order_id, gateway_key_id, gateway_customer_id = _ensure_gateway_order(db, session)
        pending = db.get(Payment, (session.metadata_snapshot or {}).get("pending_payment_id") or "") if gateway_order_id else None
        if pending is not None:
            amount = pending.amount

    gateway_available = bool(gateway_order_id and gateway_key_id)
    gateway_message = None
    if not gateway_available and D(amount) > 0 and session.status not in (CheckoutSessionStatus.SUCCESSFUL,) and not is_expired:
        gateway_message = (
            org_lifecycle.CUSTOMER_UNAVAILABLE_MESSAGE
            if not merchant_available
            else "Online payment is currently unavailable for this link. Please contact the merchant to complete your payment."
        )

    return PublicCheckoutView(
        token=token,
        purpose=session.purpose.value,
        status=session.status.value,
        amount=amount,
        currency=session.currency,
        expires_at=session.expires_at,
        is_expired=is_expired,
        customer_name=session.customer.display_name if session.customer else None,
        customer_email=session.customer.email if session.customer else None,
        item_description=desc_text,
        organization_name=org.name if org else "Rooman Billing",
        branding=branding,
        save_payment_method_default=portal_settings.save_payment_method_default if portal_settings else True,
        allow_save_payment_methods=bool(session.save_payment_method) and (portal_settings.allow_save_payment_methods if portal_settings else True),
        prevent_deselecting_save_payment=portal_settings.prevent_deselecting_save_payment if portal_settings else False,
        gateway="razorpay",
        gateway_order_id=gateway_order_id,
        gateway_key_id=gateway_key_id,
        gateway_customer_id=gateway_customer_id,
        gateway_available=gateway_available,
        gateway_message=gateway_message,
    )


def _record_failed_attempt(db: Session, session: CheckoutSession, amount: Decimal, currency: str, reason: str, category: str) -> None:
    """Persist a failed attempt (committed, so it survives the error response)."""
    if session.invoice_id and session.customer_id:
        db.add(
            PaymentAttempt(
                organization_id=session.organization_id,
                invoice_id=session.invoice_id,
                customer_id=session.customer_id,
                gateway=PaymentGateway.RAZORPAY,
                amount=amount,
                currency=currency,
                status=PaymentAttemptStatus.FAILED,
                failure_reason=reason[:500],
                failure_category=category,
            )
        )
    session.status = CheckoutSessionStatus.FAILED
    db.flush()
    db.commit()


def _redirect_for(session: CheckoutSession) -> Optional[str]:
    if session.template and session.template.redirect_url and _is_safe_redirect_url(session.template.redirect_url):
        return session.template.redirect_url
    return None


def confirm_checkout_payment(
    db: Session,
    token: str,
    data: CheckoutConfirmIn,
) -> CheckoutConfirmOut:
    """Settle a hosted checkout from the browser's Razorpay handler.

    Public and unauthenticated, so nothing the browser says is trusted: the order id
    must be the one this session created, the signature must verify with the
    organization's key, and the payment fetched from Razorpay must be captured for
    that order and exactly the ordered amount. The manual gateway and vaulted-token
    charging are never available here.
    """
    session = _lookup_session(db, token)
    if not session:
        raise NotFoundAppError("Checkout session not found.")
    session = _lock_session(db, session)

    if session.status == CheckoutSessionStatus.SUCCESSFUL:
        return CheckoutConfirmOut(
            status="successful",
            message="Payment has already been successfully recorded for this session.",
            payment_id=session.payment_id,
            invoice_id=session.invoice_id,
            subscription_id=session.subscription_id,
            redirect_url=_redirect_for(session),
        )
    if session.status == CheckoutSessionStatus.PROCESSING:
        raise ConflictAppError("A payment confirmation is currently processing for this checkout session.")

    if (data.gateway or "razorpay").strip().lower() != "razorpay" or data.gateway_token:
        raise BadRequestAppError(
            "This checkout only accepts payments completed through the online payment gateway.",
            {"fields": {"gateway": "unsupported"}},
        )

    meta = dict(session.metadata_snapshot or {})
    expected_order_id = meta.get("gateway_order_id")
    charge_currency = session.currency
    charge_amount = D(session.amount)

    if not (data.razorpay_payment_id and data.razorpay_order_id and data.razorpay_signature):
        expires_at = session.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at < utcnow():
            session.status = CheckoutSessionStatus.EXPIRED
            db.flush()
            raise ValidationAppError("This checkout session has expired.")
        raise ValidationAppError(
            "Payment confirmation requires verified gateway credentials (razorpay_payment_id, razorpay_order_id, razorpay_signature)."
        )

    if not expected_order_id or data.razorpay_order_id != expected_order_id:
        _record_failed_attempt(db, session, charge_amount, charge_currency, "Gateway order ID mismatch with checkout session.", "authentication_failed")
        raise ValidationAppError("Gateway order ID does not match this checkout session.")

    creds = razorpay_gateway.credentials_for(db, session.organization_id)
    adapter = get_gateway_adapter(PaymentGateway.RAZORPAY)
    try:
        is_valid = adapter.verify_payment_signature(
            payment_id=data.razorpay_payment_id,
            order_id=data.razorpay_order_id,
            signature=data.razorpay_signature,
            credentials=creds,
        )
    except TypeError:  # adapters (e.g. test doubles) without per-organization credential support
        is_valid = adapter.verify_payment_signature(
            payment_id=data.razorpay_payment_id,
            order_id=data.razorpay_order_id,
            signature=data.razorpay_signature,
        )
    if not is_valid:
        _record_failed_attempt(db, session, charge_amount, charge_currency, "Cryptographic signature verification failed.", "authentication_failed")
        raise ValidationAppError("Cryptographic signature verification failed for gateway payment.")

    payment = db.get(Payment, meta.get("pending_payment_id") or "") if meta.get("pending_payment_id") else None
    if payment is None:
        payment = payment_service.find_by_order_id(db, expected_order_id, session.organization_id)
    if payment is None:
        raise ValidationAppError("No pending payment is linked to this checkout session.")
    payment = payment_service.lock_payment(db, payment)

    if payment.status not in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED):
        # A valid signature only proves Razorpay issued (order, payment). Ask Razorpay
        # whether that payment was actually captured, for this order and amount.
        fetched = razorpay_gateway.fetch_payment(data.razorpay_payment_id, creds=creds)
        problem = razorpay_gateway.verify_fetched_payment(
            fetched,
            expected_order_id=expected_order_id,
            expected_amount_paise=payment_service.to_paise(payment.amount),
            expected_currency=payment.currency,
        )
        if problem:
            _record_failed_attempt(db, session, D(payment.amount), payment.currency, f"Gateway verification failed: {problem}", "verification_failed")
            raise ValidationAppError(f"Payment could not be verified with the gateway: {problem}.")
        session.status = CheckoutSessionStatus.PROCESSING
        db.flush()
        invoice = session.invoice if session.purpose == CheckoutSessionPurpose.INVOICE_PAYMENT else None
        payment_service.capture_gateway_payment(
            db,
            payment,
            invoice,
            gateway_payment_id=data.razorpay_payment_id,
            payload={
                "source": "hosted_checkout",
                "razorpay_order_id": expected_order_id,
                "razorpay_payment_id": data.razorpay_payment_id,
                "gateway_status": fetched.get("status"),
            },
            signature_verified=True,
            actor_label=audit.CUSTOMER_ACTOR,
            lock=False,
        )
    else:
        fetched = dict(((payment.gateway_payload or {}).get("capture") or {}).get("entity") or {})

    _fulfill_session(db, session, payment, fetched, creds=creds, actor_label=audit.CUSTOMER_ACTOR)
    return CheckoutConfirmOut(
        status="successful",
        message="Checkout completed successfully.",
        payment_id=session.payment_id,
        invoice_id=session.invoice_id,
        subscription_id=session.subscription_id,
        redirect_url=_redirect_for(session),
    )


def complete_session_from_capture(db: Session, payment: Payment, entity: Dict[str, Any]) -> Optional[CheckoutSession]:
    """Webhook path: payment.captured arrived for a checkout order. Idempotent. No commit."""
    notes = dict((payment.gateway_payload or {}).get("notes") or {})
    session_id = notes.get("checkout_session_id")
    if not session_id:
        return None
    session = db.scalars(
        select(CheckoutSession).where(
            CheckoutSession.id == session_id, CheckoutSession.organization_id == payment.organization_id
        )
    ).first()
    if session is None:
        return None
    session = _lock_session(db, session)
    creds = razorpay_gateway.credentials_for(db, session.organization_id)
    _fulfill_session(db, session, payment, entity, creds=creds, actor_label=audit.WEBHOOK_ACTOR)
    return session


def _fulfill_session(
    db: Session,
    session: CheckoutSession,
    payment: Payment,
    gateway_entity: Dict[str, Any],
    *,
    creds,
    actor_label: str,
) -> None:
    """Deliver what the customer paid for, exactly once per session (caller holds the row lock).

    - invoice_payment: the capture already allocated the payment to the invoice.
    - new_subscription / one_time_addon: issue the GST tax invoice from the priced
      snapshot (numbered at issue), allocate the payment to it, and for a new
      subscription create the subscription on the plan's terms.
    Then optionally save the card (only real gateway token + card details) and
    mark the session successful.
    """
    if session.status == CheckoutSessionStatus.SUCCESSFUL:
        return
    meta = dict(session.metadata_snapshot or {})
    now = utcnow()
    invoice: Optional[Invoice] = session.invoice if session.purpose == CheckoutSessionPurpose.INVOICE_PAYMENT else None
    sub_id = session.subscription_id

    if session.purpose in (CheckoutSessionPurpose.NEW_SUBSCRIPTION, CheckoutSessionPurpose.ONE_TIME_ADDON):
        customer = session.customer or db.get(Customer, session.customer_id)
        if customer is None:
            raise ValidationAppError("Checkout session has no customer to invoice.")
        pricing = meta.get("pricing") or {}
        lines = _lines_from_snapshot(pricing)
        if not lines:
            raise ValidationAppError("Checkout session has no priced items to invoice.")
        subscription = None
        period_start = period_end = None
        if session.purpose == CheckoutSessionPurpose.NEW_SUBSCRIPTION:
            plan = session.plan or db.get(Plan, session.plan_id)
            if plan is None:
                raise ValidationAppError("The plan for this checkout no longer exists.")
            today = timezones.org_today_for_id(db, session.organization_id)
            period_start = today
            period_end = period_end_for(today, plan, today.day)
            subscription = Subscription(
                organization_id=session.organization_id,
                subscription_number=next_number(db, session.organization_id, "subscription"),
                customer_id=customer.id,
                plan_id=plan.id,
                quantity=1,
                status=SubscriptionStatus.ACTIVE,
                currency=plan.currency or session.currency,
                start_date=today,
                current_period_start=today,
                current_period_end=period_end,
                next_billing_date=period_end,
            )
            subscription.customer = customer
            db.add(subscription)
            db.flush()
            apply_plan_terms(db, subscription, plan, 1)
            sub_id = subscription.id
        invoice = invoice_service.create_invoice_record(
            db,
            organization_id=session.organization_id,
            customer=customer,
            lines=lines,
            currency=session.currency,
            subscription_id=sub_id,
            period_start=period_start,
            period_end=period_end,
            status=InvoiceStatus.SENT,
            notes=f"Paid via hosted checkout ({session.purpose.value}).",
        )
        audit.record(
            db,
            action="INVOICE_CREATED",
            entity_type="invoice",
            entity_id=invoice.id,
            entity_label=invoice.invoice_number,
            organization_id=session.organization_id,
            actor_label=actor_label,
            after=invoice_service.snapshot(invoice),
        )
        payment_service.allocate_captured_payment(db, payment, invoice, actor_label=actor_label)
        if subscription is not None:
            db.add(
                OutboxEvent(
                    organization_id=session.organization_id,
                    event_type=DomainEventType.SUBSCRIPTION_CREATED,
                    aggregate_type="subscription",
                    aggregate_id=subscription.id,
                    payload={"subscription_id": subscription.id, "plan_id": subscription.plan_id, "payment_id": payment.id, "invoice_id": invoice.id},
                    status=OutboxStatus.PENDING,
                )
            )

    attempt = None
    if invoice is not None and session.customer_id:
        attempt = PaymentAttempt(
            organization_id=session.organization_id,
            invoice_id=invoice.id,
            customer_id=session.customer_id,
            payment_id=payment.id,
            gateway=PaymentGateway.RAZORPAY,
            amount=payment.amount,
            currency=payment.currency,
            status=PaymentAttemptStatus.SUCCEEDED,
            gateway_attempt_reference=payment.gateway_payment_id,
            payload={"source": actor_label, "gateway_status": gateway_entity.get("status")},
        )
        db.add(attempt)
        db.flush()
        session.payment_attempt_id = attempt.id

    if session.save_payment_method and session.customer_id:
        pm = _save_payment_method(db, session, payment, gateway_entity, creds=creds)
        if pm is not None and attempt is not None:
            attempt.customer_payment_method_id = pm.id

    session.status = CheckoutSessionStatus.SUCCESSFUL
    session.payment_id = payment.id
    session.subscription_id = sub_id
    session.invoice_id = invoice.id if invoice is not None else session.invoice_id
    session.completed_at = now
    meta["fulfilled"] = True
    session.metadata_snapshot = meta
    db.flush()


def _save_payment_method(
    db: Session,
    session: CheckoutSession,
    payment: Payment,
    entity: Dict[str, Any],
    *,
    creds,
) -> Optional[CustomerPaymentMethod]:
    """Vault the card only when Razorpay actually issued a reusable token for a known
    Razorpay customer. Card network/last4/expiry come from Razorpay, never the browser;
    without a real token nothing is saved."""
    if not entity and payment.gateway_payment_id:
        try:
            entity = razorpay_gateway.fetch_payment(payment.gateway_payment_id, creds=creds)
        except Exception:
            entity = {}
    token_id = entity.get("token_id")
    gateway_customer_id = entity.get("customer_id") or (session.metadata_snapshot or {}).get("gateway_customer_id")
    if not token_id or not gateway_customer_id or (entity.get("method") or "card") != "card":
        return None
    existing = db.scalars(
        select(CustomerPaymentMethod).where(
            CustomerPaymentMethod.organization_id == session.organization_id,
            CustomerPaymentMethod.customer_id == session.customer_id,
            CustomerPaymentMethod.gateway_token == token_id,
        )
    ).first()
    if existing is not None:
        return existing
    card = entity.get("card") if isinstance(entity.get("card"), dict) else {}
    if not card and payment.gateway_payment_id:
        card = razorpay_gateway.fetch_card(payment.gateway_payment_id, creds=creds)
    last4 = str(card.get("last4") or "")[-4:] or None
    for other in db.scalars(
        select(CustomerPaymentMethod).where(
            CustomerPaymentMethod.organization_id == session.organization_id,
            CustomerPaymentMethod.customer_id == session.customer_id,
            CustomerPaymentMethod.is_default.is_(True),
        )
    ).all():
        other.is_default = False
    pm = CustomerPaymentMethod(
        organization_id=session.organization_id,
        customer_id=session.customer_id,
        gateway=PaymentGateway.RAZORPAY,
        gateway_customer_id=gateway_customer_id,
        gateway_token=token_id,
        type="card",
        card_brand=(card.get("network") or None),
        last4=last4,
        exp_month=int(card["expiry_month"]) if str(card.get("expiry_month") or "").isdigit() else None,
        exp_year=int(card["expiry_year"]) if str(card.get("expiry_year") or "").isdigit() else None,
        is_default=True,
        status=CustomerPaymentMethodStatus.ACTIVE,
    )
    db.add(pm)
    db.flush()
    return pm
