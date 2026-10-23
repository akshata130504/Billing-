import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QuoteDetailPage } from './QuoteDetailPage';
import { quoteService } from '../../services/quoteService';
import type { Quote } from '../../types/quotes';

const showToast = vi.fn();
let role: 'admin' | 'finance' = 'admin';

vi.mock('../../services/quoteService', () => ({
  quoteService: {
    getQuote: vi.fn(),
    approveQuote: vi.fn(),
    rejectQuote: vi.fn(),
    sendQuote: vi.fn(),
    markViewed: vi.fn(),
    overrideAccept: vi.fn(),
    overrideDecline: vi.fn(),
    EMAIL_NOT_SENT_MESSAGE: 'email not sent',
  },
}));

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    // admin > finance > viewer
    hasRole: (min: string) => (min === 'admin' ? role === 'admin' : true),
  }),
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast }),
}));

vi.mock('../../pages/settings/PreferencesTab', () => ({
  loadPreferences: () => ({ confirmBeforeSendInvoice: false }),
}));

function makeQuote(overrides: Partial<Quote> = {}): Quote {
  return {
    id: 'q-1',
    quote_number: 'QT-000002',
    customer: { id: 'c-1', display_name: 'Acme Corp', email: 'ap@acme.test' },
    status: 'sent',
    issue_date: '2026-09-01',
    expiry_date: '2099-12-31',
    currency: 'INR',
    subtotal: '10000.00',
    discount_pct: '0.00',
    discount_amount: '0.00',
    tax_amount: '1800.00',
    total: '11800.00',
    items: [{ id: 'li-1', description: 'Implementation', quantity: '1', unit_price: '10000.00', tax_rate_pct: '18', amount: '10000.00', position: 0 }],
    public_url: 'https://app.example.test/quote/tok_abc',
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-01T10:00:00Z',
    ...overrides,
  } as unknown as Quote;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/quotes/q-1']}>
      <Routes>
        <Route path="/quotes/:id" element={<QuoteDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

const getQuote = () => vi.mocked(quoteService.getQuote);

describe('<QuoteDetailPage /> internal workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    role = 'admin';
  });

  it('admin approves a pending quote without sending it', async () => {
    getQuote().mockResolvedValueOnce(makeQuote({ status: 'pending_approval', public_url: undefined }));
    getQuote().mockResolvedValueOnce(makeQuote({ status: 'approved', public_url: undefined }));
    vi.mocked(quoteService.approveQuote).mockResolvedValue(makeQuote({ status: 'approved' }));
    renderPage();

    const approve = await screen.findByRole('button', { name: /approve quote/i });
    expect(screen.queryByText(/approve & send/i)).not.toBeInTheDocument();
    fireEvent.click(approve);

    await waitFor(() => expect(quoteService.approveQuote).toHaveBeenCalledWith('q-1'));
    expect(quoteService.sendQuote).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith('success', 'Quote approved. Send it to the customer when ready.');
    expect(await screen.findByRole('button', { name: /send to customer/i })).toBeInTheDocument();
  });

  it('finance sees pending approval as awaiting an admin', async () => {
    role = 'finance';
    getQuote().mockResolvedValue(makeQuote({ status: 'pending_approval', public_url: undefined }));
    renderPage();
    expect(await screen.findByText('Awaiting admin approval')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /approve quote/i })).not.toBeInTheDocument();
  });

  it('sends an approved quote to the customer', async () => {
    role = 'finance';
    getQuote().mockResolvedValue(makeQuote({ status: 'approved', public_url: undefined }));
    vi.mocked(quoteService.sendQuote).mockResolvedValue(makeQuote({ status: 'sent', email_sent: true }));
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /send to customer/i }));
    await waitFor(() => expect(quoteService.sendQuote).toHaveBeenCalledWith('q-1'));
    expect(showToast).toHaveBeenCalledWith('success', 'Quote sent');
  });

  it('a sent quote waits for the customer: staff get no plain Accept / Decline', async () => {
    role = 'finance';
    getQuote().mockResolvedValue(makeQuote({ status: 'sent' }));
    renderPage();
    expect(await screen.findByText('Awaiting customer response')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^accept quote$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^decline$/i })).not.toBeInTheDocument();
    // finance cannot override either
    expect(screen.queryByRole('button', { name: /admin override/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /customer view/i })).toBeInTheDocument();
  });

  it('admin override needs a reason and is clearly labelled', async () => {
    getQuote()
      .mockResolvedValueOnce(makeQuote({ status: 'viewed' }))
      .mockResolvedValueOnce(
        makeQuote({
          status: 'accepted',
          customer_decision: { outcome: 'accepted', actor_type: 'staff', title: 'Marked accepted by admin', actor_display: 'Admin User', name: 'Admin User', reason: 'Signed PDF received', at: '2026-09-02T09:00:00Z' },
        })
      );
    vi.mocked(quoteService.overrideAccept).mockResolvedValue(makeQuote({ status: 'accepted' }));
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Mark as Accepted (Admin Override)' }));
    const record = await screen.findByRole('button', { name: 'Record Acceptance' });
    expect(record).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/reason \/ evidence/i), { target: { value: 'Signed PDF received' } });
    expect(record).toBeEnabled();
    fireEvent.click(record);

    await waitFor(() => expect(quoteService.overrideAccept).toHaveBeenCalledWith('q-1', 'Signed PDF received'));
    expect(await screen.findByText('Marked accepted by admin')).toBeInTheDocument();
    expect(screen.getByText('Admin: Admin User')).toBeInTheDocument();
    expect(screen.queryByText(/by customer/i)).not.toBeInTheDocument();
    expect(screen.getByText('Reason: Signed PDF received')).toBeInTheDocument();
  });

  it('admin override decline sends the reason', async () => {
    getQuote().mockResolvedValue(makeQuote({ status: 'sent' }));
    vi.mocked(quoteService.overrideDecline).mockResolvedValue(makeQuote({ status: 'declined' }));
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Mark as Declined (Admin Override)' }));
    fireEvent.change(await screen.findByLabelText(/reason \/ evidence/i), { target: { value: 'Customer said no by phone' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record Decline' }));
    await waitFor(() => expect(quoteService.overrideDecline).toHaveBeenCalledWith('q-1', 'Customer said no by phone'));
  });

  it('shows that the customer accepted on their link', async () => {
    getQuote().mockResolvedValue(
      makeQuote({
        status: 'accepted',
        accepted_at: '2026-09-02T09:00:00Z',
        customer_decision: { outcome: 'accepted', actor_type: 'customer', title: 'Accepted by customer', actor_display: 'Priya Sharma (Acme Corp)', name: 'Priya Sharma', reason: null, at: '2026-09-02T09:00:00Z' },
      })
    );
    renderPage();
    expect(await screen.findByText('Accepted by customer')).toBeInTheDocument();
    expect(screen.getByText('Priya Sharma (Acme Corp) via quote link')).toBeInTheDocument();
    expect(screen.queryByText(/by admin/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Awaiting customer response')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /admin override/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /convert to invoice/i })).toBeInTheDocument();
  });

  it('shows that the customer declined on their link', async () => {
    getQuote().mockResolvedValue(
      makeQuote({
        status: 'declined',
        customer_decision: { outcome: 'declined', actor_type: 'customer', title: 'Declined by customer', actor_display: 'Acme Corp', name: null, reason: 'Over budget', at: '2026-09-02T09:00:00Z' },
      })
    );
    renderPage();
    expect(await screen.findByText('Declined by customer')).toBeInTheDocument();
    expect(screen.getByText('Reason: Over budget')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /convert to invoice/i })).not.toBeInTheDocument();
  });

  it.each([
    ['declined', 'staff', 'Marked declined by admin', 'Admin: Olivia Owner', 'Customer said no by phone'],
    ['accepted', 'customer', 'Accepted by customer', 'Priya Sharma (Acme Corp) via quote link', null],
    ['accepted', 'staff', 'Marked accepted by admin', 'Admin: Olivia Owner', 'Signed PDF received'],
    ['declined', 'customer', 'Declined by customer', 'Acme Corp via quote link', 'Over budget'],
  ] as const)('%s by %s reads "%s"', async (outcome, actorType, title, actorLine, reason) => {
    const actor = actorType === 'customer' ? (outcome === 'accepted' ? 'Priya Sharma (Acme Corp)' : 'Acme Corp') : 'Olivia Owner';
    getQuote().mockResolvedValue(
      makeQuote({
        status: outcome,
        customer_decision: { outcome, actor_type: actorType, title, actor_display: actor, name: actor, reason, at: '2026-09-02T09:00:00Z' },
      })
    );
    renderPage();
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(actorLine)).toBeInTheDocument();
    if (reason) expect(screen.getByText(`Reason: ${reason}`)).toBeInTheDocument();
  });
});

