"""Authentication endpoints (contract §2). Mounted at /auth."""
from typing import List

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
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
    LoginResponse,
    LogoutRequest,
    MeResponse,
    MfaLoginRequest,
    RefreshRequest,
    ResendOtpRequest,
    ResetPasswordRequest,
    SessionOut,
    SignupResponse,
    SignupVerificationRequest,
    SignupVerificationResponse,
    SignupVerifyOtpRequest,
    SwitchOrganizationRequest,
    TotpDisableRequest,
    TotpEnableRequest,
    TotpSetupResponse,
    UserOut,
)
from backend.app.services import auth_service, avatar_service

router = APIRouter()


def _ua(request: Request) -> str | None:
    return (request.headers.get("user-agent") or "")[:400] or None


@router.post(
    "/signup/request-verification",
    response_model=SignupVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate signup details and dispatch email OTP verification",
)
@limiter.limit(auth_rate_limit)
def request_signup_verification(
    request: Request,
    payload: SignupVerificationRequest,
    db: Session = Depends(get_db),
) -> SignupVerificationResponse:
    email, expires_in, cooldown = auth_service.request_signup_verification(
        db, payload, ip=client_ip(request), user_agent=_ua(request)
    )
    return SignupVerificationResponse(
        message="A 6-digit verification code has been sent to your work email.",
        email=email,
        expires_in_seconds=expires_in,
        resend_cooldown_seconds=cooldown,
    )


@router.post(
    "/signup/resend-otp",
    response_model=SignupVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend a new 6-digit OTP to the pending signup email",
)
@limiter.limit(auth_rate_limit)
def resend_signup_otp(
    request: Request,
    payload: ResendOtpRequest,
    db: Session = Depends(get_db),
) -> SignupVerificationResponse:
    email, expires_in, cooldown = auth_service.resend_signup_otp(db, payload.email)
    return SignupVerificationResponse(
        message="A new verification code has been sent to your work email.",
        email=email,
        expires_in_seconds=expires_in,
        resend_cooldown_seconds=cooldown,
    )


@router.post(
    "/signup/verify-otp",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Verify OTP, finalize registration and activate organization owner account",
)
@limiter.limit(auth_rate_limit)
def verify_signup_otp(
    request: Request,
    payload: SignupVerifyOtpRequest,
    db: Session = Depends(get_db),
) -> SignupResponse:
    tokens, ctx = auth_service.verify_signup_otp(
        db, payload.email, payload.otp, payload.password, ip=client_ip(request), user_agent=_ua(request)
    )
    return SignupResponse(**tokens.as_dict(), me=auth_service.build_me(db, ctx))


@router.post(
    "/signup",
    status_code=status.HTTP_410_GONE,
    summary="Removed: use /signup/request-verification + /signup/verify-otp",
    deprecated=True,
)
def signup() -> JSONResponse:
    # The one-step signup skipped email verification; only the OTP flow creates accounts now.
    return JSONResponse(
        status_code=status.HTTP_410_GONE,
        content={
            "error": {
                "code": "GONE",
                "message": "This endpoint was removed. Use /auth/signup/request-verification and /auth/signup/verify-otp.",
                "details": {},
            }
        },
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    response_model_exclude_none=True,
    summary="Sign in with email and password (returns an MFA challenge when 2FA is on)",
)
@limiter.limit(auth_rate_limit)
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    result = auth_service.login(db, payload.email, payload.password, ip=client_ip(request), user_agent=_ua(request))
    return LoginResponse(**result.as_dict())


@router.post("/login/mfa", response_model=AuthTokens, summary="Complete a two-factor sign-in with a TOTP code")
@limiter.limit(auth_rate_limit)
def login_mfa(request: Request, payload: MfaLoginRequest, db: Session = Depends(get_db)) -> AuthTokens:
    tokens = auth_service.login_mfa(db, payload.mfa_token, payload.code, ip=client_ip(request), user_agent=_ua(request))
    return AuthTokens(**tokens.as_dict())


@router.post("/2fa/setup", response_model=TotpSetupResponse, summary="Start two-factor enrolment (new TOTP seed)")
def setup_two_factor(
    ctx: CurrentContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> TotpSetupResponse:
    return TotpSetupResponse(**auth_service.setup_totp(db, ctx))


@router.post(
    "/2fa/enable",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
    summary="Confirm enrolment with a code from the authenticator app",
)
@limiter.limit(auth_rate_limit)
def enable_two_factor(
    request: Request,
    payload: TotpEnableRequest,
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> Response:
    auth_service.enable_totp(db, ctx, payload.code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/2fa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
    summary="Turn two-factor authentication off (password + current code)",
)
@limiter.limit(auth_rate_limit)
def disable_two_factor(
    request: Request,
    payload: TotpDisableRequest,
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> Response:
    auth_service.disable_totp(db, ctx, payload.password, payload.code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=List[SessionOut], summary="The current user's signed-in sessions")
def list_sessions(ctx: CurrentContext = Depends(get_current_context), db: Session = Depends(get_db)) -> List[SessionOut]:
    current = getattr(ctx.user, "_token_session_id", None)
    return [SessionOut(**row) for row in auth_service.list_sessions(db, ctx, current)]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
    summary="Sign out one session (revokes its refresh token and access token)",
)
def revoke_session(
    session_id: str, ctx: CurrentContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> Response:
    auth_service.revoke_session(db, ctx, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.post("/me/avatar", response_model=UserOut, summary="Upload current user's profile photo")
async def upload_my_avatar(
    file: UploadFile = File(...),
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> UserOut:
    user = await avatar_service.save_avatar(db, ctx.user, file)
    return UserOut.model_validate(user)


@router.delete("/me/avatar", response_model=UserOut, summary="Remove current user's profile photo")
def delete_my_avatar(
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> UserOut:
    user = avatar_service.delete_avatar(db, ctx.user)
    return UserOut.model_validate(user)


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
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset link",
)
@limiter.limit(auth_rate_limit)
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> ForgotPasswordResponse:
    message = auth_service.forgot_password(db, payload.email, ip=client_ip(request), user_agent=_ua(request))
    return ForgotPasswordResponse(message=message)


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
        db,
        payload.token,
        payload.full_name,
        payload.password,
        ip=client_ip(request),
        user_agent=_ua(request),
        totp_code=payload.totp_code,
    )
    return AuthTokens(**tokens.as_dict())
