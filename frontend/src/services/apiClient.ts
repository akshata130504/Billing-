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

const ACCESS_TOKEN_KEY = 'rooman.access_token';
const REFRESH_TOKEN_KEY = 'rooman.refresh_token';

/** Dispatched on `window` when the session can no longer be recovered. */
export const LOGOUT_EVENT = 'rooman:logout';

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------

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
    // Storage unavailable (private mode / blocked). Session simply won't persist.
  }
}

export const tokenStorage = {
  getAccessToken: (): string | null => safeGet(ACCESS_TOKEN_KEY),
  getRefreshToken: (): string | null => safeGet(REFRESH_TOKEN_KEY),
  set: (tokens: Pick<AuthTokens, 'access_token' | 'refresh_token'>): void => {
    safeSet(ACCESS_TOKEN_KEY, tokens.access_token);
    safeSet(REFRESH_TOKEN_KEY, tokens.refresh_token);
  },
  clear: (): void => {
    safeSet(ACCESS_TOKEN_KEY, null);
    safeSet(REFRESH_TOKEN_KEY, null);
  },
  hasSession: (): boolean => Boolean(safeGet(ACCESS_TOKEN_KEY)),
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

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
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

function isAuthRoute(url: string | undefined): boolean {
  if (!url) return false;
  return /\/auth\//.test(url) || url.startsWith('auth/') || url.startsWith('/auth/');
}

function performRefresh(): Promise<AuthTokens> {
  if (!refreshPromise) {
    const refresh_token = tokenStorage.getRefreshToken();
    if (!refresh_token) {
      return Promise.reject<AuthTokens>({
        code: 'UNAUTHORIZED',
        message: 'Your session has expired. Please sign in again.',
        status: 401,
      } satisfies ApiError);
    }
    // Plain axios (not apiClient) so this call never re-enters the interceptor.
    refreshPromise = axios
      .post<AuthTokens>(`${API_BASE_URL}/auth/refresh`, { refresh_token }, { timeout: 15000 })
      .then((res) => {
        tokenStorage.set(res.data);
        return res.data;
      })
      .finally(() => {
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

    if (
      status === 401 &&
      config &&
      !config._retried &&
      !isAuthRoute(config.url) &&
      tokenStorage.getRefreshToken()
    ) {
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
