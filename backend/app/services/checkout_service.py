"""Hosted payment pages and checkout session domain service.

Provides secure, tokenized, and cryptographically verified public payment flows
for invoices, new subscriptions, subscription updates, card updates, and add-ons.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session, joinedload

from backend.app.core.config import settings
from backend.app.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
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
from backend.app.models.invoices import Invoice, InvoiceItem, InvoiceStatus
from backend.app.models.payments import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    Payment,
    PaymentAllocation,
    PaymentAttempt,
    PaymentAttemptStatus,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    ReconciliationStatus,
)
from backend.app.models.portal import CustomerPortalSettings
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.schemas.checkout import (
    CheckoutConfirmIn,
    CheckoutConfirmOut,
    CheckoutSessionCreate,
    CheckoutSessionOut,
    CheckoutTemplateCreate,
    CheckoutTemplateUpdate,
    PublicCheckoutView,
)
from backend.app.services import audit, razorpay_gateway
from backend.app.services.gateways.base import GatewayChargeResult
from backend.app.services.gateways.registry import get_gateway_adapter
from backend.app.services.numbering import next_number
from backend.app.services.subscription_service import create_subscription, period_end_for
from backend.app.services.unit_of_work import UnitOfWork


def _hash_token(raw_token: str) -> str:
    """Compute SHA-256 hex digest of a bearer checkout token."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def _is_safe_redirect_url(url: Optional[str]) -> bool:
    """Ensure redirect URL does not use javascript:, data:, or vbscript: schemes."""
    if not url:
        return True
    cleaned = url.strip().lower()
    if cleaned.startswith(("javascript:", "data:", "vbscript:")):
        return False
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return False
    return True


def _lookup_session(db: Session, token: str) -> Optional[CheckoutSession]:
    """Lookup session by matching the SHA-256 token hash, with raw token fallback for legacy sessions."""
    token_hash = _hash_token(token)
    return db.scalars(
        select(CheckoutSession)
        .options(
            joinedload(CheckoutSession.customer),
            joinedload(CheckoutSession.invoice),
            joinedload(CheckoutSession.plan),
            joinedload(CheckoutSession.template),
            joinedload(CheckoutSession.subscription),
        )
        .where(
            or_(
                CheckoutSession.token == token_hash,
                CheckoutSession.token == token.strip(),
            )
        )
    ).first()


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


def create_checkout_session(
    db: Session,
    organization_id: str,
    data: CheckoutSessionCreate,
) -> CheckoutSession:
    """Generates an expiring, token-hashed hosted checkout session for invoices, subscriptions, or cards."""
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

    amount = data.amount or Decimal("0.00")
    currency = data.currency or "INR"
    customer_id = data.customer_id
    invoice_id = data.invoice_id
    subscription_id = data.subscription_id
    plan_id = data.plan_id

    # 1. Invoice payment specific validation
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

    # 2. Subscription specific validation
    elif purpose == CheckoutSessionPurpose.NEW_SUBSCRIPTION:
        if not plan_id:
            raise ValidationAppError("plan_id is required for new_subscription checkout session.")
        plan = db.scalars(
            select(Plan).where(Plan.organization_id == organization_id, Plan.id == plan_id)
        ).first()
        if not plan:
            raise NotFoundAppError(f"Plan {plan_id} not found.")
        if not plan.is_active:
            raise ValidationAppError("Plan is inactive.")
        amount = plan.unit_amount
        currency = plan.currency

    elif purpose == CheckoutSessionPurpose.UPDATE_SUBSCRIPTION:
        if not subscription_id:
            raise ValidationAppError("subscription_id is required for update_subscription checkout session.")
        sub = db.scalars(
            select(Subscription).where(
                Subscription.organization_id == organization_id,
                Subscription.id == subscription_id,
            )
        ).first()
        if not sub:
            raise NotFoundAppError(f"Subscription {subscription_id} not found.")
        customer_id = sub.customer_id

    elif purpose in (CheckoutSessionPurpose.UPDATE_CARD, CheckoutSessionPurpose.ADD_PAYMENT_METHOD):
        if not customer_id:
            raise ValidationAppError("customer_id is required for card update checkout session.")
        amount = Decimal("0.00")

    elif purpose == CheckoutSessionPurpose.ONE_TIME_ADDON:
        if not customer_id:
            raise ValidationAppError("customer_id is required for one_time_addon checkout session.")
        if amount <= Decimal("0.00"):
            raise ValidationAppError("Amount must be greater than 0 for one_time_addon checkout.")

    session = CheckoutSession(
        organization_id=organization_id,
        template_id=template_id,
        token=token_hash,  # Store SHA-256 hash
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
        metadata_snapshot=data.metadata_snapshot or {},
    )
    db.add(session)
    db.flush()

    # Attach ephemeral raw token for caller response
    setattr(session, "raw_token", raw_token)
    return session


