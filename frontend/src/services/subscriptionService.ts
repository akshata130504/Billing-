import { apiClient, cleanParams } from './apiClient';
import type {
  InvoiceOut,
  PageParams,
  Paginated,
  SubscriptionCancelRequest,
  SubscriptionIn,
  SubscriptionListParams,
  SubscriptionOut,
  SubscriptionSummaryOut,
  SubscriptionUpdate,
} from '../types/api';

export const subscriptionService = {
  summary: async (): Promise<SubscriptionSummaryOut> => {
    const { data } = await apiClient.get<SubscriptionSummaryOut>('/subscriptions/summary');
    return data;
  },

  list: async (params?: SubscriptionListParams): Promise<Paginated<SubscriptionOut>> => {
    const { data } = await apiClient.get<Paginated<SubscriptionOut>>('/subscriptions', {
      params: cleanParams(params),
    });
    return data;
  },

  get: async (id: string): Promise<SubscriptionOut> => {
    const { data } = await apiClient.get<SubscriptionOut>(`/subscriptions/${id}`);
    return data;
  },

  create: async (body: SubscriptionIn): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>('/subscriptions', body);
    return data;
  },

  update: async (id: string, body: SubscriptionUpdate): Promise<SubscriptionOut> => {
    const { data } = await apiClient.patch<SubscriptionOut>(`/subscriptions/${id}`, body);
    return data;
  },

  activate: async (id: string): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>(`/subscriptions/${id}/activate`);
    return data;
  },

  pause: async (id: string): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>(`/subscriptions/${id}/pause`);
    return data;
  },

  resume: async (id: string): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>(`/subscriptions/${id}/resume`);
    return data;
  },

  renew: async (id: string): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>(`/subscriptions/${id}/renew`);
    return data;
  },

  cancel: async (id: string, body: SubscriptionCancelRequest): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>(`/subscriptions/${id}/cancel`, body);
    return data;
  },

  generateInvoice: async (id: string): Promise<InvoiceOut> => {
    const { data } = await apiClient.post<InvoiceOut>(`/subscriptions/${id}/generate-invoice`);
    return data;
  },

  invoices: async (id: string, params?: PageParams): Promise<Paginated<InvoiceOut>> => {
    const { data } = await apiClient.get<Paginated<InvoiceOut>>(
      `/subscriptions/${id}/invoices`,
      { params: cleanParams(params) }
    );
    return data;
  },
};
