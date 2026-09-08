import type { BadgeVariant } from '../../utils/format';
import type { AgingBucket, CollectionActivityType, CollectionStatus, PromiseToPayStatus } from '../../types/collections';

/** Badge variant for each collection status, matching the rest of the app's semantics. */
export const COLLECTION_STATUS_VARIANTS: Record<CollectionStatus, BadgeVariant> = {
  current: 'success',
  due_soon: 'warning',
  overdue: 'danger',
  in_follow_up: 'primary',
  promise_to_pay: 'primary',
  disputed: 'danger',
  escalated: 'danger',
  collected: 'success',
  written_off: 'neutral',
};

export const COLLECTION_STATUS_LABELS: Record<CollectionStatus, string> = {
  current: 'Current',
  due_soon: 'Due Soon',
  overdue: 'Overdue',
  in_follow_up: 'In Follow-up',
  promise_to_pay: 'Promise to Pay',
  disputed: 'Disputed',
  escalated: 'Escalated',
  collected: 'Collected',
  written_off: 'Written Off',
};

export const AGING_BUCKET_LABELS: Record<AgingBucket, string> = {
  current: 'Current',
  '1_30': '1-30 Days',
  '31_60': '31-60 Days',
  '61_90': '61-90 Days',
  '90_plus': '90+ Days',
};

export const ACTIVITY_TYPE_LABELS: Record<CollectionActivityType, string> = {
  email_sent: 'Email Sent',
  phone_call: 'Phone Call',
  reminder: 'Reminder',
  payment_promise: 'Payment Promise',
  customer_contacted: 'Customer Contacted',
  dispute_raised: 'Dispute Raised',
  dispute_resolved: 'Dispute Resolved',
  internal_note: 'Internal Note',
};

export const PROMISE_STATUS_VARIANTS: Record<PromiseToPayStatus, BadgeVariant> = {
  pending: 'warning',
  kept: 'success',
  broken: 'danger',
  cancelled: 'neutral',
};

export const PROMISE_STATUS_LABELS: Record<PromiseToPayStatus, string> = {
  pending: 'Pending',
  kept: 'Kept',
  broken: 'Broken',
  cancelled: 'Cancelled',
};
