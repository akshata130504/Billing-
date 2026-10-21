"""UPI AutoPay / e-mandate: a local subscription collected by a Razorpay Subscription.

Razorpay owns the mandate and the charge schedule (it charges on each cycle and retries a failed
charge on T+1..T+3 before halting). This row mirrors that provider subscription for one local
Subscription so webhooks can be attributed, applied once and in order, and so staff and the
customer can see the mandate state. No card, UPI id or bank details are ever stored here.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AutopayStatus:
    """Razorpay subscription states (mirrored verbatim) plus nothing of our own."""

    CREATED = "created"  # waiting for the customer to authorise the mandate
    AUTHENTICATED = "authenticated"  # mandate authorised, first charge on start_at
    ACTIVE = "active"
    PENDING = "pending"  # a charge failed; Razorpay is retrying
    HALTED = "halted"  # retries exhausted; no more automatic charges
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    EXPIRED = "expired"  # authorisation link expired unused

    ALL = (CREATED, AUTHENTICATED, ACTIVE, PENDING, HALTED, PAUSED, CANCELLED, COMPLETED, EXPIRED)
    # A mandate in one of these can still charge (or be authorised): at most one per subscription.
    LIVE = (CREATED, AUTHENTICATED, ACTIVE, PENDING, HALTED, PAUSED)
    ENDED = (CANCELLED, COMPLETED, EXPIRED)


class GatewaySubscription(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "gateway_subscriptions"
    __table_args__ = (Index("ix_gateway_subscriptions_org_subscription", "organization_id", "subscription_id"),)

    subscription_id = Column(String(36), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    gateway = Column(String(20), nullable=False, default="razorpay")
    # The Razorpay account (key id, not secret) the plan/subscription live in: a tenant that
    # switches keys must set up a new mandate rather than reuse ids from another account.
    gateway_key_id = Column(String(64), nullable=False)
    gateway_plan_id = Column(String(64), nullable=False)
    gateway_subscription_id = Column(String(64), nullable=False, unique=True)
    status = Column(String(20), nullable=False, default=AutopayStatus.CREATED, index=True)
    amount = Column(Numeric(14, 2), nullable=False)  # charged per cycle, tax included
    currency = Column(String(3), nullable=False, default="INR")
    period = Column(String(16), nullable=False)  # Razorpay plan period: weekly / monthly / yearly
    interval = Column(Integer, nullable=False, default=1)
    total_count = Column(Integer, nullable=False)
    paid_count = Column(Integer, nullable=False, default=0)
    short_url = Column(Text, nullable=True)  # Razorpay's hosted authorisation page
    public_token_hash = Column(String(64), nullable=False, unique=True)  # our /autopay/<token> page
    start_at = Column(DateTime(timezone=True), nullable=True)
    charge_at = Column(DateTime(timezone=True), nullable=True)
    current_end = Column(DateTime(timezone=True), nullable=True)
    authorized_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    # created_at of the newest subscription.* event applied: older deliveries never roll state back.
    last_event_at = Column(DateTime(timezone=True), nullable=True)
    # Charge cycle (Razorpay charge_at) whose failure the customer was already told about.
    failure_notified_cycle = Column(String(32), nullable=True)
    last_error = Column(Text, nullable=True)
