import { apiClient, cleanParams } from './apiClient';
import type {
  TimeEntryCreate,
  TimeEntryRead,
  TimeEntryStatus,
  TimeEntrySummaryKPIs,
  TimeEntryUpdate,
  TimesheetInvoiceCreate,
  WeeklyTimesheetResponse,
} from '../types/api';

export interface TimesheetListParams {
  start_date?: string;
  end_date?: string;
  customer_id?: string;
  project_id?: string;
  user_id?: string;
  billable?: boolean;
  status?: TimeEntryStatus;
  search?: string;
}

export const timesheetService = {
  list: async (params?: TimesheetListParams): Promise<TimeEntryRead[]> => {
    const { data } = await apiClient.get<TimeEntryRead[]>('/timesheets', {
      params: cleanParams(params),
    });
    return data;
  },

  summary: async (params?: { start_date?: string; end_date?: string }): Promise<TimeEntrySummaryKPIs> => {
    const { data } = await apiClient.get<TimeEntrySummaryKPIs>('/timesheets/summary', {
      params: cleanParams(params),
    });
    return data;
  },

  weekly: async (weekStart: string): Promise<WeeklyTimesheetResponse> => {
    const { data } = await apiClient.get<WeeklyTimesheetResponse>('/timesheets/weekly', {
      params: { week_start: weekStart },
    });
    return data;
  },

  get: async (id: string): Promise<TimeEntryRead> => {
    const { data } = await apiClient.get<TimeEntryRead>(`/timesheets/${id}`);
    return data;
  },

  create: async (body: TimeEntryCreate): Promise<TimeEntryRead> => {
    const { data } = await apiClient.post<TimeEntryRead>('/timesheets', body);
    return data;
  },

  update: async (id: string, body: TimeEntryUpdate): Promise<TimeEntryRead> => {
    const { data } = await apiClient.patch<TimeEntryRead>(`/timesheets/${id}`, body);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/timesheets/${id}`);
  },

  submit: async (id: string): Promise<TimeEntryRead> => {
    const { data } = await apiClient.post<TimeEntryRead>(`/timesheets/${id}/submit`);
    return data;
  },

  approve: async (id: string): Promise<TimeEntryRead> => {
    const { data } = await apiClient.post<TimeEntryRead>(`/timesheets/${id}/approve`);
    return data;
  },

  reject: async (id: string, reason?: string): Promise<TimeEntryRead> => {
    const { data } = await apiClient.post<TimeEntryRead>(`/timesheets/${id}/reject`, { reason });
    return data;
  },

  generateInvoice: async (body: TimesheetInvoiceCreate): Promise<any> => {
    const { data } = await apiClient.post<any>('/timesheets/generate-invoice', body);
    return data;
  },
};
