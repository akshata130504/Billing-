/**
 * Rooman's own plan billing for the platform console (GET /platform/billing/*). Read-only, stored state only:
 * the server never calls Razorpay for these views and never returns secrets, signatures or webhook payloads.
 * Platform Administrator and Platform Operations only (enforced by the server).
 */
import { consoleRequest } from './platformApi';

export interface BillingPage<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export type SubscriptionFilter =
  | 'paid' | 'active' | 'cancellation_scheduled' | 'past_due' | 'cancelled' | 'expired' | 'trialing' | 'all';
export type CheckoutFilter =
  | 'open' | 'created' | 'pending' | 'unknown' | 'authorized' | 'completed' | 'failed' | 'expired' | 'all';
export type WebhookFilter = 'processed' | 'ignored' | 'needs_review' | 'all';

export interface PlatformSubscriptionRow {
  organization_id: string;
  organization_name: string | null;
  plan_code: string | null;
  plan_name: string | null;
  sandbox: boolean;
  /** Stored state. */
  state: string;
  /** What access is right now (an ended period counts even before the scheduler records it). */
  effective_state: string;
  writable: boolean;
  cancel_at_period_end: boolean;
  billing_interval: string | null;
  billing_interval_count: number | null;
  current_period_start: string | null;
  current_period_end: string | null;
  grace_period_end: string | null;
  cancelled_at: string | null;
  trial_ends_at: string | null;
  /** From the checkout that started the Razorpay subscription; null when there is none. */
  amount_minor: number | null;
  currency: string | null;
  provider_subscription_id: string | null;
  provider_mode: string | null;
  provider_paid_count: number | null;
  updated_at: string | null;
}

export interface CheckoutAttemptRow {
  id: string;
  organization_id: string;
  organization_name: string | null;
  plan_code: string;
  plan_name: string | null;
  sandbox: boolean;
  amount_minor: number;
  currency: string;
  billing_interval: string;
  billing_interval_count: number;
  seat_limit: number;
  mode: string;
  status: string;
  provider_subscription_id: string | null;
  provider_payment_id: string | null;
  created_at: string | null;
  expires_at: string | null;
  authorized_at: string | null;
  completed_at: string | null;
  last_error: string | null;
  webhook_review: boolean;
  /** Latest durable review finding for this checkout (callback, webhook or reconciliation). */
  review_reason: string | null;
  /** When the checkout was first flagged for review. */
  review_flagged_at: string | null;
  stuck: boolean;
}

export interface WebhookEventRow {
  id: string;
  event_id: string;
  event_type: string;
  mode: string | null;
  status: string;
  outcome: string | null;
  provider_subscription_id: string | null;
  provider_payment_id: string | null;
  organization_id: string | null;
  organization_name: string | null;
  event_created_at: string | null;
  received_at: string | null;
}

export type ReviewCaseStatus = 'open' | 'resolved';
export type ReviewFilter = 'open' | 'resolved' | 'all';
export type ReviewResolutionCategory =
  | 'no_action_needed' | 'resolved_by_payment_lifecycle' | 'handled_in_razorpay' | 'customer_contacted'
  | 'duplicate_case' | 'other';

export const RESOLUTION_CATEGORY_LABELS: Record<ReviewResolutionCategory, string> = {
  no_action_needed: 'No action needed',
  resolved_by_payment_lifecycle: 'Resolved by the normal payment flow',
  handled_in_razorpay: 'Handled in the Razorpay dashboard',
  customer_contacted: 'Customer contacted',
  duplicate_case: 'Duplicate of another case',
  other: 'Other',
};

export interface ResolveReviewBody {
  category: ReviewResolutionCategory;
  reason: string;
  ticket_ref?: string;
}

