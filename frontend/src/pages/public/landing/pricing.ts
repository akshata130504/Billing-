/**
 * The landing page's illustrative pricing calculator. These are MARKETING EXAMPLES only - they are
 * not Rooman Billing's own prices and are not connected to any tenant's Plans & Pricing.
 *
 * A faithful, parameterised port of the original hard-coded functions: with the seeded parameters
 * (defaultContent.json) every number and string is identical to the page before the CMS.
 */
import type { PricingModel, Tier } from './types';

const n0 = (v: number) => v.toLocaleString('en-IN');
const n2 = (v: number) => v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export interface PriceBreakdown {
  basePrice: string;
  basePriceNote: string;
  quantity: string;
  quantityNote: string;
  discount: string;
  discountNote: string;
  tax: string;
  taxNote: string;
  finalPrice: number;
  formula: string;
  explanation: string;
}

function tiersOf(model: PricingModel): Tier[] {
  return model.tiers && model.tiers.length > 0 ? model.tiers : [{ up_to: null, rate: 0 }];
}

/** Volume: the tier the whole quantity falls into. */
function volumeTier(tiers: Tier[], qty: number): number {
  const idx = tiers.findIndex((t) => t.up_to === null || qty <= t.up_to);
  return idx === -1 ? tiers.length - 1 : idx;
}

/** Tiered/graduated: units priced in each bracket. */
function bracketUnits(tiers: Tier[], qty: number): number[] {
  let previous = 0;
  return tiers.map((t) => {
    const cap = t.up_to === null ? Infinity : t.up_to;
    const units = Math.max(0, Math.min(qty, cap) - previous);
    previous = cap;
    return units;
  });
}

export function calculatePrice(model: PricingModel, qty: number): number {
  const price = model.price ?? 0;
  switch (model.kind) {
    case 'flat':
      return price;
    case 'per_unit':
      return qty * price;
    case 'volume': {
      const tiers = tiersOf(model);
      return qty * tiers[volumeTier(tiers, qty)].rate;
    }
    case 'tiered': {
      const tiers = tiersOf(model);
      return bracketUnits(tiers, qty).reduce((sum, units, i) => sum + units * tiers[i].rate, 0);
    }
    case 'package': {
      const size = Math.max(1, model.bundle_size ?? 1);
      return Math.ceil(qty / size) * price;
    }
    default:
      return 0;
  }
}

const NO_TAX = { tax: '₹0.00', taxNote: 'Net B2B / Excl.' };

