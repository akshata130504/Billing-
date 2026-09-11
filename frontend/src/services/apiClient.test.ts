import { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ApiError } from '../types/api';
import {
  API_BASE_URL,
  LOGOUT_EVENT,
  absoluteUrl,
  apiClient,
  cleanParams,
  fieldErrors,
  isApiError,
  toApiError,
  tokenStorage,
} from './apiClient';

const ACCESS_KEY = 'rooman.access_token';
const REFRESH_KEY = 'rooman.refresh_token';

function axiosErrorWithResponse(
  status: number,
  data: unknown,
  message = 'Request failed',
  code: string | undefined = `HTTP_${status}`
): AxiosError {
  const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
  const response = {
    data,
    status,
    statusText: '',
    headers: {},
    config,
  } as AxiosResponse;
  return new AxiosError(message, code, config, {}, response);
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------

describe('tokenStorage', () => {
  it('stores both tokens under the namespaced keys', () => {
    tokenStorage.set({ access_token: 'acc-1', refresh_token: 'ref-1' });
    expect(window.localStorage.getItem(ACCESS_KEY)).toBe('acc-1');
    expect(window.localStorage.getItem(REFRESH_KEY)).toBe('ref-1');
    expect(tokenStorage.getAccessToken()).toBe('acc-1');
    expect(tokenStorage.getRefreshToken()).toBe('ref-1');
  });

  it('reports no session before login and a session after', () => {
    expect(tokenStorage.hasSession()).toBe(false);
    expect(tokenStorage.getAccessToken()).toBeNull();
    tokenStorage.set({ access_token: 'acc-1', refresh_token: 'ref-1' });
    expect(tokenStorage.hasSession()).toBe(true);
  });

  it('clear() removes both tokens (no stale credentials after logout)', () => {
    tokenStorage.set({ access_token: 'acc-1', refresh_token: 'ref-1' });
    tokenStorage.clear();
    expect(window.localStorage.getItem(ACCESS_KEY)).toBeNull();
    expect(window.localStorage.getItem(REFRESH_KEY)).toBeNull();
    expect(tokenStorage.hasSession()).toBe(false);
  });

  it('overwrites the previous session on re-login', () => {
    tokenStorage.set({ access_token: 'acc-1', refresh_token: 'ref-1' });
    tokenStorage.set({ access_token: 'acc-2', refresh_token: 'ref-2' });
    expect(tokenStorage.getAccessToken()).toBe('acc-2');
    expect(tokenStorage.getRefreshToken()).toBe('ref-2');
  });

  it('degrades gracefully when localStorage reads throw (private mode)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(tokenStorage.getAccessToken()).toBeNull();
    expect(tokenStorage.hasSession()).toBe(false);
  });

  it('degrades gracefully when localStorage writes throw', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota');
    });
    expect(() => tokenStorage.set({ access_token: 'a', refresh_token: 'b' })).not.toThrow();
  });
});

// ---------------------------------------------------------------------------

describe('isApiError', () => {
  it('recognises the {code, message} envelope', () => {
    expect(isApiError({ code: 'X', message: 'y' })).toBe(true);
  });

  it('rejects anything else', () => {
    expect(isApiError(null)).toBe(false);
    expect(isApiError(undefined)).toBe(false);
    expect(isApiError('boom')).toBe(false);
    expect(isApiError({ message: 'no code' })).toBe(false);
    expect(isApiError({ code: 'X' })).toBe(false);
    expect(isApiError({ code: 1, message: 'y' })).toBe(false);
  });
});

