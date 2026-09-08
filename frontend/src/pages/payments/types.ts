import type { PaymentGateway } from '../../types/api';

/**
 * UI-facing payment shapes. Every field here is derived from a real API
 * response (see paymentMapper.ts) — nothing is defaulted to an invented value.
 */

export type PaymentStatus =
  | 'completed'
  | 'pending'
  | 'failed'
  | 'partially_refunded'
  | 'refunded';

export type PaymentMethod =
  | 'UPI'
  | 'Credit Card'
  | 'Debit Card'
  | 'Bank Transfer'
  | 'Net Banking'
  | 'Cash'
  | 'Cheque'
  | 'Razorpay'
  | 'Other';

/** Methods a user may pick when recording a payment by hand (Razorpay is gateway-only). */
export const MANUAL_PAYMENT_METHODS: PaymentMethod[] = [
  'UPI',
  'Bank Transfer',
  'Net Banking',
  'Credit Card',
  'Debit Card',
  'Cash',
  'Cheque',
  'Other',
];

export type PaymentType = 'invoice_payment' | 'customer_advance';

export type AllocationStatus = 'fully_applied' | 'partially_applied' | 'unapplied';

/** One invoice this payment was applied to. */
export interface InvoiceAllocation {
  invoiceId: string;
  invoiceNumber: string;
  appliedAmount: number;
}

export interface PaymentRefund {
  id: string;
  paymentId: string;
  amount: number;
  date: string;
  reason: string;
  refundMode: string;
  referenceNumber?: string;
  notes?: string;
}

export interface Payment {
  /** Human-readable number, e.g. PAY-000123. */
  id: string;
  /** Server UUID — the identifier every write goes through. */
  backendId?: string;
  receiptNumber: string;
  paymentType: PaymentType;
  customerId: string;
  customerName: string;
  customerEmail?: string;
  amount: number;
  paymentDate: string;
  paymentMethod: PaymentMethod;
  status: PaymentStatus;
  allocationStatus: AllocationStatus;
  referenceNumber: string;
  notes?: string;
  appliedAmount: number;
  unappliedAmount: number;
  refundedAmount: number;
  allocations: InvoiceAllocation[];
  refunds: PaymentRefund[];
  /** Gateway payment/order id for online payments; absent for manual ones. */
  gatewayReference?: string;
  gateway?: PaymentGateway;
  createdAt: string;
  updatedAt: string;
}

export interface OutstandingInvoice {
  id: string;
  invoiceNumber: string;
  customerId: string;
  customerName: string;
  date: string;
  dueDate: string;
  totalAmount: number;
  amountPaid: number;
  balanceDue: number;
  status: 'unpaid' | 'partially_paid' | 'overdue';
}

export interface PaymentCustomer {
  id: string;
  name: string;
  companyName?: string;
  email: string;
  phone: string;
  /** Populated by loadCustomerInvoices(); empty until the invoices are fetched. */
  outstandingInvoices: OutstandingInvoice[];
}

export interface PaymentFilterState {
  searchQuery: string;
  statusTab: 'all' | 'completed' | 'pending' | 'failed' | 'refunded';
  /** Customer id, or 'all'. */
  customer: string;
  paymentMethod: string;
  status: string;
  sortBy: 'newest' | 'oldest' | 'amount_high' | 'amount_low';
}

/** Totals for every payment matching the active filters (server-computed). */
export interface PaymentsSummary {
  totalCollected: number;
  pendingProcessing: number;
  totalRefunded: number;
  unappliedCredit: number;
}
