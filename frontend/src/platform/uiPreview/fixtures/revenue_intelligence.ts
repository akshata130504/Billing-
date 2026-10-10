/**
 * Visual-editor preview sample data for Revenue Intelligence (/revenue-intelligence).
 * On mount the page loads GET /reports/dashboard, /reports/revenue, /reports/receivables,
 * /reports/payments, /reports/customers, /reports/invoices (all with ?range=...) and
 * GET /subscriptions/summary. Fictional figures only.
 *
 * NOTE: the built-in GET_ROUTES in ../sampleData.ts also define these paths (with simplified
 * shapes) and built-in routes win on clashes, so these handlers only take effect once those
 * built-in entries are removed or replaced with the ones below.
 */
import type { CustomerRef, SubscriptionSummaryOut } from '../../../types/api';
import { previewSubscriptionSummary } from './trials';
import type {
  CustomerAnalyticsOut,
  InvoiceAnalyticsOut,
  PaymentAnalyticsOut,
  ReceivablesAnalyticsOut,
  ReportKPIs,
  RevenueAnalyticsOut,
} from '../../../types/reports';

/** Same ids / numbers as the built-in sample customers (sampleData.ts). */
const customer = (n: number, display_name: string, email: string): CustomerRef => ({
  id: `00000000-0000-4000-a000-0000000000${String(n).padStart(2, '0')}`,
  customer_number: `CUST-${String(n).padStart(5, '0')}`,
  display_name,
  email,
});
const ACME = customer(1, 'Acme Traders', 'accounts@acmetraders.example.in');
const SUNRISE = customer(2, 'Sunrise Foods', 'billing@sunrisefoods.example.in');
const LOTUS = customer(3, 'Lotus Textiles', 'finance@lotustextiles.example.in');
const BLUEWAVE = customer(5, 'Bluewave Logistics', 'ap@bluewave.example.in');
const SAFFRON = customer(6, 'Saffron Studio', 'studio@saffron.example.in');

const sampleInrKpis = {
  currency: 'INR',
  total_revenue: '285736.00',
  net_revenue: '243200.00',
  total_invoiced: '285736.00',
  total_collected: '165464.00',
  outstanding_receivables: '120272.00',
  overdue_receivables: '50858.00',
  collection_rate: '57.91',
  average_invoice_value: '31748.44',
  invoice_count: 9,
};

export const sampleRevenueKpis: ReportKPIs = {
  ...sampleInrKpis,
  currencies: ['INR'],
  by_currency: [sampleInrKpis],
};

export const sampleRevenueAnalytics: RevenueAnalyticsOut = {
  currency: 'INR',
  currencies: ['INR'],
  granularity: 'month',
  revenue_over_time: [
    { period: '2026-05', amount: '28500.00' },
    { period: '2026-06', amount: '34200.00' },
    { period: '2026-07', amount: '41800.00' },
    { period: '2026-08', amount: '52300.00' },
    { period: '2026-09', amount: '69016.00' },
    { period: '2026-10', amount: '59920.00' },
  ],
  invoiced_vs_collected: [
    { period: '2026-05', invoiced: '28500.00', collected: '26000.00' },
    { period: '2026-06', invoiced: '34200.00', collected: '30100.00' },
    { period: '2026-07', invoiced: '41800.00', collected: '22400.00' },
    { period: '2026-08', invoiced: '52300.00', collected: '27600.00' },
    { period: '2026-09', invoiced: '69016.00', collected: '35780.00' },
    { period: '2026-10', invoiced: '59920.00', collected: '23584.00' },
  ],
  revenue_by_customer: [
    { customer: LOTUS, amount: '76700.00', currency: 'INR' },
    { customer: ACME, amount: '67968.00', currency: 'INR' },
    { customer: SUNRISE, amount: '46610.00', currency: 'INR' },
    { customer: SAFFRON, amount: '41300.00', currency: 'INR' },
    { customer: BLUEWAVE, amount: '32450.00', currency: 'INR' },
  ],
  revenue_by_product: [
    { id: 'prod-1', name: 'Implementation services', revenue: '98000.00', quantity: '14', currency: 'INR' },
    { id: 'prod-2', name: 'Annual support', revenue: '64500.00', quantity: '6', currency: 'INR' },
    { id: 'prod-3', name: 'Training workshop', revenue: '27500.00', quantity: '11', currency: 'INR' },
  ],
  revenue_by_plan: [
    { id: 'plan-1', name: 'Growth (monthly)', revenue: '53982.00', quantity: '6', currency: 'INR' },
    { id: 'plan-2', name: 'Starter (monthly)', revenue: '17994.00', quantity: '6', currency: 'INR' },
  ],
};

