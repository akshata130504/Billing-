import { describe, expect, it } from 'vitest';
import {
  addDays,
  calculateValidityDays,
  currencySymbol,
  formatDate,
  formatDateTime,
  formatMonth,
  formatMoney,
  formatNumber,
  formatPercent,
  formatQuoteTerms,
  formatRelative,
  humanize,
  initials,
  parseMoney,
  statusVariant,
  toIsoDate,
  toMoneyString,
  todayIso,
  updateTermsValidity,
} from './format';

// ICU shortens September to "Sep" or "Sept" depending on the ICU version bundled
// with the runtime, so month assertions are matched loosely on purpose.
const SEP = /Sept?/;

describe('parseMoney', () => {
  it('parses contract money strings', () => {
    expect(parseMoney('1250.00')).toBe(1250);
    expect(parseMoney('0.01')).toBe(0.01);
    expect(parseMoney('-99.95')).toBe(-99.95);
  });

  it('passes numbers through', () => {
    expect(parseMoney(1250.5)).toBe(1250.5);
    expect(parseMoney(0)).toBe(0);
  });

  it('returns NaN for empty / nullish / non-numeric input', () => {
    expect(parseMoney(null)).toBeNaN();
    expect(parseMoney(undefined)).toBeNaN();
    expect(parseMoney('')).toBeNaN();
    expect(parseMoney('abc')).toBeNaN();
    expect(parseMoney('12,50')).toBeNaN();
  });

  it('returns NaN for non-finite numbers', () => {
    expect(parseMoney(Infinity)).toBeNaN();
    expect(parseMoney(-Infinity)).toBeNaN();
    expect(parseMoney(NaN)).toBeNaN();
  });

  // BUG: Number('   ') === 0, so a whitespace-only money field is silently read
  // as zero rupees instead of being rejected as missing data.
  // See src/utils/format.ts:34-38 (parseMoney).
  it('should reject a whitespace-only string instead of reading it as 0', () => {
    expect(parseMoney('   ')).toBeNaN();
  });
});

describe('formatMoney', () => {
  it('formats INR with the rupee symbol, 2 decimals and en-IN grouping', () => {
    expect(formatMoney('1250.00')).toBe('₹1,250.00');
    expect(formatMoney(1250)).toBe('₹1,250.00');
    expect(formatMoney('0')).toBe('₹0.00');
    expect(formatMoney('99.5')).toBe('₹99.50');
  });

  it('uses lakh/crore grouping for large amounts', () => {
    expect(formatMoney('1234567.891')).toBe('₹12,34,567.89');
  });

  it('renders negatives with a leading minus', () => {
    expect(formatMoney('-1250.50')).toBe('-₹1,250.50');
  });

  it('returns an em dash for missing or unparseable amounts', () => {
    expect(formatMoney(null)).toBe('—');
    expect(formatMoney(undefined)).toBe('—');
    expect(formatMoney('')).toBe('—');
    expect(formatMoney('not-money')).toBe('—');
  });

  it('honours a non-INR currency', () => {
    expect(formatMoney('1250', 'USD')).toBe('$1,250.00');
  });

  it('falls back to plain number formatting for an invalid currency code', () => {
    // Intl throws on a bad currency; the helper must not blow up the page.
    const out = formatMoney('1250', 'NOTACURRENCY');
    expect(out).toContain('1,250.00');
  });

  describe('compact (lakh / crore) branch', () => {
    it('leaves amounts below 1 lakh unchanged', () => {
      expect(formatMoney('99999.99', 'INR', { compact: true })).toBe('₹99,999.99');
    });

    it('switches to lakhs at exactly 1 lakh', () => {
      expect(formatMoney('100000', 'INR', { compact: true })).toBe('₹1.00 L');
      expect(formatMoney('150000', 'INR', { compact: true })).toBe('₹1.50 L');
      expect(formatMoney('9999999', 'INR', { compact: true })).toBe('₹100.00 L');
    });

    it('switches to crores at exactly 1 crore', () => {
      expect(formatMoney('10000000', 'INR', { compact: true })).toBe('₹1.00 Cr');
      expect(formatMoney('12500000', 'INR', { compact: true })).toBe('₹1.25 Cr');
    });

    it('is ignored when compact is not requested', () => {
      expect(formatMoney('150000')).toBe('₹1,50,000.00');
    });

    // BUG: the compact branch concatenates the symbol before the signed number,
    // producing "₹-1.50 L" instead of "-₹1.50 L" (the sign lands inside the
    // currency prefix, unlike every non-compact amount).
    // See src/utils/format.ts:48-52 (formatMoney compact branch).
    it('should place the minus sign before the currency symbol', () => {
      expect(formatMoney('-150000', 'INR', { compact: true })).toBe('-₹1.50 L');
    });

  });
});

