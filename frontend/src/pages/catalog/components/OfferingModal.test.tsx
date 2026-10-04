import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { OfferingModal } from './OfferingModal';
import type { OfferingOut } from '../../../types/catalog_cpq';

function makeOffering(): OfferingOut {
  return {
    id: 'off-1',
    name: 'Cloud Compute',
    sku: 'CLOUD-1',
    description: null,
    type: 'service',
    category: 'Infrastructure',
    unit: 'unit',
    currency: 'INR',
    pricing_model: 'tiered',
    base_price: '10.00',
    tax_rate_pct: '18.00',
    hsn_sac_code: null,
    billing_frequency: 'monthly',
    is_active: true,
    pricing_tiers: [
      { min_qty: 0, max_qty: 100, unit_price: 10 },
      { min_qty: 101, max_qty: null, unit_price: 8 },
    ],
    bundle_components: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

describe('OfferingModal pricing tiers', () => {
  it('does not mutate the edited offering when tier edits are cancelled', () => {
    const offering = makeOffering();
    const snapshot = JSON.parse(JSON.stringify(offering.pricing_tiers));
    const onClose = vi.fn();
    render(<OfferingModal isOpen onClose={onClose} onSave={vi.fn()} initialData={offering} />);

    const rates = screen.getAllByPlaceholderText('Rate') as HTMLInputElement[];
    fireEvent.change(rates[0], { target: { value: '99' } });
    fireEvent.change(screen.getAllByPlaceholderText('Min Qty')[1], { target: { value: '150' } });
    fireEvent.change(screen.getAllByPlaceholderText('Max (blank=∞)')[0], { target: { value: '149' } });
    expect(rates[0].value).toBe('99');

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalled();
    expect(offering.pricing_tiers).toEqual(snapshot);
  });

  it('saves the edited tiers without touching the original object', async () => {
    const offering = makeOffering();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<OfferingModal isOpen onClose={vi.fn()} onSave={onSave} initialData={offering} />);

    fireEvent.change(screen.getAllByPlaceholderText('Rate')[1], { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: 'Update Offering' }));

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][0].pricing_tiers).toEqual([
      { min_qty: 0, max_qty: 100, unit_price: 10 },
      { min_qty: 101, max_qty: null, unit_price: 7 },
    ]);
    expect(offering.pricing_tiers![1].unit_price).toBe(8);
  });
});
