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
      login: vi.fn(), me: vi.fn(), refresh: vi.fn(), sessions: vi.fn(),
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
      organizationActivity: vi.fn(), lifecycle: vi.fn(), staff: vi.fn(), staffMember: vi.fn(), jobs: vi.fn(),
      staffAction: vi.fn(), audit: vi.fn(), tenantAdmins: vi.fn(),
      entitlements: vi.fn(), updateEntitlements: vi.fn(), subscriptionRequests: vi.fn(), subscriptionRequest: vi.fn(),
      approveSubscriptionRequest: vi.fn(), rejectSubscriptionRequest: vi.fn(), provisionTenantAdmin: vi.fn(),
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
    documents: { customer_count: 12, quote_count: 5, invoice_count: 9, credit_note_count: 1, payment_count: 7, subscription_count: 3 },
    security: { members_with_two_factor: 2, active_members: 4, live_tenant_sessions: 3 },
    lifecycle: {
      status: 'active', status_changed_at: null, status_reason: null, status_changed_by: null,
      deletion_scheduled_for: null, jobs_paused: false, automation_running: true, renewals_waiting: 0,
    },
    allowed_actions: ['suspend', 'schedule_deletion', 'pause_jobs', 'revoke_sessions'],
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
  recent_activity: [{ id: 'ra1', occurred_at: '2026-09-30T09:30:00Z', action: 'ORGANIZATION_SUSPENDED', result: 'success',
    platform_staff_id: 's', staff_email_snapshot: 'ops@rooman.test', staff_role_snapshot: 'platform_operations',
    organization_id: 'org-2', organization_name_snapshot: 'Beta Corp', target_type: 'organization', target_id: 'org-2',
    reason: 'x', ticket_ref: null, ip_address: null, user_agent: null, details: null }],
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
  api.tenantAdmins.mockResolvedValue([]);
  api.entitlements.mockResolvedValue({ organization_id: 'org-1', module_access: 'unrestricted', modules: [], seat_limit: null, seats_used: 4 });
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
    expect(screen.getByText('Recent platform activity')).toBeInTheDocument();
    expect(screen.getByText('ops@rooman.test · Beta Corp')).toBeInTheDocument();
  });

  it('highlights organizations waiting for approval and links to the filtered directory', async () => {
    api.dashboard.mockResolvedValue({ ...DASHBOARD, organizations: { ...DASHBOARD.organizations, pending_approval: 2 } });
    renderAt('/');
    expect(await screen.findByText('2 organizations are waiting for approval.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review pending organizations' })).toHaveAttribute(
      'href', '/organizations?status=pending_approval',
    );
    expect(within(screen.getByRole('main')).getByText('Pending approval').closest('div')).toHaveTextContent('2');
  });

  it('highlights subscription requests waiting for review', async () => {
    api.dashboard.mockResolvedValue({ ...DASHBOARD, subscription_requests_pending: 3 });
    renderAt('/');
    expect(await screen.findByText('3 subscription requests are waiting for review.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review subscription requests' })).toHaveAttribute('href', '/subscription-requests');
    expect(within(screen.getByRole('main')).getByText('Subscription requests').closest('div')).toHaveTextContent('3');
  });

  it('shows no approval callout when nothing is pending', async () => {
    renderAt('/');
    await screen.findByText('Acme Traders');
    expect(screen.queryByRole('link', { name: 'Review pending organizations' })).not.toBeInTheDocument();
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
    expect(screen.getByText(/without an access grant: scoped, read-only and time-limited, approved by the organization.s Owner/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request access' })).toBeInTheDocument(); // administrators and support only
    for (const label of ['Suspend organization', 'Schedule deletion', 'Pause billing automation', 'Sign out all tenant users']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: 'Reactivate organization' })).not.toBeInTheDocument();
  });

  const PENDING = { status: 'pending_approval' as const, allowed_actions: ['approve', 'reject'] as OrganizationDetail['allowed_actions'] };

  it('approves a pending organization', async () => {
    api.organization.mockResolvedValueOnce(orgDetail(PENDING)).mockResolvedValue(orgDetail());
    api.lifecycle.mockResolvedValue({ organization: { ...ORG_SUMMARY, status: 'active' }, changed: {} });
    renderAt('/organizations/org-1');

    expect(await screen.findByText('Organization Pending Super Admin Approval')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve Organization' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Verified business documents' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^Approve/ }));
    await waitFor(() => expect(api.lifecycle).toHaveBeenCalledWith('org-1', 'approve', expect.objectContaining({ reason: 'Verified business documents' })));
  });

  it('rejects a pending organization only with a reason', async () => {
    api.organization.mockResolvedValueOnce(orgDetail(PENDING)).mockResolvedValue(orgDetail({ status: 'rejected', allowed_actions: [] }));
    api.lifecycle.mockResolvedValue({ organization: { ...ORG_SUMMARY, status: 'rejected' }, changed: {} });
    renderAt('/organizations/org-1');

    fireEvent.click(await screen.findByRole('button', { name: 'Reject Organization' }));
    const dialog = await screen.findByRole('dialog');
    const submit = within(dialog).getByRole('button', { name: /^Reject/ });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Could not verify the business registration' } });
    fireEvent.click(submit);
    await waitFor(() => expect(api.lifecycle).toHaveBeenCalledWith(
      'org-1', 'reject', expect.objectContaining({ reason: 'Could not verify the business registration' }),
    ));
  });

  it('hides approve and reject from non-administrators', async () => {
    api.organization.mockResolvedValue(orgDetail(PENDING));
    renderAt('/organizations/org-1', 'platform_operations');
    expect(await screen.findByText('Organization Pending Super Admin Approval')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve Organization' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reject Organization' })).not.toBeInTheDocument();
  });

  it('suspends with reason and ticket, asking for the password when the server requires step-up', async () => {
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

    const password = await within(dialog).findByLabelText(/^Password/);
    expect(password).toHaveAttribute('type', 'password');
    fireEvent.change(password, { target: { value: 'Platform-Passw0rd-2026!' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Verify and suspend' }));

    await waitFor(() => expect(auth.stepUp).toHaveBeenCalledWith('Platform-Passw0rd-2026!'));
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

  it('shows billing automation as held for a trial organization (BUG-17)', async () => {
    api.organization.mockResolvedValue(orgDetail({
      lifecycle: { ...orgDetail().lifecycle, automation_running: false, automation_state: 'held_trial',
        automation_label: 'Held - trial (no approved subscription)' },
    }));
    renderAt('/organizations/org-1');
    expect(await screen.findByText('Held - trial (no approved subscription)')).toBeInTheDocument();
    expect(screen.queryByText('Running')).not.toBeInTheDocument();
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
    expect(screen.getByRole('button', { name: 'Request access' })).toBeInTheDocument(); // support may request a grant
  });

  it('does not offer tenant access requests to Operations', async () => {
    api.organization.mockResolvedValue(orgDetail({ allowed_actions: ['suspend'] }));
    renderAt('/organizations/org-1', 'platform_operations');
    await screen.findByRole('button', { name: 'Suspend organization' });
    expect(screen.queryByRole('button', { name: 'Request access' })).not.toBeInTheDocument();
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
    // the same lifecycle event appears in both the lifecycle history and the full activity list
    expect(await screen.findAllByText('Organization suspended')).toHaveLength(2);
    expect(screen.getAllByText('Unpaid for 90 days')).toHaveLength(2);
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

  it('reports the scheduler as running from its heartbeat, not the API process flag (BUG-33)', async () => {
    api.health.mockResolvedValue({
      api: { status: 'ok', version: '0.1.0', environment: 'production' },
      database: { status: 'connected' },
      migrations: { status: 'at_head', current: 'x', head: 'x' },
      scheduler: { enabled: true, running: true, status: 'ok', last_finished_at: '2026-10-10T08:00:00Z', interval_minutes: 15,
        last_error_count: 0, total_runs: 40, last_counts: {} },
      platform: { auth_enabled: true, step_up_minutes: 15, session_idle_minutes: 30, session_max_hours: 8, deletion_waiting_days: 30 },
      integrations: { email_configured: true, payments_configured: true },
    });
    renderAt('/health');
    const label = await screen.findByText('Running (last run within the expected interval)');
    expect(label.parentElement).toHaveTextContent('Yes');
    expect(screen.queryByText('Enabled', { selector: 'dt' })).not.toBeInTheDocument();
  });

  it('shows an error state', async () => {
    api.health.mockRejectedValue(new PlatformApiError('Health check failed', 500));
    renderAt('/health');
    expect(await screen.findByText('Health check failed')).toBeInTheDocument();
  });
});

describe('phase 3 completion', () => {
  it('shows document counts and lifecycle history on the detail page', async () => {
    api.organization.mockResolvedValue(orgDetail());
    api.organizationActivity.mockImplementation((_id: string, _page: number, lifecycle: boolean) => Promise.resolve(lifecycle
      ? { items: [{ id: 'h1', occurred_at: '2026-09-30T08:00:00Z', action: 'TENANT_JOBS_PAUSED', result: 'success',
          platform_staff_id: 's', staff_email_snapshot: 'me@rooman.test', staff_role_snapshot: null, organization_id: 'org-1',
          organization_name_snapshot: null, target_type: null, target_id: null, reason: 'Paused for review', ticket_ref: 'T-7',
          ip_address: null, user_agent: null, details: null }], total: 1, page: 1, page_size: 20, total_pages: 1 }
      : { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 }));
    renderAt('/organizations/org-1');
    expect(await screen.findByText('Tenant jobs paused')).toBeInTheDocument();
    expect(screen.getByText('Paused for review')).toBeInTheDocument();
    const docs = screen.getByRole('heading', { name: 'Documents' }).closest('section')!;
    expect(within(docs).getByText('Customers')).toBeInTheDocument();
    expect(within(docs).getByText('12')).toBeInTheDocument();
    expect(within(docs).getByText('Credit notes')).toBeInTheDocument();
  });

  it('revokes tenant sessions through the reason dialog', async () => {
    api.organization.mockResolvedValue(orgDetail());
    api.lifecycle.mockResolvedValue({ organization: ORG_SUMMARY, changed: { tenant_sessions_revoked: 3 } });
    renderAt('/organizations/org-1');
    fireEvent.click(await screen.findByRole('button', { name: 'Sign out all tenant users' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Only this organization.s sessions end/)).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Suspected credential leak' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Sign out all tenant users' }));
    await waitFor(() => expect(api.lifecycle).toHaveBeenCalledWith('org-1', 'revoke_sessions', { reason: 'Suspected credential leak' }));
  });

  it('shows background job counts to administrators and operations, not support', async () => {
    const health = {
      api: { status: 'ok', version: '0.1.0', environment: 'development' }, database: { status: 'connected' },
      migrations: { status: 'at_head', current: 'x', head: 'x' }, scheduler: { enabled: true, status: 'ok', last_counts: {} },
      platform: { auth_enabled: true, step_up_minutes: 15, session_idle_minutes: 30, session_max_hours: 8, deletion_waiting_days: 30 },
      integrations: { email_configured: true, payments_configured: true },
    };
    api.health.mockResolvedValue(health);
    api.jobs.mockResolvedValue({ scheduler: health.scheduler, durable_jobs: { pending: 2, failed: 1 }, durable_jobs_failed_24h: 1,
      outbox: { pending: 0, failed: 4 }, webhooks_received_24h: 9, organizations_not_running: 2 });
    const { unmount } = renderAt('/health', 'platform_operations');
    expect(await screen.findByText('Background jobs')).toBeInTheDocument();
    expect(screen.getByText('Organizations not running automation').closest('div')).toHaveTextContent('2');
    unmount();
    api.jobs.mockClear();
    renderAt('/health', 'platform_support');
    await screen.findByText('Database: connected');
    expect(screen.queryByText('Background jobs')).not.toBeInTheDocument();
    expect(api.jobs).not.toHaveBeenCalled();
  });

  it('searches the audit log by text and date', async () => {
    api.audit.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50, total_pages: 0 });
    renderAt('/audit');
    await screen.findByText('No audit entries');
    fireEvent.change(screen.getByPlaceholderText(/Action, staff email, organization/), { target: { value: 'SUP-1234' } });
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-09-01T00:00' } });
    fireEvent.change(screen.getByLabelText('Target type'), { target: { value: 'organization' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(api.audit).toHaveBeenLastCalledWith(expect.objectContaining({
      q: 'SUP-1234', target_type: 'organization', since: new Date('2026-09-01T00:00').toISOString(),
    })));
  });
});


const REQUEST = {
  id: 'req-1', organization_id: 'org-9', organization_name: 'Trial Co', organization_slug: 'trial-co',
  organization_status: 'trial_expired' as const, trial_ends_at: '2026-10-04T00:00:00Z', status: 'submitted' as const,
  modules: ['quotes'], seats: 5, billing_cycle: 'annual' as const, notes: 'Need CPQ', created_at: '2026-10-05T00:00:00Z',
  reviewed_at: null, decision_reason: null, approved_modules: null, approved_seats: null, approved_billing_cycle: null,
  requested_by_email: 'owner@trial.test', requested_by_name: 'Tia Owner', seats_used: 2,
};

describe('subscription requests', () => {
  beforeEach(() => {
    api.subscriptionRequests.mockResolvedValue({ items: [REQUEST], total: 1, page: 1, page_size: 25 });
  });

  it('support can read the queue but cannot review', async () => {
    renderAt('/subscription-requests', 'platform_support');
    expect(await screen.findByText('Trial Co')).toBeInTheDocument();
    expect(screen.getByText(/Only a Platform Administrator can approve or reject/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Review' })).not.toBeInTheDocument();
  });

  it('administrator approves with modified seats, reason and step-up', async () => {
    api.approveSubscriptionRequest
      .mockRejectedValueOnce(new PlatformApiError('Confirm your password.', 403, 'STEP_UP_REQUIRED'))
      .mockResolvedValueOnce({ ...REQUEST, status: 'approved' });
    auth.stepUp.mockResolvedValue({});
    renderAt('/subscription-requests');
    fireEvent.click(await screen.findByRole('button', { name: 'Review' }));
    fireEvent.change(screen.getByLabelText('User seats'), { target: { value: '8' } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve with changes' }));
    fireEvent.change(await screen.findByLabelText(/Reason/), { target: { value: 'Approved after the sales call' } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    const stepUpForm = await screen.findByRole('form', { name: 'Confirm with your password' });
    fireEvent.change(within(stepUpForm).getByLabelText(/^Password/), { target: { value: 'secret-pass' } });
    fireEvent.submit(stepUpForm);
    await waitFor(() => expect(api.approveSubscriptionRequest).toHaveBeenCalledTimes(2));
    expect(api.approveSubscriptionRequest).toHaveBeenLastCalledWith('req-1', {
      modules: ['quotes'], seats: 8, billing_cycle: 'annual', reason: 'Approved after the sales call',
    });
    await waitFor(() => expect(api.subscriptionRequests).toHaveBeenCalledTimes(2));
  });
});


describe('create admin after approval', () => {
  const APPROVED = { ...REQUEST, status: 'approved' as const, approved_modules: ['quotes'], approved_seats: 5,
    approved_billing_cycle: 'annual' as const, organization_status: 'active' as const };

  beforeEach(() => {
    api.subscriptionRequests.mockResolvedValue({ items: [APPROVED], total: 1, page: 1, page_size: 25 });
  });

  it('support sees approved requests but no Create Admin', async () => {
    renderAt('/subscription-requests', 'platform_support');
    expect(await screen.findByText('Trial Co')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create Admin' })).not.toBeInTheDocument();
  });

  it('administrator creates the tenant Admin with fixed organization and role, after password step-up', async () => {
    api.provisionTenantAdmin
      .mockRejectedValueOnce(new PlatformApiError('Confirm your password.', 403, 'STEP_UP_REQUIRED'))
      .mockResolvedValueOnce({
        organization_id: 'org-9', organization_name: 'Trial Co', user_id: 'u-1', membership_id: 'm-1',
        full_name: 'Acme Admin', email: 'admin@acme.test', role: 'admin', status: 'invited',
        invite_expires_at: '2026-10-10T00:00:00Z', email_delivered: true,
      });
    auth.stepUp.mockResolvedValue({});
    renderAt('/subscription-requests');
    fireEvent.click(await screen.findByRole('button', { name: 'Create Admin' }));
    const form = await screen.findByRole('form', { name: 'Create Admin' });
    expect(within(form).getByLabelText(/^Organization/)).toHaveValue('Trial Co');
    expect(within(form).getByLabelText(/^Organization/)).toBeDisabled();
    expect(within(form).getByLabelText(/^Role/)).toHaveValue('Admin');
    expect(within(form).getByLabelText(/^Role/)).toBeDisabled();
    expect(within(form).queryByLabelText(/password/i)).not.toBeInTheDocument();
    fireEvent.change(within(form).getByLabelText(/^Admin name/), { target: { value: 'Acme Admin' } });
    fireEvent.change(within(form).getByLabelText(/^Admin email/), { target: { value: 'admin@acme.test' } });
    fireEvent.submit(form);
    const stepUpForm = await screen.findByRole('form', { name: 'Confirm with your password' });
    fireEvent.change(within(stepUpForm).getByLabelText(/^Password/), { target: { value: 'secret-pass' } });
    fireEvent.submit(stepUpForm);
    expect(await screen.findByText('Admin created for Trial Co')).toBeInTheDocument();
    expect(screen.getByText(/The invitation email was sent/)).toBeInTheDocument();
    expect(api.provisionTenantAdmin).toHaveBeenLastCalledWith('org-9', { full_name: 'Acme Admin', email: 'admin@acme.test' });
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(await screen.findByText('Admin invited: admin@acme.test (invitation sent)')).toBeInTheDocument();
  });
});
