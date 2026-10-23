import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RecordPaymentModal } from './RecordPaymentModal';
import type { PaymentCustomer } from '../types';

let customers: PaymentCustomer[] = [];
vi.mock('../PaymentsContext', () => ({
  usePayments: () => ({
    customers,
    recordPayment: vi.fn(),
    createCustomer: vi.fn(),
    loadCustomerInvoices: vi.fn().mockResolvedValue(undefined),
    searchCustomers: vi.fn().mockResolvedValue(undefined),
  }),
}));
vi.mock('../../../components/common/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));

function customer(over: Partial<PaymentCustomer>): PaymentCustomer {
  return { id: 'c-1', name: 'Gulf Trading LLC', email: '', phone: '', currency: 'AED', outstandingInvoices: [], ...over };
}

/** The "Amount Received" label text, without the required-field asterisk. */
const amountLabel = () =>
  (screen.getByText(/^Amount Received/, { selector: 'label' }).textContent ?? '').replace('*', '').trim();

// The dialog said "Amount Received (currency unknown)" before any customer was chosen.
describe('<RecordPaymentModal /> amount label', () => {
  beforeEach(() => {
    customers = [];
  });

  it('shows "Amount Received" with no currency before a customer is selected', () => {
    render(<RecordPaymentModal isOpen onClose={vi.fn()} />);
    expect(amountLabel()).toBe('Amount Received');
    expect(screen.queryByText(/currency unknown/)).toBeNull();
    expect(screen.queryByText('INR')).toBeNull();
    expect(screen.queryByText('?')).toBeNull();
    // Summary rows show plain amounts, not "0.00 (currency unknown)".
    expect(screen.getAllByText('0.00').length).toBeGreaterThan(0);
  });

  it("shows the selected customer's currency (AED)", () => {
    customers = [customer({})];
    render(<RecordPaymentModal isOpen onClose={vi.fn()} preselectedCustomerId="c-1" />);
    expect(amountLabel()).toBe('Amount Received (AED)');
  });

  it("shows the selected customer's currency (USD and INR)", () => {
    customers = [customer({ id: 'c-usd', name: 'Acme Inc', currency: 'USD' }), customer({ id: 'c-inr', name: 'Bharat Pvt Ltd', currency: 'INR' })];
    const { unmount } = render(<RecordPaymentModal isOpen onClose={vi.fn()} preselectedCustomerId="c-usd" />);
    expect(amountLabel()).toBe('Amount Received (USD)');
    expect(screen.getByText('$')).toBeInTheDocument();
    unmount();
    render(<RecordPaymentModal isOpen onClose={vi.fn()} preselectedCustomerId="c-inr" />);
    expect(amountLabel()).toBe('Amount Received (INR)');
    expect(screen.getByText('₹')).toBeInTheDocument();
  });

  it('updates the label when a customer is picked from the search list', () => {
    // Customers arrive after the dialog opens, so none is selected at first.
    const { rerender } = render(<RecordPaymentModal isOpen onClose={vi.fn()} />);
    expect(amountLabel()).toBe('Amount Received');
    customers = [customer({})];
    rerender(<RecordPaymentModal isOpen onClose={vi.fn()} />);
    expect(amountLabel()).toBe('Amount Received');
    fireEvent.click(screen.getByPlaceholderText('Search customer...'));
    fireEvent.click(screen.getByRole('button', { name: /Gulf Trading LLC/ }));
    expect(amountLabel()).toBe('Amount Received (AED)');
    expect(screen.getAllByText(/AED\s?0\.00/).length).toBeGreaterThan(0);
  });

  it('keeps "currency unknown" for a selected customer whose currency is missing', () => {
    customers = [customer({ currency: null })];
    render(<RecordPaymentModal isOpen onClose={vi.fn()} preselectedCustomerId="c-1" />);
    expect(amountLabel()).toBe('Amount Received (currency unknown)');
  });
});
