import type { SubscriptionOut } from '../../types/api';
import { formatDate, todayIso } from '../../utils/format';

export interface ManualRenewalState {
  /** POST /subscriptions/{id}/renew would be accepted now. */
  due: boolean;
  /** Why Renew is unavailable (shown as the button tooltip and hint); null when due. */
  reason: string | null;
}

/**
 * The server only renews an active subscription whose next billing date has been reached (a
 * manual renewal is a catch-up, never an early bill), so the Renew action follows the same
 * rule. `renewal_due` comes from the API; older responses fall back to the date comparison.
 */
export function manualRenewalState(
  subscription: Pick<SubscriptionOut, 'status' | 'next_billing_date' | 'renewal_due'>,
  today: string = todayIso()
): ManualRenewalState {
  if (subscription.status !== 'active') {
    return { due: false, reason: 'Only active subscriptions can be renewed.' };
  }
  const next = subscription.next_billing_date;
  const due = subscription.renewal_due ?? (next !== null && next <= today);
  if (due) return { due: true, reason: null };
  return {
    due: false,
    reason: next
      ? `Not due yet: renews automatically on ${formatDate(next)}.`
      : 'No upcoming billing date to renew.',
  };
}
