import type { CustomerRef } from './api';

export type ReportRangeKey =
  | 'today'
  | 'this_week'
  | 'this_month'
  | 'last_month'
  | 'this_quarter'
  | 'this_year'
  | 'last_12_months'
  | 'custom';

export interface ReportRangeParams {
  range: ReportRangeKey;
  start?: string;
  end?: string;
  /** Reporting currency (ISO-4217); omitted = the organization's base currency. */
  currency?: string;
}

/**
 * Every money figure of a report response is in `currency`; `currencies` lists every
 * currency the organization has invoices or payments in. There is no FX conversion, so
 * amounts in different currencies are never added together.
 */
export interface CurrencyScopedReport {
  currency: string;
  currencies: string[];
}

export type ReportExportSection =
  | 'revenue_over_time'
  | 'invoiced_vs_collected'
  | 'revenue_by_customer'
  | 'revenue_by_product'
  | 'revenue_by_plan'
  | 'outstanding_by_aging'
  | 'top_customers_by_outstanding'
  | 'method_breakdown';

export type AgingBucket = 'current' | '1_30' | '31_60' | '61_90' | '90_plus';

export interface CurrencyKPIs {
  currency: string;
  total_revenue: string;
  net_revenue: string;
  total_invoiced: string;
  total_collected: string;
  outstanding_receivables: string;
  overdue_receivables: string;
  collection_rate: string | null;
  average_invoice_value: string | null;
  invoice_count: number;
}

export interface ReportKPIs extends CurrencyKPIs, CurrencyScopedReport {
  /** The same KPIs for every currency (base first). */
  by_currency: CurrencyKPIs[];
}

export interface TimeSeriesPoint {
  period: string;
  amount: string;
}

export interface InvoicedVsCollectedPoint {
  period: string;
  invoiced: string;
  collected: string;
}

export interface CustomerAmount {
  customer: CustomerRef;
  amount: string;
  currency: string;
}

export interface NamedAmount {
  id: string;
  name: string;
  revenue: string;
  quantity: string;
  currency: string;
}

export interface RevenueAnalyticsOut extends CurrencyScopedReport {
  granularity: 'day' | 'month';
  revenue_over_time: TimeSeriesPoint[];
  invoiced_vs_collected: InvoicedVsCollectedPoint[];
  revenue_by_customer: CustomerAmount[];
  revenue_by_product: NamedAmount[];
  revenue_by_plan: NamedAmount[];
}

export interface AgingBucketOut {
  bucket: AgingBucket;
  count: number;
  amount: string;
}

export interface CollectionRatePoint {
  period: string;
  rate: string | null;
}

export interface ReceivablesAnalyticsOut extends CurrencyScopedReport {
  outstanding_by_aging: AgingBucketOut[];
  /**
   * Currently-overdue invoices grouped by the period their due date falls in.
   * NOT a historical day-by-day snapshot of overdue balances — this app has
   * no receivables snapshot table to produce that.
   */
  overdue_by_due_period: TimeSeriesPoint[];
  collection_rate_trend: CollectionRatePoint[];
  top_customers_by_outstanding: CustomerAmount[];
  average_days_to_payment: number | null;
}

export interface InvoiceStatusBreakdown {
  count: number;
  amount: string;
}

export interface InvoiceAnalyticsOut extends CurrencyScopedReport {
  by_status: Record<string, InvoiceStatusBreakdown>;
  total_count: number;
  average_invoice_amount: string | null;
}

export interface MethodAmount {
  method: string;
  amount: string;
  currency: string;
}

export interface PaymentAnalyticsOut extends CurrencyScopedReport {
  total_payments: string;
  payment_count: number;
  method_breakdown: MethodAmount[];
  trend: TimeSeriesPoint[];
  refund_amount: string;
  net_collected: string;
}

export interface CustomerAnalyticsOut extends CurrencyScopedReport {
  total_customers: number;
  active_customers: number;
  customers_with_outstanding_balance: number;
  top_customers_by_revenue: CustomerAmount[];
  top_customers_by_outstanding: CustomerAmount[];
}

export interface PricingModelAmount {
  pricing_model: string;
  amount: string;
  currency: string;
}

export interface QuantitySold {
  id: string;
  name: string;
  quantity: string;
}

export interface ProductAnalyticsOut extends CurrencyScopedReport {
  best_selling: NamedAmount[];
  revenue_by_offering: NamedAmount[];
  revenue_by_pricing_model: PricingModelAmount[];
  plan_revenue: NamedAmount[];
  quantity_sold: QuantitySold[];
}
