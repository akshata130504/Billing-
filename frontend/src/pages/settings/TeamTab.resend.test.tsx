import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const org = vi.hoisted(() => ({ listTeam: vi.fn(), invite: vi.fn(), updateMemberRole: vi.fn(), deactivateMember: vi.fn() }));
vi.mock('../../services/organizationService', () => ({ organizationService: org }));
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'me' }, membership: { id: 'm-me' }, hasRole: () => true }),
}));
vi.mock('../../components/common/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));

import { TeamTab } from './TeamTab';

const member = (id: string, name: string, status: string, role = 'finance') => ({
  id: `m-${id}`, role, status, user: { id, email: `${id}@example.test`, full_name: name },
  invited_by: null, accepted_at: status === 'active' ? '2026-10-01T00:00:00Z' : null,
  invite_expires_at: status === 'invited' ? '2026-10-30T00:00:00Z' : null, created_at: '2026-10-01T00:00:00Z',
});

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><TeamTab canEdit /></QueryClientProvider>);
}

// BUG-34: an invited member had no way to get a fresh invitation except re-inviting by hand.
describe('TeamTab resend invitation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    org.listTeam.mockResolvedValue([member('u1', 'Ivy Invited', 'invited'), member('u2', 'Ann Active', 'active')]);
    org.invite.mockResolvedValue({ ...member('u1', 'Ivy Invited', 'invited'), email_delivered: true });
  });

  it('offers Resend only on invited members and re-invites with the same email and role', async () => {
    renderTab();
    const invitedRow = (await screen.findByText('Ivy Invited')).closest('tr') as HTMLElement;
    const activeRow = screen.getByText('Ann Active').closest('tr') as HTMLElement;
    expect(within(activeRow).queryByRole('button', { name: /Resend invitation/ })).toBeNull();

    fireEvent.click(within(invitedRow).getByRole('button', { name: /Resend invitation/ }));
    await waitFor(() => expect(org.invite).toHaveBeenCalledWith({
      email: 'u1@example.test', role: 'finance', full_name: 'Ivy Invited',
    }));
  });
});