describe('currencySymbol', () => {
  it('returns the locale symbol for known currencies', () => {
    expect(currencySymbol('INR')).toBe('₹');
    expect(currencySymbol('USD')).toBe('$');
    // Same convention as the backend's pricing_engine._CURRENCY_SYMBOLS.
    expect(currencySymbol('SGD')).toBe('S$');
    expect(currencySymbol('CAD')).toBe('C$');
    expect(currencySymbol('AUD')).toBe('A$');
    expect(currencySymbol('AED')).toBe('AED');
    expect(currencySymbol()).toBe('₹');
  });

  it('echoes the code back for an unknown currency', () => {
    expect(currencySymbol('NOTACURRENCY')).toBe('NOTACURRENCY');
  });
});

describe('toMoneyString', () => {
  it('always serialises 2 decimals', () => {
    expect(toMoneyString(1250)).toBe('1250.00');
    expect(toMoneyString('1250.5')).toBe('1250.50');
    expect(toMoneyString(-99.95)).toBe('-99.95');
    expect(toMoneyString(0)).toBe('0.00');
  });

  // BUG (money-critical): toFixed rounds the *binary* double, so half-way
  // decimal amounts round down. 2.675 is stored as 2.67499999999999982…, so a
  // ₹2.675 line total is serialised to the API as "2.67", losing a paisa on
  // every such row. A decimal-safe rounding step is needed.
  // See src/utils/format.ts:66-69 (toMoneyString).
  it('should round half-way amounts up (decimal rounding)', () => {
    expect(toMoneyString(2.675)).toBe('2.68');
    expect(toMoneyString(1.005)).toBe('1.01');
  });


  it('never emits thousands separators (the API rejects them)', () => {
    expect(toMoneyString(1234567.89)).toBe('1234567.89');
  });

  it('coerces unparseable input to "0.00"', () => {
    // NOTE: silently sending 0.00 for garbage input is risky, but it is the
    // documented contract of this helper today.
    expect(toMoneyString('abc')).toBe('0.00');
    expect(toMoneyString('')).toBe('0.00');
  });
});

describe('formatPercent', () => {
  it('formats with one decimal by default and strips a trailing .0', () => {
    expect(formatPercent('12.5')).toBe('12.5%');
    expect(formatPercent(10)).toBe('10%');
    expect(formatPercent(0)).toBe('0%');
    expect(formatPercent('-3.25')).toBe('-3.3%');
  });

  it('honours an explicit digit count', () => {
    expect(formatPercent('12.345', 2)).toBe('12.35%');
    expect(formatPercent(100, 2)).toBe('100%');
  });

  it('returns an em dash for missing values', () => {
    expect(formatPercent(null)).toBe('—');
    expect(formatPercent(undefined)).toBe('—');
    expect(formatPercent('')).toBe('—');
    expect(formatPercent('n/a')).toBe('—');
  });

  it('only strips zeros that make up the whole fraction', () => {
    // "20.10" keeps its trailing zero while "20.00" collapses to "20" — the
    // regex only matches an all-zero fraction. Documented, not asserted as ideal.
    expect(formatPercent('20.1', 2)).toBe('20.10%');
    expect(formatPercent('20', 2)).toBe('20%');
  });
});

describe('formatNumber', () => {
  it('groups with the Indian numbering system', () => {
    expect(formatNumber(1234567)).toBe('12,34,567');
    expect(formatNumber('1000')).toBe('1,000');
    expect(formatNumber(0)).toBe('0');
  });

  it('returns an em dash for missing values', () => {
    expect(formatNumber(null)).toBe('—');
    expect(formatNumber('')).toBe('—');
    expect(formatNumber('abc')).toBe('—');
  });
});

describe('formatDate', () => {
  it('formats a plain YYYY-MM-DD date', () => {
    expect(formatDate('2026-09-07')).toMatch(/^07 Sept? 2026$/);
  });

  it('does not shift a date-only value across the timezone boundary', () => {
    // The classic bug: new Date('2026-01-01') is UTC midnight, which is the
    // previous day in negative offsets. The helper parses date-only as local.
    expect(formatDate('2026-01-01')).toBe('01 Jan 2026');
    expect(formatDate('2026-12-31')).toBe('31 Dec 2026');
  });

  it('accepts Date instances and full ISO timestamps', () => {
    expect(formatDate(new Date(2026, 8, 7))).toMatch(/^07 Sept? 2026$/);
    expect(formatDate('2026-03-15T09:30:00Z')).toMatch(/^1[56] Mar 2026$/);
  });

  it('returns an em dash for missing or invalid input', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatDate(undefined)).toBe('—');
    expect(formatDate('')).toBe('—');
    expect(formatDate('never')).toBe('—');
    expect(formatDate(new Date('nope'))).toBe('—');
  });
});

