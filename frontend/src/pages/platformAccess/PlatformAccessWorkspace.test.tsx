import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { GRANT_MESSAGE, PLATFORM_ORIGIN, PlatformAccessWorkspace, READY_MESSAGE } from './PlatformAccessWorkspace';

const SESSION = {
  grant_id: 'g1', organization_id: 'org-1', organization_name: 'Acme Traders', staff_name: 'Sam Support',
  scopes: ['READ_METADATA', 'READ_CUSTOMERS'], areas: ['Organization profile and team', 'Customers'],
  expires_at: new Date(Date.now() + 30 * 60_000).toISOString(), is_emergency: false, ticket_ref: 'SUP-9',
};

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

let opener: { postMessage: ReturnType<typeof vi.fn> };
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  opener = { postMessage: vi.fn() };
  Object.defineProperty(window, 'opener', { value: opener, configurable: true });
  fetchMock = vi.fn((url: string) => {
    if (url.endsWith('/platform-access/session')) return Promise.resolve(json(200, SESSION));
    if (url.includes('/customers')) return Promise.resolve(json(200, { items: [{ id: 'c1', customer_number: 'CUS-1', display_name: 'Visible Customer', email: 'a@b.c', status: 'active' }] }));
    if (url.endsWith('/platform-access/exit')) return Promise.resolve(new Response(null, { status: 204 }));
    return Promise.resolve(json(403, { error: { message: 'refused' } }));
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  Object.defineProperty(window, 'opener', { value: null, configurable: true });
});

function deliver(origin: string, source: unknown, token = 'grant-token-abc') {
  act(() => {
    window.dispatchEvent(new MessageEvent('message', { origin, source: source as MessageEventSource, data: { type: GRANT_MESSAGE, token } }));
  });
}

describe('platform access workspace (tenant app)', () => {
  it('announces readiness to the opener, pinned to the platform origin', () => {
    render(<PlatformAccessWorkspace />);
    expect(opener.postMessage).toHaveBeenCalledWith({ type: READY_MESSAGE }, PLATFORM_ORIGIN);
    expect(screen.getByText('Waiting for the platform console...')).toBeInTheDocument();
  });

  it('ignores tokens from any other origin or window', async () => {
    render(<PlatformAccessWorkspace />);
    deliver('https://evil.example', opener);
    deliver(PLATFORM_ORIGIN, window); // right origin, wrong window
    await new Promise((r) => setTimeout(r, 20));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText('Waiting for the platform console...')).toBeInTheDocument();
  });

  it('shows the banner and granted areas, uses the token only in memory, and exits', async () => {
    render(<PlatformAccessWorkspace />);
    deliver(PLATFORM_ORIGIN, opener);
    expect(await screen.findByText('Acme Traders')).toBeInTheDocument();
    const banner = screen.getByRole('status');
    expect(banner).toHaveTextContent('Platform access');
    expect(banner).toHaveTextContent('read-only: Organization profile and team, Customers');
    expect(banner).toHaveTextContent(/time left \d+:\d{2}/);
    expect(banner).toHaveTextContent('ticket SUP-9');
    expect(await screen.findByText('Visible Customer')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Invoices' })).not.toBeInTheDocument(); // not granted
    const [, init] = fetchMock.mock.calls.find(([u]) => String(u).includes('/customers'))!;
    expect(init.headers.Authorization).toBe('Bearer grant-token-abc');
    expect(init.credentials).toBe('omit');
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    fireEvent.click(screen.getByRole('button', { name: /Exit tenant/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith('/platform-access/exit') && i.method === 'POST')).toBe(true));
    expect(await screen.findByText(/You have exited the tenant/)).toBeInTheDocument();
  });

  it('ends cleanly when the server says the access is over', async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(url.endsWith('/platform-access/session') ? json(401, {}) : json(403, {})));
    render(<PlatformAccessWorkspace />);
    deliver(PLATFORM_ORIGIN, opener);
    expect(await screen.findByText(/This platform access has ended or expired/)).toBeInTheDocument();
  });

  it('refuses to run when not opened by the platform console', () => {
    Object.defineProperty(window, 'opener', { value: null, configurable: true });
    render(<PlatformAccessWorkspace />);
    expect(screen.getByText(/Open this page from the Rooman platform console/)).toBeInTheDocument();
  });
});
