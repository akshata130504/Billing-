"""Customer Portal service: settings, authentication, session tokens, and self-service views."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from backend.app.core.config import settings
from backend.app.core.exceptions import ConflictAppError, NotFoundAppError, UnauthorizedError, ValidationAppError
from backend.app.core.security import hash_password, verify_password
from backend.app.models.base import utcnow
from backend.app.models.customers import Customer, CustomerContact
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.payments import CustomerPaymentMethod, CustomerPaymentMethodStatus
from backend.app.models.portal import (
    CustomerPortalSession,
    CustomerPortalSettings,
    CustomerPortalUser,
)
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.schemas.portal import (
    CustomerPortalSettingsOut,
    CustomerPortalSettingsUpdate,
    PortalDashboardOut,
    PortalLoginIn,
    PortalSignupIn,
)


def _hash_token(token: str) -> str:
    """Computes SHA-256 digest of a session token for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_signed_document_token(
    organization_id: str,
    customer_id: str,
    invoice_id: str,
    expires_in_seconds: int = 300,
) -> str:
    """Generates an HMAC-SHA256 signed short-lived token for temporary invoice download."""
    expires_at = int(datetime.now(timezone.utc).timestamp()) + expires_in_seconds
    data = f"{organization_id}:{customer_id}:{invoice_id}:{expires_at}"
    sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{data}:{sig}"


def verify_signed_document_token(token: str) -> Tuple[str, str, str]:
    """Verifies a signed document token, checking signature and expiration."""
    parts = token.split(":")
    if len(parts) != 5:
        raise ValidationAppError("Invalid signed document token format.")
    org_id, cust_id, inv_id, exp_str, sig = parts
    expected_data = f"{org_id}:{cust_id}:{inv_id}:{exp_str}"
    expected_sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), expected_data.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise UnauthorizedError("Invalid or forged document signature.")
    try:
        exp_ts = int(exp_str)
    except ValueError:
        raise ValidationAppError("Invalid expiration timestamp.")
    if exp_ts < int(datetime.now(timezone.utc).timestamp()):
        raise UnauthorizedError("Signed document link has expired.")
    return org_id, cust_id, inv_id
from backend.app.services import audit


def get_or_create_portal_settings(db: Session, organization_id: str) -> CustomerPortalSettings:
    """Retrieves existing portal settings or initializes default organization settings."""
    settings = db.scalars(
        select(CustomerPortalSettings).where(CustomerPortalSettings.organization_id == organization_id)
    ).first()
    if settings:
        return settings

    settings = CustomerPortalSettings(
        organization_id=organization_id,
        portal_name="Customer Billing Portal",
        portal_url_slug=f"portal-{organization_id[:8]}",
        auto_invite_enabled=False,
        mfa_enabled=False,
        prevent_duplicate_payments=True,
        allow_self_signup=True,
        allow_document_upload=True,
        allow_document_forwarding=True,
        allow_save_payment_methods=True,
        save_payment_method_default=True,
        prevent_deselecting_save_payment=False,
        enable_identity_verification_public_links=True,
        trials_allow_customer_extension=True,
        trials_max_extensions=2,
        trials_activate_immediately=True,
    )
    db.add(settings)
    db.flush()
    return settings


def update_portal_settings(
    db: Session,
    organization_id: str,
    data: CustomerPortalSettingsUpdate,
) -> CustomerPortalSettings:
    """Updates organizational customer portal settings."""
    settings = get_or_create_portal_settings(db, organization_id)
    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(settings, key, value)
    settings.updated_at = utcnow()
    db.flush()
    return settings


def portal_signup(db: Session, data: PortalSignupIn) -> CustomerPortalUser:
    """Registers a new customer portal user with verified customer link."""
    settings = get_or_create_portal_settings(db, data.organization_id)
    if not settings.allow_self_signup:
        raise ValidationAppError("Self sign-up is currently disabled for this customer portal.")

    existing = db.scalars(
        select(CustomerPortalUser).where(
            CustomerPortalUser.organization_id == data.organization_id,
            CustomerPortalUser.email == data.email.lower(),
        )
    ).first()
    if existing:
        raise ConflictAppError("An account with this email already exists in this portal.")

    customer: Optional[Customer] = None
    if data.customer_id:
        customer = db.scalars(
            select(Customer)
            .options(joinedload(Customer.contacts))
            .where(
                Customer.id == data.customer_id,
                Customer.organization_id == data.organization_id,
            )
        ).first()
        if not customer:
            raise NotFoundAppError("Customer account not found in this organization.")

        # Prevent arbitrary customer account takeover:
        # The signup email must match either the customer's email or one of their verified contacts
        contact_emails = {c.email.lower() for c in (customer.contacts or []) if c.email}
        customer_email = customer.email.lower() if customer.email else None
        if data.email.lower() != customer_email and data.email.lower() not in contact_emails:
            raise ValidationAppError(
                "Provided email does not match any registered email or contact for this customer."
            )
    else:
        # Match customer by verified primary email
        customer = db.scalars(
            select(Customer).where(
                Customer.organization_id == data.organization_id,
                Customer.email == data.email.lower(),
            )
        ).first()
        if not customer:
            # Check customer contacts in this organization
            contact = db.scalars(
                select(CustomerContact)
                .options(joinedload(CustomerContact.customer))
                .where(
                    CustomerContact.organization_id == data.organization_id,
                    CustomerContact.email == data.email.lower(),
                )
            ).first()
            if contact and contact.customer:
                customer = contact.customer
            else:
                raise ValidationAppError(
                    "No customer account matches this email in this organization. Please contact support."
                )

    user = CustomerPortalUser(
        organization_id=data.organization_id,
        customer_id=customer.id,
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        is_active=True,
        mfa_enabled=False,
    )
    db.add(user)
    db.flush()
    return user


