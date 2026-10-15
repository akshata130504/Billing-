import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ReconciliationPage } from './ReconciliationPage';
import { paymentService } from '../../services/paymentService';
import { invoiceService } from '../../services/invoiceService';
import type { PaymentOut } from '../../types/api';

const showToast = vi.fn();

vi.mock('../../services/paymentService', () => ({
  paymentService: {
    reconciliationSummary: vi.fn(),
    list: vi.fn(),
    setAllocations: vi.fn(),
    addAllocation: vi.fn(),
  },
}));
vi.mock('../../services/invoiceService', () => ({ invoiceService: { listInvoices: vi.fn() } }));
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ hasRole: () => true }) }));
vi.mock('../../components/common/Toast', () => ({ useToast: () => ({ showToast }) }));

// The L-5 scenario: 120 received, 100 already settles INV-A, 20 left to allocate.
const payment = {
  id: 'pay-1',
  payment_number: 'PAY-000021',
  customer: { id: 'c-1', display_name: 'Rupee Customer' },
  amount: '120.00',
  currency: 'INR',
  method: 'bank_transfer',
  gateway: 'manual',
  status: 'succeeded',
  reconciliation_status: 'exception',
  reference: 'NEFT-1',
  amount_refunded: '0.00',
  amount_allocated: '100.00',
  amount_unallocated: '20.00',
  allocations: [{ id: 'al-1', invoice_id: 'inv-a', invoice_number: 'INV-A', amount: '100.00' }],
  refunds: [],
  created_at: '2026-10-15T00:00:00Z',
  updated_at: '2026-10-15T00:00:00Z',
} as unknown as PaymentOut;

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ReconciliationPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function openAllocation() {
  renderPage();
  fireEvent.click(await screen.findByRole('button', { name: 'Inspect' }));
  const dialog = await screen.findByRole('dialog');
  const select = await within(dialog).findByLabelText('Invoice');
  await waitFor(() => expect(within(select as HTMLSelectElement).getAllByRole('option').length).toBeGreaterThan(1));
  return { dialog, select: select as HTMLSelectElement };
}

describe('<ReconciliationPage /> manual allocation (L-5)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(paymentService.reconciliationSummary).mockResolvedValue({ matched: 0, auto_matched: 0, unmatched: 0, exception: 1 } as never);
    vi.mocked(paymentService.list).mockResolvedValue({ items: [payment], total: 1, page: 1, page_size: 25, total_pages: 1 } as never);
    vi.mocked(invoiceService.listInvoices).mockResolvedValue({
      items: [
        { id: 'inv-b', invoice_number: 'INV-B', amount_due: '50.00', currency: 'INR' },
        { id: 'inv-aed', invoice_number: 'INV-AED', amount_due: '433.36', currency: 'AED' },
      ],
      total: 2,
    } as never);
  });

  it('adds an allocation for the unallocated amount and never replaces the existing ones', async () => {
    let resolve: (v: PaymentOut) => void = () => {};
    vi.mocked(paymentService.addAllocation).mockReturnValue(new Promise((r) => { resolve = r; }));
    const { dialog, select } = await openAllocation();

    fireEvent.change(select, { target: { value: 'inv-b' } });
    expect((within(dialog).getByLabelText('Amount to allocate') as HTMLInputElement).value).toBe('20.00');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save Allocation' }));

    await waitFor(() => expect(paymentService.addAllocation).toHaveBeenCalledWith('pay-1', { invoice_id: 'inv-b', amount: '20.00' }));
    expect(paymentService.setAllocations).not.toHaveBeenCalled();
    // No success message until the server has confirmed.
    expect(showToast).not.toHaveBeenCalledWith('success', expect.anything(), expect.anything());

    resolve({ ...payment, amount_allocated: '120.00', amount_unallocated: '0.00', reconciliation_status: 'matched' } as PaymentOut);
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('success', 'Payment allocated', expect.any(String)));
  });

  it('shows the server error and no success when the add is refused', async () => {
    vi.mocked(paymentService.addAllocation).mockRejectedValue(new Error('Allocation is invalid.'));
    const { dialog, select } = await openAllocation();

    fireEvent.change(select, { target: { value: 'inv-b' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save Allocation' }));

    await waitFor(() => expect(showToast).toHaveBeenCalledWith('error', 'Could not allocate payment', expect.any(String)));
    expect(showToast).not.toHaveBeenCalledWith('success', expect.anything(), expect.anything());
  });

  it('blocks an amount above the unallocated amount', async () => {
    const { dialog, select } = await openAllocation();

    fireEvent.change(select, { target: { value: 'inv-b' } });
    fireEvent.change(within(dialog).getByLabelText('Amount to allocate'), { target: { value: '20.01' } });

    expect(within(dialog).getByRole('button', { name: 'Save Allocation' })).toBeDisabled();
    expect(within(dialog).getByText(/More than the ₹20\.00 still unallocated/)).toBeInTheDocument();
    expect(paymentService.addAllocation).not.toHaveBeenCalled();
  });

  it('labels each invoice option in its own currency', async () => {
    const { select } = await openAllocation();
    const labels = within(select).getAllByRole('option').map((o) => o.textContent ?? '');

    expect(labels.find((l) => l.startsWith('INV-B'))).toContain('₹50.00');
    const aed = labels.find((l) => l.startsWith('INV-AED')) ?? '';
    expect(aed).toMatch(/AED\s?433\.36/);
    expect(aed).not.toContain('₹');
  });
});
