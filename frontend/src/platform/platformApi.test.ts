import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PlatformApiError, consoleRequest, platformApi, setPlatformSessionExpiredHandler } from './platformApi';
import { consoleApi } from './consoleApi';

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('platformApi', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    document.cookie = 'rb_platform_csrf=csrf-value-123; path=/';
    window.localStorage.setItem('rooman.access_token', 'tenant-token-must-not-be-sent');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = 'rb_platform_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    window.localStorage.clear();
  });

  it('sends same-origin credentials, the CSRF header on writes, and never a bearer token', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await platformApi.logout();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/platform/auth/logout'); // always same-origin, never a configured API host
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('same-origin');
    expect(init.headers['X-Platform-CSRF']).toBe('csrf-value-123');
    expect(init.headers.Authorization).toBeUndefined();
  });

  it('does not send the CSRF header on reads', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { sessions: [] }));
    await platformApi.sessions();
    expect(fetchMock.mock.calls[0][1].headers['X-Platform-CSRF']).toBeUndefined();
  });

  it('surfaces the server error message and status', async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, { error: { code: 'UNAUTHORIZED', message: 'Invalid email or password.' } }));
    await expect(platformApi.login('a@rooman.test', 'x')).rejects.toMatchObject({
      message: 'Invalid email or password.',
      status: 401,
      code: 'UNAUTHORIZED',
    });
    await expect(platformApi.login('a@rooman.test', 'x')).rejects.toBeInstanceOf(PlatformApiError);
  });

  it('reads the __Host- prefixed CSRF cookie used with secure cookies', async () => {
    // jsdom (http) cannot store __Host- cookies, so present the browser's cookie string directly.
    vi.spyOn(document, 'cookie', 'get').mockReturnValue('__Host-rb_platform_csrf=host-prefixed-456');
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await platformApi.logoutAll();
    expect(fetchMock.mock.calls[0][1].headers['X-Platform-CSRF']).toBe('host-prefixed-456');
  });

  it('login posts email and password to /login and returns the signed-in staff', async () => {
    const me = { staff: { id: 's1', email: 'ops@rooman.test', full_name: 'Olga Ops', role: 'platform_administrator' }, session_id: 'sess-1', session_expires_at: 'x', access_expires_in: 600 };
    fetchMock.mockResolvedValue(jsonResponse(200, me));
    const result = await platformApi.login('ops@rooman.test', 'Platform-Passw0rd-2026!');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/platform/auth/login');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ email: 'ops@rooman.test', password: 'Platform-Passw0rd-2026!' });
    expect(result).toEqual(me);
    expect(fetchMock).toHaveBeenCalledTimes(1); // no second (2FA) request
  });

  it('has no two-factor sign-in call', () => {
    expect((platformApi as Record<string, unknown>).verifyTwoFactor).toBeUndefined();
  });

  it('step-up posts only the password, with the CSRF header', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { step_up_expires_at: '2026-09-30T10:15:00Z', expires_in: 900 }));
    const result = await platformApi.stepUp('Platform-Passw0rd-2026!');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/platform/auth/step-up');
    expect(JSON.parse(init.body)).toEqual({ password: 'Platform-Passw0rd-2026!' });
    expect(init.headers['X-Platform-CSRF']).toBe('csrf-value-123');
    expect(result.expires_in).toBe(900);
  });

  it('console calls refresh an expired access token once and retry once', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: 'UNAUTHORIZED', message: 'Platform access token has expired.' } }))
      .mockResolvedValueOnce(jsonResponse(200, { staff: {} })) // /auth/refresh
      .mockResolvedValueOnce(jsonResponse(200, { items: [] }));
    await expect(consoleApi.staff()).resolves.toEqual({ items: [] });
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([
      '/api/v1/platform/staff', '/api/v1/platform/auth/refresh', '/api/v1/platform/staff',
    ]);
  });

  it('console calls give up when the refresh fails (no loop)', async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, { error: { code: 'UNAUTHORIZED', message: 'Your platform session has ended.' } }));
    await expect(consoleRequest('GET', '/dashboard')).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('console writes send CSRF, query strings are encoded, and 403 step-up errors pass through', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(403, { error: { code: 'STEP_UP_REQUIRED', message: 'Confirm it is you.' } }));
    await expect(consoleApi.lifecycle('org/1', 'suspend', { reason: 'x'.repeat(12), ticket_ref: 'T-1' })).rejects.toMatchObject({
      status: 403, code: 'STEP_UP_REQUIRED',
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/platform/organizations/org%2F1/suspend');
    expect(init.headers['X-Platform-CSRF']).toBe('csrf-value-123');
    expect(init.credentials).toBe('same-origin');
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, page: 1, page_size: 25, total_pages: 0 }));
    await consoleApi.organizations({ q: 'a&b', status: '', page: 2 });
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/platform/organizations?q=a%26b&page=2');
  });

  it('step-up on an expired session refreshes once, then reports the session as expired (BUG-38)', async () => {
    const expired = vi.fn();
    const unregister = setPlatformSessionExpiredHandler(expired);
    fetchMock.mockResolvedValue(jsonResponse(401, { error: { code: 'UNAUTHORIZED', message: 'Platform authentication required.' } }));
    await expect(platformApi.stepUp('pw')).rejects.toMatchObject({ status: 401 });
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(['/api/v1/platform/auth/step-up', '/api/v1/platform/auth/refresh']);
    expect(expired).toHaveBeenCalledTimes(1);
    unregister();
  });

  it('step-up retries after a successful refresh of an idle access token', async () => {
    const expired = vi.fn();
    const unregister = setPlatformSessionExpiredHandler(expired);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: 'UNAUTHORIZED', message: 'Platform access token has expired.' } }))
      .mockResolvedValueOnce(jsonResponse(200, { staff: {} }))
      .mockResolvedValueOnce(jsonResponse(200, { step_up_expires_at: '2026-10-10T00:15:00Z', expires_in: 900 }));
    await expect(platformApi.stepUp('pw')).resolves.toMatchObject({ expires_in: 900 });
    expect(expired).not.toHaveBeenCalled();
    unregister();
  });

  it('a wrong step-up password (403) is shown as is, without refresh or sign-out', async () => {
    const expired = vi.fn();
    const unregister = setPlatformSessionExpiredHandler(expired);
    fetchMock.mockResolvedValueOnce(jsonResponse(403, { error: { code: 'STEP_UP_FAILED', message: 'Incorrect password.' } }));
    await expect(platformApi.stepUp('bad')).rejects.toMatchObject({ status: 403 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(expired).not.toHaveBeenCalled();
    unregister();
  });

  it('console calls report the expired session when the refresh fails', async () => {
    const expired = vi.fn();
    const unregister = setPlatformSessionExpiredHandler(expired);
    fetchMock.mockResolvedValue(jsonResponse(401, { error: { code: 'UNAUTHORIZED', message: 'Your platform session has ended.' } }));
    await expect(consoleRequest('GET', '/dashboard')).rejects.toMatchObject({ status: 401 });
    expect(expired).toHaveBeenCalledTimes(1);
    unregister();
  });
});
