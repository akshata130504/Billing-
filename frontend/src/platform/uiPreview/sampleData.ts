/**
 * Sample data and a network-free axios adapter for the Super Admin visual-editor preview.
 *
 * The preview renders the REAL tenant page components with no tenant session. Installing
 * `apiClient.defaults.adapter = previewAdapter` answers every request locally:
 *
 * - GET requests the previewed pages make are answered from the FICTIONAL fixtures below
 *   (typed with the app's own interfaces so the shapes stay in sync with the pages).
 * - Unknown GET paths reject with a 404 envelope, so pages show their normal error state.
 * - Every other method rejects with 403 PREVIEW_READ_ONLY. Nothing is ever sent: this adapter
 *   never calls the network and never falls back to axios' default adapter.
 *
 * All names, numbers, GSTINs and e-mail addresses are made up (example.com / example.in).
 */
import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import type {
  ActionCenterResponse,
  ActivityItem,
  CustomerOut,
  CustomerRef,
  DashboardSummary,
  Paginated,
  PaymentOut,
} from '../../types/api';
import type { Invoice, InvoiceKPIs, InvoiceStatus } from '../../types/invoices';
import type { CatalogSummary, DealsSummary, FinancialSummary, QuotesSummary } from '../../services/dashboardSummaryService';
import type { UiConfigBundle } from '../../appUi/UiConfigContext';
import type {
  NotificationPreferencesResponse,
  NotificationReadStateItem,
} from '../../services/notificationService';
import type { PlatformAccessGrant } from '../../services/platformAccessService';

// ---------------------------------------------------------------------------
// Customers
// ---------------------------------------------------------------------------

interface CustomerSeed {
  n: number;
  name: string;
  company: string;
  email: string;
  city: string;
  state: string;
  gstin: string | null;
  terms: number;
  status: CustomerOut['status'];
  created: string;
}

const CUSTOMER_SEEDS: CustomerSeed[] = [
  { n: 1, name: 'Acme Traders', company: 'Acme Traders Pvt Ltd', email: 'accounts@acmetraders.example.in', city: 'Bengaluru', state: 'Karnataka', gstin: '29AAACA0000A1Z5', terms: 30, status: 'active', created: '2026-09-28T10:15:00Z' },
  { n: 2, name: 'Sunrise Foods', company: 'Sunrise Foods LLP', email: 'billing@sunrisefoods.example.in', city: 'Pune', state: 'Maharashtra', gstin: '27AAFCS0000B1Z2', terms: 15, status: 'active', created: '2026-09-20T08:40:00Z' },
  { n: 3, name: 'Lotus Textiles', company: 'Lotus Textiles Pvt Ltd', email: 'finance@lotustextiles.example.in', city: 'Surat', state: 'Gujarat', gstin: '24AABCL0000C1Z9', terms: 30, status: 'active', created: '2026-09-12T12:05:00Z' },
  { n: 4, name: 'Greenleaf Organics', company: 'Greenleaf Organics', email: 'hello@greenleaf.example.in', city: 'Mysuru', state: 'Karnataka', gstin: null, terms: 0, status: 'active', created: '2026-08-30T09:30:00Z' },
  { n: 5, name: 'Bluewave Logistics', company: 'Bluewave Logistics Pvt Ltd', email: 'ap@bluewave.example.in', city: 'Chennai', state: 'Tamil Nadu', gstin: '33AACCB0000D1Z1', terms: 45, status: 'active', created: '2026-08-18T14:20:00Z' },
  { n: 6, name: 'Saffron Studio', company: 'Saffron Design Studio', email: 'studio@saffron.example.in', city: 'Hyderabad', state: 'Telangana', gstin: '36AAHFS0000E1Z7', terms: 15, status: 'active', created: '2026-08-02T11:00:00Z' },
  { n: 7, name: 'Peacock Handicrafts', company: 'Peacock Handicrafts', email: 'orders@peacock.example.in', city: 'Jaipur', state: 'Rajasthan', gstin: '08AAJFP0000F1Z3', terms: 30, status: 'inactive', created: '2026-07-21T07:45:00Z' },
  { n: 8, name: 'Monsoon Cafe', company: 'Monsoon Cafe & Bakery', email: 'owner@monsooncafe.example.in', city: 'Kochi', state: 'Kerala', gstin: null, terms: 0, status: 'inactive', created: '2026-07-04T16:10:00Z' },
];

const customerId = (n: number) => `00000000-0000-4000-a000-0000000000${String(n).padStart(2, '0')}`;
const customerNumber = (n: number) => `CUST-${String(n).padStart(5, '0')}`;

export const sampleCustomers: CustomerOut[] = CUSTOMER_SEEDS.map((s) => ({
  id: customerId(s.n),
  customer_number: customerNumber(s.n),
  display_name: s.name,
  company_name: s.company,
  email: s.email,
  phone: `+91 98450 0${String(s.n).padStart(4, '0')}`,
  website: null,
  gstin: s.gstin,
  pan: s.gstin ? s.gstin.slice(2, 12) : null,
  tax_exempt: false,
  currency: 'INR',
  payment_terms_days: s.terms,
  status: s.status,
  billing_address_line1: `${10 + s.n}, Sample Industrial Area`,
  billing_address_line2: null,
  billing_city: s.city,
  billing_state: s.state,
  billing_postal_code: '560001',
  billing_country: 'IN',
  notes: null,
  portal_url: null,
  contacts: [],
  created_at: s.created,
  updated_at: s.created,
}));

function customerRef(n: number): CustomerRef {
  const c = sampleCustomers[n - 1];
  return { id: c.id, customer_number: c.customer_number, display_name: c.display_name, email: c.email };
}

// ---------------------------------------------------------------------------
// Invoices
// ---------------------------------------------------------------------------

interface InvoiceSeed {
  n: number;
  customer: number;
  status: InvoiceStatus;
  subtotal: number;
  paid: number;
  issue: string;
  due: string;
}

