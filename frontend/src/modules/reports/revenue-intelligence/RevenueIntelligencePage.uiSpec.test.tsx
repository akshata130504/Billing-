/**
 * Revenue Intelligence honours its visual-editor spec (appUi/specs/revenue_intelligence.json) and
 * renders exactly as before without configuration. Requests are answered by this page's preview
 * fixtures (platform/uiPreview/fixtures/revenue_intelligence.ts), then the preview adapter.
 */
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { AxiosAdapter, AxiosRequestConfig } from 'axios';
import { apiClient } from '../../../services/apiClient';
import { previewAdapter, resolvePreviewRequest } from '../../../platform/uiPreview/sampleData';
import { routes as fixtureRoutes } from '../../../platform/uiPreview/fixtures/revenue_intelligence';
import { AuthContext, type AuthContextValue } from '../../../hooks/useAuth';
import { ToastProvider } from '../../../components/common/Toast';
import { UiConfigOverride, type UiSelection } from '../../../appUi/UiConfigContext';
import type { PageConfigs } from '../../../appUi/registry';
import { RevenueIntelligencePage } from './RevenueIntelligencePage';

const NOW = '2026-01-01T00:00:00Z';
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
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const node: ReactNode = pages ? (
    <UiConfigOverride pages={pages} selection={selection}>
      <RevenueIntelligencePage />
    </UiConfigOverride>
  ) : (
    <RevenueIntelligencePage />
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/revenue-intelligence']}>
        <AuthContext.Provider value={fakeAuth}>
          <ToastProvider>{node}</ToastProvider>
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ids = (container: HTMLElement, prefix: string) =>
  Array.from(container.querySelectorAll(`[data-ui-id^="${prefix}"]`)).map((el) => el.getAttribute('data-ui-id'));

/** This page's fixtures first (the shared preview routes define simplified /reports shapes). */
const adapter: AxiosAdapter = async (config) => {
  const { path, query } = resolvePreviewRequest(config);
  const handler = fixtureRoutes[path];
  if (!handler || (config.method || 'get').toLowerCase() !== 'get') return previewAdapter(config);
  return { data: JSON.parse(JSON.stringify(handler(query))), status: 200, statusText: 'OK', headers: {}, config };
};

let originalAdapter: AxiosRequestConfig['adapter'];
beforeEach(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = adapter;
});
afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
});



const KPI_TITLES = ['MRR', 'ARR', 'Net Revenue', 'Collection Rate', 'Outstanding', 'Overdue', 'Avg Days to Payment', 'Total Invoiced'];
/** KPI card titles in rendered order (StatCard renders its title as an uppercase span). */
const kpiTitles = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('span.uppercase'))
    .map((el) => el.textContent ?? '')
    .filter((t) => KPI_TITLES.some((k) => t.startsWith(k)) || t === 'Net Sales');

describe('Revenue Intelligence page spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    const { container } = renderPage();
    expect(screen.getByRole('heading', { name: 'Revenue Intelligence' })).toBeInTheDocument();
    expect(await screen.findByText('Revenue Over Time')).toBeInTheDocument();
    expect(await screen.findByText('Lotus Textiles')).toBeInTheDocument();
    expect(kpiTitles(container)).toEqual([
      'MRR', 'ARR', 'Net Revenue', 'Collection Rate', 'Outstanding', 'Overdue', 'Avg Days to Payment', 'Total Invoiced',
    ]);
    for (const text of [
      'Invoiced vs Collected', 'Revenue by Plan', 'Revenue by Product', 'Receivables Aging', 'Top Customers',
      'Subscription Mix', 'Cash Summary', 'Recognised revenue per month for this year.',
      'Payments, refunds and customer coverage for this year.', 'Gross payments', 'Customers with billing activity',
    ]) {
      expect(await screen.findByText(text)).toBeInTheDocument();
    }
    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['#', 'Customer', 'Revenue', 'Share', 'Outstanding']);
    expect(document.querySelector('[data-ui-id]')).toBeNull();
  });

  it('relabels the header, a KPI card, a section and a column; tokens are filled', async () => {
    const { container } = renderPage({
      revenue_intelligence: {
        header: { title: 'Revenue Pulse' },
        kpis: [{ key: 'net_revenue', label: 'Net Sales' }],
        revenue_trend: { title: 'Revenue Trend', description: 'Per {unit}, {range}.' },
        customer_columns: [{ key: 'revenue', label: 'Billed' }],
      },
    });
    expect(screen.getByRole('heading', { name: 'Revenue Pulse' })).toBeInTheDocument();
    expect(await screen.findByText('Revenue Trend')).toBeInTheDocument();
    expect(await screen.findByText('Per month, this year.')).toBeInTheDocument();
    expect(kpiTitles(container)).toContain('Net Sales');
    expect(kpiTitles(container)).not.toContain('Net Revenue');
    await screen.findByText('Lotus Textiles');
    expect(within(screen.getByRole('table')).getByRole('columnheader', { name: 'Billed' })).toBeInTheDocument();
  });

  it('hides KPI cards and columns, but never the required Customer column', async () => {
    const { container } = renderPage({
      revenue_intelligence: {
        kpis: [{ key: 'overdue', hidden: true }],
        customer_columns: [{ key: 'customer', hidden: true }, { key: 'share', hidden: true }],
      },
    });
    await screen.findByText('Lotus Textiles');
    expect(ids(container, 'revenue_intelligence.kpis.')).not.toContain('revenue_intelligence.kpis.overdue');
    expect(kpiTitles(container)).not.toContain('Overdue');
    expect(within(screen.getByRole('table')).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['Customer', '#', 'Revenue', 'Outstanding']); // configured entries first
  });

  it('reorders KPI cards and columns (cells follow the headers)', async () => {
    const { container } = renderPage({
      revenue_intelligence: {
        kpis: [{ key: 'total_invoiced' }, { key: 'mrr' }],
        customer_columns: [{ key: 'revenue' }, { key: 'customer' }],
      },
    });
    await screen.findByText('Lotus Textiles');
    expect(ids(container, 'revenue_intelligence.kpis.').slice(0, 3)).toEqual([
      'revenue_intelligence.kpis.total_invoiced', 'revenue_intelligence.kpis.mrr', 'revenue_intelligence.kpis.arr',
    ]);
    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['Revenue', 'Customer', '#', 'Share', 'Outstanding']);
    const firstRow = within(table).getAllByRole('row')[1];
    const cells = Array.from(firstRow.querySelectorAll('td')).map((td) => td.textContent);
    expect(cells[1]).toContain('Lotus Textiles');
    expect(cells[2]).toBe('1');
  });
});
