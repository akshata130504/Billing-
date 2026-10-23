/**
 * Hosted Payment Pages honours its visual-editor spec (appUi/specs/hosted_payment_pages.json) and renders exactly
 * as before without configuration. Requests are answered by the preview sample-data adapter.
 */
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from '../../../services/apiClient';
import { previewAdapter } from '../../../platform/uiPreview/sampleData';
import { AuthContext, type AuthContextValue } from '../../../hooks/useAuth';
import { ToastProvider } from '../../../components/common/Toast';
import { UiConfigOverride, type UiSelection } from '../../../appUi/UiConfigContext';
import type { PageConfigs } from '../../../appUi/registry';
import { HostedPaymentPagesPage } from './HostedPaymentPagesPage';

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
      <HostedPaymentPagesPage />
    </UiConfigOverride>
  ) : (
    <HostedPaymentPagesPage />
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/hosted-payment-pages']}>
        <AuthContext.Provider value={fakeAuth}>
          <ToastProvider>{node}</ToastProvider>
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ids = (container: HTMLElement, prefix: string) =>
  Array.from(container.querySelectorAll(`[data-ui-id^="${prefix}"]`)).map((el) => el.getAttribute('data-ui-id'));

let originalAdapter: AxiosRequestConfig['adapter'];
beforeEach(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = previewAdapter;
});
afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
});



const headers = () => screen.getAllByRole('columnheader').map((th) => th.textContent);

describe('Hosted Payment Pages page spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'Hosted Payment Pages' })).toBeInTheDocument();
    expect(screen.getByText('Customer Experience')).toBeInTheDocument();
    // KPI titles render as spans (the status filter also has a "Successful" option).
    for (const label of ['Total sessions', 'Awaiting payment', 'Successful', 'Failed / expired']) {
      expect(screen.getByText(label, { selector: 'span' })).toBeInTheDocument();
    }
    // Sample sessions load, with customer names resolved from the sample customers.
    expect(await screen.findByText('Sunrise Foods')).toBeInTheDocument();
    expect(headers()).toEqual(['Reference', 'Customer', 'Amount', 'Status', 'Expires', 'Created', 'Actions']);
    expect(screen.getByRole('button', { name: /Sessions/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Templates/ })).toBeInTheDocument();
    expect(document.querySelector('[data-ui-id]')).toBeNull();
  });

  it('relabels the header, a KPI card, a tab and a column', async () => {
    renderPage({
      hosted_payment_pages: {
        header: { title: 'Payment Links', eyebrow: 'Checkout' },
        kpis: [{ key: 'total', label: 'Links created' }],
        tabs: [{ key: 'templates', label: 'Brand themes' }],
        columns: [{ key: 'ref', label: 'Link ref' }],
      },
    });
    expect(screen.getByRole('heading', { name: 'Payment Links' })).toBeInTheDocument();
    expect(screen.getByText('Checkout')).toBeInTheDocument();
    expect(screen.getByText('Links created')).toBeInTheDocument();
    expect(screen.queryByText('Total sessions')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Brand themes/ })).toBeInTheDocument();
    await screen.findByText('Sunrise Foods');
    expect(headers()[0]).toBe('Link ref');
  });

  it('hides KPI cards and columns, but never the required Reference column', async () => {
    renderPage({
      hosted_payment_pages: {
        kpis: [{ key: 'closed', hidden: true }],
        columns: [{ key: 'ref', hidden: true }, { key: 'customer', hidden: true }, { key: 'created', hidden: true }],
      },
    });
    expect(screen.queryByText('Failed / expired')).not.toBeInTheDocument();
    await screen.findAllByText('Invoice payment');
    expect(headers()).toEqual(['Reference', 'Amount', 'Status', 'Expires', 'Actions']);
    expect(screen.queryByText('Sunrise Foods')).not.toBeInTheDocument();
  });

  it('reorders KPI cards, tabs and columns (cells follow the headers)', async () => {
    const { container } = renderPage({
      hosted_payment_pages: {
        kpis: [{ key: 'successful' }],
        tabs: [{ key: 'templates' }],
        columns: [{ key: 'status' }, { key: 'ref' }],
      },
    });
    expect(ids(container, 'hosted_payment_pages.kpis.')).toEqual([
      'hosted_payment_pages.kpis.successful', 'hosted_payment_pages.kpis.total',
      'hosted_payment_pages.kpis.awaiting', 'hosted_payment_pages.kpis.closed',
    ]);
    expect(ids(container, 'hosted_payment_pages.tabs.')).toEqual(['hosted_payment_pages.tabs.templates', 'hosted_payment_pages.tabs.sessions']);
    await screen.findByText('Sunrise Foods');
    expect(headers()).toEqual(['Status', 'Reference', 'Customer', 'Amount', 'Expires', 'Created', 'Actions']);
    const firstRow = screen.getAllByRole('row')[1];
    const cells = Array.from(firstRow.querySelectorAll('td')).map((td) => td.textContent);
    expect(cells[0]).toBe('Pending');
    expect(cells[1]).toContain('Invoice payment');
    expect(cells[2]).toBe('Sunrise Foods');
  });
});