const INVOICE_SEEDS: InvoiceSeed[] = [
  { n: 1048, customer: 1, status: 'paid', subtotal: 42000, paid: 49560, issue: '2026-10-03', due: '2026-11-02' },
  { n: 1047, customer: 2, status: 'sent', subtotal: 18500, paid: 0, issue: '2026-10-01', due: '2026-10-16' },
  { n: 1046, customer: 3, status: 'partially_paid', subtotal: 65000, paid: 30000, issue: '2026-09-27', due: '2026-10-27' },
  { n: 1045, customer: 5, status: 'overdue', subtotal: 27500, paid: 0, issue: '2026-08-14', due: '2026-09-28' },
  { n: 1044, customer: 4, status: 'paid', subtotal: 9800, paid: 11564, issue: '2026-09-22', due: '2026-09-22' },
  { n: 1043, customer: 6, status: 'draft', subtotal: 35000, paid: 0, issue: '2026-09-20', due: '2026-10-05' },
  { n: 1042, customer: 2, status: 'paid', subtotal: 21000, paid: 24780, issue: '2026-09-15', due: '2026-09-30' },
  { n: 1041, customer: 1, status: 'overdue', subtotal: 15600, paid: 0, issue: '2026-08-05', due: '2026-09-04' },
  { n: 1040, customer: 7, status: 'void', subtotal: 8000, paid: 0, issue: '2026-07-28', due: '2026-08-27' },
];

const money = (value: number) => value.toFixed(2);

export const sampleInvoices: Invoice[] = INVOICE_SEEDS.map((s) => {
  const tax = Math.round(s.subtotal * 0.18 * 100) / 100;
  const total = s.subtotal + tax;
  const due = s.status === 'void' || s.status === 'paid' ? 0 : total - s.paid;
  const c = sampleCustomers[s.customer - 1];
  return {
    id: `00000000-0000-4000-b000-00000000${s.n}`,
    invoice_number: `INV-${s.n}`,
    customer_id: c.id,
    customer: {
      id: c.id,
      customer_number: c.customer_number,
      display_name: c.display_name,
      email: c.email ?? undefined,
    },
    status: s.status,
    issue_date: s.issue,
    due_date: s.due,
    currency: 'INR',
    subtotal: money(s.subtotal),
    discount_pct: '0.00',
    discount_amount: '0.00',
    tax_amount: money(tax),
    cgst_amount: money(tax / 2),
    sgst_amount: money(tax / 2),
    igst_amount: '0.00',
    total: money(total),
    amount_paid: money(s.paid),
    amount_due: money(due),
    items: [],
    created_at: `${s.issue}T09:00:00Z`,
    updated_at: `${s.issue}T09:00:00Z`,
  };
});

function countStatus(status: string): number {
  return sampleInvoices.filter((i) => i.status === status).length;
}

export const sampleInvoiceKpis: InvoiceKPIs = {
  total_invoices: sampleInvoices.length,
  draft_count: countStatus('draft'),
  sent_count: countStatus('sent'),
  partially_paid_count: countStatus('partially_paid'),
  paid_count: countStatus('paid'),
  overdue_count: countStatus('overdue'),
  void_count: countStatus('void'),
  total_outstanding: sampleInvoices.reduce((sum, i) => sum + Number(i.amount_due), 0),
  total_revenue: sampleInvoices
    .filter((i) => i.status !== 'void')
    .reduce((sum, i) => sum + Number(i.amount_paid), 0),
};

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

function samplePayment(n: number, customer: number, amount: number, invoice: number, paidAt: string): PaymentOut {
  return {
    id: `00000000-0000-4000-c000-0000000000${String(n).padStart(2, '0')}`,
    payment_number: `PAY-${String(300 + n).padStart(5, '0')}`,
    customer: customerRef(customer),
    amount: money(amount),
    currency: 'INR',
    method: n % 2 === 0 ? 'upi' : 'bank_transfer',
    gateway: 'manual',
    status: 'succeeded',
    reconciliation_status: 'matched',
    gateway_order_id: null,
    gateway_payment_id: null,
    gateway_signature_verified: false,
    reference: `UTR${String(880000 + n)}`,
    paid_at: paidAt,
    failure_reason: null,
    notes: null,
    amount_refunded: '0.00',
    amount_allocated: money(amount),
    amount_unallocated: '0.00',
    allocations: [
      {
        id: `00000000-0000-4000-d000-0000000000${String(n).padStart(2, '0')}`,
        invoice_id: `00000000-0000-4000-b000-00000000${invoice}`,
        invoice_number: `INV-${invoice}`,
        amount: money(amount),
      },
    ],
    refunds: [],
    recorded_by: null,
    created_at: paidAt,
    updated_at: paidAt,
  };
}

const sampleActivity: ActivityItem[] = [
  { id: 'act-1', title: 'Payment received', description: '₹49,560.00 from Acme Traders for INV-1048', timestamp: '2026-10-04T11:20:00Z', category: 'payments', severity: 'success', entity_type: 'payment', entity_id: null },
  { id: 'act-2', title: 'Invoice sent', description: 'INV-1047 sent to Sunrise Foods', timestamp: '2026-10-01T09:05:00Z', category: 'billing', severity: 'normal', entity_type: 'invoice', entity_id: null },
  { id: 'act-3', title: 'Invoice overdue', description: 'INV-1045 for Bluewave Logistics is past due', timestamp: '2026-09-29T00:00:00Z', category: 'billing', severity: 'warning', entity_type: 'invoice', entity_id: null },
  { id: 'act-4', title: 'New customer', description: 'Acme Traders was added', timestamp: '2026-09-28T10:15:00Z', category: 'customers', severity: 'normal', entity_type: 'customer', entity_id: null },
  { id: 'act-5', title: 'Partial payment', description: '₹30,000.00 from Lotus Textiles for INV-1046', timestamp: '2026-09-27T15:40:00Z', category: 'payments', severity: 'success', entity_type: 'payment', entity_id: null },
];

