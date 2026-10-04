import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '../../components/common/Toast';
import { PlatformRoutes } from '../PlatformApp';
import { PlatformApiError, platformApi, type PlatformRole } from '../platformApi';
import { consoleApi } from '../consoleApi';
import { GRANT_MESSAGE, READY_MESSAGE, TENANT_APP_ORIGIN, grantsApi, type AccessGrant } from '../grantsApi';

vi.mock('../platformApi', async () => {
  const actual = await vi.importActual<typeof import('../platformApi')>('../platformApi');
  return { ...actual, platformApi: { me: vi.fn(), refresh: vi.fn(), logout: vi.fn(), stepUp: vi.fn(), sessions: vi.fn() } };
});
vi.mock('../consoleApi', async () => {
  const actual = await vi.importActual<typeof import('../consoleApi')>('../consoleApi');
  return { ...actual, consoleApi: { organizations: vi.fn(), dashboard: vi.fn() } };
});
vi.mock('../grantsApi', async () => {
  const actual = await vi.importActual<typeof import('../grantsApi')>('../grantsApi');
  return {
    ...actual,
    grantsApi: { list: vi.fn(), request: vi.fn(), requestEmergency: vi.fn(), cancel: vi.fn(), revoke: vi.fn(), enter: vi.fn(),
      approveEmergency: vi.fn(), review: vi.fn() },
  };
});

type Mocked<T> = { [K in keyof T]: ReturnType<typeof vi.fn> };
const auth = platformApi as unknown as Mocked<typeof platformApi>;
const api = grantsApi as unknown as Mocked<typeof grantsApi>;
const orgs = consoleApi as unknown as Mocked<typeof consoleApi>;

const ME_ID = 'staff-me';
function grant(over: Partial<AccessGrant> = {}): AccessGrant {
  return {
    id: 'g1', organization_id: 'org-1', organization_name: 'Acme Traders', status: 'approved', scopes: ['READ_METADATA', 'READ_CUSTOMERS'],
    reason: 'Customer reports wrong GST split on invoices', ticket_ref: 'SUP-9', requested_duration_minutes: 60, is_emergency: false,
    requested_by: { id: ME_ID, full_name: 'Sam Support', role: 'platform_support' }, approved_by: { id: 'u1', full_name: 'Olive Owner', kind: 'tenant_user' },
    created_at: '2026-10-01T09:00:00Z', approved_at: '2026-10-01T09:05:00Z', first_used_at: null, last_entered_at: null,
    expires_at: '2026-10-01T10:05:00Z', revoked_at: null, revoked_by_kind: null, revoke_reason: null, denied_at: null, denied_reason: null,
    request_count: 0, reviewed_at: null, review_notes: null, review_due_at: null, review_overdue: false, ...over,
  };
}

function renderAt(role: PlatformRole = 'platform_support', path = '/access-grants') {
  auth.me.mockResolvedValue({ staff: { id: ME_ID, email: 'sam@rooman.test', full_name: 'Sam Support', role }, session_id: 's', session_expires_at: '2026-10-02T00:00:00Z', access_expires_in: 600 });
  return render(<ToastProvider><MemoryRouter initialEntries={[path]}><PlatformRoutes /></MemoryRouter></ToastProvider>);
}

beforeEach(() => vi.clearAllMocks());

