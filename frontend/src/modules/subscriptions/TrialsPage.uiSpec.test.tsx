/**
 * The Trials page honours its visual-editor spec (appUi/specs/trials.json) and renders exactly its
 * built-in UI without configuration. Rendered against the preview sample-data adapter, with this
 * page's fixtures (platform/uiPreview/fixtures/trials.ts) answering first.
 */
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { AxiosAdapter, AxiosRequestConfig } from 'axios';
import { apiClient } from '../../services/apiClient';
import { previewAdapter, resolvePreviewRequest } from '../../platform/uiPreview/sampleData';
import { routes as trialRoutes } from '../../platform/uiPreview/fixtures/trials';
import { ToastProvider } from '../../components/common/Toast';
import { AuthContext, type AuthContextValue } from '../../hooks/useAuth';
import { UiConfigOverride, type UiSelection } from '../../appUi/UiConfigContext';
import type { PageConfigs } from '../../appUi/registry';
import { TrialsPage } from './TrialsPage';

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

function renderPage(pages?: PageConfigs) {
  const node: ReactNode = pages ? (
    <UiConfigOverride pages={pages} selection={selection}>
      <TrialsPage />
    </UiConfigOverride>
  ) : (
    <TrialsPage />
  );
  return render(
    <MemoryRouter initialEntries={['/trials']}>
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

describe('TrialsPage visual-editor spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    const { container } = renderPage();
    expect(await screen.findByText('SUB-2101')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Trial Center & Pipeline');
    expect(screen.getByText('Back to Subscriptions')).toBeInTheDocument();
    expect(screen.getByText('Monitor active trial periods, track expiration timelines, and convert prospects into recurring revenue.')).toBeInTheDocument();
    expect(screen.getByText('Active Trials')).toBeInTheDocument();
    expect(screen.getByText('Potential customer pipeline')).toBeInTheDocument();
    expect(screen.getByText('Expiring Within 7 Days')).toBeInTheDocument();
    expect(await screen.findByText('2 currently paid & active')).toBeInTheDocument();
    expect(screen.getByText('Active Trial Accounts')).toBeInTheDocument();
    expect(headers()).toEqual(['Trial / Subscription', 'Customer', 'Plan & Terms', 'Trial Window', 'Timeline', 'Potential MRR', 'Actions']);
    expect(firstRowCells()).toHaveLength(7);
    // Outside the editor the DOM carries no selection hooks.
    expect(container.querySelector('[data-ui-id]')).toBeNull();
  });

  it('relabels the header, a KPI card (label and caption) and a column', async () => {
    renderPage({
      trials: {
        header: { title: 'Trial Pipeline', back_link: 'All subscriptions' },
        kpis: [
          { key: 'active', label: 'Trials running', caption: 'Prospects evaluating' },
          { key: 'total_base', caption: '{active} paying today' },
        ],
        columns: [{ key: 'customer', label: 'Account' }],
        section: { title: 'Open trials' },
      },
    });
    await screen.findByText('SUB-2101');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Trial Pipeline');
    expect(screen.getByText('All subscriptions')).toBeInTheDocument();
    expect(screen.getByText('Trials running')).toBeInTheDocument();
    expect(screen.queryByText('Active Trials')).toBeNull();
    expect(screen.getByText('Prospects evaluating')).toBeInTheDocument();
    expect(await screen.findByText('2 paying today')).toBeInTheDocument();
    expect(screen.getByText('Open trials')).toBeInTheDocument();
    expect(headers()).toContain('Account');
    expect(headers()).not.toContain('Customer');
  });

  it('hides a column (header and cells)', async () => {
    renderPage({ trials: { columns: [{ key: 'customer', hidden: true }] } });
    await screen.findByText('SUB-2101');
    expect(headers()).not.toContain('Customer');
    expect(screen.queryByText('Nimbus Analytics')).toBeNull();
    expect(firstRowCells()).toHaveLength(6);
  });

  it('reorders columns and body cells together, and KPI cards', async () => {
    const { container } = renderPage({
      trials: {
        columns: [{ key: 'timeline' }, { key: 'customer' }],
        kpis: [{ key: 'total_base' }],
      },
    });
    await screen.findByText('SUB-2101');
    expect(headers().slice(0, 3)).toEqual(['Timeline', 'Customer', 'Trial / Subscription']);
    expect(ids(container, 'trials.columns.')).toEqual([
      'trials.columns.timeline', 'trials.columns.customer', 'trials.columns.subscription', 'trials.columns.plan',
      'trials.columns.window', 'trials.columns.mrr', 'trials.columns.actions',
    ]);
    const cells = firstRowCells();
    expect(cells[0]).toHaveTextContent('days left');
    expect(cells[1]).toHaveTextContent('Nimbus Analytics');
    expect(cells[2]).toHaveTextContent('SUB-2101');
    expect(ids(container, 'trials.kpis.')).toEqual(['trials.kpis.total_base', 'trials.kpis.active', 'trials.kpis.expiring']);
  });
});
