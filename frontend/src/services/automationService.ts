import { apiClient, cleanParams } from './apiClient';
import type {
  AutomationLog,
  AutomationLogsParams,
  AutomationRule,
  AutomationRuleCreate,
  AutomationRuleTestRequest,
  AutomationRuleTestResult,
  AutomationRuleUpdate,
  AutomationRulesParams,
  AutomationSchedule,
  AutomationScheduleCreate,
  AutomationScheduleUpdate,
  ScheduleTriggerResult,
  StatusMessageResponse,
} from '../types/automation';

/**
 * Automation rules, execution logs and schedules.
 * Backend: backend/app/api/v1/endpoints/customization.py (mounted with no prefix).
 */
export const automationService = {
  // --- Rules ---------------------------------------------------------------
  listRules: async (params?: AutomationRulesParams): Promise<AutomationRule[]> => {
    const { data } = await apiClient.get<AutomationRule[]>('/automation/rules', {
      params: cleanParams(params),
    });
    return data;
  },

  getRule: async (ruleId: string): Promise<AutomationRule> => {
    const { data } = await apiClient.get<AutomationRule>(`/automation/rules/${ruleId}`);
    return data;
  },

  createRule: async (body: AutomationRuleCreate): Promise<AutomationRule> => {
    const { data } = await apiClient.post<AutomationRule>('/automation/rules', body);
    return data;
  },

  updateRule: async (ruleId: string, body: AutomationRuleUpdate): Promise<AutomationRule> => {
    const { data } = await apiClient.put<AutomationRule>(`/automation/rules/${ruleId}`, body);
    return data;
  },

  deleteRule: async (ruleId: string): Promise<StatusMessageResponse> => {
    const { data } = await apiClient.delete<StatusMessageResponse>(`/automation/rules/${ruleId}`);
    return data;
  },

  /** Dry-run a rule's conditions against a sample payload. No actions run. */
  testRule: async (ruleId: string, body: AutomationRuleTestRequest): Promise<AutomationRuleTestResult> => {
    const { data } = await apiClient.post<AutomationRuleTestResult>(
      `/automation/rules/${ruleId}/test`,
      body
    );
    return data;
  },

  // --- Logs ----------------------------------------------------------------
  listLogs: async (params?: AutomationLogsParams): Promise<AutomationLog[]> => {
    const { data } = await apiClient.get<AutomationLog[]>('/automation/logs', {
      params: cleanParams(params),
    });
    return data;
  },

  // --- Schedules -----------------------------------------------------------
  listSchedules: async (): Promise<AutomationSchedule[]> => {
    const { data } = await apiClient.get<AutomationSchedule[]>('/automation/schedules');
    return data;
  },

  getSchedule: async (scheduleId: string): Promise<AutomationSchedule> => {
    const { data } = await apiClient.get<AutomationSchedule>(`/automation/schedules/${scheduleId}`);
    return data;
  },

  createSchedule: async (body: AutomationScheduleCreate): Promise<AutomationSchedule> => {
    const { data } = await apiClient.post<AutomationSchedule>('/automation/schedules', body);
    return data;
  },

  updateSchedule: async (
    scheduleId: string,
    body: AutomationScheduleUpdate
  ): Promise<AutomationSchedule> => {
    const { data } = await apiClient.put<AutomationSchedule>(
      `/automation/schedules/${scheduleId}`,
      body
    );
    return data;
  },

  deleteSchedule: async (scheduleId: string): Promise<StatusMessageResponse> => {
    const { data } = await apiClient.delete<StatusMessageResponse>(
      `/automation/schedules/${scheduleId}`
    );
    return data;
  },

  /** Runs the schedule's target action now and advances next_date. */
  triggerSchedule: async (scheduleId: string): Promise<ScheduleTriggerResult> => {
    const { data } = await apiClient.post<ScheduleTriggerResult>(
      `/automation/schedules/${scheduleId}/trigger`
    );
    return data;
  },
};
