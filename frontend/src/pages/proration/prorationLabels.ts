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
