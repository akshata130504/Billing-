"""The organization's OWN commercial relationship with Rooman Billing: its free trial, then a paid plan.

Not to be confused with `Subscription` / `Plan` / `TrialPeriod`, which describe a tenant's
customers. One row per organization; the commercial state is deliberately kept apart from
`organizations.status`, which is the operational lifecycle (suspended, deleted, ...).

Organizations created before the trial existed have no row and are never restricted by it.
Not a TenantMixin table: the reminder job reads it across organizations.

Stored states and what they mean (services/platform_subscription_service.py derives the effective
state and access from them and the clock on every request; nothing waits for a scheduler):
  trialing   free trial; access until trial_ends_at, read-only afterwards (TRIAL_EXPIRED, derived)
  active     paid plan for [current_period_start, current_period_end)
  past_due   a renewal payment failed; access until grace_period_end
  cancelled  paid access has ended because the subscription was cancelled
  expired    paid access has ended because it was not renewed in time
Paid periods are half-open: access ends exactly AT current_period_end (or grace_period_end).
"""
import enum

from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, false, text,
)

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class PlatformSubscriptionState(str, enum.Enum):
    TRIALING = "trialing"
    # Not stored: derived when state is TRIALING and trial_ends_at has passed, so enforcement never
    # waits for a scheduler tick.
    TRIAL_EXPIRED = "trial_expired"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


STORED_STATES = ("trialing", "active", "past_due", "cancelled", "expired")
PAID_STATES = ("active", "past_due", "cancelled", "expired")
_PAID_SQL = ", ".join(f"'{s}'" for s in PAID_STATES)


class PlatformSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "state IN (%s)" % ", ".join(f"'{s}'" for s in STORED_STATES), name="ck_platform_subscription_state"
        ),
        # A trial row always has its trial window.
        CheckConstraint(
            "state <> 'trialing' OR (trial_started_at IS NOT NULL AND trial_ends_at IS NOT NULL)",
            name="ck_platform_subscription_trial_window",
        ),
        # A paid row always names its plan and a non-empty billing period.
        CheckConstraint(
            f"state NOT IN ({_PAID_SQL}) OR (plan_code IS NOT NULL AND billing_interval IS NOT NULL "
            "AND billing_interval_count IS NOT NULL AND current_period_start IS NOT NULL "
            "AND current_period_end IS NOT NULL AND current_period_end > current_period_start)",
            name="ck_platform_subscription_paid_period",
        ),
        CheckConstraint("state <> 'past_due' OR grace_period_end IS NOT NULL",
                        name="ck_platform_subscription_grace"),
        CheckConstraint("state <> 'cancelled' OR cancelled_at IS NOT NULL",
                        name="ck_platform_subscription_cancelled_at"),
        CheckConstraint("billing_interval IS NULL OR billing_interval IN ('month', 'year')",
                        name="ck_platform_subscription_interval"),
        CheckConstraint("billing_interval_count IS NULL OR (billing_interval_count >= 1 AND billing_interval_count <= 12)",
                        name="ck_platform_subscription_interval_count"),
        UniqueConstraint("provider_subscription_id", name="uq_platform_subscription_provider_subscription_id"),
    )

    organization_id = Column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    state = Column(String(20), nullable=False, default=PlatformSubscriptionState.TRIALING.value)
    # The free trial (NULL for an organization that subscribed without one).
    trial_started_at = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    # "Minutes remaining" offsets already handled (sent or deliberately skipped as stale); each
    # offset is handled at most once, so a reminder can never be sent twice.
    reminders_sent = Column(JSON, nullable=False, default=list)

    # The paid plan: a code from core/plan_catalog.json (prices, modules and seats live there, not here)
    # and the billing interval copied from the catalog when the period started.
    plan_code = Column(String(32), nullable=True)
    billing_interval = Column(String(10), nullable=True)
    billing_interval_count = Column(Integer, nullable=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    # Cancelled by the customer to take effect at current_period_end: access continues until then.
    cancel_at_period_end = Column(Boolean, nullable=False, default=False, server_default=false())
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    grace_period_end = Column(DateTime(timezone=True), nullable=True)
    # The Razorpay Subscription (Rooman's account) paying for the current plan, its mode, and how many of
    # its paid cycles have been applied here (activation = 1, each renewal + 1): a cycle is applied once.
    provider_subscription_id = Column(String(64), nullable=True)
    provider_mode = Column(String(8), nullable=True)
    provider_paid_count = Column(Integer, nullable=True)


# --- Plan checkout with Rooman's own Razorpay account (services/platform_checkout_service.py) --------

PROVIDER_MODES = ("test", "live")
PROVIDER_PLAN_STATUSES = ("pending", "created", "unknown", "failed")
CHECKOUT_STATUSES = ("pending", "created", "unknown", "authorized", "failed", "expired", "completed")
# Attempts that may still turn into a payment: at most one per organization. 'authorized' = Razorpay has
# the customer's authorization but the first charge is not confirmed yet (never expires locally).
OPEN_CHECKOUT_STATUSES = ("pending", "created", "unknown", "authorized")
_OPEN_SQL = "status IN (%s)" % ", ".join(f"'{s}'" for s in OPEN_CHECKOUT_STATUSES)


class PlatformProviderPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Razorpay Plan (in Rooman's account) for one catalog plan's billing terms in one mode.

    Keyed by a fingerprint of everything that defines the charge (code, amount, currency, interval,
    tax treatment): a catalog change gets a NEW provider plan, never a silent reuse. Razorpay plans
    cannot be edited, and creating one is not idempotent, so `reconcile_ref` is written into the plan's
    notes before the create call: after an ambiguous failure ('unknown') the plan is looked up by it
    instead of being created twice.
    """

    __tablename__ = "platform_provider_plans"
    __table_args__ = (
        UniqueConstraint("provider", "mode", "fingerprint", name="uq_platform_provider_plan_terms"),
        UniqueConstraint("reconcile_ref", name="uq_platform_provider_plans_reconcile_ref"),
        UniqueConstraint("provider_plan_id", name="uq_platform_provider_plans_provider_plan_id"),
        CheckConstraint("mode IN ('test', 'live')", name="ck_platform_provider_plan_mode"),
        CheckConstraint("status IN ('pending', 'created', 'unknown', 'failed')", name="ck_platform_provider_plan_status"),
        CheckConstraint("status <> 'created' OR provider_plan_id IS NOT NULL", name="ck_platform_provider_plan_created_id"),
    )

    provider = Column(String(16), nullable=False, default="razorpay")
    mode = Column(String(8), nullable=False)
    plan_code = Column(String(32), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    amount_minor = Column(BigInteger, nullable=False)
    currency = Column(String(3), nullable=False)
    billing_interval = Column(String(10), nullable=False)
    billing_interval_count = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    reconcile_ref = Column(String(64), nullable=False)
    provider_plan_id = Column(String(64), nullable=True)
    attempts = Column(Integer, nullable=False, default=0, server_default=text("0"))
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(300), nullable=True)


class PlatformCheckoutAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An Owner started buying a plan: the Razorpay Subscription created for it and a snapshot of what
    was offered. NOT a paid subscription - it grants nothing; a verified payment (later stage) moves the
    organization's platform_subscriptions row. At most one open attempt per organization."""

    __tablename__ = "platform_checkout_attempts"
    __table_args__ = (
        UniqueConstraint("provider_subscription_id", name="uq_platform_checkout_attempts_provider_subscription_id"),
        CheckConstraint("mode IN ('test', 'live')", name="ck_platform_checkout_mode"),
        CheckConstraint("status IN (%s)" % ", ".join(f"'{s}'" for s in CHECKOUT_STATUSES), name="ck_platform_checkout_status"),
        CheckConstraint("status <> 'created' OR provider_subscription_id IS NOT NULL",
                        name="ck_platform_checkout_created_id"),
        Index("uq_platform_checkout_one_open", "organization_id", unique=True,
              postgresql_where=text(_OPEN_SQL), sqlite_where=text(_OPEN_SQL)),
        Index("ix_platform_checkout_attempts_review_flagged_at", "review_flagged_at"),
    )

    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # What was offered, from the catalog at the time (the catalog stays the source of truth).
    plan_code = Column(String(32), nullable=False)
    catalog_version = Column(Integer, nullable=False)
    fingerprint = Column(String(64), nullable=False)
    amount_minor = Column(BigInteger, nullable=False)
    currency = Column(String(3), nullable=False)
    billing_interval = Column(String(10), nullable=False)
    billing_interval_count = Column(Integer, nullable=False)
    seat_limit = Column(Integer, nullable=False)
    tax_treatment = Column(String(16), nullable=True)
    provider = Column(String(16), nullable=False, default="razorpay")
    mode = Column(String(8), nullable=False)
    provider_plan_id = Column(String(64), nullable=True)
    provider_subscription_id = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, default="pending")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_error = Column(String(300), nullable=True)
    # Set by payment verification (services/platform_payment_service.py).
    provider_payment_id = Column(String(64), nullable=True)
    authorized_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    # Durable "needs review" marker (migration 0041), written by platform_payment_service._review: the LATEST
    # finding as "<outcome>: <detail>" (application text only) and when the checkout was FIRST flagged. Never
    # cleared automatically; the console lists it until a resolve step exists.
    review_reason = Column(String(300), nullable=True)
    review_flagged_at = Column(DateTime(timezone=True), nullable=True)


WEBHOOK_EVENT_STATUSES = ("processed", "ignored", "needs_review")


class PlatformWebhookEvent(UUIDPrimaryKeyMixin, Base):
    """One verified Razorpay webhook event for Rooman's own account, recorded in the same transaction as
    its effects (so an event whose changes failed is not recorded, and Razorpay's retry processes it).
    Normalized fields only - never the payload, which carries customer and payment details."""

    __tablename__ = "platform_webhook_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_platform_webhook_events_event_id"),
        CheckConstraint("status IN ('processed', 'ignored', 'needs_review')", name="ck_platform_webhook_event_status"),
    )

    provider = Column(String(16), nullable=False, default="razorpay")
    event_id = Column(String(128), nullable=False)
    event_type = Column(String(64), nullable=False)
    mode = Column(String(8), nullable=True)
    provider_subscription_id = Column(String(64), nullable=True)
    provider_payment_id = Column(String(64), nullable=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(16), nullable=False)
    outcome = Column(String(40), nullable=False)
    event_created_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False)


