/**
 * Visual-editor preview sample data for Customer Lifecycle (/customer-lifecycle).
 * All names and e-mail addresses are fictional.
 *
 * On mount the page reads `GET /lifecycle/kpis` and `GET /lifecycle` (stage / health / search
 * filters are honoured so the filter controls behave in the preview).
 */
import type { CustomerLifecycleItem, LifecycleKPIs } from '../../../types/api';

interface Seed {
  n: number;
  name: string;
  company: string | null;
  stage: CustomerLifecycleItem['lifecycle_stage'];
  health: CustomerLifecycleItem['health_status'];
  score: number;
  spent: string;
  due: string;
  subs: number;
  hours: string;
  next: string | null;
}

const SEEDS: Seed[] = [
  { n: 1, name: 'Nimbus Analytics', company: 'Nimbus Analytics Pvt Ltd', stage: 'onboarding', health: 'healthy', score: 82, spent: '24990.00', due: '0.00', subs: 1, hours: '12.5', next: 'Kick-off call with finance team' },
  { n: 2, name: 'Harbor Freight Co', company: 'Harbor Freight Co LLP', stage: 'active', health: 'healthy', score: 91, spent: '412500.00', due: '0.00', subs: 3, hours: '64.0', next: null },
  { n: 3, name: 'Maple Clinics', company: null, stage: 'renewal_due', health: 'neutral', score: 68, spent: '158400.00', due: '19992.00', subs: 1, hours: '8.0', next: 'Send renewal quote' },
  { n: 4, name: 'Orchid Wellness', company: 'Orchid Wellness Pvt Ltd', stage: 'at_risk', health: 'at_risk', score: 41, spent: '36000.00', due: '11800.00', subs: 1, hours: '3.5', next: 'Schedule account review' },
  { n: 5, name: 'Riverbend Schools', company: 'Riverbend Education Trust', stage: 'expansion', health: 'healthy', score: 88, spent: '240000.00', due: '0.00', subs: 2, hours: '21.0', next: 'Propose additional campus seats' },
  { n: 6, name: 'Copperleaf Studio', company: null, stage: 'prospect', health: 'neutral', score: 55, spent: '0.00', due: '0.00', subs: 0, hours: '0.0', next: 'Share product demo recording' },
];

const STAMP = '2026-09-15T09:00:00Z';

export const previewLifecycles: CustomerLifecycleItem[] = SEEDS.map((s) => ({
  id: `lc-preview-${s.n}`,
  customer_id: `cust-lc-preview-${s.n}`,
  customer_name: s.name,
  customer_number: `CUST-${String(300 + s.n).padStart(5, '0')}`,
  customer_email: `accounts@${s.name.toLowerCase().replace(/[^a-z]+/g, '')}.example.in`,
  company_name: s.company,
  lifecycle_stage: s.stage,
  stage_entered_at: STAMP,
  health_status: s.health,
  health_score: s.score,
  next_action: s.next,
  next_action_due: null,
  notes: null,
  total_spent: s.spent,
  amount_due: s.due,
  active_subscriptions_count: s.subs,
  total_invoices_count: s.subs * 3,
  total_quotes_count: 1,
  total_billable_hours: s.hours,
  last_activity_at: STAMP,
  created_at: STAMP,
  updated_at: STAMP,
}));

const count = (stage: Seed['stage']) => SEEDS.filter((s) => s.stage === stage).length;

export const previewLifecycleKpis: LifecycleKPIs = {
  total_customers: SEEDS.length,
  new_onboarding_count: count('onboarding'),
  active_customers_count: count('active'),
  renewal_due_count: count('renewal_due'),
  at_risk_count: count('at_risk'),
  churned_count: count('churned'),
  expansion_count: count('expansion'),
};

function listLifecycles(query: URLSearchParams): CustomerLifecycleItem[] {
  const stage = query.get('stage');
  const health = query.get('health');
  const search = (query.get('search') || '').toLowerCase();
  return previewLifecycles.filter(
    (i) =>
      (!stage || i.lifecycle_stage === stage) &&
      (!health || i.health_status === health) &&
      (!search || [i.customer_name, i.customer_number, i.company_name ?? '', i.customer_email ?? ''].some((v) => v.toLowerCase().includes(search)))
  );
}

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/lifecycle': listLifecycles,
  '/lifecycle/kpis': () => previewLifecycleKpis,
};