describe('tenant access grants in the console', () => {
  it('is not available to Operations', async () => {
    renderAt('platform_operations');
    expect(await screen.findByText('Not available for your role')).toBeInTheDocument();
    expect(api.list).not.toHaveBeenCalled();
  });

  it('requests access with scopes, duration, reason and ticket', async () => {
    api.list.mockResolvedValue({ items: [] });
    orgs.organizations.mockResolvedValue({ items: [{ id: 'org-1', name: 'Acme Traders', slug: 'acme' }], total: 1, page: 1, page_size: 8, total_pages: 1 });
    api.request.mockResolvedValue(grant({ status: 'pending' }));
    renderAt();
    fireEvent.click(await screen.findByRole('button', { name: 'Request access' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByPlaceholderText('Name, slug or id'), { target: { value: 'acme' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Find' }));
    fireEvent.click(await within(dialog).findByRole('button', { name: /Acme Traders/ }));
    fireEvent.click(within(dialog).getByLabelText('Invoices and credit notes'));
    const submit = within(dialog).getByRole('button', { name: 'Send request to the Owner' });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Ticket reference/), { target: { value: 'SUP-9' } });
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Customer reports wrong GST split on invoices' } });
    fireEvent.click(submit);
    await waitFor(() => expect(api.request).toHaveBeenCalledWith({
      organization_id: 'org-1', scopes: ['READ_CUSTOMERS', 'READ_INVOICES'], duration_minutes: 60,
      reason: 'Customer reports wrong GST split on invoices', ticket_ref: 'SUP-9',
    }));
  });

  it('enters the tenant: opens the workspace tab, asks for a fresh code, and hands the token over by postMessage only', async () => {
    api.list.mockResolvedValue({ items: [grant()] });
    api.enter
      .mockRejectedValueOnce(new PlatformApiError('Confirm it is you.', 403, 'STEP_UP_REQUIRED'))
      .mockResolvedValueOnce({ grant: grant({ status: 'active' }), token: 'grant-token-abc', token_expires_at: 'x', organization: { id: 'org-1', name: 'Acme Traders' } });
    auth.stepUp.mockResolvedValue({});
    const popup = { postMessage: vi.fn() } as unknown as Window;
    const open = vi.spyOn(window, 'open').mockReturnValue(popup);
    renderAt();
    fireEvent.click(await screen.findByRole('button', { name: /Enter tenant/ }));
    expect(open).toHaveBeenCalledWith(`${TENANT_APP_ORIGIN}/platform-access`, 'rooman-platform-access-g1');
    fireEvent.change(await screen.findByLabelText(/^Authenticator code/), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }));
    await waitFor(() => expect(api.enter).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(popup.postMessage).toHaveBeenCalledWith({ type: GRANT_MESSAGE, token: 'grant-token-abc' }, TENANT_APP_ORIGIN));
    // a "ready" from the right window/origin re-delivers; from anywhere else it is ignored
    (popup.postMessage as ReturnType<typeof vi.fn>).mockClear();
    window.dispatchEvent(new MessageEvent('message', { origin: 'https://evil.example', source: popup as unknown as MessageEventSource, data: { type: READY_MESSAGE } }));
    expect(popup.postMessage).not.toHaveBeenCalled();
    window.dispatchEvent(new MessageEvent('message', { origin: TENANT_APP_ORIGIN, source: popup as unknown as MessageEventSource, data: { type: READY_MESSAGE } }));
    expect(popup.postMessage).toHaveBeenCalledWith({ type: GRANT_MESSAGE, token: 'grant-token-abc' }, TENANT_APP_ORIGIN);
    // the token never touches storage
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    open.mockRestore();
  });

  it('shows only the right actions per status and person', async () => {
    api.list.mockResolvedValue({ items: [
      grant({ id: 'p', status: 'pending' }),
      grant({ id: 'o', status: 'approved', requested_by: { id: 'someone', full_name: 'Other Support' } }),
      grant({ id: 'd', status: 'denied' }),
    ] });
    renderAt();
    const items = await screen.findAllByRole('listitem');
    expect(within(items[0]).getByRole('button', { name: 'Cancel request' })).toBeInTheDocument();
    expect(within(items[0]).queryByRole('button', { name: /Enter tenant/ })).not.toBeInTheDocument();
    expect(within(items[1]).queryByRole('button', { name: /Enter tenant/ })).not.toBeInTheDocument(); // not my grant
    expect(within(items[2]).queryAllByRole('button')).toHaveLength(0);
  });

  it('emergency: only a different administrator sees Approve; review is recorded', async () => {
    api.list.mockResolvedValue({ items: [
      grant({ id: 'mine', is_emergency: true, status: 'pending', requested_by: { id: ME_ID, full_name: 'Me' } }),
      grant({ id: 'theirs', is_emergency: true, status: 'pending', requested_by: { id: 'other-admin', full_name: 'Other Admin' } }),
      grant({ id: 'used', is_emergency: true, status: 'expired', approved_at: '2026-09-20T09:00:00Z', review_overdue: true }),
    ] });
    api.approveEmergency.mockResolvedValue(grant({ id: 'theirs', is_emergency: true }));
    api.review.mockResolvedValue(grant({ id: 'used', reviewed_at: 'x' }));
    auth.stepUp.mockResolvedValue({});
    renderAt('platform_administrator');
    const items = await screen.findAllByRole('listitem');
    expect(within(items[0]).queryByRole('button', { name: /Approve/ })).not.toBeInTheDocument();
    expect(within(items[2]).getByText('Review overdue')).toBeInTheDocument();
    fireEvent.click(within(items[1]).getByRole('button', { name: 'Approve (second administrator)' }));
    await waitFor(() => expect(api.approveEmergency).toHaveBeenCalledWith('theirs'));
    fireEvent.click(within(items[2]).getByRole('button', { name: 'Record review' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'Fraud contained; owner informed by phone.' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save review' }));
    await waitFor(() => expect(api.review).toHaveBeenCalledWith('used', 'Fraud contained; owner informed by phone.'));
  });

  it('caps emergency requests at 60 minutes in the form', async () => {
    api.list.mockResolvedValue({ items: [] });
    renderAt('platform_administrator');
    fireEvent.click(await screen.findByRole('button', { name: /Emergency access/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/A DIFFERENT Platform Administrator must approve/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/Duration \(minutes, max 60\)/)).toHaveAttribute('max', '60');
  });
});
