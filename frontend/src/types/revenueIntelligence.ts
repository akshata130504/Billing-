import type { ReportRangeKey } from './reports';

/** Display labels for the report range keys, in menu order. */
export const REVENUE_RANGE_OPTIONS: { value: ReportRangeKey; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'this_week', label: 'This Week' },
  { value: 'this_month', label: 'This Month' },
  { value: 'last_month', label: 'Last Month' },
  { value: 'this_quarter', label: 'This Quarter' },
  { value: 'this_year', label: 'This Year' },
  { value: 'last_12_months', label: 'Last 12 Months' },
  { value: 'custom', label: 'Custom Range' },
];

/**
 * What GET /subscriptions/summary actually returns today. The shared
 * `SubscriptionSummaryOut` type in types/api.ts lists extra fields
 * (total_arr, past_due_count, draft_count, expiring_soon_count, ...) that the
 * backend does not send, and omits `renewing_soon_count` which it does — so
 * the page normalises the live payload into this shape instead.
 */
export interface SubscriptionMix {
  total: number;
  active: number;
  trialing: number;
  paused: number;
  pastDue: number;
  cancelled: number;
  renewingSoon: number;
  /** Monthly recurring revenue as a number (0 when unparseable). */
  mrr: number;
  /** Annual recurring revenue: the API's figure when present, otherwise MRR × 12. */
  arr: number;
  /** True when `arr` was derived from MRR rather than reported by the API. */
  arrDerived: boolean;
}

export type InsightTone = 'positive' | 'neutral' | 'caution' | 'critical';

export interface Insight {
  id: string;
  tone: InsightTone;
  title: string;
  detail: string;
}
