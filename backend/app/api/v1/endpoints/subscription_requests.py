"""The organization's trial state and subscription request. Mounted at /subscription-requests.

    GET  /                  any member        trial / access state, module catalog, current request, history
    POST /                  Owner, Admin      submit a request (modules, seats, billing cycle) - one open at a time
    POST /{id}/withdraw     Owner, Admin      withdraw the open request

Reachable while the trial has ended (api/deps.py TRIAL_EXPIRED_ALLOWED). Only members of the
organization (never a platform grant) may submit or withdraw.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_tenant_user, require_viewer
from backend.app.models import MemberRole
from backend.app.schemas.subscription_access import (
    SubscriptionRequestCreate,
    SubscriptionRequestOut,
    TenantSubscriptionState,
)
from backend.app.services import subscription_request_service as svc

router = APIRouter()


@router.get("", response_model=TenantSubscriptionState, summary="Trial state, modules and subscription requests")
def subscription_state(ctx: CurrentContext = Depends(require_viewer), db: Session = Depends(get_db)):
    return TenantSubscriptionState(**svc.tenant_state(db, ctx))


@router.post("", response_model=SubscriptionRequestOut, status_code=status.HTTP_201_CREATED,
             summary="Request a subscription (Owner or Admin)")
def submit_request(body: SubscriptionRequestCreate,
                   ctx: CurrentContext = Depends(require_tenant_user(MemberRole.ADMIN)),
                   db: Session = Depends(get_db)):
    return SubscriptionRequestOut(**svc.submit(db, ctx, modules=body.modules, seats=body.seats,
                                               billing_cycle=body.billing_cycle, notes=body.notes))


@router.post("/{request_id}/withdraw", response_model=SubscriptionRequestOut,
             summary="Withdraw the open subscription request (Owner or Admin)")
def withdraw_request(request_id: str, ctx: CurrentContext = Depends(require_tenant_user(MemberRole.ADMIN)),
                     db: Session = Depends(get_db)):
    return SubscriptionRequestOut(**svc.withdraw(db, ctx, request_id))
