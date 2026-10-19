"""Platform organization directory and lifecycle (docs/platform-administration-design.md, 8/9/14).

Metadata only. Nothing here reads or returns tenant financial or customer data: no amounts,
customer names, invoices, payments or integration credentials. The directory shows directory data
(name, slug, status, dates, member COUNTS, owner contact email on the detail page) and the
lifecycle state. Counts that help a lifecycle decision (for example how many subscriptions have a
renewal waiting) are counts, never the records.

Lifecycle transitions (reason required everywhere; a ticket where the design requires one):

    suspend            ACTIVE                -> SUSPENDED          Administrator, Operations; ticket
    reactivate         SUSPENDED             -> ACTIVE             Administrator, Operations
    schedule_deletion  ACTIVE | SUSPENDED    -> PENDING_DELETION   Administrator; ticket
    cancel_deletion    PENDING_DELETION      -> SUSPENDED          Administrator

DELETED is never reached here: the purge is a later, separately approved step. Reactivation sets
the status back to ACTIVE but KEEPS jobs_paused set, so renewals that fell due while suspended
are not replayed automatically; a Platform Administrator resumes automation explicitly
(resume_jobs) once the tenant has been contacted. Suspension itself acts through the Phase 1
scheduler safeguards (services/org_lifecycle.py): nothing money-moving runs for a non-ACTIVE or
paused organization. Every change, and every refused attempt, writes a platform audit row.
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from backend.app.core.logging import logger
from backend.app.core.tenant_context import tenant_context
from backend.app.models import (
    CreditNote,
    Customer,
    Invoice,
    Membership,
    MemberRole,
    MembershipStatus,
    Organization,
    OrganizationStatus,
    Payment,
    Quote,
    RefreshToken,
    Subscription,
    SubscriptionStatus,
    User,
)
from backend.app.models.portal import CustomerPortalSession, CustomerPortalUser
from backend.app.models.base import utcnow
from backend.app.models.platform import PlatformAuditLog, PlatformRole, PlatformStaff
from backend.app.services import org_access, org_lifecycle, platform_audit
from backend.app.services.email import frontend_url, send_email

ADMIN = PlatformRole.PLATFORM_ADMINISTRATOR
OPS = PlatformRole.PLATFORM_OPERATIONS
LIFECYCLE_ROLES: FrozenSet[PlatformRole] = frozenset({ADMIN, OPS})
ADMINISTRATOR_ONLY: FrozenSet[PlatformRole] = frozenset({ADMIN})

MAX_PAGE_SIZE = 100
SORTS = {"name", "created_at", "updated_at", "status"}


@dataclass(frozen=True)
class Transition:
    action: str
    sources: FrozenSet[OrganizationStatus]
    target: OrganizationStatus
    roles: FrozenSet[PlatformRole]
    needs_ticket: bool
    audit_action: str


TRANSITIONS: Dict[str, Transition] = {
    t.action: t
    for t in (
        Transition("approve", frozenset({OrganizationStatus.PENDING_APPROVAL}), OrganizationStatus.ACTIVE,
                   ADMINISTRATOR_ONLY, False, platform_audit.ORGANIZATION_APPROVED),
        Transition("reject", frozenset({OrganizationStatus.PENDING_APPROVAL}), OrganizationStatus.REJECTED,
                   ADMINISTRATOR_ONLY, False, platform_audit.ORGANIZATION_REJECTED),
        Transition("suspend", frozenset({OrganizationStatus.ACTIVE}), OrganizationStatus.SUSPENDED,
                   LIFECYCLE_ROLES, True, platform_audit.ORGANIZATION_SUSPENDED),
        Transition("reactivate", frozenset({OrganizationStatus.SUSPENDED}), OrganizationStatus.ACTIVE,
                   LIFECYCLE_ROLES, False, platform_audit.ORGANIZATION_REACTIVATED),
        Transition("schedule_deletion", frozenset({OrganizationStatus.ACTIVE, OrganizationStatus.SUSPENDED}),
                   OrganizationStatus.PENDING_DELETION, ADMINISTRATOR_ONLY, True,
                   platform_audit.ORGANIZATION_DELETION_SCHEDULED),
        Transition("cancel_deletion", frozenset({OrganizationStatus.PENDING_DELETION}), OrganizationStatus.SUSPENDED,
                   ADMINISTRATOR_ONLY, False, platform_audit.ORGANIZATION_DELETION_CANCELLED),
    )
}
JOB_ACTIONS = {"pause_jobs": platform_audit.TENANT_JOBS_PAUSED, "resume_jobs": platform_audit.TENANT_JOBS_RESUMED}
# Platform audit actions that make up an organization's lifecycle history.
LIFECYCLE_EVENTS = (
    platform_audit.ORGANIZATION_CREATED, platform_audit.ORGANIZATION_CREATED_PENDING_APPROVAL,
    platform_audit.ORGANIZATION_APPROVED, platform_audit.ORGANIZATION_REJECTED,
    platform_audit.ORGANIZATION_SUSPENDED, platform_audit.ORGANIZATION_REACTIVATED,
    platform_audit.ORGANIZATION_DELETION_SCHEDULED, platform_audit.ORGANIZATION_DELETION_CANCELLED,
    platform_audit.ORGANIZATION_LIFECYCLE_REFUSED, platform_audit.TENANT_JOBS_PAUSED,
    platform_audit.TENANT_JOBS_RESUMED, platform_audit.TENANT_SESSIONS_REVOKED,
    platform_audit.TENANT_ADMIN_DEACTIVATED, platform_audit.TENANT_ADMIN_REACTIVATED,
    platform_audit.TENANT_ADMIN_SESSIONS_REVOKED,
    platform_audit.ORGANIZATION_TRIAL_STARTED, platform_audit.ORGANIZATION_TRIAL_EXPIRED,
    platform_audit.SUBSCRIPTION_REQUEST_SUBMITTED, platform_audit.SUBSCRIPTION_REQUEST_WITHDRAWN,
    platform_audit.SUBSCRIPTION_REQUEST_APPROVED, platform_audit.SUBSCRIPTION_REQUEST_REJECTED,
    platform_audit.ORGANIZATION_ENTITLEMENTS_UPDATED, platform_audit.SUBSCRIPTION_REQUEST_APPROVED_WITH_CHANGES,
    platform_audit.TENANT_ADMIN_PROVISIONING_INITIATED, platform_audit.TENANT_ADMIN_PROVISIONED,
    platform_audit.TENANT_ADMIN_INVITATION_SENT, platform_audit.TENANT_ADMIN_ACTIVATED,
)
# Document COUNTS shown on the detail page (design section 4: counts, never records or amounts).
DOCUMENT_COUNTS = (
    ("customer_count", Customer), ("quote_count", Quote), ("invoice_count", Invoice),
    ("credit_note_count", CreditNote), ("payment_count", Payment), ("subscription_count", Subscription),
)


@dataclass
class Actor:
    """The acting platform staff member and request metadata (from PlatformContext)."""

    staff: PlatformStaff
    session_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]

    @property
    def role(self) -> PlatformRole:
        return self.staff.role


@dataclass
class DirectoryPage:
    items: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int


@dataclass
class LifecycleResult:
    organization: Dict[str, Any]
    changed: Dict[str, Any] = field(default_factory=dict)


# --- reads ----------------------------------------------------------------------------------------------


def _member_counts():
    return (
        select(Membership.organization_id.label("oid"), func.count(Membership.id).label("members"))
        .where(Membership.status == MembershipStatus.ACTIVE)
        .group_by(Membership.organization_id)
        .subquery()
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _summary(org: Organization, members: int) -> Dict[str, Any]:
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        # The platform lifecycle status (an approved self-service organization in its trial is ACTIVE;
        # trial_ends_at / module_access tell the trial apart).
        "status": (org.status or OrganizationStatus.ACTIVE).value,
        "jobs_paused": bool(org.jobs_paused),
        "member_count": int(members or 0),
        "created_at": org.created_at,
        "updated_at": org.updated_at,
        "status_changed_at": org.status_changed_at,
        "deletion_scheduled_for": org.deletion_scheduled_for,
        "trial_ends_at": org.trial_ends_at,
        "seat_limit": org.seat_limit,
        "module_access": org.module_access or "unrestricted",
    }


def list_organizations(
    db: Session,
    *,
    q: Optional[str] = None,
    status: Optional[OrganizationStatus] = None,
    sort: str = "created_at",
    direction: str = "desc",
    page: int = 1,
    page_size: int = 25,
) -> DirectoryPage:
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    sort = sort if sort in SORTS else "created_at"
    counts = _member_counts()
    stmt = select(Organization, func.coalesce(counts.c.members, 0)).outerjoin(counts, counts.c.oid == Organization.id)
    count_stmt = select(func.count(Organization.id))
    filters = []
    if status is not None:
        filters.append(Organization.status == status)
    term = (q or "").strip()[:100]
    if term:
        like = f"%{_escape_like(term.lower())}%"
        filters.append(
            or_(
                func.lower(Organization.name).like(like, escape="\\"),
                func.lower(Organization.slug).like(like, escape="\\"),
                Organization.id == term,
            )
        )
    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)
    column = getattr(Organization, sort)
    ordered = column.asc() if direction == "asc" else column.desc()
    stmt = stmt.order_by(ordered, Organization.id.asc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).all()
    total = int(db.scalar(count_stmt) or 0)
    return DirectoryPage(items=[_summary(org, members) for org, members in rows], total=total, page=page,
                         page_size=page_size)


def _active_members(db: Session, organization_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(Membership.id)).where(
                Membership.organization_id == organization_id, Membership.status == MembershipStatus.ACTIVE
            )
        )
        or 0
    )


LOCK_TIMEOUT = "10s"
BUSY_MESSAGE = "Billing automation is working on this organization right now. Please try again in a moment."


def _get(db: Session, organization_id: str, *, lock: bool = False) -> Organization:
    stmt = select(Organization).where(Organization.id == organization_id)
    if lock:
        stmt = stmt.with_for_update()
        if db.get_bind().dialect.name == "postgresql":
            # A scheduler transaction may hold this row while it charges (org_lifecycle re-reads it
            # FOR NO KEY UPDATE). Wait for it - that is what makes a suspension take effect safely -
            # but not forever: a stuck wait becomes a clear "try again" instead of a hung request.
            db.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    try:
        org = db.scalars(stmt).first()
    except OperationalError as exc:
        orig = getattr(exc, "orig", None)
        code = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
        if code == "55P03" or "lock timeout" in str(exc).lower():  # lock_not_available
            db.rollback()
            raise ConflictError(BUSY_MESSAGE)
        raise
    if org is None:
        raise NotFoundError("Organization not found.")
    return org


def renewals_waiting(db: Session, organization_id: str) -> int:
    """How many ACTIVE subscriptions already have a renewal due (a count, never the records).
    These are what resuming automation would bill on the next scheduler run."""
    today = datetime.now(timezone.utc).date()
    # Scoped to this one organization so both the ORM filter and PostgreSQL RLS admit its rows
    # (platform requests carry no tenant context, which would otherwise fail closed to 0).
    with tenant_context(organization_id):
        return int(
            db.scalar(
                select(func.count(Subscription.id)).where(
                    Subscription.organization_id == organization_id,
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.next_billing_date.is_not(None),
                    Subscription.next_billing_date <= today,
                )
            )
            or 0
        )


AUTOMATION_LABELS = {
    "running": "Running",
    "paused": "Paused",
    "held_trial": "Held - trial (no approved subscription)",
}


def automation_state(org: Organization) -> Dict[str, Any]:
    """The effective billing-automation state, matching org_lifecycle.automation_allowed: an
    ACTIVE, unpaused organization still in its trial has its automation held."""
    if (org.status or OrganizationStatus.ACTIVE) != OrganizationStatus.ACTIVE or org.jobs_paused:
        state = "paused"
    elif org.module_access == org_lifecycle.TRIAL_ACCESS:
        state = "held_trial"
    else:
        state = "running"
    return {"automation_running": state == "running", "automation_state": state, "automation_label": AUTOMATION_LABELS[state]}


def allowed_actions(org: Organization, role: PlatformRole) -> List[str]:
    """What this role may do to this organization right now (the server re-checks every call)."""
    status = org.status or OrganizationStatus.ACTIVE
    actions = [t.action for t in TRANSITIONS.values() if status in t.sources and role in t.roles]
    if role in ADMINISTRATOR_ONLY and status not in (
        OrganizationStatus.DELETED,
        OrganizationStatus.REJECTED,
        OrganizationStatus.PENDING_APPROVAL,
    ):
        actions.append("resume_jobs" if org.jobs_paused else "pause_jobs")
    if role in LIFECYCLE_ROLES and status not in (OrganizationStatus.DELETED, OrganizationStatus.REJECTED):
        actions.append("revoke_sessions")
    return actions


def organization_detail(db: Session, organization_id: str, actor: Actor) -> Dict[str, Any]:
    org = _get(db, organization_id)
    counts = dict(
        db.execute(
            select(Membership.status, func.count(Membership.id))
            .where(Membership.organization_id == org.id)
            .group_by(Membership.status)
        ).all()
    )
    roles = dict(
        db.execute(
            select(Membership.role, func.count(Membership.id))
            .where(Membership.organization_id == org.id, Membership.status == MembershipStatus.ACTIVE)
            .group_by(Membership.role)
        ).all()
    )
    owners = db.execute(
        select(User.full_name, User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == org.id,
            Membership.status == MembershipStatus.ACTIVE,
            Membership.role == MemberRole.OWNER,
        )
        .order_by(User.email)
        .limit(10)
    ).all()
    two_factor = int(
        db.scalar(
            select(func.count(Membership.id))
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.organization_id == org.id,
                Membership.status == MembershipStatus.ACTIVE,
                User.totp_enabled_at.is_not(None),
            )
        )
        or 0
    )
    now = utcnow()
    live_sessions = int(
        db.scalar(
            select(func.count(RefreshToken.id)).where(
                RefreshToken.organization_id == org.id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
        or 0
    )
    # Counts only, scoped to this organization (ORM filter + RLS), never the records.
    with tenant_context(org.id):
        documents = {
            name: int(db.scalar(select(func.count(model.id)).where(model.organization_id == org.id)) or 0)
            for name, model in DOCUMENT_COUNTS
        }
    changed_by = db.get(PlatformStaff, org.status_changed_by_staff_id) if org.status_changed_by_staff_id else None
    active_members = int(counts.get(MembershipStatus.ACTIVE, 0))
    status = org.status or OrganizationStatus.ACTIVE
    detail = {
        **_summary(org, active_members),
        "country": org.country,
        "timezone": org.timezone,
        "owners": [{"full_name": name, "email": email} for name, email in owners],
        "members": {
            "active": active_members,
            "invited": int(counts.get(MembershipStatus.INVITED, 0)),
            "deactivated": int(counts.get(MembershipStatus.DEACTIVATED, 0)),
            "by_role": {role.value: int(roles.get(role, 0)) for role in MemberRole},
        },
        "documents": documents,
        "security": {
            "members_with_two_factor": two_factor,
            "active_members": active_members,
            "live_tenant_sessions": live_sessions,
        },
        "lifecycle": {
            "status": status.value,
            "status_changed_at": org.status_changed_at,
            "status_reason": org.status_reason,
            "status_changed_by": (
                {"id": changed_by.id, "full_name": changed_by.full_name, "email": changed_by.email}
                if changed_by is not None else None
            ),
            "deletion_scheduled_for": org.deletion_scheduled_for,
            "jobs_paused": bool(org.jobs_paused),
            **automation_state(org),
            "renewals_waiting": renewals_waiting(db, org.id),
        },
        "allowed_actions": allowed_actions(org, actor.role),
    }
    platform_audit.record(
        db, action=platform_audit.ORGANIZATION_VIEWED, result=platform_audit.SUCCESS, staff=actor.staff,
        session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent, organization=org,
    )
    db.commit()
    return detail


def organization_activity(
    db: Session, organization_id: str, *, page: int = 1, page_size: int = 25, lifecycle_only: bool = False
) -> Tuple[List[PlatformAuditLog], int]:
    """Platform audit rows about this organization (read-only; the table is append-only).
    `lifecycle_only` narrows it to the lifecycle history (transitions, refusals, pauses, revocations)."""
    _get(db, organization_id)
    return audit_page(db, organization_id=organization_id, page=page, page_size=page_size,
                      actions=LIFECYCLE_EVENTS if lifecycle_only else None)


def audit_page(
    db: Session,
    *,
    organization_id: Optional[str] = None,
    staff_id: Optional[str] = None,
    action: Optional[str] = None,
    result: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    q: Optional[str] = None,
    actions: Optional[Tuple[str, ...]] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[PlatformAuditLog], int]:
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    filters = []
    if actions:
        filters.append(PlatformAuditLog.action.in_(actions))
    if target_type:
        filters.append(PlatformAuditLog.target_type == target_type[:32])
    if target_id:
        filters.append(PlatformAuditLog.target_id == target_id[:36])
    term = (q or "").strip()[:100]
    if term:
        like = f"%{_escape_like(term.lower())}%"
        filters.append(or_(*(
            func.lower(column).like(like, escape="\\")
            for column in (PlatformAuditLog.action, PlatformAuditLog.staff_email_snapshot,
                           PlatformAuditLog.organization_name_snapshot, PlatformAuditLog.reason,
                           PlatformAuditLog.ticket_ref)
        )))
    if organization_id:
        filters.append(PlatformAuditLog.organization_id == organization_id)
    if staff_id:
        filters.append(PlatformAuditLog.platform_staff_id == staff_id)
    if action:
        filters.append(PlatformAuditLog.action == action[:64])
    if result:
        filters.append(PlatformAuditLog.result == result[:16])
    if since:
        filters.append(PlatformAuditLog.occurred_at >= since)
    if until:
        filters.append(PlatformAuditLog.occurred_at <= until)
    stmt = select(PlatformAuditLog)
    count_stmt = select(func.count(PlatformAuditLog.id))
    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)
    rows = db.scalars(
        stmt.order_by(PlatformAuditLog.occurred_at.desc(), PlatformAuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), int(db.scalar(count_stmt) or 0)


# --- lifecycle ------------------------------------------------------------------------------------------


def _clean(text: Optional[str]) -> str:
    return " ".join((text or "").split())


def _refuse(db: Session, org: Organization, actor: Actor, action: str, message: str, *, reason: str,
            ticket_ref: Optional[str], status_code: str = "conflict") -> None:
    platform_audit.record(
        db, action=platform_audit.ORGANIZATION_LIFECYCLE_REFUSED, result=platform_audit.DENIED, staff=actor.staff,
        session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent, organization=org,
        reason=reason or None, ticket_ref=ticket_ref or None,
        details={"attempted": action, "status": (org.status or OrganizationStatus.ACTIVE).value},
    )
    db.commit()
    if status_code == "forbidden":
        raise ForbiddenError(message)
    raise ConflictError(message, {"status": (org.status or OrganizationStatus.ACTIVE).value, "attempted": action})


def change_lifecycle(
    db: Session, organization_id: str, action: str, actor: Actor, *, reason: str, ticket_ref: Optional[str] = None
) -> LifecycleResult:
    transition = TRANSITIONS.get(action)
    if transition is None:
        raise NotFoundError("Unknown lifecycle action.")
    reason, ticket_ref = _clean(reason), _clean(ticket_ref) or None
    if action == "reject" and (not reason or len(reason) < 10):
        raise ConflictError("A mandatory reason (at least 10 characters) is required to reject an organization.")
    if action == "approve" and not reason:
        reason = "Approved by Platform Administrator"
    org = _get(db, organization_id, lock=True)
    if actor.role not in transition.roles:  # routes check this first; defence in depth
        _refuse(db, org, actor, action, "Your platform role does not allow this action.",
                reason=reason, ticket_ref=ticket_ref, status_code="forbidden")
    current = org.status or OrganizationStatus.ACTIVE
    if current not in transition.sources:
        _refuse(db, org, actor, action,
                f"Cannot {action.replace('_', ' ')} an organization that is {current.value.replace('_', ' ')}.",
                reason=reason, ticket_ref=ticket_ref)
    if transition.needs_ticket and not ticket_ref:
        raise ConflictError("A ticket reference is required for this action.")

    now = utcnow()
    before = {"status": current.value, "jobs_paused": bool(org.jobs_paused),
              "deletion_scheduled_for": org.deletion_scheduled_for.isoformat() if org.deletion_scheduled_for else None}
    org.status = transition.target
    org.status_changed_at = now
    org.status_changed_by_staff_id = actor.staff.id
    org.status_reason = reason[:500]
    extra: Dict[str, Any] = {}
    if action == "schedule_deletion":
        org.deletion_scheduled_for = now + timedelta(days=settings.PLATFORM_DELETION_WAITING_DAYS)
        extra["waiting_days"] = settings.PLATFORM_DELETION_WAITING_DAYS
    elif action == "cancel_deletion":
        org.deletion_scheduled_for = None
    elif action == "approve" and (org.module_access or "") == "trial" and org.trial_started_at is None:
        # Self-service organization: its free trial starts now, at approval (never at signup).
        org.trial_started_at = now
        org.trial_ends_at = now + timedelta(days=settings.ORGANIZATION_TRIAL_DAYS)
        extra["trial_started_at"] = org.trial_started_at.isoformat()
        extra["trial_ends_at"] = org.trial_ends_at.isoformat()
    elif action == "reactivate":
        # Keep billing automation paused: nothing that fell due while suspended is replayed
        # until a Platform Administrator resumes it (resume_jobs).
        org.jobs_paused = True
        extra["renewals_waiting"] = renewals_waiting(db, org.id)
    after = {"status": org.status.value, "jobs_paused": bool(org.jobs_paused),
             "deletion_scheduled_for": org.deletion_scheduled_for.isoformat() if org.deletion_scheduled_for else None}
    platform_audit.record(
        db, action=transition.audit_action, result=platform_audit.SUCCESS, staff=actor.staff,
        session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent, organization=org,
        reason=reason, ticket_ref=ticket_ref, details={"from": before, "to": after, **extra},
    )
    org_id, org_name = org.id, org.name
    if "trial_ends_at" in extra:
        platform_audit.record(
            db, action=platform_audit.ORGANIZATION_TRIAL_STARTED, result=platform_audit.SUCCESS, staff=actor.staff,
            session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent, organization=org,
            target_type="organization", target_id=org.id,
            details={"trial_started_at": extra["trial_started_at"], "trial_ends_at": extra["trial_ends_at"],
                     "trial_days": settings.ORGANIZATION_TRIAL_DAYS},
        )
    db.commit()
    if action == "approve":
        _notify_owners_approved(db, org_id, org_name)
    return LifecycleResult(organization=_summary(org, _active_members(db, org.id)), changed={"from": before, "to": after, **extra})


def _approval_email(owner_name: str, organization_name: str, login_url: str) -> Tuple[str, str, str]:
    """(subject, text, html) for the approval notice. Only a plain sign-in link: no credentials or tokens."""
    subject = "Your Rooman Billing organization has been approved"
    text_body = (
        f"Hello {owner_name},\n\n"
        f"Good news! Your organization \"{organization_name}\" has been approved and you can now access Rooman Billing.\n\n"
        "Use the password you created during registration to sign in:\n\n"
        f"{login_url}\n\n"
        "— Rooman Billing"
    )
    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
    .card {{ max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 32px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
    .header {{ text-align: center; margin-bottom: 24px; }}
    .title {{ font-size: 20px; font-weight: 700; color: #0f172a; margin: 0 0 8px 0; }}
    .subtitle {{ font-size: 14px; color: #64748b; margin: 0; }}
    .cta {{ text-align: center; margin: 32px 0; }}
    .button {{ display: inline-block; background: #4f46e5; color: #ffffff !important; text-decoration: none; font-weight: 600; padding: 12px 28px; border-radius: 8px; }}
    .footer {{ font-size: 12px; color: #94a3b8; text-align: center; margin-top: 32px; border-top: 1px solid #f1f5f9; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1 class="title">Your organization has been approved</h1>
      <p class="subtitle">Good news, {html.escape(owner_name)}!</p>
    </div>
    <p><strong>{html.escape(organization_name)}</strong> has been approved and you can now access Rooman Billing.</p>
    <p>Use the password you created during registration to sign in.</p>
    <div class="cta">
      <a class="button" href="{html.escape(login_url, quote=True)}">Sign in to Rooman Billing</a>
    </div>
    <div class="footer">
      &copy; Rooman Billing. All rights reserved.
    </div>
  </div>
</body>
</html>"""
    return subject, text_body, html_body


