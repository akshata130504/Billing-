import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '../../components/common/Toast';
import { PlatformAccessBanner } from '../../components/layout/PlatformAccessBanner';
import { platformAccessService, type PlatformAccessGrant } from '../../services/platformAccessService';
import { PlatformAccessTab } from './PlatformAccessTab';

let role = 'owner';
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    hasRole: (min: string) => ({ viewer: 1, finance: 2, admin: 3, owner: 4 } as Record<string, number>)[role] >= ({ viewer: 1, finance: 2, admin: 3, owner: 4 } as Record<string, number>)[min],
  }),
}));
vi.mock('../../services/platformAccessService', async () => {
  const actual = await vi.importActual<typeof import('../../services/platformAccessService')>('../../services/platformAccessService');
  return { ...actual, platformAccessService: { list: vi.fn(), active: vi.fn(), approve: vi.fn(), deny: vi.fn(), revoke: vi.fn() } };
});

const svc = platformAccessService as unknown as Record<keyof typeof platformAccessService, ReturnType<typeof vi.fn>>;

const G = (over: Partial<PlatformAccessGrant> = {}): PlatformAccessGrant => ({
  id: 'g1', organization_id: 'o', organization_name: 'Acme', status: 'pending', scopes: ['READ_METADATA', 'READ_INVOICES'],
  reason: 'Customer reports wrong GST split on invoices', ticket_ref: 'SUP-9', requested_duration_minutes: 60, is_emergency: false,
  requested_by: { id: 's', full_name: 'Sam Support', role: 'platform_support' }, approved_by: null, created_at: '2026-10-01T09:00:00Z',
  approved_at: null, first_used_at: null, expires_at: null, revoked_at: null, revoke_reason: null, denied_reason: null, request_count: 0, ...over,
});

function wrap(ui: JSX.Element) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><ToastProvider><MemoryRouter>{ui}</MemoryRouter></ToastProvider></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  role = 'owner';
});

describe('Settings > Platform access', () => {
  it('lets the Owner see the request details and approve it', async () => {
    svc.list.mockResolvedValue([G()]);
    svc.approve.mockResolvedValue(G({ status: 'approved' }));
    wrap(<PlatformAccessTab />);
    expect(await screen.findByText('Sam Support')).toBeInTheDocument();
    expect(screen.getByText('Customer reports wrong GST split on invoices')).toBeInTheDocument();
    expect(screen.getByText('Invoices and credit notes')).toBeInTheDocument();
    expect(screen.getByText(/Ticket SUP-9/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(svc.approve).toHaveBeenCalled());
    expect(svc.approve.mock.calls[0][0]).toBe('g1');
  });

  it('does not let an Admin approve, but lets them revoke', async () => {
    role = 'admin';
    svc.list.mockResolvedValue([G(), G({ id: 'g2', status: 'active', expires_at: '2026-10-01T10:00:00Z' })]);
    svc.revoke.mockResolvedValue(G({ id: 'g2', status: 'revoked' }));
    wrap(<PlatformAccessTab />);
    await screen.findAllByText('Sam Support');
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    const items = screen.getAllByRole('listitem');
    fireEvent.click(within(items[1]).getByRole('button', { name: 'Revoke now' }));
    fireEvent.change(within(items[1]).getByLabelText(/Reason for revoking/), { target: { value: 'Issue solved' } });
    fireEvent.click(within(items[1]).getByRole('button', { name: 'Revoke access' }));
    await waitFor(() => expect(svc.revoke).toHaveBeenCalledWith('g2', 'Issue solved'));
  });

  it('denies with an optional reason; emergency grants cannot be approved by the Owner', async () => {
    svc.list.mockResolvedValue([G(), G({ id: 'e1', is_emergency: true })]);
    svc.deny.mockResolvedValue(G({ status: 'denied' }));
    wrap(<PlatformAccessTab />);
    const items = await screen.findAllByRole('listitem');
    expect(within(items[1]).getByText('Emergency')).toBeInTheDocument();
    expect(within(items[1]).queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    fireEvent.click(within(items[0]).getByRole('button', { name: 'Deny' }));
    fireEvent.click(within(items[0]).getByRole('button', { name: 'Deny request' }));
    await waitFor(() => expect(svc.deny).toHaveBeenCalledWith('g1', undefined));
  });

  it('banner shows active access to Owners and Admins only', async () => {
    svc.active.mockResolvedValue([G({ status: 'active', expires_at: '2026-10-01T10:30:00Z' })]);
    const { unmount } = wrap(<PlatformAccessBanner />);
    expect(await screen.findByText(/has read access to Invoices and credit notes/)).toBeInTheDocument();
    unmount();
    role = 'finance';
    svc.active.mockClear();
    wrap(<PlatformAccessBanner />);
    await new Promise((r) => setTimeout(r, 20));
    expect(svc.active).not.toHaveBeenCalled();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
