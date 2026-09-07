import { apiClient, cleanParams } from './apiClient';
import type {
  Paginated,
  PaymentAllocationIn,
  PaymentIn,
  PaymentListParams,
  PaymentOut,
  PaymentUpdate,
  ReconciliationSummary,
  RefundRequest,
} from '../types/api';

export const paymentService = {
  list: async (params?: PaymentListParams): Promise<Paginated<PaymentOut>> => {
    const { data } = await apiClient.get<Paginated<PaymentOut>>('/payments', {
      params: cleanParams(params),
    });
    return data;
  },

  get: async (id: string): Promise<PaymentOut> => {
    const { data } = await apiClient.get<PaymentOut>(`/payments/${id}`);
    return data;
  },

  create: async (body: PaymentIn): Promise<PaymentOut> => {
    const { data } = await apiClient.post<PaymentOut>('/payments', body);
    return data;
  },

  update: async (id: string, body: PaymentUpdate): Promise<PaymentOut> => {
    const { data } = await apiClient.patch<PaymentOut>(`/payments/${id}`, body);
    return data;
  },

  setAllocations: async (id: string, allocations: PaymentAllocationIn[]): Promise<PaymentOut> => {
    const { data } = await apiClient.put<PaymentOut>(`/payments/${id}/allocations`, {
      allocations,
    });
    return data;
  },

  refund: async (id: string, body: RefundRequest): Promise<PaymentOut> => {
    const { data } = await apiClient.post<PaymentOut>(`/payments/${id}/refund`, body);
    return data;
  },

  reconciliationSummary: async (): Promise<ReconciliationSummary> => {
    const { data } = await apiClient.get<ReconciliationSummary>(
      '/payments/reconciliation/summary'
    );
    return data;
  },
};
