import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PlatformApiError, platformApi } from './platformApi';

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
});