PAYMENT_KINDS = ("initial", "renewal")
PAYMENT_STATUSES = ("paid",)  # refunds / chargebacks would be added by a later, reviewed migration


class PlatformPayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A VERIFIED, successful payment for an organization's Rooman plan, and its payment receipt (migration 0042).

    Written only by services/platform_receipt_service.py from a payment that the shared verification already
    accepted (captured, exactly the checkout's amount and currency, for that checkout's Razorpay subscription). One
    row per Razorpay payment id - the same payment can never produce a second receipt. Rows are never updated or
    deleted by the application: the amount, plan and billing identity are a snapshot taken when the payment was
    recorded, so later price, plan, subscription or profile changes never rewrite a receipt.

    A payment RECEIPT, not a GST tax invoice: tax treatment, Rooman's legal / tax details and invoice numbering are
    not decided (see docs/operations.md). Rooman's own billing only - never a tenant's payments.
    """

    __tablename__ = "platform_payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="uq_platform_payments_provider_payment"),
        UniqueConstraint("receipt_number", name="uq_platform_payments_receipt_number"),
        CheckConstraint("mode IN ('test', 'live')", name="ck_platform_payments_mode"),
        CheckConstraint("kind IN (%s)" % ", ".join(f"'{k}'" for k in PAYMENT_KINDS), name="ck_platform_payments_kind"),
        CheckConstraint("status IN (%s)" % ", ".join(f"'{s}'" for s in PAYMENT_STATUSES), name="ck_platform_payments_status"),
        CheckConstraint("amount_minor > 0", name="ck_platform_payments_amount_positive"),
        Index("ix_platform_payments_org_paid_at", "organization_id", "paid_at"),
    )

    # RESTRICT: a payment record outlives everything else (financial record retention).
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    checkout_attempt_id = Column(String(36), ForeignKey("platform_checkout_attempts.id", ondelete="RESTRICT"),
                                 nullable=False, index=True)
    provider = Column(String(16), nullable=False, default="razorpay")
    mode = Column(String(8), nullable=False)
    provider_payment_id = Column(String(64), nullable=False)
    provider_subscription_id = Column(String(64), nullable=False, index=True)
    provider_invoice_id = Column(String(64), nullable=True)
    kind = Column(String(16), nullable=False)
    cycle_number = Column(Integer, nullable=True)  # position among the subscription's paid cycles, when known
    status = Column(String(16), nullable=False, default="paid")
    amount_minor = Column(BigInteger, nullable=False)
    currency = Column(String(3), nullable=False)
    method = Column(String(32), nullable=True)  # card / upi / emandate ... (no instrument details)
    paid_at = Column(DateTime(timezone=True), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    plan_code = Column(String(32), nullable=False)
    plan_name = Column(String(80), nullable=True)
    billing_interval = Column(String(10), nullable=False)
    billing_interval_count = Column(Integer, nullable=False)
    sandbox = Column(Boolean, nullable=False, default=False, server_default=false())
    receipt_number = Column(String(32), nullable=False)
    # Billing identity of the organization when the payment was recorded (Settings -> Organization), never invented.
    billed_name = Column(String(200), nullable=False)
    billed_legal_name = Column(String(200), nullable=True)
    billed_email = Column(String(255), nullable=True)
    billed_address_line1 = Column(String(255), nullable=True)
    billed_address_line2 = Column(String(255), nullable=True)
    billed_city = Column(String(120), nullable=True)
    billed_state = Column(String(120), nullable=True)
    billed_postal_code = Column(String(20), nullable=True)
    billed_country = Column(String(10), nullable=True)
    billed_gstin = Column(String(20), nullable=True)


REVIEW_CASE_STATUSES = ("open", "resolved")
# What the staff member concluded. Recording a resolution never changes a payment, a subscription or access.
REVIEW_RESOLUTION_CATEGORIES = (
    "no_action_needed",            # investigated: nothing was wrong / nothing to do
    "resolved_by_payment_lifecycle",  # fixed by the normal verified flow (e.g. a later verified payment / sync)
    "handled_in_razorpay",         # handled in the Razorpay dashboard (e.g. a refund made there)
    "customer_contacted",          # followed up with the organization
    "duplicate_case",              # the same issue is tracked by another case
    "other",
)


class PlatformPaymentReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One payment-review case for a checkout (migration 0043): opened by platform_payment_service._review when a
    payment finding cannot be applied automatically, resolved by platform staff with a category and an explanation.

    History is kept, never erased: repeated findings while a case is open update `latest_reason`, `last_seen_at` and
    `finding_count` on that case; a finding after the case was resolved opens a NEW case (the resolved one stays as it
    was). At most one open case per checkout (partial unique index). Resolving is bookkeeping only: it does not mark
    a payment successful, activate a plan, change any checkout / subscription status, call Razorpay, refund or replay.
    """

    __tablename__ = "platform_payment_reviews"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'resolved')", name="ck_platform_payment_reviews_status"),
        CheckConstraint("resolution_category IS NULL OR resolution_category IN (%s)"
                        % ", ".join(f"'{c}'" for c in REVIEW_RESOLUTION_CATEGORIES),
                        name="ck_platform_payment_reviews_category"),
        CheckConstraint("(status = 'open' AND resolved_at IS NULL) OR (status = 'resolved' AND resolved_at IS NOT NULL "
                        "AND resolution_category IS NOT NULL AND resolution_note IS NOT NULL)",
                        name="ck_platform_payment_reviews_resolution"),
        Index("uq_platform_payment_reviews_one_open", "checkout_attempt_id", unique=True,
              postgresql_where=text("status = 'open'"), sqlite_where=text("status = 'open'")),
        Index("ix_platform_payment_reviews_status_opened", "status", "opened_at"),
    )

    checkout_attempt_id = Column(String(36), ForeignKey("platform_checkout_attempts.id", ondelete="RESTRICT"),
                                 nullable=False, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    provider_subscription_id = Column(String(64), nullable=True)
    mode = Column(String(8), nullable=True)
    status = Column(String(16), nullable=False, default="open")
    first_reason = Column(String(300), nullable=False)
    latest_reason = Column(String(300), nullable=False)
    finding_count = Column(Integer, nullable=False, default=1)
    opened_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)
    resolution_category = Column(String(40), nullable=True)
    resolution_note = Column(String(500), nullable=True)
    resolution_ticket_ref = Column(String(100), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="SET NULL"), nullable=True)
    resolved_by_email = Column(String(255), nullable=True)  # snapshot: survives a staff account change
    resolved_by_role = Column(String(32), nullable=True)


