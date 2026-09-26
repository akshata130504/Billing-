"""Organization settings and team endpoints (contract §3). Mounted with an empty prefix."""
from typing import List

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_viewer
from backend.app.schemas.organization import (
    OrganizationOut,
    OrganizationUpdate,
    TeamInviteRequest,
    TeamMember,
    TeamMemberInvited,
    TeamRoleUpdate,
)
from backend.app.services import organization_service

router = APIRouter()


@router.get("/organization", response_model=OrganizationOut, summary="Current organization settings")
def get_organization(ctx: CurrentContext = Depends(require_viewer)) -> OrganizationOut:
    return OrganizationOut.model_validate(ctx.organization)


@router.patch("/organization", response_model=OrganizationOut, summary="Update organization settings")
def update_organization(
    payload: OrganizationUpdate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OrganizationOut:
    organization = organization_service.update_organization(db, ctx, payload.model_dump(exclude_unset=True))
    return OrganizationOut.model_validate(organization)


@router.get("/team", response_model=List[TeamMember], summary="List team members")
def list_team(ctx: CurrentContext = Depends(require_viewer), db: Session = Depends(get_db)) -> List[TeamMember]:
    return organization_service.list_team(db, ctx.organization_id)


@router.post(
    "/team/invitations",
    response_model=TeamMemberInvited,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a team member",
)
def invite_member(
    payload: TeamInviteRequest,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TeamMemberInvited:
    return organization_service.invite_member(db, ctx, payload.email, payload.role, payload.full_name)


@router.patch("/team/{membership_id}", response_model=TeamMember, summary="Change a member's role")
def update_member_role(
    membership_id: str,
    payload: TeamRoleUpdate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TeamMember:
    return organization_service.change_role(db, ctx, membership_id, payload.role)


@router.delete(
    "/team/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
    summary="Deactivate a team member",
)
def deactivate_member(
    membership_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    organization_service.deactivate_member(db, ctx, membership_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/organization/logo", summary="Upload organization logo")
async def upload_org_logo(
    file: UploadFile = File(...),
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from backend.app.services import logo_service
    logo_url = await logo_service.save_organization_logo(db, ctx.organization, file)
    db.commit()
    return {"logo_url": logo_url}


@router.delete("/organization/logo", summary="Remove organization logo")
def delete_org_logo(
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from backend.app.services import logo_service
    logo_service.delete_organization_logo(db, ctx.organization)
    db.commit()
    return {"status": "success", "logo_url": None}