const TREND: Array<[string, string, number, number]> = [
  ['Nov 2025', '2025-11-01', 182000, 196000],
  ['Dec 2025', '2025-12-01', 175500, 188000],
  ['Jan 2026', '2026-01-01', 198000, 210500],
  ['Feb 2026', '2026-02-01', 204500, 215000],
  ['Mar 2026', '2026-03-01', 231000, 242000],
  ['Apr 2026', '2026-04-01', 219000, 236500],
  ['May 2026', '2026-05-01', 245500, 251000],
  ['Jun 2026', '2026-06-01', 252000, 268000],
  ['Jul 2026', '2026-07-01', 266500, 274000],
  ['Aug 2026', '2026-08-01', 259000, 281500],
  ['Sep 2026', '2026-09-01', 284000, 297000],
  ['Oct 2026', '2026-10-01', 61124, 71780],
];

export const sampleDashboardSummary: DashboardSummary = {
  currency: 'INR',
  metrics: {
    total_revenue: '284000.00',
    revenue_change_pct: '9.7',
    outstanding_amount: '120120.00',
    outstanding_count: 4,
    overdue_count: 2,
    active_customers: 6,
    new_customers: 3,
    at_risk_amount: '50858.00',
    at_risk_count: 2,
  },
  revenue: {
    mrr: '86500.00',
    arr: '1038000.00',
    mrr_change_pct: '4.2',
    mrr_currency: 'INR',
    mrr_other_currencies: {},
    trend: TREND.map(([label, period_start, revenue, invoiced]) => ({
      label,
      period_start,
      revenue: money(revenue),
      invoiced: money(invoiced),
    })),
  },
  pipeline: {
    draft: { count: 1, amount: '41300.00' },
    sent: { count: 1, amount: '21830.00' },
    partially_paid: { count: 1, amount: '46700.00' },
    overdue: { count: 2, amount: '50858.00' },
    paid_this_period: { count: 3, amount: '85904.00' },
  },
  customer_health: {
    active: 6,
    trialing: 1,
    past_due: 1,
    paused: 0,
    cancelled_this_period: 0,
    churned_customers: 0,
    customers_at_period_start: 5,
    churn_rate: '0.00',
  },
  recovery: {
    failed_payments: 1,
    failed_amount: '18408.00',
    recovered_amount: '12500.00',
    reminders_sent: 4,
  },
  recent_transactions: [
    samplePayment(1, 1, 49560, 1048, '2026-10-04T11:20:00Z'),
    samplePayment(2, 3, 30000, 1046, '2026-09-27T15:40:00Z'),
    samplePayment(3, 2, 24780, 1042, '2026-09-25T10:00:00Z'),
    samplePayment(4, 4, 11564, 1044, '2026-09-22T13:30:00Z'),
  ],
  activity: sampleActivity,
};

export const sampleActionCenter: ActionCenterResponse = {
  items: [
    {
      id: 'ac-1',
      category: 'overdue',
      title: 'INV-1045 is overdue',
      description: 'Bluewave Logistics — 7 days past due',
      amount: '32450.00',
      customer: customerRef(5),
      entity_type: 'invoice',
      entity_id: '00000000-0000-4000-b000-000000001045',
      due_info: '7 days overdue',
      urgency: 'high',
      suggested_action: 'send_reminder',
    },
    {
      id: 'ac-2',
      category: 'overdue',
      title: 'INV-1041 is overdue',
      description: 'Acme Traders — 31 days past due',
      amount: '18408.00',
      customer: customerRef(1),
      entity_type: 'invoice',
      entity_id: '00000000-0000-4000-b000-000000001041',
      due_info: '31 days overdue',
      urgency: 'critical',
      suggested_action: 'send_reminder',
    },
    {
      id: 'ac-3',
      category: 'expiring_trial',
      title: 'Trial ending soon',
      description: 'Saffron Studio — Growth plan trial',
      amount: null,
      customer: customerRef(6),
      entity_type: 'subscription',
      entity_id: '00000000-0000-4000-e000-000000000001',
      due_info: 'Ends in 3 days',
      urgency: 'medium',
      suggested_action: 'convert_trial',
    },
  ],
  counts: { overdue: 2, failed_payment: 0, expiring_trial: 1, pending_quote: 0, pending_approval: 0 },
};

export const sampleFinancialSummary: FinancialSummary = {
  base_currency: 'INR',
  date_from: '2026-09-05',
  date_to: '2026-10-05',
  invoices: {
    total_count: sampleInvoices.length,
    by_status: {
      draft: sampleInvoiceKpis.draft_count,
      sent: sampleInvoiceKpis.sent_count,
      partially_paid: sampleInvoiceKpis.partially_paid_count,
      paid: sampleInvoiceKpis.paid_count,
      overdue: sampleInvoiceKpis.overdue_count,
      void: sampleInvoiceKpis.void_count ?? 0,
    },
    by_currency: [
      {
        currency: 'INR',
        count: sampleInvoices.length,
        total: '285736.00',
        amount_paid: '115904.00',
        amount_due: '120120.00',
        by_status: {},
      },
    ],
  },
  receivables: [
    { currency: 'INR', open_count: 4, amount_due: '120120.00', overdue_count: 2, overdue_amount: '50858.00' },
  ],
  payments_collected: [{ currency: 'INR', count: 4, gross: '115904.00', refunded: '0.00', net: '115904.00' }],
  subscriptions: { total_count: 7, by_status: { active: 6, trialing: 1 } },
  mrr: { currency: 'INR', mrr: '86500.00', arr: '1038000.00', by_currency: { INR: '86500.00' }, subscription_count: 6 },
  quotes: { total_count: 3, by_status: { sent: 2, accepted: 1 }, value_by_currency: [] },
  credit_notes: { total_count: 0, count_by_status: {}, currencies: [] },
  customers: { total: sampleCustomers.length, active: 6, new_in_period: 3 },
};

// ---------------------------------------------------------------------------
// Shell (UI config, header)
// ---------------------------------------------------------------------------

const sampleUiConfig: UiConfigBundle = { pages: {}, versions: {}, etag: 'preview' };

