"""Customer Portal service: settings, authentication, session tokens, and self-service views."""
from __future__ import annotations

import hashlib
import hmac
import html
import logging
import secrets
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from backend.app.api.deps import CurrentContext
from backend.app.core.config import settings
from backend.app.core.exceptions import ConflictAppError, NotFoundAppError, UnauthorizedError, ValidationAppError
from backend.app.core.security import hash_password, validate_password_strength, verify_password
from backend.app.models.base import utcnow
from backend.app.models.customers import Customer, CustomerContact
from backend.app.models.identity import Organization, User
from backend.app.models.invoices import OPEN_INVOICE_STATUSES, Invoice, InvoiceStatus
from backend.app.models.payments import CustomerPaymentMethod, CustomerPaymentMethodStatus
from backend.app.models.portal import (
    CustomerPortalInvitation,
    CustomerPortalSession,
    CustomerPortalSettings,
    CustomerPortalUser,
)
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.schemas.portal import (
    CustomerPortalAccessStatusOut,
    CustomerPortalInvitationOut,
    CustomerPortalSettingsOut,
    CustomerPortalSettingsUpdate,
    PortalActivateIn,
    PortalDashboardOut,
    PortalInvitationValidateOut,
    PortalLoginIn,
    PortalSignupIn,
    PortalUserOut,
)
from backend.app.services import audit
from backend.app.services.email import resolve_smtp_config, send_email


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes for DateTime(timezone=True); treat them as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


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
        allow_self_signup=False,
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
    # Portal MFA is not implemented; the flag is not user-settable so it cannot imply protection.
    updates.pop("mfa_enabled", None)
    for key, value in updates.items():
        setattr(settings, key, value)
    settings.updated_at = utcnow()
    db.flush()
    return settings


def portal_signup(db: Session, data: PortalSignupIn) -> CustomerPortalUser:
    """Customer portal open/self sign-up is disabled. Access is by invitation only."""
    raise ValidationAppError("Self sign-up is disabled. Access to the Customer Portal is by invitation only.")


def portal_login(db: Session, data: PortalLoginIn) -> Tuple[str, CustomerPortalUser]:
    """Authenticates a customer portal user and creates an active session."""
    email_clean = data.email.strip().lower()
    if data.organization_id and data.organization_id.strip():
        user = db.scalars(
            select(CustomerPortalUser)
            .options(joinedload(CustomerPortalUser.customer))
            .where(
                CustomerPortalUser.organization_id == data.organization_id.strip(),
                CustomerPortalUser.email == email_clean,
            )
        ).first()
    else:
        users = list(
            db.scalars(
                select(CustomerPortalUser)
                .options(joinedload(CustomerPortalUser.customer))
                .where(
                    CustomerPortalUser.email == email_clean,
                )
            ).all()
        )
        if len(users) > 1:
            raise ValidationAppError("Multiple accounts found for this email. Please specify Organization ID.")
        user = users[0] if users else None

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


def serialize_portal_invitation(
    inv: CustomerPortalInvitation,
    raw_token: Optional[str] = None,
) -> CustomerPortalInvitationOut:
    status_str = "pending"
    now = utcnow()
    if inv.revoked_at:
        status_str = "revoked"
    elif inv.accepted_at:
        status_str = "accepted"
    elif inv.expires_at and aware(inv.expires_at) <= now:
        status_str = "expired"

    invite_url = None
    if raw_token:
        invite_url = f"{settings.FRONTEND_URL.rstrip('/')}/portal/activate?token={raw_token}"

    invited_by_name = inv.invited_by.full_name if inv.invited_by else None

    return CustomerPortalInvitationOut(
        id=inv.id,
        customer_id=inv.customer_id,
        email=inv.email,
        expires_at=inv.expires_at,
        created_at=inv.created_at,
        invited_by_name=invited_by_name,
        invite_url=invite_url,
        status=status_str,
    )


