"""Trial organization -> subscription request -> Platform Administrator decision -> entitlements.

Tenant side (Owner/Admin of a trial or trial-expired organization): choose optional modules
(base modules are always included), seats and a billing cycle, and submit one request at a time.

Platform side (Administrator only, step-up enforced by the routes; Operations/Support read):
approve - as requested or modified - or reject with a reason. Approval makes the organization
ACTIVE, records its module entitlements and seat limit, and emails its Owners a sign-in link
(never a password). The existing Owner stays the organization's Owner: approval creates no user,
membership or platform staff account.

No money moves here and nothing reads or writes tenant financial data.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.entitlements import registry, with_requirements
from backend.app.core.exceptions import ConflictError, NotFoundError
from backend.app.core.logging import logger
from backend.app.core.tenant_context import system_context, tenant_context
from backend.app.models import Membership, MemberRole, MembershipStatus, Organization, OrganizationStatus, User
from backend.app.models.base import utcnow
from backend.app.models.subscription_access import (
    ModuleAccess,
    OrganizationEntitlement,
    SubscriptionRequest,
    SubscriptionRequestStatus,
)
from backend.app.services import audit, org_access, platform_audit
from backend.app.services.email import frontend_url, send_email
from backend.app.services.platform_org_service import Actor, MAX_PAGE_SIZE, _get as _get_org

# Effective statuses (org_access.effective_status): an approved organization in, or past, its trial.
# A PENDING_APPROVAL organization must first be approved itself (organization approval, stage 1).
REQUESTABLE_STATUSES = (OrganizationStatus.TRIAL, OrganizationStatus.TRIAL_EXPIRED)
APPROVABLE_STATUSES = REQUESTABLE_STATUSES


def module_catalog() -> List[Dict[str, Any]]:
    return [
        {"key": m.key, "label": m.label, "description": m.description, "base": m.base, "requires": list(m.requires)}
        for m in registry().modules
    ]


def _out(req: SubscriptionRequest) -> Dict[str, Any]:
    return {
        "id": req.id,
        "organization_id": req.organization_id,
        "status": req.status.value,
        "modules": list(req.modules or []),
        "seats": req.seats,
        "billing_cycle": req.billing_cycle.value,
        "notes": req.notes,
        "created_at": req.created_at,
        "reviewed_at": req.reviewed_at,
        "decision_reason": req.decision_reason,
        "approved_modules": list(req.approved_modules) if req.approved_modules is not None else None,
        "approved_seats": req.approved_seats,
        "approved_billing_cycle": req.approved_billing_cycle.value if req.approved_billing_cycle else None,
    }


def _normalise_modules(keys: Iterable[str]) -> List[str]:
    reg = registry()
    full = with_requirements(k for k in keys if k in reg.optional_keys)
    return [m.key for m in reg.modules if m.key in full and not m.base]


# --- tenant ------------------------------------------------------------------------------------


def tenant_state(db: Session, ctx: CurrentContext) -> Dict[str, Any]:
    org = ctx.organization
    with tenant_context(org.id):
        rows = db.scalars(
            select(SubscriptionRequest)
            .where(SubscriptionRequest.organization_id == org.id)
            .order_by(SubscriptionRequest.created_at.desc(), SubscriptionRequest.id)
            .limit(20)
        ).all()
    current = next((r for r in rows if r.status == SubscriptionRequestStatus.SUBMITTED), None)
    return {
        "access": org_access.access_summary(db, org),
        "modules": module_catalog(),
        "current_request": _out(current) if current else None,
        "history": [_out(r) for r in rows],
    }


def submit(db: Session, ctx: CurrentContext, *, modules: List[str], seats: int, billing_cycle: str,
           notes: Optional[str]) -> Dict[str, Any]:
    org = db.scalars(select(Organization).where(Organization.id == ctx.organization_id).with_for_update()).first()
    if org is None:
        raise NotFoundError("Organization not found.")
    status = org_access.effective_status(org)
    if status not in REQUESTABLE_STATUSES:
        raise ConflictError("A subscription can be requested only during or after the free trial.",
                            {"code": "SUBSCRIPTION_REQUEST_NOT_ALLOWED", "status": status.value})
    used = org_access.seats_used(db, org.id)
    if seats < used:
        raise ConflictError(
            f"Your organization already has {used} member(s) and invitation(s). Request at least {used} seats.",
            {"fields": {"seats": f"at least {used}"}},
        )
    with tenant_context(org.id):
        open_request = db.scalars(select(SubscriptionRequest.id).where(
            SubscriptionRequest.organization_id == org.id,
            SubscriptionRequest.status == SubscriptionRequestStatus.SUBMITTED,
        )).first()
        if open_request:
            raise ConflictError("A subscription request is already waiting for review. Withdraw it to change it.",
                                {"code": "SUBSCRIPTION_REQUEST_OPEN"})
        req = SubscriptionRequest(
            organization_id=org.id, status=SubscriptionRequestStatus.SUBMITTED, modules=_normalise_modules(modules),
            seats=seats, billing_cycle=billing_cycle, notes=notes, requested_by_user_id=ctx.user.id,
        )
        db.add(req)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise ConflictError("A subscription request is already waiting for review.",
                                {"code": "SUBSCRIPTION_REQUEST_OPEN"})
        summary = {"modules": req.modules, "seats": seats, "billing_cycle": billing_cycle}
        audit.record(db, action="SUBSCRIPTION_REQUEST_SUBMITTED", entity_type="subscription_request",
                     entity_id=req.id, entity_label=org.name, ctx=ctx, after=summary)
        platform_audit.record(
            db, action=platform_audit.SUBSCRIPTION_REQUEST_SUBMITTED, result=platform_audit.SUCCESS,
            ip_address=ctx.ip_address, user_agent=ctx.user_agent, organization=org,
            target_type="subscription_request", target_id=req.id, details={**summary, "requested_by": ctx.user.email},
        )
        db.commit()
        db.refresh(req)
        return _out(req)


def withdraw(db: Session, ctx: CurrentContext, request_id: str) -> Dict[str, Any]:
    with tenant_context(ctx.organization_id):
        req = db.scalars(select(SubscriptionRequest).where(
            SubscriptionRequest.id == request_id, SubscriptionRequest.organization_id == ctx.organization_id,
        ).with_for_update()).first()
        if req is None:
            raise NotFoundError("Subscription request not found.")
        if req.status != SubscriptionRequestStatus.SUBMITTED:
            raise ConflictError(f"This request is already {req.status.value}.")
        req.status = SubscriptionRequestStatus.WITHDRAWN
        audit.record(db, action="SUBSCRIPTION_REQUEST_WITHDRAWN", entity_type="subscription_request",
                     entity_id=req.id, entity_label=ctx.organization.name, ctx=ctx,
                     before={"status": "submitted"}, after={"status": "withdrawn"})
        platform_audit.record(
            db, action=platform_audit.SUBSCRIPTION_REQUEST_WITHDRAWN, result=platform_audit.SUCCESS,
            ip_address=ctx.ip_address, user_agent=ctx.user_agent, organization=ctx.organization,
            target_type="subscription_request", target_id=req.id,
        )
        db.commit()
        db.refresh(req)
        return _out(req)


# --- platform ----------------------------------------------------------------------------------


def _platform_out(db: Session, req: SubscriptionRequest, org: Organization,
                  requester: Optional[User]) -> Dict[str, Any]:
    return {
        **_out(req),
        "organization_name": org.name,
        "organization_slug": org.slug,
        "organization_status": org_access.effective_status(org).value,
        "trial_ends_at": org.trial_ends_at,
        "requested_by_email": requester.email if requester else None,
        "requested_by_name": requester.full_name if requester else None,
        "seats_used": org_access.seats_used(db, org.id),
    }


def list_requests(db: Session, *, status: Optional[str] = "submitted", page: int = 1,
                  page_size: int = 25) -> Dict[str, Any]:
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    with system_context():
        stmt = (select(SubscriptionRequest, Organization, User)
                .join(Organization, Organization.id == SubscriptionRequest.organization_id)
                .outerjoin(User, User.id == SubscriptionRequest.requested_by_user_id))
        count = select(func.count(SubscriptionRequest.id))
        if status:
            stmt = stmt.where(SubscriptionRequest.status == SubscriptionRequestStatus(status))
            count = count.where(SubscriptionRequest.status == SubscriptionRequestStatus(status))
        order = SubscriptionRequest.created_at.asc() if status == "submitted" else SubscriptionRequest.created_at.desc()
        rows = db.execute(stmt.order_by(order, SubscriptionRequest.id).offset((page - 1) * page_size).limit(page_size)).all()
        total = int(db.scalar(count) or 0)
        items = [_platform_out(db, req, org, user) for req, org, user in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def pending_count(db: Session) -> int:
    with system_context():
        return int(db.scalar(select(func.count(SubscriptionRequest.id)).where(
            SubscriptionRequest.status == SubscriptionRequestStatus.SUBMITTED)) or 0)


def _load(db: Session, request_id: str, *, lock: bool = False) -> Tuple[SubscriptionRequest, Organization]:
    with system_context():
        stmt = select(SubscriptionRequest).where(SubscriptionRequest.id == request_id)
        req = db.scalars(stmt.with_for_update() if lock else stmt).first()
        if req is None:
            raise NotFoundError("Subscription request not found.")
        org = _get_org(db, req.organization_id, lock=lock)
    return req, org


def request_detail(db: Session, request_id: str) -> Dict[str, Any]:
    req, org = _load(db, request_id)
    requester = db.get(User, req.requested_by_user_id) if req.requested_by_user_id else None
    return _platform_out(db, req, org, requester)


def _replace_entitlements(db: Session, org: Organization, modules: List[str], *, source: str,
                          staff_id: str, request_id: Optional[str] = None) -> None:
    with tenant_context(org.id):
        db.execute(delete(OrganizationEntitlement).where(OrganizationEntitlement.organization_id == org.id))
        for key in modules:
            db.add(OrganizationEntitlement(organization_id=org.id, module_key=key, source=source,
                                           request_id=request_id, granted_by_staff_id=staff_id))
        db.flush()


def _refuse(db: Session, org: Organization, actor: Actor, action: str, message: str, request_id: str) -> None:
    platform_audit.record(
        db, action=action, result=platform_audit.DENIED, staff=actor.staff, session_id=actor.session_id,
        ip_address=actor.ip_address, user_agent=actor.user_agent, organization=org,
        target_type="subscription_request", target_id=request_id, details={"refused": message},
    )
    db.commit()
    raise ConflictError(message)


def approve(db: Session, request_id: str, actor: Actor, *, modules: Optional[List[str]] = None,
            seats: Optional[int] = None, billing_cycle: Optional[str] = None,
            reason: Optional[str] = None) -> Dict[str, Any]:
    req, org = _load(db, request_id, lock=True)
    action = platform_audit.SUBSCRIPTION_REQUEST_APPROVED
    if req.status != SubscriptionRequestStatus.SUBMITTED:
        _refuse(db, org, actor, action, f"This request is already {req.status.value}.", req.id)
    status = org_access.effective_status(org)
    if status not in APPROVABLE_STATUSES:
        _refuse(db, org, actor, action,
                f"The organization is {status.value.replace('_', ' ')}; only trial organizations can be approved.", req.id)
    granted = _normalise_modules(req.modules if modules is None else modules)
    seat_limit = req.seats if seats is None else seats
    cycle = req.billing_cycle.value if billing_cycle is None else billing_cycle
    used = org_access.seats_used(db, org.id)
    if seat_limit < used:
        raise ConflictError(f"The organization already has {used} member(s) and invitation(s); approve at least {used} seats.")
    modified = granted != list(req.modules or []) or seat_limit != req.seats or cycle != req.billing_cycle.value
    if modified:
        action = platform_audit.SUBSCRIPTION_REQUEST_APPROVED_WITH_CHANGES

    with tenant_context(org.id):  # RLS: tenant rows are written under the organization's context
        now = utcnow()
        before = {"status": status.value, "module_access": org.module_access, "seat_limit": org.seat_limit}
        org.status = OrganizationStatus.ACTIVE
        org.status_changed_at = now
        org.status_changed_by_staff_id = actor.staff.id
        org.status_reason = (reason or "Subscription approved")[:500]
        org.module_access = ModuleAccess.ENTITLED.value
        org.seat_limit = seat_limit
        req.status = SubscriptionRequestStatus.APPROVED
        req.reviewed_at = now
        req.reviewed_by_staff_id = actor.staff.id
        req.decision_reason = reason
        req.approved_modules = granted
        req.approved_seats = seat_limit
        req.approved_billing_cycle = cycle
        _replace_entitlements(db, org, granted, source="subscription_request", staff_id=actor.staff.id, request_id=req.id)
        after = {"status": org.status.value, "modules": granted, "seat_limit": seat_limit, "billing_cycle": cycle}
        platform_audit.record(
            db, action=action, result=platform_audit.SUCCESS, staff=actor.staff, session_id=actor.session_id,
            ip_address=actor.ip_address, user_agent=actor.user_agent, organization=org, reason=reason,
            target_type="subscription_request", target_id=req.id,
            details={"from": before, "to": after, "modified": modified,
                     "requested": {"modules": list(req.modules or []), "seats": req.seats,
                                   "billing_cycle": req.billing_cycle.value}},
        )
        audit.record(db, action="SUBSCRIPTION_APPROVED", entity_type="organization", entity_id=org.id,
                     entity_label=org.name, organization_id=org.id, actor_label="Rooman", before=before, after=after)
        db.commit()
        _notify_owners(db, org, approved=True, modules=granted, seat_limit=seat_limit, cycle=cycle, reason=reason,
                       actor=actor, request_id=request_id)
    # Not req.id: after the commit that would reload the row outside the tenant context, where row
    # level security (runtime role) hides it.
    return request_detail(db, request_id)


def reject(db: Session, request_id: str, actor: Actor, *, reason: str) -> Dict[str, Any]:
    req, org = _load(db, request_id, lock=True)
    action = platform_audit.SUBSCRIPTION_REQUEST_REJECTED
    if req.status != SubscriptionRequestStatus.SUBMITTED:
        _refuse(db, org, actor, action, f"This request is already {req.status.value}.", req.id)
    with tenant_context(org.id):  # RLS: tenant rows are written under the organization's context
        now = utcnow()
        req.status = SubscriptionRequestStatus.REJECTED
        req.reviewed_at = now
        req.reviewed_by_staff_id = actor.staff.id
        req.decision_reason = reason
        # The organization keeps its trial state and may submit a new request.
        platform_audit.record(
            db, action=action, result=platform_audit.SUCCESS, staff=actor.staff, session_id=actor.session_id,
            ip_address=actor.ip_address, user_agent=actor.user_agent, organization=org, reason=reason,
            target_type="subscription_request", target_id=req.id,
        )
        audit.record(db, action="SUBSCRIPTION_REQUEST_REJECTED", entity_type="subscription_request", entity_id=req.id,
                     entity_label=org.name, organization_id=org.id, actor_label="Rooman",
                     after={"status": "rejected", "reason": reason})
        db.commit()
        _notify_owners(db, org, approved=False, reason=reason, actor=actor, request_id=request_id)
    return request_detail(db, request_id)


def entitlements(db: Session, organization_id: str) -> Dict[str, Any]:
    org = _get_org(db, organization_id)
    with tenant_context(org.id):
        rows = db.scalars(select(OrganizationEntitlement.module_key)
                          .where(OrganizationEntitlement.organization_id == org.id)).all()
    return {"organization_id": org.id, "module_access": org.module_access or ModuleAccess.UNRESTRICTED.value,
            "modules": sorted(rows), "seat_limit": org.seat_limit, "seats_used": org_access.seats_used(db, org.id),
            "trial_ends_at": org.trial_ends_at}


def update_entitlements(db: Session, organization_id: str, actor: Actor, *, modules: List[str],
                        seat_limit: Optional[int], reason: str) -> Dict[str, Any]:
    """Administrator edit of an approved organization's modules and seats (upgrade/downgrade)."""
    org = _get_org(db, organization_id, lock=True)
    status = org_access.effective_status(org)
    if status not in (OrganizationStatus.ACTIVE, OrganizationStatus.SUSPENDED):
        raise ConflictError("Modules and seats can be changed only for active or suspended organizations; "
                            "trial organizations are decided through their subscription request.")
    used = org_access.seats_used(db, org.id)
    if seat_limit is not None and seat_limit < used:
        raise ConflictError(f"The organization already has {used} member(s) and invitation(s); "
                            f"the seat limit cannot be lower than {used}.")
    with tenant_context(org.id):  # RLS: tenant rows are written under the organization's context
        granted = _normalise_modules(modules)
        current = entitlements(db, org.id)
        before = {"module_access": current["module_access"], "modules": current["modules"], "seat_limit": org.seat_limit}
        org.module_access = ModuleAccess.ENTITLED.value
        org.seat_limit = seat_limit
        _replace_entitlements(db, org, granted, source="platform", staff_id=actor.staff.id)
        after = {"module_access": org.module_access, "modules": granted, "seat_limit": seat_limit}
        platform_audit.record(
            db, action=platform_audit.ORGANIZATION_ENTITLEMENTS_UPDATED, result=platform_audit.SUCCESS,
            staff=actor.staff, session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent,
            organization=org, reason=reason, target_type="organization", target_id=org.id,
            details={"from": before, "to": after},
        )
        audit.record(db, action="SUBSCRIPTION_ENTITLEMENTS_UPDATED", entity_type="organization", entity_id=org.id,
                     entity_label=org.name, organization_id=org.id, actor_label="Rooman", before=before, after=after)
        db.commit()
        return entitlements(db, org.id)


