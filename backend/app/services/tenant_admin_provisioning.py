"""A Platform Administrator provisions an organization's Admin after its subscription is approved.

The Admin is a TENANT user: a users row (password-less until they accept) plus ONE membership with
role ADMIN in that organization. Nothing here reads or writes platform_staff, so provisioning can
never create a platform account. The person sets their own password through the normal invitation
link (auth_service.accept_invitation); no password or invitation token is ever returned to the
console. Seat limits apply. Every step is in the platform audit (initiated / provisioned / invitation
sent), and the organization's own audit log records the invitation.
"""
from __future__ import annotations

import html
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import ConflictError, ForbiddenError
from backend.app.core.logging import logger
from backend.app.core.security import generate_opaque_token, hash_token, invite_token_expiry
from backend.app.models import Membership, MemberRole, MembershipStatus, OrganizationStatus, User
from backend.app.models.platform import PlatformAuditLog
from backend.app.models.subscription_access import ModuleAccess
from backend.app.schemas.organization import normalize_email
from backend.app.services import audit, org_access, platform_audit
from backend.app.services.email import frontend_url, send_email
from backend.app.services.platform_org_service import ADMINISTRATOR_ONLY, Actor, _get


def was_provisioned(db: Session, membership_id: str) -> bool:
    """Whether this membership was created by platform Admin provisioning (for the activation audit)."""
    return db.scalar(
        select(PlatformAuditLog.id).where(
            PlatformAuditLog.action == platform_audit.TENANT_ADMIN_PROVISIONED,
            PlatformAuditLog.target_id == membership_id,
        ).limit(1)
    ) is not None


def provision_admin(db: Session, organization_id: str, actor: Actor, *, full_name: str, email: str) -> Dict[str, Any]:
    if actor.role not in ADMINISTRATOR_ONLY:  # the route checks this first; defence in depth
        raise ForbiddenError("Only a Platform Administrator can provision an organization's Admin.")
    email = normalize_email(email)
    full_name = " ".join((full_name or "").split())
    org = _get(db, organization_id, lock=True)

    def refuse(message: str) -> None:
        platform_audit.record(
            db, action=platform_audit.TENANT_ADMIN_PROVISIONING_INITIATED, result=platform_audit.DENIED,
            staff=actor.staff, session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent,
            organization=org, target_type="organization", target_id=org.id,
            details={"admin_email": email, "refused": message},
        )
        db.commit()
        raise ConflictError(message)

    if (org.status or OrganizationStatus.ACTIVE) != OrganizationStatus.ACTIVE:
        refuse(f"The organization is {org.status.value.replace('_', ' ')}; an Admin can be provisioned only for an active organization.")
    if (org.module_access or "") != ModuleAccess.ENTITLED.value:
        refuse("Approve the organization's subscription request before provisioning its Admin.")

    platform_audit.record(
        db, action=platform_audit.TENANT_ADMIN_PROVISIONING_INITIATED, result=platform_audit.SUCCESS,
        staff=actor.staff, session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent,
        organization=org, target_type="organization", target_id=org.id, details={"admin_email": email},
    )

    user = db.scalars(select(User).where(User.email == email)).first()
    membership = None
    if user is None:
        # Password-less until they accept the invitation (the same placeholder a tenant invitation makes).
        user = User(email=email, full_name=full_name, hashed_password=None)
        db.add(user)
        db.flush()
    else:
        membership = db.scalars(
            select(Membership).where(Membership.organization_id == org.id, Membership.user_id == user.id)
        ).first()
        if membership is not None and membership.status == MembershipStatus.ACTIVE:
            refuse("This person is already an active member of the organization.")
        if membership is not None and membership.role == MemberRole.OWNER:
            refuse("This person is the organization's Owner.")

    reinvited = membership is not None
    org_access.ensure_seat_available(
        db, org, already_counted=membership is not None and membership.status == MembershipStatus.INVITED
    )
    raw = generate_opaque_token()
    if membership is None:
        membership = Membership(organization_id=org.id, user_id=user.id)
        db.add(membership)
    membership.role = MemberRole.ADMIN
    membership.status = MembershipStatus.INVITED
    membership.invited_by_id = None  # invited by Rooman, not by a member of the organization
    membership.invite_token_hash = hash_token(raw)
    membership.invite_expires_at = invite_token_expiry()
    membership.accepted_at = None
    membership.deactivated_at = None
    db.flush()

    platform_audit.record(
        db, action=platform_audit.TENANT_ADMIN_PROVISIONED, result=platform_audit.SUCCESS, staff=actor.staff,
        session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent, organization=org,
        target_type="membership", target_id=membership.id,
        details={"admin_email": email, "admin_name": user.full_name, "user_id": user.id, "role": MemberRole.ADMIN.value,
                 "reinvited": reinvited},
    )
    audit.record(
        db, action="TEAM_MEMBER_INVITED", entity_type="membership", entity_id=membership.id, entity_label=email,
        organization_id=org.id, actor_label="Rooman",
        after={"email": email, "role": MemberRole.ADMIN.value, "status": MembershipStatus.INVITED.value,
               "provisioned_by": "platform"},
    )
    db.commit()

    # The invitation link is a credential: platform SMTP only, never returned to the console.
    link = frontend_url(f"accept-invitation?token={raw}")
    delivered = False
    try:
        delivered = send_email(
            email,
            f"Your Admin account for {org.name} on Rooman Billing",
            (f"Hello {user.full_name},\n\nRooman has set up an Admin account for you in {org.name} on Rooman Billing.\n"
             f"Set your password and sign in within {settings.INVITE_TOKEN_EXPIRE_HOURS} hours:\n\n{link}\n"),
            html_body=(f"<p>Hello {html.escape(user.full_name)},</p><p>Rooman has set up an Admin account for you in "
                       f"<strong>{html.escape(org.name)}</strong> on Rooman Billing.</p>"
                       f'<p><a href="{html.escape(link)}">Set your password and sign in</a> '
                       f"(valid for {settings.INVITE_TOKEN_EXPIRE_HOURS} hours)</p>"),
        )
    except Exception as exc:  # the account exists; provisioning again re-sends the invitation
        logger.error("Admin invitation email for organization %s failed: %s", org.id, type(exc).__name__)
    platform_audit.record(
        db, action=platform_audit.TENANT_ADMIN_INVITATION_SENT,
        result=platform_audit.SUCCESS if delivered else platform_audit.FAILURE, staff=actor.staff,
        session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent, organization=org,
        target_type="membership", target_id=membership.id, details={"admin_email": email, "delivered": delivered},
    )
    db.commit()
    return {
        "organization_id": org.id,
        "organization_name": org.name,
        "user_id": user.id,
        "membership_id": membership.id,
        "full_name": user.full_name,
        "email": email,
        "role": MemberRole.ADMIN.value,
        "status": MembershipStatus.INVITED.value,
        "invite_expires_at": membership.invite_expires_at,
        "email_delivered": delivered,
    }