def get_customer_portal_access(
    db: Session,
    organization_id: str,
    customer_id: str,
) -> CustomerPortalAccessStatusOut:
    customer = db.scalars(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.organization_id == organization_id,
        )
    ).first()
    if not customer:
        raise NotFoundAppError("Customer not found.")

    user = db.scalars(
        select(CustomerPortalUser).where(
            CustomerPortalUser.organization_id == organization_id,
            CustomerPortalUser.customer_id == customer_id,
        )
    ).first()

    latest_invitation = db.scalars(
        select(CustomerPortalInvitation)
        .options(joinedload(CustomerPortalInvitation.invited_by))
        .where(
            CustomerPortalInvitation.organization_id == organization_id,
            CustomerPortalInvitation.customer_id == customer_id,
        )
        .order_by(desc(CustomerPortalInvitation.created_at))
    ).first()

    portal_base_url = f"{settings.FRONTEND_URL.rstrip('/')}/portal"

    user_out = PortalUserOut.model_validate(user) if user else None
    inv_out = serialize_portal_invitation(latest_invitation) if latest_invitation else None

    now = utcnow()
    if user:
        status = "active" if user.is_active else "revoked"
    elif latest_invitation:
        if latest_invitation.revoked_at:
            status = "revoked"
        elif latest_invitation.accepted_at:
            status = "active"
        elif latest_invitation.expires_at and aware(latest_invitation.expires_at) > now:
            status = "invitation_pending"
        else:
            status = "not_invited"
    else:
        status = "not_invited"

    return CustomerPortalAccessStatusOut(
        status=status,
        user=user_out,
        invitation=inv_out,
        portal_url=portal_base_url,
    )


def _send_portal_invitation_email(
    db: Session,
    organization_id: str,
    target_email: str,
    invite_url: str,
    org_name: str,
    inviter_name: Optional[str],
) -> bool:
    """Sends the activation email via the organization's SMTP settings.

    Synchronous on purpose: the admin UI shows the activation link as a fallback when this
    returns False. User-controlled values are HTML-escaped in the HTML part.
    """
    inviter = inviter_name or org_name
    e_inviter, e_org, e_url = html.escape(inviter), html.escape(org_name), html.escape(invite_url, quote=True)
    try:
        return send_email(
            to=target_email,
            subject=f"Access your Customer Billing Portal at {org_name}",
            text_body=(
                "Hello,\n\n"
                f"You have been invited by {inviter} ({org_name}) to access your Customer Billing Portal.\n\n"
                f"Set up your password and access your portal here:\n{invite_url}\n\n"
                "This link is secure and will expire in 48 hours.\n"
            ),
            html_body=(
                "<p>Hello,</p>"
                f"<p>You have been invited by <strong>{e_inviter}</strong> ({e_org}) to access your Customer Billing Portal.</p>"
                f'<p><a href="{e_url}" style="display:inline-block;background:#4f46e5;color:#ffffff;padding:10px 20px;text-decoration:none;border-radius:6px;">Activate Portal Account</a></p>'
                f"<p>Or copy this link: <br><code>{e_url}</code></p>"
                "<p>This link is secure and will expire in 48 hours.</p>"
            ),
            smtp_config=resolve_smtp_config(db, organization_id),
        )
    except Exception as exc:  # delivery problems must not lose the invitation
        logger.error("Portal invitation email to %s failed: %s", target_email, exc)
        return False


def portal_trial_extension_denial(db: Session, subscription: Subscription) -> Optional[str]:
    """Enforces the portal trial settings for customer self-service extensions.

    Returns a human-readable reason when the extension is not allowed, else None.
    """
    portal_settings = get_or_create_portal_settings(db, subscription.organization_id)
    if not portal_settings.trials_allow_customer_extension:
        return "Self-service trial extensions are disabled for this portal."
    from backend.app.models.trials import TrialPeriod

    tp = db.scalars(
        select(TrialPeriod).where(
            TrialPeriod.organization_id == subscription.organization_id,
            TrialPeriod.subscription_id == subscription.id,
        )
    ).first()
    used = tp.extension_count if tp else 0
    if used >= (portal_settings.trials_max_extensions or 0):
        return f"Maximum self-service trial extensions ({portal_settings.trials_max_extensions}) reached."
    return None