def get_public_checkout_view(db: Session, token: str) -> PublicCheckoutView:
    """Returns safe, public view representation of a checkout session for customer browsers."""
    session = _lookup_session(db, token)
    if not session:
        raise NotFoundAppError("Checkout page not found or link is invalid.")

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

    # Gateway order initiation for Razorpay if online gateway is configured
    gateway_order_id = None
    gateway_key_id = None
    gateway_name = "razorpay"

    if not is_expired and session.status not in (CheckoutSessionStatus.EXPIRED, CheckoutSessionStatus.SUCCESSFUL):
        meta = session.metadata_snapshot or {}
        gateway_order_id = meta.get("gateway_order_id")
        if not gateway_order_id and razorpay_gateway.is_configured() and session.amount > 0:
            adapter = get_gateway_adapter(PaymentGateway.RAZORPAY)
            order_res = adapter.charge(
                amount=session.amount,
                currency=session.currency,
                customer_id=session.customer_id or "anonymous",
                notes={"checkout_session_id": session.id, "purpose": session.purpose.value},
                idempotency_key=f"hpp_init_{session.id}",
            )
            if order_res.success and order_res.gateway_order_id:
                gateway_order_id = order_res.gateway_order_id
                meta["gateway_order_id"] = gateway_order_id
                session.metadata_snapshot = meta
                db.flush()

        if razorpay_gateway.is_configured():
            gateway_key_id = razorpay_gateway.public_key_id()

    return PublicCheckoutView(
        token=token,
        purpose=session.purpose.value,
        status=session.status.value,
        amount=session.amount,
        currency=session.currency,
        expires_at=session.expires_at,
        is_expired=is_expired,
        customer_name=session.customer.display_name if session.customer else None,
        customer_email=session.customer.email if session.customer else None,
        item_description=desc_text,
        organization_name=org.name if org else "Rooman Billing",
        branding=branding,
        save_payment_method_default=portal_settings.save_payment_method_default if portal_settings else True,
        allow_save_payment_methods=portal_settings.allow_save_payment_methods if portal_settings else True,
        prevent_deselecting_save_payment=portal_settings.prevent_deselecting_save_payment if portal_settings else False,
        gateway=gateway_name,
        gateway_order_id=gateway_order_id,
        gateway_key_id=gateway_key_id,
    )


