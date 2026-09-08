import { apiClient, cleanParams } from './apiClient';
import type { Paginated, InvoiceOut } from '../types/api';
import type {
  CollectionActivityIn,
  CollectionActivityOut,
  CollectionInvoiceDetailOut,
  CollectionInvoiceListParams,
  CollectionInvoiceOut,
  CollectionsDashboardOut,
  CollectionStatusUpdate,
  PromiseToPayIn,
  PromiseToPayOut,
  PromiseToPayUpdate,
} from '../types/collections';

export const collectionsService = {
  dashboard: async (): Promise<CollectionsDashboardOut> => {
    const { data } = await apiClient.get<CollectionsDashboardOut>('/collections/dashboard');
    return data;
  },

  list: async (params?: CollectionInvoiceListParams): Promise<Paginated<CollectionInvoiceOut>> => {
    const { data } = await apiClient.get<Paginated<CollectionInvoiceOut>>('/collections/invoices', {
      params: cleanParams(params),
    });
    return data;
  },

  get: async (id: string): Promise<CollectionInvoiceDetailOut> => {
    const { data } = await apiClient.get<CollectionInvoiceDetailOut>(`/collections/invoices/${id}`);
    return data;
  },

  listActivities: async (id: string): Promise<CollectionActivityOut[]> => {
    const { data } = await apiClient.get<CollectionActivityOut[]>(
      `/collections/invoices/${id}/activities`
    );
    return data;
  },

  addActivity: async (id: string, body: CollectionActivityIn): Promise<CollectionActivityOut> => {
    const { data } = await apiClient.post<CollectionActivityOut>(
      `/collections/invoices/${id}/activities`,
      body
    );
    return data;
  },

  addPromise: async (id: string, body: PromiseToPayIn): Promise<PromiseToPayOut> => {
    const { data } = await apiClient.post<PromiseToPayOut>(
      `/collections/invoices/${id}/promises`,
      body
    );
    return data;
  },

  updatePromise: async (promiseId: string, body: PromiseToPayUpdate): Promise<PromiseToPayOut> => {
    const { data } = await apiClient.patch<PromiseToPayOut>(
      `/collections/promises/${promiseId}`,
      body
    );
    return data;
  },

  updateStatus: async (
    id: string,
    body: CollectionStatusUpdate
  ): Promise<CollectionInvoiceDetailOut> => {
    const { data } = await apiClient.patch<CollectionInvoiceDetailOut>(
      `/collections/invoices/${id}/status`,
      body
    );
    return data;
  },

  sendReminder: async (id: string): Promise<InvoiceOut> => {
    const { data } = await apiClient.post<InvoiceOut>(`/collections/invoices/${id}/send-reminder`);
    return data;
  },
};
