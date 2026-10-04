/** Rooman platform access to this organization (tenant side; Owner approves, Admin can revoke). */
import { apiClient } from './apiClient';

export interface PlatformAccessGrant {
  id: string;
  organization_id: string;
  organization_name: string | null;
  status: 'pending' | 'approved' | 'active' | 'denied' | 'cancelled' | 'revoked' | 'expired';
  scopes: string[];
  reason: string;
  ticket_ref: string;
  requested_duration_minutes: number;
  is_emergency: boolean;
  requested_by: { id: string; full_name: string; email?: string | null; role?: string | null } | null;
  approved_by: { id: string; full_name: string; kind?: string | null } | null;
  created_at: string | null;
  approved_at: string | null;
  first_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  revoke_reason: string | null;
  denied_reason: string | null;
  request_count: number;
}

export const SCOPE_LABELS: Record<string, string> = {
  READ_METADATA: 'Organization profile and team',
  READ_CUSTOMERS: 'Customers',
  READ_QUOTES: 'Quotes and deals',
  READ_INVOICES: 'Invoices and credit notes',
  READ_PAYMENTS: 'Payments and collections',
  READ_SUBSCRIPTIONS: 'Subscriptions, plans and catalog',
  READ_AUDIT: 'Audit log',
  READ_CONFIG: 'Templates and automation settings',
};

export const platformAccessService = {
  list: async () => (await apiClient.get<{ items: PlatformAccessGrant[] }>('/organization/platform-access')).data.items,
  active: async () => (await apiClient.get<{ items: PlatformAccessGrant[] }>('/organization/platform-access/active')).data.items,
  approve: async (id: string) => (await apiClient.post<PlatformAccessGrant>(`/organization/platform-access/${encodeURIComponent(id)}/approve`, {})).data,
  deny: async (id: string, reason?: string) =>
    (await apiClient.post<PlatformAccessGrant>(`/organization/platform-access/${encodeURIComponent(id)}/deny`, { reason })).data,
  revoke: async (id: string, reason?: string) =>
    (await apiClient.post<PlatformAccessGrant>(`/organization/platform-access/${encodeURIComponent(id)}/revoke`, { reason })).data,
};