NOTIFICATION_KINDS = ("subscription_activated", "renewal_payment_received", "payment_past_due", "access_expired",
                      "cancellation_scheduled", "cancelled_immediately", "cancellation_effective")
NOTIFICATION_STATUSES = ("pending", "sent", "failed", "superseded")


class PlatformNotification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One Rooman subscription lifecycle email to one recipient (migration 0044).

    Queued by platform_notification_service in the same transaction as the state change it reports and sent only
    after that commit by the platform_notifications scheduler job (Rooman's server SMTP sender). UNIQUE (event_key,
    recipient) keeps the callback, webhook and reconciliation from queueing the same event twice; event_key is
    namespaced by kind. pending -> sent | failed (attempts exhausted) | superseded (no longer true when sent).
    Retrying re-sends this stored email only. Platform data: never shown to tenants, no row level security.
    """

    __tablename__ = "platform_notifications"
    __table_args__ = (
        UniqueConstraint("event_key", "recipient", name="uq_platform_notifications_event_recipient"),
        CheckConstraint("kind IN (%s)" % ", ".join(f"'{k}'" for k in NOTIFICATION_KINDS),
                        name="ck_platform_notifications_kind"),
        CheckConstraint("status IN (%s)" % ", ".join(f"'{s}'" for s in NOTIFICATION_STATUSES),
                        name="ck_platform_notifications_status"),
        CheckConstraint("event_key LIKE kind || ':%'", name="ck_platform_notifications_key_namespace"),
        CheckConstraint("(status = 'sent') = (sent_at IS NOT NULL)", name="ck_platform_notifications_sent_at"),
        CheckConstraint("attempts >= 0", name="ck_platform_notifications_attempts"),
        Index("ix_platform_notifications_status_next", "status", "next_attempt_at"),
    )

    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    platform_subscription_id = Column(String(36), ForeignKey("platform_subscriptions.id", ondelete="CASCADE"),
                                      nullable=True)
    kind = Column(String(40), nullable=False)
    event_key = Column(String(200), nullable=False)
    reference_at = Column(DateTime(timezone=True), nullable=True)  # the date the email is about (staleness check)
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    text_body = Column(Text, nullable=False)
    html_body = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(120), nullable=True)  # an error class only, never server replies or credentials
    sent_at = Column(DateTime(timezone=True), nullable=True)
