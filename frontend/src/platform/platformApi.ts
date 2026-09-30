/**
 * Platform (Rooman staff) API client - deliberately separate from the tenant apiClient.
 *
 * The platform session lives in HttpOnly cookies set by the server (the access token is never
 * visible to this code, and nothing is written to localStorage). State-changing requests echo the
 * readable CSRF cookie in the X-Platform-CSRF header (double submit). Tenant tokens are never sent.
 *
 * The console is served from its own origin and always calls that same origin (no configurable API
 * origin, no cross-origin credentials); it imports nothing from the tenant API client.
 */
const BASE = '/api/v1/platform/auth';
// "__Host-" prefixed when the server uses secure cookies (production), plain in local http dev.
const CSRF_COOKIES = ['__Host-rb_platform_csrf', 'rb_platform_csrf'];
const CSRF_HEADER = 'X-Platform-CSRF';

export type PlatformRole = 'platform_administrator' | 'platform_operations' | 'platform_support';

export interface PlatformStaff {
  id: string;
  email: string;
  full_name: string;
  role: PlatformRole;
  last_login_at?: string | null;
}

export interface PlatformMe {
  staff: PlatformStaff;
  session_id: string;
  session_expires_at: string;
  access_expires_in: number;
}

export interface PlatformSessionInfo {
  id: string;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  ip_address?: string | null;
  user_agent?: string | null;
  current: boolean;
}

export interface PlatformStepUp {
  step_up_expires_at: string;
  expires_in: number;
}

export interface PlatformChallenge {
  two_factor_required: true;
  challenge_token: string;
  expires_in: number;
}

export class PlatformApiError extends Error {
  constructor(message: string, public status: number, public code?: string) {
    super(message);
  }
}

export const ROLE_LABELS: Record<PlatformRole, string> = {
  platform_administrator: 'Platform Administrator (Super Admin)',
  platform_operations: 'Platform Operations',
  platform_support: 'Platform Support',
};

function readCookie(name: string): string | null {
  const match = document.cookie.split('; ').find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') {
    const csrf = CSRF_COOKIES.map(readCookie).find((value) => value);
    if (csrf) headers[CSRF_HEADER] = csrf;
  }
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: 'same-origin',
  });
  if (res.status === 204) return undefined as T;
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const message = data?.error?.message || data?.detail || 'Request failed.';
    throw new PlatformApiError(message, res.status, data?.error?.code);
  }
  return data as T;
}

export const platformApi = {
  login: (email: string, password: string) => request<PlatformChallenge>('POST', '/login', { email, password }),
  verifyTwoFactor: (challenge_token: string, code: string) =>
    request<PlatformMe>('POST', '/2fa', { challenge_token, code }),
  me: () => request<PlatformMe>('GET', '/me'),
  refresh: () => request<PlatformMe>('POST', '/refresh'),
  sessions: () => request<{ sessions: PlatformSessionInfo[] }>('GET', '/sessions'),
  revokeSession: (id: string) => request<void>('DELETE', `/sessions/${encodeURIComponent(id)}`),
  logout: () => request<void>('POST', '/logout'),
  logoutAll: () => request<{ sessions_revoked: number }>('POST', '/logout-all'),
  /** Re-confirm identity with a fresh authenticator code before a sensitive action. */
  stepUp: (code: string) => request<PlatformStepUp>('POST', '/step-up', { code }),
};
