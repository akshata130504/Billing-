import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { QuoteFormPage } from './QuoteFormPage';
import { addDays, todayIso } from '../../utils/format';
import { catalogCpqService } from '../../services/catalogCpqService';
import { planPricingService } from '../../services/planPricingService';
import { quoteService } from '../../services/quoteService';
import type { OfferingOut } from '../../types/catalog_cpq';

const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }));

vi.mock('../../services/catalogCpqService', () => ({
  catalogCpqService: {
    listOfferings: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    getOffering: vi.fn(),
  },
}));

vi.mock('../../services/planPricingService', () => ({
  planPricingService: {
    simulatePricing: vi.fn(),
  },
}));

vi.mock('../../services/customerService', () => ({
  customerService: {
    list: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  },
}));

vi.mock('../../services/quoteService', () => ({
  quoteService: {
    getQuote: vi.fn(),
    createQuote: vi.fn(),
    updateQuote: vi.fn(),
    sendQuote: vi.fn(),
    getSupplyPreview: vi.fn(),
  },
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast }),
}));

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe('<QuoteFormPage /> Quote Validity and Terms & Conditions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes with default 30-day validity and matching terms', async () => {
    renderWithProviders(<QuoteFormPage />);

    await waitFor(() => {
      expect(screen.getByText('Line Items & Offerings')).toBeInTheDocument();
    });

    const termsTextarea = screen.getByPlaceholderText('Standard payment terms, warranty and SLA...') as HTMLTextAreaElement;
    expect(termsTextarea.value).toContain('Quote valid for 30 days.');
    expect(termsTextarea.value).toContain('Payment terms: 30 days from invoice date.');
    expect(termsTextarea.value).toContain('Taxes as applicable per Indian GST.');

    // Check default 30d preset is selected/highlighted
    const btn30 = screen.getByRole('button', { name: '30d' });
    expect(btn30.className).toContain('bg-indigo-600');
  });

  it('updates terms and expiry date dynamically when selecting 15-day validity', async () => {
    renderWithProviders(<QuoteFormPage />);

    await waitFor(() => {
      expect(screen.getByText('Line Items & Offerings')).toBeInTheDocument();
    });

    const btn15 = screen.getByRole('button', { name: '15d' });
    fireEvent.click(btn15);

    const termsTextarea = screen.getByPlaceholderText('Standard payment terms, warranty and SLA...') as HTMLTextAreaElement;
    expect(termsTextarea.value).toContain('Quote valid for 15 days.');
    expect(termsTextarea.value).not.toContain('Quote valid for 30 days.');
    expect(termsTextarea.value).toContain('Payment terms: 30 days from invoice date.');

    const dateInputs = document.querySelectorAll('input[type="date"]');
    const expiryInput = dateInputs[1] as HTMLInputElement;
    const today = todayIso();
    expect(expiryInput.value).toBe(addDays(today, 15));
  });

  it('updates terms and expiry date dynamically when selecting 60-day validity', async () => {
    renderWithProviders(<QuoteFormPage />);

    await waitFor(() => {
      expect(screen.getByText('Line Items & Offerings')).toBeInTheDocument();
    });

    const btn60 = screen.getByRole('button', { name: '60d' });
    fireEvent.click(btn60);

    const termsTextarea = screen.getByPlaceholderText('Standard payment terms, warranty and SLA...') as HTMLTextAreaElement;
    expect(termsTextarea.value).toContain('Quote valid for 60 days.');
    expect(termsTextarea.value).not.toContain('Quote valid for 30 days.');
    expect(termsTextarea.value).toContain('Payment terms: 30 days from invoice date.');

    const dateInputs = document.querySelectorAll('input[type="date"]');
    const expiryInput = dateInputs[1] as HTMLInputElement;
    const today = todayIso();
    expect(expiryInput.value).toBe(addDays(today, 60));
  });

  it('updates terms and expiry date dynamically when selecting 90-day validity', async () => {
    renderWithProviders(<QuoteFormPage />);

    await waitFor(() => {
      expect(screen.getByText('Line Items & Offerings')).toBeInTheDocument();
    });

    const btn90 = screen.getByRole('button', { name: '90d' });
    fireEvent.click(btn90);

    const termsTextarea = screen.getByPlaceholderText('Standard payment terms, warranty and SLA...') as HTMLTextAreaElement;
    expect(termsTextarea.value).toContain('Quote valid for 90 days.');
    expect(termsTextarea.value).not.toContain('Quote valid for 30 days.');
    expect(termsTextarea.value).toContain('Payment terms: 30 days from invoice date.');

    const dateInputs = document.querySelectorAll('input[type="date"]');
    const expiryInput = dateInputs[1] as HTMLInputElement;
    const today = todayIso();
    expect(expiryInput.value).toBe(addDays(today, 90));
  });

  it('updates terms and expiry date dynamically when selecting 7-day validity', async () => {
    renderWithProviders(<QuoteFormPage />);

    await waitFor(() => {
      expect(screen.getByText('Line Items & Offerings')).toBeInTheDocument();
    });

    const btn7 = screen.getByRole('button', { name: '7d' });
    fireEvent.click(btn7);

    const termsTextarea = screen.getByPlaceholderText('Standard payment terms, warranty and SLA...') as HTMLTextAreaElement;
    expect(termsTextarea.value).toContain('Quote valid for 7 days.');
    expect(termsTextarea.value).not.toContain('Quote valid for 30 days.');
    expect(termsTextarea.value).toContain('Payment terms: 30 days from invoice date.');

    const dateInputs = document.querySelectorAll('input[type="date"]');
    const expiryInput = dateInputs[1] as HTMLInputElement;
    const today = todayIso();
    expect(expiryInput.value).toBe(addDays(today, 7));
  });

  it('updates terms when date input is modified directly', async () => {
    renderWithProviders(<QuoteFormPage />);

    await waitFor(() => {
      expect(screen.getByText('Line Items & Offerings')).toBeInTheDocument();
    });

    const dateInputs = document.querySelectorAll('input[type="date"]');
    const issueInput = dateInputs[0] as HTMLInputElement;
    const expiryInput = dateInputs[1] as HTMLInputElement;

    // Set issue to 2026-09-01 and expiry to 2026-09-16 (15 days)
    fireEvent.change(issueInput, { target: { value: '2026-09-01' } });
    fireEvent.change(expiryInput, { target: { value: '2026-09-16' } });

    const termsTextarea = screen.getByPlaceholderText('Standard payment terms, warranty and SLA...') as HTMLTextAreaElement;
    expect(termsTextarea.value).toContain('Quote valid for 15 days.');
    expect(termsTextarea.value).not.toContain('Quote valid for 30 days.');
  });
});

