import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const auth = vi.hoisted(() => ({ getInvitation: vi.fn() }));
vi.mock('../../services/authService', () => ({ authService: auth }));
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ applyTokens: vi.fn(), logout: vi.fn(), isAuthenticated: false }) }));
vi.mock('../../components/common/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));

import { AcceptInvitationPage } from './AcceptInvitationPage';

const INVITATION = {
  email: 'ravi@example.test', organization_name: 'Acme', role: 'admin', invited_by: 'Platform',
  expires_at: '2026-10-30T00:00:00Z', user_exists: false,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/accept-invitation?token=tok123']}>
        <AcceptInvitationPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// BUG-37: the name entered by whoever sent the invitation was not prefilled on the form.
describe('AcceptInvitationPage name prefill', () => {
  beforeEach(() => auth.getInvitation.mockReset());

  it('prefills the invited name', async () => {
    auth.getInvitation.mockResolvedValue({ ...INVITATION, full_name: 'Ravi Kumar' });
    renderPage();
    expect(await screen.findByDisplayValue('Ravi Kumar')).toBeInTheDocument();
  });

  it('leaves the name empty when none was given', async () => {
    auth.getInvitation.mockResolvedValue({ ...INVITATION, full_name: null });
    renderPage();
    const input = (await screen.findByLabelText(/Your full name/)) as HTMLInputElement;
    expect(input.value).toBe('');
  });
});
