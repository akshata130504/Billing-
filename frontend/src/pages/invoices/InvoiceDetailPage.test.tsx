import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { InvoiceDetailPage } from './InvoiceDetailPage';
import { invoiceService } from '../../services/invoiceService';
import type { Invoice } from '../../types/invoices';

vi.mock('../../services/invoiceService', () => ({
  invoiceService: {
    getInvoice: vi.fn(),
    getInvoicePayments: vi.fn(),
  },
}));

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ hasRole: () => true }),
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

vi.mock('../settings/PreferencesTab', () => ({
  loadPreferences: () => ({ confirmBeforeSendInvoice: false }),
}));

const explanation = JSON.stringify({
  catalog_base_price: '1200.00',
  price_book_adjustment: { name: 'Partner book', adjustment_pct: '-10' },
  effective_unit_price: '1000.00',
  tier_explanation: 'Volume tier 1-10',
});

function makeInvoice(): Invoice {
  return {
    id: 'inv-1',
    invoice_number: 'INV-000001',
    customer_id: 'c-1',
    customer: { id: 'c-1', display_name: 'Acme Corp', email: 'ap@acme.test' },
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
    items: [
      { id: 'li-1', description: 'Analytics Seat', quantity: '1', unit_price: '1000.00', tax_rate_pct: '18', amount: '1000.00', position: 0, pricing_explanation: explanation },
    ],
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-01T10:00:00Z',
  } as unknown as Invoice;
}

describe('<InvoiceDetailPage /> pricing explanation (BUG-05)', () => {
  it('renders the stored JSON as readable pricing details, never the raw string', async () => {
    vi.mocked(invoiceService.getInvoice).mockResolvedValue(makeInvoice());
    vi.mocked(invoiceService.getInvoicePayments).mockResolvedValue([]);
    const { container } = render(
      <MemoryRouter initialEntries={['/invoices/inv-1']}>
        <Routes>
          <Route path="/invoices/:id" element={<InvoiceDetailPage />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByText('Pricing details')).toBeInTheDocument();
    expect(screen.getByText('Catalog base price')).toBeInTheDocument();
    expect(screen.getByText('Price book adjustment')).toBeInTheDocument();
    expect(screen.getByText('Name: Partner book; Adjustment: -10%')).toBeInTheDocument();
    expect(container.textContent).not.toContain(explanation);
    expect(container.textContent).not.toContain('catalog_base_price');
    expect(container.textContent).not.toContain('{"');
  });
});