/**
 * BUG (high impact): `isApiError` only checks that `code` and `message` are
 * strings — and every AxiosError has both (`code` is 'ERR_BAD_REQUEST',
 * 'ERR_NETWORK', 'ECONNABORTED', …). `toApiError` therefore returns the raw
 * AxiosError from its first line and NEVER reaches the normalisation below.
 * Consequences in production:
 *   - toasts show "Request failed with status code 422" instead of the
 *     backend's human message;
 *   - `fieldErrors()` always returns {} so inline form validation never shows;
 *   - timeout/offline errors are not translated to friendly copy.
 * Fix: make isApiError reject values where `isAxiosError === true` (or check
 * for a plain object / an explicit brand).
 * See src/services/apiClient.ts:66-73 (isApiError) and :75-76 (toApiError).
 */
describe('toApiError', () => {
  it('passes an already-normalised ApiError straight through', () => {
    const err: ApiError = { code: 'VALIDATION_ERROR', message: 'Bad input', status: 422 };
    expect(toApiError(err)).toBe(err);
  });

  it('normalises a plain Error', () => {
    expect(toApiError(new TypeError('x is not a function'))).toEqual({
      code: 'CLIENT_ERROR',
      message: 'x is not a function',
    });
  });

  it('normalises anything else to a safe generic error', () => {
    expect(toApiError('boom')).toEqual({
      code: 'UNKNOWN_ERROR',
      message: 'An unexpected error occurred.',
    });
    expect(toApiError(undefined).code).toBe('UNKNOWN_ERROR');
  });

  it('should unwrap the backend { error: {...} } envelope and keep the status', () => {
    const err = axiosErrorWithResponse(
      422,
      {
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Amount must be greater than zero.',
          details: { fields: { amount: 'must be > 0' } },
        },
      },
      'Request failed with status code 422',
      'ERR_BAD_REQUEST'
    );
    expect(toApiError(err)).toEqual({
      code: 'VALIDATION_ERROR',
      message: 'Amount must be greater than zero.',
      details: { fields: { amount: 'must be > 0' } },
      status: 422,
    });
  });


  it('should fall back to HTTP_<status> when there is no usable envelope', () => {
    const err = axiosErrorWithResponse(
      500,
      { detail: 'Internal Server Error' },
      'Request failed with status code 500',
      'ERR_BAD_RESPONSE'
    );
    expect(toApiError(err).code).toBe('HTTP_500');
  });

  it('should map a client timeout to a human message', () => {
    const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
    const err = new AxiosError('timeout of 20000ms exceeded', 'ECONNABORTED', config);
    expect(toApiError(err)).toMatchObject({
      code: 'TIMEOUT',
      message: 'The server took too long to respond.',
    });
  });

  it('should map a missing response to a network error', () => {
    const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
    const err = new AxiosError('Network Error', 'ERR_NETWORK', config);
    expect(toApiError(err)).toMatchObject({
      code: 'NETWORK_ERROR',
      message: 'Unable to reach the server. Check your connection and try again.',
    });
  });

  it('does normalise an AxiosError that carries no code (the only path that works)', () => {
    const err = axiosErrorWithResponse(
      503,
      { error: { code: 'MAINTENANCE', message: 'Down for maintenance' } },
      'Request failed with status code 503',
      '' // no axios error code, so isApiError does not short-circuit
    );
    expect(toApiError(err)).toMatchObject({ code: 'MAINTENANCE', message: 'Down for maintenance' });
  });

  it('always returns something with a string message the UI can toast', () => {
    for (const input of [undefined, null, 'x', 42, new Error('nope')]) {
      expect(typeof toApiError(input).message).toBe('string');
      expect(toApiError(input).message.length).toBeGreaterThan(0);
    }
  });
});

