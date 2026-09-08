import { apiClient } from './apiClient';
import type {
  Invoice,
  PaymentRecordIn,
} from '../types/invoices';

export const invoiceService = {
  async listInvoices(params?: {
    search?: string;
    status?: string;
    customer_id?: string;
    date_from?: string;
    date_to?: string;
    overdue_only?: boolean;
    page?: number;
    page_size?: number;
    sort?: string;
  }): Promise<{ items: Invoice[]; total: number; kpis?: any }> {
    const q = new URLSearchParams();
    if (params?.search) q.set('search', params.search);
    if (params?.status && params.status !== 'all') q.set('status', params.status);
    if (params?.customer_id) q.set('customer_id', params.customer_id);
    if (params?.date_from) q.set('date_from', params.date_from);
    if (params?.date_to) q.set('date_to', params.date_to);
    if (params?.overdue_only) q.set('overdue_only', 'true');
    if (params?.page) q.set('page', String(params.page));
    if (params?.page_size) q.set('page_size', String(params.page_size));
    if (params?.sort) q.set('sort', params.sort);

    const res = await apiClient.get<{ items: Invoice[]; total: number; kpis?: any }>(`/invoices?${q.toString()}`);
    return res.data;
  },

  async list(params?: {
    search?: string;
    status?: string;
    customer_id?: string;
    date_from?: string;
    date_to?: string;
    overdue_only?: boolean;
    page?: number;
    page_size?: number;
    sort?: string;
  }): Promise<{ items: Invoice[]; total: number; kpis?: any }> {
    return this.listInvoices(params);
  },

  async getInvoices(params?: any) {
    return this.listInvoices(params);
  },

  async getInvoicePayments(id: string) {
    return this.listPayments(id);
  },

  async getInvoice(id: string): Promise<Invoice> {
    const res = await apiClient.get<Invoice>(`/invoices/${id}`);
    return res.data;
  },

  async createInvoice(data: any): Promise<Invoice> {
    const res = await apiClient.post<Invoice>('/invoices', data);
    return res.data;
  },

  async updateInvoice(id: string, data: any): Promise<Invoice> {
    const res = await apiClient.patch<Invoice>(`/invoices/${id}`, data);
    return res.data;
  },

  async deleteInvoice(id: string): Promise<void> {
    await apiClient.delete(`/invoices/${id}`);
  },

  async sendInvoice(id: string): Promise<Invoice> {
    const res = await apiClient.post<Invoice>(`/invoices/${id}/send`);
    return res.data;
  },

  async sendReminder(id: string): Promise<Invoice> {
    const res = await apiClient.post<Invoice>(`/invoices/${id}/send-reminder`);
    return res.data;
  },

  async voidInvoice(id: string, reason?: string): Promise<Invoice> {
    const res = await apiClient.post<Invoice>(`/invoices/${id}/void`, {
      reason: reason && reason.trim() ? reason.trim() : 'Voided by user',
    });
    return res.data;
  },

  async recordPayment(id: string, data: PaymentRecordIn): Promise<any> {
    const methodStr = (data.payment_method || 'bank_transfer').toLowerCase();
    const res = await apiClient.post<any>(`/invoices/${id}/record-payment`, {
      amount: data.amount,
      paid_at: data.payment_date ? `${data.payment_date}T00:00:00Z` : undefined,
      method: methodStr,
      reference: data.reference_number || undefined,
      notes: data.notes || undefined,
    });
    return res.data;
  },

  async listPayments(id: string): Promise<any[]> {
    try {
      const res = await apiClient.get<any[]>(`/invoices/${id}/payments`);
      return res.data || [];
    } catch {
      return [];
    }
  },

  getDownloadPdfUrl(id: string): string {
    return `${apiClient.defaults.baseURL || '/api/v1'}/invoices/${id}/pdf`;
  },
};
