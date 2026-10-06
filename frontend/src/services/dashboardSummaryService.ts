import { apiClient, cleanParams } from './apiClient';
import type { DashboardRange } from '../types';

// Server-side KPI counters (backend/app/services/dashboard_summary_service.py).
// Money is always reported per currency — never summed across currencies — with the
// organization's base currency first.

export interface InvoiceStatusAmount {
  count: number;
  total: string;
  amount_due: string;
}

export interface InvoiceCurrencyTotals {
  currency: string;
  count: number;
  /** Excludes void invoices. */
  total: string;
  amount_paid: string;
  /** Excludes draft and void invoices. */
  amount_due: string;
  by_status: Record<string, InvoiceStatusAmount>;
}

export interface ReceivableTotals {
  currency: string;
  open_count: number;
  amount_due: string;
  overdue_count: number;
  overdue_amount: string;
}

export interface CollectedTotals {
  currency: string;
  count: number;
  gross: string;
  refunded: string;
  net: string;
}

export interface QuoteValueByCurrency {
  currency: string;
  count: number;
  total: string;
  open_total: string;
}

export interface FinancialSummary {
  base_currency: string;
  date_from: string | null;
  date_to: string | null;
  invoices: { total_count: number; by_status: Record<string, number>; by_currency: InvoiceCurrencyTotals[] };
  /** Point in time (now), independent of the date range. */
  receivables: ReceivableTotals[];
  payments_collected: CollectedTotals[];
  subscriptions: { total_count: number; by_status: Record<string, number> };
  mrr: { currency: string; mrr: string; arr: string; by_currency: Record<string, string>; subscription_count: number };
  quotes: { total_count: number; by_status: Record<string, number>; value_by_currency: QuoteValueByCurrency[] };
  credit_notes: {
    total_count: number;
    count_by_status: Record<string, number>;
    currencies: Array<{
      currency: string;
      count: number;
      issued_total: string;
      applied_total: string;
      remaining_balance: string;
      voided_total: string;
      draft_total: string;
    }>;
  };
  customers: { total: number; active: number; new_in_period: number };
}

export interface QuotesSummary {
  total_count: number;
  by_status: Record<string, number>;
  groups: { draft: number; pending_approval: number; sent: number; accepted: number };
  value_by_currency: QuoteValueByCurrency[];
  base_currency: string;
}

export interface CatalogSummary {
  offerings: {
    total: number;
    active: number;
    inactive: number;
    by_type: Record<string, number>;
    active_by_type: Record<string, number>;
    inactive_by_type: Record<string, number>;
  };
  price_books: { total: number; by_status: Record<string, number> };
}

export interface DealsSummary {
  total_count: number;
  by_status: Record<string, number>;
  groups: { pending: number; approved: number; converted: number };
  value_by_currency: Array<{ currency: string; count: number; total: string }>;
  base_currency: string;
}

export interface FinancialSummaryParams {
  range?: DashboardRange;
  date_from?: string;
  date_to?: string;
}

export const dashboardSummaryService = {
  financial: async (params?: FinancialSummaryParams): Promise<FinancialSummary> => {
    const { data } = await apiClient.get<FinancialSummary>('/dashboard/financial-summary', {
      params: cleanParams(params),
    });
    return data;
  },

  quotes: async (params?: {
    search?: string;
    customer_id?: string;
    date_from?: string;
    date_to?: string;
  }): Promise<QuotesSummary> => {
    const { data } = await apiClient.get<QuotesSummary>('/dashboard/quotes-summary', { params: cleanParams(params) });
    return data;
  },

  catalog: async (params?: { search?: string }): Promise<CatalogSummary> => {
    const { data } = await apiClient.get<CatalogSummary>('/dashboard/catalog-summary', { params: cleanParams(params) });
    return data;
  },

  deals: async (params?: { customer_id?: string; date_from?: string; date_to?: string }): Promise<DealsSummary> => {
    const { data } = await apiClient.get<DealsSummary>('/dashboard/deals-summary', { params: cleanParams(params) });
    return data;
  },
};

/** "₹1,200.00 · $40.00" — one figure per currency, base currency first. */
export function formatPerCurrency<T extends { currency: string }>(
  rows: T[],
  pick: (row: T) => string,
  format: (amount: string, currency: string) => string,
  fallbackCurrency: string,
): string {
  if (!rows.length) return format('0', fallbackCurrency);
  return rows.map((r) => format(pick(r), r.currency)).join(' · ');
}