describe('fieldErrors', () => {
  it('extracts per-field validation messages from a normalised ApiError', () => {
    const err: ApiError = {
      code: 'VALIDATION_ERROR',
      message: 'Invalid',
      details: { fields: { amount: 'must be > 0', customer_id: 'required' } },
    };
    expect(fieldErrors(err)).toEqual({ amount: 'must be > 0', customer_id: 'required' });
  });

  it('returns an empty map when there are no field errors', () => {
    expect(fieldErrors(new Error('boom'))).toEqual({});
    expect(fieldErrors(null)).toEqual({});
    expect(fieldErrors({ code: 'X', message: 'y', details: {} })).toEqual({});
  });

  // Same root cause as above: the AxiosError is returned verbatim, so
  // `details.fields` is undefined and no inline form errors are ever shown.
  it('should extract field errors from a 422 axios response', () => {
    const err = axiosErrorWithResponse(
      422,
      {
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Invalid',
          details: { fields: { amount: 'must be > 0' } },
        },
      },
      'Request failed with status code 422',
      'ERR_BAD_REQUEST'
    );
    expect(fieldErrors(err)).toEqual({ amount: 'must be > 0' });
  });
});

// ---------------------------------------------------------------------------

describe('cleanParams', () => {
  it('drops undefined, null and empty-string params', () => {
    expect(cleanParams({ a: 1, b: undefined, c: null, d: '', e: 'x' })).toEqual({ a: 1, e: 'x' });
  });

  it('keeps falsy-but-meaningful values (0 and false)', () => {
    expect(cleanParams({ page: 0, unpaid_only: false })).toEqual({ page: 0, unpaid_only: false });
  });

  it('returns an empty object for undefined input', () => {
    expect(cleanParams(undefined)).toEqual({});
    expect(cleanParams({})).toEqual({});
  });

  it('does not mutate the caller\'s object', () => {
    const input = { a: 1, b: '' };
    cleanParams(input);
    expect(input).toEqual({ a: 1, b: '' });
  });

  it('keeps a whitespace-only string (callers must trim their own filters)', () => {
    expect(cleanParams({ q: ' ' })).toEqual({ q: ' ' });
  });
});