describe('<QuoteDetailPage /> pricing explanation (BUG-05)', () => {
  const explanation = JSON.stringify({
    catalog_base_price: '1200.00',
    price_book_adjustment: '-200.00',
    effective_unit_price: '1000.00',
    tier_explanation: 'Volume tier 1-10',
  });

  beforeEach(() => {
    vi.clearAllMocks();
    role = 'admin';
  });

  it('renders the stored JSON as readable pricing details, never the raw string', async () => {
    getQuote().mockResolvedValue(
      makeQuote({
        items: [{ id: 'li-1', description: 'Analytics Seat', quantity: '1', unit_price: '1000.00', tax_rate_pct: '18', amount: '1000.00', position: 0, pricing_explanation: explanation }],
      } as Partial<Quote>)
    );
    const { container } = renderPage();
    expect(await screen.findByText('Pricing details')).toBeInTheDocument();
    expect(screen.getByText('Catalog base price')).toBeInTheDocument();
    expect(screen.getByText('Volume tier 1-10')).toBeInTheDocument();
    expect(container.textContent).not.toContain(explanation);
    expect(container.textContent).not.toContain('catalog_base_price');
    expect(container.textContent).not.toContain('{"');
  });

  it('keeps a plain-text explanation as text', async () => {
    getQuote().mockResolvedValue(
      makeQuote({
        items: [{ id: 'li-1', description: 'Seat', quantity: '1', unit_price: '10.00', tax_rate_pct: '18', amount: '10.00', position: 0, pricing_explanation: 'Base Catalog Price' }],
      } as Partial<Quote>)
    );
    renderPage();
    expect(await screen.findByText('Base Catalog Price')).toBeInTheDocument();
  });
});

