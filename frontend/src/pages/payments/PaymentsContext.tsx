import { createContext, useContext, useState, useEffect, useMemo, useCallback, ReactNode } from 'react';
import {
  Payment,
  PaymentCustomer,
  PaymentsSummary,
  InvoiceAllocation,
  PaymentType,
  PaymentMethod,
} from './types';
import { initialPayments, mockCustomersWithInvoices } from './mockPayments';
import { paymentService } from '../../services/paymentService';
import { customerService } from '../../services/customerService';
import { invoiceService } from '../../services/invoiceService';
import { toApiError } from '../../services/apiClient';
import { useToast } from '../../components/common/Toast';
import { paymentOutToUi, uiToPaymentIn, customerToUi } from './paymentMapper';
import type { ReconciliationSummary } from '../../types/api';

const STORAGE_PAYMENTS_KEY = 'rooman_payments_list_v1';
const STORAGE_CUSTOMERS_KEY = 'rooman_payments_customers_v1';

export interface RecordPaymentInput {
  paymentType: PaymentType;
  customerId: string;
  customerName: string;
  amount: number;
  paymentDate: string;
  paymentMethod: PaymentMethod;
  referenceNumber: string;
  notes?: string;
  bankAccount?: string;
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

export interface PaymentsContextType {
  payments: Payment[];
  customers: PaymentCustomer[];
  summary: PaymentsSummary;
  isLoading: boolean;
  reconciliationSummary: ReconciliationSummary | null;
  recordPayment: (input: RecordPaymentInput) => Promise<Payment>;
  refundPayment: (input: RefundPaymentInput) => Promise<void>;
  updatePayment: (id: string, updates: Partial<Payment>) => Promise<void>;
  deletePayment: (id: string) => void;
  getPaymentById: (id: string) => Payment | undefined;
  fetchPaymentById: (id: string) => Promise<Payment | undefined>;
  getCustomerById: (id: string) => PaymentCustomer | undefined;
  getCustomerPayments: (customerId: string) => Promise<Payment[]>;
  createCustomer: (data: { displayName: string; companyName?: string; email?: string; phone?: string }) => Promise<PaymentCustomer>;
  refreshPayments: () => Promise<void>;
}

const PaymentsContext = createContext<PaymentsContextType | undefined>(undefined);

export function PaymentsProvider({ children }: { children: ReactNode }) {
  const { showToast } = useToast();

  const [payments, setPayments] = useState<Payment[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_PAYMENTS_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch (e) {
      console.error('Failed to load payments from localStorage:', e);
    }
    return initialPayments;
  });

