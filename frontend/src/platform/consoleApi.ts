/**
 * Platform console API (phase 3): directory, lifecycle, staff, audit, dashboard and health.
 * Metadata only - the server never returns tenant financial or customer data here, and every
 * permission is enforced server-side; the UI only hides what the role cannot do.
 */
import { PlatformRole, consoleRequest } from './platformApi';

export type OrgStatus = 'trial' | 'trial_expired' | 'pending_approval' | 'active' | 'rejected' | 'suspended' | 'pending_deletion' | 'deleted';
export type LifecycleAction =
  | 'approve' | 'reject' | 'suspend' | 'reactivate' | 'schedule_deletion' | 'cancel_deletion' | 'pause_jobs' | 'resume_jobs' | 'revoke_sessions';

export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
  status: OrgStatus;
  jobs_paused: boolean;
  member_count: number;
  created_at: string | null;
  updated_at: string | null;
  status_changed_at: string | null;
  deletion_scheduled_for: string | null;
  trial_ends_at?: string | null;
  seat_limit?: number | null;
  module_access?: 'unrestricted' | 'entitled';
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface OrganizationDetail extends OrganizationSummary {
  country: string | null;
  timezone: string | null;
  owners: { full_name: string; email: string }[];
  members: { active: number; invited: number; deactivated: number; by_role: Record<string, number> };
  documents: Record<string, number>;
  security: { members_with_two_factor: number; active_members: number; live_tenant_sessions: number };
  lifecycle: {
    status: OrgStatus;
    status_changed_at: string | null;
    status_reason: string | null;
    status_changed_by: { id: string; full_name: string; email: string } | null;
    deletion_scheduled_for: string | null;
    jobs_paused: boolean;
    automation_running: boolean;
    renewals_waiting: number;
  };
  allowed_actions: LifecycleAction[];
}

export interface LifecycleResult {
  organization: OrganizationSummary;
  changed: Record<string, unknown>;
}

export interface TenantAdmin {
  membership_id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  status: string;
  has_2fa: boolean;
  live_sessions: number;
  created_at: string;
  last_login_at: string | null;
}

export interface TenantAdminActionResult {
  user_id: string;
  action: string;
  success: boolean;
  message: string;
}

export interface AuditEntry {
  id: string;
  occurred_at: string;
  action: string;
  result: 'success' | 'failure' | 'denied' | string;
  platform_staff_id: string | null;
  staff_email_snapshot: string | null;
  staff_role_snapshot: string | null;
  organization_id: string | null;
  organization_name_snapshot: string | null;
  target_type: string | null;
  target_id: string | null;
  reason: string | null;
  ticket_ref: string | null;
  ip_address: string | null;
  user_agent: string | null;
  details: Record<string, unknown> | null;
}

export interface StaffSummary {
  id: string;
  email: string;
  full_name: string;
  role: PlatformRole;
  is_active: boolean;
  deactivated_at: string | null;
  two_factor_enrolled: boolean;
  last_login_at: string | null;
  created_at: string | null;
  active_sessions: number;
  sign_in_locked: boolean;
}

export interface StaffDetail extends StaffSummary {
  is_self: boolean;
  sessions: {
    id: string;
    created_at: string;
    last_used_at: string;
    expires_at: string;
    ip_address: string | null;
    user_agent: string | null;
    current: boolean;
  }[];
}

export interface SchedulerStatus {
  enabled: boolean;
  status: string;
  interval_minutes?: number | null;
  last_finished_at?: string | null;
  seconds_since_last_run?: number | null;
  last_error_count?: number | null;
  total_runs?: number | null;
  last_counts: Record<string, number>;
}

export interface Health {
  api: { status: string; version: string; environment: string };
  database: { status: string };
  migrations: { status: string; current: string | null; head: string | null };
  scheduler: SchedulerStatus;
  platform: {
    auth_enabled: boolean;
    step_up_minutes: number;
    session_idle_minutes: number;
    session_max_hours: number;
    deletion_waiting_days: number;
  };
  integrations: { email_configured: boolean; payments_configured: boolean };
}

