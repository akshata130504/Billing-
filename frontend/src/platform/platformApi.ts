/**
 * Platform (Rooman staff) API client - deliberately separate from the tenant apiClient.
 *
 * The platform session lives in HttpOnly cookies set by the server (the access token is never
 * visible to this code, and nothing is written to localStorage). State-changing requests echo the
 * readable CSRF cookie in the X-Platform-CSRF header (double submit). Tenant tokens are never sent.
 *
 * The console is served at /superadmin on the one application origin and always calls that same
 * origin (no configurable API origin, no cross-origin credentials); it imports nothing from the
 * tenant API client. Same origin is not shared authorization: the server accepts only the platform
 * session on platform routes and never on tenant routes.
 */
const ROOT = '/api/v1/platform';
const BASE = `${ROOT}/auth`;
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

export class PlatformApiError extends Error {
  constructor(message: string, public status: number, public code?: string, public details?: Record<string, unknown>) {
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

async function send<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') {
    const csrf = CSRF_COOKIES.map(readCookie).find((value) => value);
    if (csrf) headers[CSRF_HEADER] = csrf;
  }
  const res = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
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
    throw new PlatformApiError(message, res.status, data?.error?.code, data?.error?.details);
  }
  return data as T;
}

function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  return send<T>(method, `${BASE}${path}`, body);
}

let refreshing: Promise<unknown> | null = null;

let sessionExpiredHandler: (() => void) | null = null;

/**
 * The console registers what to do when the platform session is gone for good (the refresh was
 * refused): return to sign-in. Returns the unregister function.
 */
export function setPlatformSessionExpiredHandler(handler: () => void): () => void {
  sessionExpiredHandler = handler;
  return () => {
    if (sessionExpiredHandler === handler) sessionExpiredHandler = null;
  };
}

/** Report that the platform session has ended (sends the console to sign-in). */
export function platformSessionExpired(): void {
  sessionExpiredHandler?.();
}

function isUnauthorized(err: unknown): err is PlatformApiError {
  return err instanceof PlatformApiError && err.status === 401;
}

/**
 * The access token lives only 10 minutes, so a 401 triggers ONE shared refresh of the session
 * cookie and a single retry. If the session cannot be refreshed (or is refused again) the 401 is
 * thrown and the console is sent back to the sign-in page instead of repeating the error.
 */
async function withSessionRefresh<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (err) {
    if (!isUnauthorized(err)) throw err;
    if (!refreshing) {
      refreshing = platformApi.refresh().finally(() => {
        refreshing = null;
      });
    }
    try {
      await refreshing;
    } catch {
      platformSessionExpired();
      throw err;
    }
    try {
      return await call();
    } catch (retryErr) {
      if (isUnauthorized(retryErr)) platformSessionExpired();
      throw retryErr;
    }
  }
}

/** Console API call (`path` is relative to /api/v1/platform), see withSessionRefresh. */
export function consoleRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  return withSessionRefresh(() => send<T>(method, `${ROOT}${path}`, body));
}

export const platformApi = {
  login: (email: string, password: string) => request<PlatformMe>('POST', '/login', { email, password }),
  me: () => request<PlatformMe>('GET', '/me'),
  refresh: () => request<PlatformMe>('POST', '/refresh'),
  sessions: () => request<{ sessions: PlatformSessionInfo[] }>('GET', '/sessions'),
  revokeSession: (id: string) => request<void>('DELETE', `/sessions/${encodeURIComponent(id)}`),
  logout: () => request<void>('POST', '/logout'),
  logoutAll: () => request<{ sessions_revoked: number }>('POST', '/logout-all'),
  /** Re-confirm identity with the current password before a sensitive action. */
  // A wrong password is a 403; a 401 means the session itself has expired (see withSessionRefresh).
  stepUp: (password: string) => withSessionRefresh(() => request<PlatformStepUp>('POST', '/step-up', { password })),
};
