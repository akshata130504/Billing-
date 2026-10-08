import { apiClient } from './apiClient';
import type { OrganizationAccess } from '../types/api';

export type BillingCycle = 'monthly' | 'quarterly' | 'annual';

export interface ModuleOption {
  key: string;
  label: string;
  description: string;
  base: boolean;
  requires: string[];
}

export interface SubscriptionRequestOut {
  id: string;
  organization_id: string;
  status: 'submitted' | 'approved' | 'rejected' | 'withdrawn';
  modules: string[];
  seats: number;
  billing_cycle: BillingCycle;
  notes: string | null;
  created_at: string;
  reviewed_at: string | null;
  decision_reason: string | null;
  approved_modules: string[] | null;
  approved_seats: number | null;
  approved_billing_cycle: BillingCycle | null;
}

export interface SubscriptionState {
  access: OrganizationAccess;
  modules: ModuleOption[];
  current_request: SubscriptionRequestOut | null;
  history: SubscriptionRequestOut[];
}

export interface SubscriptionRequestCreate {
  modules: string[];
  seats: number;
  billing_cycle: BillingCycle;
  notes?: string | null;
}

export const subscriptionAccessService = {
  state: async (): Promise<SubscriptionState> => {
    const { data } = await apiClient.get<SubscriptionState>('/subscription-requests');
    return data;
  },
  submit: async (body: SubscriptionRequestCreate): Promise<SubscriptionRequestOut> => {
    const { data } = await apiClient.post<SubscriptionRequestOut>('/subscription-requests', body);
    return data;
  },
  withdraw: async (id: string): Promise<SubscriptionRequestOut> => {
    const { data } = await apiClient.post<SubscriptionRequestOut>(`/subscription-requests/${id}/withdraw`);
    return data;
  },
};
