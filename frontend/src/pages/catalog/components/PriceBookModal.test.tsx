import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PriceBookModal } from './PriceBookModal';
import type { OfferingOut, PriceBookOut } from '../../../types/catalog_cpq';

const offer = (id: string, name: string, base_price: string, currency: string) =>
  ({ id, name, sku: id.toUpperCase(), base_price, currency, type: 'service', is_active: true }) as OfferingOut;

describe('PriceBookModal offering picker (BUG-10)', () => {
  it('shows each offering base price in the offering currency', () => {
    const offerings = [
      offer('o-aed', 'Gulf Support', '367.25', 'AED'),
      offer('o-usd', 'US Licence', '1000.00', 'USD'),
      offer('o-inr', 'India Setup', '1234.50', 'INR'),
    ];
    const book = {
      id: 'pb-1',
      name: 'Gulf book',
      description: null,
      currency: 'AED',
      customer_segment: 'Enterprise',
      is_default: false,
      status: 'active',
      effective_from: null,
      effective_until: null,
      entries_count: 1,
      entries: [{ offering_id: 'o-aed', custom_price: null, discount_pct: '10' }],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    } as unknown as PriceBookOut;
    render(<PriceBookModal isOpen onClose={vi.fn()} onSave={vi.fn()} initialData={book} offerings={offerings} />);

    const option = (name: string) => screen.getByRole('option', { name: new RegExp(name) }).textContent ?? '';
    expect(option('Gulf Support')).toMatch(/Base: AED\s?367\.25/);
    expect(option('US Licence')).toContain('Base: $1,000.00');
    expect(option('India Setup')).toContain('Base: ₹1,234.50');
    expect(option('Gulf Support')).not.toContain('₹');
    expect(option('US Licence')).not.toContain('₹');
  });
});
