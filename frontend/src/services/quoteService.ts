import { apiClient, cleanParams } from './apiClient';
import type {
  InvoiceOut,
  Paginated,
  QuoteConvertRequest,
  QuoteIn,
  QuoteListParams,
  QuoteOut,
  QuoteUpdate,
} from '../types/api';

export const quoteService = {
  list: async (params?: QuoteListParams): Promise<Paginated<QuoteOut>> => {
    const { data } = await apiClient.get<Paginated<QuoteOut>>('/quotes', {
      params: cleanParams(params),
    });
    return data;
  },

  get: async (id: string): Promise<QuoteOut> => {
    const { data } = await apiClient.get<QuoteOut>(`/quotes/${id}`);
    return data;
  },

  create: async (body: QuoteIn): Promise<QuoteOut> => {
    const { data } = await apiClient.post<QuoteOut>('/quotes', body);
    return data;
  },

  update: async (id: string, body: QuoteUpdate): Promise<QuoteOut> => {
    const { data } = await apiClient.patch<QuoteOut>(`/quotes/${id}`, body);
    return data;
  },

  remove: async (id: string): Promise<void> => {
    await apiClient.delete(`/quotes/${id}`);
  },

  send: async (id: string): Promise<QuoteOut> => {
    const { data } = await apiClient.post<QuoteOut>(`/quotes/${id}/send`);
    return data;
  },

  markAccepted: async (id: string): Promise<QuoteOut> => {
    const { data } = await apiClient.post<QuoteOut>(`/quotes/${id}/mark-accepted`, {});
    return data;
  },

  markDeclined: async (id: string, reason?: string): Promise<QuoteOut> => {
    const { data } = await apiClient.post<QuoteOut>(`/quotes/${id}/mark-declined`, {
      reason,
    });
    return data;
  },

  convert: async (id: string, body: QuoteConvertRequest = {}): Promise<InvoiceOut> => {
    const { data } = await apiClient.post<InvoiceOut>(`/quotes/${id}/convert`, body);
    return data;
  },
};
