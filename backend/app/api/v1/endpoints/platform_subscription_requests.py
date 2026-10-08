"""Subscription requests and organization entitlements in the platform console.
Mounted at /platform/subscription-requests.

    GET  /                                    any platform role   queue (?status=submitted|approved|rejected|withdrawn|all)
    GET  /{id}                                any platform role   one request
    POST /{id}/approve                        Administrator       approve as requested or modified; step-up
    POST /{id}/reject                         Administrator       reason (10+ characters); step-up
    GET  /organizations/{org_id}/entitlements any platform role   modules + seat limit
    POST /organizations/{org_id}/entitlements Administrator       change modules / seats; step-up

Operations and Support can read but never decide. Nothing here moves money or reads tenant
financial data.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.api.platform_deps import (
    ADMINISTRATOR_ONLY,
    PlatformContext,
    require_platform_roles_with_step_up,
    require_platform_staff,
)
from backend.app.schemas.subscription_access import (
    ApproveSubscriptionRequest,
    OrganizationEntitlementsOut,
    PlatformSubscriptionRequestOut,
    PlatformSubscriptionRequestPage,
    RejectSubscriptionRequest,
    UpdateEntitlements,
)
from backend.app.services import platform_org_service, subscription_request_service as svc

router = APIRouter()


def _actor(ctx: PlatformContext) -> platform_org_service.Actor:
    return platform_org_service.Actor(staff=ctx.staff, session_id=ctx.session.id, ip_address=ctx.ip_address,
                                      user_agent=ctx.user_agent)


@router.get("", response_model=PlatformSubscriptionRequestPage, summary="Subscription request queue")
def list_requests(
    status: Literal["submitted", "approved", "rejected", "withdrawn", "all"] = "submitted",
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=25, ge=1, le=100),
    ctx: PlatformContext = Depends(require_platform_staff),
    db: Session = Depends(get_db),
):
    result = svc.list_requests(db, status=None if status == "all" else status, page=page, page_size=page_size)
    return PlatformSubscriptionRequestPage(
        items=[PlatformSubscriptionRequestOut(**i) for i in result["items"]],
        total=result["total"], page=result["page"], page_size=result["page_size"],
    )


@router.get("/organizations/{organization_id}/entitlements", response_model=OrganizationEntitlementsOut,
            summary="An organization's modules and seat limit")
def get_entitlements(organization_id: str, ctx: PlatformContext = Depends(require_platform_staff),
                     db: Session = Depends(get_db)):
    return OrganizationEntitlementsOut(**svc.entitlements(db, organization_id))


@router.post("/organizations/{organization_id}/entitlements", response_model=OrganizationEntitlementsOut,
            summary="Change an active organization's modules and seat limit (Administrator)")
def update_entitlements(organization_id: str, body: UpdateEntitlements,
                        ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
                        db: Session = Depends(get_db)):
    return OrganizationEntitlementsOut(**svc.update_entitlements(
        db, organization_id, _actor(ctx), modules=body.modules, seat_limit=body.seat_limit, reason=body.reason))


@router.get("/{request_id}", response_model=PlatformSubscriptionRequestOut, summary="One subscription request")
def get_request(request_id: str, ctx: PlatformContext = Depends(require_platform_staff),
                db: Session = Depends(get_db)):
    return PlatformSubscriptionRequestOut(**svc.request_detail(db, request_id))


@router.post("/{request_id}/approve", response_model=PlatformSubscriptionRequestOut,
             summary="Approve a subscription request, optionally modified (Administrator)")
def approve(request_id: str, body: ApproveSubscriptionRequest,
            ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
            db: Session = Depends(get_db)):
    return PlatformSubscriptionRequestOut(**svc.approve(
        db, request_id, _actor(ctx), modules=body.modules, seats=body.seats, billing_cycle=body.billing_cycle,
        reason=body.reason))


@router.post("/{request_id}/reject", response_model=PlatformSubscriptionRequestOut,
             summary="Reject a subscription request with a reason (Administrator)")
def reject(request_id: str, body: RejectSubscriptionRequest,
           ctx: PlatformContext = Depends(require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)),
           db: Session = Depends(get_db)):
    return PlatformSubscriptionRequestOut(**svc.reject(db, request_id, _actor(ctx), reason=body.reason))
