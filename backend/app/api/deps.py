"""FastAPI dependencies: database session, authenticated user, tenant context, RBAC."""
import ipaddress
from dataclasses import dataclass
from functools import lru_cache
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.exceptions import ForbiddenError, UnauthorizedError
from backend.app.core.security import GRANT_TOKEN_TYPE, decode_access_token, peek_token_type
from backend.app.models import ROLE_RANK, Membership, MemberRole, MembershipStatus, Organization, OrganizationStatus, RefreshToken, User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentContext:
    """Everything a request handler needs to know about who is calling.

    Normally a tenant user with an active Membership. Under a platform access grant (see
    services/access_grant_service.py) `user` and `membership` are None and `grant` describes the
    platform staff member: no Membership is created or faked, and only the read routes allowed by
    the grant's scopes (core/grant_scopes.py) are reachable.
    """

    user: Optional[User]
    organization: Organization
    membership: Optional[Membership]
    ip_address: Optional[str]
    user_agent: Optional[str]
    grant: Optional[Any] = None

    @property
    def user_id(self) -> Optional[str]:
        return self.user.id if self.user is not None else None

    @property
    def role(self) -> MemberRole:
        return self.membership.role if self.membership is not None else MemberRole.VIEWER

    @property
    def organization_id(self) -> str:
        return self.organization.id

    @property
    def is_platform_grant(self) -> bool:
        return self.grant is not None

    @property
    def actor_label(self) -> str:
        if self.grant is not None:
            return self.grant.actor_label
        return self.user.full_name if self.user is not None else "System"

    def has_role(self, minimum: MemberRole) -> bool:
        # Grant contexts only ever reach routes on the explicit read allow-list, which was checked
        # when the context was built; tenant role ranks do not apply to them.
        if self.grant is not None:
            return True
        return ROLE_RANK[self.role] >= ROLE_RANK[minimum]


