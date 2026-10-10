/**
 * Visual-editor preview sample data for Proration (/proration). All names are fictional.
 *
 * On mount the page lists `GET /subscriptions` (status=active and status=trialing; answered by the
 * status-aware handler in ./trials.ts), `GET /plans` and `GET /subscriptions/plan-options` (the
 * upgrade/downgrade picker: legacy plans plus a Plans & Pricing plan offering). Selecting a subscription loads
 * `GET /subscriptions/<id>/changes`, answered here with an empty history.
 */
import type { Paginated, PlanOut, SubscribablePlanOption } from '../../../types/api';
import type { SubscriptionChangeOut } from '../../../types/proration';
import { listPreviewSubscriptions, previewPlans } from './trials';

const plans = (): Paginated<PlanOut> => ({
  items: previewPlans, total: previewPlans.length, page: 1, page_size: 100, total_pages: 1,
});

const planOption = (p: PlanOut): SubscribablePlanOption => ({
  id: p.id, source: 'plan', plan_id: p.id, offering_id: null, name: p.name, code: p.code, product_name: 'Cloud Workspace',
  billing_interval: p.billing_interval, interval_count: p.interval_count, pricing_model: p.pricing_model,
  unit_amount: p.unit_amount, currency: p.currency, tax_rate_pct: '18.00', trial_days: p.trial_days, pricing_tiers: [],
  is_active: p.is_active,
});

export const previewPlanOptions: SubscribablePlanOption[] = [
  ...previewPlans.map(planOption),
  {
    id: 'off-1', source: 'offering', plan_id: null, offering_id: 'off-1', name: 'Cloud ERP Pro', code: 'PRO-ERP-01',
    product_name: 'Cloud ERP Pro', billing_interval: 'monthly', interval_count: 1, pricing_model: 'flat',
    unit_amount: '4999.00', currency: 'INR', tax_rate_pct: '18.00', trial_days: 0, pricing_tiers: [], is_active: true,
  },
];

const noChanges = (): SubscriptionChangeOut[] => [];

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/plans': plans,
  '/subscriptions/plan-options': () => previewPlanOptions,
  ...Object.fromEntries(
    listPreviewSubscriptions(new URLSearchParams()).items.map((s) => [`/subscriptions/${s.id}/changes`, noChanges])
  ),
};