// --- Archived offerings ------------------------------------------------------------------------------

function offering(over: Partial<OfferingOut>): OfferingOut {
  return {
    id: 'o-x',
    name: 'Offering',
    sku: 'SKU',
    description: null,
    type: 'product',
    category: null,
    unit: 'unit',
    currency: 'INR',
    pricing_model: 'per_unit',
    base_price: '100.00',
    tax_rate_pct: '18.00',
    hsn_sac_code: null,
    billing_frequency: 'one_time',
    is_active: true,
    pricing_tiers: null,
    bundle_components: [],
    created_at: '',
    updated_at: '',
    ...over,
  };
}

const ACTIVE_A = offering({ id: 'off-a', name: 'Alpha', sku: 'ALP', base_price: '111.00' });
const ACTIVE_B = offering({ id: 'off-b', name: 'Beta', sku: 'BET', base_price: '222.00' });
const ARCHIVED = offering({ id: 'off-archived', name: 'Old Plan', sku: 'OLD', is_active: false });

function storedQuote() {
  const today = todayIso();
  return {
    id: 'q1',
    customer: { id: 'c1', display_name: 'Acme' },
    title: 'Stored',
    issue_date: today,
    expiry_date: addDays(today, 30),
    currency: 'INR',
    discount_pct: '0',
    notes: '',
    terms: '',
    items: [
      { id: 'line-archived', offering_id: 'off-archived', description: 'Old Plan (OLD)', quantity: '2', unit_price: '100.00', tax_rate_pct: '18' },
      { id: 'line-active', offering_id: 'off-a', description: 'Alpha (ALP)', quantity: '1', unit_price: '111.00', tax_rate_pct: '18' },
    ],
  };
}