def _notify_owners_approved(db: Session, organization_id: str, organization_name: str) -> None:
    """Email the organization's active owner(s) after an approval has committed.

    Best-effort by design: the approval is already durable, so nothing here may raise or undo it.
    """
    try:
        owners = db.execute(
            select(User.full_name, User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == organization_id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.role == MemberRole.OWNER,
            )
            .order_by(User.email)
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not look up owners to notify of approval of organization %s: %s", organization_id, exc)
        return
    login_url = frontend_url("login")
    for full_name, email in owners:
        if not email:
            continue
        try:
            subject, text_body, html_body = _approval_email(full_name or email, organization_name, login_url)
            if not send_email(to=email, subject=subject, text_body=text_body, html_body=html_body):
                logger.warning("Approval email for organization %s was not sent to %s (SMTP disabled)", organization_id, email)
        except Exception as exc:  # noqa: BLE001 - smtplib / OSError / anything: approval stands
            logger.error("Approval email to %s for organization %s failed: %s", email, organization_id, exc)


def set_jobs_paused(
    db: Session, organization_id: str, action: str, actor: Actor, *, reason: str, ticket_ref: Optional[str] = None
) -> LifecycleResult:
    if action not in JOB_ACTIONS:
        raise NotFoundError("Unknown jobs action.")
    reason, ticket_ref = _clean(reason), _clean(ticket_ref) or None
    org = _get(db, organization_id, lock=True)
    if actor.role not in ADMINISTRATOR_ONLY:
        _refuse(db, org, actor, action, "Your platform role does not allow this action.",
                reason=reason, ticket_ref=ticket_ref, status_code="forbidden")
    pause = action == "pause_jobs"
    current = org.status or OrganizationStatus.ACTIVE
    if bool(org.jobs_paused) == pause:
        _refuse(db, org, actor, action,
                "Billing automation is already paused." if pause else "Billing automation is not paused.",
                reason=reason, ticket_ref=ticket_ref)
    if not pause and current != OrganizationStatus.ACTIVE:
        _refuse(db, org, actor, action, "Reactivate the organization before resuming its billing automation.",
                reason=reason, ticket_ref=ticket_ref)
    waiting = renewals_waiting(db, org.id)
    org.jobs_paused = pause
    platform_audit.record(
        db, action=JOB_ACTIONS[action], result=platform_audit.SUCCESS, staff=actor.staff,
        session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent, organization=org,
        reason=reason, ticket_ref=ticket_ref,
        details={"jobs_paused": pause, "status": current.value, "renewals_waiting": waiting},
    )
    db.commit()
    return LifecycleResult(organization=_summary(org, _active_members(db, org.id)), changed={"jobs_paused": pause, "renewals_waiting": waiting})


# --- tenant session revocation ------------------------------------------------------------------------


def revoke_tenant_sessions(
    db: Session, organization_id: str, actor: Actor, *, reason: str, ticket_ref: Optional[str] = None
) -> LifecycleResult:
    """Sign every tenant user and customer-portal user out of THIS organization.

    Refresh-token rows bound to the organization are revoked; access tokens bound to those rows die
    on their next request (api/deps.get_current_user checks the session row). Portal sessions of the
    organization's portal users are revoked. Other organizations the same users belong to are not
    touched. Tenant data, roles and passwords are unchanged.
    """
    reason, ticket_ref = _clean(reason), _clean(ticket_ref) or None
    org = _get(db, organization_id, lock=True)
    if actor.role not in LIFECYCLE_ROLES:
        _refuse(db, org, actor, "revoke_sessions", "Your platform role does not allow this action.",
                reason=reason, ticket_ref=ticket_ref, status_code="forbidden")
    now = utcnow()
    staff_sessions = db.execute(
        update(RefreshToken)
        .where(RefreshToken.organization_id == org.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    ).rowcount or 0
    portal_ids = select(CustomerPortalUser.id).where(CustomerPortalUser.organization_id == org.id)
    portal_sessions = db.execute(
        update(CustomerPortalSession)
        .where(CustomerPortalSession.portal_user_id.in_(portal_ids), CustomerPortalSession.is_revoked.is_(False))
        .values(is_revoked=True)
        .execution_options(synchronize_session=False)
    ).rowcount or 0
    changed = {"tenant_sessions_revoked": int(staff_sessions), "portal_sessions_revoked": int(portal_sessions)}
    platform_audit.record(
        db, action=platform_audit.TENANT_SESSIONS_REVOKED, result=platform_audit.SUCCESS, staff=actor.staff,
        session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent, organization=org,
        reason=reason, ticket_ref=ticket_ref, details=changed,
    )
    db.commit()
    return LifecycleResult(organization=_summary(org, _active_members(db, org.id)), changed=changed)


# --- tenant admin management -------------------------------------------------------------------------


def list_tenant_admins(db: Session, organization_id: str, actor: Actor) -> List[Dict[str, Any]]:
    """List Owner and Admin members of an organization with security/session metadata."""
    org = _get(db, organization_id)
    if actor.role not in ADMINISTRATOR_ONLY:
        raise ForbiddenError("Only Platform Administrator can administer tenant Admins.")

    now = utcnow()
    memberships = (
        db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.organization_id == org.id,
                Membership.role.in_([MemberRole.OWNER, MemberRole.ADMIN]),
            )
            .order_by(Membership.role.asc(), Membership.created_at.asc())
        )
        .all()
    )

    results = []
    for m, u in memberships:
        live_sessions = int(
            db.scalar(
                select(func.count(RefreshToken.id)).where(
                    RefreshToken.user_id == u.id,
                    RefreshToken.organization_id == org.id,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > now,
                )
            )
            or 0
        )
        results.append(
            {
                "membership_id": m.id,
                "user_id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "role": m.role.value,
                "status": m.status.value,
                "has_2fa": bool(u.totp_enabled_at),
                "live_sessions": live_sessions,
                "created_at": m.created_at,
                "last_login_at": u.last_login_at,
            }
        )
    return results


