import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import {
  INITIAL_PAYMENT_FILTERS,
  PAYMENTS_PAGE_SIZE,
  PaymentsProvider,
  toListParams,
  usePayments,
} from './PaymentsContext';
import type { PaymentFilterState } from './types';
import { paymentService } from '../../services/paymentService';
import { customerService } from '../../services/customerService';

vi.mock('../../services/paymentService', () => ({
  paymentService: {
    list: vi.fn(),
    summary: vi.fn(),
    create: vi.fn(),
  },
}));
vi.mock('../../services/customerService', () => ({
  customerService: { list: vi.fn().mockResolvedValue({ items: [], total: 0 }), get: vi.fn(), create: vi.fn() },
}));
vi.mock('../../services/invoiceService', () => ({ invoiceService: { listInvoices: vi.fn() } }));
const toast = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock('../../components/common/Toast', () => ({ useToast: () => toast }));

const f = (over: Partial<PaymentFilterState>): PaymentFilterState => ({ ...INITIAL_PAYMENT_FILTERS, ...over });

describe('toListParams status handling', () => {
  it('sends no status for the All tab', () => {
    expect(toListParams(f({}), 1).status).toBeUndefined();
  });
  it.each([
    ['completed', 'succeeded'],
    ['pending', 'pending'],
    ['failed', 'failed'],
    ['refunded', 'refunded,partially_refunded'],
  ] as const)('maps the %s tab to %s', (tab, expected) => {
    expect(toListParams(f({ statusTab: tab }), 1).status).toBe(expected);
  });
  it('lets the dropdown override the tab', () => {
    expect(toListParams(f({ statusTab: 'refunded', status: 'failed' }), 1).status).toBe('failed');
    expect(toListParams(f({ statusTab: 'all', status: 'refunded' }), 1).status).toBe('refunded');
    expect(toListParams(f({ statusTab: 'all', status: 'partially_refunded' }), 1).status).toBe('partially_refunded');
    expect(toListParams(f({ statusTab: 'pending', status: 'completed' }), 1).status).toBe('succeeded');
  });
  it('keeps paging and sort params', () => {
    expect(toListParams(f({ statusTab: 'refunded', sortBy: 'oldest' }), 2)).toMatchObject({
      page: 2,
      page_size: PAYMENTS_PAGE_SIZE,
      sort: 'created_at',
    });
  });
});

describe('PaymentsProvider refunded tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(customerService.list).mockResolvedValue({ items: [], total: 0 } as any);
    vi.mocked(paymentService.list).mockResolvedValue({ items: [], total: 0, total_pages: 0 } as any);
    vi.mocked(paymentService.summary).mockResolvedValue({
      total_collected: '0',
      pending_amount: '0',
      total_refunded: '0',
      unallocated_amount: '0',
    } as any);
  });

  it('sends the same refunded status to list and summary, and the dropdown takes precedence', async () => {
    let ctx!: ReturnType<typeof usePayments>;
    const Probe = () => {
      ctx = usePayments();
      return null;
    };
    render(
      <PaymentsProvider>
        <Probe />
      </PaymentsProvider>
    );
    await waitFor(() => expect(paymentService.summary).toHaveBeenCalledTimes(1));
    expect(vi.mocked(paymentService.list).mock.calls[0][0]).not.toHaveProperty('status', expect.anything());

    await act(async () => {
      ctx.setFilters(f({ statusTab: 'refunded' }));
    });
    await waitFor(() => expect(paymentService.summary).toHaveBeenCalledTimes(2));
    const listArg = vi.mocked(paymentService.list).mock.calls[1][0]!;
    const summaryArg = vi.mocked(paymentService.summary).mock.calls[1][0]!;
    expect(listArg.status).toBe('refunded,partially_refunded');
    expect(summaryArg.status).toBe('refunded,partially_refunded');
    expect(summaryArg).not.toHaveProperty('page');

    await act(async () => {
      ctx.setFilters(f({ statusTab: 'refunded', status: 'partially_refunded' }));
    });
    await waitFor(() => expect(paymentService.summary).toHaveBeenCalledTimes(3));
    expect(vi.mocked(paymentService.list).mock.calls[2][0]!.status).toBe('partially_refunded');
    expect(vi.mocked(paymentService.summary).mock.calls[2][0]!.status).toBe('partially_refunded');
  });
});

describe('PaymentsProvider duplicate warnings (BUG-18)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(customerService.list).mockResolvedValue({ items: [], total: 0 } as any);
    vi.mocked(paymentService.list).mockResolvedValue({ items: [], total: 0, total_pages: 0 } as any);
    vi.mocked(paymentService.summary).mockResolvedValue({
      total_collected: '0', pending_amount: '0', total_refunded: '0', unallocated_amount: '0',
    } as any);
  });

  it('saves the payment and shows the server warning as a non-blocking toast', async () => {
    const warning = 'Reference UTR-1 is also used on PAY-000001. Check this is not a duplicate payment.';
    vi.mocked(paymentService.create).mockResolvedValue({
      id: 'p2', payment_number: 'PAY-000002', customer: { id: 'c1', display_name: 'Acme' }, amount: '10.00',
      currency: 'INR', method: 'bank_transfer', status: 'succeeded', reconciliation_status: 'unmatched',
      reference: 'UTR-1', paid_at: '2026-10-10T00:00:00Z', amount_refunded: '0.00', amount_allocated: '0.00',
      amount_unallocated: '10.00', allocations: [], refunds: [], created_at: '2026-10-10T00:00:00Z',
      updated_at: '2026-10-10T00:00:00Z', warnings: [warning],
    } as any);
    let ctx!: ReturnType<typeof usePayments>;
    const Probe = () => {
      ctx = usePayments();
      return null;
    };
    render(
      <PaymentsProvider>
        <Probe />
      </PaymentsProvider>
    );
    await waitFor(() => expect(paymentService.summary).toHaveBeenCalled());
    await act(async () => {
      await ctx.recordPayment({
        paymentType: 'customer_advance', customerId: 'c1', customerName: 'Acme', amount: 10,
        paymentDate: '2026-10-10', paymentMethod: 'Bank Transfer' as any, referenceNumber: 'UTR-1', allocations: [],
      });
    });
    expect(toast.showToast).toHaveBeenCalledWith('success', 'Payment recorded', expect.any(String));
    expect(toast.showToast).toHaveBeenCalledWith('warning', 'Possible duplicate', warning);
  });
});
