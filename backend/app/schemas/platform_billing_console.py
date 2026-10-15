"""Platform console views of Rooman's own plan billing (no secrets, payloads or customer contact data), and the
one write: recording a payment-review resolution (bookkeeping only)."""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.organization import UTCDateTime


class _Page(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


class PlatformSubscriptionRowOut(BaseModel):
    organization_id: str
    organization_name: Optional[str] = None
    plan_code: Optional[str] = None
    plan_name: Optional[str] = None
    sandbox: bool = False
    state: str  # stored
    effective_state: str  # what access is right now (platform_subscription_service.evaluate)
    writable: bool
    cancel_at_period_end: bool
    billing_interval: Optional[str] = None
    billing_interval_count: Optional[int] = None
    current_period_start: Optional[UTCDateTime] = None
    current_period_end: Optional[UTCDateTime] = None
    grace_period_end: Optional[UTCDateTime] = None
    cancelled_at: Optional[UTCDateTime] = None
    trial_ends_at: Optional[UTCDateTime] = None
    amount_minor: Optional[int] = None  # from the checkout that started the Razorpay subscription
    currency: Optional[str] = None
    provider_subscription_id: Optional[str] = None
    provider_mode: Optional[str] = None
    provider_paid_count: Optional[int] = None
    updated_at: Optional[UTCDateTime] = None


class PlatformSubscriptionPageOut(_Page):
    items: List[PlatformSubscriptionRowOut]


class CheckoutAttemptRowOut(BaseModel):
    id: str
    organization_id: str
    organization_name: Optional[str] = None
    plan_code: str
    plan_name: Optional[str] = None
    sandbox: bool = False
    amount_minor: int
    currency: str
    billing_interval: str
    billing_interval_count: int
    seat_limit: int
    mode: str
    status: str
    provider_subscription_id: Optional[str] = None
    provider_payment_id: Optional[str] = None
    created_at: Optional[UTCDateTime] = None
    expires_at: Optional[UTCDateTime] = None
    authorized_at: Optional[UTCDateTime] = None
    completed_at: Optional[UTCDateTime] = None
    last_error: Optional[str] = None  # the application's own short summary (Razorpay text already truncated)
    webhook_review: bool  # a webhook for its subscription was marked needs_review
    review_reason: Optional[str] = None  # latest durable review finding (migration 0041)
    review_flagged_at: Optional[UTCDateTime] = None  # first flagged
    stuck: bool  # unknown, or authorized for more than a day


class CheckoutAttemptPageOut(_Page):
    items: List[CheckoutAttemptRowOut]


class WebhookEventRowOut(BaseModel):
    id: str
    event_id: str
    event_type: str
    mode: Optional[str] = None
    status: str
    outcome: Optional[str] = None
    provider_subscription_id: Optional[str] = None
    provider_payment_id: Optional[str] = None
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None
    event_created_at: Optional[UTCDateTime] = None
    received_at: Optional[UTCDateTime] = None


class WebhookEventPageOut(_Page):
    items: List[WebhookEventRowOut]


class ReviewItemOut(BaseModel):
    source: str  # checkout_review | webhook_needs_review | checkout_unknown | checkout_authorized_stuck
    explanation: str
    detected_at: Optional[UTCDateTime] = None
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None
    # Review case (checkout_review only, migration 0043); other sources are state-derived and not resolvable.
    case_id: Optional[str] = None
    case_status: str = "open"  # open | resolved
    resolvable: bool = False
    first_reason: Optional[str] = None
    review_reason: Optional[str] = None  # the latest finding
    finding_count: Optional[int] = None
    flagged_at: Optional[UTCDateTime] = None  # when the case was opened
    last_seen_at: Optional[UTCDateTime] = None
    resolution_category: Optional[str] = None
    resolution_note: Optional[str] = None
    resolution_ticket_ref: Optional[str] = None
    resolved_at: Optional[UTCDateTime] = None
    resolved_by_email: Optional[str] = None
    resolved_by_role: Optional[str] = None
    checkout_status: Optional[str] = None
    outcome: Optional[str] = None
    event_type: Optional[str] = None
    checkout_attempt_id: Optional[str] = None
    provider_subscription_id: Optional[str] = None
    provider_payment_id: Optional[str] = None
    mode: Optional[str] = None


class ReviewQueuePageOut(_Page):
    items: List[ReviewItemOut]
    untracked_sources: List[str]  # review outcomes that are logged/alerted but not stored (none since 0041)


class ResolveReviewIn(BaseModel):
    """A staff member's conclusion. Recording it never approves, refunds or changes a payment."""

    model_config = ConfigDict(extra="forbid")

    category: Literal["no_action_needed", "resolved_by_payment_lifecycle", "handled_in_razorpay", "customer_contacted",
                      "duplicate_case", "other"]
    reason: str = Field(min_length=10, max_length=500)  # what was investigated
    ticket_ref: Optional[str] = Field(default=None, max_length=100)

    @field_validator("reason")
    @classmethod
    def _reason_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 10:
            raise ValueError("Describe what was investigated in at least 10 characters.")
        return value

    @field_validator("ticket_ref")
    @classmethod
    def _ticket(cls, value: Optional[str]) -> Optional[str]:
        value = (value or "").strip()
        return value or None


class ReviewCaseOut(BaseModel):
    """A review case after resolution. Its payment, checkout, subscription and access are unchanged."""

    case_id: str
    case_status: str
    checkout_attempt_id: str
    organization_id: str
    first_reason: str
    review_reason: str
    finding_count: int
    flagged_at: UTCDateTime
    last_seen_at: UTCDateTime
    resolution_category: Optional[str] = None
    resolution_note: Optional[str] = None
    resolution_ticket_ref: Optional[str] = None
    resolved_at: Optional[UTCDateTime] = None
    resolved_by_email: Optional[str] = None
    resolved_by_role: Optional[str] = None


class NotificationRowOut(BaseModel):
    """One Rooman lifecycle email's delivery record. No subject, body or full recipient address."""

    id: str
    kind: str
    status: str  # pending | sent (SMTP accepted it - not proof of inbox delivery) | failed | superseded
    attempts: int
    organization_id: str
    organization_name: Optional[str] = None
    recipient_hint: Optional[str] = None  # e.g. "o***@example.test"
    created_at: Optional[UTCDateTime] = None
    updated_at: Optional[UTCDateTime] = None
    sent_at: Optional[UTCDateTime] = None
    next_attempt_at: Optional[UTCDateTime] = None  # pending rows only
    error_code: Optional[str] = None  # allow-listed category, or "unclassified"
    error_label: Optional[str] = None


class NotificationStatusCounts(BaseModel):
    pending: int = 0
    sent: int = 0
    failed: int = 0
    superseded: int = 0


class NotificationPageOut(_Page):
    items: List[NotificationRowOut]
    status_counts: NotificationStatusCounts
