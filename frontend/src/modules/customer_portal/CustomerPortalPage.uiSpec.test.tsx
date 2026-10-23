/**
 * The Customer Portal settings page honours its visual-editor spec (appUi/specs/customer_portal.json) and renders exactly
 * as before without configuration. Requests are answered by the preview sample-data adapter.
 */
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from '../../services/apiClient';
import { previewAdapter } from '../../platform/uiPreview/sampleData';
import { AuthContext, type AuthContextValue } from '../../hooks/useAuth';
import { ToastProvider } from '../../components/common/Toast';
import { UiConfigOverride, type UiSelection } from '../../appUi/UiConfigContext';
import type { PageConfigs } from '../../appUi/registry';
import { CustomerPortalPage } from './CustomerPortalPage';

const NOW = '2026-01-01T00:00:00Z';
const fail = async (): Promise<never> => {
  throw new Error('not used');
};
const fakeAuth: AuthContextValue = {
  user: { id: 'u', email: 'asha@example.in', full_name: 'Asha Rao', last_login_at: null, created_at: NOW, two_factor_enabled: false },
  organization: null,
  membership: { id: 'm', role: 'owner', status: 'active', joined_at: NOW },
  organizations: [],
  isAuthenticated: true,
  isLoading: false,
  login: fail,
  completeMfaLogin: fail,
  logout: async () => undefined,
  switchOrganization: fail,
  refreshMe: async () => null,
  applyTokens: fail,
  hasRole: () => true,
};
// A selection API makes components emit data-ui-id, which lets us read the rendered order.
const selection: UiSelection = { selectedId: null, select: () => undefined };

function renderPage(pages?: PageConfigs) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const node: ReactNode = pages ? (
    <UiConfigOverride pages={pages} selection={selection}>
      <CustomerPortalPage />
    </UiConfigOverride>
  ) : (
    <CustomerPortalPage />
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/customer-portal']}>
        <AuthContext.Provider value={fakeAuth}>
          <ToastProvider>{node}</ToastProvider>
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ids = (container: HTMLElement, prefix: string) =>
  Array.from(container.querySelectorAll(`[data-ui-id^="${prefix}"]`)).map((el) => el.getAttribute('data-ui-id'));

let originalAdapter: AxiosRequestConfig['adapter'];
beforeEach(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = previewAdapter;
});
afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
});


describe('Customer Portal page spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'Customer Portal' })).toBeInTheDocument();
    expect(screen.getByText('Customer Experience')).toBeInTheDocument();
    expect(await screen.findByText('Portal identity')).toBeInTheDocument();
    for (const text of [
      'Access & security', 'Payments & saved cards', 'Trials', 'Portal access', 'What customers see',
      'Allow self sign-up', 'Identity verification on public links', 'Lock the save option',
      'Read-only preview of portal capabilities.', 'Shown in the portal header and dashboard.',
    ]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
    expect(screen.getByRole('switch', { name: 'Allow self sign-up' })).toHaveAttribute('aria-checked', 'true');
    expect(document.querySelector('[data-ui-id]')).toBeNull();
  });

  it('relabels the header, a section and a setting row', async () => {
    renderPage({
      customer_portal: {
        header: { title: 'Client Portal', subtitle: 'What clients can do once signed in.' },
        access: { title: 'Sign-in & sharing' },
        access_toggles: [{ key: 'allow_self_signup', label: 'Let clients register', caption: 'Clients create their own login.' }],
      },
    });
    expect(screen.getByRole('heading', { name: 'Client Portal' })).toBeInTheDocument();
    expect(screen.getByText('What clients can do once signed in.')).toBeInTheDocument();
    expect(await screen.findByText('Sign-in & sharing')).toBeInTheDocument();
    expect(screen.queryByText('Access & security')).not.toBeInTheDocument();
    // The relabelled row still drives the same setting.
    expect(screen.getByRole('switch', { name: 'Let clients register' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('Clients create their own login.')).toBeInTheDocument();
    expect(screen.queryByText('Allow self sign-up')).not.toBeInTheDocument();
  });

  it('never hides a setting row (the toggle lists are not hideable)', async () => {
    renderPage({
      customer_portal: {
        access_toggles: [{ key: 'auto_invite_enabled', hidden: true }],
        payment_toggles: [{ key: 'prevent_duplicate_payments', hidden: true }],
      },
    });
    expect(await screen.findByRole('switch', { name: 'Auto-invite new customers' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Prevent duplicate payments' })).toBeInTheDocument();
  });

  it('reorders setting rows, but keeps the fixed payment order', async () => {
    const { container } = renderPage({
      customer_portal: {
        access_toggles: [{ key: 'allow_document_forwarding' }, { key: 'identity_verification' }],
        payment_toggles: [{ key: 'prevent_deselecting_save_payment' }, { key: 'prevent_duplicate_payments' }],
      },
    });
    await screen.findByText('Portal identity');
    expect(ids(container, 'customer_portal.access_toggles.')).toEqual([
      'customer_portal.access_toggles.allow_document_forwarding',
      'customer_portal.access_toggles.identity_verification',
      'customer_portal.access_toggles.allow_self_signup',
      'customer_portal.access_toggles.auto_invite_enabled',
      'customer_portal.access_toggles.allow_document_upload',
    ]);
    expect(ids(container, 'customer_portal.payment_toggles.')).toEqual([
      'customer_portal.payment_toggles.prevent_duplicate_payments',
      'customer_portal.payment_toggles.allow_save_payment_methods',
      'customer_portal.payment_toggles.save_payment_method_default',
      'customer_portal.payment_toggles.prevent_deselecting_save_payment',
    ]);
  });
});