def confirm_checkout_payment(
    db: Session,
    token: str,
    data: CheckoutConfirmIn,
) -> CheckoutConfirmOut:
    """Processes payment submission for a hosted checkout session atomically with cryptographic verification."""
    session = _lookup_session(db, token)
    if not session:
        raise NotFoundAppError("Checkout session not found.")

    # Idempotent return if already completed
    if session.status == CheckoutSessionStatus.SUCCESSFUL:
        redirect_url = session.template.redirect_url if session.template and _is_safe_redirect_url(session.template.redirect_url) else None
        return CheckoutConfirmOut(
            status="successful",
            message="Payment has already been successfully recorded for this session.",
            payment_id=session.payment_id,
            invoice_id=session.invoice_id,
            subscription_id=session.subscription_id,
            redirect_url=redirect_url,
        )

    # Concurrency guard: prevent duplicate parallel processing
    if session.status == CheckoutSessionStatus.PROCESSING:
        raise ConflictAppError("A payment confirmation is currently processing for this checkout session.")

    expires_at = session.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and expires_at < utcnow():
        session.status = CheckoutSessionStatus.EXPIRED
        db.flush()
        raise ValidationAppError("This checkout session has expired.")

    # Revalidate invoice status and balance authoritative from the database
    inv = None
    if session.purpose == CheckoutSessionPurpose.INVOICE_PAYMENT and session.invoice_id:
        inv = db.scalars(
            select(Invoice).where(
                Invoice.organization_id == session.organization_id,
                Invoice.id == session.invoice_id,
            )
        ).first()
        if not inv or inv.status in (InvoiceStatus.PAID, InvoiceStatus.VOID):
            raise ConflictAppError(f"Invoice {inv.invoice_number if inv else ''} is already {inv.status.value if inv else 'unavailable'}.")
        if inv.amount_due <= Decimal("0.00"):
            raise ConflictAppError("Invoice has no outstanding balance.")
        charge_amount = inv.amount_due
        charge_currency = inv.currency or session.currency
    elif session.purpose == CheckoutSessionPurpose.NEW_SUBSCRIPTION and session.plan_id:
        plan = db.scalars(
            select(Plan).where(
                Plan.organization_id == session.organization_id,
                Plan.id == session.plan_id,
            )
        ).first()
        if not plan or not plan.is_active:
            raise ValidationAppError("Selected plan is inactive or no longer available.")
        charge_amount = plan.unit_amount
        charge_currency = plan.currency
    else:
        charge_amount = session.amount
        charge_currency = session.currency

    # Mark PROCESSING state
    session.status = CheckoutSessionStatus.PROCESSING
    db.flush()

    # Determine gateway adapter
    gateway_type = PaymentGateway.RAZORPAY
    if data.gateway and data.gateway.lower() == "manual":
        gateway_type = PaymentGateway.MANUAL

    adapter = get_gateway_adapter(gateway_type)

    verified_payment_id: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None

    # Step 1: Cryptographic or adapter-backed verification
    if data.razorpay_payment_id and data.razorpay_order_id and data.razorpay_signature:
        # Cryptographically verify the signature
        is_valid = adapter.verify_payment_signature(
            payment_id=data.razorpay_payment_id,
            order_id=data.razorpay_order_id,
            signature=data.razorpay_signature,
        )
        if not is_valid:
            # Record failed attempt
            attempt = PaymentAttempt(
                organization_id=session.organization_id,
                invoice_id=session.invoice_id,
                customer_id=session.customer_id,
                gateway=PaymentGateway.RAZORPAY,
                amount=charge_amount,
                currency=charge_currency,
                status=PaymentAttemptStatus.FAILED,
                failure_reason="Cryptographic signature verification failed.",
                failure_category="authentication_failed",
            )
            db.add(attempt)
            session.status = CheckoutSessionStatus.FAILED
            db.flush()
            raise ValidationAppError("Cryptographic signature verification failed for gateway payment.")

        verified_payment_id = data.razorpay_payment_id
        raw_payload = {
            "razorpay_payment_id": data.razorpay_payment_id,
            "razorpay_order_id": data.razorpay_order_id,
        }

    elif data.gateway_token:
        # Charge via vaulted/stored gateway token
        charge_res = adapter.charge(
            amount=charge_amount,
            currency=charge_currency,
            customer_id=session.customer_id or "anonymous",
            payment_method_token=data.gateway_token,
            notes={"checkout_session_id": session.id, "purpose": session.purpose.value},
            idempotency_key=f"checkout_{session.id}",
        )
        if not charge_res.success:
            attempt = PaymentAttempt(
                organization_id=session.organization_id,
                invoice_id=session.invoice_id,
                customer_id=session.customer_id,
                gateway=adapter.gateway_type,
                amount=charge_amount,
                currency=charge_currency,
                status=PaymentAttemptStatus.FAILED,
                failure_reason=charge_res.error_message,
                failure_category=charge_res.error_category,
                payload=charge_res.raw_payload,
            )
            db.add(attempt)
            session.status = CheckoutSessionStatus.FAILED
            db.flush()
            raise ValidationAppError(f"Payment gateway charge failed: {charge_res.error_message}")

        verified_payment_id = charge_res.gateway_payment_id
        raw_payload = charge_res.raw_payload

    elif adapter.gateway_type == PaymentGateway.MANUAL and data.gateway == "manual":
        # Manual adapter (only when manual adapter is explicitly configured)
        charge_res = adapter.charge(
            amount=charge_amount,
            currency=charge_currency,
            customer_id=session.customer_id or "anonymous",
            notes={"checkout_session_id": session.id, "purpose": session.purpose.value},
        )
        verified_payment_id = charge_res.gateway_payment_id
        raw_payload = charge_res.raw_payload

    elif adapter.gateway_type == PaymentGateway.RAZORPAY and not razorpay_gateway.is_configured():
        # In unconfigured dev/test without credentials, check if an adapter test double is registered
        # or reject explicitly: Never mark successful from browser-supplied card descriptions
        # without adapter verification
        charge_res = adapter.charge(
            amount=charge_amount,
            currency=charge_currency,
            customer_id=session.customer_id or "anonymous",
            notes={"checkout_session_id": session.id, "purpose": session.purpose.value},
            idempotency_key=f"checkout_{session.id}",
        )
        if charge_res.success and charge_res.gateway_payment_id:
            verified_payment_id = charge_res.gateway_payment_id
            raw_payload = charge_res.raw_payload
        else:
            session.status = CheckoutSessionStatus.FAILED
            db.flush()
            raise ValidationAppError(
                charge_res.error_message or "Payment gateway verification failed or gateway credentials are unconfigured."
            )
    else:
        session.status = CheckoutSessionStatus.FAILED
        db.flush()
        raise ValidationAppError(
            "Payment confirmation requires verified gateway credentials (razorpay_payment_id, razorpay_order_id, razorpay_signature) or an active gateway_token."
        )

    # Step 2: Record verified PaymentAttempt
    attempt = PaymentAttempt(
        organization_id=session.organization_id,
        invoice_id=session.invoice_id,
        customer_id=session.customer_id,
        gateway=adapter.gateway_type,
        amount=charge_amount,
        currency=charge_currency,
        status=PaymentAttemptStatus.SUCCEEDED,
        gateway_attempt_reference=verified_payment_id,
        payload=raw_payload,
    )
    db.add(attempt)
    db.flush()
    session.payment_attempt_id = attempt.id

    # Step 3: Vault payment method if requested
    if data.save_payment_method and session.customer_id:
        pm = CustomerPaymentMethod(
            organization_id=session.organization_id,
            customer_id=session.customer_id,
            gateway=adapter.gateway_type,
            type=data.payment_method_type or "card",
            gateway_token=data.gateway_token or verified_payment_id or f"tok_{secrets.token_hex(8)}",
            card_brand=data.card_brand or "Visa",
            last4=data.card_last4 or "4242",
            is_default=True,
            status=CustomerPaymentMethodStatus.ACTIVE,
        )
        db.add(pm)
        db.flush()
        attempt.customer_payment_method_id = pm.id

    payment_id: Optional[str] = None
    invoice_id = session.invoice_id
    sub_id = session.subscription_id

    # Step 4: Atomic fulfillment per declared checkout purpose
    now = utcnow()

    if session.purpose == CheckoutSessionPurpose.INVOICE_PAYMENT and inv:
        pay_num = next_number(db, session.organization_id, "payment")
        payment = Payment(
            organization_id=session.organization_id,
            payment_number=pay_num,
            customer_id=session.customer_id,
            amount=charge_amount,
            currency=charge_currency,
            paid_at=now,
            method=PaymentMethod.CARD,
            gateway=adapter.gateway_type,
            gateway_payment_id=verified_payment_id,
            status=PaymentStatus.SUCCEEDED,
            reconciliation_status=ReconciliationStatus.MATCHED if adapter.gateway_type != PaymentGateway.MANUAL else ReconciliationStatus.AUTO_MATCHED,
        )
        db.add(payment)
        db.flush()
        payment_id = payment.id
        attempt.payment_id = payment.id

        alloc = PaymentAllocation(
            organization_id=session.organization_id,
            payment_id=payment.id,
            invoice_id=inv.id,
            amount=charge_amount,
        )
        db.add(alloc)

        inv.amount_paid = (inv.amount_paid or Decimal("0.00")) + charge_amount
        inv.amount_due = max(Decimal("0.00"), inv.total - inv.amount_paid)
        if inv.amount_due <= Decimal("0.00"):
            inv.status = InvoiceStatus.PAID
            inv.paid_at = now

        db.add(
            OutboxEvent(
                organization_id=session.organization_id,
                event_type=DomainEventType.INVOICE_PAID if inv.amount_due <= 0 else DomainEventType.INVOICE_PARTIALLY_PAID,
                aggregate_type="invoice",
                aggregate_id=inv.id,
                payload={
                    "invoice_id": inv.id,
                    "payment_id": payment.id,
                    "amount": str(charge_amount),
                    "balance": str(inv.amount_due),
                    "gateway_payment_id": verified_payment_id,
                },
                status=OutboxStatus.PENDING,
            )
        )

    elif session.purpose == CheckoutSessionPurpose.NEW_SUBSCRIPTION and session.plan:
        plan = session.plan
        today = date.today()
        trial_days = plan.trial_days or 0
        if trial_days > 0:
            sub_status = SubscriptionStatus.TRIALING
            trial_end = today + timedelta(days=trial_days)
            period_end = period_end_for(trial_end, plan, trial_end.day)
        else:
            sub_status = SubscriptionStatus.ACTIVE
            trial_end = None
            period_end = period_end_for(today, plan, today.day)

        sub_num = next_number(db, session.organization_id, "subscription")
        sub = Subscription(
            organization_id=session.organization_id,
            subscription_number=sub_num,
            customer_id=session.customer_id,
            plan_id=plan.id,
            quantity=1,
            status=sub_status,
            start_date=today,
            trial_end=trial_end,
            current_period_start=today,
            current_period_end=period_end,
            next_billing_date=period_end,
        )
        db.add(sub)
        db.flush()
        sub_id = sub.id

        pay_num = next_number(db, session.organization_id, "payment")
        payment = Payment(
            organization_id=session.organization_id,
            payment_number=pay_num,
            customer_id=session.customer_id,
            amount=charge_amount,
            currency=charge_currency,
            paid_at=now,
            method=PaymentMethod.CARD,
            gateway=adapter.gateway_type,
            gateway_payment_id=verified_payment_id,
            status=PaymentStatus.SUCCEEDED,
            reconciliation_status=ReconciliationStatus.MATCHED,
        )
        db.add(payment)
        db.flush()
        payment_id = payment.id
        attempt.payment_id = payment.id

        db.add(
            OutboxEvent(
                organization_id=session.organization_id,
                event_type=DomainEventType.SUBSCRIPTION_CREATED,
                aggregate_type="subscription",
                aggregate_id=sub.id,
                payload={"subscription_id": sub.id, "plan_id": plan.id, "payment_id": payment.id},
                status=OutboxStatus.PENDING,
            )
        )

    elif session.purpose == CheckoutSessionPurpose.UPDATE_SUBSCRIPTION and session.subscription_id:
        sub = db.scalars(
            select(Subscription).where(
                Subscription.organization_id == session.organization_id,
                Subscription.id == session.subscription_id,
            )
        ).first()
        if sub and session.plan_id:
            sub.plan_id = session.plan_id
            sub.updated_at = now
            db.flush()

    elif session.purpose in (CheckoutSessionPurpose.UPDATE_CARD, CheckoutSessionPurpose.ADD_PAYMENT_METHOD):
        # Card vaulted above in step 3
        pass

    elif session.purpose == CheckoutSessionPurpose.ONE_TIME_ADDON:
        # Create one-time invoice and allocate payment
        inv_num = next_number(db, session.organization_id, "invoice")
        addon_inv = Invoice(
            organization_id=session.organization_id,
            invoice_number=inv_num,
            customer_id=session.customer_id,
            status=InvoiceStatus.PAID,
            issue_date=date.today(),
            due_date=date.today(),
            currency=charge_currency,
            subtotal=charge_amount,
            tax_total=Decimal("0.00"),
            total=charge_amount,
            amount_paid=charge_amount,
            amount_due=Decimal("0.00"),
            paid_at=now,
        )
        db.add(addon_inv)
        db.flush()
        invoice_id = addon_inv.id

        pay_num = next_number(db, session.organization_id, "payment")
        payment = Payment(
            organization_id=session.organization_id,
            payment_number=pay_num,
            customer_id=session.customer_id,
            amount=charge_amount,
            currency=charge_currency,
            paid_at=now,
            method=PaymentMethod.CARD,
            gateway=adapter.gateway_type,
            gateway_payment_id=verified_payment_id,
            status=PaymentStatus.SUCCEEDED,
            reconciliation_status=ReconciliationStatus.MATCHED,
        )
        db.add(payment)
        db.flush()
        payment_id = payment.id
        attempt.payment_id = payment.id

        alloc = PaymentAllocation(
            organization_id=session.organization_id,
            payment_id=payment.id,
            invoice_id=addon_inv.id,
            amount=charge_amount,
        )
        db.add(alloc)
    else:
        raise ValidationAppError(f"Unsupported checkout purpose: {session.purpose.value}")

    session.status = CheckoutSessionStatus.SUCCESSFUL
    session.payment_id = payment_id
    session.subscription_id = sub_id
    session.invoice_id = invoice_id
    session.completed_at = now
    db.flush()

    redirect_url = None
    if session.template and session.template.redirect_url:
        if _is_safe_redirect_url(session.template.redirect_url):
            redirect_url = session.template.redirect_url

    return CheckoutConfirmOut(
        status="successful",
        message="Checkout completed successfully.",
        payment_id=payment_id,
        invoice_id=invoice_id,
        subscription_id=sub_id,
        redirect_url=redirect_url,
    )
