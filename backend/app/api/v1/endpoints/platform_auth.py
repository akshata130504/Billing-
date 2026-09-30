"""Platform (Rooman staff) authentication. Mounted at /platform/auth.

Entirely separate from /auth (tenant users): its own principal (PlatformStaff), mandatory TOTP,
its own sessions and signing key, and HttpOnly cookies scoped to the platform API paths. Tenant
tokens are not accepted anywhere here, and nothing here can reach tenant data.

    POST /login     email + password  -> single-use 2FA challenge (no session yet)
    POST /2fa       challenge + TOTP  -> session cookies
    POST /refresh   refresh cookie    -> rotated session cookies        (CSRF header required)
    GET  /me        current staff member and session
    GET  /sessions  the caller's active sessions
    DELETE /sessions/{id}             revoke one of the caller's sessions
    POST /logout    end this session
    POST /logout-all end every session of the caller
"""
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import client_ip, get_db
from backend.app.api.platform_deps import (
    PlatformContext,
    check_csrf,
    clear_session_cookies,
    read_csrf_cookie,
    read_refresh_cookie,
    require_platform_staff,
    set_session_cookies,
    user_agent,
)
from backend.app.core.config import settings
from backend.app.core.exceptions import UnauthorizedError
from backend.app.core.rate_limit import auth_rate_limit, limiter
from backend.app.core.security import generate_opaque_token
from backend.app.schemas.platform import (
    PlatformLoginChallengeOut,
    PlatformLoginRequest,
    PlatformLogoutAllOut,
    PlatformMeOut,
    PlatformSessionOut,
    PlatformSessionsOut,
    PlatformStaffOut,
    PlatformTwoFactorRequest,
)
from backend.app.services import platform_auth_service

router = APIRouter()


def _staff_out(staff) -> PlatformStaffOut:
    return PlatformStaffOut(
        id=staff.id, email=staff.email, full_name=staff.full_name, role=staff.role.value, last_login_at=staff.last_login_at
    )


def _me(staff, session) -> PlatformMeOut:
    return PlatformMeOut(
        staff=_staff_out(staff),
        session_id=session.id,
        session_expires_at=session.expires_at,
        access_expires_in=settings.PLATFORM_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.post("/login", response_model=PlatformLoginChallengeOut, summary="Platform sign-in, step 1: email and password")
@limiter.limit(auth_rate_limit)
def platform_login(request: Request, response: Response, body: PlatformLoginRequest, db: Session = Depends(get_db)):
    _no_store(response)
    issued = platform_auth_service.login(db, body.email, body.password, client_ip(request), user_agent(request))
    return PlatformLoginChallengeOut(challenge_token=issued.challenge_token, expires_in=issued.expires_in)


@router.post("/2fa", response_model=PlatformMeOut, summary="Platform sign-in, step 2: TOTP code (mandatory)")
@limiter.limit(auth_rate_limit)
def platform_two_factor(request: Request, response: Response, body: PlatformTwoFactorRequest, db: Session = Depends(get_db)):
    _no_store(response)
    est = platform_auth_service.verify_2fa(db, body.challenge_token, body.code, client_ip(request), user_agent(request))
    set_session_cookies(response, est.access_token, est.refresh_secret, generate_opaque_token(24))
    return _me(est.staff, est.session)


@router.post("/refresh", response_model=PlatformMeOut, summary="Rotate the platform session and issue a new access token")
@limiter.limit(auth_rate_limit)
def platform_refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    _no_store(response)
    platform_auth_service.ensure_enabled()
    check_csrf(request)
    secret = read_refresh_cookie(request)
    if not secret:
        raise UnauthorizedError(platform_auth_service.SESSION_INVALID)
    est = platform_auth_service.refresh(db, secret, client_ip(request), user_agent(request))
    # The CSRF value stays the same across refreshes (it already passed check_csrf above).
    set_session_cookies(response, est.access_token, est.refresh_secret, read_csrf_cookie(request))
    return _me(est.staff, est.session)


@router.get("/me", response_model=PlatformMeOut, summary="Current platform staff member and session")
def platform_me(response: Response, ctx: PlatformContext = Depends(require_platform_staff)):
    _no_store(response)
    return _me(ctx.staff, ctx.session)


@router.get("/sessions", response_model=PlatformSessionsOut, summary="The caller's active platform sessions")
def platform_sessions(response: Response, ctx: PlatformContext = Depends(require_platform_staff), db: Session = Depends(get_db)):
    _no_store(response)
    rows = platform_auth_service.active_sessions(db, ctx.staff)
    return PlatformSessionsOut(
        sessions=[
            PlatformSessionOut(
                id=s.id, created_at=s.created_at, last_used_at=s.last_used_at, expires_at=s.expires_at,
                ip_address=s.ip_address, user_agent=s.user_agent, current=s.id == ctx.session.id,
            )
            for s in rows
        ]
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
               summary="Revoke one of the caller's platform sessions")
def platform_revoke_session(session_id: str, ctx: PlatformContext = Depends(require_platform_staff), db: Session = Depends(get_db)):
    platform_auth_service.revoke_session(db, ctx.staff, ctx.session, session_id, ctx.ip_address, ctx.user_agent)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    if session_id == ctx.session.id:
        clear_session_cookies(response)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, summary="End this platform session")
def platform_logout(ctx: PlatformContext = Depends(require_platform_staff), db: Session = Depends(get_db)):
    platform_auth_service.logout(db, ctx.staff, ctx.session, ctx.ip_address, ctx.user_agent)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookies(response)
    return response


@router.post("/logout-all", response_model=PlatformLogoutAllOut, summary="End every platform session of the caller")
def platform_logout_all(response: Response, ctx: PlatformContext = Depends(require_platform_staff), db: Session = Depends(get_db)):
    count = platform_auth_service.logout_all(db, ctx.staff, ctx.session, ctx.ip_address, ctx.user_agent)
    clear_session_cookies(response)
    return PlatformLogoutAllOut(sessions_revoked=count)