def deactivate_tenant_admin(
    db: Session,
    organization_id: str,
    user_id: str,
    actor: Actor,
    *,
    reason: str,
    ticket_ref: Optional[str] = None,
) -> Dict[str, Any]:
    if actor.role not in ADMINISTRATOR_ONLY:
        raise ForbiddenError("Only Platform Administrator can administer tenant Admins.")
    reason, ticket_ref = _clean(reason), _clean(ticket_ref) or None
    if not reason or len(reason) < 10:
        raise ConflictError("A reason of at least 10 characters is required.")

    org = _get(db, organization_id, lock=True)
    m = db.scalars(
        select(Membership).where(
            Membership.organization_id == org.id,
            Membership.user_id == user_id,
        )
    ).first()
    if m is None:
        raise NotFoundError("Member not found in this organization.")

    # OWNER PROTECTION: Owner cannot be deleted, deactivated, or downgraded
    if m.role == MemberRole.OWNER:
        raise ForbiddenError("The organization Owner cannot be deactivated or downgraded by Admin management.")
    if m.role != MemberRole.ADMIN:
        raise ConflictError("Target member is not a tenant Admin.")
    if m.status == MembershipStatus.DEACTIVATED:
        raise ConflictError("Tenant Admin is already deactivated.")

    m.status = MembershipStatus.DEACTIVATED
    u = db.get(User, user_id)
    now = utcnow()
    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.organization_id == org.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )

    platform_audit.record(
        db,
        action=platform_audit.TENANT_ADMIN_DEACTIVATED,
        result=platform_audit.SUCCESS,
        staff=actor.staff,
        session_id=actor.session_id,
        ip_address=actor.ip_address,
        user_agent=actor.user_agent,
        organization=org,
        target_type="user",
        target_id=user_id,
        reason=reason,
        ticket_ref=ticket_ref,
        details={
            "user_email": u.email if u else None,
            "user_name": u.full_name if u else None,
            "role": m.role.value,
        },
    )
    db.commit()
    return {"user_id": user_id, "action": "deactivate", "success": True, "message": f"Tenant Admin {u.email if u else user_id} deactivated."}