const sampleNotificationPreferences: NotificationPreferencesResponse = {
  preferences: {
    paymentReceived: true,
    paymentFailed: true,
    invoiceCreated: true,
    invoiceOverdue: true,
    invoicePaid: true,
    refundProcessed: true,
    subscriptionCreated: true,
    subscriptionUpgraded: true,
    subscriptionDowngraded: true,
    subscriptionCancelled: true,
    trialEnding: true,
    trialExpired: true,
    newCustomer: true,
    customerPortalActivity: true,
    paymentMethodChanges: true,
    systemAlerts: true,
    serviceNotifications: true,
    securityAlerts: true,
    emailNotifications: true,
    inAppNotifications: true,
  },
  updated_at: null,
};

const emptyReadState: { items: NotificationReadStateItem[] } = { items: [] };
const emptyPlatformAccess: { items: PlatformAccessGrant[] } = { items: [] };

// ---------------------------------------------------------------------------
// Milestone 2 Target Module Sample Data
// ---------------------------------------------------------------------------

export const sampleOfferings: any[] = [
  {
    id: 'off-1', name: 'Cloud ERP Pro', sku: 'PRO-ERP-01', description: 'Enterprise resource planning cloud suite',
    type: 'plan', category: 'Software', unit: 'tenant', currency: 'INR', pricing_model: 'flat', base_price: '4999.00',
    tax_rate_pct: '18.00', hsn_sac_code: '998313', billing_frequency: 'monthly', is_active: true, pricing_tiers: [],
    bundle_components: [], created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
  },
  {
    id: 'off-2', name: 'Dedicated Support Add-on', sku: 'SUPP-DED-01', description: '24/7 dedicated support SLA',
    type: 'service', category: 'Services', unit: 'month', currency: 'INR', pricing_model: 'flat', base_price: '1999.00',
    tax_rate_pct: '18.00', hsn_sac_code: '998314', billing_frequency: 'monthly', is_active: true, pricing_tiers: [],
    bundle_components: [], created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
  },
  {
    id: 'off-3', name: 'API Expansion Pack', sku: 'API-EXP-100K', description: '100,000 monthly API calls',
    type: 'product', category: 'Addon', unit: 'pack', currency: 'INR', pricing_model: 'tiered', base_price: '799.00',
    tax_rate_pct: '18.00', hsn_sac_code: '998315', billing_frequency: 'monthly', is_active: true, pricing_tiers: [],
    bundle_components: [], created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
  },
  {
    id: 'off-4', name: 'Startup Growth Bundle', sku: 'BNDL-STARTUP', description: 'Complete startup stack with ERP and Support',
    type: 'bundle', category: 'Bundles', unit: 'package', currency: 'INR', pricing_model: 'package', base_price: '5999.00',
    tax_rate_pct: '18.00', hsn_sac_code: '998319', billing_frequency: 'monthly', is_active: true, pricing_tiers: [],
    bundle_components: [], created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
  },
];

export const samplePriceBooks: any[] = [
  {
    id: 'pb-1', name: 'Standard INR Price Book', description: 'Default commercial pricing for India domestic customers',
    currency: 'INR', customer_segment: 'General', is_default: true, status: 'active', entries_count: 4,
    created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
  },
  {
    id: 'pb-2', name: 'Enterprise Volume Direct', description: 'Volume discounted tier for large enterprises',
    currency: 'INR', customer_segment: 'Enterprise', is_default: false, status: 'active', entries_count: 4,
    created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
  },
];

// Same shape as GET /dashboard/catalog-summary (dashboardSummaryService.CatalogSummary).
export const sampleCatalogSummary: CatalogSummary = {
  offerings: {
    total: sampleOfferings.length,
    active: sampleOfferings.filter((o) => o.is_active).length,
    inactive: sampleOfferings.filter((o) => !o.is_active).length,
    by_type: Object.fromEntries(['product', 'service', 'plan', 'bundle'].map((t) => [t, sampleOfferings.filter((o) => o.type === t).length])),
    active_by_type: Object.fromEntries(['product', 'service', 'plan', 'bundle'].map((t) => [t, sampleOfferings.filter((o) => o.type === t && o.is_active).length])),
    inactive_by_type: Object.fromEntries(['product', 'service', 'plan', 'bundle'].map((t) => [t, sampleOfferings.filter((o) => o.type === t && !o.is_active).length])),
  },
  price_books: {
    total: samplePriceBooks.length,
    by_status: samplePriceBooks.reduce<Record<string, number>>((acc, pb) => ({ ...acc, [pb.status ?? 'active']: (acc[pb.status ?? 'active'] ?? 0) + 1 }), {}),
  },
};

export const sampleDeals: any[] = [
  {
    id: 'deal-1', deal_number: 'DEAL-1001', title: 'Acme Traders Enterprise Rollout', customer_id: customerId(1),
    customer_name: 'Acme Traders', status: 'approved', currency: 'INR', total_amount: '145000.00', discount_amount: '15000.00',
    valid_until: '2026-11-30', items: [], created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
  },
  {
    id: 'deal-2', deal_number: 'DEAL-1002', title: 'Sunrise Foods Multi-site Expansion', customer_id: customerId(2),
    customer_name: 'Sunrise Foods', status: 'configured', currency: 'INR', total_amount: '89000.00', discount_amount: '5000.00',
    valid_until: '2026-11-15', items: [], created_at: '2026-10-02T00:00:00Z', updated_at: '2026-10-02T00:00:00Z',
  },
];

// Same shape as GET /dashboard/deals-summary (dashboardSummaryService.DealsSummary).
export const sampleDealsSummary: DealsSummary = {
  total_count: sampleDeals.length,
  by_status: sampleDeals.reduce<Record<string, number>>((acc, d) => ({ ...acc, [d.status]: (acc[d.status] ?? 0) + 1 }), {}),
  groups: {
    pending: sampleDeals.filter((d) => d.status === 'pending_approval').length,
    approved: sampleDeals.filter((d) => d.status === 'approved' || d.status === 'configured').length,
    converted: sampleDeals.filter((d) => d.status === 'converted').length,
  },
  value_by_currency: [{ currency: 'INR', count: sampleDeals.length, total: '234000.00' }],
  base_currency: 'INR',
};

