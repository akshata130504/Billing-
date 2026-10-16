import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const auth = vi.hoisted(() => ({ validateResetToken: vi.fn(), resetPassword: vi.fn() }));
vi.mock('../../services/authService', () => ({ authService: auth }));
vi.mock('../../components/common/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));

import { ResetPasswordPage } from './ResetPasswordPage';

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/reset-password?token=tok123']}>
      <ResetPasswordPage />
    </MemoryRouter>,
  );

// BUG-27: an invalid or used reset link showed the password form and failed only on submit.
describe('ResetPasswordPage link check', () => {
  beforeEach(() => vi.clearAllMocks());

  it('tells the user straight away that a dead link cannot be used', async () => {
    auth.validateResetToken.mockRejectedValue({ code: 'VALIDATION_ERROR', message: 'invalid', status: 422 });
    renderPage();
    expect(await screen.findByText('This reset link is no longer valid')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request a new link' })).toBeInTheDocument();
    expect(auth.validateResetToken).toHaveBeenCalledWith('tok123');
  });

  it('shows the form for a usable link', async () => {
    auth.validateResetToken.mockResolvedValue(undefined);
    renderPage();
    expect(await screen.findByText('Choose a new password')).toBeInTheDocument();
  });

  it('still shows the form when the check cannot reach the server', async () => {
    auth.validateResetToken.mockRejectedValue({ code: 'NETWORK_ERROR', message: 'offline' });
    renderPage();
    expect(await screen.findByText('Choose a new password')).toBeInTheDocument();
    expect(screen.queryByText('This reset link is no longer valid')).toBeNull();
  });
});