function renderRoute(path: string, state?: unknown) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[{ pathname: path, state }]}>
        <Routes>
          <Route path="/quotes/new" element={<QuoteFormPage />} />
          <Route path="/quotes/:id/edit" element={<QuoteFormPage />} />
          <Route path="/quotes/:id" element={<div>quote detail</div>} />
          <Route path="/quotes" element={<div>quote list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const offeringSelects = () =>
  screen.getAllByRole('combobox').filter((s) => within(s).queryByText('Custom Item')) as HTMLSelectElement[];
const quantityInputs = () => Array.from(document.querySelectorAll('input[type="number"][min="1"]')) as HTMLInputElement[];

type SavedItem = { id?: string; offering_id?: string; quantity?: number; unit_price?: number };
// updateQuote(id, payload) carries the payload second, createQuote(payload) first.
const savedItems = (mock: unknown, payloadArg = 1): SavedItem[] =>
  (mock as { mock: { calls: Array<Array<{ items: SavedItem[] }>> } }).mock.calls[0][payloadArg].items;

describe('<QuoteFormPage /> archived offerings', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(catalogCpqService.listOfferings).mockResolvedValue({
      items: [ACTIVE_A, ACTIVE_B],
      total: 2,
      page: 1,
      page_size: 100,
      total_pages: 1,
    } as never);
    vi.mocked(catalogCpqService.getOffering).mockResolvedValue(ARCHIVED);
    vi.mocked(quoteService.getQuote).mockResolvedValue(storedQuote() as never);
    vi.mocked(quoteService.updateQuote).mockResolvedValue({ id: 'q1' } as never);
    vi.mocked(quoteService.createQuote).mockResolvedValue({ id: 'q2' } as never);
  });

  it('asks only for active offerings and offers only those in the new-line picker', async () => {
    renderRoute('/quotes/new');
    await waitFor(() => expect(offeringSelects().length).toBe(1));
    expect(catalogCpqService.listOfferings).toHaveBeenCalledWith(expect.objectContaining({ is_active: true }));
    const options = within(offeringSelects()[0]).getAllByRole('option').map((o) => o.textContent);
    expect(options.some((t) => t?.includes('Alpha'))).toBe(true);
    expect(options.some((t) => t?.includes('Beta'))).toBe(true);
    expect(options.some((t) => t?.includes('Old Plan'))).toBe(false);
  });

  it('starts a new quote with the first active offering', async () => {
    renderRoute('/quotes/new');
    await waitFor(() => expect(offeringSelects().length).toBe(1));
    expect(offeringSelects()[0].value).toBe('off-a');
  });

  it('adds new lines using an active offering', async () => {
    renderRoute('/quotes/new');
    await waitFor(() => expect(offeringSelects().length).toBe(1));
    fireEvent.click(screen.getByRole('button', { name: /Add Item/i }));
    await waitFor(() => expect(offeringSelects().length).toBe(2));
    expect(offeringSelects()[1].value).toBe('off-a');
    expect(within(offeringSelects()[1]).queryByText(/Old Plan/)).toBeNull();
  });

  it('keeps an archived line of an existing quote visible as a disabled "(Archived)" option', async () => {
    renderRoute('/quotes/q1/edit');
    await waitFor(() => expect(offeringSelects().length).toBe(2));
    expect(catalogCpqService.getOffering).toHaveBeenCalledWith('off-archived');
    const archivedSelect = offeringSelects()[0];
    expect(archivedSelect.value).toBe('off-archived');
    const option = within(archivedSelect).getByRole('option', { name: /Old Plan.*\(Archived\)/ }) as HTMLOptionElement;
    expect(option.disabled).toBe(true);
    // The other (active) line and any new line must not offer the archived option.
    expect(within(offeringSelects()[1]).queryByText(/Old Plan/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Add Item/i }));
    await waitFor(() => expect(offeringSelects().length).toBe(3));
    expect(within(offeringSelects()[2]).queryByText(/Old Plan/)).toBeNull();
  });

  it('sends the stored id of retained lines when updating', async () => {
    renderRoute('/quotes/q1/edit');
    await waitFor(() => expect(offeringSelects().length).toBe(2));
    fireEvent.click(screen.getByRole('button', { name: /Save Draft/i }));
    await waitFor(() => expect(quoteService.updateQuote).toHaveBeenCalled());
    expect(vi.mocked(quoteService.updateQuote).mock.calls[0][0]).toBe('q1');
    const items = savedItems(quoteService.updateQuote);
    expect(items[0]).toEqual(expect.objectContaining({ id: 'line-archived', offering_id: 'off-archived' }));
    expect(items[1]).toEqual(expect.objectContaining({ id: 'line-active', offering_id: 'off-a' }));
  });

  it('does not send an id for a newly added line', async () => {
    renderRoute('/quotes/q1/edit');
    await waitFor(() => expect(offeringSelects().length).toBe(2));
    fireEvent.click(screen.getByRole('button', { name: /Add Item/i }));
    await waitFor(() => expect(offeringSelects().length).toBe(3));
    fireEvent.click(screen.getByRole('button', { name: /Save Draft/i }));
    await waitFor(() => expect(quoteService.updateQuote).toHaveBeenCalled());
    const items = savedItems(quoteService.updateQuote);
    expect(items).toHaveLength(3);
    expect(items[2].id).toBeUndefined();
  });

  it('never sends line ids when creating a quote', async () => {
    renderRoute('/quotes/new', {
      prefilledCustomer: 'c1',
      prefilledItem: { offering_id: 'off-a', name: 'Alpha', sku: 'ALP', quantity: 1, unit_price: 111, tax_rate_pct: 18 },
    });
    await waitFor(() => expect(offeringSelects().length).toBe(1));
    fireEvent.click(screen.getByRole('button', { name: /Save Draft/i }));
    await waitFor(() => expect(quoteService.createQuote).toHaveBeenCalled());
    const items = savedItems(quoteService.createQuote, 0);
    expect(items[0].offering_id).toBe('off-a');
    expect(items[0].id).toBeUndefined();
    expect(quoteService.updateQuote).not.toHaveBeenCalled();
  });

  it('keeps the stored price and does not simulate pricing when changing the quantity of an archived line', async () => {
    renderRoute('/quotes/q1/edit');
    await waitFor(() => expect(offeringSelects().length).toBe(2));
    fireEvent.change(quantityInputs()[0], { target: { value: '5' } });
    await waitFor(() => expect(quantityInputs()[0].value).toBe('5'));
    expect(planPricingService.simulatePricing).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /Save Draft/i }));
    await waitFor(() => expect(quoteService.updateQuote).toHaveBeenCalled());
    expect(savedItems(quoteService.updateQuote)[0]).toEqual(
      expect.objectContaining({ id: 'line-archived', quantity: 5, unit_price: 100 })
    );
  });

  it('drops the line id when the user switches an existing line to another offering', async () => {
    vi.mocked(planPricingService.simulatePricing).mockResolvedValue({ effective_unit_price: '222', explanation: {} } as never);
    renderRoute('/quotes/q1/edit');
    await waitFor(() => expect(offeringSelects().length).toBe(2));
    fireEvent.change(offeringSelects()[1], { target: { value: 'off-b' } });
    await waitFor(() => expect(offeringSelects()[1].value).toBe('off-b'));
    fireEvent.click(screen.getByRole('button', { name: /Save Draft/i }));
    await waitFor(() => expect(quoteService.updateQuote).toHaveBeenCalled());
    const items = savedItems(quoteService.updateQuote);
    expect(items[0].id).toBe('line-archived');
    expect(items[1]).toEqual(expect.objectContaining({ offering_id: 'off-b' }));
    expect(items[1].id).toBeUndefined();
  });

  it('shows the backend error instead of silently using the base price when an offering cannot be priced', async () => {
    vi.mocked(planPricingService.simulatePricing).mockRejectedValue({
      code: 'VALIDATION_ERROR',
      message: "Offering 'Beta' is archived and cannot be priced.",
      status: 422,
    });
    renderRoute('/quotes/new');
    await waitFor(() => expect(offeringSelects().length).toBe(1));
    fireEvent.change(offeringSelects()[0], { target: { value: 'off-b' } });
    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith('error', expect.any(String), expect.stringContaining('archived'))
    );
    // The line is unchanged: still Alpha, not Beta at its 222.00 base price.
    expect(offeringSelects()[0].value).toBe('off-a');
  });

  it('still falls back to the base price when pricing is merely unavailable (unchanged behaviour)', async () => {
    vi.mocked(planPricingService.simulatePricing).mockRejectedValue(new Error('network down'));
    renderRoute('/quotes/new');
    await waitFor(() => expect(offeringSelects().length).toBe(1));
    fireEvent.change(offeringSelects()[0], { target: { value: 'off-b' } });
    await waitFor(() => expect(offeringSelects()[0].value).toBe('off-b'));
    expect(showToast).not.toHaveBeenCalledWith('error', expect.any(String), expect.stringContaining('archived'));
  });
});