export const sampleQuotes: any[] = [
  {
    id: 'quote-1', quote_number: 'QT-1001', customer_id: customerId(1), customer: sampleCustomers[0],
    title: 'Cloud Migration & Annual License', status: 'sent', issue_date: '2026-10-01', expiry_date: '2026-10-31',
    currency: 'INR', subtotal: '100000.00', discount_pct: '5.00', discount_amount: '5000.00', tax_amount: '17100.00',
    total: '112100.00', created_at: '2026-10-01T09:00:00Z', updated_at: '2026-10-01T09:00:00Z',
  },
  {
    id: 'quote-2', quote_number: 'QT-1002', customer_id: customerId(2), customer: sampleCustomers[1],
    title: 'Q4 Consulting Services', status: 'accepted', issue_date: '2026-09-25', expiry_date: '2026-10-25',
    currency: 'INR', subtotal: '55000.00', discount_pct: '0.00', discount_amount: '0.00', tax_amount: '9900.00',
    total: '64900.00', created_at: '2026-09-25T09:00:00Z', updated_at: '2026-09-25T09:00:00Z',
  },
  {
    id: 'quote-3', quote_number: 'QT-1003', customer_id: customerId(3), customer: sampleCustomers[2],
    title: 'Infrastructure Maintenance Pack', status: 'pending_approval', issue_date: '2026-10-04', expiry_date: '2026-11-04',
    currency: 'INR', subtotal: '80000.00', discount_pct: '25.00', discount_amount: '20000.00', tax_amount: '10800.00',
    total: '70800.00', created_at: '2026-10-04T09:00:00Z', updated_at: '2026-10-04T09:00:00Z',
  },
];

// Same shape as GET /dashboard/quotes-summary (dashboardSummaryService.QuotesSummary).
export const sampleQuotesSummary: QuotesSummary = {
  total_count: 3,
  by_status: { draft: 0, pending_approval: 1, sent: 1, accepted: 1, converted: 0, declined: 0, expired: 0 },
  groups: { draft: 0, pending_approval: 1, sent: 1, accepted: 1 },
  value_by_currency: [{ currency: 'INR', count: 3, total: '247800.00', open_total: '154200.00' }],
  base_currency: 'INR',
};

export const sampleSubscriptions: any[] = [
  {
    id: 'sub-1', subscription_number: 'SUB-1001', customer_id: customerId(1), customer: sampleCustomers[0],
    plan_name: 'Cloud ERP Pro', status: 'active', currency: 'INR', billing_period: 'monthly',
    unit_price: '4999.00', quantity: 5, total_amount: '24995.00', current_period_start: '2026-10-01',
    current_period_end: '2026-10-31', auto_renew: true, created_at: '2026-09-01T00:00:00Z',
  },
  {
    id: 'sub-2', subscription_number: 'SUB-1002', customer_id: customerId(2), customer: sampleCustomers[1],
    plan_name: 'Dedicated Support', status: 'active', currency: 'INR', billing_period: 'monthly',
    unit_price: '1999.00', quantity: 1, total_amount: '1999.00', current_period_start: '2026-10-01',
    current_period_end: '2026-10-31', auto_renew: true, created_at: '2026-09-15T00:00:00Z',
  },
];

export const sampleSubscriptionSummary = {
  total: sampleSubscriptions.length,
  active: 2,
  trialing: 0,
  past_due: 0,
  canceled: 0,
  paused: 0,
  mrr: '26994.00',
  arr: '323928.00',
};

export const samplePayments: PaymentOut[] = [
  {
    id: 'pay-1', payment_number: 'PAY-1001', customer: customerRef(1), amount: '49560.00', currency: 'INR',
    method: 'bank_transfer', gateway: 'manual', status: 'succeeded', reconciliation_status: 'matched',
    gateway_order_id: null, gateway_payment_id: null, gateway_signature_verified: false, reference: 'NEFT-987213',
    paid_at: '2026-10-03T10:00:00Z', failure_reason: null, notes: 'NEFT Ref #987213', amount_refunded: '0.00',
    amount_allocated: '49560.00', amount_unallocated: '0.00', allocations: [], refunds: [], recorded_by: null,
    created_at: '2026-10-03T10:00:00Z', updated_at: '2026-10-03T10:00:00Z',
  },
  {
    id: 'pay-2', payment_number: 'PAY-1002', customer: customerRef(2), amount: '24780.00', currency: 'INR',
    method: 'upi', gateway: 'manual', status: 'succeeded', reconciliation_status: 'matched',
    gateway_order_id: null, gateway_payment_id: null, gateway_signature_verified: false, reference: 'UPI-123487',
    paid_at: '2026-09-15T11:30:00Z', failure_reason: null, notes: 'UPI txn #123487', amount_refunded: '0.00',
    amount_allocated: '24780.00', amount_unallocated: '0.00', allocations: [], refunds: [], recorded_by: null,
    created_at: '2026-09-15T11:30:00Z', updated_at: '2026-09-15T11:30:00Z',
  },
];

export const samplePaymentsSummary = {
  total_count: samplePayments.length,
  total_amount: '74340.00',
  successful_count: samplePayments.length,
  successful_amount: '74340.00',
  refunded_count: 0,
  refunded_amount: '0.00',
};

export const sampleReconciliationSummary = {
  matched_count: 18,
  matched_amount: '385000.00',
  unmatched_count: 2,
  unmatched_amount: '18500.00',
  auto_matched_pct: '90.0',
};

export const sampleCreditNotes: any[] = [
  {
    id: 'cn-1', credit_note_number: 'CN-1001', customer_id: customerId(3), customer: sampleCustomers[2],
    status: 'issued', issue_date: '2026-10-02', currency: 'INR', subtotal: '5000.00', tax_amount: '900.00',
    total: '5900.00', balance: '5900.00', reason: 'Service SLA rebate', created_at: '2026-10-02T10:00:00Z',
  },
];