def maybe_auto_invite_customer(db: Session, ctx: CurrentContext, customer: Customer) -> Optional[CustomerPortalInvitationOut]:
    """Sends a portal invitation for a newly created customer when the portal's
    ``auto_invite_enabled`` setting is on and the customer has an email address.

    Call from customer creation (customer_service) after the customer row is flushed.
    Never raises: auto-invite problems must not block customer creation.
    """
    try:
        portal_settings = get_or_create_portal_settings(db, ctx.organization_id)
        if not portal_settings.auto_invite_enabled or not (customer.email or "").strip():
            return None
        return create_customer_portal_invitation(db, ctx, customer.id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Auto portal invite for customer %s failed: %s", customer.id, exc)
        return None


def create_customer_portal_invitation(
    db: Session,
    ctx: CurrentContext,
    customer_id: str,
    email: Optional[str] = None,
) -> CustomerPortalInvitationOut:
    customer = db.scalars(
        select(Customer)
        .options(joinedload(Customer.contacts))
        .where(
            Customer.id == customer_id,
            Customer.organization_id == ctx.organization_id,
        )
    ).first()
    if not customer:
        raise NotFoundAppError("Customer not found.")

    target_email = email.strip().lower() if email and email.strip() else None
    if not target_email:
        if customer.email:
            target_email = customer.email.strip().lower()
        elif customer.contacts:
            primary_contact = next((c for c in customer.contacts if c.is_primary and c.email), None)
            if primary_contact and primary_contact.email:
                target_email = primary_contact.email.strip().lower()
            else:
                first_contact = next((c for c in customer.contacts if c.email), None)
                if first_contact and first_contact.email:
                    target_email = first_contact.email.strip().lower()

    if not target_email:
        raise ValidationAppError("Customer does not have an email address configured. Please add an email to the customer or contacts before inviting.")

    # Invalidate existing active invitations for this customer
    pending_invites = list(
        db.scalars(
            select(CustomerPortalInvitation).where(
                CustomerPortalInvitation.organization_id == ctx.organization_id,
                CustomerPortalInvitation.customer_id == customer_id,
                CustomerPortalInvitation.accepted_at.is_(None),
                CustomerPortalInvitation.revoked_at.is_(None),
            )
        ).all()
    )
    for old_inv in pending_invites:
        old_inv.revoked_at = utcnow()

    # Generate secure random token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = utcnow() + timedelta(hours=48)

    invitation = CustomerPortalInvitation(
        organization_id=ctx.organization_id,
        customer_id=customer_id,
        email=target_email,
        token_hash=token_hash,
        expires_at=expires_at,
        invited_by_id=ctx.user.id,
    )
    db.add(invitation)
    db.flush()

    invite_url = f"{settings.FRONTEND_URL.rstrip('/')}/portal/activate?token={raw_token}"
    org_name = ctx.organization.name if ctx.organization else "our organization"

    _send_portal_invitation_email(db, ctx.organization_id, target_email, invite_url, org_name, ctx.user.full_name)

    audit.record(
        db,
        ctx=ctx,
        action="CUSTOMER_PORTAL_INVITED",
        entity_type="customer",
        entity_id=customer_id,
        entity_label=customer.display_name,
        after={
            "email": target_email,
            "expires_at": expires_at.isoformat(),
        },
    )

    return serialize_portal_invitation(invitation, raw_token=raw_token)


def revoke_customer_portal_access(
    db: Session,
    ctx: CurrentContext,
    customer_id: str,
) -> CustomerPortalAccessStatusOut:
    customer = db.scalars(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.organization_id == ctx.organization_id,
        )
    ).first()
    if not customer:
        raise NotFoundAppError("Customer not found.")

    # 1. Revoke pending invitations
    pending_invites = list(
        db.scalars(
            select(CustomerPortalInvitation).where(
                CustomerPortalInvitation.organization_id == ctx.organization_id,
                CustomerPortalInvitation.customer_id == customer_id,
                CustomerPortalInvitation.accepted_at.is_(None),
                CustomerPortalInvitation.revoked_at.is_(None),
            )
        ).all()
    )
    for inv in pending_invites:
        inv.revoked_at = utcnow()

    # 2. Deactivate customer portal user and revoke sessions
    users = list(
        db.scalars(
            select(CustomerPortalUser).where(
                CustomerPortalUser.organization_id == ctx.organization_id,
                CustomerPortalUser.customer_id == customer_id,
            )
        ).all()
    )
    for user in users:
        user.is_active = False
        db.query(CustomerPortalSession).filter(
            CustomerPortalSession.portal_user_id == user.id
        ).update({"is_revoked": True}, synchronize_session=False)

    audit.record(
        db,
        ctx=ctx,
        action="CUSTOMER_PORTAL_REVOKED",
        entity_type="customer",
        entity_id=customer_id,
        entity_label=customer.display_name,
    )

    return get_customer_portal_access(db, ctx.organization_id, customer_id)


def reactivate_customer_portal_access(
    db: Session,
    ctx: CurrentContext,
    customer_id: str,
) -> CustomerPortalAccessStatusOut:
    customer = db.scalars(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.organization_id == ctx.organization_id,
        )
    ).first()
    if not customer:
        raise NotFoundAppError("Customer not found.")

    users = list(
        db.scalars(
            select(CustomerPortalUser).where(
                CustomerPortalUser.organization_id == ctx.organization_id,
                CustomerPortalUser.customer_id == customer_id,
            )
        ).all()
    )
    if users:
        for user in users:
            user.is_active = True
    else:
        create_customer_portal_invitation(db, ctx, customer_id)

    audit.record(
        db,
        ctx=ctx,
        action="CUSTOMER_PORTAL_REACTIVATED",
        entity_type="customer",
        entity_id=customer_id,
        entity_label=customer.display_name,
    )

    return get_customer_portal_access(db, ctx.organization_id, customer_id)


