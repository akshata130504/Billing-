/**
 * AI in Billing honours its visual-editor spec (appUi/specs/ai_billing.json) and renders exactly
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
import { AIBillingPage } from './AIBillingPage';

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
      <AIBillingPage />
    </UiConfigOverride>
  ) : (
    <AIBillingPage />
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/ai-billing']}>
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
  // jsdom has no layout; the Ask panel scrolls its transcript on mount.
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => undefined;
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = previewAdapter;
});
afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
});

describe('AI in Billing page spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'AI in Billing' })).toBeInTheDocument();
    expect(screen.getByText('Insights')).toBeInTheDocument();
    for (const label of ['Requests logged', 'Questions answered', 'Action drafts', 'Texts generated']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText('Grounded answers with sources')).toBeInTheDocument();
    expect(screen.getByText('Propose → validate → confirm')).toBeInTheDocument();
    expect(screen.getByText('How it works')).toBeInTheDocument();
    // Sample activity log loads into the side rail.
    expect(await screen.findByText('What is our MRR this month?')).toBeInTheDocument();
    expect(document.querySelector('[data-ui-id]')).toBeNull();
  });

  it('relabels the header, a KPI card and a tab', () => {
    renderPage({
      ai_billing: {
        header: { title: 'Billing Copilot', eyebrow: 'Assist' },
        kpis: [{ key: 'requests', label: 'All requests' }],
        tabs: [{ key: 'history', label: 'Audit trail', caption: 'Everything the assistant did' }],
        rail: { how_it_works: 'Under the hood' },
      },
    });
    expect(screen.getByRole('heading', { name: 'Billing Copilot' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'AI in Billing' })).not.toBeInTheDocument();
    expect(screen.getByText('Assist')).toBeInTheDocument();
    expect(screen.getByText('All requests')).toBeInTheDocument();
    expect(screen.queryByText('Requests logged')).not.toBeInTheDocument();
    expect(screen.getByText('Audit trail')).toBeInTheDocument();
    expect(screen.getByText('Everything the assistant did')).toBeInTheDocument();
    expect(screen.getByText('Under the hood')).toBeInTheDocument();
  });

  it('hides KPI cards and tabs, but never the required Ask tab', () => {
    const { container } = renderPage({
      ai_billing: {
        kpis: [{ key: 'drafts', hidden: true }],
        tabs: [{ key: 'writing', hidden: true }, { key: 'ask', hidden: true }],
      },
    });
    expect(screen.queryByText('Action drafts')).not.toBeInTheDocument();
    expect(screen.getByText('Requests logged')).toBeInTheDocument();
    expect(screen.queryByText('Reminders and notes')).not.toBeInTheDocument();
    expect(ids(container, 'ai_billing.tabs.')).toEqual(['ai_billing.tabs.ask', 'ai_billing.tabs.draft', 'ai_billing.tabs.history']);
  });

  it('reorders KPI cards and tabs', () => {
    const { container } = renderPage({
      ai_billing: {
        kpis: [{ key: 'texts' }, { key: 'requests' }],
        tabs: [{ key: 'history' }, { key: 'ask' }],
      },
    });
    expect(ids(container, 'ai_billing.kpis.')).toEqual([
      'ai_billing.kpis.texts', 'ai_billing.kpis.requests', 'ai_billing.kpis.questions', 'ai_billing.kpis.drafts',
    ]);
    expect(ids(container, 'ai_billing.tabs.')).toEqual([
      'ai_billing.tabs.history', 'ai_billing.tabs.ask', 'ai_billing.tabs.draft', 'ai_billing.tabs.writing',
    ]);
  });
});
