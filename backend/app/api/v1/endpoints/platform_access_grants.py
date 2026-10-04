"""Tenant access grants - platform side. Mounted at /platform/access-grants.

    GET  /                           Support (own), Administrator (all)
    POST /                           Support, Administrator   request (organization, scopes, duration, reason, ticket)
    GET  /{id}                       requester, Administrator
    POST /{id}/cancel                requester                withdraw a pending request
    POST /{id}/revoke                requester, Administrator
    POST /{id}/enter                 requester                step-up; returns a short grant token for the tenant API
    POST /emergency                  Administrator            break-glass request
    POST /{id}/emergency-approve     a DIFFERENT Administrator, step-up
    POST /{id}/review                Administrator            post-incident review of an emergency grant

Platform Operations has no tenant-data access (design section 4). Scopes are read-only.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.api.platform_deps import (
    ADMINISTRATOR_ONLY,
    PlatformContext,
    require_platform_roles,
    require_platform_roles_with_step_up,
)
from backend.app.models.access_grants import GrantScope
from backend.app.models.platform import PlatformRole
from backend.app.schemas.organization import UTCDateTime
from backend.app.services import access_grant_service as svc
from backend.app.services.platform_org_service import Actor

router = APIRouter()
GRANT_ROLES = frozenset({PlatformRole.PLATFORM_ADMINISTRATOR, PlatformRole.PLATFORM_SUPPORT})
require_grant_roles = require_platform_roles(GRANT_ROLES)
require_admin = require_platform_roles(ADMINISTRATOR_ONLY)


class GrantRequest(BaseModel):
    organization_id: str = Field(min_length=1, max_length=36)
    scopes: List[GrantScope] = Field(default_factory=list, max_length=8)
    duration_minutes: int = Field(default=svc.DEFAULT_MINUTES, ge=svc.MIN_MINUTES, le=svc.MAX_MINUTES)
    reason: str = Field(min_length=svc.MIN_REASON, max_length=2000)
    ticket_ref: str = Field(min_length=2, max_length=100)


class EmergencyRequest(GrantRequest):
    duration_minutes: int = Field(default=svc.EMERGENCY_MAX_MINUTES, ge=svc.MIN_MINUTES, le=svc.EMERGENCY_MAX_MINUTES)


class RevokeRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=300)


class ReviewRequest(BaseModel):
    notes: str = Field(min_length=svc.MIN_REASON, max_length=4000)


class PersonOut(BaseModel):
    id: str
    full_name: str
    email: Optional[str] = None
    role: Optional[str] = None
    kind: Optional[str] = None


class GrantOut(BaseModel):
    id: str
    organization_id: str
    organization_name: Optional[str] = None
    status: str
    scopes: List[str]
    reason: str
    ticket_ref: str
    requested_duration_minutes: int
    is_emergency: bool
    requested_by: Optional[PersonOut] = None
    approved_by: Optional[PersonOut] = None
    created_at: Optional[UTCDateTime] = None
    approved_at: Optional[UTCDateTime] = None
    first_used_at: Optional[UTCDateTime] = None
    last_entered_at: Optional[UTCDateTime] = None
    expires_at: Optional[UTCDateTime] = None
    revoked_at: Optional[UTCDateTime] = None
    revoked_by_kind: Optional[str] = None
    revoke_reason: Optional[str] = None
    denied_at: Optional[UTCDateTime] = None
    denied_reason: Optional[str] = None
    request_count: int
    reviewed_at: Optional[UTCDateTime] = None
    review_notes: Optional[str] = None
    review_due_at: Optional[UTCDateTime] = None
    review_overdue: bool


class GrantListOut(BaseModel):
    items: List[GrantOut]


class EnterOut(BaseModel):
    grant: GrantOut
    token: str
    token_expires_at: datetime
    organization: Dict[str, Any]


def _actor(ctx: PlatformContext) -> Actor:
    return Actor(staff=ctx.staff, session_id=ctx.session.id, ip_address=ctx.ip_address, user_agent=ctx.user_agent)


@router.get("", response_model=GrantListOut, summary="Access grants (own requests; all for Administrators)")
def list_grants(status: Optional[str] = Query(default=None, max_length=16),
                organization_id: Optional[str] = Query(default=None, max_length=36),
                emergency: Optional[bool] = None,
                ctx: PlatformContext = Depends(require_grant_roles), db: Session = Depends(get_db)):
    return GrantListOut(items=[GrantOut(**g) for g in svc.list_grants(
        db, _actor(ctx), status=status, organization_id=organization_id, emergency=emergency)])


@router.post("", response_model=GrantOut, summary="Request access to one tenant (needs the tenant Owner's approval)")
def request_grant(body: GrantRequest, background: BackgroundTasks, ctx: PlatformContext = Depends(require_grant_roles),
                  db: Session = Depends(get_db)):
    grant, notice = svc.request_grant(db, _actor(ctx), organization_id=body.organization_id,
                                      scopes=[s.value for s in body.scopes], duration_minutes=body.duration_minutes,
                                      reason=body.reason, ticket_ref=body.ticket_ref)
    background.add_task(notice.send)
    return GrantOut(**grant)


@router.post("/emergency", response_model=GrantOut, summary="Request break-glass emergency access")
def request_emergency(body: EmergencyRequest, ctx: PlatformContext = Depends(require_admin), db: Session = Depends(get_db)):
    return GrantOut(**svc.request_emergency(db, _actor(ctx), organization_id=body.organization_id,
                                            scopes=[s.value for s in body.scopes], duration_minutes=body.duration_minutes,
                                            reason=body.reason, ticket_ref=body.ticket_ref))


@router.get("/{grant_id}", response_model=GrantOut, summary="One access grant")
def get_grant(grant_id: str, ctx: PlatformContext = Depends(require_grant_roles), db: Session = Depends(get_db)):
    return GrantOut(**svc.get_for_staff(db, _actor(ctx), grant_id))


@router.post("/{grant_id}/cancel", response_model=GrantOut, summary="Withdraw a pending request")
def cancel(grant_id: str, ctx: PlatformContext = Depends(require_grant_roles), db: Session = Depends(get_db)):
    return GrantOut(**svc.cancel(db, _actor(ctx), grant_id))


@router.post("/{grant_id}/revoke", response_model=GrantOut, summary="End a grant now")
def revoke(grant_id: str, body: RevokeRequest, background: BackgroundTasks,
           ctx: PlatformContext = Depends(require_grant_roles), db: Session = Depends(get_db)):
    grant, notice = svc.revoke_by_staff(db, _actor(ctx), grant_id, body.reason)
    if notice:
        background.add_task(notice.send)
    return GrantOut(**grant)


@router.post("/{grant_id}/enter", response_model=EnterOut, summary="Enter the tenant under an approved grant")
def enter(grant_id: str, ctx: PlatformContext = Depends(require_platform_roles_with_step_up(GRANT_ROLES)),
          db: Session = Depends(get_db)):
    result = svc.enter(db, _actor(ctx), grant_id)
    return EnterOut(grant=GrantOut(**result["grant"]), token=result["token"], token_expires_at=result["token_expires_at"],
                    organization=result["organization"])


@router.post("/{grant_id}/emergency-approve", response_model=GrantOut, summary="Approve emergency access (second Administrator)")
def emergency_approve(grant_id: str, background: BackgroundTasks,
                      ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
                      db: Session = Depends(get_db)):
    grant, notice = svc.approve_emergency(db, _actor(ctx), grant_id)
    background.add_task(notice.send)
    return GrantOut(**grant)


@router.post("/{grant_id}/review", response_model=GrantOut, summary="Record the post-incident review of emergency access")
def review(grant_id: str, body: ReviewRequest, ctx: PlatformContext = Depends(require_admin), db: Session = Depends(get_db)):
    return GrantOut(**svc.review_emergency(db, _actor(ctx), grant_id, body.notes))
