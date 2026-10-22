import { describe, expect, it } from 'vitest';
import type { CustomerOut, InvoiceOut, PaymentOut } from '../../types/api';
import type { RecordPaymentInput } from './PaymentsContext';
import { MANUAL_PAYMENT_METHODS, type PaymentMethod as UiPaymentMethod } from './types';
import {
  customerToUi,
  paymentOutToUi,
  toBackendPaymentMethod,
  toUiPaymentMethod,
  toUiPaymentStatus,
  uiToPaymentIn,
  OverAllocationError,
} from './paymentMapper';

// ---------------------------------------------------------------------------
// Fixtures — shaped exactly like the FastAPI responses (money as strings).
// ---------------------------------------------------------------------------

function makePayment(over: Partial<PaymentOut> = {}): PaymentOut {
  return {
    id: 'a1b2c3d4-0000-0000-0000-000000000001',
    payment_number: 'PAY-000123',
    customer: {
      id: 'cus_1',
      customer_number: 'CUST-0001',
      display_name: 'Acme Pvt Ltd',
      email: 'ap@acme.test',
    },
    amount: '1000.00',
    currency: 'INR',
    method: 'upi',
    gateway: 'manual',
    status: 'succeeded',
    reconciliation_status: 'matched',
    gateway_order_id: null,
    gateway_payment_id: null,
    gateway_signature_verified: false,
    reference: 'UTR123',
    paid_at: '2026-09-07T12:00:00Z',
    failure_reason: null,
    notes: null,
    amount_refunded: '0.00',
    amount_allocated: '1000.00',
    amount_unallocated: '0.00',
    allocations: [
      { id: 'alloc_1', invoice_id: 'inv_1', invoice_number: 'INV-0001', amount: '1000.00' },
    ],
    refunds: [],
    recorded_by: null,
    created_at: '2026-09-07T12:00:05Z',
    updated_at: '2026-09-07T12:00:05Z',
    ...over,
  };
}

function makeInvoice(over: Partial<InvoiceOut> = {}): InvoiceOut {
  return {
    id: 'inv_1',
    invoice_number: 'INV-0001',
    customer: { id: 'cus_1', customer_number: 'CUST-0001', display_name: 'Acme Pvt Ltd', email: null },
    subscription_id: null,
    quote_id: null,
    status: 'sent',
    issue_date: '2026-09-01',
    due_date: '2026-09-15',
    currency: 'INR',
    subtotal: '1000.00',
    discount_pct: '0.00',
    discount_amount: '0.00',
    tax_amount: '180.00',
    total: '1180.00',
    amount_paid: '0.00',
    amount_due: '1180.00',
    notes: null,
    terms: null,
    items: [],
    public_url: '',
    pdf_url: '',
    sent_at: null,
    paid_at: null,
    voided_at: null,
    void_reason: null,
    last_reminder_at: null,
    reminder_count: 0,
    period_start: null,
    period_end: null,
    days_overdue: 0,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...over,
  } as InvoiceOut;
}

function makeCustomer(over: Partial<CustomerOut> = {}): CustomerOut {
  return {
    id: 'cus_1',
    customer_number: 'CUST-0001',
    display_name: 'Acme Pvt Ltd',
    company_name: 'Acme Private Limited',
    email: 'ap@acme.test',
    phone: '+91 99999 99999',
    website: null,
    gstin: null,
    pan: null,
    tax_exempt: false,
    currency: 'INR',
    payment_terms_days: 14,
    status: 'active',
    billing_address_line1: null,
    billing_address_line2: null,
    billing_city: null,
    billing_state: null,
    billing_postal_code: null,
    billing_country: null,
    notes: null,
    portal_url: null,
    contacts: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  } as CustomerOut;
}

// ---------------------------------------------------------------------------

describe('toBackendPaymentMethod', () => {
  it('maps every UI method onto a valid ManualPaymentMethod', () => {
    expect(toBackendPaymentMethod('UPI')).toBe('upi');
    expect(toBackendPaymentMethod('Bank Transfer')).toBe('bank_transfer');
    expect(toBackendPaymentMethod('Net Banking')).toBe('bank_transfer');
    expect(toBackendPaymentMethod('Credit Card')).toBe('card');
    expect(toBackendPaymentMethod('Debit Card')).toBe('card');
    expect(toBackendPaymentMethod('Cash')).toBe('cash');
    expect(toBackendPaymentMethod('Cheque')).toBe('cheque');
    expect(toBackendPaymentMethod('Other')).toBe('other');
  });

  it('never sends the gateway-only "razorpay" method for a manual entry', () => {
    const allowed = ['upi', 'bank_transfer', 'card', 'cash', 'cheque', 'other'];
    for (const m of MANUAL_PAYMENT_METHODS) {
      expect(allowed).toContain(toBackendPaymentMethod(m));
    }
    expect(toBackendPaymentMethod('Razorpay' as UiPaymentMethod)).toBe('other');
  });
});

