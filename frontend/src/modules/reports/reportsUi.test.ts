import { describe, expect, it } from 'vitest';
import {
  AGING_BUCKET_LABELS,
  PAYMENT_METHOD_LABELS,
  PRICING_MODEL_LABELS,
  formatReportPeriod,
} from './reportsUi';

describe('AGING_BUCKET_LABELS', () => {
  it('covers every aging bucket the reports API returns, in order', () => {
    expect(Object.keys(AGING_BUCKET_LABELS)).toEqual([
      'current',
      '1_30',
      '31_60',
      '61_90',
      '90_plus',
    ]);
    expect(AGING_BUCKET_LABELS['90_plus']).toBe('90+ Days');
    expect(AGING_BUCKET_LABELS.current).toBe('Current');
  });
});

describe('PAYMENT_METHOD_LABELS', () => {
  it('labels every backend payment method', () => {
    for (const code of ['razorpay', 'bank_transfer', 'upi', 'card', 'cash', 'cheque', 'other']) {
      expect(PAYMENT_METHOD_LABELS[code]).toBeTruthy();
    }
    expect(PAYMENT_METHOD_LABELS.upi).toBe('UPI');
    expect(PAYMENT_METHOD_LABELS.bank_transfer).toBe('Bank Transfer');
  });
});

describe('PRICING_MODEL_LABELS', () => {
  it('labels both pricing models', () => {
    expect(PRICING_MODEL_LABELS).toEqual({ flat: 'Flat', per_unit: 'Per Unit' });
  });
});

describe('formatReportPeriod', () => {
  it('formats a day-granularity period as day + month', () => {
    expect(formatReportPeriod('2026-09-07')).toMatch(/^07 Sept?$/);
    expect(formatReportPeriod('2026-01-01')).toBe('01 Jan');
  });

  it('formats a month-granularity period as month + year', () => {
    expect(formatReportPeriod('2026-09')).toMatch(/^Sept? 2026$/);
    expect(formatReportPeriod('2026-01')).toBe('Jan 2026');
  });

  it('does not shift the day across the timezone boundary', () => {
    // Built from local calendar parts, so 1 Jan never renders as 31 Dec.
    expect(formatReportPeriod('2026-12-31')).toBe('31 Dec');
  });

  it('echoes back anything that is not a recognised period', () => {
    expect(formatReportPeriod('2026')).toBe('2026');
    expect(formatReportPeriod('Q1 FY26')).toBe('Q1 FY26');
    expect(formatReportPeriod('')).toBe('');
  });

  it('rolls an out-of-range month over rather than erroring (documented quirk)', () => {
    // '2026-13' is not a period the API emits; Date rolls it into Jan 2027.
    expect(formatReportPeriod('2026-13')).toBe('Jan 2027');
  });
});
