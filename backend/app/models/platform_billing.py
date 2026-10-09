"""The organization's OWN commercial relationship with Rooman Billing (free trial today; plans later).

Not to be confused with `Subscription` / `Plan` / `TrialPeriod`, which describe a tenant's
customers. One row per organization; the commercial state is deliberately kept apart from
`organizations.status`, which is the operational lifecycle (suspended, deleted, ...).

Organizations created before the trial existed have no row and are never restricted by it.
Not a TenantMixin table: the reminder job reads it across organizations.
"""
import enum

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class PlatformSubscriptionState(str, enum.Enum):
    TRIALING = "trialing"
    # Not stored: derived when state is TRIALING and trial_ends_at has passed, so enforcement never
    # waits for a scheduler tick.
    TRIAL_EXPIRED = "trial_expired"


class PlatformSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_subscriptions"

    organization_id = Column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    state = Column(String(20), nullable=False, default=PlatformSubscriptionState.TRIALING.value)
    trial_started_at = Column(DateTime(timezone=True), nullable=False)
    trial_ends_at = Column(DateTime(timezone=True), nullable=False)
    # "Minutes remaining" offsets already handled (sent or deliberately skipped as stale); each
    # offset is handled at most once, so a reminder can never be sent twice.
    reminders_sent = Column(JSON, nullable=False, default=list)
