import { Suspense } from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

type Role = 'owner' | 'admin' | 'finance' | 'viewer';
const RANK: Record<Role, number> = { viewer: 1, finance: 2, admin: 3, owner: 4 };

let auth: {
  role: Role;
  status: string;
  reason?: string | null;
  /** /auth/me access.status (the server's effective status), when present. */
  accessStatus?: string;
  /** /auth/me access.module_access ('trial' only for the legacy request-and-approve trial). */
  moduleAccess?: string;
  organizations: { id: string; name: string; slug: string; role: string }[];
};
const switchOrganization = vi.fn();

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
    organization: { id: 'org-1', name: 'Acme Pvt Ltd', slug: 'acme', status: auth.status, status_reason: auth.reason ?? null },
    organizations: auth.organizations,
    access: auth.accessStatus
      ? { status: auth.accessStatus, trial_ends_at: null, nav_items: [], module_access: auth.moduleAccess ?? 'unrestricted' }
      : null,
    logout: vi.fn(),
    refreshMe: vi.fn(),
    switchOrganization,
    hasRole: (min: Role) => RANK[auth.role] >= RANK[min],
  }),
}));

vi.mock('../pages/subscription-access/SubscriptionRequestPage', () => ({
  SubscriptionRequestPage: () => <div>Subscription page</div>,
  TrialExpiredScreen: ({ organizationName }: { organizationName: string }) => <div>Trial ended for {organizationName}</div>,
}));

import { LegacySubscriptionRoute, ProtectedRoute } from './index';

function renderGuard() {
  return render(
    <MemoryRouter initialEntries={['/app']}>
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/app" element={<div>Workspace content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProtectedRoute organization lifecycle', () => {
  beforeEach(() => {
    auth = { role: 'owner', status: 'active', organizations: [] };
    switchOrganization.mockReset();
  });

  it('renders the workspace for an active organization', () => {
    renderGuard();
    expect(screen.getByText('Workspace content')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('renders the workspace during the trial', () => {
    auth.status = 'trial';
    auth.accessStatus = 'trial';
    renderGuard();
    expect(screen.getByText('Workspace content')).toBeInTheDocument();
  });

  it('shows only the subscription screen once the server says the trial has ended', async () => {
    auth.status = 'trial'; // stored status not yet updated by the scheduler
    auth.accessStatus = 'trial_expired';
    renderGuard();
    expect(await screen.findByText('Trial ended for Acme Pvt Ltd')).toBeInTheDocument();
    expect(screen.queryByText('Workspace content')).not.toBeInTheDocument();
  });

  it('no longer shows an approval screen: a pending organization gets the workspace', () => {
    auth.status = 'pending_approval';
    renderGuard();
    expect(screen.getByText('Workspace content')).toBeInTheDocument();
    expect(screen.queryByText(/pending approval/i)).not.toBeInTheDocument();
  });

  it('shows the rejection reason', () => {
    auth.status = 'rejected';
    auth.reason = 'Incomplete KYC';
    renderGuard();
    expect(screen.getByText('Registration Not Approved')).toBeInTheDocument();
    expect(screen.getByText('Incomplete KYC')).toBeInTheDocument();
    expect(screen.queryByText('Workspace content')).not.toBeInTheDocument();
  });

  it.each<Role>(['owner', 'admin'])('suspended %s keeps read-only access under a banner', (role) => {
    auth.status = 'suspended';
    auth.role = role;
    auth.reason = 'Unpaid platform fees';
    renderGuard();
    expect(screen.getByText('Workspace content')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(/suspended/i);
    expect(screen.getByRole('status')).toHaveTextContent(/read-only/i);
    expect(screen.getByRole('status')).toHaveTextContent('Unpaid platform fees');
  });

  it.each<Role>(['finance', 'viewer'])('suspended %s is locked out', (role) => {
    auth.status = 'suspended';
    auth.role = role;
    renderGuard();
    expect(screen.getByText('Organization Suspended')).toBeInTheDocument();
    expect(screen.queryByText('Workspace content')).not.toBeInTheDocument();
  });

  it('pending deletion: owner read-only, admin locked out', () => {
    auth.status = 'pending_deletion';
    renderGuard();
    expect(screen.getByText('Workspace content')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(/scheduled for deletion/i);
  });

  it('pending deletion locks out an admin', () => {
    auth.status = 'pending_deletion';
    auth.role = 'admin';
    renderGuard();
    expect(screen.getByText('Organization Scheduled for Deletion')).toBeInTheDocument();
    expect(screen.queryByText('Workspace content')).not.toBeInTheDocument();
  });

  it('lets a locked-out user switch to another organization', () => {
    auth.status = 'suspended';
    auth.role = 'viewer';
    auth.organizations = [
      { id: 'org-1', name: 'Acme Pvt Ltd', slug: 'acme', role: 'viewer' },
      { id: 'org-2', name: 'Beta Traders', slug: 'beta', role: 'owner' },
    ];
    renderGuard();
    screen.getByRole('button', { name: 'Beta Traders' }).click();
    expect(switchOrganization).toHaveBeenCalledWith('org-2');
    expect(screen.queryByRole('button', { name: 'Acme Pvt Ltd' })).not.toBeInTheDocument();
  });
});

describe('/subscription', () => {
  function renderSubscription() {
    return render(
      <MemoryRouter initialEntries={['/subscription']}>
        <Routes>
          {/* AppLayout provides the Suspense boundary for lazy pages in the app */}
          <Route path="/subscription" element={<Suspense fallback={null}><LegacySubscriptionRoute /></Suspense>} />
          <Route path="/settings/subscription" element={<div>Plans and billing</div>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  beforeEach(() => {
    auth = { role: 'owner', status: 'active', organizations: [] };
  });

  it.each(['unrestricted', 'entitled'])('redirects a %s organization to /settings/subscription', (moduleAccess) => {
    auth.accessStatus = 'active';
    auth.moduleAccess = moduleAccess;
    renderSubscription();
    expect(screen.getByText('Plans and billing')).toBeInTheDocument();
    expect(screen.queryByText('Subscription page')).not.toBeInTheDocument();
  });

  it('redirects when access is not known yet', () => {
    renderSubscription();
    expect(screen.getByText('Plans and billing')).toBeInTheDocument();
  });

  it('keeps the request page for an organization on the legacy module trial', async () => {
    auth.accessStatus = 'trial';
    auth.moduleAccess = 'trial';
    renderSubscription();
    expect(await screen.findByText('Subscription page')).toBeInTheDocument();
    expect(screen.queryByText('Plans and billing')).not.toBeInTheDocument();
  });
});
