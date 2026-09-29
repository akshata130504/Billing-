import { apiClient } from './apiClient';

/** Every channel the backend knows about. `sms` exists only for legacy rows - it cannot deliver. */
export type NotificationChannel = 'email' | 'sms' | 'webhook';
/** Channels a template can be created with. SMS is rejected by the API (422 "SMS delivery is not supported yet"). */
export type SupportedNotificationChannel = Exclude<NotificationChannel, 'sms'>;

export const NOTIFICATION_CHANNEL_LABELS: Record<NotificationChannel, string> = {
  email: 'Email',
  sms: 'SMS',
  webhook: 'Webhook',
};

/** Shown wherever SMS appears, so the UI never implies SMS messages are sent. */
export const SMS_NOT_AVAILABLE_MESSAGE = 'SMS delivery is not supported yet';

export function isChannelSupported(channel: NotificationChannel): boolean {
  return channel !== 'sms';
}

export interface NotificationTemplate {
  id: string;
  name: string;
  code: string;
  channel: NotificationChannel;
  /** False for channels with no delivery provider (SMS); such templates never send. */
  channel_supported?: boolean;
  subject_template?: string | null;
  body_template: string;
  description?: string | null;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at?: string | null;
}

export interface NotificationChannelInfo {
  channel: NotificationChannel;
  supported: boolean;
  reason?: string | null;
}

/** The signed-in user's in-app notification preferences (per organization, stored server-side). */
export interface NotificationPreferences {
  paymentReceived: boolean;
  paymentFailed: boolean;
  invoiceCreated: boolean;
  invoiceOverdue: boolean;
  invoicePaid: boolean;
  refundProcessed: boolean;
  subscriptionCreated: boolean;
  subscriptionUpgraded: boolean;
  subscriptionDowngraded: boolean;
  subscriptionCancelled: boolean;
  trialEnding: boolean;
  trialExpired: boolean;
  newCustomer: boolean;
  customerPortalActivity: boolean;
  paymentMethodChanges: boolean;
  systemAlerts: boolean;
  serviceNotifications: boolean;
  securityAlerts: boolean;
  emailNotifications: boolean;
  inAppNotifications: boolean;
}

export interface NotificationPreferencesResponse {
  preferences: NotificationPreferences;
  updated_at: string | null;
}

export interface NotificationReadStateItem {
  key: string;
  read_at: string | null;
  dismissed_at: string | null;
}

export type NotificationReadStateAction = 'read' | 'dismiss' | 'read_all';

/** Query keys are scoped by user + organization so switching org never shows another org's state. */
export const notificationQueryKeys = {
  preferences: (userId?: string, orgId?: string) => ['notifications', 'preferences', userId, orgId] as const,
  readState: (userId?: string, orgId?: string) => ['notifications', 'read-state', userId, orgId] as const,
};

export interface NotificationTemplateCreate {
  name: string;
  code: string;
  channel?: SupportedNotificationChannel;
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

  listChannels: async (): Promise<NotificationChannelInfo[]> => {
    const { data } = await apiClient.get<NotificationChannelInfo[]>('/notifications/channels');
    return data;
  },

  getPreferences: async (): Promise<NotificationPreferencesResponse> => {
    const { data } = await apiClient.get<NotificationPreferencesResponse>('/notifications/preferences');
    return data;
  },

  updatePreferences: async (prefs: Partial<NotificationPreferences>): Promise<NotificationPreferencesResponse> => {
    const { data } = await apiClient.put<NotificationPreferencesResponse>('/notifications/preferences', prefs);
    return data;
  },

  getReadState: async (): Promise<NotificationReadStateItem[]> => {
    const { data } = await apiClient.get<{ items: NotificationReadStateItem[] }>('/notifications/read-state');
    return data.items;
  },

  /** `read_all` without keys marks every item currently in the action center as read. */
  updateReadState: async (
    action: NotificationReadStateAction,
    keys?: string[]
  ): Promise<NotificationReadStateItem[]> => {
    const { data } = await apiClient.post<{ items: NotificationReadStateItem[] }>('/notifications/read-state', {
      action,
      ...(keys && keys.length ? { keys } : {}),
    });
    return data.items;
  },
};
