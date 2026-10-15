import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PaymentReceipt, PaymentReceiptPage } from '../../services/platformSubscriptionService';

const listReceipts = vi.fn();
vi.mock('../../services/platformSubscriptionService', () => ({
  platformSubscriptionService: {
    listReceipts: (page: number) => listReceipts(page),
    receiptPdfUrl: (id: string) => `/api/v1/plan-subscription/receipts/${id}/pdf`,
  },
}));
const downloadAuthenticated = vi.fn();
vi.mock('../../services/download', () => ({
  downloadAuthenticated: (url: string, name: string) => downloadAuthenticated(url, name),
}));

import { ReceiptsSection } from './ReceiptsSection';

function receipt(overrides: Partial<PaymentReceipt> = {}): PaymentReceipt {
  return {
    id: 'r-1', receipt_number: 'RCPT-202610-AB12CD34', document_type: 'payment_receipt',
    note: 'This is a payment receipt, not a tax invoice.', status: 'paid', kind: 'initial', cycle_number: 1,
    amount_minor: 79900, currency: 'INR', method: 'upi', paid_at: '2026-10-13T10:00:00Z', issued_at: '2026-10-13T10:00:05Z',
    period_start: '2026-10-13T10:00:00Z', period_end: '2026-11-13T10:00:00Z', plan_code: 'starter', plan_name: 'Starter',
    billing_interval: 'month', billing_interval_count: 1, sandbox: false, mode: 'live', provider_payment_id: 'pay_1',
    provider_invoice_id: 'inv_1',
    billed_to: { name: 'Acme', legal_name: 'Acme Private Limited', email: null, address_line1: null, address_line2: null,
      city: null, state: null, postal_code: null, country: 'IN', gstin: null },
    ...overrides,
  };
}

function page(items: PaymentReceipt[], total = items.length): PaymentReceiptPage {
  return { items, total, page: 1, page_size: 25, total_pages: total ? Math.ceil(total / 25) : 0 };
}

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReceiptsSection />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listReceipts.mockReset().mockResolvedValue(page([]));
  downloadAuthenticated.mockReset().mockResolvedValue(undefined);
});

describe('ReceiptsSection', () => {
  it('shows a loading state', () => {
    listReceipts.mockReturnValue(new Promise(() => undefined));
    renderSection();
    expect(screen.getByText('Loading receipts...')).toBeInTheDocument();
  });

  it('shows an empty state and says receipts are not tax invoices', async () => {
    renderSection();
    expect(await screen.findByText(/No payment receipts yet/)).toBeInTheDocument();
    expect(screen.getByText(/payment receipts, not tax invoices/)).toBeInTheDocument();
  });

  it('shows an error with a retry', async () => {
    listReceipts.mockRejectedValueOnce({ code: 'FORBIDDEN', message: 'You do not have permission.', status: 403 });
    renderSection();
    expect(await screen.findByText('You do not have permission.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /try again|retry/i }));
    await waitFor(() => expect(listReceipts).toHaveBeenCalledTimes(2));
  });

  it('lists receipts with amount, period and kind', async () => {
    listReceipts.mockResolvedValue(page([
      receipt({ id: 'r-2', receipt_number: 'RCPT-202611-EF56GH78', kind: 'renewal', cycle_number: 2 }),
      receipt(),
      receipt({ id: 'r-3', receipt_number: 'RCPT-202610-TEST0001', sandbox: true, mode: 'test', amount_minor: 100,
        plan_name: 'Sandbox Test Plan (Foundation)' }),
    ]));
    renderSection();
    const rows = await screen.findAllByTestId('receipt-row');
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText('Starter plan - renewal (cycle 2)')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Starter plan - purchase')).toBeInTheDocument();
    expect(within(rows[1]).getByText('₹799.00')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Paid')).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent('Period 13 Oct 2026');
    expect(within(rows[2]).getByText('Test mode')).toBeInTheDocument();
    expect(within(rows[2]).getByText('₹1.00')).toBeInTheDocument();
  });

  it('downloads the receipt PDF', async () => {
    listReceipts.mockResolvedValue(page([receipt()]));
    renderSection();
    await userEvent.click(await screen.findByRole('button', { name: 'Download receipt RCPT-202610-AB12CD34' }));
    expect(downloadAuthenticated).toHaveBeenCalledWith('/api/v1/plan-subscription/receipts/r-1/pdf', 'RCPT-202610-AB12CD34.pdf');
  });

  it('reports a failed download', async () => {
    listReceipts.mockResolvedValue(page([receipt()]));
    downloadAuthenticated.mockRejectedValue({ code: 'HTTP_404', message: 'Receipt not found.', status: 404 });
    renderSection();
    await userEvent.click(await screen.findByRole('button', { name: /Download receipt/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Receipt not found.');
  });

  it('pages through many receipts', async () => {
    listReceipts.mockResolvedValue(page(Array.from({ length: 25 }, (_, i) => receipt({ id: `r-${i}` })), 30));
    renderSection();
    await screen.findAllByTestId('receipt-row');
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(listReceipts).toHaveBeenLastCalledWith(2));
  });
});