  const [customers, setCustomers] = useState<PaymentCustomer[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_CUSTOMERS_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch (e) {
      console.error('Failed to load payment customers from localStorage:', e);
    }
    return mockCustomersWithInvoices;
  });

  const [reconciliation, setReconciliation] = useState<ReconciliationSummary | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Sync state with localStorage for offline resilience
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_PAYMENTS_KEY, JSON.stringify(payments));
    } catch (e) {
      console.error('Failed to save payments to localStorage:', e);
    }
  }, [payments]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_CUSTOMERS_KEY, JSON.stringify(customers));
    } catch (e) {
      console.error('Failed to save customers to localStorage:', e);
    }
  }, [customers]);

  // Load live data from the backend API
  const refreshPayments = useCallback(async () => {
    setIsLoading(true);
    try {
      const [paymentsRes, reconRes, customersRes, invoicesRes] = await Promise.allSettled([
        paymentService.list({ page_size: 100 }),
        paymentService.reconciliationSummary(),
        customerService.list({ page_size: 100 }),
        invoiceService.list({ page_size: 100 }),
      ]);

      if (paymentsRes.status === 'fulfilled') {
        const livePayments = paymentsRes.value.items.map(paymentOutToUi);
        setPayments(livePayments);
      }

      if (reconRes.status === 'fulfilled') {
        setReconciliation(reconRes.value);
      }

      if (customersRes.status === 'fulfilled') {
        const liveCusts = customersRes.value.items;
        const liveInvoices = invoicesRes.status === 'fulfilled' ? invoicesRes.value.items : [];
        const mappedCusts = liveCusts.map((c) => customerToUi(c, liveInvoices));
        setCustomers(mappedCusts);
      }
    } catch (err) {
      console.warn('API hydration encountered an issue, keeping existing cache:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshPayments();
  }, [refreshPayments]);

  // Compute 4 dynamic summary metrics
  const summary: PaymentsSummary = useMemo(() => {
    let totalCollected = 0;
    let pendingProcessing = 0;
    let totalRefunded = 0;
    let unappliedCredit = 0;

    for (const p of payments) {
      totalRefunded += p.refundedAmount || 0;

      if (p.status === 'completed' || p.status === 'partially_refunded') {
        totalCollected += p.amount - (p.refundedAmount || 0);
        unappliedCredit += p.unappliedAmount || 0;
      } else if (p.status === 'pending' || p.status === 'processing') {
        pendingProcessing += p.amount;
      }
    }

    // Override unapplied credit with backend reconciliation summary if available
    if (reconciliation && reconciliation.unallocated_amount) {
      const backendUnapplied = parseFloat(reconciliation.unallocated_amount);
      if (!isNaN(backendUnapplied) && backendUnapplied > 0) {
        unappliedCredit = backendUnapplied;
      }
    }

    return {
      totalCollected,
      pendingProcessing,
      totalRefunded,
      unappliedCredit,
    };
  }, [payments, reconciliation]);

  // Record a new payment with live API integration and offline fallback
  const recordPayment = useCallback(
    async (input: RecordPaymentInput): Promise<Payment> => {
      try {
        const payload = uiToPaymentIn(input);
        const createdOut = await paymentService.create(payload);
        const createdUi = paymentOutToUi(createdOut);

        setPayments((prev) => [createdUi, ...prev]);

        showToast(
          'success',
          'Payment Recorded',
          `Payment #${createdUi.id} of ₹${input.amount.toLocaleString('en-IN')} has been recorded successfully.`
        );

        paymentService.reconciliationSummary().then(setReconciliation).catch(() => {});
        return createdUi;
      } catch (err) {
        const apiErr = toApiError(err);
        console.error('Backend payment create failed:', apiErr.message);
        showToast('error', 'Payment Failed', apiErr.message || 'Failed to record payment on the server.');
        throw err;
      }
    },
    [showToast]
  );

  // Issue a refund (full or partial) with live API integration and RBAC awareness
  const refundPayment = useCallback(
    async (input: RefundPaymentInput): Promise<void> => {
      const target = payments.find((p) => p.id === input.paymentId || p.backendId === input.paymentId);
      const backendId = target?.backendId || input.paymentId;

      try {
        const updatedOut = await paymentService.refund(backendId, {
          amount: input.amount.toFixed(2),
          reason: input.reason,
        });
        const updatedUi = paymentOutToUi(updatedOut);

        setPayments((prev) =>
          prev.map((p) => (p.id === input.paymentId || p.backendId === backendId ? updatedUi : p))
        );

        showToast(
          'success',
          'Refund Processed',
          `Refund of ₹${input.amount.toLocaleString('en-IN')} processed successfully for ${updatedUi.id}.`
        );
      } catch (err) {
        const apiErr = toApiError(err);
        console.error('Backend refund failed:', apiErr.message);
        showToast('error', 'Refund Failed', apiErr.message || 'Failed to process refund on the server.');
        throw err;
      }
    },
    [payments, showToast]
  );

  const updatePayment = useCallback(
    async (id: string, updates: Partial<Payment>): Promise<void> => {
      const target = payments.find((p) => p.id === id || p.backendId === id);
      const backendId = target?.backendId || id;

      try {
        await paymentService.update(backendId, {
          reference: updates.referenceNumber,
          notes: updates.notes,
        });
      } catch (err) {
        console.warn('Backend update failed:', err);
      }

      setPayments((prev) =>
        prev.map((p) =>
          p.id === id || p.backendId === backendId
            ? { ...p, ...updates, updatedAt: new Date().toISOString() }
            : p
        )
      );
      showToast('success', 'Payment Updated', 'Payment record changes saved.');
    },
    [payments, showToast]
  );

  const deletePayment = useCallback(
    (id: string) => {
      setPayments((prev) => prev.filter((p) => p.id !== id && p.backendId !== id));
      showToast('info', 'Payment Deleted', `Payment record ${id} was removed.`);
    },
    [showToast]
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
        const res = await paymentService.get(id);
        const mapped = paymentOutToUi(res);
        setPayments((prev) => {
          if (prev.some((p) => p.id === mapped.id || p.backendId === mapped.backendId)) return prev;
          return [mapped, ...prev];
        });
        return mapped;
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

  const getCustomerPayments = useCallback(
    async (customerId: string): Promise<Payment[]> => {
      try {
        const res = await customerService.payments(customerId);
        return res.items.map(paymentOutToUi);
      } catch {
        return payments.filter((p) => p.customerId === customerId);
      }
    },
    [payments]
  );

  const createCustomer = useCallback(
    async (data: { displayName: string; companyName?: string; email?: string; phone?: string }): Promise<PaymentCustomer> => {
      try {
        const created = await customerService.create({
          display_name: data.displayName,
          company_name: data.companyName || undefined,
          email: data.email || undefined,
          phone: data.phone || undefined,
          currency: 'INR',
        });
        const uiCust = customerToUi(created, []);
        setCustomers((prev) => [uiCust, ...prev.filter((c) => c.id !== uiCust.id)]);
        showToast('success', 'Customer Created', `Customer "${uiCust.name}" has been registered.`);
        return uiCust;
      } catch (err) {
        const apiErr = toApiError(err);
        showToast('error', 'Creation Failed', apiErr.message || 'Failed to create customer on the server.');
        throw err;
      }
    },
    [showToast]
  );

  return (
    <PaymentsContext.Provider
      value={{
        payments,
        customers,
        summary,
        isLoading,
        reconciliationSummary: reconciliation,
        recordPayment,
        refundPayment,
        updatePayment,
        deletePayment,
        getPaymentById,
        fetchPaymentById,
        getCustomerById,
        getCustomerPayments,
        createCustomer,
        refreshPayments,
      }}
    >
      {children}
    </PaymentsContext.Provider>
  );
}

export function usePayments() {
  const context = useContext(PaymentsContext);
  if (!context) {
    throw new Error('usePayments must be used within a PaymentsProvider');
  }
  return context;
}
