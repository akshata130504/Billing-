import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '../../components/common/Toast';
import { PlatformRoutes } from '../PlatformApp';
import { PlatformApiError, platformApi, type PlatformMe, type PlatformRole } from '../platformApi';
import { consoleApi, type OrganizationDetail } from '../consoleApi';

vi.mock('../platformApi', async () => {
  const actual = await vi.importActual<typeof import('../platformApi')>('../platformApi');
  return {
    ...actual,
    platformApi: {
      login: vi.fn(), verifyTwoFactor: vi.fn(), me: vi.fn(), refresh: vi.fn(), sessions: vi.fn(),
      revokeSession: vi.fn(), logout: vi.fn(), logoutAll: vi.fn(), stepUp: vi.fn(),
    },
  };
});
vi.mock('../consoleApi', async () => {
  const actual = await vi.importActual<typeof import('../consoleApi')>('../consoleApi');
  return {
    ...actual,
    consoleApi: {
      dashboard: vi.fn(), health: vi.fn(), organizations: vi.fn(), organization: vi.fn(),
      organizationActivity: vi.fn(), lifecycle: vi.fn(), staff: vi.fn(), staffMember: vi.fn(),
      staffAction: vi.fn(), audit: vi.fn(),
    },
  };
});

type Mocked<T> = { [K in keyof T]: ReturnType<typeof vi.fn> };
const auth = platformApi as unknown as Mocked<typeof platformApi>;
const api = consoleApi as unknown as Mocked<typeof consoleApi>;

function me(role: PlatformRole = 'platform_administrator'): PlatformMe {
  return {
    staff: { id: 'staff-me', email: 'me@rooman.test', full_name: 'Priya Platform', role },
    session_id: 'sess-me',
    session_expires_at: '2026-10-01T10:00:00Z',
    access_expires_in: 600,
  };
}

const EMPTY_PAGE = { items: [], total: 0, page: 1, page_size: 25, total_pages: 0 };

const ORG_SUMMARY = {
  id: 'org-1', name: 'Acme Traders', slug: 'acme-traders', status: 'active' as const, jobs_paused: false,
  member_count: 4, created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-20T10:00:00Z',
  status_changed_at: null, deletion_scheduled_for: null,
};

function orgDetail(overrides: Partial<OrganizationDetail> = {}): OrganizationDetail {
  return {
    ...ORG_SUMMARY,
    country: 'IN',
    timezone: 'Asia/Kolkata',
    owners: [{ full_name: 'Olive Owner', email: 'owner@acme.test' }],
    members: { active: 4, invited: 1, deactivated: 0, by_role: { owner: 1, admin: 1, finance: 1, viewer: 1 } },
    security: { members_with_two_factor: 2, active_members: 4, live_tenant_sessions: 3 },
    lifecycle: {
      status: 'active', status_changed_at: null, status_reason: null, status_changed_by: null,
      deletion_scheduled_for: null, jobs_paused: false, automation_running: true, renewals_waiting: 0,
    },
    allowed_actions: ['suspend', 'schedule_deletion', 'pause_jobs'],
    ...overrides,
  };
}

const DASHBOARD = {
  organizations: { active: 7, suspended: 2, pending_deletion: 1, deleted: 0, total: 10, jobs_paused: 3 },
  created_last_7_days: 4,
  recent_organizations: [{ id: 'org-1', name: 'Acme Traders', slug: 'acme-traders', status: 'active', created_at: '2026-09-29T10:00:00Z' }],
  staff: { total: 3, active: 2 },
  health: { api: 'ok', database: 'connected', migrations: 'at_head', scheduler: 'ok' },
  scheduler: { enabled: true, status: 'ok', last_finished_at: '2026-09-30T09:00:00Z', last_counts: {} },
};

function renderAt(path: string, role: PlatformRole = 'platform_administrator') {
  auth.me.mockResolvedValue(me(role));
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <PlatformRoutes />
      </MemoryRouter>
    </ToastProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.dashboard.mockResolvedValue(DASHBOARD);
  api.organizationActivity.mockResolvedValue({ ...EMPTY_PAGE, page_size: 20 });
});

