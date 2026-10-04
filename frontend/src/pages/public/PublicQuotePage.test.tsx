import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { PublicQuotePage } from './PublicQuotePage';
import { publicService } from '../../services/publicService';
import type { PublicQuoteFull } from '../../types/public';

const showToast = vi.fn();

vi.mock('../../services/publicService', () => ({
  publicService: {
    getQuote: vi.fn(),
    acceptQuote: vi.fn(),
    declineQuote: vi.fn(),
  },
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast }),
}));

const TOKEN = 'tok_abc123';

function makeQuote(overrides: Partial<PublicQuoteFull> = {}): PublicQuoteFull {
  return {
    quote_number: 'QT-000002',
    status: 'viewed',
    title: 'Website rollout',
    issue_date: '2026-09-01',
    expiry_date: '2099-12-31',
    currency: 'INR',
    subtotal: '10000.00',
    discount_pct: '10.00',
    discount_amount: '1000.00',
    tax_amount: '1620.00',
    total: '10620.00',
    items: [
      {
        id: 'li-1',
        description: 'Implementation services',
        quantity: '2',
        unit_price: '5000.00',
        tax_rate_pct: '18',
        amount: '10000.00',
        position: 0,
      },
    ],
    notes: 'Delivery in 15 working days.',
    terms: '1. Quote valid for 30 days.\n2. Payment terms: 30 days from invoice date.',
    sent_at: '2026-09-01T10:00:00Z',
    accepted_at: null,
    declined_at: null,
    organization: {
      name: 'Rooman Technologies',
      legal_name: null,
      email: 'billing@rooman.test',
      phone: null,
      website: null,
      address_line1: null,
      address_line2: null,
      city: 'Bengaluru',
      state: 'Karnataka',
      postal_code: null,
      country: 'IN',
      gstin: null,
      logo_url: null,
    },
    customer: {
      display_name: 'Acme Corp',
      company_name: null,
      email: 'ap@acme.test',
      billing_address_line1: null,
      billing_address_line2: null,
      billing_city: null,
      billing_state: null,
      billing_postal_code: null,
      billing_country: null,
    },
    ...overrides,
  } as unknown as PublicQuoteFull;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/quote/${TOKEN}`]}>
      <Routes>
        <Route path="/quote/:token" element={<PublicQuotePage />} />
      </Routes>
    </MemoryRouter>
  );
}

const getQuote = () => vi.mocked(publicService.getQuote);
const acceptQuote = () => vi.mocked(publicService.acceptQuote);
const declineQuote = () => vi.mocked(publicService.declineQuote);

describe('<PublicQuotePage /> customer quote experience', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a loading state first', () => {
    getQuote().mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading your quote…')).toBeInTheDocument();
  });

  it.each(['sent', 'viewed'] as const)('a %s quote is ready: details plus Accept and Decline', async (status) => {
    getQuote().mockResolvedValue(makeQuote({ status }));
    renderPage();
    expect(await screen.findByRole('button', { name: /accept quote/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /decline/i })).toBeInTheDocument();
    expect(screen.queryByText(/isn't ready yet/i)).not.toBeInTheDocument();
    expect(getQuote()).toHaveBeenCalledWith(TOKEN);
    // quote details
    expect(screen.getAllByText('QT-000002').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Rooman Technologies').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Acme Corp').length).toBeGreaterThan(0);
    expect(screen.getByText('Implementation services')).toBeInTheDocument();
    expect(screen.getByText(/Quote valid for 30 days/)).toBeInTheDocument();
    expect(screen.getByText(/Payment terms: 30 days/)).toBeInTheDocument();
  });

  it('requires the customer name before accepting', async () => {
    getQuote().mockResolvedValue(makeQuote());
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /accept quote/i }));
    expect(screen.getByText('Please enter your full name to accept this quote.')).toBeInTheDocument();
    expect(acceptQuote()).not.toHaveBeenCalled();
  });

  it('accepts with the customer token and name, then shows the accepted state', async () => {
    getQuote()
      .mockResolvedValueOnce(makeQuote())
      .mockResolvedValueOnce(makeQuote({ status: 'accepted', accepted_at: '2026-09-02T09:00:00Z' }));
    let resolveAccept: (v: { status: string }) => void = () => {};
    acceptQuote().mockReturnValue(new Promise((r) => (resolveAccept = r)));
    renderPage();

    fireEvent.change(await screen.findByLabelText('Your full name'), { target: { value: 'Priya Sharma' } });
    fireEvent.click(screen.getByRole('button', { name: /accept quote/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, accept' }));

    expect(acceptQuote()).toHaveBeenCalledWith(TOKEN, 'Priya Sharma');
    // while the request is in flight, the actions are locked against double submits
    await waitFor(() => expect(screen.getByRole('button', { name: /decline/i })).toBeDisabled());

    resolveAccept({ status: 'accepted' });
    expect(await screen.findByText('Quote accepted — thank you!')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /accept quote/i })).not.toBeInTheDocument();
    expect(acceptQuote()).toHaveBeenCalledTimes(1);
    expect(showToast).toHaveBeenCalledWith('success', 'Quote accepted', expect.stringContaining('Priya Sharma'));
  });

  it('declines with an optional reason, then shows the declined state', async () => {
    getQuote()
      .mockResolvedValueOnce(makeQuote())
      .mockResolvedValueOnce(makeQuote({ status: 'declined', declined_at: '2026-09-02T09:00:00Z' }));
    declineQuote().mockResolvedValue({ status: 'declined' });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /^decline$/i }));
    fireEvent.change(await screen.findByLabelText(/reason/i), { target: { value: 'Over budget' } });
    fireEvent.click(screen.getByRole('button', { name: 'Decline quote' }));

    await waitFor(() => expect(declineQuote()).toHaveBeenCalledWith(TOKEN, 'Over budget'));
    expect(await screen.findByText('Quote declined')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /accept quote/i })).not.toBeInTheDocument();
  });

  it('surfaces an error and reloads when the quote can no longer be accepted', async () => {
    getQuote()
      .mockResolvedValueOnce(makeQuote())
      .mockResolvedValueOnce(makeQuote({ status: 'expired' }));
    acceptQuote().mockRejectedValue({ code: 'INVALID_STATE', message: 'This quote can no longer be accepted.', status: 409 });
    renderPage();

    fireEvent.change(await screen.findByLabelText('Your full name'), { target: { value: 'Priya' } });
    fireEvent.click(screen.getByRole('button', { name: /accept quote/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, accept' }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith('error', 'Could not accept quote', 'This quote can no longer be accepted.')
    );
    expect(await screen.findByText('This quote has expired')).toBeInTheDocument();
  });

  it('shows an already-accepted quote without actions', async () => {
    getQuote().mockResolvedValue(makeQuote({ status: 'accepted', accepted_at: '2026-09-02T09:00:00Z' }));
    renderPage();
    expect(await screen.findByText('This quote has been accepted')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /accept quote/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /decline/i })).not.toBeInTheDocument();
  });

  it('shows a suspended merchant quote without Accept or Decline', async () => {
    getQuote().mockResolvedValue(
      makeQuote({ actions_unavailable_reason: "This merchant's account is temporarily unavailable." }),
    );
    renderPage();
    expect(await screen.findByText('Responses are temporarily unavailable')).toBeInTheDocument();
    expect(screen.getByText(/account is temporarily unavailable/)).toBeInTheDocument();
    expect(screen.getByText('Implementation services')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /accept quote/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /decline/i })).not.toBeInTheDocument();
  });

  it('shows an already-declined quote without actions', async () => {
    getQuote().mockResolvedValue(makeQuote({ status: 'declined', declined_at: '2026-09-02T09:00:00Z' }));
    renderPage();
    expect(await screen.findByText('This quote was declined')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /accept quote/i })).not.toBeInTheDocument();
  });

  it.each(['expired', 'viewed'] as const)('shows an expired quote (%s status) without actions', async (status) => {
    getQuote().mockResolvedValue(makeQuote({ status, expiry_date: '2020-01-01' }));
    renderPage();
    expect(await screen.findByText('This quote has expired')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /accept quote/i })).not.toBeInTheDocument();
  });

  it.each(['converted', 'invoiced', 'partially_invoiced'] as const)(
    'an accepted-and-%s quote never reads as "not ready yet"',
    async (status) => {
      getQuote().mockResolvedValue(makeQuote({ status: status as PublicQuoteFull['status'] }));
      renderPage();
      expect(await screen.findByText('Accepted and invoiced')).toBeInTheDocument();
      expect(screen.queryByText(/isn't ready yet/i)).not.toBeInTheDocument();
    }
  );

  it('shows "not ready yet" only for a quote that was never sent', async () => {
    getQuote().mockResolvedValue(makeQuote({ status: 'approved' }));
    renderPage();
    expect(await screen.findByText("This quote isn't ready yet")).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /accept quote/i })).not.toBeInTheDocument();
  });

  it('explains an invalid link', async () => {
    getQuote().mockRejectedValue({ code: 'ENTITY_NOT_FOUND', message: 'Not found', status: 404 });
    renderPage();
    expect(await screen.findByText("This quote link isn't valid")).toBeInTheDocument();
  });

  it('keeps Accept and Decline usable at phone width', async () => {
    window.innerWidth = 375;
    window.dispatchEvent(new Event('resize'));
    getQuote().mockResolvedValue(makeQuote());
    renderPage();
    const accept = await screen.findByRole('button', { name: /accept quote/i });
    const decline = screen.getByRole('button', { name: /decline/i });
    // both actions sit side by side in a two-column grid and the input spans the full width on mobile
    expect(accept.parentElement).toHaveClass('grid', 'grid-cols-2');
    expect(decline.parentElement).toBe(accept.parentElement);
    expect(accept.closest('.w-full')).not.toBeNull();
  });
});
