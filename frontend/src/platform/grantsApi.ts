/** Tenant access grants - platform console side. The server enforces every rule. */
import { consoleRequest } from './platformApi';

export type GrantStatus = 'pending' | 'approved' | 'active' | 'denied' | 'cancelled' | 'revoked' | 'expired';

export interface AccessGrant {
  id: string;
  organization_id: string;
  organization_name: string | null;
  status: GrantStatus;
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
  last_entered_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  revoked_by_kind: string | null;
  revoke_reason: string | null;
  denied_at: string | null;
  denied_reason: string | null;
  request_count: number;
  reviewed_at: string | null;
  review_notes: string | null;
  review_due_at: string | null;
  review_overdue: boolean;
}

export interface GrantRequestBody {
  organization_id: string;
  scopes: string[];
  duration_minutes: number;
  reason: string;
  ticket_ref: string;
}

export const REQUESTABLE_SCOPES: { value: string; label: string }[] = [
  { value: 'READ_CUSTOMERS', label: 'Customers' },
  { value: 'READ_QUOTES', label: 'Quotes and deals' },
  { value: 'READ_INVOICES', label: 'Invoices and credit notes' },
  { value: 'READ_PAYMENTS', label: 'Payments and collections (masked)' },
  { value: 'READ_SUBSCRIPTIONS', label: 'Subscriptions, plans and catalog' },
  { value: 'READ_AUDIT', label: 'Audit log' },
  { value: 'READ_CONFIG', label: 'Templates and automation settings' },
];

export const SCOPE_NAMES: Record<string, string> = {
  READ_METADATA: 'Organization profile and team',
  ...Object.fromEntries(REQUESTABLE_SCOPES.map((s) => [s.value, s.label])),
};

const id = (v: string) => encodeURIComponent(v);

export const grantsApi = {
  list: (params: { status?: string; emergency?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set('status', params.status);
    if (params.emergency !== undefined) q.set('emergency', String(params.emergency));
    const qs = q.toString();
    return consoleRequest<{ items: AccessGrant[] }>('GET', `/access-grants${qs ? `?${qs}` : ''}`);
  },
  request: (body: GrantRequestBody) => consoleRequest<AccessGrant>('POST', '/access-grants', body),
  requestEmergency: (body: GrantRequestBody) => consoleRequest<AccessGrant>('POST', '/access-grants/emergency', body),
  cancel: (grantId: string) => consoleRequest<AccessGrant>('POST', `/access-grants/${id(grantId)}/cancel`),
  revoke: (grantId: string, reason: string) => consoleRequest<AccessGrant>('POST', `/access-grants/${id(grantId)}/revoke`, { reason }),
  enter: (grantId: string) =>
    consoleRequest<{ grant: AccessGrant; token: string; token_expires_at: string; organization: { id: string; name: string } }>(
      'POST', `/access-grants/${id(grantId)}/enter`
    ),
  approveEmergency: (grantId: string) => consoleRequest<AccessGrant>('POST', `/access-grants/${id(grantId)}/emergency-approve`),
  review: (grantId: string, notes: string) => consoleRequest<AccessGrant>('POST', `/access-grants/${id(grantId)}/review`, { notes }),
};

/** Where the tenant app runs (the grant token is handed ONLY to this exact origin). */
export const TENANT_APP_ORIGIN: string =
  import.meta.env.VITE_TENANT_APP_ORIGIN || (import.meta.env.DEV ? 'http://localhost:5173' : '');
export const GRANT_MESSAGE = 'rooman-platform-grant';
export const READY_MESSAGE = 'rooman-platform-ready';

/**
 * Deliver a grant token to the tenant workspace tab by postMessage, pinned to the tenant origin
 * (never a URL, never storage). Delivered when the tab reports it is ready; stops listening after
 * a minute.
 */
export function handOffGrant(win: Window, token: string) {
  const deliver = () => win.postMessage({ type: GRANT_MESSAGE, token }, TENANT_APP_ORIGIN);
  const onMessage = (event: MessageEvent) => {
    if (event.origin !== TENANT_APP_ORIGIN || event.source !== win) return;
    if ((event.data as { type?: string } | null)?.type === READY_MESSAGE) {
      deliver();
      window.removeEventListener('message', onMessage);
    }
  };
  window.addEventListener('message', onMessage);
  deliver(); // in case the tab is already listening
  setTimeout(() => window.removeEventListener('message', onMessage), 60_000);
}
