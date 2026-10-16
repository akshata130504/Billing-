import { apiClient, cleanParams } from './apiClient';
import type {
  Paginated,
  PaymentAllocationIn,
  PaymentIn,
  PaymentListParams,
  PaymentOut,
  PaymentStatus,
  PaymentsSummary,
  PaymentUpdate,
  ReconciliationSummary,
  RefundRequest,
} from '../types/api';
import { idempotencyHeaders } from '../utils/idempotency';

/**
 * List/summary query. `status` may be a single status or a comma-separated
 * list (e.g. 'refunded,partially_refunded') which the API matches with OR.
 */
export type BackendPaymentStatus = PaymentStatus | `${PaymentStatus},${string}`;
export type PaymentQueryParams = Omit<PaymentListParams, 'status'> & { status?: BackendPaymentStatus };

export const paymentService = {
  list: async (params?: PaymentQueryParams): Promise<Paginated<PaymentOut>> => {
    const { data } = await apiClient.get<Paginated<PaymentOut>>('/payments', {
      params: cleanParams(params),
    });
    return data;
  },

  get: async (id: string): Promise<PaymentOut> => {
    const { data } = await apiClient.get<PaymentOut>(`/payments/${id}`);
    return data;
  },

  /** Pass the same `idempotencyKey` for every retry of one payment; a fresh key is used otherwise. */
  create: async (body: PaymentIn, idempotencyKey?: string): Promise<PaymentOut> => {
    const { data } = await apiClient.post<PaymentOut>('/payments', body, idempotencyHeaders(idempotencyKey));
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

  /** Org-wide money totals for the same rows list() returns. */
  summary: async (params?: PaymentQueryParams): Promise<PaymentsSummary> => {
    const { data } = await apiClient.get<PaymentsSummary>('/payments/summary', {
      params: cleanParams(params),
    });
    return data;
  },

  reconciliationSummary: async (): Promise<ReconciliationSummary> => {
    const { data } = await apiClient.get<ReconciliationSummary>(
      '/payments/reconciliation/summary'
    );
    return data;
  },
};
