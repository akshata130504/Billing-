"""Approvals API (contract section 10). Mounted at /approvals."""
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_viewer
from backend.app.schemas.approvals import ApprovalDecisionIn, ApprovalOut, ApprovalRejectIn
from backend.app.schemas.common_refs import PaginatedResponse
from backend.app.services import approval_service as svc
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


@router.get("", response_model=PaginatedResponse[ApprovalOut], summary="List approval requests")
def list_approvals(
    status_: Optional[str] = Query(None, alias="status"),
    type_: Optional[str] = Query(None, alias="type"),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_approvals(db, ctx, params, status=status_, type_=type_)
    return {
        "items": svc.serialize_approvals(db, ctx.organization_id, page.items),
        "total": page.total,
        "page": page.page,
        "page_size": page.page_size,
        "total_pages": page.total_pages,
    }


@router.post("/{approval_id}/approve", response_model=ApprovalOut, summary="Approve a request and apply its effect")
def approve(
    approval_id: str,
    body: ApprovalDecisionIn = Body(default=ApprovalDecisionIn()),
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    approval = svc.approve(db, ctx, approval_id, body.note)
    return svc.serialize_approvals(db, ctx.organization_id, [approval])[0]


@router.post("/{approval_id}/reject", response_model=ApprovalOut, summary="Reject a request")
def reject(
    approval_id: str,
    body: ApprovalRejectIn,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    approval = svc.reject(db, ctx, approval_id, body.note)
    return svc.serialize_approvals(db, ctx.organization_id, [approval])[0]