export interface ReviewItem {
  source: 'checkout_review' | 'webhook_needs_review' | 'checkout_unknown' | 'checkout_authorized_stuck' | string;
  explanation: string;
  detected_at: string | null;
  organization_id: string | null;
  organization_name: string | null;
  /** Stored review case (checkout_review); null for state-derived signals, which cannot be resolved. */
  case_id: string | null;
  case_status: ReviewCaseStatus | null;
  /** Only open stored cases can be resolved. */
  resolvable: boolean;
  /** checkout_review: the finding that opened the case, and the latest one. */
  first_reason: string | null;
  review_reason: string | null;
  finding_count: number | null;
  /** checkout_review: when the case was opened, and when a finding was last seen. */
  flagged_at: string | null;
  last_seen_at: string | null;
  resolution_category: ReviewResolutionCategory | null;
  resolution_note: string | null;
  resolution_ticket_ref: string | null;
  resolved_at: string | null;
  resolved_by_email: string | null;
  resolved_by_role: string | null;
  checkout_status: string | null;
  outcome: string | null;
  event_type: string | null;
  checkout_attempt_id: string | null;
  provider_subscription_id: string | null;
  provider_payment_id: string | null;
  mode: string | null;
}

export interface ReviewQueuePage extends BillingPage<ReviewItem> {
  /** Review outcomes the application logs and alerts but does not store, so they cannot be listed. */
  untracked_sources: string[];
}

export type NotificationStatus = 'pending' | 'sent' | 'failed' | 'superseded';
export type NotificationFilter = NotificationStatus | 'all';
export type NotificationKind =
  | 'subscription_activated' | 'renewal_payment_received' | 'payment_past_due' | 'access_expired'
  | 'cancellation_scheduled' | 'cancelled_immediately' | 'cancellation_effective';

export const NOTIFICATION_KIND_LABELS: Record<NotificationKind, string> = {
  subscription_activated: 'Plan activated (payment confirmed)',
  renewal_payment_received: 'Renewal payment received',
  payment_past_due: 'Renewal payment not confirmed',
  access_expired: 'Plan expired (read-only)',
  cancellation_scheduled: 'Cancellation scheduled',
  cancelled_immediately: 'Cancelled immediately',
  cancellation_effective: 'Plan ended as scheduled',
};

/** One lifecycle email's delivery record. Never the email content or the full recipient address. */
export interface NotificationRow {
  id: string;
  kind: NotificationKind | string;
  /** `sent` = Rooman's SMTP server accepted it; not proof that it reached or was read in an inbox. */
  status: NotificationStatus;
  attempts: number;
  organization_id: string;
  organization_name: string | null;
  /** Masked, e.g. "o***@example.test". */
  recipient_hint: string | null;
  created_at: string | null;
  updated_at: string | null;
  sent_at: string | null;
  /** Pending emails only. */
  next_attempt_at: string | null;
  /** Allow-listed category (or "unclassified") and its description; never a server reply. */
  error_code: string | null;
  error_label: string | null;
}

export interface NotificationPage extends BillingPage<NotificationRow> {
  status_counts: Record<NotificationStatus, number>;
}

export const PAGE_SIZE = 25;

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

export const billingApi = {
  subscriptions: (p: { status: SubscriptionFilter; organization?: string; page: number }) =>
    consoleRequest<BillingPage<PlatformSubscriptionRow>>(
      'GET', `/billing/subscriptions${query({ ...p, page_size: PAGE_SIZE })}`),
  checkoutAttempts: (p: { status: CheckoutFilter; mode?: string; organization?: string; page: number }) =>
    consoleRequest<BillingPage<CheckoutAttemptRow>>(
      'GET', `/billing/checkout-attempts${query({ ...p, page_size: PAGE_SIZE })}`),
  webhookEvents: (p: { status: WebhookFilter; event_type?: string; organization?: string; page: number }) =>
    consoleRequest<BillingPage<WebhookEventRow>>(
      'GET', `/billing/webhook-events${query({ ...p, page_size: PAGE_SIZE })}`),
  reviewQueue: (p: { status: ReviewFilter; organization?: string; page: number }) =>
    consoleRequest<ReviewQueuePage>('GET', `/billing/review-queue${query({ ...p, page_size: PAGE_SIZE })}`),
  /** Read-only delivery status of Rooman's subscription emails. */
  notifications: (p: { status: NotificationFilter; kind?: NotificationKind | ''; organization?: string; page: number }) =>
    consoleRequest<NotificationPage>('GET', `/billing/notifications${query({ ...p, page_size: PAGE_SIZE })}`),
  /** Records a review resolution only: it never approves, refunds, retries or changes a payment. */
  resolveReviewCase: (caseId: string, body: ResolveReviewBody) =>
    consoleRequest<ReviewItem>('POST', `/billing/review-cases/${encodeURIComponent(caseId)}/resolve`, body),
};
