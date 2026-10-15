"""Client platform endpoints: native auth exchange, device registration/trust, and mobile/desktop bootstrap."""
from typing import List

from fastapi import APIRouter, Depends, Request

from backend.app.api.deps import CurrentContext, client_ip, get_db, require_tenant_user
from backend.app.models import MemberRole
from backend.app.core.rate_limit import auth_rate_limit, limiter
from backend.app.schemas.devices import (
    DeviceOut,
    DeviceRegisterIn,
    MobileBootstrapOut,
    NativeExchangeRequest,
    NativeExchangeResponse,
)
from sqlalchemy.orm import Session

from backend.app.services import device_service

router = APIRouter(tags=["Client Platforms"])

# The caller's own devices: members of the organization only, through the same lifecycle, trial and
# module ("platforms") gates as every other tenant route (api/deps.py).
require_member = require_tenant_user(MemberRole.VIEWER)


def _ua(request: Request) -> str | None:
    return (request.headers.get("user-agent") or "")[:400] or None


@router.post("/auth/native/exchange", response_model=NativeExchangeResponse, summary="Credential exchange for native desktop/mobile clients")
@limiter.limit(auth_rate_limit)
def exchange_native_credentials(
    request: Request,
    payload: NativeExchangeRequest,
    db: Session = Depends(get_db),
) -> NativeExchangeResponse:
    """Authenticates a native client and registers/refreshes its device in one round trip."""
    tokens, device = device_service.exchange_native_credentials(
        db,
        payload.email,
        payload.password,
        payload.device,
        ip=client_ip(request),
        user_agent=_ua(request),
    )
    return NativeExchangeResponse(**tokens.as_dict(), device=device)


@router.post("/devices", response_model=DeviceOut, summary="Register or refresh the caller's own device")
def register_device(
    data: DeviceRegisterIn,
    ctx: CurrentContext = Depends(require_member),
    db: Session = Depends(get_db),
) -> DeviceOut:
    device = device_service.register_device(db, ctx.organization_id, ctx.user_id, data)
    db.commit()
    db.refresh(device)
    return device


@router.get("/devices", response_model=List[DeviceOut], summary="List the caller's registered devices")
def list_devices(
    ctx: CurrentContext = Depends(require_member),
    db: Session = Depends(get_db),
) -> List[DeviceOut]:
    return device_service.list_devices(db, ctx.organization_id, ctx.user_id)


@router.delete("/devices/{device_id}", summary="Revoke one of the caller's devices")
def revoke_device(
    device_id: str,
    ctx: CurrentContext = Depends(require_member),
    db: Session = Depends(get_db),
):
    device_service.revoke_device(db, device_id, ctx.organization_id, ctx.user_id)
    db.commit()
    return {"status": "success", "message": "Device revoked."}


@router.get("/mobile/bootstrap", response_model=MobileBootstrapOut, summary="Compact org/user context for native client startup")
def mobile_bootstrap(
    ctx: CurrentContext = Depends(require_member),
    db: Session = Depends(get_db),
) -> MobileBootstrapOut:
    return device_service.build_mobile_bootstrap(db, ctx)
