import { absoluteUrl, apiClient, cleanParams } from './apiClient';
import type {
  CustomerAnalyticsOut,
  InvoiceAnalyticsOut,
  PaymentAnalyticsOut,
  ProductAnalyticsOut,
  ReceivablesAnalyticsOut,
  ReportExportSection,
  ReportKPIs,
  ReportRangeParams,
  RevenueAnalyticsOut,
} from '../types/reports';

export const reportsService = {
  dashboard: async (params: ReportRangeParams): Promise<ReportKPIs> => {
    const { data } = await apiClient.get<ReportKPIs>('/reports/dashboard', {
      params: cleanParams(params),
    });
    return data;
  },

  revenue: async (params: ReportRangeParams): Promise<RevenueAnalyticsOut> => {
    const { data } = await apiClient.get<RevenueAnalyticsOut>('/reports/revenue', {
      params: cleanParams(params),
    });
    return data;
  },

  receivables: async (params: ReportRangeParams): Promise<ReceivablesAnalyticsOut> => {
    const { data } = await apiClient.get<ReceivablesAnalyticsOut>('/reports/receivables', {
      params: cleanParams(params),
    });
    return data;
  },

  invoices: async (params: ReportRangeParams): Promise<InvoiceAnalyticsOut> => {
    const { data } = await apiClient.get<InvoiceAnalyticsOut>('/reports/invoices', {
      params: cleanParams(params),
    });
    return data;
  },

  payments: async (params: ReportRangeParams): Promise<PaymentAnalyticsOut> => {
    const { data } = await apiClient.get<PaymentAnalyticsOut>('/reports/payments', {
      params: cleanParams(params),
    });
    return data;
  },

  customers: async (params: ReportRangeParams): Promise<CustomerAnalyticsOut> => {
    const { data } = await apiClient.get<CustomerAnalyticsOut>('/reports/customers', {
      params: cleanParams(params),
    });
    return data;
  },

  products: async (params: ReportRangeParams): Promise<ProductAnalyticsOut> => {
    const { data } = await apiClient.get<ProductAnalyticsOut>('/reports/products', {
      params: cleanParams(params),
    });
    return data;
  },

  /**
   * Absolute URL of a report section CSV export (requires the bearer token;
   * pair with `downloadAuthenticated`).
   */
  exportUrl: (section: ReportExportSection, params: ReportRangeParams): string =>
    absoluteUrl('/reports/export', { section, ...cleanParams(params) }),
};
