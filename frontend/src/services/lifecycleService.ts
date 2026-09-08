import { apiClient, cleanParams } from './apiClient';
import type {
  CustomerLifecycleDetail,
  CustomerLifecycleItem,
  CustomerLifecycleStage,
  CustomerLifecycleUpdate,
  HealthStatus,
  LifecycleKPIs,
  TimelineEvent,
} from '../types/api';

export interface LifecycleListParams {
  stage?: CustomerLifecycleStage;
  health?: HealthStatus;
  search?: string;
}

export const lifecycleService = {
  list: async (params?: LifecycleListParams): Promise<CustomerLifecycleItem[]> => {
    const { data } = await apiClient.get<CustomerLifecycleItem[]>('/lifecycle', {
      params: cleanParams(params),
    });
    return data;
  },

  kpis: async (): Promise<LifecycleKPIs> => {
    const { data } = await apiClient.get<LifecycleKPIs>('/lifecycle/kpis');
    return data;
  },

  get: async (customerId: string): Promise<CustomerLifecycleDetail> => {
    const { data } = await apiClient.get<CustomerLifecycleDetail>(`/lifecycle/${customerId}`);
    return data;
  },

  timeline: async (customerId: string): Promise<TimelineEvent[]> => {
    const { data } = await apiClient.get<TimelineEvent[]>(`/lifecycle/${customerId}/timeline`);
    return data;
  },

  update: async (customerId: string, body: CustomerLifecycleUpdate): Promise<CustomerLifecycleItem> => {
    const { data } = await apiClient.patch<CustomerLifecycleItem>(`/lifecycle/${customerId}`, body);
    return data;
  },
};
