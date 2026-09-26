import { describe, expect, it } from 'vitest';
import { formatPerCurrency } from './dashboardSummaryService';

const fmt = (amount: string, currency: string) => `${currency} ${amount}`;

describe('formatPerCurrency', () => {
  it('lists one figure per currency without summing across currencies', () => {
    const rows = [
      { currency: 'INR', net: '1200.00' },
      { currency: 'USD', net: '40.00' },
    ];
    expect(formatPerCurrency(rows, (r) => r.net, fmt, 'INR')).toBe('INR 1200.00 · USD 40.00');
  });

  it('shows a zero in the fallback currency for an empty organization', () => {
    expect(formatPerCurrency<{ currency: string; net: string }>([], (r) => r.net, fmt, 'INR')).toBe('INR 0');
  });
});
