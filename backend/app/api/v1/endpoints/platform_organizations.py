"""Platform organization directory and lifecycle. Mounted at /platform/organizations.

Metadata only (services/platform_org_service.py). Authorization is enforced here, server-side:

    GET  /                          any platform role         directory (search, status filter, sort, pages)
    GET  /{id}                      any platform role         detail (audited as ORGANIZATION_VIEWED)
    GET  /{id}/activity             any platform role         platform audit rows about this organization
                                                              (?lifecycle=true: lifecycle history only)
    POST /{id}/suspend              Administrator, Operations reason + ticket, step-up
    POST /{id}/reactivate           Administrator, Operations reason (automation stays paused)
    POST /{id}/schedule-deletion    Administrator             reason + ticket, step-up
    POST /{id}/cancel-deletion      Administrator             reason
    POST /{id}/jobs/pause           Administrator             reason, step-up
    POST /{id}/jobs/resume          Administrator             reason, step-up
    POST /{id}/revoke-sessions      Administrator, Operations reason, step-up (tenant + portal sessions)
    POST /{id}/admins               Administrator             provision the tenant Admin (invitation), step-up

There is no hard delete, no tenant data endpoint, and nothing here runs billing jobs.
"""
import math
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.api.platform_deps import (
    ADMINISTRATOR_ONLY,
    LIFECYCLE_ROLES,
    PlatformContext,
    require_platform_roles,
    require_platform_roles_with_step_up,
    require_platform_staff,
)
from backend.app.models import OrganizationStatus
from backend.app.schemas.platform_console import (
    AuditEntryOut,
    AuditPageOut,
    LifecycleResultOut,
    OptionalReasonRequest,
    OrganizationDetailOut,
    OrganizationPageOut,
    OrganizationSummaryOut,
    ProvisionAdminRequest,
    ProvisionedAdminOut,
    ReasonRequest,
    TenantAdminActionResult,
    TenantAdminOut,
    TicketedReasonRequest,
)
from backend.app.services import platform_audit, platform_org_service as svc

router = APIRouter()


def _actor(ctx: PlatformContext) -> svc.Actor:
    return svc.Actor(staff=ctx.staff, session_id=ctx.session.id, ip_address=ctx.ip_address, user_agent=ctx.user_agent)


def audit_out(row) -> AuditEntryOut:
    return AuditEntryOut(
        id=row.id, occurred_at=row.occurred_at, action=row.action, result=row.result,
        platform_staff_id=row.platform_staff_id, staff_email_snapshot=row.staff_email_snapshot,
        staff_role_snapshot=row.staff_role_snapshot, organization_id=row.organization_id,
        organization_name_snapshot=row.organization_name_snapshot, target_type=row.target_type,
        target_id=row.target_id, reason=row.reason, ticket_ref=row.ticket_ref, ip_address=row.ip_address,
        user_agent=row.user_agent, details=platform_audit.scrub(row.details),
    )


def audit_page_out(rows, total: int, page: int, page_size: int) -> AuditPageOut:
    page_size = max(1, min(page_size, svc.MAX_PAGE_SIZE))
    return AuditPageOut(items=[audit_out(r) for r in rows], total=total, page=page, page_size=page_size,
                        total_pages=max(1, math.ceil(total / page_size)) if total else 0)


@router.get("", response_model=OrganizationPageOut, summary="Organization directory (metadata only)")
def list_organizations(
    q: Optional[str] = Query(default=None, max_length=100),
    status: Optional[OrganizationStatus] = Query(default=None),
    sort: Literal["name", "created_at", "updated_at", "status"] = "created_at",
    direction: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=25, ge=1, le=svc.MAX_PAGE_SIZE),
    ctx: PlatformContext = Depends(require_platform_staff),
    db: Session = Depends(get_db),
):
    result = svc.list_organizations(db, q=q, status=status, sort=sort, direction=direction, page=page,
                                    page_size=page_size)
    return OrganizationPageOut(
        items=[OrganizationSummaryOut(**item) for item in result.items],
        total=result.total, page=result.page, page_size=result.page_size,
        total_pages=math.ceil(result.total / result.page_size) if result.total else 0,
    )


