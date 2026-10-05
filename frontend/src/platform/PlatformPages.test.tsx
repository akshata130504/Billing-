import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { PlatformRoutes, SUPERADMIN_BASE } from './PlatformApp';
import superadminHtml from '../../superadmin.html?raw';
import tenantRoutesSource from '../routes/index.tsx?raw';
import { PlatformApiError, platformApi } from './platformApi';
import { consoleApi } from './consoleApi';
import { ToastProvider } from '../components/common/Toast';

vi.mock('./platformApi', async () => {
  const actual = await vi.importActual<typeof import('./platformApi')>('./platformApi');
  return {
    ...actual,
    platformApi: {
      login: vi.fn(),
      me: vi.fn(),
      refresh: vi.fn(),
      sessions: vi.fn(),
      revokeSession: vi.fn(),
      logout: vi.fn(),
      logoutAll: vi.fn(),
      stepUp: vi.fn(),
    },
  };
});

vi.mock('./consoleApi', async () => {
  const actual = await vi.importActual<typeof import('./consoleApi')>('./consoleApi');
  return { ...actual, consoleApi: { dashboard: vi.fn() } };
});

const api = platformApi as unknown as Record<keyof typeof platformApi, ReturnType<typeof vi.fn>>;
const consoleMock = consoleApi as unknown as { dashboard: ReturnType<typeof vi.fn> };

const DASHBOARD = {
  organizations: { active: 3, suspended: 1, pending_deletion: 0, deleted: 0, total: 4, jobs_paused: 1 },
  created_last_7_days: 2,
  recent_organizations: [],
  staff: { total: 2, active: 2 },
  health: { api: 'ok', database: 'connected', migrations: 'at_head', scheduler: 'ok' },
  scheduler: { enabled: true, status: 'ok', last_counts: {} },
  recent_activity: [],
};

const ME = {
  staff: { id: 's1', email: 'ops@rooman.test', full_name: 'Olga Ops', role: 'platform_administrator' as const },
  session_id: 'sess-1',
  session_expires_at: '2026-10-01T10:00:00Z',
  access_expires_in: 600,
};

function renderAt(path: string) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <PlatformRoutes />
      </MemoryRouter>
    </ToastProvider>
  );
}

describe('Platform staff sign-in', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    consoleMock.dashboard.mockResolvedValue(DASHBOARD);
  });

  it('has an Email input, a Password input and a Sign In button', () => {
    renderAt('/login');
    expect(screen.getByLabelText(/^Email/)).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText(/^Password/)).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: 'Sign In' })).toBeInTheDocument();
  });

  it('has no authenticator / one-time code input', () => {
    const { container } = renderAt('/login');
    expect(container.querySelector('[autocomplete="one-time-code"]')).toBeNull();
    expect(screen.queryByLabelText(/authenticator|code/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Continue|Verify/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole('textbox')).toHaveLength(1); // only the email field
  });

  it('signs in with email and password and opens the Super Admin dashboard', async () => {
    api.login.mockResolvedValue(ME);
    api.me.mockResolvedValue(ME);
    renderAt('/login');

    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: '  ops@rooman.test ' } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'Platform-Passw0rd-2026!' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));

    await waitFor(() => expect(api.login).toHaveBeenCalledWith('ops@rooman.test', 'Platform-Passw0rd-2026!'));
    expect(api.login).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole('heading', { name: 'Platform dashboard' })).toBeInTheDocument();
    expect(window.localStorage.length).toBe(0); // nothing about the platform session is stored in JS
  });

  it('shows the server error for bad credentials, clears the password and stays on sign-in', async () => {
    api.login.mockRejectedValue(new PlatformApiError('Invalid email or password.', 401));
    renderAt('/login');
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'x@rooman.test' } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'nope' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.');
    expect(screen.getByLabelText(/^Password/)).toHaveValue('');
    expect(screen.getByText('Platform staff sign-in')).toBeInTheDocument();
    expect(consoleMock.dashboard).not.toHaveBeenCalled();
  });

  it('shows a generic message when sign-in fails for a non-API reason', async () => {
    api.login.mockRejectedValue(new Error('boom'));
    renderAt('/login');
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'x@rooman.test' } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'pw' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Sign-in failed. Please try again.');
  });
});

