import type { PlatformSubscriptionInfo } from '../../types/api';
import { formatMoney } from '../../utils/format';

/** "₹799.00" from 79900 paise. The catalog stores the smallest currency unit; never display it raw. */
export function formatPlanPrice(amountMinor: number, currency: string): string {
  return formatMoney(amountMinor / 100, currency);
}

const INTERVAL_NOUNS: Record<string, string> = { day: 'day', week: 'week', month: 'month', year: 'year' };

/** "per month", "every 3 months", "per year". */
export function formatInterval(interval: string, count = 1): string {
  const noun = INTERVAL_NOUNS[interval] ?? interval;
  return count > 1 ? `every ${count} ${noun}s` : `per ${noun}`;
}

/**
 * The tax line comes only from the catalog's tax_treatment. Nothing is inferred: no tax name or rate is
 * shown, and an unknown or missing value shows nothing rather than a guess.
 */
export function taxLabel(taxTreatment: string | null | undefined): string | null {
  if (taxTreatment === 'exclusive') return 'Plus applicable taxes';
  if (taxTreatment === 'inclusive') return 'Inclusive of applicable taxes';
  return null;
}

export function seatLabel(seatLimit: number): string {
  return `Up to ${seatLimit} user${seatLimit === 1 ? '' : 's'}`;
}

/**
 * The organization already pays for a plan: active, or past_due still inside its grace period. The server
 * refuses a second checkout (SUBSCRIPTION_ALREADY_ACTIVE); the page mirrors that so it never offers one.
 */
export function hasPaidPlan(subscription: PlatformSubscriptionInfo | null | undefined): boolean {
  return subscription?.state === 'active' || subscription?.state === 'past_due';
}
