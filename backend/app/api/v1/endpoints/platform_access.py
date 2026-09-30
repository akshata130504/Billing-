"""Platform access - tenant side (design sections 11 and 14). Mounted at "".

Tenant users (never a platform grant):
    GET  /organization/platform-access                 Admin, Owner   current and past grants
    GET  /organization/platform-access/active          Admin, Owner   grants active right now (banner)
    POST /organization/platform-access/{id}/approve    Owner          starts the expiry clock
    POST /organization/platform-access/{id}/deny       Owner
    POST /organization/platform-access/{id}/revoke     Admin, Owner   ends it immediately

Platform staff under a grant (grant token only):
    GET  /platform-access/session                       what this grant allows and until when
    POST /platform-access/exit                          end this grant session now
"""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, client_ip, get_db, require_grant_context, require_tenant_user
from backend.app.api.v1.endpoints.platform_access_grants import GrantOut
from backend.app.core.grant_scopes import SCOPE_LABELS
from backend.app.models import MemberRole
from backend.app.models.access_grants import GrantScope
from backend.app.schemas.organization import UTCDateTime
from backend.app.services import access_grant_service as svc

router = APIRouter()
require_admin_user = require_tenant_user(MemberRole.ADMIN)
require_owner_user = require_tenant_user(MemberRole.OWNER)


class DecisionRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=300)


class TenantGrantListOut(BaseModel):
    items: List[GrantOut]


class GrantSessionOut(BaseModel):
    grant_id: str
    organization_id: str
    organization_name: str
    staff_name: str
    scopes: List[str]
    areas: List[str]
    expires_at: Optional[UTCDateTime] = None
    is_emergency: bool
    ticket_ref: str


def _ua(request: Request) -> Optional[str]:
    return (request.headers.get("user-agent") or "")[:400] or None


@router.get("/organization/platform-access", response_model=TenantGrantListOut, summary="Platform access to this organization")
def list_access(ctx: CurrentContext = Depends(require_admin_user), db: Session = Depends(get_db)):
    return TenantGrantListOut(items=[GrantOut(**g) for g in svc.list_for_organization(db, ctx.organization_id)])


@router.get("/organization/platform-access/active", response_model=TenantGrantListOut, summary="Platform access active now")
def active_access(ctx: CurrentContext = Depends(require_admin_user), db: Session = Depends(get_db)):
    return TenantGrantListOut(items=[GrantOut(**g) for g in svc.active_grants_for_banner(db, ctx.organization_id)])


@router.post("/organization/platform-access/{grant_id}/approve", response_model=GrantOut, summary="Approve a platform access request")
def approve(grant_id: str, request: Request, background: BackgroundTasks,
            ctx: CurrentContext = Depends(require_owner_user), db: Session = Depends(get_db)):
    grant = svc.owner_approve(db, ctx.organization_id, ctx.user, grant_id, ip=client_ip(request), ua=_ua(request))
    return GrantOut(**grant)


@router.post("/organization/platform-access/{grant_id}/deny", response_model=GrantOut, summary="Deny a platform access request")
def deny(grant_id: str, body: DecisionRequest, request: Request, ctx: CurrentContext = Depends(require_owner_user),
         db: Session = Depends(get_db)):
    return GrantOut(**svc.owner_deny(db, ctx.organization_id, ctx.user, grant_id, body.reason, ip=client_ip(request), ua=_ua(request)))


@router.post("/organization/platform-access/{grant_id}/revoke", response_model=GrantOut, summary="End platform access now")
def revoke(grant_id: str, body: DecisionRequest, request: Request, ctx: CurrentContext = Depends(require_admin_user),
           db: Session = Depends(get_db)):
    return GrantOut(**svc.tenant_revoke(db, ctx.organization_id, ctx.user, grant_id, body.reason, ip=client_ip(request), ua=_ua(request)))


@router.get("/platform-access/session", response_model=GrantSessionOut, summary="The current platform grant session")
def grant_session(ctx: CurrentContext = Depends(require_grant_context)):
    g = ctx.grant.grant
    return GrantSessionOut(
        grant_id=g.id, organization_id=ctx.organization_id, organization_name=ctx.organization.name,
        staff_name=ctx.grant.staff.full_name, scopes=list(g.scopes),
        areas=[SCOPE_LABELS[GrantScope(s)] for s in g.scopes], expires_at=g.expires_at,
        is_emergency=bool(g.is_emergency), ticket_ref=g.ticket_ref,
    )


@router.post("/platform-access/exit", status_code=204, summary="Exit the tenant (ends this grant token)")
def exit_access(request: Request, ctx: CurrentContext = Depends(require_grant_context), db: Session = Depends(get_db)):
    svc.exit_grant(db, ctx.grant, ip=client_ip(request), ua=_ua(request))