describe('Platform console shell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    consoleMock.dashboard.mockResolvedValue(DASHBOARD);
  });

  it('redirects to the platform login when there is no session', async () => {
    api.me.mockRejectedValue(new PlatformApiError('Platform authentication required.', 401));
    api.refresh.mockRejectedValue(new PlatformApiError('Your platform session has ended.', 401));
    renderAt('/');
    expect(await screen.findByText('Platform staff sign-in')).toBeInTheDocument();
  });

  it('refreshes once when the access token has expired', async () => {
    api.me.mockRejectedValue(new PlatformApiError('Platform access token has expired.', 401));
    api.refresh.mockResolvedValue(ME);
    api.sessions.mockResolvedValue({ sessions: [] });
    renderAt('/');
    expect(await screen.findByText('Olga Ops')).toBeInTheDocument();
    expect(api.refresh).toHaveBeenCalledTimes(1);
  });

  it('shows the Super Admin label, own sessions on My account, and signs out', async () => {
    api.me.mockResolvedValue(ME);
    api.sessions.mockResolvedValue({
      sessions: [
        { id: 'sess-1', created_at: '2026-09-30T08:00:00Z', last_used_at: '2026-09-30T08:00:00Z', expires_at: '2026-09-30T16:00:00Z', user_agent: 'This browser', ip_address: '10.0.0.1', current: true },
        { id: 'sess-2', created_at: '2026-09-29T08:00:00Z', last_used_at: '2026-09-29T08:00:00Z', expires_at: '2026-09-29T16:00:00Z', user_agent: 'Old laptop', ip_address: '10.0.0.2', current: false },
      ],
    });
    api.revokeSession.mockResolvedValue(undefined);
    api.logout.mockResolvedValue(undefined);
    renderAt('/account');
    expect((await screen.findAllByText('Platform Administrator (Super Admin)')).length).toBeGreaterThan(0);
    expect(await screen.findByText('This browser (this session)')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }));
    await waitFor(() => expect(api.revokeSession).toHaveBeenCalledWith('sess-2'));
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    await waitFor(() => expect(api.logout).toHaveBeenCalled());
    expect(await screen.findByText('Platform staff sign-in')).toBeInTheDocument();
  });

  it('has no tenant routes: unknown paths fall back to the platform console', async () => {
    api.me.mockRejectedValue(new PlatformApiError('Platform authentication required.', 401));
    api.refresh.mockRejectedValue(new PlatformApiError('ended', 401));
    renderAt('/dashboard');
    expect(await screen.findByText('Platform staff sign-in')).toBeInTheDocument();
  });

  it('opens on the platform dashboard after sign-in', async () => {
    api.me.mockResolvedValue(ME);
    renderAt('/');
    expect(await screen.findByRole('heading', { name: 'Platform dashboard' })).toBeInTheDocument();
    expect(consoleMock.dashboard).toHaveBeenCalledTimes(1);
  });
});

/** Renders the console the way production mounts it: under /superadmin on the application origin. */
function renderSuperadmin(path: string) {
  function Where() {
    return <output data-testid="where">{SUPERADMIN_BASE + useLocation().pathname}</output>;
  }
  return render(
    <ToastProvider>
      <MemoryRouter basename={SUPERADMIN_BASE} initialEntries={[path]}>
        <PlatformRoutes />
        <Where />
      </MemoryRouter>
    </ToastProvider>
  );
}

describe('Served at /superadmin', () => {
  beforeEach(() => vi.clearAllMocks());

  it('uses /superadmin as the console base path', () => {
    expect(SUPERADMIN_BASE).toBe('/superadmin');
  });

  it('/superadmin without a platform session shows the staff sign-in, not the console', async () => {
    // e.g. a signed-in tenant user: their tenant token is no platform credential, the API says 401
    api.me.mockRejectedValue(new PlatformApiError('Platform authentication required.', 401));
    api.refresh.mockRejectedValue(new PlatformApiError('Your platform session has ended.', 401));
    renderSuperadmin('/superadmin');
    expect(await screen.findByText('Platform staff sign-in')).toBeInTheDocument();
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/superadmin\/login$/);
    expect(screen.queryByRole('heading', { name: 'Platform dashboard' })).not.toBeInTheDocument();
    expect(consoleMock.dashboard).not.toHaveBeenCalled();
  });

  it('a deep link without a session also lands on the staff sign-in', async () => {
    api.me.mockRejectedValue(new PlatformApiError('Platform authentication required.', 401));
    api.refresh.mockRejectedValue(new PlatformApiError('ended', 401));
    renderSuperadmin('/superadmin/organizations');
    expect(await screen.findByText('Platform staff sign-in')).toBeInTheDocument();
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/superadmin\/login$/);
  });

  it('email and password sign in, then the console at /superadmin', async () => {
    api.login.mockResolvedValue(ME);
    api.me.mockResolvedValue(ME);
    consoleMock.dashboard.mockResolvedValue(DASHBOARD);
    renderSuperadmin('/superadmin/login');
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/superadmin\/login$/);
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'ops@rooman.test' } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'Platform-Passw0rd-2026!' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));
    await waitFor(() => expect(api.login).toHaveBeenCalledWith('ops@rooman.test', 'Platform-Passw0rd-2026!'));
    expect(await screen.findByRole('heading', { name: 'Platform dashboard' })).toBeInTheDocument();
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/superadmin\/$/);
  });

  it('a direct link to a console page opens it under /superadmin', async () => {
    api.me.mockResolvedValue(ME);
    api.sessions.mockResolvedValue({ sessions: [] });
    renderSuperadmin('/superadmin/account');
    expect((await screen.findAllByText('Platform Administrator (Super Admin)')).length).toBeGreaterThan(0);
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/superadmin\/account$/);
  });

  it('console navigation stays under /superadmin', async () => {
    api.me.mockResolvedValue(ME);
    renderSuperadmin('/superadmin/no-such-page');
    expect(await screen.findByRole('heading', { name: 'Platform dashboard' })).toBeInTheDocument();
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/superadmin\/$/);
  });

  it('the console document loads only its own entry and no third-party resources', () => {
    expect(superadminHtml).toContain('src="/src/platform/main.tsx"');
    expect(superadminHtml).not.toMatch(/https?:\/\//);
    expect(superadminHtml).toContain('noindex');
  });
});

describe('One application, separate console', () => {
  it('the tenant app does not contain the platform console', () => {
    expect(tenantRoutesSource).not.toMatch(/platform\/Platform(Login|Home)Page/);
    // no /platform or /platform/* console route (the tenant's /platform-access grant workspace is different)
    expect(tenantRoutesSource).not.toMatch(/path="\/platform("|\/)/);
  });
});