@router.get("/{organization_id}", response_model=OrganizationDetailOut, summary="Organization detail (metadata only)")
def get_organization(organization_id: str, ctx: PlatformContext = Depends(require_platform_staff),
                     db: Session = Depends(get_db)):
    return OrganizationDetailOut(**svc.organization_detail(db, organization_id, _actor(ctx)))


@router.get("/{organization_id}/activity", response_model=AuditPageOut, summary="Platform audit for this organization")
def organization_activity(
    organization_id: str,
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=25, ge=1, le=svc.MAX_PAGE_SIZE),
    lifecycle: bool = False,
    ctx: PlatformContext = Depends(require_platform_staff),
    db: Session = Depends(get_db),
):
    rows, total = svc.organization_activity(db, organization_id, page=page, page_size=page_size,
                                            lifecycle_only=lifecycle)
    return audit_page_out(rows, total, page, page_size)


def _lifecycle(db: Session, organization_id: str, action: str, ctx: PlatformContext, body: ReasonRequest):
    result = svc.change_lifecycle(db, organization_id, action, _actor(ctx), reason=body.reason, ticket_ref=body.ticket_ref)
    return LifecycleResultOut(organization=OrganizationSummaryOut(**result.organization), changed=result.changed)


@router.post("/{organization_id}/suspend", response_model=LifecycleResultOut, summary="Suspend an organization")
def suspend(organization_id: str, body: TicketedReasonRequest,
            ctx: PlatformContext = Depends(require_platform_roles_with_step_up(LIFECYCLE_ROLES)),
            db: Session = Depends(get_db)):
    return _lifecycle(db, organization_id, "suspend", ctx, body)


@router.post("/{organization_id}/reactivate", response_model=LifecycleResultOut,
             summary="Reactivate a suspended organization (billing automation stays paused)")
def reactivate(organization_id: str, body: ReasonRequest,
               ctx: PlatformContext = Depends(require_platform_roles(LIFECYCLE_ROLES)),
               db: Session = Depends(get_db)):
    return _lifecycle(db, organization_id, "reactivate", ctx, body)


@router.post("/{organization_id}/schedule-deletion", response_model=LifecycleResultOut,
             summary="Schedule an organization for deletion after the waiting period")
def schedule_deletion(organization_id: str, body: TicketedReasonRequest,
                      ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
                      db: Session = Depends(get_db)):
    return _lifecycle(db, organization_id, "schedule_deletion", ctx, body)


@router.post("/{organization_id}/cancel-deletion", response_model=LifecycleResultOut,
             summary="Cancel a scheduled deletion (the organization returns to suspended)")
def cancel_deletion(organization_id: str, body: ReasonRequest,
                    ctx: PlatformContext = Depends(require_platform_roles(ADMINISTRATOR_ONLY)),
                    db: Session = Depends(get_db)):
    return _lifecycle(db, organization_id, "cancel_deletion", ctx, body)


@router.post("/{organization_id}/jobs/pause", response_model=LifecycleResultOut,
             summary="Pause billing automation for one organization")
def pause_jobs(organization_id: str, body: ReasonRequest,
               ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
               db: Session = Depends(get_db)):
    result = svc.set_jobs_paused(db, organization_id, "pause_jobs", _actor(ctx), reason=body.reason,
                                 ticket_ref=body.ticket_ref)
    return LifecycleResultOut(organization=OrganizationSummaryOut(**result.organization), changed=result.changed)


@router.post("/{organization_id}/jobs/resume", response_model=LifecycleResultOut,
             summary="Resume billing automation for one organization")
def resume_jobs(organization_id: str, body: ReasonRequest,
                ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
                db: Session = Depends(get_db)):
    result = svc.set_jobs_paused(db, organization_id, "resume_jobs", _actor(ctx), reason=body.reason,
                                 ticket_ref=body.ticket_ref)
    return LifecycleResultOut(organization=OrganizationSummaryOut(**result.organization), changed=result.changed)


@router.post("/{organization_id}/revoke-sessions", response_model=LifecycleResultOut,
             summary="Sign all tenant and customer-portal users out of this organization")