export const sampleCreditNotesSummary = {
  total_count: 1,
  total_amount: '5900.00',
  applied_amount: '0.00',
  available_amount: '5900.00',
};

export const sampleDunningMetrics = {
  active_cases: 2,
  recovered_amount: '52000.00',
  at_risk_amount: '27500.00',
  recovery_rate_pct: '74.5',
};

export const sampleDunningCases: any[] = [
  {
    id: 'dc-1', invoice_id: sampleInvoices[3].id, invoice_number: 'INV-1045', customer_id: customerId(5),
    customer_name: 'Bluewave Logistics', stage: 'first_reminder', status: 'in_progress', amount_due: '27500.00',
    days_overdue: 7, last_action_at: '2026-10-01T08:00:00Z', next_action_at: '2026-10-08T08:00:00Z',
  },
];

export const sampleDunningPolicies: any[] = [
  { id: 'pol-1', name: 'Default SaaS Retries', is_active: true, is_default: true, max_retry_attempts: 4, grace_period_days: 3 },
];

export const sampleCollectionsDashboard = {
  kpis: {
    total_overdue: '43100.00',
    overdue_30: '24600.00',
    overdue_60: '12500.00',
    overdue_90_plus: '6000.00',
    total_invoices: 2,
    average_dso: 28,
    promises_to_pay: 1,
    dispute_count: 0,
  },
  aging_summary: [
    { range: '1-30 days', count: 1, amount: '24600.00' },
    { range: '31-60 days', count: 1, amount: '12500.00' },
  ],
  pipeline: [
    { stage: 'friendly_reminder', count: 1, amount: '24600.00' },
    { stage: 'formal_notice', count: 1, amount: '12500.00' },
  ],
  top_overdue_customers: [],
  upcoming_due_invoices: [],
  recent_activities: [],
};

export const sampleExpenses: any[] = [
  {
    id: 'exp-1', expense_number: 'EXP-1001', category: 'Software & Cloud', title: 'AWS Cloud Hosting',
    merchant: 'Amazon Web Services', amount: '18500.00', currency: 'INR', expense_date: '2026-10-01',
    status: 'approved', is_billable: false, created_at: '2026-10-01T00:00:00Z',
  },
  {
    id: 'exp-2', expense_number: 'EXP-1002', category: 'Travel & Lodging', title: 'Client Onsite Bengaluru',
    merchant: 'Indigo Airlines', amount: '12400.00', currency: 'INR', expense_date: '2026-09-28',
    status: 'billed', is_billable: true, customer_id: customerId(1), created_at: '2026-09-28T00:00:00Z',
  },
];

export const sampleExpensesSummary = {
  total_expenses: '30900.00',
  unbilled_expenses: '18500.00',
  billed_expenses: '12400.00',
};

export const sampleProjects: any[] = [
  {
    id: 'proj-1', project_number: 'PRJ-101', name: 'Acme Traders Omnichannel Billing', customer_id: customerId(1),
    customer_name: 'Acme Traders', status: 'in_progress', billing_type: 'time_and_materials', budget: '250000.00',
    spent: '120000.00', progress_pct: 55, start_date: '2026-09-01', end_date: '2026-12-31',
  },
  {
    id: 'proj-2', project_number: 'PRJ-102', name: 'Sunrise Portal Integration', customer_id: customerId(2),
    customer_name: 'Sunrise Foods', status: 'completed', billing_type: 'fixed_fee', budget: '150000.00',
    spent: '145000.00', progress_pct: 100, start_date: '2026-08-01', end_date: '2026-09-30',
  },
];

export const sampleProjectsSummary = {
  total_projects: 2,
  active_projects: 1,
  completed_projects: 1,
  total_budget: '400000.00',
  total_spend: '265000.00',
};

export const sampleTimesheets: any[] = [
  {
    id: 'ts-1', project_id: 'proj-1', project_name: 'Acme Traders Omnichannel Billing', user_name: 'Asha Sharma',
    entry_date: '2026-10-04', hours: '7.5', is_billable: true, status: 'approved', notes: 'API Integration testing',
    created_at: '2026-10-04T18:00:00Z',
  },
  {
    id: 'ts-2', project_id: 'proj-1', project_name: 'Acme Traders Omnichannel Billing', user_name: 'Asha Sharma',
    entry_date: '2026-10-05', hours: '8.0', is_billable: true, status: 'submitted', notes: 'Custom webhook deployment',
    created_at: '2026-10-05T17:30:00Z',
  },
];

export const sampleTimesheetsSummary = {
  total_hours: '15.5',
  billable_hours: '15.5',
  non_billable_hours: '0.0',
  utilization_pct: '100.0',
};

export const sampleReportKpis = {
  gross_revenue: '285736.00',
  net_revenue: '243200.00',
  total_collections: '115904.00',
  total_receivables: '120120.00',
  overdue_receivables: '50858.00',
  active_subscribers: 6,
  average_invoice_value: '31748.00',
  collection_efficiency_pct: '88.5',
};

export const sampleTemplates: any[] = [
  { id: 'tmpl-1', name: 'Standard GST Invoice Template', template_type: 'invoice', is_default: true, updated_at: '2026-09-01T00:00:00Z' },
  { id: 'tmpl-2', name: 'Corporate Quote Template', template_type: 'quote', is_default: true, updated_at: '2026-09-01T00:00:00Z' },
];

export const sampleReportingTags: any[] = [
  { id: 'tag-1', name: 'Enterprise Accounts', category: 'segment', is_active: true },
  { id: 'tag-2', name: 'Direct Sales', category: 'channel', is_active: true },
];

export const sampleNumberSeries: any[] = [
  { id: 'ser-1', document_type: 'invoice', prefix: 'INV-', next_number: 1049, padding_digits: 4 },
  { id: 'ser-2', document_type: 'quote', prefix: 'QT-', next_number: 1004, padding_digits: 4 },
];