describe('toUiPaymentMethod', () => {
  it('maps backend methods to their UI labels', () => {
    expect(toUiPaymentMethod('upi')).toBe('UPI');
    expect(toUiPaymentMethod('bank_transfer')).toBe('Bank Transfer');
    expect(toUiPaymentMethod('card')).toBe('Credit Card');
    expect(toUiPaymentMethod('cash')).toBe('Cash');
    expect(toUiPaymentMethod('cheque')).toBe('Cheque');
    expect(toUiPaymentMethod('razorpay')).toBe('Razorpay');
  });

  it('falls back to "Other" for an unknown method', () => {
    expect(toUiPaymentMethod('bitcoin')).toBe('Other');
    expect(toUiPaymentMethod('')).toBe('Other');
  });

  it('round-trips losslessly for the methods the backend models 1:1', () => {
    for (const m of ['UPI', 'Bank Transfer', 'Cash', 'Cheque', 'Other'] as UiPaymentMethod[]) {
      expect(toUiPaymentMethod(toBackendPaymentMethod(m))).toBe(m);
    }
  });

  it('collapses Debit Card and Net Banking on the round trip (backend has no such enum)', () => {
    // Known lossy mapping: the backend enum has no debit/netbanking member, so a
    // payment recorded as "Debit Card" is displayed afterwards as "Credit Card".
    expect(toUiPaymentMethod(toBackendPaymentMethod('Debit Card'))).toBe('Credit Card');
    expect(toUiPaymentMethod(toBackendPaymentMethod('Net Banking'))).toBe('Bank Transfer');
  });
});

describe('toUiPaymentStatus', () => {
  it('renames succeeded to completed and passes the rest through', () => {
    expect(toUiPaymentStatus('succeeded')).toBe('completed');
    expect(toUiPaymentStatus('pending')).toBe('pending');
    expect(toUiPaymentStatus('failed')).toBe('failed');
    expect(toUiPaymentStatus('refunded')).toBe('refunded');
    expect(toUiPaymentStatus('partially_refunded')).toBe('partially_refunded');
  });

  it('never shows an unknown status as collected money', () => {
    for (const unknown of ['authorized', 'captured', 'disputed', '', 'completed']) {
      expect(toUiPaymentStatus(unknown)).toBe('pending');
    }
  });
});

