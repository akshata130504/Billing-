import { absoluteUrl, apiClient, cleanParams } from './apiClient';
import type {
  InvoiceIn,
  InvoiceListParams,
  InvoiceOut,
  InvoiceUpdate,
  Paginated,
  PaymentOut,
  RecordPaymentRequest,
} from '../types/api';

export const invoiceService = {
  list: async (params?: InvoiceListParams): Promise<Paginated<InvoiceOut>> => {
    const { data } = await apiClient.get<Paginated<InvoiceOut>>('/invoices', {
      params: cleanParams(params),
    });
    return data;
  },

  get: async (id: string): Promise<InvoiceOut> => {
    const { data } = await apiClient.get<InvoiceOut>(`/invoices/${id}`);
    return data;
  },

  create: async (body: InvoiceIn): Promise<InvoiceOut> => {
    const { data } = await apiClient.post<InvoiceOut>('/invoices', body);
    return data;
  },

  update: async (id: string, body: InvoiceUpdate): Promise<InvoiceOut> => {
    const { data } = await apiClient.patch<InvoiceOut>(`/invoices/${id}`, body);
    return data;
  },

  remove: async (id: string): Promise<void> => {
    await apiClient.delete(`/invoices/${id}`);
  },

  send: async (id: string): Promise<InvoiceOut> => {
    const { data } = await apiClient.post<InvoiceOut>(`/invoices/${id}/send`);
    return data;
  },

  sendReminder: async (id: string): Promise<InvoiceOut> => {
    const { data } = await apiClient.post<InvoiceOut>(`/invoices/${id}/send-reminder`);
    return data;
  },

  voidInvoice: async (id: string, reason: string): Promise<InvoiceOut> => {
    const { data } = await apiClient.post<InvoiceOut>(`/invoices/${id}/void`, { reason });
    return data;
  },

  recordPayment: async (id: string, body: RecordPaymentRequest): Promise<PaymentOut> => {
    const { data } = await apiClient.post<PaymentOut>(`/invoices/${id}/record-payment`, body);
    return data;
  },

  /**
   * Absolute URL of the authenticated PDF endpoint. Requires the bearer token —
   * use `downloadAuthenticated(invoiceService.pdfUrl(id), 'INV-….pdf')`.
   */
  pdfUrl: (id: string): string => absoluteUrl(`/invoices/${id}/pdf`),
};