export const sampleReceivablesAnalytics: ReceivablesAnalyticsOut = {
  currency: 'INR',
  currencies: ['INR'],
  outstanding_by_aging: [
    { bucket: 'current', count: 2, amount: '69414.00' },
    { bucket: '1_30', count: 1, amount: '32450.00' },
    { bucket: '31_60', count: 1, amount: '18408.00' },
    { bucket: '61_90', count: 0, amount: '0.00' },
    { bucket: '90_plus', count: 0, amount: '0.00' },
  ],
  overdue_by_due_period: [
    { period: '2026-09', amount: '50858.00' },
  ],
  collection_rate_trend: [
    { period: '2026-09', rate: '51.84' },
    { period: '2026-10', rate: '39.36' },
  ],
  top_customers_by_outstanding: [
    { customer: LOTUS, amount: '46700.00', currency: 'INR' },
    { customer: BLUEWAVE, amount: '32450.00', currency: 'INR' },
    { customer: SUNRISE, amount: '21830.00', currency: 'INR' },
    { customer: ACME, amount: '18408.00', currency: 'INR' },
  ],
  average_days_to_payment: 18.4,
};

export const samplePaymentAnalytics: PaymentAnalyticsOut = {
  currency: 'INR',
  currencies: ['INR'],
  total_payments: '168464.00',
  payment_count: 7,
  method_breakdown: [
    { method: 'bank_transfer', amount: '98560.00', currency: 'INR' },
    { method: 'upi', amount: '45120.00', currency: 'INR' },
    { method: 'card', amount: '24784.00', currency: 'INR' },
  ],
  trend: [
    { period: '2026-09', amount: '96780.00' },
    { period: '2026-10', amount: '71684.00' },
  ],
  refund_amount: '3000.00',
  net_collected: '165464.00',
};

export const sampleCustomerAnalytics: CustomerAnalyticsOut = {
  currency: 'INR',
  currencies: ['INR'],
  total_customers: 8,
  active_customers: 6,
  customers_with_outstanding_balance: 4,
  top_customers_by_revenue: sampleRevenueAnalytics.revenue_by_customer,
  top_customers_by_outstanding: sampleReceivablesAnalytics.top_customers_by_outstanding,
};

export const sampleInvoiceAnalytics: InvoiceAnalyticsOut = {
  currency: 'INR',
  currencies: ['INR'],
  by_status: {
    paid: { count: 3, amount: '85904.00' },
    sent: { count: 1, amount: '21830.00' },
    partially_paid: { count: 1, amount: '76700.00' },
    overdue: { count: 2, amount: '50858.00' },
    draft: { count: 1, amount: '41300.00' },
  },
  total_count: 9,
  average_invoice_amount: '31748.44',
};

/** The live summary payload also carries `renewing_soon_count` (see types/revenueIntelligence.ts). */
// The same summary every preview page sees (fixtures/trials.ts owns the subscription data).
export const sampleSubscriptionMixSummary: SubscriptionSummaryOut & { renewing_soon_count: number } = {
  ...previewSubscriptionSummary,
  renewing_soon_count: 1,
};

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/reports/dashboard': () => sampleRevenueKpis,
  '/reports/revenue': () => sampleRevenueAnalytics,
  '/reports/receivables': () => sampleReceivablesAnalytics,
  '/reports/payments': () => samplePaymentAnalytics,
  '/reports/customers': () => sampleCustomerAnalytics,
  '/reports/invoices': () => sampleInvoiceAnalytics,
  '/subscriptions/summary': () => sampleSubscriptionMixSummary,
};
