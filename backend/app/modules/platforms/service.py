"""Client platform device registration/trust, native auth exchange, and mobile/desktop bootstrap.

Server remains authoritative for every billing action; devices only ever carry a bearer
session and a push token, never invoice numbers or billing state.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import AppException, NotFoundAppError, ValidationAppError
from backend.app.core.security import decode_access_token
from backend.app.models.base import utcnow
from backend.app.models.devices import Device, DeviceTrustStatus
from backend.app.schemas.devices import DeviceRegisterIn, MobileBootstrapOut
from backend.app.services import auth_service
from backend.app.services.auth_service import TokenBundle


def _upsert_device(db: Session, organization_id: str, user_id: str, data: DeviceRegisterIn) -> Device:
    device = db.scalars(
        select(Device).where(
            Device.organization_id == organization_id,
            Device.user_id == user_id,
            Device.device_identifier == data.device_identifier,
        )
    ).first()
    now = utcnow()

    if device:
        if device.trust_status == DeviceTrustStatus.REVOKED:
            raise ValidationAppError("This device has been revoked. Register it again under a new device identifier.")
        device.device_name = data.device_name if data.device_name is not None else device.device_name
        device.platform = data.platform
        device.os_version = data.os_version
        device.app_version = data.app_version
        if data.push_token is not None:
            device.push_token = data.push_token
        device.last_seen_at = now
    else:
        # Registration requires an already-authenticated session, so the device is trusted
        # immediately in this MVP; there is no separate administrator-approval step yet.
        device = Device(
            organization_id=organization_id,
            user_id=user_id,
            device_identifier=data.device_identifier,
            device_name=data.device_name,
            platform=data.platform,
            os_version=data.os_version,
            app_version=data.app_version,
            push_token=data.push_token,
            trust_status=DeviceTrustStatus.TRUSTED,
            trusted_at=now,
            last_seen_at=now,
        )
        db.add(device)

    db.flush()
    return device


def register_device(db: Session, organization_id: str, user_id: str, data: DeviceRegisterIn) -> Device:
    """Registers (or refreshes) the caller's own device for push/session purposes."""
    return _upsert_device(db, organization_id, user_id, data)


def list_devices(db: Session, organization_id: str, user_id: str) -> List[Device]:
    return list(
        db.scalars(
            select(Device)
            .where(Device.organization_id == organization_id, Device.user_id == user_id)
            .order_by(Device.created_at.desc())
        ).all()
    )


def get_device(db: Session, device_id: str, organization_id: str, user_id: str) -> Device:
    device = db.scalars(
        select(Device).where(
            Device.id == device_id,
            Device.organization_id == organization_id,
            Device.user_id == user_id,
        )
    ).first()
    if not device:
        raise NotFoundAppError("Device not found.")
    return device


def revoke_device(db: Session, device_id: str, organization_id: str, user_id: str) -> Device:
    """Mark the device revoked and drop its push token.

    Devices are not linked to refresh tokens (there is no device_id on refresh_tokens), so
    this cannot sign the device's session out by itself. Clients should also end the session
    via DELETE /auth/sessions/{id} (the Security settings "Active sessions" list), which
    revokes both the refresh token and its access token.
    """
    device = get_device(db, device_id, organization_id, user_id)
    if device.trust_status == DeviceTrustStatus.REVOKED:
        raise ValidationAppError("Device is already revoked.")
    device.trust_status = DeviceTrustStatus.REVOKED
    device.revoked_at = utcnow()
    device.revoked_reason = "revoked_by_user"
    device.push_token = None
    db.flush()
    return device


def exchange_native_credentials(
    db: Session,
    email: str,
    password: str,
    device_data: DeviceRegisterIn,
    ip: Optional[str],
    user_agent: Optional[str],
) -> Tuple[TokenBundle, Device]:
    """OAuth-style credential exchange for native (desktop/mobile) clients.

    Authenticates exactly like the web login, then registers/refreshes the calling device as
    part of the same call so native clients only need one round trip to obtain both a session
    and a trusted device record.
    """
    tokens = auth_service.login(db, email, password, ip, user_agent)
    if isinstance(tokens, auth_service.MfaChallenge):
        # Two-factor accounts: finish with POST /auth/login/mfa, then register the device
        # with the resulting session.
        raise AppException(
            message="Two-factor authentication is required. Complete sign-in with /auth/login/mfa.",
            code="MFA_REQUIRED",
            status_code=401,
            details=tokens.as_dict(),
        )
    payload = decode_access_token(tokens.access_token)
    user_id = payload["sub"]
    organization_id = payload["org"]

    device = register_device(db, organization_id, user_id, device_data)
    db.commit()
    db.refresh(device)
    return tokens, device


def build_mobile_bootstrap(db: Session, ctx: CurrentContext) -> MobileBootstrapOut:
    """Compact org/user context for native (desktop/mobile) client startup."""
    me = auth_service.build_me(db, ctx)
    return MobileBootstrapOut(
        user=me.user,
        organization=me.organization,
        membership=me.membership,
        organizations=me.organizations,
        server_time=utcnow(),
    )
