/**
 * Platform console API (phase 3): directory, lifecycle, staff, audit, dashboard and health.
 * Metadata only - the server never returns tenant financial or customer data here, and every
 * permission is enforced server-side; the UI only hides what the role cannot do.
 */
import { PlatformRole, consoleRequest } from './platformApi';

export type OrgStatus = 'active' | 'suspended' | 'pending_deletion' | 'deleted';
export type LifecycleAction =
  | 'suspend' | 'reactivate' | 'schedule_deletion' | 'cancel_deletion' | 'pause_jobs' | 'resume_jobs' | 'revoke_sessions';

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
  staff: () => consoleRequest<{ items: StaffSummary[] }>('GET', '/staff'),
  staffMember: (staffId: string) => consoleRequest<StaffDetail>('GET', `/staff/${id(staffId)}`),
  staffAction: (staffId: string, action: 'deactivate' | 'activate' | 'revoke-sessions', body: ReasonBody) =>
    consoleRequest<StaffSummary & { sessions_revoked?: number | null }>('POST', `/staff/${id(staffId)}/${action}`, body),
  audit: (params: AuditQuery = {}) => consoleRequest<Page<AuditEntry>>('GET', `/audit${query(params)}`),
};

export const STATUS_LABELS: Record<OrgStatus, string> = {
  active: 'Active',
  suspended: 'Suspended',
  pending_deletion: 'Pending deletion',
  deleted: 'Deleted',
};

export const ACTION_LABELS: Record<LifecycleAction, string> = {
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
