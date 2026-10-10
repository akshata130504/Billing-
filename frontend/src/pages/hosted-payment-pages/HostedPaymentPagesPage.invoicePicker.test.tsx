/**
 * BUG-58: the "New checkout session" form offers only invoices the server will accept
 * (sent / partially paid / overdue with a balance) - never drafts, which it refuses with 409.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext, type AuthContextValue } from '../../hooks/useAuth';
import { ToastProvider } from '../../components/common/Toast';
import { HostedPaymentPagesPage } from './HostedPaymentPagesPage';

const empty = { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };

vi.mock('../../services/checkoutService', () => ({
  checkoutService: {
    listSessions: vi.fn(async () => empty),
    listTemplates: vi.fn(async () => []),
    publicUrl: (t: string) => `/checkout/${t}`,
  },
}));
vi.mock('../../services/customerService', () => ({
  customerService: { list: vi.fn(async () => empty) },
}));
vi.mock('../../services/catalogService', () => ({
  catalogService: { listPlans: vi.fn(async () => empty) },
}));
vi.mock('../../services/subscriptionService', () => ({
  subscriptionService: { list: vi.fn(async () => empty) },
}));

const inv = (id: string, status: string, amount_due: string) => ({
  id,
  invoice_number: id,
  status,
  amount_due,
  currency: 'INR',
  customer: { id: 'c1', display_name: 'Acme' },
});

vi.mock('../../services/invoiceService', () => ({
  invoiceService: {
    list: vi.fn(async () => ({
      items: [
        inv('INV-DRAFT', 'draft', '100.00'),
        inv('INV-SENT', 'sent', '100.00'),
        inv('INV-PART', 'partially_paid', '50.00'),
        inv('INV-LATE', 'OVERDUE', '75.00'),
        inv('INV-PAID', 'paid', '0.00'),
        inv('INV-VOID', 'void', '100.00'),
        inv('INV-ZERO', 'sent', '0.00'),
      ],
      total: 7,
    })),
  },
}));

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

describe('<HostedPaymentPagesPage /> new checkout session', () => {
  it('lists only payable invoices in the invoice picker', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/hosted-payment-pages']}>
          <AuthContext.Provider value={fakeAuth}>
            <ToastProvider>
              <HostedPaymentPagesPage />
            </ToastProvider>
          </AuthContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole('button', { name: /New checkout session/ }));
    const dialog = await screen.findByRole('dialog');
    const picker = await waitFor(() => {
      const el = within(dialog).getByLabelText(/Invoice/) as HTMLSelectElement;
      expect(el.disabled).toBe(false);
      return el;
    });
    const labels = Array.from(picker.options).map((o) => o.textContent ?? '');
    const listed = ['INV-DRAFT', 'INV-SENT', 'INV-PART', 'INV-LATE', 'INV-PAID', 'INV-VOID', 'INV-ZERO'].filter((n) =>
      labels.some((l) => l.startsWith(`${n} `)),
    );
    expect(listed).toEqual(['INV-SENT', 'INV-PART', 'INV-LATE']);
  });
});