export interface Dashboard {
  organizations: Record<string, number>;
  created_last_7_days: number;
  recent_organizations: { id: string; name: string; slug: string; status: OrgStatus; created_at: string | null }[];
  staff: { total: number; active: number };
  health: { api: string; database: string; migrations: string; scheduler: string | null };
  scheduler: SchedulerStatus;
  recent_activity: AuditEntry[];
  subscription_requests_pending?: number;
}

export interface Jobs {
  scheduler: SchedulerStatus;
  durable_jobs: Record<string, number>;
  durable_jobs_failed_24h: number;
  outbox: Record<string, number>;
  webhooks_received_24h: number;
  organizations_not_running: number;
}

export interface DirectoryQuery {
  q?: string;
  status?: OrgStatus | '';
  sort?: 'name' | 'created_at' | 'updated_at' | 'status';
  direction?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface AuditQuery {
  action?: string;
  result?: string;
  organization_id?: string;
  staff_id?: string;
  target_type?: string;
  target_id?: string;
  q?: string;
  since?: string;
  until?: string;
  page?: number;
  page_size?: number;
}

export type BillingCycle = 'monthly' | 'quarterly' | 'annual';
export type SubscriptionRequestStatus = 'submitted' | 'approved' | 'rejected' | 'withdrawn';

/** A trial organization's subscription request, as the console sees it (no financial data). */
export interface PlatformSubscriptionRequest {
  id: string;
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  organization_status: OrgStatus;
  trial_ends_at: string | null;
  status: SubscriptionRequestStatus;
  modules: string[];
  seats: number;
  billing_cycle: BillingCycle;
  notes: string | null;
  created_at: string;
  reviewed_at: string | null;
  decision_reason: string | null;
  approved_modules: string[] | null;
  approved_seats: number | null;
  approved_billing_cycle: BillingCycle | null;
  requested_by_email: string | null;
  requested_by_name: string | null;
  seats_used: number;
}

export interface ApproveBody {
  modules?: string[];
  seats?: number;
  billing_cycle?: BillingCycle;
  reason?: string;
}

export interface OrganizationEntitlements {
  organization_id: string;
  module_access: 'unrestricted' | 'trial' | 'entitled';
  trial_ends_at?: string | null;
  modules: string[];
  seat_limit: number | null;
  seats_used: number;
}

/** A provisioned tenant Admin (never a password or invitation link). */
export interface ProvisionedAdmin {
  organization_id: string;
  organization_name: string;
  user_id: string;
  membership_id: string;
  full_name: string;
  email: string;
  role: 'admin';
  status: 'invited';
  invite_expires_at: string | null;
  email_delivered: boolean;
}

export interface ReasonBody {
  reason: string;
  ticket_ref?: string;
}

function query(params: object): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

const id = (value: string) => encodeURIComponent(value);

const ACTION_PATHS: Record<LifecycleAction, string> = {
  approve: 'approve',
  reject: 'reject',
  suspend: 'suspend',
  reactivate: 'reactivate',
  schedule_deletion: 'schedule-deletion',
  cancel_deletion: 'cancel-deletion',
  pause_jobs: 'jobs/pause',
  resume_jobs: 'jobs/resume',
  revoke_sessions: 'revoke-sessions',
};

export const consoleApi = {
  dashboard: () => consoleRequest<Dashboard>('GET', '/dashboard'),
  health: () => consoleRequest<Health>('GET', '/health'),
  organizations: (params: DirectoryQuery = {}) =>
    consoleRequest<Page<OrganizationSummary>>('GET', `/organizations${query(params)}`),
  organization: (orgId: string) => consoleRequest<OrganizationDetail>('GET', `/organizations/${id(orgId)}`),
  organizationActivity: (orgId: string, page = 1, lifecycle = false) =>
    consoleRequest<Page<AuditEntry>>(
      'GET', `/organizations/${id(orgId)}/activity${query({ page, page_size: 20, lifecycle: lifecycle ? 'true' : undefined })}`
    ),
  jobs: () => consoleRequest<Jobs>('GET', '/jobs'),
  lifecycle: (orgId: string, action: LifecycleAction, body: ReasonBody) =>
    consoleRequest<LifecycleResult>('POST', `/organizations/${id(orgId)}/${ACTION_PATHS[action]}`, body),
  tenantAdmins: (orgId: string) =>
    consoleRequest<TenantAdmin[]>('GET', `/organizations/${id(orgId)}/admins`),
  deactivateTenantAdmin: (orgId: string, userId: string, body: ReasonBody) =>
    consoleRequest<TenantAdminActionResult>('POST', `/organizations/${id(orgId)}/admins/${id(userId)}/deactivate`, body),
  reactivateTenantAdmin: (orgId: string, userId: string, body: ReasonBody) =>
    consoleRequest<TenantAdminActionResult>('POST', `/organizations/${id(orgId)}/admins/${id(userId)}/reactivate`, body),
  revokeTenantAdminSessions: (orgId: string, userId: string, body: ReasonBody) =>
    consoleRequest<TenantAdminActionResult>('POST', `/organizations/${id(orgId)}/admins/${id(userId)}/revoke-sessions`, body),
  staff: () => consoleRequest<{ items: StaffSummary[] }>('GET', '/staff'),
  staffMember: (staffId: string) => consoleRequest<StaffDetail>('GET', `/staff/${id(staffId)}`),
  staffAction: (staffId: string, action: 'deactivate' | 'activate' | 'revoke-sessions', body: ReasonBody) =>
    consoleRequest<StaffSummary & { sessions_revoked?: number | null }>('POST', `/staff/${id(staffId)}/${action}`, body),
  audit: (params: AuditQuery = {}) => consoleRequest<Page<AuditEntry>>('GET', `/audit${query(params)}`),
  subscriptionRequests: (status: SubscriptionRequestStatus | 'all' = 'submitted', page = 1) =>
    consoleRequest<Omit<Page<PlatformSubscriptionRequest>, 'total_pages'>>(
      'GET', `/subscription-requests${query({ status, page, page_size: 25 })}`
    ),
  subscriptionRequest: (requestId: string) =>
    consoleRequest<PlatformSubscriptionRequest>('GET', `/subscription-requests/${id(requestId)}`),
  approveSubscriptionRequest: (requestId: string, body: ApproveBody) =>
    consoleRequest<PlatformSubscriptionRequest>('POST', `/subscription-requests/${id(requestId)}/approve`, body),
  rejectSubscriptionRequest: (requestId: string, body: { reason: string }) =>
    consoleRequest<PlatformSubscriptionRequest>('POST', `/subscription-requests/${id(requestId)}/reject`, body),
  provisionTenantAdmin: (orgId: string, body: { full_name: string; email: string }) =>
    consoleRequest<ProvisionedAdmin>('POST', `/organizations/${id(orgId)}/admins`, body),
  entitlements: (orgId: string) =>
    consoleRequest<OrganizationEntitlements>('GET', `/subscription-requests/organizations/${id(orgId)}/entitlements`),
  updateEntitlements: (orgId: string, body: { modules: string[]; seat_limit: number | null; reason: string }) =>
    consoleRequest<OrganizationEntitlements>('POST', `/subscription-requests/organizations/${id(orgId)}/entitlements`, body),
};

export const STATUS_LABELS: Record<OrgStatus, string> = {
  trial: 'Trial',
  trial_expired: 'Trial ended',
  pending_approval: 'Pending Approval',
  active: 'Active',
  rejected: 'Rejected',
  suspended: 'Suspended',
  pending_deletion: 'Pending deletion',
  deleted: 'Deleted',
};

export const ACTION_LABELS: Record<LifecycleAction, string> = {
  approve: 'Approve organization',
  reject: 'Reject organization',
  suspend: 'Suspend organization',
  reactivate: 'Reactivate organization',
  schedule_deletion: 'Schedule deletion',
  cancel_deletion: 'Cancel deletion',
  pause_jobs: 'Pause billing automation',
  resume_jobs: 'Resume billing automation',
  revoke_sessions: 'Sign out all tenant users',
};

/** Actions the design requires a ticket for (the server enforces this too). */
export const TICKET_REQUIRED: ReadonlySet<LifecycleAction> = new Set(['suspend', 'schedule_deletion']);