// NEW-01: amounts in the quote's own currency, never a hard-coded rupee.
describe('<QuoteDetailPage /> amounts in the quote currency (NEW-01)', () => {
  it('shows USD line, tax and total amounts with the dollar sign', async () => {
    getQuote().mockResolvedValue(makeQuote({
      currency: 'USD', subtotal: '1000.00', tax_amount: '180.00', total: '1180.00',
      items: [{ id: 'li-1', description: 'Implementation', quantity: '1', unit_price: '1000.00', tax_rate_pct: '18', amount: '1000.00', position: 0 }],
    } as unknown as Partial<Quote>));
    const { container } = renderPage();
    await screen.findAllByText('Implementation');
    const text = container.textContent ?? '';
    expect(text).not.toContain('₹');
    expect(text).toContain('$1,000.00');
    expect(text).toContain('$180.00');
    expect(text).toContain('$1,180.00');
  });

  it('shows AED amounts with the dirham code', async () => {
    getQuote().mockResolvedValue(makeQuote({ currency: 'AED', subtotal: '367.25', tax_amount: '66.11', total: '433.36' } as unknown as Partial<Quote>));
    const { container } = renderPage();
    await screen.findAllByText('Implementation');
    const text = container.textContent ?? '';
    expect(text).not.toContain('₹');
    expect(text).toMatch(/AED\s?433\.36/);
    expect(text).toMatch(/AED\s?66\.11/);
  });
});
