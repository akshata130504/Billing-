import { describe, expect, it } from 'vitest';
import {
  CHANGE_STATUS_VARIANTS,
  CHANGE_TYPE_LABELS,
  CHANGE_TYPE_VARIANTS,
  EFFECTIVE_TYPE_LABELS,
  changeStatusVariant,
  changeTypeLabel,
  changeTypeVariant,
  formatQuantity,
  intervalLabel,
  intervalMonths,
  monthlyEquivalent,
} from './prorationLabels';

describe('change type labels and variants', () => {
  it('labels every subscription change type', () => {
    expect(CHANGE_TYPE_LABELS).toEqual({
      upgrade: 'Upgrade',
      downgrade: 'Downgrade',
      quantity_change: 'Quantity change',
      addon_change: 'Add-on change',
      cancellation: 'Cancellation',
    });
  });

  it('uses money-semantic colours (upgrade positive, cancellation negative)', () => {
    expect(CHANGE_TYPE_VARIANTS.upgrade).toBe('success');
    expect(CHANGE_TYPE_VARIANTS.downgrade).toBe('warning');
    expect(CHANGE_TYPE_VARIANTS.cancellation).toBe('danger');
  });

  it('falls back to a de-underscored label for an unknown type', () => {
    expect(changeTypeLabel('upgrade')).toBe('Upgrade');
    expect(changeTypeLabel('plan_swap')).toBe('plan swap');
    expect(changeTypeLabel('')).toBe('');
  });

  it('falls back to a neutral variant for an unknown type', () => {
    expect(changeTypeVariant('upgrade')).toBe('success');
    expect(changeTypeVariant('plan_swap')).toBe('neutral');
  });
});

describe('changeStatusVariant', () => {
  it('maps every change status', () => {
    expect(CHANGE_STATUS_VARIANTS).toEqual({
      previewed: 'neutral',
      scheduled: 'warning',
      applied: 'success',
      cancelled: 'neutral',
      failed: 'danger',
    });
  });

  it('never shows a failed change as success', () => {
    expect(changeStatusVariant('failed')).toBe('danger');
    expect(changeStatusVariant('applied')).toBe('success');
  });

  it('falls back to neutral for an unknown status', () => {
    expect(changeStatusVariant('half_applied')).toBe('neutral');
  });
});

describe('EFFECTIVE_TYPE_LABELS', () => {
  it('covers every proration effective type', () => {
    expect(Object.keys(EFFECTIVE_TYPE_LABELS).sort()).toEqual([
      'end_of_term',
      'immediate',
      'scheduled',
    ]);
  });
});

describe('formatQuantity', () => {
  it('strips the decimal padding the API sends', () => {
    expect(formatQuantity('5.000')).toBe('5');
    expect(formatQuantity('2.500')).toBe('2.5');
    expect(formatQuantity(3)).toBe('3');
  });

  it('keeps zero and negative quantities visible', () => {
    expect(formatQuantity('0.000')).toBe('0');
    expect(formatQuantity('-1.500')).toBe('-1.5');
  });

  it('returns an em dash for missing values', () => {
    expect(formatQuantity(null)).toBe('—');
    expect(formatQuantity(undefined)).toBe('—');
    expect(formatQuantity('')).toBe('—');
  });

  it('echoes non-numeric input instead of rendering NaN', () => {
    expect(formatQuantity('many')).toBe('many');
  });

  it('does not group large quantities (unlike the usage formatter)', () => {
    // Worth knowing: proration shows "1000000" where usage shows "10,00,000".
    expect(formatQuantity('1000000')).toBe('1000000');
  });
});

describe('intervalLabel', () => {
  it('renders the singular label for a count of one', () => {
    expect(intervalLabel('monthly')).toBe('month');
    expect(intervalLabel('quarterly')).toBe('quarter');
    expect(intervalLabel('semiannual')).toBe('half-year');
    expect(intervalLabel('yearly')).toBe('year');
  });

  it('pluralises for a multi-interval billing period', () => {
    expect(intervalLabel('monthly', 3)).toBe('3 months');
    expect(intervalLabel('yearly', 2)).toBe('2 years');
    expect(intervalLabel('semiannual', 2)).toBe('2 half-years');
  });

  it('never pluralises a one-time charge', () => {
    expect(intervalLabel('one_time')).toBe('one-time');
    expect(intervalLabel('one_time', 5)).toBe('one-time');
  });

  it('returns an empty string when the interval is unknown or missing', () => {
    expect(intervalLabel(undefined)).toBe('');
    expect(intervalLabel('')).toBe('');
  });

  it('passes an unrecognised interval through', () => {
    expect(intervalLabel('weekly')).toBe('weekly');
  });

  it('treats a count of zero or one as singular', () => {
    expect(intervalLabel('monthly', 1)).toBe('month');
    expect(intervalLabel('monthly', 0)).toBe('month');
  });
});

describe('intervalMonths', () => {
  it('maps each billing interval to its month count', () => {
    expect(intervalMonths('monthly')).toBe(1);
    expect(intervalMonths('quarterly')).toBe(3);
    expect(intervalMonths('semiannual')).toBe(6);
    expect(intervalMonths('yearly')).toBe(12);
  });

  it('multiplies by interval_count', () => {
    expect(intervalMonths('monthly', 3)).toBe(3);
    expect(intervalMonths('yearly', 2)).toBe(24);
  });

  it('treats a missing or zero count as one period', () => {
    expect(intervalMonths('monthly', 0)).toBe(1);
    expect(intervalMonths('quarterly', undefined as unknown as number)).toBe(3);
  });

  it('returns null for intervals that cannot be expressed per month', () => {
    expect(intervalMonths('one_time')).toBeNull();
    expect(intervalMonths('fortnightly')).toBeNull();
    expect(intervalMonths(undefined)).toBeNull();
  });
});

describe('monthlyEquivalent', () => {
  it('normalises a yearly price to a monthly one', () => {
    expect(monthlyEquivalent('24000', 'yearly')).toBe(2000);
    expect(monthlyEquivalent('45000', 'quarterly')).toBe(15000);
  });

  it('leaves a monthly price unchanged', () => {
    expect(monthlyEquivalent('2500', 'monthly')).toBe(2500);
  });

  it('ranks a cheaper-per-month yearly plan below a monthly one', () => {
    // The bug this guards: comparing raw unit_amount called the yearly plan an
    // upgrade (24000 > 2500) when it is actually cheaper per month.
    const yearly = monthlyEquivalent('24000', 'yearly')!;
    const monthly = monthlyEquivalent('2500', 'monthly')!;
    expect(yearly).toBeLessThan(monthly);
  });

  it('accounts for interval_count', () => {
    expect(monthlyEquivalent('6000', 'monthly', 3)).toBe(2000);
  });

  it('returns null when the amount or interval is not comparable', () => {
    expect(monthlyEquivalent('not-a-number', 'monthly')).toBeNull();
    expect(monthlyEquivalent(null, 'monthly')).toBeNull();
    expect(monthlyEquivalent('1000', 'one_time')).toBeNull();
  });
});