# --- notifications -----------------------------------------------------------------------------


def _owner_emails(db: Session, org_id: str) -> List[Tuple[str, str]]:
    rows = db.execute(
        select(User.email, User.full_name).join(Membership, Membership.user_id == User.id).where(
            Membership.organization_id == org_id, Membership.role == MemberRole.OWNER,
            Membership.status == MembershipStatus.ACTIVE, User.is_active.is_(True),
        )
    ).all()
    return [(email, name) for email, name in rows]


def _notify_owners(db: Session, org: Organization, *, approved: bool, actor: Actor, request_id: str,
                   reason: Optional[str] = None, modules: Optional[List[str]] = None,
                   seat_limit: Optional[int] = None, cycle: Optional[str] = None) -> None:
    """Email the organization's Owners after the decision is committed. A sign-in link only:
    Owners already have their own password; no credentials or tokens are ever emailed."""
    link = frontend_url("login")
    org_name = html.escape(org.name)
    labels = [registry().by_key[k].label for k in sorted(registry().base_keys)] + \
             [registry().by_key[k].label for k in (modules or [])]
    delivered = 0
    recipients = _owner_emails(db, org.id)
    for email, name in recipients:
        safe = html.escape(name or "")
        if approved:
            subject = f"{org.name} is now active on Rooman Billing"
            text = (f"Hello {name},\n\nYour subscription for {org.name} has been approved.\n"
                    f"Modules: {', '.join(labels)}\nUser seats: {seat_limit}\nBilling cycle: {cycle}\n\n"
                    f"Sign in with your existing password:\n{link}\n\n"
                    "Rooman will set up your organization's Admin account and email them an invitation.\n")
            body = (f"<p>Hello {safe},</p><p>Your subscription for <strong>{org_name}</strong> has been approved.</p>"
                    f"<ul><li>Modules: {html.escape(', '.join(labels))}</li><li>User seats: {seat_limit}</li>"
                    f"<li>Billing cycle: {html.escape(cycle or '')}</li></ul>"
                    "<p>Sign in with your existing password. Rooman will set up your organization's Admin account "
                    f'and email them an invitation.</p><p><a href="{html.escape(link)}">Sign in to Rooman Billing</a></p>')
        else:
            subject = f"Your Rooman Billing subscription request for {org.name}"
            text = (f"Hello {name},\n\nYour subscription request for {org.name} was not approved.\n"
                    f"Reason: {reason}\n\nYou can sign in and submit a new request:\n{link}\n")
            body = (f"<p>Hello {safe},</p><p>Your subscription request for <strong>{org_name}</strong> was not approved.</p>"
                    f"<p>Reason: {html.escape(reason or '')}</p>"
                    f'<p>You can <a href="{html.escape(link)}">sign in</a> and submit a new request.</p>')
        try:
            if send_email(email, subject, text, html_body=body):
                delivered += 1
        except Exception as exc:  # the decision is committed; a mail problem must not undo it
            logger.error("Subscription decision email for organization %s failed: %s", org.id, type(exc).__name__)
    platform_audit.record(
        db, action=platform_audit.ORGANIZATION_ONBOARDING_EMAIL, result=platform_audit.SUCCESS if delivered else platform_audit.FAILURE,
        staff=actor.staff, session_id=actor.session_id, ip_address=actor.ip_address, user_agent=actor.user_agent,
        organization=org, target_type="subscription_request", target_id=request_id,
        details={"approved": approved, "recipients": len(recipients), "delivered": delivered},
    )
    db.commit()
