"""Platform console API schemas (phase 3).

Response models are explicit allow-lists: only the fields named here can ever leave the platform
API, so tenant financial or customer data cannot slip into a response by accident
(tests/test_platform_console.py checks this).
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from backend.app.schemas.organization import EmailAddress, UTCDateTime
from backend.app.schemas.validators import validate_sensible_name

OrgStatus = Literal["trial", "trial_expired", "pending_approval", "active", "rejected", "suspended", "pending_deletion", "deleted"]
PlatformRoleName = Literal["platform_administrator", "platform_operations", "platform_support"]


# --- organizations --------------------------------------------------------------------------------------


class OrganizationSummaryOut(BaseModel):
    id: str
    name: str
    slug: str
    status: OrgStatus
    jobs_paused: bool
    member_count: int
    created_at: Optional[UTCDateTime] = None
    updated_at: Optional[UTCDateTime] = None
    status_changed_at: Optional[UTCDateTime] = None
    deletion_scheduled_for: Optional[UTCDateTime] = None
    trial_ends_at: Optional[UTCDateTime] = None
    seat_limit: Optional[int] = None
    module_access: str = "unrestricted"


class OrganizationPageOut(BaseModel):
    items: List[OrganizationSummaryOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class OwnerContactOut(BaseModel):
    full_name: str
    email: str


class MemberCountsOut(BaseModel):
    active: int
    invited: int
    deactivated: int
    by_role: Dict[str, int]


class OrganizationSecurityOut(BaseModel):
    members_with_two_factor: int
    active_members: int
    live_tenant_sessions: int


class StaffRefOut(BaseModel):
    id: str
    full_name: str
    email: str


class LifecycleStateOut(BaseModel):
    status: OrgStatus
    status_changed_at: Optional[UTCDateTime] = None
    status_reason: Optional[str] = None
    status_changed_by: Optional[StaffRefOut] = None
    deletion_scheduled_for: Optional[UTCDateTime] = None
    jobs_paused: bool
    automation_running: bool
    automation_state: Literal["running", "paused", "held_trial"] = "running"
    automation_label: str = "Running"
    renewals_waiting: int


class OrganizationDetailOut(OrganizationSummaryOut):
    country: Optional[str] = None
    timezone: Optional[str] = None
    owners: List[OwnerContactOut]
    members: MemberCountsOut
    documents: Dict[str, int]
    security: OrganizationSecurityOut
    lifecycle: LifecycleStateOut
    allowed_actions: List[str]


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=500)
    ticket_ref: Optional[str] = Field(default=None, max_length=100)

    @field_validator("reason")
    @classmethod
    def _reason_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 10:
            raise ValueError("Give a reason of at least 10 characters.")
        return value

    @field_validator("ticket_ref")
    @classmethod
    def _ticket(cls, value: Optional[str]) -> Optional[str]:
        value = " ".join((value or "").split())
        return value or None


class TicketedReasonRequest(ReasonRequest):
    """For actions the design requires a ticket for (suspend, schedule deletion)."""

    ticket_ref: str = Field(min_length=2, max_length=100)

    @field_validator("ticket_ref")
    @classmethod
    def _ticket_required(cls, value: str) -> str:
        value = " ".join((value or "").split())
        if len(value) < 2:
            raise ValueError("A ticket reference is required.")
        return value


class LifecycleResultOut(BaseModel):
    organization: OrganizationSummaryOut
    changed: Dict[str, Any]


class OptionalReasonRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)
    ticket_ref: Optional[str] = Field(default=None, max_length=100)


class TenantAdminOut(BaseModel):
    membership_id: str
    user_id: str
    email: str
    full_name: str
    role: str
    status: str
    has_2fa: bool
    live_sessions: int
    created_at: UTCDateTime
    last_login_at: Optional[UTCDateTime] = None


class TenantAdminActionResult(BaseModel):
    user_id: str
    action: str
    success: bool
    message: str


# --- audit ------------------------------------------------------------------------------------------------


class AuditEntryOut(BaseModel):
    id: str
    occurred_at: UTCDateTime
    action: str
    result: str
    platform_staff_id: Optional[str] = None
    staff_email_snapshot: Optional[str] = None
    staff_role_snapshot: Optional[str] = None
    organization_id: Optional[str] = None
    organization_name_snapshot: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    reason: Optional[str] = None
    ticket_ref: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class AuditPageOut(BaseModel):
    items: List[AuditEntryOut]
    total: int
    page: int
    page_size: int
    total_pages: int


# --- staff ------------------------------------------------------------------------------------------------


class StaffSummaryOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: PlatformRoleName
    is_active: bool
    deactivated_at: Optional[UTCDateTime] = None
    two_factor_enrolled: bool
    last_login_at: Optional[UTCDateTime] = None
    created_at: Optional[UTCDateTime] = None
    active_sessions: int
    sign_in_locked: bool


class StaffListOut(BaseModel):
    items: List[StaffSummaryOut]


class StaffSessionMetaOut(BaseModel):
    id: str
    created_at: UTCDateTime
    last_used_at: UTCDateTime
    expires_at: UTCDateTime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    current: bool


class StaffDetailOut(StaffSummaryOut):
    is_self: bool
    sessions: List[StaffSessionMetaOut]


class StaffActionOut(StaffSummaryOut):
    sessions_revoked: Optional[int] = None


# --- dashboard / health -----------------------------------------------------------------------------------


class SchedulerStatusOut(BaseModel):
    enabled: bool
    running: bool = False  # from the scheduler's own heartbeat, not this API process's flag
    status: str
    interval_minutes: Optional[int] = None
    last_finished_at: Optional[UTCDateTime] = None
    seconds_since_last_run: Optional[int] = None
    last_error_count: Optional[int] = None
    total_runs: Optional[int] = None
    last_counts: Dict[str, int] = Field(default_factory=dict)


class HealthApiOut(BaseModel):
    status: str
    version: str
    environment: str


class HealthStateOut(BaseModel):
    status: str


class MigrationStateOut(BaseModel):
    status: str
    current: Optional[str] = None
    head: Optional[str] = None


class PlatformSettingsOut(BaseModel):
    auth_enabled: bool
    step_up_minutes: int
    session_idle_minutes: int
    session_max_hours: int
    deletion_waiting_days: int


class IntegrationFlagsOut(BaseModel):
    email_configured: bool
    payments_configured: bool


class HealthOut(BaseModel):
    api: HealthApiOut
    database: HealthStateOut
    migrations: MigrationStateOut
    scheduler: SchedulerStatusOut
    platform: PlatformSettingsOut
    integrations: IntegrationFlagsOut


class RecentOrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    status: OrgStatus
    created_at: Optional[UTCDateTime] = None


class StaffCountsOut(BaseModel):
    total: int
    active: int


class HealthSummaryOut(BaseModel):
    api: str
    database: str
    migrations: str
    scheduler: Optional[str] = None


class DashboardOut(BaseModel):
    organizations: Dict[str, int]
    created_last_7_days: int
    recent_organizations: List[RecentOrganizationOut]
    staff: StaffCountsOut
    health: HealthSummaryOut
    scheduler: SchedulerStatusOut
    recent_activity: List[AuditEntryOut]
    subscription_requests_pending: int = 0


class JobsOut(BaseModel):
    """Background work, counts only. Observation: nothing in the platform API runs a job."""

    scheduler: SchedulerStatusOut
    durable_jobs: Dict[str, int]
    durable_jobs_failed_24h: int
    outbox: Dict[str, int]
    webhooks_received_24h: int
    organizations_not_running: int


class ProvisionAdminRequest(BaseModel):
    """A Platform Administrator provisions an organization's tenant Admin. The organization comes from
    the URL and the role is always Admin: neither can be chosen in the body (unknown fields refused)."""

    model_config = {"extra": "forbid"}

    full_name: str = Field(min_length=1, max_length=200)
    email: EmailAddress

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        return validate_sensible_name(v, "Admin name")


class ProvisionedAdminOut(BaseModel):
    """The provisioned Admin and the invitation state. Never a password or invitation token."""

    organization_id: str
    organization_name: str
    user_id: str
    membership_id: str
    full_name: str
    email: str
    role: Literal["admin"]
    status: Literal["invited"]
    invite_expires_at: Optional[UTCDateTime] = None
    email_delivered: bool