export const sampleAutomationRules: any[] = [
  {
    id: 'rule-1',
    name: 'Auto-send Payment Reminders',
    trigger_event: 'invoice.due_soon',
    is_active: true,
    actions_count: 1,
    actions: [{ id: 'act-1', action_type: 'send_email', execution_order: 1 }],
  },
  {
    id: 'rule-2',
    name: 'Escalate Overdue to Collections',
    trigger_event: 'invoice.overdue_15d',
    is_active: true,
    actions_count: 2,
    actions: [{ id: 'act-2', action_type: 'webhook_notify', execution_order: 1 }],
  },
];

export const sampleAutomationSchedules: any[] = [
  { id: 'sch-1', name: 'Daily Dunning Evaluation', cron_expression: '0 6 * * *', is_active: true, last_run_at: '2026-10-05T06:00:00Z' },
];

export const sampleAutomationLogs: any[] = [
  {
    id: 'log-1',
    organization_id: 'preview-org',
    action_type: 'send_email',
    name: 'Auto-send Payment Reminders',
    entity_type: 'invoice',
    entity_id: 'inv-1',
    status: 'success',
    occurred_at: '2026-10-05T06:00:00Z',
    details: { count: 3 },
    error_message: null,
  },
];

export const sampleAllIntegrations = {
  razorpay: {
    provider: 'razorpay' as const,
    is_connected: true,
    mode: 'test' as const,
    masked_key_id: 'rzp_test_••••1234',
    has_webhook_secret: true,
    last_tested_at: '2026-10-04T12:00:00Z',
    status_message: 'Gateway ready for test checkouts',
  },
  smtp: {
    provider: 'smtp' as const,
    is_connected: false,
    host: null,
    port: null,
    username: null,
    use_tls: true,
    use_ssl: false,
    from_email: null,
    from_name: null,
    has_password: false,
    last_tested_at: null,
    status_message: null,
  },
  webhook: {
    provider: 'webhook' as const,
    is_connected: true,
    url: 'https://webhook.site/sample-endpoint',
    events: ['invoice.created', 'payment.received'],
    has_signing_secret: true,
    last_tested_at: '2026-10-04T12:00:00Z',
    status_message: 'Webhook destination active',
  },
  accounting: { provider: 'accounting', is_connected: false as const, status: 'coming_soon' as const, status_message: 'Accounting integration coming soon' },
  crm: { provider: 'crm', is_connected: false as const, status: 'coming_soon' as const, status_message: 'CRM integration coming soon' },
  storage: { provider: 'storage', is_connected: false as const, status: 'coming_soon' as const, status_message: 'Storage integration coming soon' },
};

// ---------------------------------------------------------------------------
// Request routing
// ---------------------------------------------------------------------------

type Query = URLSearchParams;

function paginate<T>(items: T[], query: Query): Paginated<T> {
  const pageSize = Math.max(1, Number(query.get('page_size')) || 20);
  const page = Math.max(1, Number(query.get('page')) || 1);
  return {
    items: items.slice((page - 1) * pageSize, page * pageSize),
    total: items.length,
    page,
    page_size: pageSize,
    total_pages: Math.max(1, Math.ceil(items.length / pageSize)),
  };
}

function matchesSearch(query: Query, ...fields: Array<string | null | undefined>): boolean {
  const term = (query.get('search') || '').trim().toLowerCase();
  if (!term) return true;
  return fields.some((f) => (f || '').toLowerCase().includes(term));
}

function listCustomers(query: Query): Paginated<CustomerOut> {
  const status = query.get('status');
  const rows = sampleCustomers.filter(
    (c) =>
      (!status || c.status === status) &&
      matchesSearch(query, c.display_name, c.company_name, c.email, c.customer_number, c.gstin),
  );
  return paginate(rows, query);
}

function listInvoices(query: Query): { items: Invoice[]; total: number; page: number; page_size: number; kpis: InvoiceKPIs } {
  const status = (query.get('status') || '').toLowerCase();
  const customer = query.get('customer_id');
  const rows = sampleInvoices.filter(
    (i) =>
      (!status || status === 'all' || String(i.status).toLowerCase() === status) &&
      (!customer || i.customer_id === customer) &&
      matchesSearch(query, i.invoice_number, i.customer.display_name, i.customer.email),
  );
  const { items, total, page, page_size } = paginate(rows, query);
  return { items, total, page, page_size, kpis: sampleInvoiceKpis };
}

