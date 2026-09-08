import type {
  PaymentOut,
  PaymentIn,
  CustomerOut,
  InvoiceOut,
  ManualPaymentMethod,
  PaymentMethod as BackendPaymentMethod,
  PaymentStatus as BackendPaymentStatus,
} from '../../types/api';
import type {
  Payment,
  PaymentMethod as UiPaymentMethod,
  PaymentStatus as UiPaymentStatus,
  AllocationStatus,
  PaymentType,
  InvoiceAllocation,
  PaymentRefund,
  PaymentCustomer,
  OutstandingInvoice,
} from './types';
import type { RecordPaymentInput } from './PaymentsContext';

/**
 * Maps frontend UI PaymentMethod to backend ManualPaymentMethod.
 */
export function toBackendPaymentMethod(uiMethod: UiPaymentMethod): ManualPaymentMethod {
  switch (uiMethod) {
    case 'UPI':
      return 'upi';
    case 'Bank Transfer':
    case 'Net Banking':
      return 'bank_transfer';
    case 'Credit Card':
    case 'Debit Card':
      return 'card';
    case 'Cash':
      return 'cash';
    case 'Cheque':
      return 'cheque';
    default:
      return 'other';
  }
}

/**
 * Maps backend PaymentMethod to frontend UI PaymentMethod.
 */
export function toUiPaymentMethod(backendMethod: BackendPaymentMethod | string): UiPaymentMethod {
  switch (backendMethod) {
    case 'upi':
      return 'UPI';
    case 'bank_transfer':
      return 'Bank Transfer';
    case 'card':
      return 'Credit Card';
    case 'cash':
      return 'Cash';
    case 'cheque':
      return 'Cheque';
    case 'razorpay':
      return 'Razorpay';
    default:
      return 'Other';
  }
}

/**
 * Maps backend PaymentStatus to frontend UI PaymentStatus.
 * Handles 'succeeded' <-> 'completed' mapping.
 */
export function toUiPaymentStatus(backendStatus: BackendPaymentStatus | string): UiPaymentStatus {
  switch (backendStatus) {
    case 'succeeded':
      return 'completed';
    case 'pending':
      return 'pending';
    case 'failed':
      return 'failed';
    case 'refunded':
      return 'refunded';
    case 'partially_refunded':
      return 'partially_refunded';
    default:
      // An unrecognised status must never be presented as collected money.
      return 'pending';
  }
}

/**
 * Maps backend PaymentOut to frontend UI Payment.
 */
export function paymentOutToUi(p: PaymentOut): Payment {
  const amount = parseFloat(p.amount) || 0;
  const appliedAmount = parseFloat(p.amount_allocated) || 0;
  const unappliedAmount = parseFloat(p.amount_unallocated) || 0;
  const refundedAmount = parseFloat(p.amount_refunded) || 0;

  let allocationStatus: AllocationStatus = 'unapplied';
  if (unappliedAmount <= 0 && appliedAmount > 0) {
    allocationStatus = 'fully_applied';
  } else if (appliedAmount > 0 && unappliedAmount > 0) {
    allocationStatus = 'partially_applied';
  } else {
    allocationStatus = 'unapplied';
  }

  const paymentType: PaymentType =
    p.allocations && p.allocations.length > 0 ? 'invoice_payment' : 'customer_advance';

  const allocations: InvoiceAllocation[] = (p.allocations || []).map((a) => ({
    invoiceId: a.invoice_id,
    invoiceNumber: a.invoice_number,
    appliedAmount: parseFloat(a.amount) || 0,
  }));

  const refunds: PaymentRefund[] = (p.refunds || []).map((r) => ({
    id: r.id,
    paymentId: p.payment_number || p.id,
    amount: parseFloat(r.amount) || 0,
    date: r.created_at ? r.created_at.split('T')[0] : '',
    reason: r.reason || 'Payment refund',
    refundMode: r.gateway_refund_id ? 'Razorpay Gateway' : 'Manual Ledger',
    referenceNumber: r.gateway_refund_id || undefined,
  }));

  const receiptNum = p.payment_number
    ? `RCT-${p.payment_number.replace(/^PAY-/, '')}`
    : `RCT-${p.id.slice(0, 8).toUpperCase()}`;

  return {
    id: p.payment_number || p.id,
    backendId: p.id,
    receiptNumber: receiptNum,
    paymentType,
    customerId: p.customer?.id || '',
    customerName: p.customer?.display_name || 'Customer',
    customerEmail: p.customer?.email || undefined,
    amount,
    paymentDate: p.paid_at ? p.paid_at.split('T')[0] : p.created_at.split('T')[0],
    paymentMethod: toUiPaymentMethod(p.method),
    status: toUiPaymentStatus(p.status),
    allocationStatus,
    referenceNumber: p.reference || '',
    notes: p.notes || undefined,
    appliedAmount,
    unappliedAmount,
    refundedAmount,
    allocations,
    refunds,
    gatewayReference: p.gateway_payment_id || p.gateway_order_id || undefined,
    gateway: p.gateway,
    createdAt: p.created_at,
    updatedAt: p.updated_at,
  };
}

/**
 * Maps frontend RecordPaymentInput to backend PaymentIn payload.
 */
export function uiToPaymentIn(input: RecordPaymentInput): PaymentIn {
  const backendMethod = toBackendPaymentMethod(input.paymentMethod);
  const paidAt = input.paymentDate
    ? new Date(`${input.paymentDate}T12:00:00Z`).toISOString()
    : new Date().toISOString();

  const allocations =
    input.paymentType === 'invoice_payment' && input.allocations.length > 0
      ? input.allocations
          .filter((a) => a.appliedAmount > 0)
          .map((a) => ({
            invoice_id: a.invoiceId,
            amount: a.appliedAmount.toFixed(2),
          }))
      : undefined;

  return {
    customer_id: input.customerId,
    amount: input.amount.toFixed(2),
    method: backendMethod,
    paid_at: paidAt,
    reference: input.referenceNumber || null,
    notes: input.notes || null,
    allocations: allocations && allocations.length > 0 ? allocations : undefined,
  };
}

/**
 * Maps a customer and their invoices to the frontend PaymentCustomer interface.
 */
export function customerToUi(c: CustomerOut, invoices: InvoiceOut[] = []): PaymentCustomer {
  const openInvoices: OutstandingInvoice[] = invoices
    .filter(
      (inv) =>
        (!inv.customer || inv.customer.id === c.id) &&
        (inv.status === 'sent' || inv.status === 'partially_paid' || inv.status === 'overdue')
    )
    .map((inv) => ({
      id: inv.id,
      invoiceNumber: inv.invoice_number,
      customerId: c.id,
      customerName: c.display_name,
      date: inv.issue_date,
      dueDate: inv.due_date,
      totalAmount: parseFloat(inv.total) || 0,
      amountPaid: parseFloat(inv.amount_paid) || 0,
      balanceDue: parseFloat(inv.amount_due) || 0,
      status:
        inv.status === 'partially_paid'
          ? 'partially_paid'
          : inv.status === 'overdue'
          ? 'overdue'
          : 'unpaid',
    }));

  return {
    id: c.id,
    name: c.display_name,
    companyName: c.company_name || undefined,
    email: c.email || '',
    phone: c.phone || '',
    outstandingInvoices: openInvoices,
  };
}
