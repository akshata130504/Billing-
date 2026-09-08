export type PaymentStatus =
  | 'completed'
  | 'pending'
  | 'processing'
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
  | 'Other';

export type PaymentType =
  | 'invoice_payment'
  | 'customer_advance';

export type AllocationStatus =
  | 'fully_applied'
  | 'partially_applied'
  | 'unapplied';

export interface InvoiceAllocation {
  invoiceId: string;
  invoiceNumber: string;
  invoiceDate: string;
  invoiceTotal: number;
  appliedAmount: number;
  remainingAmount: number;
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
  id: string; // e.g. PAY-2026-001
  backendId?: string;
  receiptNumber: string; // e.g. RCT-2026-001
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
  bankAccount?: string;
  gatewayFee?: number;
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
  email: string;
  phone: string;
  creditBalance: number;
  outstandingInvoices: OutstandingInvoice[];
}

export interface PaymentFilterState {
  searchQuery: string;
  statusTab: 'all' | 'completed' | 'pending' | 'failed' | 'refunded';
  customer: string;
  paymentMethod: string;
  status: string;
  sortBy: 'newest' | 'oldest' | 'amount_high' | 'amount_low';
}

export interface PaymentsSummary {
  totalCollected: number;
  pendingProcessing: number;
  totalRefunded: number;
  unappliedCredit: number;
}
