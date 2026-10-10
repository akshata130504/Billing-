import {
  createContext,
  useContext,
  useState,
  useEffect,
  useMemo,
  useCallback,
  ReactNode,
} from 'react';
import {
  Payment,
  PaymentCustomer,
  PaymentsSummary,
  PaymentFilterState,
  InvoiceAllocation,
  PaymentType,
  PaymentMethod,
} from './types';
import { paymentService, type BackendPaymentStatus, type PaymentQueryParams } from '../../services/paymentService';
import { customerService } from '../../services/customerService';
import { invoiceService } from '../../services/invoiceService';
import { toApiError } from '../../services/apiClient';
import { useToast } from '../../components/common/Toast';
import { paymentOutToUi, uiToPaymentIn, customerToUi, toBackendPaymentMethod } from './paymentMapper';
import type { ApiError, InvoiceOut } from '../../types/api';

export const PAYMENTS_PAGE_SIZE = 25;

/** Invoice statuses a payment can still be applied to. */
const OPEN_INVOICE_STATUSES = ['sent', 'partially_paid', 'overdue'] as const;

export interface RecordPaymentInput {
  paymentType: PaymentType;
  customerId: string;
  customerName: string;
  amount: number;
  paymentDate: string;
  paymentMethod: PaymentMethod;
  referenceNumber: string;
  notes?: string;
  allocations: InvoiceAllocation[];
}

export interface RefundPaymentInput {
  paymentId: string;
  amount: number;
  reason: string;
  refundMode: string;
  referenceNumber?: string;
  notes?: string;
}

const EMPTY_SUMMARY: PaymentsSummary = {
  totalCollected: 0,
  pendingProcessing: 0,
  totalRefunded: 0,
  unappliedCredit: 0,
};

export interface PaymentsContextType {
  /** The current page of payments, exactly as the server returned them. */
  payments: Payment[];
  /** Customers available for the record-payment form (first page, refined by search). */
  customers: PaymentCustomer[];
  /** Money totals for every payment matching the active filters, computed server-side. */
  summary: PaymentsSummary;
  isLoading: boolean;
  /** Set when the payment list could not be loaded. The UI must not show figures in this state. */
  error: ApiError | null;
  filters: PaymentFilterState;
  setFilters: (next: PaymentFilterState) => void;
  page: number;
  setPage: (page: number) => void;
  total: number;
  totalPages: number;
  recordPayment: (input: RecordPaymentInput) => Promise<Payment>;
  refundPayment: (input: RefundPaymentInput) => Promise<void>;
  updatePayment: (id: string, updates: { referenceNumber?: string; notes?: string }) => Promise<void>;
  getPaymentById: (id: string) => Payment | undefined;
  fetchPaymentById: (id: string) => Promise<Payment | undefined>;
  searchCustomers: (query: string) => Promise<PaymentCustomer[]>;
  getCustomerById: (id: string) => PaymentCustomer | undefined;
  loadCustomerInvoices: (customerId: string) => Promise<PaymentCustomer | undefined>;
  createCustomer: (data: {
    displayName: string;
    companyName?: string;
    email?: string;
    phone?: string;
  }) => Promise<PaymentCustomer>;
  refreshPayments: () => Promise<void>;
}

const PaymentsContext = createContext<PaymentsContextType | undefined>(undefined);

export const INITIAL_PAYMENT_FILTERS: PaymentFilterState = {
  searchQuery: '',
  statusTab: 'all',
  customer: 'all',
  paymentMethod: 'all',
  status: 'all',
  sortBy: 'newest',
};

/** Translate the UI filter state into the query parameters the API understands. */
export function toListParams(filters: PaymentFilterState, page: number): PaymentQueryParams {
  const sortMap: Record<PaymentFilterState['sortBy'], string> = {
    newest: '-created_at',
    oldest: 'created_at',
    amount_high: '-amount',
    amount_low: 'amount',
  };

  // The status tab and the status dropdown both narrow status; the dropdown wins
  // when it names a single status, otherwise the tab decides.
  let status: BackendPaymentStatus | undefined;
  if (filters.status !== 'all') {
    status = (filters.status === 'completed' ? 'succeeded' : filters.status) as BackendPaymentStatus;
  } else if (filters.statusTab === 'completed') {
    status = 'succeeded';
  } else if (filters.statusTab === 'pending') {
    status = 'pending';
  } else if (filters.statusTab === 'failed') {
    status = 'failed';
  } else if (filters.statusTab === 'refunded') {
    // Fully and partially refunded payments both belong on the Refunded tab.
    status = 'refunded,partially_refunded';
  }

  return {
    page,
    page_size: PAYMENTS_PAGE_SIZE,
    search: filters.searchQuery.trim() || undefined,
    status,
    method: filters.paymentMethod !== 'all' ? toBackendPaymentMethod(filters.paymentMethod as PaymentMethod) : undefined,
    customer_id: filters.customer !== 'all' ? filters.customer : undefined,
    sort: sortMap[filters.sortBy],
  };
}

