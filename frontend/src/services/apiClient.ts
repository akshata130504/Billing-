import axios, {
  AxiosError,
  AxiosHeaders,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios';
import type { ApiError, AuthTokens } from '../types/api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const API_ORIGIN: string = import.meta.env.VITE_API_BASE_URL || '';
export const API_BASE_URL = `${API_ORIGIN}/api/v1`;

/** Not a credential: only remembers that this browser has a session cookie worth refreshing. */
const SESSION_HINT_KEY = 'rooman.session';
/** Legacy keys from builds that kept the tokens in localStorage; wiped on load. */
const LEGACY_TOKEN_KEYS = ['rooman.access_token', 'rooman.refresh_token'];
/** Header that puts the API in cookie mode (backend/app/api/session_cookies.py). */
export const SESSION_MODE_HEADER = 'X-Rooman-Session';

/** Dispatched on `window` when the session can no longer be recovered. */
export const LOGOUT_EVENT = 'rooman:logout';
/** Fired when the API refuses a request because the organization's access changed (trial ended,
 * module not in the plan...): the app reloads /auth/me so the lifecycle screens update. */
export const ACCESS_CHANGED_EVENT = 'rooman:access-changed';
const ACCESS_CODES = new Set(['ORGANIZATION_TRIAL_EXPIRED', 'FEATURE_NOT_ENTITLED']);

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------
//
// The access token lives in memory only (gone on reload) and the refresh token never
// reaches JavaScript at all - the API keeps it in an HttpOnly, SameSite=Strict cookie scoped to
// /api/v1/auth. A reload calls POST /auth/refresh (the browser attaches the cookie) to get a new
// access token. localStorage only holds a "there may be a session" hint, never a token.

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable (private mode / blocked): the hint is simply not kept.
  }
}

LEGACY_TOKEN_KEYS.forEach((key) => safeSet(key, null));

let accessToken: string | null = null;

export const tokenStorage = {
  getAccessToken: (): string | null => accessToken,
  /** Store a token response. Any refresh token in it is ignored (it belongs in the cookie). */
  set: (tokens: Pick<AuthTokens, 'access_token'> & { refresh_token?: string | null }): void => {
    accessToken = tokens.access_token || null;
    safeSet(SESSION_HINT_KEY, accessToken ? '1' : null);
  },
  clear: (): void => {
    accessToken = null;
    safeSet(SESSION_HINT_KEY, null);
  },
  /** True when a session may exist: an access token in memory or a session cookie from earlier. */
  hasSession: (): boolean => Boolean(accessToken) || safeGet(SESSION_HINT_KEY) === '1',
};

// ---------------------------------------------------------------------------
// Error normalisation
// ---------------------------------------------------------------------------

interface ErrorEnvelope {
  error?: Partial<ApiError>;
  detail?: unknown;
}

export function isApiError(value: unknown): value is ApiError {
  // An AxiosError also has string `code` and `message` (e.g. "ERR_BAD_REQUEST",
  // "Request failed with status code 422"), so it must be excluded explicitly.
  // Without this, toApiError returned the raw AxiosError unchanged: toasts showed
  // the axios message instead of the backend one, and fieldErrors() always came
  // back empty so inline form validation never rendered.
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { isAxiosError?: boolean }).isAxiosError !== true &&
    typeof (value as ApiError).code === 'string' &&
    typeof (value as ApiError).message === 'string'
  );
}

export function toApiError(error: unknown): ApiError {
  if (isApiError(error)) return error;

  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ErrorEnvelope>;
    const status = axiosError.response?.status;
    const envelope = axiosError.response?.data?.error;
    if (envelope && typeof envelope.message === 'string') {
      return {
        code: envelope.code ?? 'UNKNOWN_ERROR',
        message: envelope.message,
        details: envelope.details,
        status,
      };
    }
    if (axiosError.code === 'ECONNABORTED') {
      return { code: 'TIMEOUT', message: 'The server took too long to respond.', status };
    }
    if (!axiosError.response) {
      return {
        code: 'NETWORK_ERROR',
        message: 'Unable to reach the server. Check your connection and try again.',
      };
    }
    // No JSON error envelope: the reply came from the reverse proxy (nginx/Caddy), not the API -
    // typically the backend was restarting, crashed, or timed out. Say so instead of
    // "Request failed with status code 502".
    if (status === 502 || status === 503 || status === 504) {
      return {
        code: status === 504 ? 'GATEWAY_TIMEOUT' : 'SERVICE_UNAVAILABLE',
        message:
          status === 504
            ? 'The server took too long to respond. Please try again in a moment.'
            : 'The service is temporarily unavailable. Please try again in a moment.',
        status,
      };
    }
    return {
      code: `HTTP_${status}`,
      message: axiosError.message || 'An unexpected error occurred.',
      status,
    };
  }

  if (error instanceof Error) {
    return { code: 'CLIENT_ERROR', message: error.message };
  }
  return { code: 'UNKNOWN_ERROR', message: 'An unexpected error occurred.' };
}

/** Convenience: pull a field-level validation message out of an ApiError. */
export function fieldErrors(error: unknown): Record<string, string> {
  const apiError = toApiError(error);
  const fields = apiError.details?.fields;
  return fields && typeof fields === 'object' ? fields : {};
}

/**
 * One readable sentence for forms that show a single banner instead of per-field errors.
 * Request validation answers with a generic "The request contains invalid fields." and puts
 * the real reason (e.g. "Pricing tiers overlap: ...") in `details.fields`; surface that.
 */