export function buildBreakdown(model: PricingModel, qty: number): PriceBreakdown {
  const price = model.price ?? 0;
  switch (model.kind) {
    case 'flat':
      return {
        basePrice: `₹${n2(price)}`,
        basePriceNote: 'Flat recurring fee',
        quantity: 'Fixed',
        quantityNote: 'Unlimited access',
        discount: '₹0.00',
        discountNote: 'Standard platform rate',
        ...NO_TAX,
        finalPrice: price,
        formula: `Fixed Platform Rate = ₹${n2(price)} / month`,
        explanation: `Predictable, static recurring billing of ₹${n2(price)}/month regardless of usage spikes or seat count, providing stable overhead forecasting.`,
      };
    case 'per_unit':
      return {
        basePrice: `₹${n2(price)} / unit`,
        basePriceNote: 'Per active seat license',
        quantity: `${qty} units`,
        quantityNote: `${qty} active seats`,
        discount: '₹0.00',
        discountNote: 'Linear unit scale',
        ...NO_TAX,
        finalPrice: qty * price,
        formula: `${qty} units × ₹${n2(price)}/unit = ₹${n2(qty * price)}`,
        explanation: `Linear pricing calculates monthly billing directly by multiplying ${qty} active provisioned seats by ₹${n2(price)}/unit with automated mid-cycle proration.`,
      };
    case 'volume': {
      const tiers = tiersOf(model);
      const base = tiers[0].rate;
      const idx = volumeTier(tiers, qty);
      const rate = tiers[idx].rate;
      const total = qty * rate;
      const savings = (base - rate) * qty;
      const from = idx === 0 ? 1 : (tiers[idx - 1].up_to ?? 0) + 1;
      const upTo = tiers[idx].up_to;
      const tierName = upTo === null
        ? `Tier ${idx + 1} (${from}+ units @ ₹${n0(rate)})`
        : `Tier ${idx + 1} (${from}-${upTo} units @ ₹${n0(rate)})`;
      const firstUpTo = tiers[0].up_to;
      return {
        basePrice: `₹${n2(base)} / unit`,
        basePriceNote: 'Baseline Tier 1 rate',
        quantity: `${qty} units`,
        quantityNote: `Qualifies for ${tierName}`,
        discount: rate < base ? `-₹${n2(savings)}` : '₹0.00',
        discountNote: rate < base
          ? `${Math.round(((base - rate) / base) * 100)}% volume savings`
          : firstUpTo === null ? 'Baseline rate' : `Baseline rate (1-${firstUpTo})`,
        ...NO_TAX,
        finalPrice: total,
        formula: `${qty} units × ₹${n2(rate)}/unit (${tierName}) = ₹${n2(total)}`,
        explanation: `All ${qty} units qualify for the discounted ${tierName} threshold, generating ₹${n0(savings)} in total volume savings over base rate.`,
      };
    }
    case 'tiered': {
      const tiers = tiersOf(model);
      const base = tiers[0].rate;
      const units = bracketUnits(tiers, qty);
      const total = units.reduce((sum, u, i) => sum + u * tiers[i].rate, 0);
      const savings = qty * base - total;
      const parts = units
        .map((u, i) => ({ u, i }))
        .filter(({ u, i }) => i === 0 || u > 0)
        .map(({ u, i }) => `${u} @ ₹${n0(tiers[i].rate)}`);
      let previous = 0;
      const brackets = tiers.map((t, i) => {
        const label = t.up_to === null
          ? (i === 0 ? `all units @ ₹${n0(t.rate)}` : `beyond @ ₹${n0(t.rate)}`)
          : i === 0 ? `first ${t.up_to} @ ₹${n0(t.rate)}` : `next ${t.up_to - previous} @ ₹${n0(t.rate)}`;
        previous = t.up_to ?? previous;
        return label;
      });
      return {
        basePrice: `₹${n2(base)} / unit`,
        basePriceNote: 'Bracket 1 initial rate',
        quantity: `${qty} units`,
        quantityNote: 'Distributed in brackets',
        discount: savings > 0 ? `-₹${n2(savings)}` : '₹0.00',
        discountNote: savings > 0 ? 'Bracket graduation savings' : 'First bracket only',
        ...NO_TAX,
        finalPrice: total,
        formula: `${parts.join(' + ')} = ₹${n2(total)}`,
        explanation: `Units are dynamically bucketed into progressive graduated brackets (${brackets.join(', ')}), guaranteeing margin control and transparent line items.`,
      };
    }
    case 'package': {
      const size = Math.max(1, model.bundle_size ?? 1);
      const bundles = Math.ceil(qty / size);
      const total = bundles * price;
      return {
        basePrice: `₹${n2(price)} / bundle`,
        basePriceNote: `Block of ${size} units`,
        quantity: `${bundles} bundle${bundles > 1 ? 's' : ''}`,
        quantityNote: `Covers ${qty} units (${bundles * size} capacity)`,
        discount: '₹0.00',
        discountNote: 'Bundled wholesale rate',
        ...NO_TAX,
        finalPrice: total,
        formula: `${bundles} bundle(s) × ₹${n2(price)}/bundle = ₹${n2(total)}`,
        explanation: `Predefined commitment allotments group units into blocks of ${size} at ₹${n2(price)} per bundle, providing predictable volume commitments with zero billing drift.`,
      };
    }
    default:
      return {
        basePrice: '₹0.00', basePriceNote: '', quantity: '', quantityNote: '', discount: '₹0.00', discountNote: '',
        ...NO_TAX, finalPrice: 0, formula: '', explanation: '',
      };
  }
}