describe('absoluteUrl', () => {
  it('builds a URL under the API base', () => {
    expect(absoluteUrl('/invoices/1/pdf')).toBe(`${API_BASE_URL}/invoices/1/pdf`);
  });

  it('adds the missing leading slash', () => {
    expect(absoluteUrl('invoices/1/pdf')).toBe(`${API_BASE_URL}/invoices/1/pdf`);
  });

  it('appends a query string, skipping empty params', () => {
    expect(absoluteUrl('/reports/aging', { format: 'csv', status: '', page: undefined })).toBe(
      `${API_BASE_URL}/reports/aging?format=csv`
    );
  });

  it('omits the "?" when every param was dropped', () => {
    expect(absoluteUrl('/reports/aging', { status: '', page: null })).toBe(
      `${API_BASE_URL}/reports/aging`
    );
    expect(absoluteUrl('/reports/aging', {})).toBe(`${API_BASE_URL}/reports/aging`);
  });

  it('percent-encodes keys and values', () => {
    expect(absoluteUrl('/customers', { q: 'Acme & Co', 'a b': 'c/d' })).toBe(
      `${API_BASE_URL}/customers?q=Acme%20%26%20Co&a%20b=c%2Fd`
    );
  });

  it('stringifies numeric and boolean params', () => {
    expect(absoluteUrl('/invoices', { page: 2, unpaid: false })).toBe(
      `${API_BASE_URL}/invoices?page=2&unpaid=false`
    );
  });

  it('is rooted at /api/v1', () => {
    expect(API_BASE_URL.endsWith('/api/v1')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Interceptors, exercised through a stub adapter (no network).
// ---------------------------------------------------------------------------

describe('apiClient interceptors', () => {
  const originalAdapter = apiClient.defaults.adapter;

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter;
  });

  it('attaches the bearer token to every request', async () => {
    tokenStorage.set({ access_token: 'acc-1', refresh_token: 'ref-1' });
    let seen: InternalAxiosRequestConfig | undefined;
    apiClient.defaults.adapter = async (config) => {
      seen = config;
      return { data: { ok: true }, status: 200, statusText: 'OK', headers: {}, config };
    };

    await apiClient.get('/customers');
    expect(AxiosHeaders.from(seen!.headers).get('Authorization')).toBe('Bearer acc-1');
  });

  it('sends no Authorization header when signed out', async () => {
    let seen: InternalAxiosRequestConfig | undefined;
    apiClient.defaults.adapter = async (config) => {
      seen = config;
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config };
    };

    await apiClient.get('/health');
    expect(AxiosHeaders.from(seen!.headers).get('Authorization')).toBeUndefined();
  });

  it('drops the JSON Content-Type for FormData uploads so a multipart boundary can be set', async () => {
    let seen: InternalAxiosRequestConfig | undefined;
    apiClient.defaults.adapter = async (config) => {
      seen = config;
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config };
    };

    const body = new FormData();
    body.append('file', new Blob(['a,b\n1,2']), 'import.csv');
    await apiClient.post('/imports', body);
    expect(AxiosHeaders.from(seen!.headers).get('Content-Type')).not.toBe('application/json');
  });

  // Same isApiError defect as above: the rejection value is the AxiosError, so
  // callers doing `showToast('error', err.message)` show axios' generic string.
  it('should reject with a normalised ApiError instead of a raw AxiosError', async () => {
    apiClient.defaults.adapter = async (config) =>
      Promise.reject(
        new AxiosError('Request failed with status code 422', 'ERR_BAD_REQUEST', config, {}, {
          data: { error: { code: 'VALIDATION_ERROR', message: 'Amount must be > 0' } },
          status: 422,
          statusText: '',
          headers: {},
          config,
        } as AxiosResponse)
      );

    await expect(apiClient.post('/payments', {})).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
      message: 'Amount must be > 0',
    });
  });

  it('force-logs-out on a 401 when there is no refresh token', async () => {
    window.localStorage.setItem(ACCESS_KEY, 'acc-1');
    const onLogout = vi.fn();
    window.addEventListener(LOGOUT_EVENT, onLogout);

    apiClient.defaults.adapter = async (config) =>
      Promise.reject(
        new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, {}, {
          data: {},
          status: 401,
          statusText: '',
          headers: {},
          config,
        } as AxiosResponse)
      );

    await expect(apiClient.get('/customers')).rejects.toMatchObject({ status: 401 });
    window.removeEventListener(LOGOUT_EVENT, onLogout);

    expect(onLogout).toHaveBeenCalledTimes(1);
    expect(tokenStorage.hasSession()).toBe(false);
    expect(window.localStorage.getItem(REFRESH_KEY)).toBeNull();
  });

  it('does not log out on a 401 from an auth route (bad credentials)', async () => {
    window.localStorage.setItem(ACCESS_KEY, 'acc-1');
    const onLogout = vi.fn();
    window.addEventListener(LOGOUT_EVENT, onLogout);

    apiClient.defaults.adapter = async (config) =>
      Promise.reject(
        new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, {}, {
          data: { error: { code: 'INVALID_CREDENTIALS', message: 'Wrong password' } },
          status: 401,
          statusText: '',
          headers: {},
          config,
        } as AxiosResponse)
      );

    await expect(apiClient.post('/auth/login', {})).rejects.toMatchObject({ status: 401 });
    window.removeEventListener(LOGOUT_EVENT, onLogout);

    expect(onLogout).not.toHaveBeenCalled();
    expect(tokenStorage.getAccessToken()).toBe('acc-1');
  });

  it('does not log out on a non-401 error', async () => {
    window.localStorage.setItem(ACCESS_KEY, 'acc-1');
    apiClient.defaults.adapter = async (config) =>
      Promise.reject(
        new AxiosError('Server error', 'ERR_BAD_RESPONSE', config, {}, {
          data: {},
          status: 500,
          statusText: '',
          headers: {},
          config,
        } as AxiosResponse)
      );

    await expect(apiClient.get('/customers')).rejects.toMatchObject({ status: 500 });
    expect(tokenStorage.getAccessToken()).toBe('acc-1');
  });
});
