"""Trial -> subscription request -> entitlement (docs: trial & subscription lifecycle).

- organization_entitlements: the product modules (core/modules.json) an organization may use.
  Read only when organizations.module_access is 'entitled'; organizations created before the
  lifecycle existed are 'unrestricted' and keep every module.
- subscription_requests: what a trial organization asks Rooman for (modules, seats, billing
  cycle). A Platform Administrator approves (optionally modifying it) or rejects it. At most one
  open ('submitted') request per organization (partial unique index).

Both are tenant tables (TenantMixin, PostgreSQL row level security): tenant code only ever sees its
own organization's rows; platform code reads them under tenant_context(org) / system_context().
Nothing here stores money, payment details or credentials.
"""
import enum

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, text

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ModuleAccess(str, enum.Enum):
    """How the API decides which product modules an organization may use."""

    UNRESTRICTED = "unrestricted"  # organizations that existed before entitlements (every module)
    # Self-service signup: once a Platform Administrator approves the organization it gets a free trial
    # (every module until trial_ends_at), then only the subscription screen until a subscription
    # request is approved (-> ENTITLED).
    TRIAL = "trial"
    ENTITLED = "entitled"  # only base modules + organization_entitlements rows


class BillingCycle(str, enum.Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class SubscriptionRequestStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


def _enum(cls, name: str, length: int):
    return Enum(cls, name=name, native_enum=False, create_constraint=False, length=length,
                values_callable=lambda members: [m.value for m in members], validate_strings=True)


class OrganizationEntitlement(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "organization_entitlements"
    __table_args__ = (UniqueConstraint("organization_id", "module_key", name="uq_org_entitlement_module"),)

    module_key = Column(String(40), nullable=False)
    # 'subscription_request' (granted by approving a request) or 'platform' (edited by an Administrator).
    source = Column(String(30), nullable=False)
    request_id = Column(String(36), ForeignKey("subscription_requests.id", ondelete="SET NULL"), nullable=True)
    granted_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)


class SubscriptionRequest(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "subscription_requests"
    __table_args__ = (
        CheckConstraint("seats >= 1 AND seats <= 10000", name="ck_subscription_request_seats"),
        CheckConstraint("approved_seats IS NULL OR (approved_seats >= 1 AND approved_seats <= 10000)",
                        name="ck_subscription_request_approved_seats"),
        Index("uq_subscription_request_one_open", "organization_id", unique=True,
              postgresql_where=text("status = 'submitted'"), sqlite_where=text("status = 'submitted'")),
    )

    status = Column(_enum(SubscriptionRequestStatus, "subscription_request_status", 16), nullable=False,
                    default=SubscriptionRequestStatus.SUBMITTED)
    modules = Column(JSON, nullable=False)  # optional module keys requested (base modules are implied)
    seats = Column(Integer, nullable=False)
    billing_cycle = Column(_enum(BillingCycle, "billing_cycle", 16), nullable=False)
    notes = Column(String(1000), nullable=True)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)
    decision_reason = Column(String(500), nullable=True)
    # What was actually granted (an Administrator may modify the request when approving).
    approved_modules = Column(JSON, nullable=True)
    approved_seats = Column(Integer, nullable=True)
    approved_billing_cycle = Column(_enum(BillingCycle, "billing_cycle", 16), nullable=True)
