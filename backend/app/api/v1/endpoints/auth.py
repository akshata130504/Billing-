"""Authentication endpoints (contract §2). Mounted at /auth."""
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, client_ip, get_current_context, get_db
from backend.app.core.rate_limit import auth_rate_limit, limiter
from backend.app.schemas.auth import (
    AcceptInvitationRequest,
    AuthTokens,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    InvitationOut,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    SwitchOrganizationRequest,
)
from backend.app.services import auth_service

router = APIRouter()


def _ua(request: Request) -> str | None:
    return (request.headers.get("user-agent") or "")[:400] or None


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization and its owner account",
)
@limiter.limit(auth_rate_limit)
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)) -> SignupResponse:
    tokens, ctx = auth_service.signup(db, payload, ip=client_ip(request), user_agent=_ua(request))
    return SignupResponse(**tokens.as_dict(), me=auth_service.build_me(db, ctx))


@router.post("/login", response_model=AuthTokens, summary="Sign in with email and password")
@limiter.limit(auth_rate_limit)
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)) -> AuthTokens:
    tokens = auth_service.login(db, payload.email, payload.password, ip=client_ip(request), user_agent=_ua(request))
    return AuthTokens(**tokens.as_dict())


@router.post("/refresh", response_model=AuthTokens, summary="Rotate a refresh token")
def refresh(request: Request, payload: RefreshRequest, db: Session = Depends(get_db)) -> AuthTokens:
    tokens = auth_service.refresh(db, payload.refresh_token, ip=client_ip(request), user_agent=_ua(request))
    return AuthTokens(**tokens.as_dict())


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
    summary="Revoke a refresh token",
)
def logout(
    payload: LogoutRequest,
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> Response:
    auth_service.logout(db, ctx, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse, summary="Current user, organization and membership")
def me(ctx: CurrentContext = Depends(get_current_context), db: Session = Depends(get_db)) -> MeResponse:
    return auth_service.build_me(db, ctx)


@router.post("/switch-organization", response_model=AuthTokens, summary="Issue tokens for another organization")
def switch_organization(
    request: Request,
    payload: SwitchOrganizationRequest,
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> AuthTokens:
    tokens = auth_service.switch_organization(
        db, ctx, payload.organization_id, ip=client_ip(request), user_agent=_ua(request)
    )
    return AuthTokens(**tokens.as_dict())


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
    summary="Change the current user's password (revokes other sessions)",
)
def change_password(
    payload: ChangePasswordRequest,
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> Response:
    auth_service.change_password(
        db, ctx, payload.current_password, payload.new_password, keep_refresh_token=payload.refresh_token
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset link",
)
@limiter.limit(auth_rate_limit)
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> ForgotPasswordResponse:
    message, reset_url = auth_service.forgot_password(db, payload.email, ip=client_ip(request), user_agent=_ua(request))
    return ForgotPasswordResponse(message=message, reset_url=reset_url)


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
    summary="Set a new password using a reset token",
)
@limiter.limit(auth_rate_limit)
def reset_password(request: Request, payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> Response:
    auth_service.reset_password(db, payload.token, payload.new_password, ip=client_ip(request), user_agent=_ua(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/invitations/{token}", response_model=InvitationOut, summary="Preview a team invitation")
def get_invitation(token: str, db: Session = Depends(get_db)) -> InvitationOut:
    return InvitationOut(**auth_service.get_invitation(db, token))


@router.post("/accept-invitation", response_model=AuthTokens, summary="Accept a team invitation")
@limiter.limit(auth_rate_limit)
def accept_invitation(request: Request, payload: AcceptInvitationRequest, db: Session = Depends(get_db)) -> AuthTokens:
    tokens = auth_service.accept_invitation(
        db, payload.token, payload.full_name, payload.password, ip=client_ip(request), user_agent=_ua(request)
    )
    return AuthTokens(**tokens.as_dict())
