import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from '../../services/apiClient';
import { customerService } from '../../services/customerService';
import { invoiceService } from '../../services/invoiceService';
import { AuthContext, type AuthContextValue } from '../../hooks/useAuth';
import { ToastProvider } from '../../components/common/Toast';
import type { MeResponse } from '../../types/api';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { CustomersListPage } from '../../pages/customers/CustomersListPage';
import { InvoicesListPage } from '../../pages/invoices/InvoicesListPage';
import { PREVIEW_GET_PATHS, PREVIEW_READ_ONLY_MESSAGE, previewAdapter, sampleCustomers } from './sampleData';

const me: MeResponse = {
  user: {
    id: 'user-1',
    email: 'asha@example.in',
    full_name: 'Asha Rao',
    last_login_at: null,
    created_at: '2026-01-01T00:00:00Z',
    two_factor_enabled: false,
  },
  organization: {
    id: 'org-1',
    name: 'Preview Workspace',
    slug: 'preview',
    legal_name: null,
    email: null,
    phone: null,
    website: null,
    address_line1: null,
    address_line2: null,
    city: null,
    state: null,
    postal_code: null,
    country: 'IN',
    gstin: null,
    pan: null,
    default_currency: 'INR',
    timezone: 'Asia/Kolkata',
    invoice_prefix: 'INV-',
    invoice_next_number: 1049,
    quote_prefix: 'QT-',
    quote_next_number: 1,
    payment_prefix: 'PAY-',
    payment_next_number: 1,
    subscription_prefix: 'SUB-',
    subscription_next_number: 1,
    customer_prefix: 'CUST-',
    customer_next_number: 9,
    default_payment_terms_days: 30,
    default_tax_rate_pct: '18.00',
    discount_approval_threshold_pct: '20.00',
    invoice_notes: null,
    invoice_terms: null,
    logo_url: null,
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  membership: { id: 'mem-1', role: 'owner', status: 'active', joined_at: '2026-01-01T00:00:00Z' },
  organizations: [],
};

const fakeAuth: AuthContextValue = {
  user: me.user,
  organization: me.organization,
  membership: me.membership,
  organizations: [],
  isAuthenticated: true,
  isLoading: false,
  login: async () => ({ status: 'signed_in', me }),
  completeMfaLogin: async () => me,
  logout: async () => undefined,
  switchOrganization: async () => me,
  refreshMe: async () => me,
  applyTokens: async () => me,
  hasRole: () => true,
};

function renderPage(page: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthContext.Provider value={fakeAuth}>
          <ToastProvider>{page}</ToastProvider>
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ERROR_TEXT = /could not load|couldn't load|something went wrong|failed to load|not available in preview/i;

let originalAdapter: AxiosRequestConfig['adapter'];
let fetchSpy: ReturnType<typeof vi.fn>;
let xhrOpen: ReturnType<typeof vi.spyOn>;
let xhrSend: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = previewAdapter;
  fetchSpy = vi.fn(() => Promise.reject(new Error('network must not be used in preview')));
  vi.stubGlobal('fetch', fetchSpy);
  xhrOpen = vi.spyOn(XMLHttpRequest.prototype, 'open');
  xhrSend = vi.spyOn(XMLHttpRequest.prototype, 'send');
});

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
  vi.unstubAllGlobals();
});

function expectNoNetwork() {
  expect(fetchSpy).not.toHaveBeenCalled();
  expect(xhrOpen).not.toHaveBeenCalled();
  expect(xhrSend).not.toHaveBeenCalled();
}