def revoke_sessions(organization_id: str, body: ReasonRequest,
                    ctx: PlatformContext = Depends(require_platform_roles_with_step_up(LIFECYCLE_ROLES)),
                    db: Session = Depends(get_db)):
    result = svc.revoke_tenant_sessions(db, organization_id, _actor(ctx), reason=body.reason, ticket_ref=body.ticket_ref)
    return LifecycleResultOut(organization=OrganizationSummaryOut(**result.organization), changed=result.changed)


@router.post("/{organization_id}/approve", response_model=LifecycleResultOut, summary="Approve a pending organization")
def approve(
    organization_id: str,
    body: OptionalReasonRequest = OptionalReasonRequest(),
    ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
    db: Session = Depends(get_db),
):
    reason = body.reason or "Approved by Platform Administrator"
    result = svc.change_lifecycle(db, organization_id, "approve", _actor(ctx), reason=reason, ticket_ref=body.ticket_ref)
    return LifecycleResultOut(organization=OrganizationSummaryOut(**result.organization), changed=result.changed)


@router.post("/{organization_id}/reject", response_model=LifecycleResultOut, summary="Reject a pending organization with a reason")
def reject(
    organization_id: str,
    body: ReasonRequest,
    ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
    db: Session = Depends(get_db),
):
    result = svc.change_lifecycle(db, organization_id, "reject", _actor(ctx), reason=body.reason, ticket_ref=body.ticket_ref)
    return LifecycleResultOut(organization=OrganizationSummaryOut(**result.organization), changed=result.changed)


@router.post("/{organization_id}/admins", response_model=ProvisionedAdminOut, status_code=201,
             summary="Provision the organization's tenant Admin (invitation; never a platform account)")
def provision_admin(
    organization_id: str,
    body: ProvisionAdminRequest,
    ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
    db: Session = Depends(get_db),
):
    from backend.app.services import tenant_admin_provisioning

    return ProvisionedAdminOut(**tenant_admin_provisioning.provision_admin(
        db, organization_id, _actor(ctx), full_name=body.full_name, email=body.email))


@router.get("/{organization_id}/admins", response_model=list[TenantAdminOut], summary="List tenant Owner and Admin accounts")
def list_admins(
    organization_id: str,
    ctx: PlatformContext = Depends(require_platform_roles(ADMINISTRATOR_ONLY)),
    db: Session = Depends(get_db),
):
    items = svc.list_tenant_admins(db, organization_id, _actor(ctx))
    return [TenantAdminOut(**item) for item in items]


@router.post("/{organization_id}/admins/{user_id}/deactivate", response_model=TenantAdminActionResult, summary="Deactivate a tenant Admin")
def deactivate_admin(
    organization_id: str,
    user_id: str,
    body: ReasonRequest,
    ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
    db: Session = Depends(get_db),
):
    res = svc.deactivate_tenant_admin(db, organization_id, user_id, _actor(ctx), reason=body.reason, ticket_ref=body.ticket_ref)
    return TenantAdminActionResult(**res)


@router.post("/{organization_id}/admins/{user_id}/reactivate", response_model=TenantAdminActionResult, summary="Reactivate a tenant Admin")
def reactivate_admin(
    organization_id: str,
    user_id: str,
    body: ReasonRequest,
    ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
    db: Session = Depends(get_db),
):
    res = svc.reactivate_tenant_admin(db, organization_id, user_id, _actor(ctx), reason=body.reason, ticket_ref=body.ticket_ref)
    return TenantAdminActionResult(**res)


@router.post("/{organization_id}/admins/{user_id}/revoke-sessions", response_model=TenantAdminActionResult, summary="Revoke sessions of a tenant Admin")
def revoke_admin_sessions(
    organization_id: str,
    user_id: str,
    body: ReasonRequest,
    ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
    db: Session = Depends(get_db),
):
    res = svc.revoke_tenant_admin_sessions(db, organization_id, user_id, _actor(ctx), reason=body.reason, ticket_ref=body.ticket_ref)
    return TenantAdminActionResult(**res)
