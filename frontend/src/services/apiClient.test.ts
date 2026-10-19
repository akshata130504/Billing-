import axios, { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ApiError } from '../types/api';
import {
  API_BASE_URL,
  LOGOUT_EVENT,
  absoluteUrl,
  apiClient,
  cleanParams,
  errorSummary,
  fieldErrors,
  isApiError,
  toApiError,
  tokenStorage,
} from './apiClient';

const HINT_KEY = 'rooman.session';
const LEGACY_ACCESS_KEY = 'rooman.access_token';
const LEGACY_REFRESH_KEY = 'rooman.refresh_token';

const unauthorized = (config: InternalAxiosRequestConfig) =>
  Promise.reject(
    new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, {}, {
      data: {}, status: 401, statusText: '', headers: {}, config,
    } as AxiosResponse)
  );
const ok = (config: InternalAxiosRequestConfig) =>
  ({ data: { ok: true }, status: 200, statusText: 'OK', headers: {}, config }) as AxiosResponse;
const bearer = (config: InternalAxiosRequestConfig) =>
  AxiosHeaders.from(config.headers).get('Authorization') as string | undefined;

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
  beforeEach(() => tokenStorage.clear());

  it('keeps the access token in memory only and never stores a refresh token', () => {
    tokenStorage.set({ access_token: 'acc-1', refresh_token: 'ref-1' });
    expect(tokenStorage.getAccessToken()).toBe('acc-1');
    const stored = Object.keys(window.localStorage).map((k) => window.localStorage.getItem(k));
    expect(stored).not.toContain('acc-1');
    expect(stored).not.toContain('ref-1');
    expect(window.localStorage.getItem(HINT_KEY)).toBe('1');
  });

  it('reports no session before login and a session after', () => {
    expect(tokenStorage.hasSession()).toBe(false);
    expect(tokenStorage.getAccessToken()).toBeNull();
    tokenStorage.set({ access_token: 'acc-1' });
    expect(tokenStorage.hasSession()).toBe(true);
  });

  it('a reload (hint only, no token in memory) still counts as a session to refresh', () => {
    window.localStorage.setItem(HINT_KEY, '1');
    expect(tokenStorage.getAccessToken()).toBeNull();
    expect(tokenStorage.hasSession()).toBe(true);
  });

  it('clear() forgets the token and the hint', () => {
    tokenStorage.set({ access_token: 'acc-1' });
    tokenStorage.clear();
    expect(tokenStorage.getAccessToken()).toBeNull();
    expect(window.localStorage.getItem(HINT_KEY)).toBeNull();
    expect(tokenStorage.hasSession()).toBe(false);
  });

  it('overwrites the previous session on re-login', () => {
    tokenStorage.set({ access_token: 'acc-1' });
    tokenStorage.set({ access_token: 'acc-2' });
    expect(tokenStorage.getAccessToken()).toBe('acc-2');
  });

  it('degrades gracefully when localStorage throws (private mode)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota');
    });
    expect(() => tokenStorage.set({ access_token: 'a' })).not.toThrow();
    expect(tokenStorage.getAccessToken()).toBe('a');
  });

  it('wipes tokens left in localStorage by older builds when the app loads', async () => {
    window.localStorage.setItem(LEGACY_ACCESS_KEY, 'old-access');
    window.localStorage.setItem(LEGACY_REFRESH_KEY, 'old-refresh');
    vi.resetModules();
    const fresh = await import('./apiClient');
    expect(window.localStorage.getItem(LEGACY_ACCESS_KEY)).toBeNull();
    expect(window.localStorage.getItem(LEGACY_REFRESH_KEY)).toBeNull();
    expect(fresh.tokenStorage.getAccessToken()).toBeNull();
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

// Regression (browser QA): overlapping / inverted pricing tiers only showed
// "The request contains invalid fields." in the offering and plan modals.
describe('errorSummary', () => {
  it('surfaces the request-validation reason instead of the generic message', () => {
    const err: ApiError = {
      code: 'VALIDATION_ERROR',
      message: 'The request contains invalid fields.',
      details: {
        fields: {
          pricing_tiers:
            "Value error, Pricing tiers overlap: a tier starting at 5 begins at or before the previous tier's max_qty (10).",
        },
      },
    };
    expect(errorSummary(err)).toBe(
      "Pricing tiers overlap: a tier starting at 5 begins at or before the previous tier's max_qty (10)."
    );
  });

  it('falls back to the message when there are no sentence-style field errors', () => {
    expect(errorSummary({ code: 'CONFLICT', message: 'Plan code already exists.' })).toBe('Plan code already exists.');
    expect(
      errorSummary({ code: 'CONFLICT', message: 'Duplicate SKU.', details: { fields: { sku: 'duplicate' } } })
    ).toBe('Duplicate SKU.');
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

  beforeEach(() => tokenStorage.clear());

  it('force-logs-out on a 401 when the session cookie can no longer be refreshed', async () => {
    tokenStorage.set({ access_token: 'acc-1' });
    vi.spyOn(axios, 'post').mockRejectedValue(axiosErrorWithResponse(401, {}));
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
  });

  it('does not log out on a 401 from an auth route (bad credentials)', async () => {
    tokenStorage.set({ access_token: 'acc-1' });
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

  // Regression (browser QA): /auth/me, /auth/sessions, /auth/2fa/* are authenticated calls.
  // Signing out on another device or changing the password supersedes the access token; the
  // next page load's /auth/me used to 401 without a refresh, which logged the user out.
  it.each(['/auth/me', '/auth/sessions', '/auth/2fa/setup'])(
    'refreshes and retries a 401 from the authenticated auth endpoint %s',
    async (url) => {
      tokenStorage.set({ access_token: 'acc-old', refresh_token: 'ref-old' });
      const refreshSpy = vi.spyOn(axios, 'post').mockResolvedValue({
        data: { access_token: 'acc-new', refresh_token: 'ref-new' },
      });
      const seenAuth: (string | undefined)[] = [];
      apiClient.defaults.adapter = async (config) => {
        const auth = AxiosHeaders.from(config.headers).get('Authorization') as string | undefined;
        seenAuth.push(auth);
        if (auth === 'Bearer acc-old') {
          return Promise.reject(
            new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, {}, {
              data: { error: { code: 'UNAUTHORIZED', message: 'Access token has been revoked.' } },
              status: 401,
              statusText: '',
              headers: {},
              config,
            } as AxiosResponse)
          );
        }
        return { data: { ok: true }, status: 200, statusText: 'OK', headers: {}, config };
      };

      await expect(apiClient.get(url)).resolves.toMatchObject({ data: { ok: true } });
      expect(refreshSpy).toHaveBeenCalledTimes(1);
      expect(seenAuth).toEqual(['Bearer acc-old', 'Bearer acc-new']);
      expect(tokenStorage.getAccessToken()).toBe('acc-new');
    }
  );

  it('refreshes from the cookie (no token in the body, session header set)', async () => {
    tokenStorage.set({ access_token: 'acc-old' });
    const refreshSpy = vi.spyOn(axios, 'post').mockResolvedValue({ data: { access_token: 'acc-new' } });
    apiClient.defaults.adapter = async (config) => {
      if (AxiosHeaders.from(config.headers).get('Authorization') === 'Bearer acc-old') {
        return Promise.reject(
          new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, {}, {
            data: {}, status: 401, statusText: '', headers: {}, config,
          } as AxiosResponse)
        );
      }
      return { data: null, status: 204, statusText: 'No Content', headers: {}, config };
    };

    await apiClient.post('/auth/change-password', { current_password: 'a', new_password: 'b' });
    expect(refreshSpy).toHaveBeenCalledTimes(1);
    const [url, body, options] = refreshSpy.mock.calls[0];
    expect(url).toMatch(/\/auth\/refresh$/);
    expect(body).toBeUndefined();
    expect(options).toMatchObject({ withCredentials: true, headers: { 'X-Rooman-Session': 'cookie' } });
    expect(tokenStorage.getAccessToken()).toBe('acc-new');
  });

  it('after a reload (no access token in memory) gets one from the cookie and retries', async () => {
    tokenStorage.clear();
    window.localStorage.setItem(HINT_KEY, '1');
    const refreshSpy = vi.spyOn(axios, 'post').mockResolvedValue({ data: { access_token: 'acc-new' } });
    const seen: (string | undefined)[] = [];
    apiClient.defaults.adapter = async (config) => {
      seen.push(bearer(config));
      return bearer(config) === 'Bearer acc-new' ? ok(config) : unauthorized(config);
    };

    await expect(apiClient.get('/auth/me')).resolves.toMatchObject({ data: { ok: true } });
    expect(refreshSpy).toHaveBeenCalledTimes(1);
    expect(seen).toEqual([undefined, 'Bearer acc-new']);
  });

  it('does not loop when the retried request is refused again: one refresh, then sign-out', async () => {
    tokenStorage.set({ access_token: 'acc-old' });
    const refreshSpy = vi.spyOn(axios, 'post').mockResolvedValue({ data: { access_token: 'acc-new' } });
    const onLogout = vi.fn();
    window.addEventListener(LOGOUT_EVENT, onLogout);
    let calls = 0;
    apiClient.defaults.adapter = async (config) => {
      calls += 1;
      return unauthorized(config);
    };

    await expect(apiClient.get('/customers')).rejects.toMatchObject({ status: 401 });
    window.removeEventListener(LOGOUT_EVENT, onLogout);
    expect(refreshSpy).toHaveBeenCalledTimes(1);
    expect(calls).toBe(2);
    expect(onLogout).toHaveBeenCalledTimes(1);
    expect(tokenStorage.hasSession()).toBe(false);
  });

  it('shares one refresh between concurrent 401s (the cookie rotates on every refresh)', async () => {
    tokenStorage.set({ access_token: 'acc-old' });
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const refreshSpy = vi
      .spyOn(axios, 'post')
      .mockImplementation(() => gate.then(() => ({ data: { access_token: 'acc-new' } })));
    apiClient.defaults.adapter = async (config) =>
      bearer(config) === 'Bearer acc-new' ? ok(config) : unauthorized(config);

    const both = Promise.all([apiClient.get('/customers'), apiClient.get('/invoices')]);
    await new Promise((resolve) => setTimeout(resolve, 0));
    release();
    await expect(both).resolves.toHaveLength(2);
    expect(refreshSpy).toHaveBeenCalledTimes(1);
  });

  it('sends the cookie-mode header on every API call', async () => {
    let seen: InternalAxiosRequestConfig | undefined;
    apiClient.defaults.adapter = async (config) => {
      seen = config;
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config };
    };
    await apiClient.get('/health');
    expect(AxiosHeaders.from(seen!.headers).get('X-Rooman-Session')).toBe('cookie');
    expect(seen!.withCredentials).toBe(true);
  });

  it.each(['/auth/login', '/auth/login/mfa', '/auth/logout', '/auth/signup/verify-otp', '/auth/reset-password'])(
    'never refreshes on a 401 from %s',
    async (url) => {
      tokenStorage.set({ access_token: 'acc-1', refresh_token: 'ref-1' });
      const refreshSpy = vi.spyOn(axios, 'post');
      apiClient.defaults.adapter = async (config) =>
        Promise.reject(
          new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, {}, {
            data: {}, status: 401, statusText: '', headers: {}, config,
          } as AxiosResponse)
        );
      await expect(apiClient.post(url, {})).rejects.toMatchObject({ status: 401 });
      expect(refreshSpy).not.toHaveBeenCalled();
      expect(tokenStorage.getAccessToken()).toBe('acc-1');
    }
  );

  it('does not log out on a non-401 error', async () => {
    tokenStorage.set({ access_token: 'acc-1' });
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


describe('toApiError: proxy errors without a JSON envelope', () => {
  it('turns an nginx 502 HTML page into a readable message instead of "Request failed with status code 502"', () => {
    const err = toApiError(axiosErrorWithResponse(502, '<html>502 Bad Gateway</html>', 'Request failed with status code 502'));
    expect(err.status).toBe(502);
    expect(err.code).toBe('SERVICE_UNAVAILABLE');
    expect(err.message).not.toContain('status code');
    expect(err.message).toMatch(/temporarily unavailable/i);
  });

  it('maps 504 to a timeout message', () => {
    const err = toApiError(axiosErrorWithResponse(504, '', 'Request failed with status code 504'));
    expect(err.code).toBe('GATEWAY_TIMEOUT');
    expect(err.message).toMatch(/too long/i);
  });

  it('still prefers the backend envelope message (e.g. the signup 503 EMAIL_DELIVERY_FAILED)', () => {
    const err = toApiError(
      axiosErrorWithResponse(503, {
        error: { code: 'EMAIL_DELIVERY_FAILED', message: "We couldn't reach the email server to send your verification code.", details: { reason: 'unreachable' } },
      })
    );
    expect(err.code).toBe('EMAIL_DELIVERY_FAILED');
    expect(err.message).toContain('verification code');
  });
});
