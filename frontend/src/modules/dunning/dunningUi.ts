import type { BadgeProps } from '../../components/common/Badge';
import type { DunningAttemptStatus, DunningCaseStatus, DunningFinalAction } from '../../types/dunning';

type BadgeVariant = NonNullable<BadgeProps['variant']>;

export const CASE_STATUS_CONFIG: Record<DunningCaseStatus, { label: string; badge: BadgeVariant }> = {
  open: { label: 'Open', badge: 'primary' },
  retry_scheduled: { label: 'Retry Scheduled', badge: 'info' },
  retrying: { label: 'Retrying', badge: 'info' },
  paused: { label: 'Paused', badge: 'warning' },
  recovered: { label: 'Recovered', badge: 'success' },
  stopped: { label: 'Stopped', badge: 'neutral' },
  exhausted: { label: 'Exhausted', badge: 'danger' },
  finalized: { label: 'Finalized', badge: 'neutral' },
};

export const CASE_STATUS_ORDER: DunningCaseStatus[] = [
  'open',
  'retry_scheduled',
  'retrying',
  'paused',
  'recovered',
  'exhausted',
  'stopped',
  'finalized',
];

export const ACTIVE_CASE_STATUSES: DunningCaseStatus[] = ['open', 'retry_scheduled', 'retrying'];
export const TERMINAL_CASE_STATUSES: DunningCaseStatus[] = ['recovered', 'stopped', 'finalized'];

export const ATTEMPT_STATUS_CONFIG: Record<DunningAttemptStatus, { label: string; badge: BadgeVariant }> = {
  scheduled: { label: 'Scheduled', badge: 'info' },
  processing: { label: 'Processing', badge: 'primary' },
  succeeded: { label: 'Succeeded', badge: 'success' },
  failed: { label: 'Failed', badge: 'danger' },
  skipped: { label: 'Skipped', badge: 'neutral' },
};

export const FINAL_ACTION_CONFIG: Record<DunningFinalAction, { label: string; description: string }> = {
  unpaid: {
    label: 'Mark unpaid',
    description: 'Keep the subscription running; the invoice stays overdue for manual follow-up.',
  },
  suspend: {
    label: 'Suspend subscription',
    description: 'Pause the subscription until the outstanding invoice is settled.',
  },
  cancel_and_void: {
    label: 'Cancel & void',
    description: 'Cancel the subscription and void the unpaid invoice.',
  },
};

export const COMMUNICATION_TEMPLATE_LABELS: Record<string, string> = {
  failure: 'Payment failed',
  retry: 'Retry notice',
  success: 'Payment recovered',
  final_notice: 'Final notice',
  card_expiry: 'Card expiring',
};

export function caseStatusLabel(status: DunningCaseStatus): string {
  return CASE_STATUS_CONFIG[status]?.label ?? status;
}

export function caseStatusBadge(status: DunningCaseStatus): BadgeVariant {
  return CASE_STATUS_CONFIG[status]?.badge ?? 'neutral';
}
