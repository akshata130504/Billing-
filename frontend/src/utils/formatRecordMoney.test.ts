import { describe, expect, it } from 'vitest';
import { formatRecordMoney, normalizeCurrency, recordCurrencySymbol } from './format';

describe('normalizeCurrency', () => {
  it('accepts three-letter codes, upper-cased and trimmed', () => {
    expect(normalizeCurrency('AED')).toBe('AED');
    expect(normalizeCurrency(' usd ')).toBe('USD');
  });

  it.each([undefined, null, '', '  ', 'IN', 'RUPEES', '₹', '12A', 42])('returns null for %p', (value) => {
    expect(normalizeCurrency(value)).toBeNull();
  });
});

describe('formatRecordMoney', () => {
  it('formats in the record currency when known', () => {
    expect(formatRecordMoney('1180.4', 'INR')).toBe('₹1,180.40');
    expect(formatRecordMoney(250, 'USD')).toBe('$250.00');
    expect(formatRecordMoney('433.36', 'AED')).toMatch(/AED\s?433\.36/);
  });

  it('marks the amount when the currency is unknown, with no symbol', () => {
    expect(formatRecordMoney('1180.4', null)).toBe('1,180.40 (currency unknown)');
    expect(formatRecordMoney('abc', null)).toBe('—');
  });

  it('uses "?" as the input prefix when unknown', () => {
    expect(recordCurrencySymbol(null)).toBe('?');
    expect(recordCurrencySymbol('USD')).toBe('$');
  });
});
