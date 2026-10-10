import { apiClient } from './apiClient';
import type { Paginated } from '../types/api';
import type {
  BillingCycleOut,
  UsageAggregateOut,
  UsageEventBatchIn,
  UsageEventIn,
  UsageEventOut,
  UsageHistoryQuery,
  UsageMeterCreateIn,
  UsageMeterOut,
  UsageMeterSummaryOut,
  UsageMeterUpdateIn,
} from '../types/meters';

export const meterService = {
  list: async (): Promise<UsageMeterOut[]> => {
    const { data } = await apiClient.get<UsageMeterOut[]>('/meters');
    return data;
  },

  /** Accepts a meter id or a meter code. */
  get: async (idOrCode: string): Promise<UsageMeterOut> => {
    const { data } = await apiClient.get<UsageMeterOut>(`/meters/${encodeURIComponent(idOrCode)}`);
    return data;
  },

  create: async (body: UsageMeterCreateIn): Promise<UsageMeterOut> => {
    const { data } = await apiClient.post<UsageMeterOut>('/meters', body);
    return data;
  },

  update: async (idOrCode: string, body: UsageMeterUpdateIn): Promise<UsageMeterOut> => {
    const { data } = await apiClient.patch<UsageMeterOut>(`/meters/${encodeURIComponent(idOrCode)}`, body);
    return data;
  },

  /** A subscription's billing cycles, newest first (for the finalize-usage picker). */
  listBillingCycles: async (subscriptionId: string): Promise<BillingCycleOut[]> => {
    const { data } = await apiClient.get<BillingCycleOut[]>('/meters/billing-cycles', {
      params: { subscription_id: subscriptionId },
    });
    return data;
  },

  /** Idempotent: re-sending the same (meter, idempotency_key) returns the original event. */
  recordEvent: async (body: UsageEventIn): Promise<UsageEventOut> => {
    const { data } = await apiClient.post<UsageEventOut>('/meters/events', body);
    return data;
  },

  /** Up to 1000 events per call. */
  recordBatch: async (body: UsageEventBatchIn): Promise<UsageEventOut[]> => {
    const { data } = await apiClient.post<UsageEventOut[]>('/meters/events/batch', body);
    return data;
  },

  /** Recorded usage events, newest first (meter_id accepts an id or a code). */
  listEvents: async (
    query: UsageHistoryQuery & { page?: number; page_size?: number } = {}
  ): Promise<Paginated<UsageEventOut>> => {
    const { data } = await apiClient.get<Paginated<UsageEventOut>>('/meters/events', { params: query });
    return data;
  },

  /** Per-meter running totals of recorded usage (every meter, zero when unused). */
  usageSummary: async (query: UsageHistoryQuery = {}): Promise<UsageMeterSummaryOut[]> => {
    const { data } = await apiClient.get<UsageMeterSummaryOut[]>('/meters/usage-summary', { params: query });
    return data;
  },

  /** Rates every meter with usage in the cycle; returns one aggregate per meter. */
  finalizeCycleUsage: async (
    subscriptionId: string,
    cycleId: string
  ): Promise<UsageAggregateOut[]> => {
    const { data } = await apiClient.post<UsageAggregateOut[]>(
      `/meters/subscriptions/${encodeURIComponent(subscriptionId)}/billing-cycles/${encodeURIComponent(cycleId)}/finalize-usage`
    );
    return data;
  },
};
