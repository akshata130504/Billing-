import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { PlatformLoginPage } from './PlatformLoginPage';
import { PlatformHomePage } from './PlatformHomePage';
import { PlatformApiError, platformApi } from './platformApi';

vi.mock('./platformApi', async () => {
  const actual = await vi.importActual<typeof import('./platformApi')>('./platformApi');
  return {
    ...actual,
    platformApi: {
      login: vi.fn(),
      verifyTwoFactor: vi.fn(),
      me: vi.fn(),
      refresh: vi.fn(),
      sessions: vi.fn(),
      revokeSession: vi.fn(),
      logout: vi.fn(),
      logoutAll: vi.fn(),
    },
  };
});

const api = platformApi as unknown as Record<keyof typeof platformApi, ReturnType<typeof vi.fn>>;

const ME = {
  staff: { id: 's1', email: 'ops@rooman.test', full_name: 'Olga Ops', role: 'platform_administrator' as const },
  session_id: 'sess-1',
  session_expires_at: '2026-10-01T10:00:00Z',
  access_expires_in: 600,
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/platform/login" element={<PlatformLoginPage />} />
        <Route path="/platform" element={<PlatformHomePage />} />
        <Route path="/login" element={<div>tenant login</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('Platform staff sign-in', () => {
  beforeEach(() => vi.clearAllMocks());

  it('asks for the authenticator code after the password and only then signs in', async () => {
    api.login.mockResolvedValue({ two_factor_required: true, challenge_token: 'chal-1', expires_in: 300 });
    api.verifyTwoFactor.mockResolvedValue(ME);
    api.me.mockResolvedValue(ME);
    api.sessions.mockResolvedValue({ sessions: [] });
    renderAt('/platform/login');

    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'ops@rooman.test' } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'Platform-Passw0rd-2026!' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    const codeInput = await screen.findByLabelText(/^Authenticator code/);
    expect(api.login).toHaveBeenCalledWith('ops@rooman.test', 'Platform-Passw0rd-2026!');
    expect(api.verifyTwoFactor).not.toHaveBeenCalled();
    fireEvent.change(codeInput, { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Verify and sign in' }));

    await waitFor(() => expect(api.verifyTwoFactor).toHaveBeenCalledWith('chal-1', '123456'));
    expect(await screen.findByText('Olga Ops')).toBeInTheDocument();
    expect(window.localStorage.length).toBe(0); // nothing about the platform session is stored in JS
  });

  it('shows the generic error for bad credentials and stays on the password step', async () => {
    api.login.mockRejectedValue(new PlatformApiError('Invalid email or password.', 401));
    renderAt('/platform/login');
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'x@rooman.test' } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'nope' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.');
    expect(screen.queryByLabelText(/^Authenticator code/)).not.toBeInTheDocument();
  });

  it('shows a wrong-code error and stays on the code step', async () => {
    api.login.mockResolvedValue({ two_factor_required: true, challenge_token: 'chal-1', expires_in: 300 });
    api.verifyTwoFactor.mockRejectedValue(new PlatformApiError('The authentication code is invalid or has already been used.', 401));
    renderAt('/platform/login');
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'ops@rooman.test' } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'pw' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.change(await screen.findByLabelText(/^Authenticator code/), { target: { value: '000000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Verify and sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('invalid or has already been used');
    expect(screen.getByLabelText(/^Authenticator code/)).toBeInTheDocument();
  });

  it('goes back to the password step when the challenge expired', async () => {
    api.login.mockResolvedValue({ two_factor_required: true, challenge_token: 'chal-1', expires_in: 300 });
    api.verifyTwoFactor.mockRejectedValue(new PlatformApiError('This sign-in attempt is invalid or has expired. Please sign in again.', 401));
    renderAt('/platform/login');
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'ops@rooman.test' } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'pw' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.change(await screen.findByLabelText(/^Authenticator code/), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Verify and sign in' }));
    expect(await screen.findByLabelText(/^Password/)).toBeInTheDocument();
  });
});

describe('Platform home', () => {
  beforeEach(() => vi.clearAllMocks());

  it('redirects to the platform login when there is no session', async () => {
    api.me.mockRejectedValue(new PlatformApiError('Platform authentication required.', 401));
    api.refresh.mockRejectedValue(new PlatformApiError('Your platform session has ended.', 401));
    renderAt('/platform');
    expect(await screen.findByText('Platform staff sign-in')).toBeInTheDocument();
  });

  it('refreshes once when the access token has expired', async () => {
    api.me.mockRejectedValue(new PlatformApiError('Platform access token has expired.', 401));
    api.refresh.mockResolvedValue(ME);
    api.sessions.mockResolvedValue({ sessions: [] });
    renderAt('/platform');
    expect(await screen.findByText('Olga Ops')).toBeInTheDocument();
    expect(api.refresh).toHaveBeenCalledTimes(1);
  });

  it('shows the Super Admin label, sessions, and signs out', async () => {
    api.me.mockResolvedValue(ME);
    api.sessions.mockResolvedValue({
      sessions: [
        { id: 'sess-1', created_at: '2026-09-30T08:00:00Z', last_used_at: '2026-09-30T08:00:00Z', expires_at: '2026-09-30T16:00:00Z', user_agent: 'This browser', ip_address: '10.0.0.1', current: true },
        { id: 'sess-2', created_at: '2026-09-29T08:00:00Z', last_used_at: '2026-09-29T08:00:00Z', expires_at: '2026-09-29T16:00:00Z', user_agent: 'Old laptop', ip_address: '10.0.0.2', current: false },
      ],
    });
    api.revokeSession.mockResolvedValue(undefined);
    api.logout.mockResolvedValue(undefined);
    renderAt('/platform');
    expect(await screen.findByText('Platform Administrator (Super Admin)')).toBeInTheDocument();
    expect(screen.getByText('This browser (this session)')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }));
    await waitFor(() => expect(api.revokeSession).toHaveBeenCalledWith('sess-2'));
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    await waitFor(() => expect(api.logout).toHaveBeenCalled());
    expect(await screen.findByText('Platform staff sign-in')).toBeInTheDocument();
  });

  it('never shows tenant login and is separate from it', async () => {
    api.me.mockRejectedValue(new PlatformApiError('Platform authentication required.', 401));
    api.refresh.mockRejectedValue(new PlatformApiError('ended', 401));
    renderAt('/platform');
    await screen.findByText('Platform staff sign-in');
    expect(screen.queryByText('tenant login')).not.toBeInTheDocument();
  });
});