export function errorSummary(error: unknown): string {
  const apiError = toApiError(error);
  const reasons = Object.values(fieldErrors(error))
    .filter((v): v is string => typeof v === 'string' && v.includes(' '))
    .map((v) => v.replace(/^Value error,\s*/i, '').trim());
  return reasons.length > 0 ? reasons.join(' ') : apiError.message;
}

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json', [SESSION_MODE_HEADER]: 'cookie' },
  withCredentials: true,
  timeout: 20000,
});

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

apiClient.interceptors.request.use((config) => {
  const token = tokenStorage.getAccessToken();
  if (token) {
    const headers = AxiosHeaders.from(config.headers);
    headers.set('Authorization', `Bearer ${token}`);
    config.headers = headers;
  }
  // Let the browser set the multipart boundary for FormData bodies.
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    const headers = AxiosHeaders.from(config.headers);
    headers.delete('Content-Type');
    config.headers = headers;
  }
  return config;
});

// A single in-flight refresh shared by every request that hits a 401 at once.
let refreshPromise: Promise<AuthTokens> | null = null;

/**
 * Auth endpoints that do not run on the access token (credentials, one-time codes, the
 * refresh itself) or that must not be replayed with a rotated token (logout). A 401 from
 * one of these is a real answer, never a reason to refresh.
 *
 * Every other /auth/* call (/auth/me, /auth/sessions, /auth/2fa/*, /auth/change-password,
 * /auth/switch-organization, ...) is an ordinary authenticated request: when its access token
 * has expired or been superseded (logout on another device and password changes bump
 * `tokens_valid_after`), it must refresh and retry like any other call. Treating those as
 * "auth routes" logged the user out on the next page load (/auth/me 401 -> session cleared)
 * even though their refresh token was still valid.
 */
const NO_REFRESH_AUTH_ROUTE =
  /(^|\/)auth\/(login(\/mfa)?|refresh|logout|signup(\/[^?]*)?|forgot-password|reset-password|accept-invitation|invitations\/[^/?]+)(\?|$)/;

function isAuthRoute(url: string | undefined): boolean {
  if (!url) return false;
  return NO_REFRESH_AUTH_ROUTE.test(url);
}

function refreshRequest(): Promise<AuthTokens> {
  // Plain axios (not apiClient) so this call never re-enters the interceptor. No body: the
  // refresh token is the HttpOnly session cookie.
  return axios
    .post<AuthTokens>(`${API_BASE_URL}/auth/refresh`, undefined, {
      timeout: 15000,
      withCredentials: true,
      headers: { [SESSION_MODE_HEADER]: 'cookie' },
    })
    .then((res) => {
      tokenStorage.set(res.data);
      return res.data;
    });
}

/** Exchange the session cookie for a fresh access token. One refresh at a time per tab, and across
 * tabs too where the Web Locks API exists (the cookie rotates on every refresh). */
export function performRefresh(): Promise<AuthTokens> {
  if (!refreshPromise) {
    const locks = typeof navigator !== 'undefined' ? (navigator as Navigator & { locks?: LockManager }).locks : undefined;
    const run = locks?.request ? locks.request('rooman-session-refresh', () => refreshRequest()) : refreshRequest();
    refreshPromise = Promise.resolve(run).finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

function forceLogout(): void {
  tokenStorage.clear();
  try {
    window.dispatchEvent(new CustomEvent(LOGOUT_EVENT));
  } catch {
    // no window (SSR/test) — nothing to notify
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ErrorEnvelope>) => {
    const config = error.config as RetriableConfig | undefined;
    const status = error.response?.status;

    if (status === 401 && config && !config._retried && !isAuthRoute(config.url) && tokenStorage.hasSession()) {
      config._retried = true;
      try {
        const tokens = await performRefresh();
        const headers = AxiosHeaders.from(config.headers);
        headers.set('Authorization', `Bearer ${tokens.access_token}`);
        config.headers = headers;
        return apiClient.request(config);
      } catch (refreshError) {
        forceLogout();
        return Promise.reject(toApiError(refreshError));
      }
    }

    if (status === 401 && !isAuthRoute(config?.url) && tokenStorage.hasSession()) {
      // Already retried, or no refresh token available: the session is gone.
      forceLogout();
    }

    if (status === 403 && ACCESS_CODES.has(error.response?.data?.error?.code ?? '')) {
      try {
        window.dispatchEvent(new CustomEvent(ACCESS_CHANGED_EVENT));
      } catch {
        // no window (SSR/test)
      }
    }

    return Promise.reject(toApiError(error));
  }
);

// ---------------------------------------------------------------------------
// Small helpers shared by services
// ---------------------------------------------------------------------------

export type QueryValue = string | number | boolean | null | undefined;

/** Drops undefined/null/empty-string params so the query string stays clean. */
export function cleanParams<T extends object>(params?: T): Partial<T> {
  if (!params) return {};
  const out: Partial<T> = {};
  (Object.keys(params) as (keyof T)[]).forEach((key) => {
    const value = params[key] as unknown;
    if (value !== undefined && value !== null && value !== '') out[key] = params[key];
  });
  return out;
}

/** Builds an absolute URL under the API base, e.g. absoluteUrl('/invoices/1/pdf'). */
export function absoluteUrl(path: string, query?: Record<string, QueryValue>): string {
  const cleaned = cleanParams(query ?? {}) as Record<string, QueryValue>;
  const qs = Object.entries(cleaned)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  const normalised = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalised}${qs ? `?${qs}` : ''}`;
}
