import type { BadgeVariant } from '../../utils/format';
import type {
  ProrationEffectiveType,
  SubscriptionChangeStatus,
  SubscriptionChangeType,
} from '../../types/proration';

export const CHANGE_TYPE_LABELS: Record<SubscriptionChangeType, string> = {
  upgrade: 'Upgrade',
  downgrade: 'Downgrade',
  quantity_change: 'Quantity change',
  addon_change: 'Add-on change',
  cancellation: 'Cancellation',
};

export const CHANGE_TYPE_VARIANTS: Record<SubscriptionChangeType, BadgeVariant> = {
  upgrade: 'success',
  downgrade: 'warning',
  quantity_change: 'info',
  addon_change: 'primary',
  cancellation: 'danger',
};

export const CHANGE_STATUS_VARIANTS: Record<SubscriptionChangeStatus, BadgeVariant> = {
  previewed: 'neutral',
  scheduled: 'warning',
  applied: 'success',
  cancelled: 'neutral',
  failed: 'danger',
};

export const EFFECTIVE_TYPE_LABELS: Record<ProrationEffectiveType, string> = {
  immediate: 'Immediately',
  end_of_term: 'At end of term',
  scheduled: 'From a specific date',
};

export function changeTypeLabel(type: string): string {
  return CHANGE_TYPE_LABELS[type as SubscriptionChangeType] ?? type.replace(/_/g, ' ');
}

export function changeTypeVariant(type: string): BadgeVariant {
  return CHANGE_TYPE_VARIANTS[type as SubscriptionChangeType] ?? 'neutral';
}

export function changeStatusVariant(status: string): BadgeVariant {
  return CHANGE_STATUS_VARIANTS[status as SubscriptionChangeStatus] ?? 'neutral';
}

/** "5.000" → "5", "2.500" → "2.5" */
export function formatQuantity(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return Number.isInteger(n) ? String(n) : String(n);
}

const INTERVAL_LABELS: Record<string, string> = {
  one_time: 'one-time',
  monthly: 'month',
  quarterly: 'quarter',
  semiannual: 'half-year',
  yearly: 'year',
};

export function intervalLabel(interval: string | undefined, count = 1): string {
  const base = INTERVAL_LABELS[interval ?? ''] ?? (interval ?? '');
  if (!base || base === 'one-time') return base;
  return count > 1 ? `${count} ${base}s` : base;
}

/** Months per billing period, mirroring the backend's `interval_months`. */
const INTERVAL_MONTHS: Record<string, number> = {
  monthly: 1,
  quarterly: 3,
  semiannual: 6,
  yearly: 12,
};

export function intervalMonths(interval: string | undefined, count = 1): number | null {
  const months = INTERVAL_MONTHS[interval ?? ''];
  if (!months) return null; // one_time or unknown: not comparable per-month
  return months * Math.max(1, count || 1);
}

/**
 * A plan's price normalised to one month, so plans on different billing
 * intervals can be ranked against each other. Comparing raw `unit_amount`
 * calls a 24,000/year plan an "upgrade" over a 2,500/month one when it is
 * actually cheaper per month.
 */
export function monthlyEquivalent(
  unitAmount: string | number | null | undefined,
  interval: string | undefined,
  count = 1
): number | null {
  // Number(null) and Number('') are 0, which would rank a plan with no price as
  // the cheapest. Absent means not comparable, not free.
  if (unitAmount === null || unitAmount === undefined) return null;
  if (typeof unitAmount === 'string' && unitAmount.trim() === '') return null;
  const amount = Number(unitAmount);
  if (!Number.isFinite(amount)) return null;
  const months = intervalMonths(interval, count);
  if (!months) return null;
  return amount / months;
}
