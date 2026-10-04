import { apiClient, cleanParams } from './apiClient';
import type {
  DeleteResponse,
  DocumentTemplate,
  DocumentTemplateCreate,
  DocumentTemplatePreview,
  DocumentTemplateUpdate,
  DocumentType,
  NumberSeries,
  NumberSeriesCreate,
  NumberSeriesPreviewRequest,
  NumberSeriesPreviewResponse,
  NumberSeriesUpdate,
  ReportingTag,
  ReportingTagCreate,
  ReportingTagUpdate,
  WebhookDelivery,
  WebhookDeliveryListParams,
  WebTab,
  WebTabCreate,
  WebTabUpdate,
} from '../types/customization';

export const customizationService = {
  // -------------------------------------------------------------------------
  // Document templates
  // -------------------------------------------------------------------------
  listTemplates: async (params?: { document_type?: DocumentType }): Promise<DocumentTemplate[]> => {
    const { data } = await apiClient.get<DocumentTemplate[]>('/templates', { params: cleanParams(params) });
    return data;
  },

  getTemplate: async (id: string): Promise<DocumentTemplate> => {
    const { data } = await apiClient.get<DocumentTemplate>(`/templates/${id}`);
    return data;
  },

  createTemplate: async (body: DocumentTemplateCreate): Promise<DocumentTemplate> => {
    const { data } = await apiClient.post<DocumentTemplate>('/templates', body);
    return data;
  },

  updateTemplate: async (id: string, body: DocumentTemplateUpdate): Promise<DocumentTemplate> => {
    const { data } = await apiClient.put<DocumentTemplate>(`/templates/${id}`, body);
    return data;
  },

  deleteTemplate: async (id: string): Promise<DeleteResponse> => {
    const { data } = await apiClient.delete<DeleteResponse>(`/templates/${id}`);
    return data;
  },

  previewTemplate: async (id: string): Promise<DocumentTemplatePreview> => {
    const { data } = await apiClient.post<DocumentTemplatePreview>(`/templates/${id}/preview`);
    return data;
  },

  uploadTemplateLogo: async (id: string, file: File): Promise<{ logo_url: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await apiClient.post<{ logo_url: string }>(`/templates/${id}/logo`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  deleteTemplateLogo: async (id: string): Promise<void> => {
    await apiClient.delete(`/templates/${id}/logo`);
  },

  // -------------------------------------------------------------------------
  // Reporting tags
  // -------------------------------------------------------------------------
  listReportingTags: async (): Promise<ReportingTag[]> => {
    const { data } = await apiClient.get<ReportingTag[]>('/reporting-tags');
    return data;
  },

  getReportingTag: async (id: string): Promise<ReportingTag> => {
    const { data } = await apiClient.get<ReportingTag>(`/reporting-tags/${id}`);
    return data;
  },

  createReportingTag: async (body: ReportingTagCreate): Promise<ReportingTag> => {
    const { data } = await apiClient.post<ReportingTag>('/reporting-tags', body);
    return data;
  },

  updateReportingTag: async (id: string, body: ReportingTagUpdate): Promise<ReportingTag> => {
    const { data } = await apiClient.put<ReportingTag>(`/reporting-tags/${id}`, body);
    return data;
  },

  deleteReportingTag: async (id: string): Promise<DeleteResponse> => {
    const { data } = await apiClient.delete<DeleteResponse>(`/reporting-tags/${id}`);
    return data;
  },

  // -------------------------------------------------------------------------
  // Transaction number series
  // -------------------------------------------------------------------------
  listNumberSeries: async (params?: { module?: string }): Promise<NumberSeries[]> => {
    const { data } = await apiClient.get<NumberSeries[]>('/settings/number-series', {
      params: cleanParams(params),
    });
    return data;
  },

  getNumberSeries: async (id: string): Promise<NumberSeries> => {
    const { data } = await apiClient.get<NumberSeries>(`/settings/number-series/${id}`);
    return data;
  },

  createNumberSeries: async (body: NumberSeriesCreate): Promise<NumberSeries> => {
    const { data } = await apiClient.post<NumberSeries>('/settings/number-series', body);
    return data;
  },

  updateNumberSeries: async (id: string, body: NumberSeriesUpdate): Promise<NumberSeries> => {
    const { data } = await apiClient.put<NumberSeries>(`/settings/number-series/${id}`, body);
    return data;
  },

  deleteNumberSeries: async (id: string): Promise<DeleteResponse> => {
    const { data } = await apiClient.delete<DeleteResponse>(`/settings/number-series/${id}`);
    return data;
  },

  previewNumberSeries: async (body: NumberSeriesPreviewRequest): Promise<NumberSeriesPreviewResponse> => {
    const { data } = await apiClient.post<NumberSeriesPreviewResponse>('/settings/number-series/preview', body);
    return data;
  },

  // -------------------------------------------------------------------------
  // Web tabs
  // -------------------------------------------------------------------------
  listWebTabs: async (): Promise<WebTab[]> => {
    const { data } = await apiClient.get<WebTab[]>('/web-tabs');
    return data;
  },

  getWebTab: async (id: string): Promise<WebTab> => {
    const { data } = await apiClient.get<WebTab>(`/web-tabs/${id}`);
    return data;
  },

  createWebTab: async (body: WebTabCreate): Promise<WebTab> => {
    const { data } = await apiClient.post<WebTab>('/web-tabs', body);
    return data;
  },

  updateWebTab: async (id: string, body: WebTabUpdate): Promise<WebTab> => {
    const { data } = await apiClient.put<WebTab>(`/web-tabs/${id}`, body);
    return data;
  },

  deleteWebTab: async (id: string): Promise<DeleteResponse> => {
    const { data } = await apiClient.delete<DeleteResponse>(`/web-tabs/${id}`);
    return data;
  },

  // -------------------------------------------------------------------------
  // Outbound webhook deliveries
  // -------------------------------------------------------------------------
  listWebhookDeliveries: async (params?: WebhookDeliveryListParams): Promise<WebhookDelivery[]> => {
    const { data } = await apiClient.get<WebhookDelivery[]>('/webhook-deliveries', {
      params: cleanParams(params),
    });
    return data;
  },

  retryWebhookDelivery: async (id: string): Promise<WebhookDelivery> => {
    const { data } = await apiClient.post<WebhookDelivery>(`/webhook-deliveries/${id}/retry`);
    return data;
  },
};
