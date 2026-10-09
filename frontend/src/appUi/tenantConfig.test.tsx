/**
 * The real tenant components honour the visual-editor configuration (and render exactly as before
 * without one). Pages are rendered against the preview sample-data adapter, so no network is used.
 */
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from '../services/apiClient';
import { previewAdapter } from '../platform/uiPreview/sampleData';
import { AuthContext, type AuthContextValue } from '../hooks/useAuth';
import { ToastProvider } from '../components/common/Toast';
import { Sidebar } from '../components/layout/Sidebar';
import { DashboardPage } from '../pages/dashboard/DashboardPage';
import { CustomersListPage } from '../pages/customers/CustomersListPage';
import { InvoicesListPage } from '../pages/invoices/InvoicesListPage';
import { UiConfigOverride, type UiSelection } from './UiConfigContext';
import type { PageConfigs } from './registry';

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

function renderWith(node: ReactNode, pages?: PageConfigs, path = '/dashboard') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const body = pages ? (
    <UiConfigOverride pages={pages} selection={selection}>
      {node}
    </UiConfigOverride>
  ) : (
    node
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AuthContext.Provider value={fakeAuth}>
          <ToastProvider>{body}</ToastProvider>
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
  sessionStorage.clear();
});
afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
});

describe('Sidebar navigation configuration', { timeout: 20000 }, () => {
  const navigation: PageConfigs = {
    navigation: {
      sections: [
        {
          key: 'workspace',
          label: 'MY WORK',
          items: [
            { key: 'customers', label: 'Clients', icon: 'Star' },
            { key: 'overview' },
            { key: 'catalog', hidden: true },
          ],
        },
        { key: 'platforms', hidden: true },
        { key: 'revenue' },
      ],
    },
  };

  it('renders the built-in navigation without configuration', () => {
    renderWith(<Sidebar isOpen onClose={() => undefined} />);
    expect(screen.getByRole('link', { name: 'Customers' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Catalog' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Mobile' })).toBeInTheDocument();
    expect(screen.getByText('WORKSPACE')).toBeInTheDocument();
    expect(screen.getByText('PLATFORMS')).toBeInTheDocument();
    expect(document.querySelector('[data-ui-id]')).toBeNull();
    const customers = screen.getByRole('link', { name: 'Customers' });
    expect(customers.querySelector('svg.lucide-users')).not.toBeNull();
  });

  it('applies labels, order, visibility and icons', () => {
    const { container } = renderWith(<Sidebar isOpen onClose={() => undefined} />, navigation);
    const clients = screen.getByRole('link', { name: 'Clients' });
    expect(clients).toHaveAttribute('href', '/customers');
    expect(clients.querySelector('svg.lucide-star')).not.toBeNull();
    expect(clients.querySelector('svg.lucide-users')).toBeNull();
    expect(screen.queryByRole('link', { name: 'Customers' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Catalog' })).not.toBeInTheDocument();
    // Section hidden with its items; section renamed.
    expect(screen.queryByText('PLATFORMS')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Mobile' })).not.toBeInTheDocument();
    expect(screen.getByText('MY WORK')).toBeInTheDocument();
    expect(screen.queryByText('WORKSPACE')).not.toBeInTheDocument();
    // Item order within the section.
    expect(ids(container, 'nav.item.').slice(0, 2)).toEqual(['nav.item.customers', 'nav.item.overview']);
    // Section order: configured first, then the rest in default order, hidden ones absent.
    expect(ids(container, 'nav.section.')).toEqual([
      'nav.section.workspace', 'nav.section.revenue', 'nav.section.subscriptions', 'nav.section.customer_experience',
      'nav.section.operations', 'nav.section.insights', 'nav.section.control_center', 'nav.section.system',
    ]);
    // Other sections untouched.
    expect(screen.getByRole('link', { name: 'Invoices' })).toBeInTheDocument();
  });

  it('cannot hide the required Settings item or the System section', () => {
    renderWith(<Sidebar isOpen onClose={() => undefined} />, {
      navigation: { sections: [{ key: 'system', hidden: true, items: [{ key: 'settings', hidden: true }, { key: 'automation', hidden: true }] }] },
    });
    expect(screen.getByText('SYSTEM')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Automation' })).not.toBeInTheDocument();
  });

  it('ignores icons outside the allow-list', () => {
    renderWith(<Sidebar isOpen onClose={() => undefined} />, {
      navigation: { sections: [{ key: 'workspace', items: [{ key: 'customers', icon: 'constructor' }] }] },
    });
    expect(screen.getByRole('link', { name: 'Customers' }).querySelector('svg.lucide-users')).not.toBeNull();
  });
});

describe('Overview (dashboard) configuration', { timeout: 20000 }, () => {
  it('renders the default header and KPI order without configuration', async () => {
    renderWith(<DashboardPage />);
    expect(await screen.findByRole('heading', { level: 1, name: 'Welcome back, Asha!' })).toBeInTheDocument();
    expect(screen.getByText('Churn Rate')).toBeInTheDocument();
  });

  it('applies header, KPI and widget configuration', async () => {
    const { container } = renderWith(<DashboardPage />, {
      overview: {
        header: { title: 'Financial overview for {first_name}', subtitle: 'Today at a glance.' },
        kpis: [{ key: 'total_revenue', label: 'Gross revenue' }, { key: 'churn_rate', hidden: true }],
        main_widgets: [
          { key: 'customer_health' },
          { key: 'recent_invoices', label: 'Latest invoices' },
          { key: 'revenue_overview' },
        ],
      },
    });
    expect(await screen.findByRole('heading', { level: 1, name: 'Financial overview for Asha' })).toBeInTheDocument();
    expect(screen.getByText('Today at a glance.')).toBeInTheDocument();
    expect(screen.queryByText('Welcome back, Asha!')).not.toBeInTheDocument();

    const kpis = ids(container, 'overview.kpi.');
    expect(kpis).toEqual([
      'overview.kpi.total_revenue', 'overview.kpi.total_invoices', 'overview.kpi.payments_received',
      'overview.kpi.outstanding', 'overview.kpi.mrr',
    ]);
    const first = container.querySelector('[data-ui-id="overview.kpi.total_revenue"]') as HTMLElement;
    expect(within(first).getByText('Gross revenue')).toBeInTheDocument();
    expect(screen.queryByText('Total Revenue')).not.toBeInTheDocument();
    expect(screen.queryByText('Churn Rate')).not.toBeInTheDocument();
    expect(screen.getByText('MRR (INR)')).toBeInTheDocument();

    const widgets = ids(container, 'overview.widget.');
    expect(widgets.slice(0, 5)).toEqual([
      'overview.widget.customer_health', 'overview.widget.recent_invoices', 'overview.widget.revenue_overview',
      'overview.widget.billing_pipeline', 'overview.widget.payment_recovery',
    ]);
    const recent = container.querySelector('[data-ui-id="overview.widget.recent_invoices"]') as HTMLElement;
    expect(within(recent).getByText('Latest invoices')).toBeInTheDocument();
    expect(screen.queryByText('Recent Invoices')).not.toBeInTheDocument();
  });
});

describe('Customers configuration', { timeout: 20000 }, () => {
  it('renders default columns without configuration', async () => {
    renderWith(<CustomersListPage />, undefined, '/customers');
    expect(await screen.findByText('Sunrise Foods')).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toEqual([
      'Customer #', 'Customer', 'Company / GSTIN', 'Status', 'Currency / Terms', 'Created',
    ]);
    expect(screen.getByRole('heading', { name: 'Customers' })).toBeInTheDocument();
  });

  it('applies header, stat and column configuration', async () => {
    const { container } = renderWith(<CustomersListPage />, {
      customers: {
        header: { title: 'Clients', eyebrow: 'Accounts' },
        stats: [{ key: 'total', label: 'All clients' }, { key: 'inactive', hidden: true }],
        columns: [
          { key: 'customer', label: 'Client' },
          { key: 'status' },
          { key: 'customer_number', label: 'Client ID' },
          { key: 'company', hidden: true },
        ],
      },
    }, '/customers');
    expect(await screen.findByText('Sunrise Foods')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Clients' })).toBeInTheDocument();
    expect(screen.getByText('Accounts')).toBeInTheDocument();
    expect(screen.getByText('All clients')).toBeInTheDocument();
    expect(screen.queryByText('Total customers')).not.toBeInTheDocument();
    expect(ids(container, 'customers.stat.')).toEqual(['customers.stat.total', 'customers.stat.active', 'customers.stat.matching']);
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toEqual([
      'Client', 'Status', 'Client ID', 'Currency / Terms', 'Created',
    ]);
    expect(screen.getByText('CUST-00001')).toBeInTheDocument();
  });
});

describe('Invoices configuration', { timeout: 20000 }, () => {
  it('renders default columns without configuration', async () => {
    renderWith(<InvoicesListPage />, undefined, '/invoices');
    expect(await screen.findByText('INV-1048')).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toEqual([
      'Invoice #', 'Customer', 'Date', 'Due Date', 'Total', 'Paid', 'Balance', 'Status', 'Actions',
    ]);
  });

  it('applies header, KPI and column configuration', async () => {
    renderWith(<InvoicesListPage />, {
      invoices: {
        header: { title: 'Bills', subtitle: 'Everything you have billed.' },
        kpis: [{ key: 'overdue', label: 'Late bills' }],
        columns: [
          { key: 'status' },
          { key: 'invoice_number', label: 'Bill #', hidden: true },
          { key: 'paid', hidden: true },
          { key: 'actions', hidden: true },
        ],
      },
    }, '/invoices');
    expect(await screen.findByText('INV-1048')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Bills' })).toBeInTheDocument();
    expect(screen.getByText('Everything you have billed.')).toBeInTheDocument();
    expect(screen.getByText('Late bills')).toBeInTheDocument();
    expect(screen.queryByText('Overdue', { selector: 'p' })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toEqual([
        'Status', 'Bill #', 'Customer', 'Date', 'Due Date', 'Total', 'Balance',
      ]),
    );
    expect(screen.queryByRole('button', { name: /View/ })).not.toBeInTheDocument();
  });
});

describe('Quick-action deep links (BUG-51)', { timeout: 20000 }, () => {
  it('/customers?action=new opens the new-customer form', async () => {
    renderWith(
      <Routes>
        <Route path="/customers" element={<CustomersListPage />} />
        <Route path="/customers/new" element={<div>customer-form</div>} />
      </Routes>,
      undefined,
      '/customers?action=new',
    );
    expect(await screen.findByText('customer-form')).toBeInTheDocument();
  });

  it('/invoices?action=new opens the new-invoice form', async () => {
    renderWith(
      <Routes>
        <Route path="/invoices" element={<InvoicesListPage />} />
        <Route path="/invoices/new" element={<div>invoice-form</div>} />
      </Routes>,
      undefined,
      '/invoices?action=new',
    );
    expect(await screen.findByText('invoice-form')).toBeInTheDocument();
  });
});
