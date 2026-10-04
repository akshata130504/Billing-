"""Tenant access grants (docs/platform-administration-design.md sections 6, 7, 12 and 15).

The ONLY way platform staff can read a tenant's data: one organization, named read-only scopes, a
reason and ticket, a short expiry, and the tenant Owner's approval - or, for break-glass emergency
access, a SECOND Platform Administrator's approval. No Membership is created or faked; the tenant
API recognises a short-lived grant token and re-validates this row on every request.

Not a TenantMixin table on purpose: the platform reads grants across organizations. Rows are never
deleted (ON DELETE RESTRICT everywhere) - they are the record of who could see what, and when.
"""
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)

from backend.app.core.database import Base
from backend.app.models.base import UUIDPrimaryKeyMixin, utcnow


class GrantStatus(str, enum.Enum):
    PENDING = "pending"  # waiting for the tenant Owner (or, emergency, a second Administrator)
    APPROVED = "approved"  # approved, not entered yet; expiry clock already running
    ACTIVE = "active"  # entered at least once; still inside its expiry
    DENIED = "denied"
    CANCELLED = "cancelled"  # withdrawn by the requester before a decision
    REVOKED = "revoked"
    EXPIRED = "expired"


OPEN_STATUSES = (GrantStatus.PENDING, GrantStatus.APPROVED, GrantStatus.ACTIVE)


class GrantScope(str, enum.Enum):
    """Read-only scopes (design section 7). No write scope is offered in this release."""

    READ_METADATA = "READ_METADATA"  # always included
    READ_CUSTOMERS = "READ_CUSTOMERS"
    READ_QUOTES = "READ_QUOTES"
    READ_INVOICES = "READ_INVOICES"
    READ_PAYMENTS = "READ_PAYMENTS"
    READ_SUBSCRIPTIONS = "READ_SUBSCRIPTIONS"
    READ_AUDIT = "READ_AUDIT"
    READ_CONFIG = "READ_CONFIG"


class TenantAccessGrant(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tenant_access_grants"
    __table_args__ = (
        CheckConstraint(
            "approved_by_staff_id IS NULL OR approved_by_staff_id <> requested_by_staff_id",
            name="ck_grant_approver_not_requester",
        ),
        CheckConstraint("expires_at IS NULL OR approved_at IS NULL OR expires_at > approved_at", name="ck_grant_expiry_after_approval"),
        CheckConstraint("NOT is_emergency OR approved_by_user_id IS NULL", name="ck_grant_emergency_staff_approval"),
        CheckConstraint("requested_duration_minutes BETWEEN 5 AND 240", name="ck_grant_duration"),
        Index("ix_tenant_access_grants_org_status", "organization_id", "status"),
        Index("ix_tenant_access_grants_staff_status", "requested_by_staff_id", "status"),
        # At most one open (pending / approved / active) grant per staff member per organization.
        Index(
            "uq_tenant_access_grants_one_open", "requested_by_staff_id", "organization_id", unique=True,
            postgresql_where=text("status IN ('pending', 'approved', 'active')"),
            sqlite_where=text("status IN ('pending', 'approved', 'active')"),
        ),
    )

    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    requested_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)
    status = Column(String(16), nullable=False, default=GrantStatus.PENDING.value, index=True)
    scopes = Column(JSON, nullable=False)
    reason = Column(Text, nullable=False)
    ticket_ref = Column(String(100), nullable=False)
    requested_duration_minutes = Column(Integer, nullable=False)
    is_emergency = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    first_used_at = Column(DateTime(timezone=True), nullable=True)
    last_entered_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by_kind = Column(String(16), nullable=True)  # tenant_user | platform_staff | system
    revoked_by_id = Column(String(36), nullable=True)
    revoke_reason = Column(String(300), nullable=True)
    denied_at = Column(DateTime(timezone=True), nullable=True)
    denied_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    denied_reason = Column(String(300), nullable=True)
    # The one grant token currently allowed to act (Exit clears it; re-entering issues a new one).
    current_token_jti = Column(String(64), nullable=True)
    request_count = Column(Integer, nullable=False, default=0)
    # Emergency post-incident review (design section 12).
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)
    review_notes = Column(Text, nullable=True)
