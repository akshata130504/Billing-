"""Sign in with Rooman One (OpenID Connect). Mounted at /auth/rooman-one.

GET  ""          {"enabled": ...} - the login page shows the button only when configured
GET  /start      303 to Rooman One (authorization code + PKCE S256), flow kept in a sealed cookie
GET  /callback   verify, set up the person on first sign-in, 303 to {FRONTEND_URL}/auth/rooman-one#handoff=...
POST /exchange   the one-time hand-over -> the usual sign-in result (tokens or the MFA challenge)

Billing keeps its tokens in localStorage, so the callback cannot set them as cookies; it hands
them over in the URL fragment, which browsers never send to servers or write to access logs.
The logic lives in services/rooman_one_service.py; see docs/rooman-one-sign-in.md.
"""
import hmac
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import client_ip, get_db
from backend.app.core.config import settings
from backend.app.core.exceptions import AppException, NotFoundError
from backend.app.core.logging import logger
from backend.app.core.rate_limit import auth_rate_limit, limiter
from backend.app.schemas.auth import RoomanOneExchangeRequest, RoomanOneExchangeResponse, RoomanOneStatus
from backend.app.services import rooman_one_service as rooman_one
from backend.app.services.email import frontend_url

router = APIRouter()

FLOW_COOKIE = "rb_rooman_one_flow"
COOKIE_PATH = "/api/v1/auth/rooman-one"
TRY_AGAIN = "Your Rooman One sign-in expired or was interrupted. Please try again."
NOT_VERIFIED = "We couldn't verify your Rooman One sign-in. Please try again."
CANCELLED = "Rooman One sign-in was cancelled."


def _require_enabled() -> None:
    if not rooman_one.enabled():
        raise NotFoundError("Sign in with Rooman One is not enabled.")


def _redirect(url: str) -> RedirectResponse:
    response = RedirectResponse(url, status_code=303)
    response.delete_cookie(FLOW_COOKIE, path=COOKIE_PATH)
    return response


def _to_login(message: str) -> RedirectResponse:
    return _redirect(frontend_url("/login") + "?" + urlencode({"sso_error": message}))


@router.get("", response_model=RoomanOneStatus, summary="Whether 'Sign in with Rooman One' is enabled")
def status() -> RoomanOneStatus:
    return RoomanOneStatus(enabled=rooman_one.enabled())


@router.get("/start", summary="Begin 'Sign in with Rooman One' (303 to Rooman One)")
@limiter.limit(auth_rate_limit)
def start(request: Request, next: Optional[str] = None) -> RedirectResponse:
    _require_enabled()
    flow = rooman_one.new_flow()
    authorize = rooman_one.discovery()["authorization_endpoint"]
    params = {
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": settings.OIDC_REDIRECT_URI or "",
        "response_type": "code",
        "scope": rooman_one.SCOPES,
        "state": flow["state"],
        "nonce": flow["nonce"],
        "code_challenge": flow["challenge"],
        "code_challenge_method": "S256",
    }
    response = RedirectResponse(f"{authorize}{'&' if '?' in authorize else '?'}{urlencode(params)}", status_code=303)
    sealed = rooman_one.seal(
        {"state": flow["state"], "nonce": flow["nonce"], "verifier": flow["verifier"], "next": rooman_one.safe_next(next)}
    )
    response.set_cookie(
        FLOW_COOKIE,
        sealed,
        max_age=rooman_one.FLOW_TTL_SECONDS,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.SECURE_COOKIES,
        samesite="lax",
    )
    return response


@router.get("/callback", summary="Rooman One redirects here after sign-in (303 to the app)")
@limiter.limit(auth_rate_limit)
def callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    _require_enabled()
    flow = rooman_one.unseal(request.cookies.get(FLOW_COOKIE))
    if flow is None or not state or not hmac.compare_digest(state, str(flow.get("state") or "")):
        return _to_login(TRY_AGAIN)
    if error or not code:
        return _to_login(CANCELLED)
    if not rooman_one.use_once("state", state, rooman_one.FLOW_TTL_SECONDS):
        return _to_login(TRY_AGAIN)

    try:
        id_token = rooman_one.exchange_code(code, str(flow["verifier"]))
        claims = rooman_one.verify_id_token(id_token, str(flow["nonce"]))
    except Exception as exc:  # any network, protocol or signature problem: never sign in
        logger.warning("Rooman One sign-in rejected: %s: %s", type(exc).__name__, exc)
        return _to_login(NOT_VERIFIED)

    ip, user_agent = client_ip(request), (request.headers.get("user-agent") or "")[:400] or None
    try:
        result = rooman_one.sign_in(db, claims, ip, user_agent)
    except AppException as exc:
        db.rollback()
        return _to_login(exc.message)

    handoff = rooman_one.make_handoff(result, str(flow.get("next") or ""))
    return _redirect(frontend_url("/auth/rooman-one") + "#" + urlencode({"handoff": handoff}))


@router.post(
    "/exchange",
    response_model=RoomanOneExchangeResponse,
    response_model_exclude_none=True,
    summary="Redeem the one-time hand-over for the sign-in result",
)
@limiter.limit(auth_rate_limit)
def exchange(request: Request, payload: RoomanOneExchangeRequest) -> RoomanOneExchangeResponse:
    _require_enabled()
    result, next_path = rooman_one.redeem_handoff(payload.handoff)
    return RoomanOneExchangeResponse(**result, next=next_path)
