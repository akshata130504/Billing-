import { apiClient } from './apiClient';
import { downloadAuthenticated } from './download';
import type { Quote, QuoteCreateInput, QuoteUpdateInput, QuoteConvertInput } from '../types/quotes';

export const quoteService = {
  async listQuotes(params?: {
    search?: string;
    status?: string;
    customer_id?: string;
    date_from?: string;
    date_to?: string;
    page?: number;
    page_size?: number;
  }): Promise<{ items: Quote[]; total: number }> {
    const q = new URLSearchParams();
    if (params?.search) q.set('search', params.search);
    if (params?.status && params.status !== 'all') q.set('status', params.status);
    if (params?.customer_id) q.set('customer_id', params.customer_id);
    if (params?.date_from) q.set('date_from', params.date_from);
    if (params?.date_to) q.set('date_to', params.date_to);
    if (params?.page) q.set('page', String(params.page));
    if (params?.page_size) q.set('page_size', String(params.page_size));

    const res = await apiClient.get<{ items: Quote[]; total: number }>(`/quotes?${q.toString()}`);
    return res.data;
  },

  async getQuote(id: string): Promise<Quote> {
    const res = await apiClient.get<Quote>(`/quotes/${id}`);
    return res.data;
  },

  async createQuote(data: QuoteCreateInput): Promise<Quote> {
    const res = await apiClient.post<Quote>('/quotes', data);
    return res.data;
  },

  async updateQuote(id: string, data: QuoteUpdateInput): Promise<Quote> {
    const res = await apiClient.patch<Quote>(`/quotes/${id}`, data);
    return res.data;
  },

  async deleteQuote(id: string): Promise<void> {
    await apiClient.delete(`/quotes/${id}`);
  },

  /** Toast copy for a send whose customer email could not be delivered (`email_sent === false`). */
  EMAIL_NOT_SENT_MESSAGE: 'Quote marked as sent but the email could not be delivered (email not configured)',

  async sendQuote(id: string): Promise<Quote> {
    const res = await apiClient.post<Quote>(`/quotes/${id}/send`);
    return res.data;
  },

  async submitForApproval(id: string): Promise<Quote> {
    const res = await apiClient.post<Quote>(`/quotes/${id}/submit`);
    return res.data;
  },

  async approveQuote(id: string): Promise<Quote> {
    const res = await apiClient.post<Quote>(`/quotes/${id}/approve`);
    return res.data;
  },

  async rejectQuote(id: string, reason?: string): Promise<Quote> {
    const res = await apiClient.post<Quote>(`/quotes/${id}/reject`, { reason });
    return res.data;
  },

  async markViewed(id: string): Promise<Quote> {
    const res = await apiClient.post<Quote>(`/quotes/${id}/mark-viewed`);
    return res.data;
  },

  /**
   * ADMIN OVERRIDE: record the customer's acceptance on their behalf (signed PDF, email, phone).
   * Customers accept on their hosted quote link; this is admin-only, needs a reason and is audited
   * separately (QUOTE_ACCEPTED_OVERRIDE).
   */
  async overrideAccept(id: string, reason: string): Promise<Quote> {
    const res = await apiClient.post<Quote>(`/quotes/${id}/mark-accepted`, { reason });
    return res.data;
  },

  /** ADMIN OVERRIDE: record the customer's decline on their behalf (see overrideAccept). */
  async overrideDecline(id: string, reason: string): Promise<Quote> {
    const res = await apiClient.post<Quote>(`/quotes/${id}/mark-declined`, { reason });
    return res.data;
  },

  async convertToInvoice(id: string, data?: QuoteConvertInput): Promise<any> {
    const res = await apiClient.post<any>(`/quotes/${id}/convert`, data || {});
    return res.data;
  },

  getDownloadPdfUrl(id: string): string {
    return `${apiClient.defaults.baseURL || '/api/v1'}/quotes/${id}/pdf`;
  },

  async downloadPdf(id: string, quoteNumber?: string): Promise<void> {
    const url = this.getDownloadPdfUrl(id);
    const filename = quoteNumber ? `Quote-${quoteNumber}.pdf` : `Quote-${id}.pdf`;
    await downloadAuthenticated(url, filename);
  },
};
