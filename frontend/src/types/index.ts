/**
 * UI-only types live here. Everything that mirrors the API contract lives in
 * `./api` and is re-exported so consumers can import from '@/types' or './api'.
 */
export * from './api';

import type { SearchCategory } from './api';

/** Dashboard date range selector (includes the client-side 'custom' option). */
export type DateRangeFilter =
  | 'today'
  | '7_days'
  | '30_days'
  | '3_months'
  | '12_months'
  | 'custom';

/** Dashboard widget toggle configuration. */
export interface WidgetVisibilityState {
  revenueIntelligence: boolean;
  actionCenter: boolean;
  billingPipeline: boolean;
  customerHealth: boolean;
  paymentRecovery: boolean;
  recentTransactions: boolean;
  activityTimeline: boolean;
}

/** Activity feed filter — 'all' plus the four server categories. */
export type ActivityCategory = 'all' | 'billing' | 'customers' | 'payments' | 'system';

/** Search modal filter — 'all' plus the server categories. */
export type SearchCategoryFilter = 'all' | SearchCategory;
