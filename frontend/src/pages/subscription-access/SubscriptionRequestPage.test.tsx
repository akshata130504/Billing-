import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SubscriptionState } from '../../services/subscriptionAccessService';

type Role = 'owner' | 'admin' | 'finance' | 'viewer';
const RANK: Record<Role, number> = { viewer: 1, finance: 2, admin: 3, owner: 4 };
let role: Role = 'owner';
let access: Record<string, unknown> | null = null;

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ hasRole: (min: Role) => RANK[role] >= RANK[min], refreshMe: vi.fn(), access }),
}));
vi.mock('../../components/common/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));

const state = vi.fn();
const submit = vi.fn();
const withdraw = vi.fn();
vi.mock('../../services/subscriptionAccessService', () => ({
  subscriptionAccessService: { state: () => state(), submit: (b: unknown) => submit(b), withdraw: (id: string) => withdraw(id) },
}));

import { SubscriptionRequestPanel } from './SubscriptionRequestPage';
import { EntitlementGuard, TrialBanner } from '../../components/layout/Entitlements';
import registry from '../../entitlements/modules.json';

const MODULES = registry.modules.map((m) => ({
  key: m.key, label: m.label, description: m.description, base: Boolean((m as { base?: boolean }).base),
  requires: (m as { requires?: string[] }).requires ?? [],
}));

function makeState(overrides: Partial<SubscriptionState> = {}): SubscriptionState {
  return {
    access: {
      status: 'trial_expired', trial_started_at: '2026-10-01T00:00:00Z', trial_ends_at: '2026-10-04T00:00:00Z',
      module_access: 'entitled', modules: [], nav_items: [], seat_limit: null, seats_used: 2,
    },
    modules: MODULES,
    current_request: null,
    history: [],
    ...overrides,
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SubscriptionRequestPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SubscriptionRequestPanel', () => {
  beforeEach(() => {
    role = 'owner';
    state.mockReset();
    submit.mockReset();
    withdraw.mockReset();
  });

  it('lets an Owner choose modules, seats and billing cycle and submit', async () => {
    state.mockResolvedValue(makeState());
    submit.mockResolvedValue({});
    renderPanel();
    expect(await screen.findByText('Trial ended')).toBeInTheDocument();
    // Base modules are listed as always included, not as choices.
    expect(screen.getByText(/Always included: Customers/)).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /^Customers/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: /Timesheets/ }));
    expect(screen.getByRole('checkbox', { name: /^Projects/ })).toBeChecked(); // required module added
    fireEvent.click(screen.getByRole('checkbox', { name: /Quotes & CPQ/ }));
    fireEvent.change(screen.getByLabelText('User seats'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('radio', { name: 'Monthly' }));
    fireEvent.click(screen.getByRole('button', { name: /Send request/ }));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(submit).toHaveBeenCalledWith({ modules: ['quotes', 'projects', 'timesheets'], seats: 7, billing_cycle: 'monthly', notes: null });
  });

  it('refuses fewer seats than members already use, before calling the API', async () => {
    state.mockResolvedValue(makeState());
    renderPanel();
    fireEvent.change(await screen.findByLabelText('User seats'), { target: { value: '1' } });
    // (the browser's own min validation also stops the button; submit the form to test ours)
    fireEvent.submit(screen.getByRole('form', { name: 'Request a subscription' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('between 2 and 10000');
    expect(submit).not.toHaveBeenCalled();
  });

  it('tells Finance and Viewer members to ask an Owner or Admin', async () => {
    role = 'viewer';
    state.mockResolvedValue(makeState());
    renderPanel();
    expect(await screen.findByText(/Ask your organization Owner or an Admin/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Send request/ })).not.toBeInTheDocument();
  });

  it('shows the open request and lets an Admin withdraw it', async () => {
    role = 'admin';
    state.mockResolvedValue(makeState({
      current_request: {
        id: 'req-1', organization_id: 'o', status: 'submitted', modules: ['reports'], seats: 4, billing_cycle: 'annual',
        notes: null, created_at: '2026-10-05T00:00:00Z', reviewed_at: null, decision_reason: null,
        approved_modules: null, approved_seats: null, approved_billing_cycle: null,
      },
    }));
    withdraw.mockResolvedValue({});
    renderPanel();
    expect(await screen.findByText(/waiting for Rooman review/)).toBeInTheDocument();
    expect(screen.getByText(/Reports & Revenue Intelligence/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Send request/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Withdraw request' }));
    await waitFor(() => expect(withdraw).toHaveBeenCalledWith('req-1'));
  });

  it('shows an active plan without a request form', async () => {
    state.mockResolvedValue(makeState({
      access: { status: 'active', trial_started_at: null, trial_ends_at: null, module_access: 'entitled',
        modules: ['customers', 'quotes'], nav_items: [], seat_limit: 5, seats_used: 2 },
    }));
    renderPanel();
    expect(await screen.findByText('Active subscription')).toBeInTheDocument();
    expect(screen.getByText(/of 5/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Send request/ })).not.toBeInTheDocument();
  });
});

describe('EntitlementGuard and TrialBanner', () => {
  function renderAt(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <TrialBanner />
        <Routes>
          <Route path="*" element={<EntitlementGuard><div>Page body</div></EntitlementGuard>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it('blocks a direct URL to a module outside the plan', () => {
    access = { status: 'active', nav_items: ['overview', 'customers', 'quotes'], trial_ends_at: null };
    renderAt('/reports');
    expect(screen.getByText('Reports & Analytics is not in your plan')).toBeInTheDocument();
    expect(screen.queryByText('Page body')).not.toBeInTheDocument();
  });

  it('allows plan modules and pages that belong to no module', () => {
    access = { status: 'active', nav_items: ['overview', 'customers', 'quotes'], trial_ends_at: null };
    renderAt('/quotes/abc');
    expect(screen.getByText('Page body')).toBeInTheDocument();
    renderAt('/subscription');
    expect(screen.getAllByText('Page body').length).toBe(2);
  });

  it('shows the trial countdown with a link to choose a plan', () => {
    access = { status: 'trial', nav_items: [], trial_ends_at: new Date(Date.now() + 2.5 * 86_400_000).toISOString() };
    renderAt('/dashboard');
    expect(screen.getByRole('status')).toHaveTextContent('Your free trial ends in 3 days.');
    expect(screen.getByRole('link', { name: 'Choose your plan' })).toHaveAttribute('href', '/subscription');
  });
});
