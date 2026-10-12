import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PlanModal } from './PlanModal';
import type { PlanPricingItem } from '../../../types/plans_pricing';

describe('<PlanModal /> Currency Display and Dynamic Formatting', () => {
  it('updates base rate label and live preview currency symbols when currency is changed to USD', () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(<PlanModal isOpen={true} onClose={onClose} onSave={onSave} />);

    // Initial state: Currency is INR (₹)
    expect(screen.getByText('Catalog Base Rate (₹)')).toBeInTheDocument();

    const numberInputs = document.body.querySelectorAll('input[type="number"]');
    const basePriceInput = numberInputs[0] as HTMLInputElement;
    const previewQtyInput = numberInputs[numberInputs.length - 1] as HTMLInputElement;

    // Set base rate to 5500 and simulate quantity to 5
    fireEvent.change(basePriceInput, { target: { value: '5500' } });
    fireEvent.change(previewQtyInput, { target: { value: '5' } });

    // Live preview in INR
    expect(screen.getByText('₹27,500')).toBeInTheDocument();
    expect(screen.getByText('₹4,950')).toBeInTheDocument();
    expect(screen.getByText('₹32,450')).toBeInTheDocument();
    expect(screen.getByText(/5 units × ₹5,500/i)).toBeInTheDocument();

    // Change currency dropdown to USD ($)
    const currencySelect = screen.getByDisplayValue('INR (₹)');
    fireEvent.change(currencySelect, { target: { value: 'USD' } });

    // 1. Base rate label updates dynamically to ($)
    expect(screen.getByText('Catalog Base Rate ($)')).toBeInTheDocument();
    expect(screen.queryByText('Catalog Base Rate (₹)')).not.toBeInTheDocument();

    // 2. Base price input retains the exact entered numeric value (no FX conversion)
    expect(basePriceInput.value).toBe('5500');

    // 3. Live pricing preview immediately updates to $
    expect(screen.getByText('$27,500')).toBeInTheDocument();
    expect(screen.getByText('$4,950')).toBeInTheDocument();
    expect(screen.getByText('$32,450')).toBeInTheDocument();
    expect(screen.getByText(/5 units × \$5,500/i)).toBeInTheDocument();

    // No lingering ₹ symbols in the live preview
    expect(screen.queryByText('₹27,500')).not.toBeInTheDocument();
  });

  it('updates dynamically for EUR (€) and GBP (£)', () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(<PlanModal isOpen={true} onClose={onClose} onSave={onSave} />);

    const currencySelect = screen.getByDisplayValue('INR (₹)');

    // Switch to EUR
    fireEvent.change(currencySelect, { target: { value: 'EUR' } });
    expect(screen.getByText('Catalog Base Rate (€)')).toBeInTheDocument();

    // Switch to GBP
    fireEvent.change(currencySelect, { target: { value: 'GBP' } });
    expect(screen.getByText('Catalog Base Rate (£)')).toBeInTheDocument();
  });

  it('initializes with the correct currency when editing an existing USD plan', () => {
    const existingPlan: PlanPricingItem = {
      id: 'plan-usd-1',
      name: 'Pro Global Plan',
      code: 'PRO-USD',
      sku: 'PRO-USD',
      description: 'Global plan billed in USD',
      category: 'Subscriptions',
      unit: 'seat',
      currency: 'USD',
      pricing_model: 'per_unit',
      base_price: 5500,
      tax_rate_pct: 18,
      billing_frequency: 'monthly',
      status: 'active',
      is_active: true,
      pricing_tiers: [],
      created_at: '2026-09-01T00:00:00Z',
      updated_at: '2026-09-01T00:00:00Z',
    };

    render(<PlanModal isOpen={true} onClose={vi.fn()} onSave={vi.fn()} initialData={existingPlan} />);

    // Currency dropdown is selected as USD
    expect(screen.getByDisplayValue('USD ($)')).toBeInTheDocument();

    // Base rate label shows ($)
    expect(screen.getByText('Catalog Base Rate ($)')).toBeInTheDocument();

    // Live preview values show $ (basePrice 5500 * default qty 5 = 27,500)
    expect(screen.getByText('$27,500')).toBeInTheDocument();
    expect(screen.getByText('$4,950')).toBeInTheDocument();
    expect(screen.getByText('$32,450')).toBeInTheDocument();
    expect(screen.getByText(/5 units × \$5,500/i)).toBeInTheDocument();
  });

  it('persists selected currency in onSave payload', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(<PlanModal isOpen={true} onClose={onClose} onSave={onSave} />);

    // Fill required plan name
    const nameInput = screen.getByPlaceholderText(/e\.g\. Enterprise Cloud Annual Plan/i);
    await user.type(nameInput, 'Enterprise US Plan');

    // Select USD currency
    const currencySelect = screen.getByDisplayValue('INR (₹)');
    fireEvent.change(currencySelect, { target: { value: 'USD' } });

    // Submit form
    const submitBtn = screen.getByRole('button', { name: /Create Plan/i });
    await user.click(submitBtn);

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Enterprise US Plan',
        currency: 'USD',
      }),
    );
  });
});

describe('<PlanModal /> labels (BUG-22)', () => {
  it('associates every field, including tier and preview number inputs, with a label', () => {
    const tieredPlan = {
      id: 'plan-t', name: 'Tiered', code: 'TIER', sku: 'TIER', description: '', category: 'Subscriptions', unit: 'seat',
      currency: 'INR', pricing_model: 'tiered', base_price: 100, tax_rate_pct: 18, billing_frequency: 'monthly',
      status: 'active', is_active: true, pricing_tiers: [{ min_qty: 1, max_qty: 10, unit_price: 90 }],
      created_at: '', updated_at: '',
    } as unknown as PlanPricingItem;
    render(<PlanModal isOpen={true} onClose={vi.fn()} onSave={vi.fn()} initialData={tieredPlan} />);
    for (const label of [/^Plan Name/, /^Plan Code/, /^Description/, /^Category/, /^Status/, /^Billing Frequency/, /^Unit of Measure/, /^Currency/, /Base Rate|Flat Rate/, /^Applicable GST/]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getByLabelText('Tier 1 minimum quantity')).toHaveValue(1);
    expect(screen.getByLabelText('Tier 1 maximum quantity')).toHaveValue(10);
    expect(screen.getByLabelText('Tier 1 rate per unit')).toHaveValue(90);
    expect(screen.getByLabelText('Simulate quantity')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove tier 1' })).toBeInTheDocument();
  });
});