/** GET routes: exact path -> handler. Paths are relative to /api/v1, without a trailing slash. */
const GET_ROUTES: Record<string, (query: Query) => unknown> = {
  '/ui-config': () => sampleUiConfig,
  '/dashboard/summary': () => sampleDashboardSummary,
  '/dashboard/financial-summary': () => sampleFinancialSummary,
  '/action-center': () => sampleActionCenter,
  '/customers': listCustomers,
  '/invoices': listInvoices,
  '/invoices/summary': () => sampleInvoiceKpis,
  '/notifications/read-state': () => emptyReadState,
  '/notifications/preferences': () => sampleNotificationPreferences,
  '/organization/platform-access/active': () => emptyPlatformAccess,
  // Catalog & Plans
  '/catalog/offerings': (query) => {
    const type = query.get('type');
    const rows = sampleOfferings.filter((o) => (!type || o.type === type) && matchesSearch(query, o.name, o.sku));
    return paginate(rows, query);
  },
  '/catalog/price-books': (query) => paginate(samplePriceBooks.filter((pb) => matchesSearch(query, pb.name, pb.customer_segment)), query),
  '/dashboard/catalog-summary': () => sampleCatalogSummary,
  // CPQ & Deals
  '/cpq/deals': (query) => paginate(sampleDeals.filter((d) => matchesSearch(query, d.deal_number, d.title)), query),
  '/cpq/rules': () => [],
  '/dashboard/deals-summary': () => sampleDealsSummary,
  // Quotes
  '/quotes': (query) => {
    const status = query.get('status');
    const rows = sampleQuotes.filter((q) => (!status || status === 'all' || q.status === status) && matchesSearch(query, q.quote_number, q.title));
    return paginate(rows, query);
  },
  '/dashboard/quotes-summary': () => sampleQuotesSummary,
  // Subscriptions
  // /subscriptions and /subscriptions/summary: typed fixtures in ./fixtures/trials.ts (full SubscriptionOut records).
  // /subscriptions/plan-options: typed fixture in ./fixtures/proration.ts (SubscribablePlanOption records).
  // Payments
  '/payments': (query) => paginate(samplePayments.filter((p) => matchesSearch(query, p.payment_number, p.notes)), query),
  '/payments/summary': () => samplePaymentsSummary,
  '/payments/reconciliation/summary': () => sampleReconciliationSummary,
  // Credit Notes
  '/credit-notes': () => ({ items: sampleCreditNotes, total: sampleCreditNotes.length }),
  '/credit-notes/summary': () => sampleCreditNotesSummary,
  // Dunning & Collections
  '/dunning/metrics': () => sampleDunningMetrics,
  '/dunning/cases': () => sampleDunningCases,
  '/dunning/policies': () => sampleDunningPolicies,
  '/dunning/expiring-cards': () => [],
  '/collections/dashboard': () => sampleCollectionsDashboard,
  '/collections/invoices': (query) => paginate(sampleInvoices.filter((i) => Number(i.amount_due) > 0), query),
  // Expenses & Projects
  '/expenses': () => sampleExpenses,
  '/expenses/summary': () => sampleExpensesSummary,
  '/expenses/recurring': () => [],
  '/projects': () => sampleProjects,
  '/projects/summary': () => sampleProjectsSummary,
  // Timesheets
  '/timesheets': () => sampleTimesheets,
  '/timesheets/summary': () => sampleTimesheetsSummary,
  '/timesheets/weekly': () => ({ entries: [], total_hours: 0 }),
  // Reports
  '/reports/products': () => ({ count: 4, items: [] }),
  // /reports/{dashboard,revenue,receivables,payments,customers,invoices} and /subscriptions/summary:
  // fully typed fixtures in ./fixtures/revenue_intelligence.ts (shared by Reports and Revenue Intelligence).
  // Customization & Automation
  '/templates': () => sampleTemplates,
  '/reporting-tags': () => sampleReportingTags,
  '/settings/number-series': () => sampleNumberSeries,
  '/web-tabs': () => [],
  '/webhook-deliveries': () => [],
  '/automation/rules': () => sampleAutomationRules,
  '/automation/schedules': () => sampleAutomationSchedules,
  '/automation/logs': () => sampleAutomationLogs,
  // Settings & Integrations
  '/organization': () => ({ id: 'preview-org', name: 'Acme Traders', slug: 'acme-traders', email: 'billing@example.com' }),
  '/team': () => [{ id: 'user-1', name: 'Asha Sharma', email: 'asha@example.com', role: 'owner' }],
  '/settings/integrations': () => sampleAllIntegrations,
};

/**
 * Per-page fixture modules (./fixtures/<page>.ts, each exporting `routes`: exact path -> handler),
 * so a module page's sample data lives next to nothing else. Built-in routes above win on clashes.
 */
const fixtureModules = import.meta.glob<Record<string, (query: Query) => unknown>>('./fixtures/*.ts', {
  eager: true,
  import: 'routes',
});
for (const routes of Object.values(fixtureModules)) {
  for (const [path, handler] of Object.entries(routes)) {
    if (!(path in GET_ROUTES)) GET_ROUTES[path] = handler;
  }
}

/** The GET paths the preview can answer (for documentation and tests). */
export const PREVIEW_GET_PATHS: readonly string[] = Object.keys(GET_ROUTES);

/** Split a request into an API-relative path and its merged query (url query + config.params). */
export function resolvePreviewRequest(config: InternalAxiosRequestConfig): { path: string; query: Query } {
  const raw = config.url || '';
  const parsed = new URL(raw, 'http://preview.invalid/');
  let path = parsed.pathname;
  const apiIndex = path.indexOf('/api/v1');
  if (apiIndex !== -1) path = path.slice(apiIndex + '/api/v1'.length);
  path = `/${path.replace(/^\/+|\/+$/g, '')}`;

  const query = new URLSearchParams(parsed.search);
  const params = config.params as Record<string, unknown> | undefined;
  if (params && typeof params === 'object') {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '') continue;
      query.set(key, String(value));
    }
  }
  return { path, query };
}

function respond<T>(config: InternalAxiosRequestConfig, data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: 'OK', headers: {}, config };
}

function reject(
  config: InternalAxiosRequestConfig,
  status: number,
  statusText: string,
  code: string,
  message: string,
): AxiosError {
  const response: AxiosResponse = {
    data: { error: { code, message } },
    status,
    statusText,
    headers: {},
    config,
  };
  return new AxiosError(
    `Request failed with status code ${status}`,
    AxiosError.ERR_BAD_REQUEST,
    config,
    undefined,
    response,
  );
}

export const PREVIEW_READ_ONLY_MESSAGE = 'Preview mode: actions are disabled. Nothing was changed.';

/**
 * Axios adapter for the visual-editor preview. Never touches the network: GETs are answered from
 * fictional sample data, everything else is refused with 403 PREVIEW_READ_ONLY.
 */
export const previewAdapter: AxiosAdapter = async (config) => {
  const method = (config.method || 'get').toLowerCase();
  if (method !== 'get') {
    throw reject(config, 403, 'Forbidden', 'PREVIEW_READ_ONLY', PREVIEW_READ_ONLY_MESSAGE);
  }
  const { path, query } = resolvePreviewRequest(config);
  const handler = GET_ROUTES[path];
  if (!handler) {
    throw reject(config, 404, 'Not Found', 'NOT_FOUND', 'Not available in preview.');
  }
  // Fresh copy per response so a page mutating its data never alters the fixtures.
  return respond(config, JSON.parse(JSON.stringify(handler(query))));
};