describe('previewAdapter safety', () => {
  it.each(['post', 'put', 'patch', 'delete'] as const)('refuses %s with 403 PREVIEW_READ_ONLY and sends nothing', async (method) => {
    const request =
      method === 'delete'
        ? apiClient.delete('/customers/abc')
        : apiClient[method]('/customers', { display_name: 'Should never be created' });
    await expect(request).rejects.toMatchObject({
      code: 'PREVIEW_READ_ONLY',
      message: PREVIEW_READ_ONLY_MESSAGE,
      status: 403,
    });
    expectNoNetwork();
  });

  it('refuses writes even on paths that are readable with GET', async () => {
    await expect(apiClient.post('/ui-config', {})).rejects.toMatchObject({ status: 403, code: 'PREVIEW_READ_ONLY' });
    await expect(apiClient.request({ method: 'HEAD', url: '/invoices' })).rejects.toMatchObject({ status: 403 });
    expectNoNetwork();
  });

  it('the adapter itself rejects with an AxiosError carrying the 403 envelope', async () => {
    const error = await previewAdapter({ method: 'post', url: '/invoices', headers: {} } as never).catch((e) => e);
    expect(error.isAxiosError).toBe(true);
    expect(error.response.status).toBe(403);
    expect(error.response.data).toEqual({
      error: { code: 'PREVIEW_READ_ONLY', message: PREVIEW_READ_ONLY_MESSAGE },
    });
  });

  it('answers unknown GET paths with 404 NOT_FOUND', async () => {
    await expect(apiClient.get('/unknown-preview-path')).rejects.toMatchObject({
      status: 404,
      code: 'NOT_FOUND',
      message: 'Not available in preview.',
    });
    expectNoNetwork();
  });

  it('answers every known GET path with a 200 response', async () => {
    for (const path of PREVIEW_GET_PATHS) {
      const res = await apiClient.get(path);
      expect(res.status).toBe(200);
      expect(res.data).toBeTruthy();
    }
    const ui = await apiClient.get('/ui-config');
    expect(ui.data).toEqual({ pages: {}, versions: {}, etag: 'preview' });
    expectNoNetwork();
  });
});

describe('previewAdapter filters', () => {
  it('honours customer status filters and page size', async () => {
    const all = await customerService.list({ page: 1, page_size: 1 });
    const active = await customerService.list({ page: 1, page_size: 1, status: 'active' });
    const inactive = await customerService.list({ page: 1, page_size: 1, status: 'inactive' });
    expect(all.total).toBe(sampleCustomers.length);
    expect(all.items).toHaveLength(1);
    expect(active.total + inactive.total).toBe(all.total);
    expect(inactive.total).toBeGreaterThan(0);
  });

  it('honours invoice status filters from the query string', async () => {
    const paid = await invoiceService.listInvoices({ status: 'paid' });
    expect(paid.items.length).toBeGreaterThan(0);
    expect(paid.items.every((i) => i.status === 'paid')).toBe(true);
    const recent = await invoiceService.listInvoices({ page_size: 5 });
    expect(recent.items).toHaveLength(5);
    expect(recent.kpis.total_invoices).toBeGreaterThan(5);
  });
});

describe('real pages render with sample data', () => {
  it('renders the dashboard', async () => {
    renderPage(<DashboardPage />);
    expect(await screen.findByText('Welcome back, Asha!')).toBeInTheDocument();
    expect((await screen.findAllByText('INV-1048')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('Acme Traders')).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.queryByText(/Loading action items/i)).not.toBeInTheDocument());
    expect(screen.queryByText(ERROR_TEXT)).not.toBeInTheDocument();
    expectNoNetwork();
  });

  it('renders the customers list', async () => {
    renderPage(<CustomersListPage />);
    expect(await screen.findByText('Sunrise Foods')).toBeInTheDocument();
    expect(screen.getByText('Acme Traders')).toBeInTheDocument();
    expect(screen.getByText('CUST-00001')).toBeInTheDocument();
    expect(screen.queryByText(ERROR_TEXT)).not.toBeInTheDocument();
    expectNoNetwork();
  });

  it('renders the invoices list', async () => {
    renderPage(<InvoicesListPage />);
    expect(await screen.findByText('INV-1048')).toBeInTheDocument();
    expect(screen.getAllByText('Sunrise Foods').length).toBeGreaterThan(0);
    expect(screen.queryByText(ERROR_TEXT)).not.toBeInTheDocument();
    expectNoNetwork();
  });
});
