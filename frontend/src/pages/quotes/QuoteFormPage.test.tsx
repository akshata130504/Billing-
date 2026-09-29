import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { QuoteFormPage } from './QuoteFormPage';
import { addDays, todayIso } from '../../utils/format';

vi.mock('../../services/catalogCpqService', () => ({
  catalogCpqService: {
    listOfferings: vi.fn().mockResolvedValue({ items: [], total: 0 }),
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
  },
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
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
