import { describe, expect, it } from 'vitest';
import { isQuoteOpenForCustomer } from './quoteStatus';

// Regression (browser QA): opening a sent quote's public link marks it "viewed", after which
// the page showed "This quote isn't ready yet" and hid Accept / Decline.
describe('isQuoteOpenForCustomer', () => {
  it('is open while sent or viewed', () => {
    expect(isQuoteOpenForCustomer('sent')).toBe(true);
    expect(isQuoteOpenForCustomer('viewed')).toBe(true);
    expect(isQuoteOpenForCustomer('VIEWED')).toBe(true);
  });

  it('is closed for every other status', () => {
    for (const s of ['draft', 'pending_approval', 'approved', 'accepted', 'declined', 'expired', 'converted', '', null, undefined]) {
      expect(isQuoteOpenForCustomer(s)).toBe(false);
    }
  });
});
