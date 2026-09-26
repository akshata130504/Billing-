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
  page?: number;
  page_size?: number;
}

export interface LifecyclePage {
  items: CustomerLifecycleItem[];
  /** From the X-Total-Count header; null when the header is not readable (CORS). */
  total: number | null;
}

export const lifecycleService = {
  list: async (params?: LifecycleListParams): Promise<CustomerLifecycleItem[]> => {
    const { data } = await apiClient.get<CustomerLifecycleItem[]>('/lifecycle', {
      params: cleanParams(params),
    });
    return data;
  },

  /** One page of lifecycles plus the total matching count (X-Total-Count header). */
  listPage: async (params?: LifecycleListParams): Promise<LifecyclePage> => {
    const response = await apiClient.get<CustomerLifecycleItem[]>('/lifecycle', {
      params: cleanParams(params),
    });
    const raw = response.headers?.['x-total-count'];
    const total = raw !== undefined && raw !== null && raw !== '' ? Number(raw) : null;
    return { items: response.data, total: Number.isFinite(total as number) ? (total as number) : null };
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