describe('formatDateTime', () => {
  it('includes a 12-hour clock time', () => {
    const out = formatDateTime(new Date(2026, 8, 7, 15, 45));
    expect(out).toMatch(SEP);
    expect(out).toMatch(/07 Sept? 2026, 03:45\s?pm/i);
  });

  it('returns an em dash for missing input', () => {
    expect(formatDateTime(null)).toBe('—');
    expect(formatDateTime('garbage')).toBe('—');
  });
});

describe('formatMonth', () => {
  it('renders month + year only', () => {
    expect(formatMonth('2026-09-07')).toMatch(/^Sept? 2026$/);
    expect(formatMonth('2026-01-31')).toBe('Jan 2026');
  });

  it('returns an em dash for missing input', () => {
    expect(formatMonth(null)).toBe('—');
  });
});

describe('formatRelative', () => {
  const now = new Date('2026-09-07T12:00:00Z');

  it('collapses anything inside 45 seconds to "just now"', () => {
    expect(formatRelative(new Date(now.getTime() - 30_000), now)).toBe('just now');
    expect(formatRelative(new Date(now.getTime() + 30_000), now)).toBe('just now');
  });

  it('reports minutes, hours and days in the past', () => {
    expect(formatRelative(new Date(now.getTime() - 5 * 60_000), now)).toBe('5 minutes ago');
    expect(formatRelative(new Date(now.getTime() - 3 * 3600_000), now)).toBe('3 hours ago');
    expect(formatRelative(new Date(now.getTime() - 24 * 3600_000), now)).toBe('yesterday');
    expect(formatRelative(new Date(now.getTime() - 5 * 86400_000), now)).toBe('5 days ago');
  });

  it('reports future instants', () => {
    expect(formatRelative(new Date(now.getTime() + 2 * 86400_000), now)).toBe('in 2 days');
    expect(formatRelative(new Date(now.getTime() + 3 * 3600_000), now)).toBe('in 3 hours');
  });

  it('rolls up to months and years', () => {
    expect(formatRelative(new Date(now.getTime() - 60 * 86400_000), now)).toBe('2 months ago');
    expect(formatRelative(new Date(now.getTime() - 400 * 86400_000), now)).toBe('last year');
  });

  it('returns an em dash for missing input', () => {
    expect(formatRelative(null, now)).toBe('—');
    expect(formatRelative('not-a-date', now)).toBe('—');
  });
});

