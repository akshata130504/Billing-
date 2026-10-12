import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { ReceiptModal } from './ReceiptModal';
import type { Payment } from '../types';

vi.mock('../../../components/common/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));
vi.mock('../../../hooks/useAuth', () => ({ useAuth: () => ({ organization: { name: 'QA Org', country: 'IN' } }) }));

function payment(over: Partial<Payment>): Payment {
  return {
    id: 'PAY-000009', backendId: 'p-9', receiptNumber: 'RCT-000009', paymentType: 'invoice_payment',
    customerId: 'c-1', customerName: 'Dollar Customer', amount: 250, currency: 'USD', paymentDate: '2026-10-12',
    paymentMethod: 'bank_transfer', status: 'completed', allocationStatus: 'fully_applied', referenceNumber: 'REF-1',
    appliedAmount: 250, unappliedAmount: 0, refundedAmount: 40,
    allocations: [{ invoiceId: 'i-1', invoiceNumber: 'INV-000020', appliedAmount: 250 }],
    refunds: [], createdAt: '2026-10-12T00:00:00Z', updatedAt: '2026-10-12T00:00:00Z',
    ...over,
  } as Payment;
}

// NEW-01: receipts printed rupees for every payment (and the refund note used a literal "₹").
describe('<ReceiptModal /> amounts in the payment currency (NEW-01)', () => {
  it('shows a USD payment, its allocation and its refund in dollars', () => {
    const { container } = render(<ReceiptModal isOpen onClose={() => {}} payment={payment({})} />);
    const text = container.ownerDocument.body.textContent ?? '';
    expect(text).not.toContain('₹');
    expect(text).toContain('$250.00');
    expect(text).toContain('$40.00');
  });

  it('keeps rupees for an INR payment', () => {
    const { container } = render(<ReceiptModal isOpen onClose={() => {}} payment={payment({ currency: 'INR', amount: 1180.4, appliedAmount: 1180.4, refundedAmount: 0 })} />);
    expect(container.ownerDocument.body.textContent).toContain('₹1,180.40');
  });
});