// BUG-08 / BUG-07: the totals preview follows the server's GST treatment instead of always
// showing CGST 9% + SGST 9%.
describe('<QuoteFormPage /> GST preview', () => {
  // storedQuote(): 2 x 100 + 1 x 111 = 311 at 18% -> 55.98 tax.
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(catalogCpqService.listOfferings).mockResolvedValue({
      items: [ACTIVE_A, ACTIVE_B],
      total: 2,
      page: 1,
      page_size: 100,
      total_pages: 1,
    } as never);
    vi.mocked(catalogCpqService.getOffering).mockResolvedValue(ARCHIVED);
    vi.mocked(quoteService.getQuote).mockResolvedValue(storedQuote() as never);
  });

  it('shows CGST + SGST for an intra-state supply', async () => {
    vi.mocked(quoteService.getSupplyPreview).mockResolvedValue({ supply_type: 'intra_state', charges_gst: true });
    renderRoute('/quotes/q1/edit');
    await waitFor(() => expect(screen.getByText('CGST')).toBeInTheDocument());
    expect(quoteService.getSupplyPreview).toHaveBeenCalledWith('c1');
    expect(screen.getByText('SGST')).toBeInTheDocument();
    expect(screen.queryByText('IGST')).not.toBeInTheDocument();
    expect(screen.getAllByText('₹28')).toHaveLength(2);
    expect(screen.getByText('₹367')).toBeInTheDocument();
  });

  it('shows IGST (not CGST/SGST) when the server resolves an inter-state supply', async () => {
    vi.mocked(quoteService.getSupplyPreview).mockResolvedValue({ supply_type: 'inter_state', charges_gst: true });
    renderRoute('/quotes/q1/edit');
    await waitFor(() => expect(screen.getByText('IGST')).toBeInTheDocument());
    expect(screen.queryByText('CGST')).not.toBeInTheDocument();
    expect(screen.queryByText('SGST')).not.toBeInTheDocument();
    expect(screen.getByText('₹56')).toBeInTheDocument();
  });

  it('charges no GST and explains why when the organization has no GSTIN', async () => {
    vi.mocked(quoteService.getSupplyPreview).mockResolvedValue({ supply_type: 'inter_state', charges_gst: false });
    renderRoute('/quotes/q1/edit');
    const notice = await screen.findByTestId('no-gst-notice');
    expect(notice).toHaveTextContent('no GSTIN');
    expect(within(notice).getByRole('link', { name: /Settings → Organization/ })).toHaveAttribute('href', '/settings/organization');
    expect(screen.queryByText('IGST')).not.toBeInTheDocument();
    expect(screen.getByText('₹0')).toBeInTheDocument();
    // Subtotal and total are equal: no tax added.
    expect(screen.getAllByText('₹311')).toHaveLength(2);
  });
});
