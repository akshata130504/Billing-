import { apiClient, cleanParams } from './apiClient';
import type {
  DunningCase,
  DunningCaseDetail,
  DunningCaseListParams,
  DunningCasePauseIn,
  DunningCaseStopIn,
  DunningMetrics,
  DunningPolicy,
  DunningPolicyCreate,
  DunningPolicyUpdate,
  ExpiringCardNotice,
  ReactivateSubscriptionResponse,
} from '../types/dunning';

export const dunningService = {
  // --- Policies -------------------------------------------------------------
  listPolicies: async (): Promise<DunningPolicy[]> => {
    const { data } = await apiClient.get<DunningPolicy[]>('/dunning/policies');
    return data;
  },

  createPolicy: async (body: DunningPolicyCreate): Promise<DunningPolicy> => {
    const { data } = await apiClient.post<DunningPolicy>('/dunning/policies', body);
    return data;
  },

  updatePolicy: async (policyId: string, body: DunningPolicyUpdate): Promise<DunningPolicy> => {
    const { data } = await apiClient.put<DunningPolicy>(`/dunning/policies/${policyId}`, body);
    return data;
  },

  // --- Cases ----------------------------------------------------------------
  listCases: async (params?: DunningCaseListParams): Promise<DunningCase[]> => {
    const { data } = await apiClient.get<DunningCase[]>('/dunning/cases', {
      params: cleanParams(params),
    });
    return data;
  },

  getCase: async (caseId: string): Promise<DunningCaseDetail> => {
    const { data } = await apiClient.get<DunningCaseDetail>(`/dunning/cases/${caseId}`);
    return data;
  },

  pauseCase: async (caseId: string, body: DunningCasePauseIn = {}): Promise<DunningCase> => {
    const { data } = await apiClient.post<DunningCase>(`/dunning/cases/${caseId}/pause`, body);
    return data;
  },

  resumeCase: async (caseId: string): Promise<DunningCase> => {
    const { data } = await apiClient.post<DunningCase>(`/dunning/cases/${caseId}/resume`);
    return data;
  },

  stopCase: async (caseId: string, body: DunningCaseStopIn = {}): Promise<DunningCase> => {
    const { data } = await apiClient.post<DunningCase>(`/dunning/cases/${caseId}/stop`, body);
    return data;
  },

  retryNow: async (caseId: string): Promise<DunningCaseDetail> => {
    const { data } = await apiClient.post<DunningCaseDetail>(`/dunning/cases/${caseId}/retry-now`);
    return data;
  },

  reactivateSubscription: async (subscriptionId: string): Promise<ReactivateSubscriptionResponse> => {
    const { data } = await apiClient.post<ReactivateSubscriptionResponse>(
      `/dunning/subscriptions/${subscriptionId}/reactivate`
    );
    return data;
  },

  // --- Analytics & pre-dunning ---------------------------------------------
  metrics: async (): Promise<DunningMetrics> => {
    const { data } = await apiClient.get<DunningMetrics>('/dunning/metrics');
    return data;
  },

  expiringCards: async (days = 30): Promise<ExpiringCardNotice[]> => {
    const { data } = await apiClient.get<ExpiringCardNotice[]>('/dunning/expiring-cards', {
      params: { days },
    });
    return data;
  },
};