describe('paymentOutToUi', () => {
  it('maps the money fields as numbers without losing paise', () => {
    const ui = paymentOutToUi(
      makePayment({
        amount: '1234.56',
        amount_allocated: '1000.00',
        amount_unallocated: '234.56',
        amount_refunded: '10.05',
      })
    );
    expect(ui.amount).toBe(1234.56);
    expect(ui.appliedAmount).toBe(1000);
    expect(ui.unappliedAmount).toBe(234.56);
    expect(ui.refundedAmount).toBe(10.05);
  });

  it('uses the human payment number as id and keeps the UUID as backendId', () => {
    const ui = paymentOutToUi(makePayment());
    expect(ui.id).toBe('PAY-000123');
    expect(ui.backendId).toBe('a1b2c3d4-0000-0000-0000-000000000001');
  });

  it('derives the receipt number from the payment number', () => {
    expect(paymentOutToUi(makePayment()).receiptNumber).toBe('RCT-000123');
  });

  it('derives a receipt number from the UUID when there is no payment number', () => {
    const ui = paymentOutToUi(makePayment({ payment_number: '' }));
    expect(ui.id).toBe('a1b2c3d4-0000-0000-0000-000000000001');
    expect(ui.receiptNumber).toBe('RCT-A1B2C3D4');
  });

  describe('allocation status', () => {
    it('is fully_applied when nothing is left unallocated', () => {
      const ui = paymentOutToUi(
        makePayment({ amount_allocated: '1000.00', amount_unallocated: '0.00' })
      );
      expect(ui.allocationStatus).toBe('fully_applied');
    });

    it('is partially_applied when some of the payment is still open', () => {
      const ui = paymentOutToUi(
        makePayment({ amount_allocated: '600.00', amount_unallocated: '400.00' })
      );
      expect(ui.allocationStatus).toBe('partially_applied');
    });

    it('is unapplied when nothing has been allocated', () => {
      const ui = paymentOutToUi(
        makePayment({ amount_allocated: '0.00', amount_unallocated: '1000.00', allocations: [] })
      );
      expect(ui.allocationStatus).toBe('unapplied');
    });
  });

  it('classifies a payment with allocations as an invoice payment', () => {
    expect(paymentOutToUi(makePayment()).paymentType).toBe('invoice_payment');
  });

  it('classifies a payment with no allocations as a customer advance', () => {
    const ui = paymentOutToUi(
      makePayment({ allocations: [], amount_allocated: '0.00', amount_unallocated: '1000.00' })
    );
    expect(ui.paymentType).toBe('customer_advance');
  });

  it('maps allocation rows', () => {
    const ui = paymentOutToUi(
      makePayment({
        allocations: [
          { id: 'a1', invoice_id: 'inv_1', invoice_number: 'INV-0001', amount: '600.00' },
          { id: 'a2', invoice_id: 'inv_2', invoice_number: 'INV-0002', amount: '400.00' },
        ],
      })
    );
    expect(ui.allocations).toEqual([
      { invoiceId: 'inv_1', invoiceNumber: 'INV-0001', appliedAmount: 600 },
      { invoiceId: 'inv_2', invoiceNumber: 'INV-0002', appliedAmount: 400 },
    ]);
  });

  it('maps refunds, labelling gateway refunds separately from manual ones', () => {
    const ui = paymentOutToUi(
      makePayment({
        refunds: [
          {
            id: 'ref_1',
            amount: '250.00',
            status: 'processed',
            gateway_refund_id: 'rfnd_xyz',
            reason: 'Duplicate charge',
            created_at: '2026-09-08T06:30:00Z',
          },
          {
            id: 'ref_2',
            amount: '100.00',
            status: 'processed',
            gateway_refund_id: null,
            reason: null,
            created_at: '2026-09-09T06:30:00Z',
          },
        ],
      })
    );
    expect(ui.refunds[0]).toEqual({
      id: 'ref_1',
      paymentId: 'PAY-000123',
      amount: 250,
      date: '2026-09-08',
      reason: 'Duplicate charge',
      refundMode: 'Razorpay Gateway',
      referenceNumber: 'rfnd_xyz',
    });
    expect(ui.refunds[1].refundMode).toBe('Manual Ledger');
    expect(ui.refunds[1].reason).toBe('Payment refund');
    expect(ui.refunds[1].referenceNumber).toBeUndefined();
  });

  it('prefers paid_at over created_at for the payment date', () => {
    const ui = paymentOutToUi(
      makePayment({ paid_at: '2026-09-07T12:00:00Z', created_at: '2026-09-09T01:00:00Z' })
    );
    expect(ui.paymentDate).toBe('2026-09-07');
  });

  it('falls back to created_at when the payment was never marked paid', () => {
    const ui = paymentOutToUi(makePayment({ paid_at: null, created_at: '2026-09-09T01:00:00Z' }));
    expect(ui.paymentDate).toBe('2026-09-09');
  });

  it('tolerates a null customer without crashing the payments list', () => {
    const ui = paymentOutToUi(makePayment({ customer: null }));
    expect(ui.customerId).toBe('');
    expect(ui.customerName).toBe('Customer');
    expect(ui.customerEmail).toBeUndefined();
  });

  it('prefers the gateway payment id over the order id as the gateway reference', () => {
    expect(
      paymentOutToUi(makePayment({ gateway_payment_id: 'pay_x', gateway_order_id: 'order_y' }))
        .gatewayReference
    ).toBe('pay_x');
    expect(
      paymentOutToUi(makePayment({ gateway_payment_id: null, gateway_order_id: 'order_y' }))
        .gatewayReference
    ).toBe('order_y');
    expect(paymentOutToUi(makePayment()).gatewayReference).toBeUndefined();
  });

  it('normalises a missing reference to an empty string, not "null"', () => {
    expect(paymentOutToUi(makePayment({ reference: null })).referenceNumber).toBe('');
  });
});