describe('toIsoDate / todayIso', () => {
  it('serialises a local Date as YYYY-MM-DD with zero padding', () => {
    expect(toIsoDate(new Date(2026, 0, 5))).toBe('2026-01-05');
    expect(toIsoDate(new Date(2026, 11, 31))).toBe('2026-12-31');
  });

  it('uses local calendar fields, not UTC', () => {
    // 00:30 local on the 5th must stay the 5th even in a +05:30 zone.
    expect(toIsoDate(new Date(2026, 0, 5, 0, 30))).toBe('2026-01-05');
    expect(toIsoDate(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05');
  });

  it('todayIso round-trips through toIsoDate', () => {
    expect(todayIso()).toBe(toIsoDate(new Date()));
    expect(todayIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe('addDays', () => {
  it('adds and subtracts days across month and year boundaries', () => {
    expect(addDays('2026-02-27', 2)).toBe('2026-03-01');
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
    expect(addDays('2026-01-01', -1)).toBe('2025-12-31');
    expect(addDays('2026-09-07', 0)).toBe('2026-09-07');
  });

  it('handles leap years', () => {
    expect(addDays('2028-02-28', 1)).toBe('2028-02-29');
    expect(addDays('2028-02-28', 2)).toBe('2028-03-01');
  });

  it('returns the input unchanged when it is not a date', () => {
    expect(addDays('nonsense', 5)).toBe('nonsense');
    expect(addDays('', 5)).toBe('');
  });
});

describe('statusVariant', () => {
  it('maps invoice/payment statuses to their badge variants', () => {
    expect(statusVariant('paid')).toBe('success');
    expect(statusVariant('overdue')).toBe('danger');
    expect(statusVariant('partially_paid')).toBe('warning');
    expect(statusVariant('draft')).toBe('neutral');
    expect(statusVariant('sent')).toBe('primary');
    expect(statusVariant('succeeded')).toBe('success');
    expect(statusVariant('failed')).toBe('danger');
  });

  it('never marks money-negative states as success', () => {
    for (const bad of ['overdue', 'failed', 'past_due', 'declined', 'rejected']) {
      expect(statusVariant(bad)).toBe('danger');
    }
  });

  it('falls back to neutral for unknown or missing statuses', () => {
    expect(statusVariant('brand_new_status')).toBe('neutral');
    expect(statusVariant(null)).toBe('neutral');
    expect(statusVariant(undefined)).toBe('neutral');
    expect(statusVariant('')).toBe('neutral');
  });
});

describe('humanize', () => {
  it('converts snake/kebab case to sentence case', () => {
    expect(humanize('partially_paid')).toBe('Partially paid');
    expect(humanize('pending-approval')).toBe('Pending approval');
    expect(humanize('paid')).toBe('Paid');
    expect(humanize('completed_with_errors')).toBe('Completed with errors');
  });

  it('returns an em dash for missing values', () => {
    expect(humanize(null)).toBe('—');
    expect(humanize(undefined)).toBe('—');
    expect(humanize('')).toBe('—');
  });
});

describe('initials', () => {
  it('uses first + last initial', () => {
    expect(initials('Faizan Khan')).toBe('FK');
    expect(initials('ada b lovelace')).toBe('AL');
  });

  it('uses the first two characters of a single-word name', () => {
    expect(initials('Rooman')).toBe('RO');
    expect(initials('x')).toBe('X');
  });

  it('falls back when there is no usable name', () => {
    expect(initials(null)).toBe('?');
    expect(initials('')).toBe('?');
    expect(initials('   ')).toBe('?');
    expect(initials(null, '--')).toBe('--');
  });
});

describe('calculateValidityDays', () => {
  it('calculates exact difference in calendar days', () => {
    expect(calculateValidityDays('2026-09-28', '2026-10-05')).toBe(7);
    expect(calculateValidityDays('2026-09-28', '2026-10-13')).toBe(15);
    expect(calculateValidityDays('2026-09-28', '2026-10-28')).toBe(30);
    expect(calculateValidityDays('2026-09-28', '2026-11-27')).toBe(60);
    expect(calculateValidityDays('2026-09-28', '2026-12-27')).toBe(90);
  });

  it('returns null when expiry is not after issue date or dates are invalid', () => {
    expect(calculateValidityDays('2026-09-28', '2026-09-28')).toBeNull();
    expect(calculateValidityDays('2026-09-28', '2026-09-20')).toBeNull();
    expect(calculateValidityDays(null, '2026-10-13')).toBeNull();
    expect(calculateValidityDays('2026-09-28', null)).toBeNull();
    expect(calculateValidityDays('invalid', '2026-10-13')).toBeNull();
  });
});

describe('formatQuoteTerms', () => {
  it('formats default terms with canonical validity tenure', () => {
    expect(formatQuoteTerms(7)).toContain('Quote valid for 7 days.');
    expect(formatQuoteTerms(15)).toContain('Quote valid for 15 days.');
    expect(formatQuoteTerms(30)).toContain('Quote valid for 30 days.');
    expect(formatQuoteTerms(60)).toContain('Quote valid for 60 days.');
    expect(formatQuoteTerms(90)).toContain('Quote valid for 90 days.');
    expect(formatQuoteTerms(15)).toContain('Payment terms: 30 days from invoice date.');
    expect(formatQuoteTerms(15)).toContain('Taxes as applicable per Indian GST.');
  });
});

describe('updateTermsValidity', () => {
  it('updates the quote validity clause while preserving payment terms and taxes', () => {
    const original = '1. Quote valid for 30 days.\n2. Payment terms: 30 days from invoice date.\n3. Taxes as applicable per Indian GST.';
    const updated15 = updateTermsValidity(original, 15);
    expect(updated15).toContain('Quote valid for 15 days');
    expect(updated15).not.toContain('Quote valid for 30 days');
    expect(updated15).toContain('Payment terms: 30 days from invoice date.');

    const updated60 = updateTermsValidity(original, 60);
    expect(updated60).toContain('Quote valid for 60 days');
    expect(updated60).not.toContain('Quote valid for 30 days');

    const updated90 = updateTermsValidity(original, 90);
    expect(updated90).toContain('Quote valid for 90 days');
    expect(updated90).not.toContain('Quote valid for 30 days');

    const updated7 = updateTermsValidity(original, 7);
    expect(updated7).toContain('Quote valid for 7 days');
    expect(updated7).not.toContain('Quote valid for 30 days');
  });

  it('preserves custom additional clauses when updating validity', () => {
    const custom = '1. Quote valid for 30 days.\n2. Payment terms: 45 days net.\n3. Custom SLA 99.99% applies.';
    const updated = updateTermsValidity(custom, 15);
    expect(updated).toContain('Quote valid for 15 days');
    expect(updated).toContain('Payment terms: 45 days net.');
    expect(updated).toContain('Custom SLA 99.99% applies.');
  });

  it('formats new terms if input is null or empty', () => {
    expect(updateTermsValidity(null, 15)).toBe(formatQuoteTerms(15));
    expect(updateTermsValidity('', 60)).toBe(formatQuoteTerms(60));
  });
});