def reactivate_tenant_admin(
    db: Session,
    organization_id: str,
    user_id: str,
    actor: Actor,
    *,
    reason: str,
    ticket_ref: Optional[str] = None,
) -> Dict[str, Any]:
    if actor.role not in ADMINISTRATOR_ONLY:
        raise ForbiddenError("Only Platform Administrator can administer tenant Admins.")
    reason, ticket_ref = _clean(reason), _clean(ticket_ref) or None
    if not reason or len(reason) < 10:
        raise ConflictError("A reason of at least 10 characters is required.")

    org = _get(db, organization_id, lock=True)
    m = db.scalars(
        select(Membership).where(
            Membership.organization_id == org.id,
            Membership.user_id == user_id,
        )
    ).first()
    if m is None:
        raise NotFoundError("Member not found in this organization.")

    if m.role == MemberRole.OWNER:
        raise ForbiddenError("Cannot modify Owner via Admin management.")
    if m.role != MemberRole.ADMIN:
        raise ConflictError("Target member is not a tenant Admin.")
    if m.status == MembershipStatus.ACTIVE:
        raise ConflictError("Tenant Admin is already active.")
    # BUG-32: only a deactivated Admin can be reactivated. An invited Admin has not accepted the
    # invitation (the user may have no password yet), so activating them would skip acceptance.
    if m.status != MembershipStatus.DEACTIVATED:
        raise ConflictError("This Admin has not accepted the invitation yet; resend the invitation instead.")
    org_access.ensure_seat_available(db, org, already_counted=False)

    m.status = MembershipStatus.ACTIVE
    u = db.get(User, user_id)

    platform_audit.record(
        db,
        action=platform_audit.TENANT_ADMIN_REACTIVATED,
        result=platform_audit.SUCCESS,
        staff=actor.staff,
        session_id=actor.session_id,
        ip_address=actor.ip_address,
        user_agent=actor.user_agent,
        organization=org,
        target_type="user",
        target_id=user_id,
        reason=reason,
        ticket_ref=ticket_ref,
        details={
            "user_email": u.email if u else None,
            "user_name": u.full_name if u else None,
            "role": m.role.value,
        },
    )
    db.commit()
    return {"user_id": user_id, "action": "reactivate", "success": True, "message": f"Tenant Admin {u.email if u else user_id} reactivated."}


