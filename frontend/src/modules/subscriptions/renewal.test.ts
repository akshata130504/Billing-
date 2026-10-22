import { describe, expect, it } from 'vitest';
import { manualRenewalState } from './renewal';

// BUG-45: Renew was offered although POST /renew answers 409 until the next billing date.
describe('manualRenewalState', () => {
  it('is not due before the next billing date, and says when it renews', () => {
    const state = manualRenewalState({ status: 'active', next_billing_date: '2026-11-09', renewal_due: false }, '2026-10-10');
    expect(state.due).toBe(false);
    expect(state.reason).toMatch(/Not due yet/);
    expect(state.reason).toMatch(/2026|Nov/);
  });

  it('is due once the server says so', () => {
    expect(manualRenewalState({ status: 'active', next_billing_date: '2026-10-10', renewal_due: true }, '2026-10-10')).toEqual({
      due: true,
      reason: null,
    });
  });

  it('follows the server flag over the browser date', () => {
    // The browser's local day can be ahead of the server's.
    expect(manualRenewalState({ status: 'active', next_billing_date: '2026-10-10', renewal_due: false }, '2026-10-10').due).toBe(false);
  });

  it('falls back to the next billing date when the flag is absent', () => {
    expect(manualRenewalState({ status: 'active', next_billing_date: '2026-10-09' }, '2026-10-10').due).toBe(true);
    expect(manualRenewalState({ status: 'active', next_billing_date: '2026-10-11' }, '2026-10-10').due).toBe(false);
    expect(manualRenewalState({ status: 'active', next_billing_date: null }, '2026-10-10').due).toBe(false);
  });

  it('is never due for a subscription that is not active', () => {
    expect(manualRenewalState({ status: 'paused', next_billing_date: '2026-10-01', renewal_due: false }, '2026-10-10').due).toBe(false);
  });
});
