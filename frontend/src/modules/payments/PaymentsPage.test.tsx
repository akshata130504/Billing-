import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { PaymentsPage } from './PaymentsPage';

vi.mock('./PaymentsContext', async (orig) => ({
  ...(await orig<typeof import('./PaymentsContext')>()),
  usePayments: () => ({
    payments: [],
    customers: [],
    isLoading: false,
    error: null,
    filters: {},
    setFilters: vi.fn(),
    page: 1,
    setPage: vi.fn(),
    total: 0,
    totalPages: 1,
    refreshPayments: vi.fn(),
  }),
}));
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ hasRole: () => true }) }));
vi.mock('./components/PaymentSummaryCards', () => ({ PaymentSummaryCards: () => null }));
vi.mock('./components/PaymentFilters', () => ({ PaymentFilters: () => null }));
vi.mock('./components/PaymentTable', () => ({ PaymentTable: () => null }));
vi.mock('./components/RefundModal', () => ({ RefundModal: () => null }));
vi.mock('./components/ReceiptModal', () => ({ ReceiptModal: () => null }));
vi.mock('./components/RecordPaymentModal', () => ({
  RecordPaymentModal: ({ isOpen }: { isOpen: boolean }) => (isOpen ? <div>record-payment-open</div> : null),
}));

function Search() {
  return <div data-testid="search">{useLocation().search}</div>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <PaymentsPage />
      <Search />
    </MemoryRouter>
  );
}

describe('<PaymentsPage /> quick-action deep link (BUG-51)', () => {
  it('opens the record-payment form for /payments?new=1 and drops the parameter', async () => {
    renderAt('/payments?new=1');
    expect(await screen.findByText('record-payment-open')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe(''));
  });

  it('keeps the form closed on a plain visit', () => {
    renderAt('/payments');
    expect(screen.queryByText('record-payment-open')).toBeNull();
  });
});
