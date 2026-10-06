/**
 * Visual-editor preview sample data for Proration (/proration). All names are fictional.
 *
 * On mount the page lists `GET /subscriptions` (status=active and status=trialing; answered by the
 * status-aware handler in ./trials.ts) and `GET /plans`. Selecting a subscription loads
 * `GET /subscriptions/<id>/changes`, answered here with an empty history.
 */
import type { Paginated, PlanOut } from '../../../types/api';
import type { SubscriptionChangeOut } from '../../../types/proration';
import { listPreviewSubscriptions, previewPlans } from './trials';

const plans = (): Paginated<PlanOut> => ({
  items: previewPlans, total: previewPlans.length, page: 1, page_size: 100, total_pages: 1,
});

const noChanges = (): SubscriptionChangeOut[] => [];

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/plans': plans,
  ...Object.fromEntries(
    listPreviewSubscriptions(new URLSearchParams()).items.map((s) => [`/subscriptions/${s.id}/changes`, noChanges])
  ),
};