def portal_login(db: Session, data: PortalLoginIn) -> Tuple[str, CustomerPortalUser]:
    """Authenticates a customer portal user and creates an active session."""
    user = db.scalars(
        select(CustomerPortalUser).where(
            CustomerPortalUser.organization_id == data.organization_id,
            CustomerPortalUser.email == data.email.lower(),
        )
    ).first()

    if not user or not verify_password(data.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password.")

    if not user.is_active:
        raise UnauthorizedError("This portal account is currently disabled.")

    raw_token = secrets.token_urlsafe(32)
    hashed_token = _hash_token(raw_token)
    session = CustomerPortalSession(
        portal_user_id=user.id,
        token=hashed_token,
        expires_at=utcnow() + timedelta(days=7),
        is_revoked=False,
    )
    db.add(session)

    user.last_login_at = utcnow()
    db.flush()
    return raw_token, user


def authenticate_portal_session(db: Session, token: str) -> CustomerPortalUser:
    """Validates session token and returns the authenticated customer portal user."""
    hashed_token = _hash_token(token)
    session = (
        db.scalars(
            select(CustomerPortalSession)
            .options(joinedload(CustomerPortalSession.user).joinedload(CustomerPortalUser.customer))
            .where(
                CustomerPortalSession.token.in_([hashed_token, token]),
                CustomerPortalSession.is_revoked.is_(False),
            )
        )
    ).first()

    if not session:
        raise UnauthorizedError("Invalid or expired portal session token.")

    expires_at = session.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and expires_at < utcnow():
        raise UnauthorizedError("Invalid or expired portal session token.")

    return session.user


def get_customer_dashboard(db: Session, portal_user: CustomerPortalUser) -> PortalDashboardOut:
    """Gathers customer billing summary: active subscriptions, invoices, and payment methods."""
    customer = portal_user.customer
    org_id = portal_user.organization_id
    settings = get_or_create_portal_settings(db, org_id)

    # Subscriptions scoped to tenant AND customer
    subs = list(
        db.scalars(
            select(Subscription)
            .options(joinedload(Subscription.plan))
            .where(
                Subscription.organization_id == org_id,
                Subscription.customer_id == customer.id,
            )
            .order_by(desc(Subscription.created_at))
        ).all()
    )
    active_subs_count = sum(1 for s in subs if s.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING))

    # Invoices scoped to tenant AND customer
    invoices = list(
        db.scalars(
            select(Invoice)
            .where(
                Invoice.organization_id == org_id,
                Invoice.customer_id == customer.id,
            )
            .order_by(desc(Invoice.issue_date))
        ).all()
    )
    open_invoices = [inv for inv in invoices if inv.status not in (InvoiceStatus.PAID, InvoiceStatus.VOID)]
    total_due = sum((inv.amount_due or Decimal("0.00")) for inv in open_invoices)

    # Payment methods scoped to tenant AND customer
    methods = list(
        db.scalars(
            select(CustomerPaymentMethod).where(
                CustomerPaymentMethod.organization_id == org_id,
                CustomerPaymentMethod.customer_id == customer.id,
                CustomerPaymentMethod.status == CustomerPaymentMethodStatus.ACTIVE,
            )
        ).all()
    )

    return PortalDashboardOut(
        portal_name=settings.portal_name,
        banner_message=settings.banner_message,
        customer_name=customer.display_name,
        customer_email=customer.email,
        active_subscriptions_count=active_subs_count,
        open_invoices_count=len(open_invoices),
        total_outstanding_amount=total_due,
        recent_invoices=[
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "issue_date": str(inv.issue_date),
                "due_date": str(inv.due_date),
                "total": str(inv.total),
                "amount_due": str(inv.amount_due),
                "status": inv.status.value,
                "public_token": inv.public_token,
            }
            for inv in invoices[:5]
        ],
        subscriptions=[
            {
                "id": s.id,
                "subscription_number": s.subscription_number,
                "plan_name": s.plan.name if s.plan else "",
                "status": s.status.value,
                "current_period_end": str(s.current_period_end),
                "trial_end": str(s.trial_end) if s.trial_end else None,
            }
            for s in subs
        ],
        saved_payment_methods=[
            {
                "id": m.id,
                "type": m.type,
                "card_brand": m.card_brand,
                "last4": m.last4,
                "is_default": m.is_default,
            }
            for m in methods
        ],
    )


def portal_logout(db: Session, token: str) -> None:
    """Revokes the given portal session token."""
    hashed_token = _hash_token(token)
    session = db.scalars(
        select(CustomerPortalSession).where(
            CustomerPortalSession.token.in_([hashed_token, token]),
        )
    ).first()
    if session:
        session.is_revoked = True
        db.flush()

