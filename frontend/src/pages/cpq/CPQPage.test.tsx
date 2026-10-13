import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CPQPage } from './CPQPage';
import { catalogCpqService } from '../../services/catalogCpqService';
import { customerService } from '../../services/customerService';
import { dashboardSummaryService } from '../../services/dashboardSummaryService';

vi.mock('../../services/catalogCpqService', () => ({
  catalogCpqService: {
    listDeals: vi.fn(),
    listOfferings: vi.fn(),
    listPriceBooks: vi.fn(),
    simulatePricing: vi.fn(),
    createDeal: vi.fn(),
  },
}));

vi.mock('../../services/dashboardSummaryService', () => ({
  dashboardSummaryService: {
    deals: vi.fn(),
  },
}));

vi.mock('../../services/customerService', () => ({
  customerService: { list: vi.fn(), create: vi.fn() },
}));

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ hasRole: () => true, user: { id: 'u-1' } }),
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 100 });

function setup() {
  vi.mocked(catalogCpqService.listDeals).mockResolvedValue(
    page([
      { id: 'd-1', deal_number: 'DL-000001', title: 'Dubai rollout', customer_name: 'Gulf LLC', customer_number: 'CUS-1', status: 'approved', currency: 'AED', total: '433.36' },
      { id: 'd-2', deal_number: 'DL-000002', title: 'US pilot', customer_name: 'Acme Inc', customer_number: 'CUS-2', status: 'approved', currency: 'USD', total: '1180.00' },
    ]) as never,
  );
  vi.mocked(catalogCpqService.listOfferings).mockResolvedValue(
    page([
      { id: 'o-aed', name: 'Gulf Support', sku: 'GS-1', type: 'service', base_price: '367.25', currency: 'AED', is_active: true },
      { id: 'o-usd', name: 'US Licence', sku: 'US-1', type: 'license', base_price: '1000.00', currency: 'USD', is_active: true },
      { id: 'o-inr', name: 'India Setup', sku: 'IN-1', type: 'service', base_price: '1234.50', currency: 'INR', is_active: true },
    ]) as never,
  );
  vi.mocked(dashboardSummaryService.deals).mockResolvedValue(
    { total_count: 2, groups: { pending: 0, approved: 2, converted: 0 } } as never,
  );
  vi.mocked(catalogCpqService.listPriceBooks).mockResolvedValue(page([]) as never);
  vi.mocked(customerService.list).mockResolvedValue(
    page([{ id: 'c-1', display_name: 'Gulf LLC', customer_number: 'CUS-1', currency: 'AED' }]) as never,
  );
}

describe('<CPQPage /> amounts in each record currency (NEW-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setup();
  });

  it('shows each deal total in the deal currency', async () => {
    render(<MemoryRouter><CPQPage /></MemoryRouter>);
    const aedRow = (await screen.findByText('Dubai rollout')).closest('tr')!;
    expect(within(aedRow).getByText(/AED\s*433\.36/)).toBeInTheDocument();
    const usdRow = screen.getByText('US pilot').closest('tr')!;
    expect(within(usdRow).getByText('$1,180.00')).toBeInTheDocument();
    expect(aedRow.textContent).not.toContain('₹');
    expect(usdRow.textContent).not.toContain('₹');
  });

  it('shows each offering card price in the offering currency', async () => {
    vi.mocked(catalogCpqService.listDeals).mockResolvedValue(page([]) as never);
    render(<MemoryRouter><CPQPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: /Start New Deal/ }));

    fireEvent.change(screen.getByPlaceholderText('Type to search or write customer name...'), {
      target: { value: 'Gulf' },
    });
    fireEvent.click(await screen.findByText(/Gulf LLC/, {}, { timeout: 2000 }));
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }));

    const card = (name: string) => screen.getByText(name).parentElement!;
    await waitFor(() => expect(screen.getByText('Gulf Support')).toBeInTheDocument());
    expect(card('Gulf Support').textContent).toMatch(/AED\s*367\.25/);
    expect(card('US Licence').textContent).toContain('$1,000.00');
    expect(card('India Setup').textContent).toContain('₹1,234.50');
    expect(card('Gulf Support').textContent).not.toContain('₹');
    expect(card('US Licence').textContent).not.toContain('₹');
  });
});