def _is_trusted_proxy_peer(host: str) -> bool:
    """Our own reverse proxy (the nginx `frontend` container) reaches the API over the private
    compose network, so only peers inside settings.TRUSTED_PROXIES (default: RFC 1918,
    loopback and IPv6 ULA ranges) may vouch for the client address."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return any(addr.version == net.version and addr in net for net in _trusted_networks(tuple(settings.TRUSTED_PROXIES)))


@lru_cache(maxsize=8)
def _trusted_networks(cidrs: tuple) -> tuple:
    return tuple(ipaddress.ip_network(c, strict=False) for c in cidrs)


def client_ip(request: Request) -> Optional[str]:
    """The real client address, used for rate limiting, login throttling and audit rows.

    X-Forwarded-For is NOT used: its leftmost entry is whatever the client sent, so anyone could
    pick their own rate-limit bucket. Instead we read X-Real-IP, which frontend/docker/nginx.conf
    overwrites on every request with the address nginx itself resolved (the TCP peer, or - when
    Caddy fronts nginx - Caddy's peer via the realip module). It is only honoured when the
    request's TCP peer is inside TRUSTED_PROXIES (i.e. came through our proxy); a directly
    exposed API ignores it and uses the socket address.
    """
    peer = request.client.host if request.client else None
    if peer and _is_trusted_proxy_peer(peer):
        real_ip = (request.headers.get("x-real-ip") or "").strip()
        if real_ip:
            try:
                return str(ipaddress.ip_address(real_ip))
            except ValueError:
                pass
    return peer


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError()
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Access token has expired.")
    except jwt.PyJWTError:
        raise UnauthorizedError("Access token is invalid.")

    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise UnauthorizedError("User account is inactive or no longer exists.")

    if user.tokens_valid_after is not None:
        token_iat = payload.get("iat")
        if token_iat is None or not isinstance(token_iat, (int, float)):
            raise UnauthorizedError("Access token is invalid.")
        try:
            token_issued_at = datetime.fromtimestamp(token_iat, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            raise UnauthorizedError("Access token is invalid.")

        valid_after = user.tokens_valid_after
        if valid_after.tzinfo is None:
            valid_after = valid_after.replace(tzinfo=timezone.utc)

        if token_issued_at < valid_after:
            raise UnauthorizedError("Access token has been revoked.")

    # Access tokens are bound to the refresh-token row ("session") they were issued with.
    # A session revoked explicitly (logout of one device, DELETE /auth/sessions/{id}, password
    # change) kills its access token too. Rows revoked by normal rotation (replaced_by_id set)
    # are not checked so in-flight requests racing a refresh keep working until expiry.
    session_id = payload.get("sid")
    if session_id:
        session = db.get(RefreshToken, session_id)
        if session is None or (session.revoked_at is not None and session.replaced_by_id is None):
            raise UnauthorizedError("Access token has been revoked.")

    # Stash the org claim so get_current_context can pick the right membership.
    user._token_org_id = payload.get("org")  # type: ignore[attr-defined]
    user._token_session_id = session_id  # type: ignore[attr-defined]
    return user


def _grant_context(request: Request, token: str, db: Session, *, enforce_scope: bool = True) -> CurrentContext:
    from backend.app.services import access_grant_service

    route = request.scope.get("route")
    principal = access_grant_service.authenticate(
        db, token, method=request.method, route_template=getattr(route, "path", None),
        path_params=dict(request.path_params or {}), ip=client_ip(request),
        ua=(request.headers.get("user-agent") or "")[:400] or None, enforce_scope=enforce_scope,
    )
    from backend.app.core.tenant_context import set_tenant_context
    set_tenant_context(principal.organization.id)
    return CurrentContext(
        user=None, organization=principal.organization, membership=None, ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400] or None, grant=principal,
    )


async def get_current_context(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentContext:
    if credentials is not None and credentials.scheme.lower() == "bearer" and peek_token_type(credentials.credentials) == GRANT_TOKEN_TYPE:
        ctx = _grant_context(request, credentials.credentials, db)
        from backend.app.core.tenant_context import set_tenant_context
        set_tenant_context(ctx.organization_id)
        return ctx
    user = get_current_user(credentials, db)
    org_id = getattr(user, "_token_org_id", None)
    stmt = select(Membership).where(
        Membership.user_id == user.id,
        Membership.status == MembershipStatus.ACTIVE,
    )
    if org_id:
        stmt = stmt.where(Membership.organization_id == org_id)
    membership = db.scalars(stmt.order_by(Membership.created_at)).first()
    if membership is None:
        raise UnauthorizedError("You are not an active member of this organization.")
    organization = db.get(Organization, membership.organization_id)
    if organization is None:
        raise UnauthorizedError("Organization no longer exists.")
    from backend.app.core.tenant_context import set_tenant_context
    set_tenant_context(organization.id)
    return CurrentContext(
        user=user,
        organization=organization,
        membership=membership,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
    )


async def require_grant_context(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentContext:
    """Only a valid grant token (the platform-access session/exit endpoints). Tenant users get 401."""
    if credentials is None or credentials.scheme.lower() != "bearer" or peek_token_type(credentials.credentials) != GRANT_TOKEN_TYPE:
        raise UnauthorizedError("Platform access token required.")
    ctx = _grant_context(request, credentials.credentials, db, enforce_scope=False)
    from backend.app.core.tenant_context import set_tenant_context
    set_tenant_context(ctx.organization_id)
    return ctx


_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class OrganizationNotActiveError(ForbiddenError):
    """403 with a machine-readable code so the SPA can show the right lifecycle screen."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


# Reachable while a trial has ended: what the organization needs to see its state and ask for a
# subscription (everything else answers ORGANIZATION_TRIAL_EXPIRED). /api/v1-relative prefixes.
TRIAL_EXPIRED_ALLOWED = ("/subscription-requests", "/ui-config", "/organization")


def _api_path(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None) or request.url.path
    prefix = settings.API_V1_STR
    return path[len(prefix):] if path.startswith(prefix) else path


def _path_allowed(path: str, prefixes) -> bool:
    return any(path == p or path.startswith(p + "/") for p in prefixes)


def _check_org_active(ctx: CurrentContext, method: str, path: str = "", db: Optional[Session] = None) -> None:
    """Organization lifecycle gate for tenant users (docs/platform-administration-design.md §8).

    - pending_approval / rejected: no business endpoints (self-service /auth/* still works).
    - suspended: Owner and Admin read-only; Finance and Viewer refused; every write refused.
    - pending_deletion: Owner read-only (data export); everyone else refused.
    - deleted: refused.
    - trial: every module (the trial's ending is computed from trial_ends_at on each request).
    - trial_expired: only TRIAL_EXPIRED_ALLOWED (status, subscription request).
    Then, for an organization whose access is 'entitled', a path belonging to a product module the
    organization is not entitled to answers FEATURE_NOT_ENTITLED (services/org_access.py).
    """
    from backend.app.services import org_access

    org = ctx.organization
    if org is None:
        return
    st = org_access.effective_status(org).value
    is_read = method.upper() in _READ_METHODS
    if st == OrganizationStatus.TRIAL_EXPIRED.value:
        if _path_allowed(path, TRIAL_EXPIRED_ALLOWED):
            return
        raise OrganizationNotActiveError(
            "Your free trial has ended. Choose your modules and request a subscription to continue.",
            "ORGANIZATION_TRIAL_EXPIRED",
        )
    if st == OrganizationStatus.PENDING_APPROVAL.value:
        raise OrganizationNotActiveError("Your organization is pending approval from Rooman.", "ORGANIZATION_PENDING_APPROVAL")
    if st == OrganizationStatus.REJECTED.value:
        msg = f"Your organization registration was rejected: {org.status_reason}" if org.status_reason else "Your organization registration was rejected."
        raise OrganizationNotActiveError(msg, "ORGANIZATION_REJECTED")
    if st == OrganizationStatus.SUSPENDED.value:
        if ROLE_RANK[ctx.role] < ROLE_RANK[MemberRole.ADMIN]:
            raise OrganizationNotActiveError(
                "Your organization is suspended. Contact your organization Owner.", "ORGANIZATION_SUSPENDED"
            )
        if not is_read:
            raise OrganizationNotActiveError(
                "Your organization is suspended and is read-only until it is reactivated.", "ORGANIZATION_SUSPENDED"
            )
        return
    if st == OrganizationStatus.PENDING_DELETION.value:
        if ctx.role == MemberRole.OWNER and is_read:
            return
        raise OrganizationNotActiveError("This organization is scheduled for deletion.", "ORGANIZATION_PENDING_DELETION")
    if st == OrganizationStatus.DELETED.value:
        raise OrganizationNotActiveError("This organization is not active.", "ORGANIZATION_DELETED")
    if db is not None and not org_access.is_unrestricted(org):
        from backend.app.core.entitlements import module_for_path

        module = module_for_path(path)
        if module is not None and module not in org_access.entitled_modules(db, org):
            raise OrganizationNotActiveError(
                "Your subscription does not include this module. Ask Rooman to add it to your plan.",
                "FEATURE_NOT_ENTITLED",
            )


def require_tenant_user(minimum: MemberRole) -> Callable[..., CurrentContext]:
    """Like require_role, but NEVER satisfied by a platform grant (e.g. deciding on grants)."""

    def dependency(
        request: Request, ctx: CurrentContext = Depends(get_current_context), db: Session = Depends(get_db)
    ) -> CurrentContext:
        if ctx.grant is not None or ctx.user is None:
            raise ForbiddenError("This action can only be performed by a member of this organization.")
        _check_org_active(ctx, request.method, _api_path(request), db)
        if not ctx.has_role(minimum):
            raise ForbiddenError(f"This action requires the {minimum.value} role or higher.")
        from backend.app.core.tenant_context import set_tenant_context
        set_tenant_context(ctx.organization_id)
        return ctx

    return dependency


def require_role(minimum: MemberRole) -> Callable[..., CurrentContext]:
    """Dependency factory: `ctx: CurrentContext = Depends(require_role(MemberRole.FINANCE))`."""

    def dependency(
        request: Request, ctx: CurrentContext = Depends(get_current_context), db: Session = Depends(get_db)
    ) -> CurrentContext:
        if ctx.grant is None:
            _check_org_active(ctx, request.method, _api_path(request), db)
        if not ctx.has_role(minimum):
            raise ForbiddenError(f"This action requires the {minimum.value} role or higher.")
        from backend.app.core.tenant_context import set_tenant_context
        set_tenant_context(ctx.organization_id)
        return ctx

    return dependency


# Convenience aliases used across endpoint modules.
require_viewer = require_role(MemberRole.VIEWER)
require_finance = require_role(MemberRole.FINANCE)
require_admin = require_role(MemberRole.ADMIN)
require_owner = require_role(MemberRole.OWNER)

__all__ = [
    "CurrentContext",
    "client_ip",
    "get_db",
    "get_current_user",
    "get_current_context",
    "require_role",
    "require_viewer",
    "require_finance",
    "require_admin",
    "require_owner",
    "require_grant_context",
    "require_tenant_user",
]
