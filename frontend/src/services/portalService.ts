import { apiClient } from './apiClient';
import type { CustomerPortalSettings, CustomerPortalSettingsUpdate } from '../types/portal';

/**
 * Admin-side Customer Portal API. The customer-facing endpoints
 * (/portal/auth/*, /portal/dashboard, /portal/invoices, ...) authenticate with a
 * separate portal session token (X-Portal-Token) and are not called from the
 * admin app; their contracts are documented in types/portal.ts.
 */
export const portalService = {
  getSettings: async (): Promise<CustomerPortalSettings> => {
    const { data } = await apiClient.get<CustomerPortalSettings>('/portal/settings');
    return data;
  },

  /** Requires admin role on the backend. Only the keys present are updated. */
  updateSettings: async (body: CustomerPortalSettingsUpdate): Promise<CustomerPortalSettings> => {
    const { data } = await apiClient.patch<CustomerPortalSettings>('/portal/settings', body);
    return data;
  },
};
