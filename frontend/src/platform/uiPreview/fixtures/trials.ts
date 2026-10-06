/**
 * Visual-editor preview sample data for Trials (/trials). All names and addresses are fictional.
 *
 * The page lists `GET /subscriptions?status=trialing` and reads `GET /subscriptions/summary`.
 * Proration (/proration) lists the same endpoint with status=active and status=trialing, so the
 * handler below answers by status with full SubscriptionOut records (plan included).
 * Trial windows are computed relative to "now" so the timeline badges always show days left.
 */
import type { Paginated, PlanOut, SubscriptionOut, SubscriptionSummaryOut } from '../../../types/api';
import { toIsoDate } from '../../../utils/format';

const DAY = 24 * 60 * 60 * 1000;
const isoDate = (offsetDays: number) => toIsoDate(new Date(Date.now() + offsetDays * DAY));
const STAMP = '2026-09-01T09:00:00Z';

export const previewPlans: PlanOut[] = [
  {
    id: 'plan-starter', product_id: 'prod-cloud', name: 'Starter', code: 'STARTER', description: 'For small teams',
    billing_interval: 'monthly', interval_count: 1, pricing_model: 'per_unit', unit_amount: '999.00', currency: 'INR',
    setup_fee: '0.00', trial_days: 14, is_active: true, active_subscriptions: 4, created_at: STAMP, updated_at: STAMP,
  },
  {
    id: 'plan-growth', product_id: 'prod-cloud', name: 'Growth', code: 'GROWTH', description: 'For growing teams',
    billing_interval: 'monthly', interval_count: 1, pricing_model: 'per_unit', unit_amount: '2499.00', currency: 'INR',
    setup_fee: '0.00', trial_days: 14, is_active: true, active_subscriptions: 3, created_at: STAMP, updated_at: STAMP,
  },
  {
    id: 'plan-enterprise', product_id: 'prod-cloud', name: 'Enterprise', code: 'ENTERPRISE', description: 'Annual contract',
    billing_interval: 'yearly', interval_count: 1, pricing_model: 'flat', unit_amount: '120000.00', currency: 'INR',
    setup_fee: '5000.00', trial_days: 30, is_active: true, active_subscriptions: 1, created_at: STAMP, updated_at: STAMP,
  },
];

function planRef(plan: PlanOut): SubscriptionOut['plan'] {
  return {
    id: plan.id, name: plan.name, code: plan.code, billing_interval: plan.billing_interval,
    interval_count: plan.interval_count, unit_amount: plan.unit_amount, currency: plan.currency,
    product_name: 'Cloud Workspace', pricing_model: plan.pricing_model, source: 'plan',
  };
}

interface SubSeed {
  n: number;
  customer: string;
  email: string;
  plan: PlanOut;
  quantity: number;
  status: 'active' | 'trialing';
  /** Trial: days since start / days left. Active: ignored. */
  started: number;
  left: number;
}

const SEEDS: SubSeed[] = [
  { n: 2101, customer: 'Nimbus Analytics', email: 'finance@nimbus.example.in', plan: previewPlans[1], quantity: 10, status: 'trialing', started: 9, left: 5 },
  { n: 2102, customer: 'Orchid Wellness', email: 'accounts@orchid.example.in', plan: previewPlans[0], quantity: 3, status: 'trialing', started: 12, left: 2 },
  { n: 2103, customer: 'Riverbend Schools', email: 'admin@riverbend.example.in', plan: previewPlans[2], quantity: 1, status: 'trialing', started: 4, left: 26 },
  { n: 2001, customer: 'Harbor Freight Co', email: 'ap@harborfreight.example.in', plan: previewPlans[1], quantity: 25, status: 'active', started: 0, left: 0 },
  { n: 2002, customer: 'Maple Clinics', email: 'billing@mapleclinics.example.in', plan: previewPlans[0], quantity: 8, status: 'active', started: 0, left: 0 },
];

function subscription(seed: SubSeed): SubscriptionOut {
  const trial = seed.status === 'trialing';
  const start = trial ? isoDate(-seed.started) : '2026-07-01';
  const rate = (Number(seed.plan.unit_amount) * seed.quantity).toFixed(2);
  const mrr = seed.plan.billing_interval === 'yearly' ? (Number(rate) / 12).toFixed(2) : rate;
  return {
    id: `sub-preview-${seed.n}`,
    subscription_number: `SUB-${seed.n}`,
    customer: {
      id: `cust-preview-${seed.n}`, customer_number: `CUST-${seed.n}`, display_name: seed.customer, email: seed.email,
    },
    plan: planRef(seed.plan),
    quantity: seed.quantity,
    status: seed.status,
    currency: 'INR',
    pricing_model: seed.plan.pricing_model,
    unit_price: seed.plan.unit_amount,
    subtotal: rate,
    start_date: start,
    trial_start: trial ? start : null,
    trial_end: trial ? isoDate(seed.left) : null,
    current_period_start: trial ? start : '2026-10-01',
    current_period_end: trial ? isoDate(seed.left) : '2026-10-31',
    next_billing_date: trial ? isoDate(seed.left) : '2026-11-01',
    cancel_at_period_end: false,
    cancelled_at: null,
    paused_at: null,
    ended_at: null,
    notes: null,
    mrr,
    created_at: STAMP,
    updated_at: STAMP,
  };
}

function page<T>(items: T[]): Paginated<T> {
  return { items, total: items.length, page: 1, page_size: 50, total_pages: 1 };
}

/** Subscriptions by `status` (all of them without one), optionally narrowed by `search`. */
export function listPreviewSubscriptions(query: URLSearchParams): Paginated<SubscriptionOut> {
  const status = query.get('status');
  const search = (query.get('search') || '').toLowerCase();
  const items = SEEDS.map(subscription).filter(
    (s) =>
      (!status || s.status === status) &&
      (!search || [s.subscription_number, s.customer.display_name, s.plan.name].some((v) => v.toLowerCase().includes(search)))
  );
  return page(items);
}

export const previewSubscriptionSummary: SubscriptionSummaryOut = {
  total_subscriptions: SEEDS.length,
  active_count: SEEDS.filter((s) => s.status === 'active').length,
  trialing_count: SEEDS.filter((s) => s.status === 'trialing').length,
  paused_count: 0,
  past_due_count: 0,
  cancelled_count: 0,
  draft_count: 0,
  total_mrr: '86980.00',
  total_arr: '1043760.00',
  expiring_soon_count: 1,
  trial_expiring_soon_count: 2,
  auto_renew_enabled_count: SEEDS.length,
};

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/subscriptions': listPreviewSubscriptions,
  '/subscriptions/summary': () => previewSubscriptionSummary,
};
