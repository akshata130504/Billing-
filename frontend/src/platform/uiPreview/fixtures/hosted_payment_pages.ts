/**
 * Visual-editor preview sample data for Hosted Payment Pages (/hosted-payment-pages).
 * On mount the page loads GET /checkout/sessions (the list, plus one page_size=1 call per status
 * for the KPI counts), GET /checkout/templates and GET /customers (answered by the built-in
 * customer fixtures, whose ids the sessions below reference). Fictional data only.
 */
import type { Paginated } from '../../../types/api';
import type { CheckoutSession, CheckoutTemplate } from '../../../types/checkout';

/** Same ids as the built-in sample customers (sampleData.ts). */
const customerId = (n: number) => `00000000-0000-4000-a000-0000000000${String(n).padStart(2, '0')}`;

interface SessionSeed {
  n: number;
  purpose: CheckoutSession['purpose'];
  status: CheckoutSession['status'];
  amount: string;
  customer: number | null;
  created: string;
  expires: string;
}

const SESSION_SEEDS: SessionSeed[] = [
  { n: 8, purpose: 'invoice_payment', status: 'pending', amount: '21830.00', customer: 2, created: '2026-10-05T10:20:00', expires: '2026-10-06T10:20:00' },
  { n: 7, purpose: 'new_subscription', status: 'successful', amount: '8999.00', customer: 4, created: '2026-10-04T15:05:00', expires: '2026-10-05T15:05:00' },
  { n: 6, purpose: 'invoice_payment', status: 'successful', amount: '49560.00', customer: 1, created: '2026-10-03T09:40:00', expires: '2026-10-04T09:40:00' },
  { n: 5, purpose: 'one_time_addon', status: 'created', amount: '2500.00', customer: 6, created: '2026-10-02T12:00:00', expires: '2026-10-09T12:00:00' },
  { n: 4, purpose: 'invoice_payment', status: 'failed', amount: '32450.00', customer: 5, created: '2026-09-30T17:25:00', expires: '2026-10-01T17:25:00' },
  { n: 3, purpose: 'invoice_payment', status: 'expired', amount: '18408.00', customer: 1, created: '2026-09-20T08:10:00', expires: '2026-09-21T08:10:00' },
];

const sessions: CheckoutSession[] = SESSION_SEEDS.map((s) => ({
  id: `00000000-0000-4000-c000-0000000000${String(s.n).padStart(2, '0')}`,
  organization_id: 'preview-org',
  token: `ref_preview${String(s.n).padStart(4, '0')}`,
  // Listings never carry the shareable link (it is shown once, at creation).
  checkout_url: null as unknown as string,
  purpose: s.purpose,
  status: s.status,
  amount: s.amount,
  currency: 'INR',
  expires_at: s.expires,
  customer_id: s.customer ? customerId(s.customer) : null,
  invoice_id: null,
  subscription_id: null,
  plan_id: null,
  payment_attempt_id: null,
  payment_id: null,
  save_payment_method: false,
  completed_at: s.status === 'successful' ? s.created : null,
  created_at: s.created,
}));

const templates: CheckoutTemplate[] = [
  {
    id: 'preview-template-1',
    organization_id: 'preview-org',
    name: 'Standard Checkout',
    template_type: 'single_page',
    primary_color: '#2563eb',
    accent_color: '#1e40af',
    logo_url: null,
    button_text: 'Pay Now',
    allow_quantity_edit: false,
    show_order_summary: true,
    redirect_url: null,
    thank_you_message: 'Thank you! Your payment has been received.',
    error_message_template: null,
    custom_fields: null,
    is_default: true,
    is_active: true,
    created_at: '2026-06-01T09:00:00',
    updated_at: '2026-06-01T09:00:00',
  },
  {
    id: 'preview-template-2',
    organization_id: 'preview-org',
    name: 'Subscription sign-up',
    template_type: 'multi_page',
    primary_color: '#0f766e',
    accent_color: '#134e4a',
    logo_url: 'https://assets.example.com/acme-logo.png',
    button_text: 'Start subscription',
    allow_quantity_edit: true,
    show_order_summary: true,
    redirect_url: 'https://www.example.com/welcome',
    thank_you_message: null,
    error_message_template: null,
    custom_fields: null,
    is_default: false,
    is_active: true,
    created_at: '2026-08-12T14:30:00',
    updated_at: '2026-08-12T14:30:00',
  },
];

function listSessions(query: URLSearchParams): Paginated<CheckoutSession> {
  const status = query.get('status');
  const rows = sessions.filter((s) => !status || s.status === status);
  const page = Math.max(1, Number(query.get('page')) || 1);
  const pageSize = Math.max(1, Number(query.get('page_size')) || 20);
  return {
    items: rows.slice((page - 1) * pageSize, page * pageSize),
    total: rows.length,
    page,
    page_size: pageSize,
    total_pages: Math.max(1, Math.ceil(rows.length / pageSize)),
  };
}

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/checkout/sessions': listSessions,
  '/checkout/templates': () => templates,
};