describe('navigation and roles', () => {
  it('shows every section to a Platform Administrator and marks the active page', async () => {
    renderAt('/organizations');
    api.organizations.mockResolvedValue(EMPTY_PAGE);
    const nav = await screen.findByRole('navigation', { name: 'Platform console' });
    for (const label of ['Dashboard', 'Organizations', 'Platform staff', 'Audit log', 'System health', 'My account']) {
      expect(within(nav).getByRole('link', { name: label })).toBeInTheDocument();
    }
    expect(within(nav).getByRole('link', { name: 'Organizations' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'Dashboard' })).not.toHaveAttribute('aria-current');
  });

  it('hides administrator sections from Operations and Support', async () => {
    for (const role of ['platform_operations', 'platform_support'] as PlatformRole[]) {
      const { unmount } = renderAt('/', role);
      const nav = await screen.findByRole('navigation', { name: 'Platform console' });
      expect(within(nav).queryByRole('link', { name: 'Platform staff' })).not.toBeInTheDocument();
      expect(within(nav).queryByRole('link', { name: 'Audit log' })).not.toBeInTheDocument();
      unmount();
    }
  });

  it('blocks a non-administrator who opens an administrator page directly', async () => {
    renderAt('/staff', 'platform_support');
    expect(await screen.findByText('Not available for your role')).toBeInTheDocument();
    expect(api.staff).not.toHaveBeenCalled();
  });

  it('opens and closes the mobile menu', async () => {
    renderAt('/');
    await screen.findByRole('heading', { name: 'Platform dashboard' });
    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
    expect(screen.getAllByRole('navigation', { name: 'Platform console' })).toHaveLength(2);
    fireEvent.click(screen.getAllByRole('button', { name: 'Close menu' })[0]);
    expect(screen.getAllByRole('navigation', { name: 'Platform console' })).toHaveLength(1);
  });
});

describe('dashboard', () => {
  it('shows counts, recent organizations, health and the current session', async () => {
    renderAt('/');
    expect(await screen.findByText('Acme Traders')).toBeInTheDocument();
    const main = screen.getByRole('main');
    expect(within(main).getByText('Organizations').closest('div')).toHaveTextContent('10');
    expect(within(main).getByText('Suspended').closest('div')).toHaveTextContent('2');
    expect(within(main).getByText('Pending deletion').closest('div')).toHaveTextContent('1');
    expect(screen.getByText('API: ok')).toBeInTheDocument();
    expect(screen.getByText('Migrations: at head')).toBeInTheDocument();
    expect(screen.getByText('Priya Platform (me@rooman.test)')).toBeInTheDocument();
  });

  it('shows an error with retry', async () => {
    api.dashboard.mockRejectedValueOnce(new PlatformApiError('Service unavailable', 503)).mockResolvedValueOnce(DASHBOARD);
    renderAt('/');
    expect(await screen.findByText('Service unavailable')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /try again|retry/i }));
    expect(await screen.findByText('Acme Traders')).toBeInTheDocument();
  });
});

describe('organizations directory', () => {
  it('lists organizations and links to the detail page', async () => {
    api.organizations.mockResolvedValue({ ...EMPTY_PAGE, items: [ORG_SUMMARY], total: 1, total_pages: 1 });
    renderAt('/organizations');
    const link = await screen.findByRole('link', { name: 'Acme Traders' });
    expect(link).toHaveAttribute('href', '/organizations/org-1');
    expect(screen.getByText('acme-traders')).toBeInTheDocument();
  });

  it('searches, filters and sorts through the API (server-side)', async () => {
    api.organizations.mockResolvedValue(EMPTY_PAGE);
    renderAt('/organizations');
    await screen.findByText('No organizations found');
    fireEvent.change(screen.getByLabelText('Search organizations'), { target: { value: 'acme' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(api.organizations).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'acme', page: 1 })));
    fireEvent.change(screen.getByLabelText('Filter by status'), { target: { value: 'suspended' } });
    await waitFor(() => expect(api.organizations).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'acme', status: 'suspended' })));
    fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'name' } });
    await waitFor(() => expect(api.organizations).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'name' })));
    expect(screen.getByText('No organization matches these filters.')).toBeInTheDocument();
  });

  it('shows a loading state, then an error with retry', async () => {
    let reject: (e: unknown) => void = () => {};
    api.organizations.mockReturnValueOnce(new Promise((_, r) => { reject = r; }));
    renderAt('/organizations');
    expect(await screen.findByText('Loading organizations...')).toBeInTheDocument();
    reject(new PlatformApiError('Directory unavailable', 500));
    expect(await screen.findByText('Directory unavailable')).toBeInTheDocument();
  });
});

