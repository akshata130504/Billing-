import type { PlanPricingModel, PlanPricingTier } from '../../../types/plans_pricing';

// Client-side price preview for the plan editor. Mirrors the bracket semantics of
// backend/app/services/pricing_engine.py (calculate_line_item_pricing / _normalize_brackets):
// brackets are ordered by min_qty and each one owns (previous max_qty, max_qty].

export interface PricePreviewInput {
  pricingModel: PlanPricingModel;
  basePrice: number;
  taxRatePct: number;
  tiers: PlanPricingTier[];
  quantity: number;
  /** Display symbol used in the explanation note. */
  symbol?: string;
}

export interface PricePreview {
  subtotal: number;
  tax: number;
  total: number;
  note: string;
}

type Bracket = { min: number; max: number | null; price: number };

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** Deterministic brackets, same rules as the backend's `_normalize_brackets`. */
export function normalizeBrackets(tiers: PlanPricingTier[], defaultPrice: number): Bracket[] {
  const rows: Bracket[] = [];
  for (const t of tiers || []) {
    if (!t) continue;
    const packageShaped =
      (t.package_qty !== undefined || t.package_price !== undefined) && !isNum(t.min_qty) && !isNum(t.max_qty);
    if (packageShaped) continue;
    const min = isNum(t.min_qty) ? t.min_qty : 0;
    const max = isNum(t.max_qty) ? t.max_qty : null;
    const price = isNum(t.unit_price) ? t.unit_price : defaultPrice;
    if (min < 0 || price < 0 || (max !== null && max < min)) continue;
    rows.push({ min, max, price });
  }
  rows.sort((a, b) => {
    if (a.min !== b.min) return a.min - b.min;
    if ((a.max === null) !== (b.max === null)) return a.max === null ? 1 : -1;
    return (a.max ?? 0) - (b.max ?? 0);
  });
  const brackets: Bracket[] = [];
  let prevUpper: number | null = -1;
  for (const row of rows) {
    if (brackets.length && brackets[brackets.length - 1].max === null) break;
    if (row.max !== null && prevUpper !== null && row.max <= prevUpper) continue;
    brackets.push(row);
    prevUpper = row.max;
  }
  return brackets;
}

export function calculatePricePreview({
  pricingModel,
  basePrice,
  taxRatePct,
  tiers,
  quantity: qty,
  symbol = '₹',
}: PricePreviewInput): PricePreview {
  const money = (n: number) => `${symbol}${n.toLocaleString('en-IN')}`;
  let subtotal = 0;
  let note = '';

  if (pricingModel === 'flat') {
    subtotal = basePrice;
    note = `Fixed ${money(basePrice)} regardless of quantity (${qty} units)`;
  } else if (pricingModel === 'per_unit') {
    subtotal = basePrice * qty;
    note = `${qty} units × ${money(basePrice)}`;
  } else if (pricingModel === 'volume') {
    // The WHOLE quantity is priced at the bracket containing it; below the first bracket
    // uses the first, in-gap quantities use the next bracket, above a closed final
    // bracket uses the final bracket.
    const brackets = normalizeBrackets(tiers, basePrice);
    if (!brackets.length) {
      subtotal = basePrice * qty;
      note = `Volume pricing (no brackets configured): all ${qty} units @ ${money(basePrice)}/unit`;
    } else {
      const chosen = brackets.find((b) => b.max === null || qty <= b.max) ?? brackets[brackets.length - 1];
      const beyond = chosen.max !== null && qty > chosen.max;
      subtotal = chosen.price * qty;
      note =
        `Volume tier [${chosen.min} - ${chosen.max ?? '∞'}]: all ${qty} units @ ${money(chosen.price)}/unit` +
        (beyond ? ' (above the final bracket; final bracket rate applied)' : '');
    }
  } else if (pricingModel === 'tiered') {
    // Graduated: bracket i covers (upper_{i-1}, upper_i]; units beyond a closed final
    // bracket are priced at the final bracket's rate.
    const brackets = normalizeBrackets(tiers, basePrice);
    if (!brackets.length) {
      subtotal = basePrice * qty;
      note = `Graduated pricing (no brackets configured): ${qty} @ ${money(basePrice)}`;
    } else {
      let remaining = qty;
      let prevUpper = 0;
      const logs: string[] = [];
      for (const b of brackets) {
        if (remaining <= 0) break;
        let units: number;
        if (b.max === null) {
          units = remaining;
        } else {
          units = Math.min(remaining, Math.max(0, b.max - prevUpper));
          prevUpper = Math.max(prevUpper, b.max);
        }
        if (units > 0) {
          subtotal += units * b.price;
          remaining -= units;
          logs.push(`${units} @ ${money(b.price)}`);
        }
      }
      if (remaining > 0) {
        const last = brackets[brackets.length - 1].price;
        subtotal += remaining * last;
        logs.push(`${remaining} @ ${money(last)} (above final bracket)`);
      }
      note = `Graduated brackets: ${logs.join(' + ')}`;
    }
  } else if (pricingModel === 'package') {
    const sorted = [...tiers].sort((a, b) => (a.package_qty || 0) - (b.package_qty || 0));
    if (sorted.length === 0) {
      subtotal = basePrice;
      note = `Default package: ${money(basePrice)}`;
    } else {
      let best = sorted[0];
      for (const t of sorted) {
        best = t;
        if ((t.package_qty || 0) >= qty) break;
      }
      subtotal = best.package_price ?? basePrice;
      note = `Covered by package of ${best.package_qty} units for ${money(best.package_price ?? 0)}`;
    }
  }

  const tax = (subtotal * taxRatePct) / 100;
  return { subtotal, tax, total: subtotal + tax, note };
}