def revoke_tenant_admin_sessions(
    db: Session,
    organization_id: str,
    user_id: str,
    actor: Actor,
    *,
    reason: str,
    ticket_ref: Optional[str] = None,
) -> Dict[str, Any]:
    if actor.role not in ADMINISTRATOR_ONLY:
        raise ForbiddenError("Only Platform Administrator can administer tenant Admins.")
    reason, ticket_ref = _clean(reason), _clean(ticket_ref) or None
    if not reason or len(reason) < 10:
        raise ConflictError("A reason of at least 10 characters is required.")

    org = _get(db, organization_id, lock=True)
    m = db.scalars(
        select(Membership).where(
            Membership.organization_id == org.id,
            Membership.user_id == user_id,
        )
    ).first()
    if m is None:
        raise NotFoundError("Member not found in this organization.")

    if m.role == MemberRole.OWNER:
        raise ForbiddenError("Cannot revoke Owner sessions via Admin management.")
    if m.role != MemberRole.ADMIN:
        raise ConflictError("Target member is not a tenant Admin.")

    now = utcnow()
    revoked = db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.organization_id == org.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    ).rowcount or 0

    u = db.get(User, user_id)
    platform_audit.record(
        db,
        action=platform_audit.TENANT_ADMIN_SESSIONS_REVOKED,
        result=platform_audit.SUCCESS,
        staff=actor.staff,
        session_id=actor.session_id,
        ip_address=actor.ip_address,
        user_agent=actor.user_agent,
        organization=org,
        target_type="user",
        target_id=user_id,
        reason=reason,
        ticket_ref=ticket_ref,
        details={
            "user_email": u.email if u else None,
            "sessions_revoked": int(revoked),
        },
    )
    db.commit()
    return {"user_id": user_id, "action": "revoke_sessions", "success": True, "message": f"{revoked} sessions revoked for tenant Admin."}
