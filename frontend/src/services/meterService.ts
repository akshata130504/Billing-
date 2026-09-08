import { apiClient } from './apiClient';
import type {
  UsageAggregateOut,
  UsageEventBatchIn,
  UsageEventIn,
  UsageEventOut,
  UsageMeterCreateIn,
  UsageMeterOut,
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

  finalizeCycleUsage: async (
    subscriptionId: string,
    cycleId: string
  ): Promise<UsageAggregateOut> => {
    const { data } = await apiClient.post<UsageAggregateOut>(
      `/meters/subscriptions/${encodeURIComponent(subscriptionId)}/billing-cycles/${encodeURIComponent(cycleId)}/finalize-usage`
    );
    return data;
  },
};
