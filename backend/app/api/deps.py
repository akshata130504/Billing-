"""FastAPI dependencies: database session, authenticated user, tenant context, RBAC."""
from dataclasses import dataclass
from typing import Callable, Optional

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.exceptions import ForbiddenError, UnauthorizedError
from backend.app.core.security import decode_access_token
from backend.app.models import ROLE_RANK, Membership, MemberRole, MembershipStatus, Organization, User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentContext:
    """Everything a request handler needs to know about who is calling."""

    user: User
    organization: Organization
    membership: Membership
    ip_address: Optional[str]
    user_agent: Optional[str]

    @property
    def role(self) -> MemberRole:
        return self.membership.role

    @property
    def organization_id(self) -> str:
        return self.organization.id

    def has_role(self, minimum: MemberRole) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[minimum]


def client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


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
    # Stash the org claim so get_current_context can pick the right membership.
    user._token_org_id = payload.get("org")  # type: ignore[attr-defined]
    return user


def get_current_context(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentContext:
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
    return CurrentContext(
        user=user,
        organization=organization,
        membership=membership,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
    )


def require_role(minimum: MemberRole) -> Callable[..., CurrentContext]:
    """Dependency factory: `ctx: CurrentContext = Depends(require_role(MemberRole.FINANCE))`."""

    def dependency(ctx: CurrentContext = Depends(get_current_context)) -> CurrentContext:
        if not ctx.has_role(minimum):
            raise ForbiddenError(f"This action requires the {minimum.value} role or higher.")
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
]