def validate_portal_invitation_token(
    db: Session,
    raw_token: str,
) -> PortalInvitationValidateOut:
    if not raw_token or not raw_token.strip():
        raise ValidationAppError("Activation token is required.")

    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    inv = db.scalars(
        select(CustomerPortalInvitation)
        .options(joinedload(CustomerPortalInvitation.customer))
        .where(
            CustomerPortalInvitation.token_hash == token_hash,
        )
    ).first()

    if not inv:
        raise NotFoundAppError("Invalid or unknown activation link.")

    if inv.revoked_at:
        raise ValidationAppError("This invitation link has been revoked. Please contact your account administrator for a new link.")

    if inv.accepted_at:
        raise ValidationAppError("This invitation has already been used. Please log in with your credentials.")

    now = utcnow()
    if inv.expires_at and aware(inv.expires_at) <= now:
        raise ValidationAppError("This activation link has expired. Please contact your account administrator for a new link.")

    org = db.get(Organization, inv.organization_id)
    portal_settings = get_or_create_portal_settings(db, inv.organization_id)

    return PortalInvitationValidateOut(
        valid=True,
        email=inv.email,
        customer_id=inv.customer_id,
        customer_name=inv.customer.display_name if inv.customer else "",
        organization_id=inv.organization_id,
        organization_name=org.name if org else "",
        portal_name=portal_settings.portal_name,
        expires_at=inv.expires_at,
    )


def activate_portal_account(
    db: Session,
    raw_token: str,
    password: str,
    display_name: Optional[str] = None,
) -> Tuple[str, CustomerPortalUser]:
    password_problem = validate_password_strength(password)
    if password_problem:
        raise ValidationAppError(password_problem)

    if not raw_token or not raw_token.strip():
        raise ValidationAppError("Activation token is required.")

    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    inv = db.scalars(
        select(CustomerPortalInvitation)
        .options(joinedload(CustomerPortalInvitation.customer))
        .where(
            CustomerPortalInvitation.token_hash == token_hash,
        )
    ).first()

    if not inv:
        raise NotFoundAppError("Invalid or unknown activation link.")

    if inv.revoked_at:
        raise ValidationAppError("This invitation link has been revoked.")

    if inv.accepted_at:
        raise ValidationAppError("This invitation has already been used. Please log in.")

    now = utcnow()
    if inv.expires_at and aware(inv.expires_at) <= now:
        raise ValidationAppError("This activation link has expired.")

    user = db.scalars(
        select(CustomerPortalUser).where(
            CustomerPortalUser.organization_id == inv.organization_id,
            CustomerPortalUser.email == inv.email.lower(),
        )
    ).first()

    chosen_display_name = (
        display_name.strip() if display_name and display_name.strip()
        else (user.display_name if user else (inv.customer.display_name if inv.customer else inv.email))
    )

    if user:
        user.password_hash = hash_password(password)
        user.is_active = True
        user.display_name = chosen_display_name
        user.customer_id = inv.customer_id
    else:
        user = CustomerPortalUser(
            organization_id=inv.organization_id,
            customer_id=inv.customer_id,
            email=inv.email.lower(),
            password_hash=hash_password(password),
            display_name=chosen_display_name,
            is_active=True,
            mfa_enabled=False,
        )
        db.add(user)
        db.flush()

    inv.accepted_at = now

    other_pending = list(
        db.scalars(
            select(CustomerPortalInvitation).where(
                CustomerPortalInvitation.organization_id == inv.organization_id,
                CustomerPortalInvitation.customer_id == inv.customer_id,
                CustomerPortalInvitation.email == inv.email.lower(),
                CustomerPortalInvitation.accepted_at.is_(None),
                CustomerPortalInvitation.revoked_at.is_(None),
                CustomerPortalInvitation.id != inv.id,
            )
        ).all()
    )
    for other in other_pending:
        other.revoked_at = now

    raw_session_token = secrets.token_urlsafe(32)
    session = CustomerPortalSession(
        portal_user_id=user.id,
        token=_hash_token(raw_session_token),
        expires_at=now + timedelta(days=7),
        is_revoked=False,
    )
    db.add(session)
    user.last_login_at = now
    db.flush()

    return raw_session_token, user


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
                Invoice.status != InvoiceStatus.DRAFT,  # drafts are never customer-visible
            )
            .order_by(desc(Invoice.issue_date))
        ).all()
    )
    open_invoices = [inv for inv in invoices if inv.status in OPEN_INVOICE_STATUSES]
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