describe('uiToPaymentIn', () => {
  const base: RecordPaymentInput = {
    paymentType: 'invoice_payment',
    customerId: 'cus_1',
    customerName: 'Acme Pvt Ltd',
    amount: 1180,
    paymentDate: '2026-09-07',
    paymentMethod: 'UPI',
    referenceNumber: 'UTR123',
    notes: 'Cleared same day',
    allocations: [{ invoiceId: 'inv_1', invoiceNumber: 'INV-0001', appliedAmount: 1180 }],
  };

  it('serialises the amount as a 2-decimal string', () => {
    expect(uiToPaymentIn({ ...base, amount: 1180 }).amount).toBe('1180.00');
    // No allocations here: a 0.50 payment cannot cover base's invoice allocations,
    // which uiToPaymentIn now rejects outright (see the over-allocation test).
    expect(uiToPaymentIn({ ...base, amount: 0.5, allocations: [] }).amount).toBe('0.50');
  });

  it('anchors paid_at at noon UTC so the calendar date survives IST conversion', () => {
    const out = uiToPaymentIn(base);
    expect(out.paid_at).toBe('2026-09-07T12:00:00.000Z');
    // Rendering that instant back in IST (+05:30) must still be the 7th.
    expect(new Date(out.paid_at!).getTime()).toBe(Date.parse('2026-09-07T12:00:00Z'));
  });

  it('falls back to "now" when no payment date was picked', () => {
    const before = Date.now();
    const out = uiToPaymentIn({ ...base, paymentDate: '' });
    const at = Date.parse(out.paid_at!);
    expect(at).toBeGreaterThanOrEqual(before - 1000);
    expect(at).toBeLessThanOrEqual(Date.now() + 1000);
  });

  it('sends allocations for an invoice payment', () => {
    expect(uiToPaymentIn(base).allocations).toEqual([{ invoice_id: 'inv_1', amount: '1180.00' }]);
  });

  it('drops zero-value allocation rows', () => {
    const out = uiToPaymentIn({
      ...base,
      allocations: [
        { invoiceId: 'inv_1', invoiceNumber: 'INV-0001', appliedAmount: 1180 },
        { invoiceId: 'inv_2', invoiceNumber: 'INV-0002', appliedAmount: 0 },
      ],
    });
    expect(out.allocations).toEqual([{ invoice_id: 'inv_1', amount: '1180.00' }]);
  });

  it('omits allocations entirely for a customer advance', () => {
    const out = uiToPaymentIn({ ...base, paymentType: 'customer_advance' });
    expect(out.allocations).toBeUndefined();
  });

  it('omits allocations when every row nets to zero', () => {
    const out = uiToPaymentIn({
      ...base,
      allocations: [{ invoiceId: 'inv_1', invoiceNumber: 'INV-0001', appliedAmount: 0 }],
    });
    expect(out.allocations).toBeUndefined();
  });

  it('nulls out blank reference and notes rather than sending empty strings', () => {
    const out = uiToPaymentIn({ ...base, referenceNumber: '', notes: undefined });
    expect(out.reference).toBeNull();
    expect(out.notes).toBeNull();
  });

  it('translates the UI method to the backend enum', () => {
    expect(uiToPaymentIn({ ...base, paymentMethod: 'Net Banking' }).method).toBe('bank_transfer');
  });

  // BUG (money-critical): allocations are summed nowhere, so the mapper happily
  // builds a payload that allocates more than the payment amount. The backend
  // rejects it with a 4xx the user then has to decode; the mapper (or the form)
  // should refuse to over-allocate.
  // See src/modules/payments/paymentMapper.ts:161-185 (uiToPaymentIn).
  it('should not allocate more than the payment amount', () => {
    expect(() =>
      uiToPaymentIn({
        ...base,
        amount: 1000,
        allocations: [
          { invoiceId: 'inv_1', invoiceNumber: 'INV-0001', appliedAmount: 900 },
          { invoiceId: 'inv_2', invoiceNumber: 'INV-0002', appliedAmount: 900 },
        ],
      })
    ).toThrow(OverAllocationError);
  });

  it('allows allocations that exactly equal the payment amount', () => {
    const out = uiToPaymentIn({
      ...base,
      amount: 1000,
      allocations: [
        { invoiceId: 'inv_1', invoiceNumber: 'INV-0001', appliedAmount: 400 },
        { invoiceId: 'inv_2', invoiceNumber: 'INV-0002', appliedAmount: 600 },
      ],
    });
    const allocated = (out.allocations ?? []).reduce((s, a) => s + Number(a.amount), 0);
    expect(allocated).toBe(1000);
  });
});

