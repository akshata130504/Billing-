import { createContext, useContext, useState, useEffect, useMemo, useCallback, ReactNode } from 'react';
import {
  Payment,
  PaymentCustomer,
  PaymentsSummary,
  InvoiceAllocation,
  PaymentRefund,
  PaymentType,
  PaymentMethod,
} from './types';
import { initialPayments, mockCustomersWithInvoices } from './mockPayments';
import { useToast } from '../../components/common/Toast';

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

interface PaymentsContextType {
  payments: Payment[];
  customers: PaymentCustomer[];
  summary: PaymentsSummary;
  recordPayment: (input: RecordPaymentInput) => Payment;
  refundPayment: (input: RefundPaymentInput) => void;
  updatePayment: (id: string, updates: Partial<Payment>) => void;
  deletePayment: (id: string) => void;
  getPaymentById: (id: string) => Payment | undefined;
  getCustomerById: (id: string) => PaymentCustomer | undefined;
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

  // Sync with localStorage
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

  // Compute 4 dynamic summary metrics
  const summary: PaymentsSummary = useMemo(() => {
    let totalCollected = 0;
    let pendingProcessing = 0;
    let totalRefunded = 0;
    let unappliedCredit = 0;

    for (const p of payments) {
      totalRefunded += p.refundedAmount || 0;

      if (p.status === 'completed' || p.status === 'partially_refunded') {
        totalCollected += (p.amount - (p.refundedAmount || 0));
        unappliedCredit += p.unappliedAmount || 0;
      } else if (p.status === 'pending' || p.status === 'processing') {
        pendingProcessing += p.amount;
      }
    }

    return {
      totalCollected,
      pendingProcessing,
      totalRefunded,
      unappliedCredit,
    };
  }, [payments]);

  // Record a new payment
  const recordPayment = useCallback(
    (input: RecordPaymentInput): Payment => {
      const numId = String(payments.length + 1).padStart(3, '0');
      const id = `PAY-2026-${numId}`;
      const receiptNumber = `RCT-2026-${numId}`;

      let appliedAmount = 0;
      if (input.paymentType === 'invoice_payment') {
        appliedAmount = input.allocations.reduce((sum, item) => sum + item.appliedAmount, 0);
      }

      const unappliedAmount = Math.max(0, input.amount - appliedAmount);

      const allocationStatus =
        appliedAmount === 0
          ? 'unapplied'
          : unappliedAmount === 0
          ? 'fully_applied'
          : 'partially_applied';

      const matchedCustomer = customers.find((c) => c.id === input.customerId);

      const newPayment: Payment = {
        id,
        receiptNumber,
        paymentType: input.paymentType,
        customerId: input.customerId,
        customerName: input.customerName,
        customerEmail: matchedCustomer?.email,
        amount: input.amount,
        paymentDate: input.paymentDate,
        paymentMethod: input.paymentMethod,
        status: 'completed',
        allocationStatus,
        referenceNumber: input.referenceNumber || `REF-${Math.floor(100000 + Math.random() * 900000)}`,
        notes: input.notes,
        appliedAmount,
        unappliedAmount,
        refundedAmount: 0,
        bankAccount: input.bankAccount || 'HDFC Bank - A/C **4920',
        gatewayFee: 0,
        allocations: input.allocations,
        refunds: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      setPayments((prev) => [newPayment, ...prev]);

      // Update customer credit balance if unapplied money exists
      if (unappliedAmount > 0) {
        setCustomers((prev) =>
          prev.map((c) =>
            c.id === input.customerId
              ? { ...c, creditBalance: c.creditBalance + unappliedAmount }
              : c
          )
        );
      }

      showToast(
        'success',
        'Payment Recorded',
        `Payment #${id} of ₹${input.amount.toLocaleString('en-IN')} has been recorded successfully.`
      );

      return newPayment;
    },
    [payments.length, customers, showToast]
  );

  // Issue a refund (full or partial)
  const refundPayment = useCallback(
    (input: RefundPaymentInput) => {
      setPayments((prev) =>
        prev.map((p) => {
          if (p.id !== input.paymentId) return p;

          const currentRefunded = p.refundedAmount || 0;
          const newRefundedTotal = currentRefunded + input.amount;
          const isFullRefund = newRefundedTotal >= p.amount;

          const newRefundRecord: PaymentRefund = {
            id: `REF-${String((p.refunds?.length || 0) + 1).padStart(3, '0')}`,
            paymentId: p.id,
            amount: input.amount,
            date: new Date().toISOString().split('T')[0],
            reason: input.reason,
            refundMode: input.refundMode,
            referenceNumber: input.referenceNumber || `REF/REV/${Math.floor(1000000 + Math.random() * 9000000)}`,
            notes: input.notes,
          };

          return {
            ...p,
            status: isFullRefund ? 'refunded' : 'partially_refunded',
            refundedAmount: newRefundedTotal,
            refunds: [...(p.refunds || []), newRefundRecord],
            updatedAt: new Date().toISOString(),
          };
        })
      );

      showToast(
        'success',
        'Refund Processed',
        `Refund of ₹${input.amount.toLocaleString('en-IN')} processed for ${input.paymentId}.`
      );
    },
    [showToast]
  );

  const updatePayment = useCallback(
    (id: string, updates: Partial<Payment>) => {
      setPayments((prev) =>
        prev.map((p) => (p.id === id ? { ...p, ...updates, updatedAt: new Date().toISOString() } : p))
      );
      showToast('success', 'Payment Updated', 'Payment record changes saved.');
    },
    [showToast]
  );

  const deletePayment = useCallback(
    (id: string) => {
      setPayments((prev) => prev.filter((p) => p.id !== id));
      showToast('info', 'Payment Deleted', `Payment record ${id} was deleted.`);
    },
    [showToast]
  );

  const getPaymentById = useCallback((id: string) => payments.find((p) => p.id === id), [payments]);

  const getCustomerById = useCallback(
    (id: string) => customers.find((c) => c.id === id),
    [customers]
  );

  return (
    <PaymentsContext.Provider
      value={{
        payments,
        customers,
        summary,
        recordPayment,
        refundPayment,
        updatePayment,
        deletePayment,
        getPaymentById,
        getCustomerById,
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
