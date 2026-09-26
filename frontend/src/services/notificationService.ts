import { apiClient } from './apiClient';

export interface NotificationTemplate {
  id: string;
  name: string;
  code: string;
  channel: 'email' | 'sms' | 'webhook';
  subject_template?: string | null;
  body_template: string;
  description?: string | null;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at?: string | null;
}

export interface NotificationTemplateCreate {
  name: string;
  code: string;
  channel?: 'email' | 'sms' | 'webhook';
  subject_template?: string;
  body_template: string;
  description?: string;
  is_active?: boolean;
}

export interface NotificationTemplateUpdate {
  name?: string;
  subject_template?: string;
  body_template?: string;
  description?: string;
  is_active?: boolean;
}

export interface NotificationTemplatePreview {
  subject: string;
  body_html: string;
  body_text: string;
}

export const notificationService = {
  listTemplates: async (): Promise<NotificationTemplate[]> => {
    const { data } = await apiClient.get<NotificationTemplate[]>('/notifications/templates');
    return data;
  },

  getTemplate: async (id: string): Promise<NotificationTemplate> => {
    const { data } = await apiClient.get<NotificationTemplate>(`/notifications/templates/${id}`);
    return data;
  },

  createTemplate: async (body: NotificationTemplateCreate): Promise<NotificationTemplate> => {
    const { data } = await apiClient.post<NotificationTemplate>('/notifications/templates', body);
    return data;
  },

  updateTemplate: async (id: string, body: NotificationTemplateUpdate): Promise<NotificationTemplate> => {
    const { data } = await apiClient.put<NotificationTemplate>(`/notifications/templates/${id}`, body);
    return data;
  },

  deleteTemplate: async (id: string): Promise<void> => {
    await apiClient.delete(`/notifications/templates/${id}`);
  },

  previewTemplate: async (
    id: string,
    overrides?: { subject_template?: string; body_template?: string; context?: Record<string, unknown> }
  ): Promise<NotificationTemplatePreview> => {
    const { data } = await apiClient.post<NotificationTemplatePreview>(`/notifications/templates/${id}/preview`, overrides);
    return data;
  },

  sendTestEmail: async (id: string, recipient: string): Promise<{ success: boolean; recipient: string }> => {
    const { data } = await apiClient.post<{ success: boolean; recipient: string }>(`/notifications/templates/${id}/test-send`, {
      recipient,
    });
    return data;
  },
};
