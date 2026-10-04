import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PricingSimulatorPage } from './PricingSimulatorPage';
import { planPricingService } from '../../services/planPricingService';
import { customerService } from '../../services/customerService';
import { catalogCpqService } from '../../services/catalogCpqService';

vi.mock('../../services/planPricingService', () => ({
  planPricingService: { listPlans: vi.fn(), simulatePricing: vi.fn() },
}));
vi.mock('../../services/customerService', () => ({ customerService: { list: vi.fn() } }));
vi.mock('../../services/catalogCpqService', () => ({ catalogCpqService: { listPriceBooks: vi.fn() } }));

describe('<PricingSimulatorPage /> overflow with huge values', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(customerService).list.mockResolvedValue({ items: [], total: 0 } as any);
    vi.mocked(catalogCpqService).listPriceBooks.mockResolvedValue({ items: [], total: 0 } as any);
    vi.mocked(planPricingService).listPlans.mockResolvedValue({
      items: [
        {
          id: 'off-1', name: 'Seats', pricing_model: 'tiered', base_price: 1, unit: 'seat', currency: 'INR',
          pricing_tiers: [{ min_qty: 1, max_qty: null, unit_price: 999999999999.99 }],
        },
      ],
      total: 1,
    } as any);
    vi.mocked(planPricingService).simulatePricing.mockResolvedValue({
      offering_name: 'A very long offering name '.repeat(6),
      offering_sku: 'SKU-' + 'X'.repeat(80),
      pricing_model: 'tiered',
      quantity: '1000000',
      effective_unit_price: '999999999999.99',
      subtotal: '999999999999999999.99',
      discount_pct: '0',
      discount_amount: '0.00',
      tax_rate_pct: '18',
      tax_amount: '0.00',
      total_amount: '999999999999999999.99',
      explanation: { catalog_base_price: '1.00', subtotal_pre_discount: '999999999999999999.99' },
    } as any);
  });

  it('wraps tier rows and the summary header, with no NaN or exponent text', async () => {
    render(
      <MemoryRouter>
        <PricingSimulatorPage />
      </MemoryRouter>
    );
    const tierLabel = await screen.findByText(/Tier \[1/);
    expect(tierLabel.className).toContain('min-w-0');
    expect(tierLabel.className).toContain('break-all');
    const tierPrice = tierLabel.nextElementSibling as HTMLElement;
    expect(tierPrice.className).toContain('break-all');
    expect(tierPrice.textContent).toContain('9,99,99,99,99,999.99');
    expect(tierLabel.parentElement!.className).toContain('tabular-nums');

    const name = await screen.findByText(/A very long offering name/);
    expect(name.parentElement!.className).toContain('min-w-0');
    expect(screen.getByText(/Tiered Model/i).className).toContain('shrink-0');

    const total = await screen.findByTestId('simulator-final-total');
    expect(total.className).toContain('break-all');
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\de\+\d/);
  });
});