export function PaymentsProvider({ children }: { children: ReactNode }) {
  const { showToast } = useToast();

  // Financial records are never seeded from fixtures and never cached in the
  // browser: an empty list means the organization genuinely has no payments,
  // and a failed load surfaces `error` rather than stale or invented figures.
  const [payments, setPayments] = useState<Payment[]>([]);
  const [customers, setCustomers] = useState<PaymentCustomer[]>([]);
  const [summary, setSummary] = useState<PaymentsSummary>(EMPTY_SUMMARY);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [filters, setFiltersState] = useState<PaymentFilterState>(INITIAL_PAYMENT_FILTERS);
  const [page, setPage] = useState(1);

  const listParams = useMemo(() => toListParams(filters, page), [filters, page]);
  // Totals ignore pagination but honour every other filter.
  const summaryParams = useMemo(() => {
    const { page: _page, page_size: _size, sort: _sort, ...rest } = listParams;
    return rest;
  }, [listParams]);

  const setFilters = useCallback((next: PaymentFilterState) => {
    setFiltersState(next);
    setPage(1); // a changed filter invalidates the current page number
  }, []);

  const loadPayments = useCallback(async () => {
    setIsLoading(true);
    try {
      const listed = await paymentService.list(listParams);
      setPayments(listed.items.map(paymentOutToUi));
      setTotal(listed.total);
      setTotalPages(listed.total_pages);
      setError(null);
    } catch (err) {
      const apiErr = toApiError(err);
      setPayments([]);
      setTotal(0);
      setTotalPages(0);
      setSummary(EMPTY_SUMMARY);
      setError(apiErr);
      return;
    } finally {
      setIsLoading(false);
    }

    // Totals are a separate query; a failure there must not blank the list.
    try {
      const totals = await paymentService.summary(summaryParams);
      setSummary({
        totalCollected: Number(totals.total_collected),
        pendingProcessing: Number(totals.pending_amount),
        totalRefunded: Number(totals.total_refunded),
        unappliedCredit: Number(totals.unallocated_amount),
      });
    } catch {
      setSummary(EMPTY_SUMMARY);
    }
  }, [listParams, summaryParams]);

  useEffect(() => {
    void loadPayments();
  }, [loadPayments]);

  // Customers for the record-payment picker. Only the first page is preloaded;
  // searchCustomers() queries the server for anything beyond it.
  useEffect(() => {
    let cancelled = false;
    customerService
      .list({ page_size: 50, status: 'active' })
      .then((res) => {
        if (!cancelled) setCustomers(res.items.map((c) => customerToUi(c)));
      })
      .catch(() => {
        if (!cancelled) setCustomers([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const searchCustomers = useCallback(async (query: string): Promise<PaymentCustomer[]> => {
    try {
      const res = await customerService.list({
        search: query.trim() || undefined,
        status: 'active',
        page_size: 20,
      });
      const mapped = res.items.map((c) => customerToUi(c));
      setCustomers((prev) => {
        const merged = [...mapped];
        for (const existing of prev) {
          if (!merged.some((c) => c.id === existing.id)) merged.push(existing);
        }
        return merged;
      });
      return mapped;
    } catch {
      return [];
    }
  }, []);

  /** Fetch the customer's open invoices so the allocation editor has real balances. */
  const loadCustomerInvoices = useCallback(
    async (customerId: string): Promise<PaymentCustomer | undefined> => {
      try {
        // Queried per status: /customers/{id}/invoices has no status filter, so
        // a customer with many settled invoices could otherwise page the open
        // ones out of reach.
        const [detail, pages] = await Promise.all([
          customerService.get(customerId),
          Promise.all(
            OPEN_INVOICE_STATUSES.map((status) =>
              invoiceService.listInvoices({
                customer_id: customerId,
                status,
                page_size: 100,
                sort: 'due_date',
              })
            )
          ),
        ]);
        const openInvoices = pages.flatMap((p) => p.items);
        // `invoiceService.listInvoices` types its rows against `types/invoices.ts`'s `Invoice`,
        // while `customerToUi` expects `types/api.ts`'s `InvoiceOut` — two pre-existing, not yet
        // unified invoice type definitions for the same backend response shape.
        const mapped = customerToUi(detail, openInvoices as unknown as InvoiceOut[]);
        setCustomers((prev) => {
          const next = prev.filter((c) => c.id !== mapped.id);
          return [mapped, ...next];
        });
        return mapped;
      } catch (err) {
        showToast('error', 'Could not load invoices', toApiError(err).message);
        return undefined;
      }
    },
    [showToast]
  );

  const recordPayment = useCallback(
    async (input: RecordPaymentInput): Promise<Payment> => {
      try {
        const createdOut = await paymentService.create(uiToPaymentIn(input));
        const createdUi = paymentOutToUi(createdOut);
        showToast(
          'success',
          'Payment recorded',
          `${createdUi.id} for ${createdUi.customerName} was saved.`
        );
        if (createdOut.warnings?.length) showToast('warning', 'Possible duplicate', createdOut.warnings.join(' '));
        // Re-read from the server so totals, allocations and invoice states are authoritative.
        await loadPayments();
        return createdUi;
      } catch (err) {
        const apiErr = toApiError(err);
        showToast('error', 'Payment failed', apiErr.message);
        throw err;
      }
    },
    [loadPayments, showToast]
  );

  const refundPayment = useCallback(
    async (input: RefundPaymentInput): Promise<void> => {
      const target = payments.find((p) => p.id === input.paymentId || p.backendId === input.paymentId);
      const backendId = target?.backendId ?? input.paymentId;
      try {
        const updatedOut = await paymentService.refund(backendId, {
          amount: input.amount.toFixed(2),
          reason: input.reason,
        });
        showToast(
          'success',
          'Refund processed',
          `Refund recorded against ${updatedOut.payment_number}.`
        );
        await loadPayments();
      } catch (err) {
        const apiErr = toApiError(err);
        showToast('error', 'Refund failed', apiErr.message);
        throw err;
      }
    },
    [payments, loadPayments, showToast]
  );

  const updatePayment = useCallback(
    async (id: string, updates: { referenceNumber?: string; notes?: string }): Promise<void> => {
      const target = payments.find((p) => p.id === id || p.backendId === id);
      const backendId = target?.backendId ?? id;
      try {
        const updated = await paymentService.update(backendId, {
          reference: updates.referenceNumber,
          notes: updates.notes,
        });
        const mapped = paymentOutToUi(updated);
        setPayments((prev) => prev.map((p) => (p.backendId === mapped.backendId ? mapped : p)));
        showToast('success', 'Payment updated', 'Reference and notes were saved.');
        if (updated.warnings?.length) showToast('warning', 'Possible duplicate', updated.warnings.join(' '));
      } catch (err) {
        // The server rejected the change, so the UI must not pretend it stuck.
        const apiErr = toApiError(err);
        showToast('error', 'Update failed', apiErr.message);
        throw err;
      }
    },
    [payments, showToast]
  );

  const getPaymentById = useCallback(
    (id: string) => payments.find((p) => p.id === id || p.backendId === id || p.receiptNumber === id),
    [payments]
  );

  const fetchPaymentById = useCallback(
    async (id: string): Promise<Payment | undefined> => {
      const local = payments.find((p) => p.id === id || p.backendId === id);
      if (local) return local;
      try {
        return paymentOutToUi(await paymentService.get(id));
      } catch {
        return undefined;
      }
    },
    [payments]
  );

  const getCustomerById = useCallback(
    (id: string) => customers.find((c) => c.id === id),
    [customers]
  );

  const createCustomer = useCallback(
    async (data: {
      displayName: string;
      companyName?: string;
      email?: string;
      phone?: string;
    }): Promise<PaymentCustomer> => {
      try {
        const created = await customerService.create({
          display_name: data.displayName,
          company_name: data.companyName || undefined,
          email: data.email || undefined,
          phone: data.phone || undefined,
          currency: 'INR',
        });
        const uiCust = customerToUi(created);
        setCustomers((prev) => [uiCust, ...prev.filter((c) => c.id !== uiCust.id)]);
        showToast('success', 'Customer created', `"${uiCust.name}" was registered.`);
        return uiCust;
      } catch (err) {
        const apiErr = toApiError(err);
        showToast('error', 'Creation failed', apiErr.message);
        throw err;
      }
    },
    [showToast]
  );

  const value = useMemo(
    () => ({
      payments,
      customers,
      summary,
      isLoading,
      error,
      filters,
      setFilters,
      page,
      setPage,
      total,
      totalPages,
      recordPayment,
      refundPayment,
      updatePayment,
      getPaymentById,
      fetchPaymentById,
      searchCustomers,
      getCustomerById,
      loadCustomerInvoices,
      createCustomer,
      refreshPayments: loadPayments,
    }),
    [
      payments,
      customers,
      summary,
      isLoading,
      error,
      filters,
      setFilters,
      page,
      total,
      totalPages,
      recordPayment,
      refundPayment,
      updatePayment,
      getPaymentById,
      fetchPaymentById,
      searchCustomers,
      getCustomerById,
      loadCustomerInvoices,
      createCustomer,
      loadPayments,
    ]
  );

  return <PaymentsContext.Provider value={value}>{children}</PaymentsContext.Provider>;
}

export function usePayments() {
  const context = useContext(PaymentsContext);
  if (!context) {
    throw new Error('usePayments must be used within a PaymentsProvider');
  }
  return context;
}
