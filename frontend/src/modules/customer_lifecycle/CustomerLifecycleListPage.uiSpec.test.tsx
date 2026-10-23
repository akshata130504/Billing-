/**
 * The Customer Lifecycle page honours its visual-editor spec (appUi/specs/customer_lifecycle.json) and renders exactly its
 * built-in UI without configuration. Rendered against the preview sample-data adapter
 * (its GETs come from platform/uiPreview/fixtures/customer_lifecycle.ts).
 */
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from '../../services/apiClient';
import { previewAdapter } from '../../platform/uiPreview/sampleData';
import { ToastProvider } from '../../components/common/Toast';
import { AuthContext, type AuthContextValue } from '../../hooks/useAuth';
import { UiConfigOverride, type UiSelection } from '../../appUi/UiConfigContext';
import type { PageConfigs } from '../../appUi/registry';
import { CustomerLifecycleListPage } from './CustomerLifecycleListPage';

const NOW = '2026-10-01T09:00:00Z';
const fail = async (): Promise<never> => {
  throw new Error('not used');
};
const fakeAuth: AuthContextValue = {
  user: { id: 'u', email: 'asha@example.in', full_name: 'Asha Rao', last_login_at: null, created_at: NOW, two_factor_enabled: false },
  organization: null,
  membership: { id: 'm', role: 'owner', status: 'active', joined_at: NOW },
  organizations: [],
  isAuthenticated: true,
  isLoading: false,
  login: fail,
  completeMfaLogin: fail,
  logout: async () => undefined,
  switchOrganization: fail,
  refreshMe: async () => null,
  applyTokens: fail,
  hasRole: () => true,
};
// A selection API makes components emit data-ui-id, which lets us read the rendered order.
const selection: UiSelection = { selectedId: null, select: () => undefined };

function renderPage(pages?: PageConfigs) {
  const node: ReactNode = pages ? (
    <UiConfigOverride pages={pages} selection={selection}>
      <CustomerLifecycleListPage />
    </UiConfigOverride>
  ) : (
    <CustomerLifecycleListPage />
  );
  return render(
    <MemoryRouter initialEntries={['/customer-lifecycle']}>
      <ToastProvider>
        <AuthContext.Provider value={fakeAuth}>{node}</AuthContext.Provider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

const headers = () => screen.getAllByRole('columnheader').map((th) => th.textContent);
const ids = (container: HTMLElement, prefix: string) =>
  Array.from(container.querySelectorAll(`[data-ui-id^="${prefix}"]`)).map((el) => el.getAttribute('data-ui-id'));
const firstRowCells = () => within(screen.getAllByRole('row')[1]).getAllByRole('cell');

let originalAdapter: AxiosRequestConfig['adapter'];
beforeEach(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = previewAdapter;
});
afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
});

describe('CustomerLifecycleListPage visual-editor spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    const { container } = renderPage();
    expect(await screen.findByText('Nimbus Analytics')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Customer Lifecycle');
    expect(screen.getByText('Customer Experience')).toBeInTheDocument();
    for (const title of ['Total Customers', 'Active Accounts', 'Renewals Due', 'At-Risk Accounts', 'Expansion Deals']) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
    expect(headers()).toEqual([
      'Customer', 'Lifecycle Stage', 'Health Score', 'Total Revenue', 'Amount Due', 'Active Subs', 'Logged Hours', 'Next Action', 'Actions',
    ]);
    expect(firstRowCells()).toHaveLength(9);
    expect(container.querySelector('[data-ui-id]')).toBeNull();
  });

  it('relabels the header, a KPI card and a column', async () => {
    renderPage({
      customer_lifecycle: {
        header: { title: 'Account Health', eyebrow: 'Success' },
        kpis: [{ key: 'at_risk', label: 'Needs attention' }],
        columns: [{ key: 'hours', label: 'Billable Hours' }],
      },
    });
    await screen.findByText('Nimbus Analytics');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Account Health');
    expect(screen.getByText('Success')).toBeInTheDocument();
    expect(screen.getByText('Needs attention')).toBeInTheDocument();
    expect(screen.queryByText('At-Risk Accounts')).toBeNull();
    expect(headers()).toContain('Billable Hours');
    expect(headers()).not.toContain('Logged Hours');
  });

  it('hides a column (header and cells)', async () => {
    renderPage({ customer_lifecycle: { columns: [{ key: 'next_action', hidden: true }] } });
    await screen.findByText('Nimbus Analytics');
    expect(headers()).not.toContain('Next Action');
    expect(screen.queryByText('Kick-off call with finance team')).toBeNull();
    expect(firstRowCells()).toHaveLength(8);
  });

  it('reorders columns and body cells together, and KPI cards', async () => {
    const { container } = renderPage({
      customer_lifecycle: { columns: [{ key: 'stage' }, { key: 'customer' }], kpis: [{ key: 'expansion' }] },
    });
    await screen.findByText('Nimbus Analytics');
    expect(headers().slice(0, 3)).toEqual(['Lifecycle Stage', 'Customer', 'Health Score']);
    const cells = firstRowCells();
    expect(cells[0]).toHaveTextContent('Onboarding');
    expect(cells[1]).toHaveTextContent('Nimbus Analytics');
    expect(ids(container, 'customer_lifecycle.kpis.')[0]).toBe('customer_lifecycle.kpis.expansion');
  });
});
