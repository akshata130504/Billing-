"""Platform staff administration. Mounted at /platform/staff. Platform Administrator only.

    GET  /                          list (role, active, 2FA enrolled, last sign-in, live sessions)
    GET  /{id}                      detail with session metadata
    POST /{id}/deactivate           reason, step-up (never yourself, never the last administrator)
    POST /{id}/activate             reason, step-up (a fresh sign-in is required afterwards)
    POST /{id}/revoke-sessions      reason

No endpoint creates staff, changes roles or resets 2FA: those stay with the server-side CLI.
No response contains a password hash, TOTP secret or session secret.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.api.platform_deps import (
    ADMINISTRATOR_ONLY,
    PlatformContext,
    require_platform_roles,
    require_platform_roles_with_step_up,
)
from backend.app.schemas.platform_console import (
    ReasonRequest,
    StaffActionOut,
    StaffDetailOut,
    StaffListOut,
    StaffSummaryOut,
)
from backend.app.services import platform_staff_service as svc
from backend.app.services.platform_org_service import Actor

router = APIRouter()
require_administrator = require_platform_roles(ADMINISTRATOR_ONLY)
require_administrator_step_up = require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)


def _actor(ctx: PlatformContext) -> Actor:
    return Actor(staff=ctx.staff, session_id=ctx.session.id, ip_address=ctx.ip_address, user_agent=ctx.user_agent)


@router.get("", response_model=StaffListOut, summary="Platform staff")
def list_staff(ctx: PlatformContext = Depends(require_administrator), db: Session = Depends(get_db)):
    return StaffListOut(items=[StaffSummaryOut(**s) for s in svc.list_staff(db)])


@router.get("/{staff_id}", response_model=StaffDetailOut, summary="Platform staff member")
def get_staff(staff_id: str, ctx: PlatformContext = Depends(require_administrator), db: Session = Depends(get_db)):
    return StaffDetailOut(**svc.staff_detail(db, staff_id, _actor(ctx)))


@router.post("/{staff_id}/deactivate", response_model=StaffActionOut, summary="Deactivate a platform staff member")
def deactivate(staff_id: str, body: ReasonRequest, ctx: PlatformContext = Depends(require_administrator_step_up),
               db: Session = Depends(get_db)):
    return StaffActionOut(**svc.deactivate(db, staff_id, _actor(ctx), reason=body.reason))


@router.post("/{staff_id}/activate", response_model=StaffActionOut, summary="Reactivate a platform staff member")
def activate(staff_id: str, body: ReasonRequest, ctx: PlatformContext = Depends(require_administrator_step_up),
             db: Session = Depends(get_db)):
    return StaffActionOut(**svc.activate(db, staff_id, _actor(ctx), reason=body.reason))


@router.post("/{staff_id}/revoke-sessions", response_model=StaffActionOut, summary="Revoke a staff member's sessions")
def revoke_sessions(staff_id: str, body: ReasonRequest, ctx: PlatformContext = Depends(require_administrator),
                    db: Session = Depends(get_db)):
    return StaffActionOut(**svc.revoke_sessions(db, staff_id, _actor(ctx), reason=body.reason))
