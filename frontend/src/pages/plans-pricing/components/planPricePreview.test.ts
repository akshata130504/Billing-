import { describe, expect, it } from 'vitest';
import { calculatePricePreview, normalizeBrackets } from './planPricePreview';
import type { PlanPricingTier } from '../../../types/plans_pricing';

const TIERS: PlanPricingTier[] = [
  { min_qty: 1, max_qty: 10, unit_price: 100 },
  { min_qty: 11, max_qty: 50, unit_price: 80 },
];

const preview = (pricingModel: 'volume' | 'tiered', quantity: number, tiers = TIERS, basePrice = 500) =>
  calculatePricePreview({ pricingModel, basePrice, taxRatePct: 0, tiers, quantity });

describe('calculatePricePreview — volume', () => {
  it('prices an in-gap fractional quantity at the next bracket, not base price', () => {
    expect(preview('volume', 10.5).subtotal).toBeCloseTo(10.5 * 80);
  });

  it('includes the boundary quantity in the lower bracket', () => {
    expect(preview('volume', 10).subtotal).toBe(1000);
    expect(preview('volume', 11).subtotal).toBe(880);
    expect(preview('volume', 50).subtotal).toBe(4000);
  });

  it('uses the first bracket below the first min_qty', () => {
    const tiers = [{ min_qty: 5, max_qty: 10, unit_price: 100 }, { min_qty: 11, unit_price: 80 }];
    expect(preview('volume', 2, tiers).subtotal).toBe(200);
  });

  it('uses the last bracket above a closed final bracket', () => {
    const res = preview('volume', 60);
    expect(res.subtotal).toBe(60 * 80);
    expect(res.note).toContain('final bracket');
  });

  it('falls back to base price with no tiers', () => {
    expect(preview('volume', 3, []).subtotal).toBe(1500);
  });

  it('ignores tier input order', () => {
    expect(preview('volume', 20, [...TIERS].reverse()).subtotal).toBe(1600);
  });
});

describe('calculatePricePreview — tiered (graduated)', () => {
  it('prices gap units in the next bracket', () => {
    // 10 @ 100 + 0.5 @ 80
    expect(preview('tiered', 10.5).subtotal).toBeCloseTo(1040);
  });

  it('splits exactly at the boundary', () => {
    expect(preview('tiered', 10).subtotal).toBe(1000);
    expect(preview('tiered', 11).subtotal).toBe(1080);
  });

  it('prices units below the first min_qty in the first bracket', () => {
    const tiers = [{ min_qty: 5, max_qty: 10, unit_price: 100 }, { min_qty: 11, unit_price: 80 }];
    expect(preview('tiered', 3, tiers).subtotal).toBe(300);
  });

  it('prices units beyond a closed final bracket at the last bracket rate, not base price', () => {
    // 10 @ 100 + 40 @ 80 + 10 @ 80
    const res = preview('tiered', 60);
    expect(res.subtotal).toBe(1000 + 50 * 80);
    expect(res.note).toContain('above final bracket');
  });

  it('falls back to base price with no tiers', () => {
    expect(preview('tiered', 4, []).subtotal).toBe(2000);
  });
});

describe('calculatePricePreview — tax and simple models', () => {
  it('applies tax on the subtotal', () => {
    const res = calculatePricePreview({ pricingModel: 'per_unit', basePrice: 100, taxRatePct: 18, tiers: [], quantity: 2 });
    expect(res).toMatchObject({ subtotal: 200, tax: 36, total: 236 });
  });

  it('flat ignores quantity', () => {
    expect(calculatePricePreview({ pricingModel: 'flat', basePrice: 999, taxRatePct: 0, tiers: [], quantity: 7 }).subtotal).toBe(999);
  });
});

describe('normalizeBrackets', () => {
  it('drops invalid, overlapped and post-open-ended brackets', () => {
    const out = normalizeBrackets(
      [
        { min_qty: 1, max_qty: 10, unit_price: 100 },
        { min_qty: 5, max_qty: 8, unit_price: 1 }, // fully overlapped
        { min_qty: 20, max_qty: 15, unit_price: 1 }, // max < min
        { min_qty: 11, unit_price: 80 }, // open-ended
        { min_qty: 100, max_qty: 200, unit_price: 1 }, // after open-ended
      ],
      500,
    );
    expect(out).toEqual([
      { min: 1, max: 10, price: 100 },
      { min: 11, max: null, price: 80 },
    ]);
  });
});
