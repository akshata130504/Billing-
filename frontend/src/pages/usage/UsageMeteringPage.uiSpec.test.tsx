/**
 * The Usage / Metering page honours its visual-editor spec (appUi/specs/usage.json) and renders exactly its
 * built-in UI without configuration. Rendered against the preview sample-data adapter
 * (its GET /meters, /meters/events and /meters/usage-summary come from platform/uiPreview/fixtures/usage.ts).
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
import { UsageMeteringPage } from './UsageMeteringPage';

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
      <UsageMeteringPage />
    </UiConfigOverride>
  ) : (
    <UsageMeteringPage />
  );
  return render(
    <MemoryRouter initialEntries={['/usage']}>
      <ToastProvider>
        <AuthContext.Provider value={fakeAuth}>{node}</AuthContext.Provider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

// The meters table is the first table; the usage history table follows it.
const metersTable = () => screen.getAllByRole('table')[0];
const headers = () => within(metersTable()).getAllByRole('columnheader').map((th) => th.textContent);
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

describe('UsageMeteringPage visual-editor spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    const { container } = renderPage();
    expect((await screen.findAllByText('API Requests'))[0]).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Usage / Metering');
    expect(screen.getByText('Subscriptions')).toBeInTheDocument();
    for (const title of ['Meters', 'Active Meters', 'Events Recorded', 'Aggregation Types']) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
    expect(headers()).toEqual(['Meter', 'Code', 'Unit', 'Aggregation', 'Recorded Usage', 'Status', 'Created', 'Actions']);
    expect(firstRowCells()).toHaveLength(8);
    expect(screen.getByText('Recorded usage events')).toBeInTheDocument();
    expect(await screen.findAllByText('Nimbus Analytics')).toHaveLength(2);
    expect(screen.getByText('Finalised cycles')).toBeInTheDocument();
    expect(screen.getByText('Nothing finalised yet')).toBeInTheDocument();
    expect(container.querySelector('[data-ui-id]')).toBeNull();
  });

  it('relabels the header, a stat card, a column and a panel', async () => {
    renderPage({
      usage: {
        header: { title: 'Metered Billing', eyebrow: 'Billing' },
        kpis: [{ key: 'meters', label: 'All meters' }],
        columns: [{ key: 'unit', label: 'Unit of measure' }],
        events: { title: 'Usage history' },
        cycles: { title: 'Rated cycles' },
      },
    });
    await screen.findAllByText('API Requests');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Metered Billing');
    expect(screen.getByText('Billing')).toBeInTheDocument();
    expect(screen.getByText('All meters')).toBeInTheDocument();
    expect(headers()).toContain('Unit of measure');
    expect(headers()).not.toContain('Unit');
    expect(screen.getByText('Usage history')).toBeInTheDocument();
    expect(screen.getByText('Rated cycles')).toBeInTheDocument();
  });

  it('hides a column (header and cells)', async () => {
    renderPage({ usage: { columns: [{ key: 'code', hidden: true }] } });
    await screen.findAllByText('API Requests');
    expect(headers()).not.toContain('Code');
    expect(within(metersTable()).queryByText('api_calls')).toBeNull();
    expect(firstRowCells()).toHaveLength(7);
  });

  it('reorders columns and body cells together, and stat cards', async () => {
    const { container } = renderPage({
      usage: { columns: [{ key: 'status' }, { key: 'meter' }], kpis: [{ key: 'events' }] },
    });
    await screen.findAllByText('API Requests');
    expect(headers().slice(0, 3)).toEqual(['Status', 'Meter', 'Code']);
    const cells = firstRowCells();
    expect(cells[0]).toHaveTextContent('Active');
    expect(cells[1]).toHaveTextContent('API Requests');
    expect(cells[2]).toHaveTextContent('api_calls');
    expect(ids(container, 'usage.kpis.')).toEqual(['usage.kpis.events', 'usage.kpis.meters', 'usage.kpis.active', 'usage.kpis.aggregations']);
  });

  it('shows stored usage history and per-meter totals after a reload (BUG-44)', async () => {
    renderPage();
    await screen.findAllByText('API Requests');
    // Events posted in an earlier session come back from GET /meters/events ...
    expect(await screen.findByText('Kestrel Logistics')).toBeInTheDocument();
    expect(screen.queryByText('No usage recorded yet')).toBeNull();
    expect(screen.queryByText(/does not list historical events/)).toBeNull();
    // ... and the meters table shows each meter's recorded total from GET /meters/usage-summary.
    const apiRow = within(metersTable()).getByText('API Requests').closest('tr')!;
    expect(apiRow).toHaveTextContent('1,730 requests');
    expect(apiRow).toHaveTextContent('2 events');
  });
});
