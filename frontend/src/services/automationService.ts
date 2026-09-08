import { apiClient, cleanParams } from './apiClient';
import type { Paginated } from '../types/api';
import type {
  AutomationDashboardOut,
  AutomationExecutionListParams,
  AutomationExecutionOut,
  AutomationRuleActiveIn,
  AutomationRuleIn,
  AutomationRuleListParams,
  AutomationRuleOut,
} from '../types/automation';

export const automationService = {
  dashboard: async (): Promise<AutomationDashboardOut> => {
    const { data } = await apiClient.get<AutomationDashboardOut>('/automation/dashboard');
    return data;
  },

  listRules: async (params?: AutomationRuleListParams): Promise<Paginated<AutomationRuleOut>> => {
    const { data } = await apiClient.get<Paginated<AutomationRuleOut>>('/automation/rules', {
      params: cleanParams(params),
    });
    return data;
  },

  createRule: async (body: AutomationRuleIn): Promise<AutomationRuleOut> => {
    const { data } = await apiClient.post<AutomationRuleOut>('/automation/rules', body);
    return data;
  },

  setRuleActive: async (id: string, body: AutomationRuleActiveIn): Promise<AutomationRuleOut> => {
    const { data } = await apiClient.patch<AutomationRuleOut>(`/automation/rules/${id}`, body);
    return data;
  },

  deleteRule: async (id: string): Promise<void> => {
    await apiClient.delete(`/automation/rules/${id}`);
  },

  listExecutions: async (
    params?: AutomationExecutionListParams
  ): Promise<Paginated<AutomationExecutionOut>> => {
    const { data } = await apiClient.get<Paginated<AutomationExecutionOut>>('/automation/executions', {
      params: cleanParams(params),
    });
    return data;
  },
};
