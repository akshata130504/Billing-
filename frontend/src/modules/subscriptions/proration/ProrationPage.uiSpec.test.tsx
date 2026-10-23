/**
 * The Proration page honours its visual-editor spec (appUi/specs/proration.json) and renders exactly its
 * built-in UI without configuration. Rendered against the preview sample-data adapter, with the
 * subscription fixtures (platform/uiPreview/fixtures/trials.ts, shared with Trials) answering first.
 */
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { AxiosAdapter, AxiosRequestConfig } from 'axios';
import { apiClient } from '../../../services/apiClient';
import { previewAdapter, resolvePreviewRequest } from '../../../platform/uiPreview/sampleData';
import { routes as trialRoutes } from '../../../platform/uiPreview/fixtures/trials';
import { ToastProvider } from '../../../components/common/Toast';
import { AuthContext, type AuthContextValue } from '../../../hooks/useAuth';
import { UiConfigOverride, type UiSelection } from '../../../appUi/UiConfigContext';
import type { PageConfigs } from '../../../appUi/registry';
import { ProrationPage } from './ProrationPage';

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

/** This page's fixtures first (the shared sample data also answers /subscriptions), then the preview adapter. */
const adapter: AxiosAdapter = async (config) => {
  const { path, query } = resolvePreviewRequest(config);
  const handler = (config.method || 'get').toLowerCase() === 'get' ? trialRoutes[path] : undefined;
  if (!handler) return previewAdapter(config);
  return { data: JSON.parse(JSON.stringify(handler(query))), status: 200, statusText: 'OK', headers: {}, config };
};

function renderPage(pages?: PageConfigs, entry = '/proration') {
  const node: ReactNode = pages ? (
    <UiConfigOverride pages={pages} selection={selection}>
      <ProrationPage />
    </UiConfigOverride>
  ) : (
    <ProrationPage />
  );
  return render(
    <MemoryRouter initialEntries={[entry]}>
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
  apiClient.defaults.adapter = adapter;
});
afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
});

describe('ProrationPage visual-editor spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    const { container } = renderPage();
    expect(await screen.findByText('SUB-2001')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Proration');
    expect(screen.getByText('Subscriptions')).toBeInTheDocument();
    for (const title of ['Eligible subscriptions', 'Scheduled changes', 'Applied changes', 'Net prorated billing']) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
    expect(screen.getByText('How proration is calculated')).toBeInTheDocument();
    expect(screen.getByText('Choose a subscription')).toBeInTheDocument();
    expect(headers()).toEqual(['Subscription', 'Customer', 'Plan', 'Qty', 'Current period', 'Recurring', 'Status', 'Action']);
    expect(firstRowCells()).toHaveLength(8);
    expect(container.querySelector('[data-ui-id]')).toBeNull();
  });

  it('relabels the header, a stat card, a column and the picker', async () => {
    renderPage({
      proration: {
        header: { title: 'Mid-cycle changes' },
        kpis: [{ key: 'eligible', label: 'Changeable subscriptions' }],
        columns: [{ key: 'quantity', label: 'Seats' }],
        picker: { title: 'Pick a subscription' },
        explainer: { title: 'The maths' },
      },
    });
    await screen.findByText('SUB-2001');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Mid-cycle changes');
    expect(screen.getByText('Changeable subscriptions')).toBeInTheDocument();
    expect(screen.queryByText('Eligible subscriptions')).toBeNull();
    expect(headers()).toContain('Seats');
    expect(headers()).not.toContain('Qty');
    expect(screen.getByText('Pick a subscription')).toBeInTheDocument();
    expect(screen.getByText('The maths')).toBeInTheDocument();
  });

  it('hides a column (header and cells)', async () => {
    renderPage({ proration: { columns: [{ key: 'customer', hidden: true }] } });
    await screen.findByText('SUB-2001');
    expect(headers()).not.toContain('Customer');
    expect(screen.queryByText('Harbor Freight Co')).toBeNull();
    expect(firstRowCells()).toHaveLength(7);
  });

  it('reorders columns and body cells together, and stat cards', async () => {
    const { container } = renderPage({
      proration: { columns: [{ key: 'customer' }, { key: 'status' }], kpis: [{ key: 'net_billing' }] },
    });
    await screen.findByText('SUB-2001');
    expect(headers().slice(0, 3)).toEqual(['Customer', 'Status', 'Subscription']);
    const cells = firstRowCells();
    expect(cells[0]).toHaveTextContent('Harbor Freight Co');
    expect(cells[1]).toHaveTextContent('Active');
    expect(cells[2]).toHaveTextContent('SUB-2001');
    expect(ids(container, 'proration.kpis.')[0]).toBe('proration.kpis.net_billing');
  });

  it('relabels and reorders the current-terms fields of a deep-linked subscription', async () => {
    const { container } = renderPage(
      { proration: { terms_fields: [{ key: 'rate', label: 'Cycle amount' }], terms: { description: 'Baseline terms' } } },
      '/proration?subscription=sub-preview-2001',
    );
    expect(await screen.findByText('Baseline terms')).toBeInTheDocument();
    expect(screen.getByText('Cycle amount')).toBeInTheDocument();
    expect(ids(container, 'proration.terms_fields.')).toEqual([
      'proration.terms_fields.rate', 'proration.terms_fields.plan', 'proration.terms_fields.unit_price',
      'proration.terms_fields.quantity', 'proration.terms_fields.period',
    ]);
  });
});
