import { apiClient } from './apiClient';

export interface RazorpayStatus {
  provider: 'razorpay';
  is_connected: boolean;
  mode: 'test' | 'live';
  masked_key_id: string | null;
  has_webhook_secret: boolean;
  last_tested_at: string | null;
  status_message: string | null;
}

export interface SMTPStatus {
  provider: 'smtp';
  is_connected: boolean;
  host: string | null;
  port: number | null;
  username: string | null;
  use_tls: boolean;
  use_ssl: boolean;
  from_email: string | null;
  from_name: string | null;
  has_password: boolean;
  last_tested_at: string | null;
  status_message: string | null;
}

export interface WebhookStatus {
  provider: 'webhook';
  is_connected: boolean;
  url: string | null;
  events: string[];
  has_signing_secret: boolean;
  last_tested_at: string | null;
  status_message: string | null;
}

export interface StubIntegrationStatus {
  provider: string;
  is_connected: false;
  status: 'coming_soon';
  status_message: string;
}

export interface AllIntegrationsStatus {
  razorpay: RazorpayStatus;
  smtp: SMTPStatus;
  webhook: WebhookStatus;
  accounting: StubIntegrationStatus;
  crm: StubIntegrationStatus;
  storage: StubIntegrationStatus;
}

export interface TestResultResponse {
  success: boolean;
  message: string;
  details?: Record<string, any>;
}

export const integrationsService = {
  getAll: async (): Promise<AllIntegrationsStatus> => {
    const { data } = await apiClient.get<AllIntegrationsStatus>('/settings/integrations');
    return data;
  },

  // Razorpay
  testRazorpay: async (payload: { key_id: string; key_secret: string }): Promise<TestResultResponse> => {
    const { data } = await apiClient.post<TestResultResponse>('/settings/integrations/razorpay/test', payload);
    return data;
  },

  configureRazorpay: async (payload: {
    key_id: string;
    key_secret: string;
    webhook_secret?: string;
    mode: 'test' | 'live';
  }): Promise<RazorpayStatus> => {
    const { data } = await apiClient.post<RazorpayStatus>('/settings/integrations/razorpay', payload);
    return data;
  },

  disconnectRazorpay: async (): Promise<RazorpayStatus> => {
    const { data } = await apiClient.delete<RazorpayStatus>('/settings/integrations/razorpay');
    return data;
  },

  // SMTP
  testSMTP: async (payload: {
    host: string;
    port: number;
    username?: string;
    password?: string;
    use_tls: boolean;
    use_ssl: boolean;
  }): Promise<TestResultResponse> => {
    const { data } = await apiClient.post<TestResultResponse>('/settings/integrations/smtp/test', payload);
    return data;
  },

  sendTestEmail: async (payload: {
    recipient_email: string;
    host?: string;
    port?: number;
    username?: string;
    password?: string;
    use_tls?: boolean;
    use_ssl?: boolean;
    from_email?: string;
    from_name?: string;
  }): Promise<TestResultResponse> => {
    const { data } = await apiClient.post<TestResultResponse>('/settings/integrations/smtp/test-email', payload);
    return data;
  },

  configureSMTP: async (payload: {
    host: string;
    port: number;
    username?: string;
    password?: string;
    use_tls: boolean;
    use_ssl: boolean;
    from_email: string;
    from_name: string;
  }): Promise<SMTPStatus> => {
    const { data } = await apiClient.post<SMTPStatus>('/settings/integrations/smtp', payload);
    return data;
  },

  disconnectSMTP: async (): Promise<SMTPStatus> => {
    const { data } = await apiClient.delete<SMTPStatus>('/settings/integrations/smtp');
    return data;
  },

  // Outbound Webhooks
  getWebhook: async (): Promise<WebhookStatus> => {
    const { data } = await apiClient.get<WebhookStatus>('/settings/integrations/webhooks');
    return data;
  },

  testWebhook: async (payload: {
    url: string;
    signing_secret?: string;
    event_type?: string;
  }): Promise<TestResultResponse> => {
    const { data } = await apiClient.post<TestResultResponse>('/settings/integrations/webhooks/test', payload);
    return data;
  },

  configureWebhook: async (payload: {
    url: string;
    signing_secret?: string;
    events: string[];
    is_enabled: boolean;
  }): Promise<WebhookStatus> => {
    const { data } = await apiClient.post<WebhookStatus>('/settings/integrations/webhooks', payload);
    return data;
  },

  disconnectWebhook: async (): Promise<WebhookStatus> => {
    const { data } = await apiClient.delete<WebhookStatus>('/settings/integrations/webhooks');
    return data;
  },
};