describe('organization detail', () => {
  it('shows overview, lifecycle, members, security and no tenant data access', async () => {
    api.organization.mockResolvedValue(orgDetail());
    renderAt('/organizations/org-1');
    expect(await screen.findByRole('heading', { name: /Acme Traders/ })).toBeInTheDocument();
    expect(screen.getByText('Olive Owner · owner@acme.test')).toBeInTheDocument();
    expect(screen.getByText('2 of 4')).toBeInTheDocument();
    expect(screen.getByText(/access grants approved by the tenant are a future capability/)).toBeInTheDocument();
    for (const label of ['Suspend organization', 'Schedule deletion', 'Pause billing automation']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: 'Reactivate organization' })).not.toBeInTheDocument();
  });

  it('suspends with reason and ticket, asking for a fresh code when the server requires step-up', async () => {
    api.organization.mockResolvedValueOnce(orgDetail()).mockResolvedValue(
      orgDetail({ status: 'suspended', allowed_actions: ['reactivate', 'schedule_deletion', 'pause_jobs'] })
    );
    api.lifecycle
      .mockRejectedValueOnce(new PlatformApiError('Confirm it is you.', 403, 'STEP_UP_REQUIRED'))
      .mockResolvedValueOnce({ organization: { ...ORG_SUMMARY, status: 'suspended' }, changed: {} });
    auth.stepUp.mockResolvedValue({ step_up_expires_at: '2026-09-30T10:15:00Z', expires_in: 900 });
    renderAt('/organizations/org-1');

    fireEvent.click(await screen.findByRole('button', { name: 'Suspend organization' }));
    const dialog = await screen.findByRole('dialog');
    const submit = within(dialog).getByRole('button', { name: 'Suspend' });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Unpaid platform invoice for 90 days' } });
    expect(submit).toBeDisabled(); // ticket is required for suspension
    fireEvent.change(within(dialog).getByLabelText(/^Ticket reference/), { target: { value: 'SUP-1234' } });
    fireEvent.click(submit);

    const code = await within(dialog).findByLabelText(/^Authenticator code/);
    fireEvent.change(code, { target: { value: '123456' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Verify and suspend' }));

    await waitFor(() => expect(auth.stepUp).toHaveBeenCalledWith('123456'));
    await waitFor(() => expect(api.lifecycle).toHaveBeenCalledTimes(2));
    expect(api.lifecycle).toHaveBeenLastCalledWith('org-1', 'suspend', { reason: 'Unpaid platform invoice for 90 days', ticket_ref: 'SUP-1234' });
    expect(await screen.findByText('Suspend organization done')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Reactivate organization' })).toBeInTheDocument();
  });

  it('warns that reactivation keeps automation paused and shows waiting renewals', async () => {
    api.organization.mockResolvedValue(orgDetail({
      status: 'suspended',
      lifecycle: { ...orgDetail().lifecycle, status: 'suspended', automation_running: false, renewals_waiting: 3 },
      allowed_actions: ['reactivate'],
    }));
    renderAt('/organizations/org-1', 'platform_operations');
    fireEvent.click(await screen.findByRole('button', { name: 'Reactivate organization' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Nothing that fell due during the suspension is replayed automatically/)).toBeInTheDocument();
    expect(within(dialog).getByText(/3 subscription renewal\(s\) are already due/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^Ticket reference \(optional\)/)).toBeInTheDocument();
  });

  it('shows server errors inside the dialog', async () => {
    api.organization.mockResolvedValue(orgDetail());
    api.lifecycle.mockRejectedValue(new PlatformApiError('Cannot suspend an organization that is suspended.', 409, 'CONFLICT'));
    renderAt('/organizations/org-1');
    fireEvent.click(await screen.findByRole('button', { name: 'Suspend organization' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Duplicate click from a colleague' } });
    fireEvent.change(within(dialog).getByLabelText(/^Ticket reference/), { target: { value: 'SUP-9' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Suspend' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Cannot suspend an organization that is suspended.');
  });

  it('shows no lifecycle buttons for Support', async () => {
    api.organization.mockResolvedValue(orgDetail({ allowed_actions: [] }));
    renderAt('/organizations/org-1', 'platform_support');
    expect(await screen.findByText(/Your platform role cannot change this organization's lifecycle/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Suspend organization' })).not.toBeInTheDocument();
  });

  it('lists platform activity for the organization', async () => {
    api.organization.mockResolvedValue(orgDetail());
    api.organizationActivity.mockResolvedValue({
      items: [{ id: 'a1', occurred_at: '2026-09-30T08:00:00Z', action: 'ORGANIZATION_SUSPENDED', result: 'success',
        platform_staff_id: 'staff-me', staff_email_snapshot: 'me@rooman.test', staff_role_snapshot: 'platform_administrator',
        organization_id: 'org-1', organization_name_snapshot: 'Acme Traders', target_type: 'organization', target_id: 'org-1',
        reason: 'Unpaid for 90 days', ticket_ref: 'SUP-1', ip_address: null, user_agent: null, details: null }],
      total: 1, page: 1, page_size: 20, total_pages: 1,
    });
    renderAt('/organizations/org-1');
    expect(await screen.findByText('Organization suspended')).toBeInTheDocument();
    expect(screen.getByText('Unpaid for 90 days')).toBeInTheDocument();
  });

  it('shows not found for an unknown organization', async () => {
    api.organization.mockRejectedValue(new PlatformApiError('Organization not found.', 404));
    renderAt('/organizations/missing');
    expect(await screen.findByText('Organization not found')).toBeInTheDocument();
  });
});

describe('platform staff', () => {
  const STAFF = [
    { id: 'staff-me', email: 'me@rooman.test', full_name: 'Priya Platform', role: 'platform_administrator', is_active: true,
      deactivated_at: null, two_factor_enrolled: true, last_login_at: '2026-09-30T08:00:00Z', created_at: null, active_sessions: 1, sign_in_locked: false },
    { id: 'staff-2', email: 'ops@rooman.test', full_name: 'Omar Ops', role: 'platform_operations', is_active: true,
      deactivated_at: null, two_factor_enrolled: true, last_login_at: null, created_at: null, active_sessions: 2, sign_in_locked: true },
    { id: 'staff-3', email: 'gone@rooman.test', full_name: 'Gita Gone', role: 'platform_support', is_active: false,
      deactivated_at: '2026-09-01T08:00:00Z', two_factor_enrolled: true, last_login_at: null, created_at: null, active_sessions: 0, sign_in_locked: false },
  ];

  it('lists staff with role, status and security, never offering to deactivate yourself', async () => {
    api.staff.mockResolvedValue({ items: STAFF });
    renderAt('/staff');
    const selfRow = (await screen.findByText('Priya Platform (you)')).closest('tr')!;
    expect(within(selfRow).queryByRole('button', { name: 'Deactivate' })).not.toBeInTheDocument();
    const opsRow = screen.getByText('Omar Ops').closest('tr')!;
    expect(within(opsRow).getByText('Platform Operations')).toBeInTheDocument();
    expect(within(opsRow).getByText('Sign-in locked')).toBeInTheDocument();
    expect(within(opsRow).getByRole('button', { name: 'Deactivate' })).toBeInTheDocument();
    const goneRow = screen.getByText('Gita Gone').closest('tr')!;
    expect(within(goneRow).getByText('Deactivated')).toBeInTheDocument();
    expect(within(goneRow).getByRole('button', { name: 'Reactivate' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /invite|add staff|create/i })).not.toBeInTheDocument();
  });

  it('deactivates a staff member with a reason', async () => {
    api.staff.mockResolvedValue({ items: STAFF });
    api.staffAction.mockResolvedValue({ ...STAFF[1], is_active: false });
    renderAt('/staff');
    const opsRow = (await screen.findByText('Omar Ops')).closest('tr')!;
    fireEvent.click(within(opsRow).getByRole('button', { name: 'Deactivate' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Left the operations team' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate' }));
    await waitFor(() => expect(api.staffAction).toHaveBeenCalledWith('staff-2', 'deactivate', { reason: 'Left the operations team' }));
  });

  it('shows session metadata for a staff member', async () => {
    api.staff.mockResolvedValue({ items: STAFF });
    api.staffMember.mockResolvedValue({ ...STAFF[1], is_self: false, sessions: [
      { id: 's-9', created_at: '2026-09-30T07:00:00Z', last_used_at: '2026-09-30T08:00:00Z', expires_at: '2026-09-30T15:00:00Z',
        ip_address: '10.1.1.1', user_agent: 'Firefox on Linux', current: false },
    ] });
    renderAt('/staff');
    fireEvent.click(await screen.findByRole('button', { name: 'Omar Ops' }));
    expect(await screen.findByText('Firefox on Linux')).toBeInTheDocument();
    expect(screen.getByText('Locked after failed attempts')).toBeInTheDocument();
  });

  it('shows an empty state', async () => {
    api.staff.mockResolvedValue({ items: [] });
    renderAt('/staff');
    expect(await screen.findByText('No platform staff')).toBeInTheDocument();
  });
});

describe('audit log', () => {
  const ENTRY = {
    id: 'e1', occurred_at: '2026-09-30T08:00:00Z', action: 'PLATFORM_STAFF_DEACTIVATED', result: 'success',
    platform_staff_id: 'staff-me', staff_email_snapshot: 'me@rooman.test', staff_role_snapshot: 'platform_administrator',
    organization_id: null, organization_name_snapshot: null, target_type: 'platform_staff', target_id: 'staff-2',
    reason: 'Left the team', ticket_ref: null, ip_address: '10.0.0.1', user_agent: 'Chrome', details: { sessions_revoked: 2 },
  };

  it('shows entries, expands details and filters through the API', async () => {
    api.audit.mockResolvedValue({ items: [ENTRY], total: 1, page: 1, page_size: 50, total_pages: 1 });
    renderAt('/audit');
    fireEvent.click(await screen.findByText('Staff deactivated'));
    expect(screen.getByText('PLATFORM_STAFF_DEACTIVATED')).toBeInTheDocument();
    expect(screen.getByText(/"sessions_revoked": 2/)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('e.g. ORGANIZATION_SUSPENDED'), { target: { value: 'organization_suspended' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(api.audit).toHaveBeenLastCalledWith(expect.objectContaining({ action: 'ORGANIZATION_SUSPENDED', page: 1 })));
    expect(screen.queryByRole('button', { name: /delete|edit|purge/i })).not.toBeInTheDocument();
  });

  it('shows an empty state', async () => {
    api.audit.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50, total_pages: 0 });
    renderAt('/audit');
    expect(await screen.findByText('No audit entries')).toBeInTheDocument();
  });
});

describe('system health', () => {
  it('shows service states without connection details', async () => {
    api.health.mockResolvedValue({
      api: { status: 'ok', version: '0.1.0', environment: 'development' },
      database: { status: 'connected' },
      migrations: { status: 'at_head', current: '7a8b9c0d1e2f', head: '7a8b9c0d1e2f' },
      scheduler: { enabled: true, status: 'stale', last_finished_at: '2026-09-29T08:00:00Z', interval_minutes: 5,
        last_error_count: 0, total_runs: 12, last_counts: { renewals: 3, skipped_org_inactive: 2 } },
      platform: { auth_enabled: true, step_up_minutes: 15, session_idle_minutes: 30, session_max_hours: 8, deletion_waiting_days: 30 },
      integrations: { email_configured: true, payments_configured: false },
    });
    renderAt('/health');
    expect(await screen.findByText('Database: connected')).toBeInTheDocument();
    expect(screen.getByText('Migrations: at head')).toBeInTheDocument();
    expect(screen.getByText('stale')).toBeInTheDocument();
    expect(screen.getByText('Skipped (suspended or paused)')).toBeInTheDocument();
    expect(screen.getByText('Payment gateway not configured')).toBeInTheDocument();
    expect(screen.getByText('30 days')).toBeInTheDocument();
  });

  it('shows an error state', async () => {
    api.health.mockRejectedValue(new PlatformApiError('Health check failed', 500));
    renderAt('/health');
    expect(await screen.findByText('Health check failed')).toBeInTheDocument();
  });
});
