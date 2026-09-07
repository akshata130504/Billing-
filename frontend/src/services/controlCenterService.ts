import { absoluteUrl, apiClient, cleanParams } from './apiClient';
import type {
  ActionCenterResponse,
  ActivityItem,
  ActivityParams,
  ApprovalListParams,
  ApprovalOut,
  AuditExportFormat,
  AuditLogOut,
  AuditLogParams,
  CalendarResponse,
  DashboardRange,
  DashboardSummary,
  ImportEntity,
  ImportResult,
  PageParams,
  Paginated,
  RunJobsResult,
  SearchResponse,
  SearchResult,
} from '../types/api';

export const controlCenterService = {
  dashboard: async (range: DashboardRange = '30_days'): Promise<DashboardSummary> => {
    const { data } = await apiClient.get<DashboardSummary>('/dashboard/summary', {
      params: { range },
    });
    return data;
  },

  actionCenter: async (): Promise<ActionCenterResponse> => {
    const { data } = await apiClient.get<ActionCenterResponse>('/action-center');
    return data;
  },

  /** @param month `YYYY-MM` */
  calendar: async (month: string): Promise<CalendarResponse> => {
    const { data } = await apiClient.get<CalendarResponse>('/calendar', { params: { month } });
    return data;
  },

  listApprovals: async (params?: ApprovalListParams): Promise<Paginated<ApprovalOut>> => {
    const { data } = await apiClient.get<Paginated<ApprovalOut>>('/approvals', {
      params: cleanParams(params),
    });
    return data;
  },

  approve: async (id: string, note?: string): Promise<ApprovalOut> => {
    const { data } = await apiClient.post<ApprovalOut>(`/approvals/${id}/approve`, { note });
    return data;
  },

  reject: async (id: string, note: string): Promise<ApprovalOut> => {
    const { data } = await apiClient.post<ApprovalOut>(`/approvals/${id}/reject`, { note });
    return data;
  },

  auditLogs: async (params?: AuditLogParams): Promise<Paginated<AuditLogOut>> => {
    const { data } = await apiClient.get<Paginated<AuditLogOut>>('/audit-logs', {
      params: cleanParams(params),
    });
    return data;
  },

  /**
   * Absolute URL of the audit export (requires the bearer token; pair with
   * `downloadAuthenticated`). Pagination params are ignored by the server.
   */
  auditExportUrl: (format: AuditExportFormat, params?: AuditLogParams): string => {
    const { page: _page, page_size: _pageSize, ...filters } = params ?? {};
    return absoluteUrl('/audit-logs/export', { format, ...filters });
  },

  activity: async (params?: ActivityParams): Promise<Paginated<ActivityItem>> => {
    const { data } = await apiClient.get<Paginated<ActivityItem>>('/activity', {
      params: cleanParams(params),
    });
    return data;
  },

  search: async (q: string, limit = 20): Promise<SearchResult[]> => {
    const { data } = await apiClient.get<SearchResponse>('/search', { params: { q, limit } });
    return data.results;
  },

  /** Absolute URL of the CSV template (requires the bearer token). */
  importTemplateUrl: (entity: ImportEntity): string =>
    absoluteUrl(`/imports/templates/${entity}`),

  runImport: async (entity: ImportEntity, file: File, dryRun: boolean): Promise<ImportResult> => {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('dry_run', dryRun ? 'true' : 'false');
    const { data } = await apiClient.post<ImportResult>(`/imports/${entity}`, form, {
      // Large CSVs can take a while to validate server-side.
      timeout: 120000,
    });
    return data;
  },

  listImports: async (params?: PageParams): Promise<Paginated<ImportResult>> => {
    const { data } = await apiClient.get<Paginated<ImportResult>>('/imports', {
      params: cleanParams(params),
    });
    return data;
  },

  runJobs: async (): Promise<RunJobsResult> => {
    const { data } = await apiClient.post<RunJobsResult>('/admin/jobs/run');
    return data;
  },
};
