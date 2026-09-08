import { apiClient } from './apiClient';
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

  async markAccepted(id: string): Promise<Quote> {
    const res = await apiClient.post<Quote>(`/quotes/${id}/mark-accepted`);
    return res.data;
  },

  async acceptQuote(id: string): Promise<Quote> {
    const res = await apiClient.post<Quote>(`/quotes/${id}/mark-accepted`);
    return res.data;
  },

  async markDeclined(id: string, reason?: string): Promise<Quote> {
    const res = await apiClient.post<Quote>(`/quotes/${id}/mark-declined`, { reason });
    return res.data;
  },

  async declineQuote(id: string, reason?: string): Promise<Quote> {
    const res = await apiClient.post<Quote>(`/quotes/${id}/mark-declined`, { reason });
    return res.data;
  },

  async convertToInvoice(id: string, data?: QuoteConvertInput): Promise<any> {
    const res = await apiClient.post<any>(`/quotes/${id}/convert`, data || {});
    return res.data;
  },
};