describe('customerToUi', () => {
  it('maps the customer profile fields', () => {
    const ui = customerToUi(makeCustomer());
    expect(ui).toMatchObject({
      id: 'cus_1',
      name: 'Acme Pvt Ltd',
      companyName: 'Acme Private Limited',
      email: 'ap@acme.test',
      phone: '+91 99999 99999',
    });
    expect(ui.outstandingInvoices).toEqual([]);
  });

  it('normalises missing contact details to empty strings', () => {
    const ui = customerToUi(makeCustomer({ email: null, phone: null, company_name: null }));
    expect(ui.email).toBe('');
    expect(ui.phone).toBe('');
    expect(ui.companyName).toBeUndefined();
  });

  it('keeps only invoices that can still receive a payment', () => {
    const invoices = [
      makeInvoice({ id: 'i_sent', invoice_number: 'INV-1', status: 'sent' }),
      makeInvoice({ id: 'i_part', invoice_number: 'INV-2', status: 'partially_paid' }),
      makeInvoice({ id: 'i_over', invoice_number: 'INV-3', status: 'overdue' }),
      makeInvoice({ id: 'i_paid', invoice_number: 'INV-4', status: 'paid' }),
      makeInvoice({ id: 'i_draft', invoice_number: 'INV-5', status: 'draft' }),
      makeInvoice({ id: 'i_void', invoice_number: 'INV-6', status: 'void' }),
    ];
    const ui = customerToUi(makeCustomer(), invoices);
    expect(ui.outstandingInvoices.map((i) => i.id)).toEqual(['i_sent', 'i_part', 'i_over']);
  });

  it('never lists another customer\'s invoice', () => {
    const other = makeInvoice({
      id: 'i_other',
      customer: { id: 'cus_2', customer_number: 'C2', display_name: 'Other', email: null },
    });
    const ui = customerToUi(makeCustomer(), [makeInvoice(), other]);
    expect(ui.outstandingInvoices.map((i) => i.id)).toEqual(['inv_1']);
  });

  it('parses invoice money strings into numbers', () => {
    const ui = customerToUi(makeCustomer(), [
      makeInvoice({ total: '1180.00', amount_paid: '180.00', amount_due: '1000.00' }),
    ]);
    expect(ui.outstandingInvoices[0]).toMatchObject({
      totalAmount: 1180,
      amountPaid: 180,
      balanceDue: 1000,
      customerId: 'cus_1',
      customerName: 'Acme Pvt Ltd',
      date: '2026-09-01',
      dueDate: '2026-09-15',
    });
  });

  it('maps the outstanding-invoice status onto the payment-form vocabulary', () => {
    const statuses = customerToUi(makeCustomer(), [
      makeInvoice({ id: 'a', status: 'sent' }),
      makeInvoice({ id: 'b', status: 'partially_paid' }),
      makeInvoice({ id: 'c', status: 'overdue' }),
    ]).outstandingInvoices.map((i) => i.status);
    expect(statuses).toEqual(['unpaid', 'partially_paid', 'overdue']);
  });
});

// NEW-01: a payment's currency comes from the API. A missing or malformed code is "unknown",
// never silently INR (the backend may have used the organization's default currency).
describe('payment currency mapping', () => {
  it('keeps the currency the API sent, upper-cased', () => {
    expect(paymentOutToUi(makePayment({ currency: 'AED' })).currency).toBe('AED');
    expect(paymentOutToUi(makePayment({ currency: 'usd' })).currency).toBe('USD');
    expect(paymentOutToUi(makePayment({ currency: 'INR' })).currency).toBe('INR');
  });

  it.each([
    ['missing', undefined],
    ['null', null],
    ['empty', ''],
    ['too long', 'RUPEES'],
    ['symbol', '₹'],
    ['digits', '123'],
  ])('maps a %s payment currency to unknown (null), not INR', (_label, value) => {
    const ui = paymentOutToUi(makePayment({ currency: value as unknown as string }));
    expect(ui.currency).toBeNull();
  });

  it('takes outstanding-invoice currency from the invoice only, unknown when invalid', () => {
    const ui = customerToUi(makeCustomer({ currency: 'AED' } as Partial<CustomerOut>), [
      makeInvoice({ id: 'i_aed', status: 'sent', currency: 'AED' } as Partial<InvoiceOut>),
      makeInvoice({ id: 'i_none', status: 'sent', currency: undefined } as unknown as Partial<InvoiceOut>),
      makeInvoice({ id: 'i_bad', status: 'sent', currency: 'XX' } as Partial<InvoiceOut>),
    ]);
    expect(ui.currency).toBe('AED');
    expect(ui.outstandingInvoices.map((i) => i.currency)).toEqual(['AED', null, null]);
  });

  it('maps a missing or invalid customer currency to unknown', () => {
    expect(customerToUi(makeCustomer({ currency: undefined } as unknown as Partial<CustomerOut>)).currency).toBeNull();
    expect(customerToUi(makeCustomer({ currency: 'dirham' } as Partial<CustomerOut>)).currency).toBeNull();
  });
});
