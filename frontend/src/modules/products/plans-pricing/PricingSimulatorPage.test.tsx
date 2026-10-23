import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import {
  PricingSimulatorPage,
  MAX_SIMULATOR_QUANTITY,
  clampSimulatorQuantity,
} from './PricingSimulatorPage';
import { planPricingService } from '../../../services/planPricingService';
import { customerService } from '../../../services/customerService';
import { catalogCpqService } from '../../../services/catalogCpqService';

vi.mock('../../../services/planPricingService', () => ({
  planPricingService: {
    listPlans: vi.fn(),
    simulatePricing: vi.fn(),
  },
}));

vi.mock('../../../services/customerService', () => ({
  customerService: { list: vi.fn() },
}));

vi.mock('../../../services/catalogCpqService', () => ({
  catalogCpqService: { listPriceBooks: vi.fn() },
}));

const mockedPricing = vi.mocked(planPricingService);

function simulation(quantity: number, total: string) {
  return {
    offering_name: 'Seats',
    offering_sku: 'SEATS',
    pricing_model: 'per_unit',
    quantity: String(quantity),
    effective_unit_price: '1.00',
    subtotal: total,
    discount_pct: '0',
    discount_amount: '0.00',
    tax_rate_pct: '18',
    tax_amount: '0.00',
    total_amount: total,
    explanation: { catalog_base_price: '1.00', subtotal_pre_discount: total },
  } as any;
}

describe('clampSimulatorQuantity', () => {
  it('clamps to 1..1,000,000 and flags over-limit values', () => {
    expect(clampSimulatorQuantity('0')).toEqual({ value: 1, error: null });
    expect(clampSimulatorQuantity('abc')).toEqual({ value: 1, error: null });
    expect(clampSimulatorQuantity('250')).toEqual({ value: 250, error: null });
    expect(clampSimulatorQuantity(String(MAX_SIMULATOR_QUANTITY))).toEqual({ value: MAX_SIMULATOR_QUANTITY, error: null });
    const over = clampSimulatorQuantity('187654446786545');
    expect(over.value).toBe(MAX_SIMULATOR_QUANTITY);
    expect(over.error).toMatch(/cannot exceed 10,00,000/);
  });
});

describe('<PricingSimulatorPage /> quantity bound', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // vite.config sets restoreMocks, so implementations are (re)installed per test.
    vi.mocked(customerService).list.mockResolvedValue({ items: [], total: 0 } as any);
    vi.mocked(catalogCpqService).listPriceBooks.mockResolvedValue({ items: [], total: 0 } as any);
    mockedPricing.listPlans.mockResolvedValue({
      items: [{ id: 'off-1', name: 'Seats', pricing_model: 'per_unit', base_price: 1, unit: 'seat', pricing_tiers: [] }],
      total: 1,
    } as any);
    mockedPricing.simulatePricing.mockImplementation(async (body: any) =>
      simulation(body.quantity, String(body.quantity))
    );
  });

  it('clamps an absurd quantity to 1,000,000, shows a message and never sends more to the API', async () => {
    render(
      <MemoryRouter>
        <PricingSimulatorPage />
      </MemoryRouter>
    );
    const input = (await screen.findByLabelText('Quantity')) as HTMLInputElement;
    expect(input.max).toBe(String(MAX_SIMULATOR_QUANTITY));

    fireEvent.change(input, { target: { value: '187654446786545' } });

    expect(input.value).toBe(String(MAX_SIMULATOR_QUANTITY));
    expect(screen.getByRole('alert')).toHaveTextContent(/cannot exceed/i);
    await waitFor(() =>
      expect(mockedPricing.simulatePricing).toHaveBeenLastCalledWith(
        expect.objectContaining({ quantity: MAX_SIMULATOR_QUANTITY })
      )
    );
    for (const call of mockedPricing.simulatePricing.mock.calls) {
      expect((call[0] as any).quantity).toBeLessThanOrEqual(MAX_SIMULATOR_QUANTITY);
    }
    // Totals wrap inside their card instead of overflowing it.
    const total = await screen.findByTestId('simulator-final-total');
    expect(total.className).toContain('break-all');
  });
});

describe('<PricingSimulatorPage /> currency', () => {
  const CASES: Array<[string, string]> = [
    ['INR', '₹'],
    ['USD', '$'],
    ['EUR', '€'],
    ['GBP', '£'],
    ['AED', 'AED'],
    ['SGD', 'S$'],
    ['AUD', 'A$'],
    ['CAD', 'C$'],
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(customerService).list.mockResolvedValue({ items: [], total: 0 } as any);
    vi.mocked(catalogCpqService).listPriceBooks.mockResolvedValue({ items: [], total: 0 } as any);
  });

  it.each(CASES)('%s plan: every amount shows %s and the plan values unchanged (no FX)', async (currency, symbol) => {
    mockedPricing.listPlans.mockResolvedValue({
      items: [{
        id: 'off-1', name: 'Seats', pricing_model: 'per_unit', base_price: 49, unit: 'seat', currency,
        pricing_tiers: [{ min_qty: 1, max_qty: null, unit_price: 49 }],
      }],
      total: 1,
    } as any);
    mockedPricing.simulatePricing.mockResolvedValue({
      offering_name: 'Seats',
      offering_sku: 'SEATS',
      pricing_model: 'per_unit',
      quantity: '10',
      effective_unit_price: '49.00',
      subtotal: '490.00',
      discount_pct: '10',
      discount_amount: '49.00',
      tax_rate_pct: '18',
      tax_amount: '79.38',
      total_amount: '520.38',
      explanation: { catalog_base_price: '49.00', subtotal_pre_discount: '490.00' },
    } as any);

    const { container } = render(
      <MemoryRouter>
        <PricingSimulatorPage />
      </MemoryRouter>
    );
    const total = await screen.findByTestId('simulator-final-total');
    expect(total).toHaveTextContent(`${symbol}520.38`);

    const text = container.textContent || '';
    // Dropdown label, tier price, unit rate, subtotal, discount, tax and total all use the plan currency.
    expect(text).toContain(`Seats (PER_UNIT) - ${symbol}49/seat`);
    expect(text).toContain(`${symbol}49/unit`);
    expect(text).toContain(`${symbol}49`);
    expect(text).toContain(`${symbol}490`);
    expect(text).toContain(`-${symbol}49`);
    expect(text).toContain(`+${symbol}79.38`);
    expect(text).toContain(`${symbol}520.38`);
    if (currency !== 'INR') expect(text).not.toContain('₹');
  });
});
