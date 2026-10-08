import type { AxiosRequestConfig } from 'axios';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiClient } from '../../services/apiClient';
import { previewAdapter } from '../../platform/uiPreview/sampleData';
import { ToastProvider } from '../../components/common/Toast';
import { UiConfigOverride } from '../../appUi/UiConfigContext';
import type { PageConfigs } from '../../appUi/registry';
import { ActionCenterPage } from './ActionCenterPage';

let originalAdapter: AxiosRequestConfig['adapter'];
beforeAll(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = previewAdapter;
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
afterEach(cleanup);

const selection = { selectedId: null, select: () => undefined };

function renderPage(pages: PageConfigs = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <UiConfigOverride pages={pages} selection={selection}>
            <ActionCenterPage />
          </UiConfigOverride>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const ids = (prefix: string) =>
  Array.from(document.querySelectorAll(`[data-ui-id^="action_center.${prefix}."]`)).map((el) =>
    el.getAttribute('data-ui-id')!.slice(`action_center.${prefix}.`.length)
  );
const el = (id: string) => document.querySelector(`[data-ui-id="action_center.${id}"]`) as HTMLElement | null;

describe('ActionCenterPage visual-editor spec', () => {
  it('renders the built-in text with no configuration', async () => {
    renderPage();
    expect(screen.getByRole('heading', { level: 1, name: 'Action Center' })).toBeInTheDocument();
    expect(screen.getByText('Operator Cockpit')).toBeInTheDocument();
    await screen.findByText('All Attention (3)');
    expect(ids('kpis')).toEqual(['overdue', 'failed_payment', 'expiring_trial', 'pending_quote', 'pending_approval']);
    expect(el('kpis.overdue')).toHaveTextContent('Overdue Invoices2Requires reminder notice');
    expect(ids('tabs')).toEqual(['all', 'overdue', 'failed_payment', 'expiring_trial', 'pending_quote', 'pending_approval']);
    expect(el('tabs.overdue')).toHaveTextContent('Overdue Invoices (2)');
    expect(screen.getAllByText('Impact Value').length).toBeGreaterThan(0);
  });

  it('applies relabels, hidden items and order', async () => {
    renderPage({
      action_center: {
        header: { title: 'Exceptions Desk', badge: 'Ops' },
        kpis: [
          { key: 'expiring_trial', label: 'Trials Ending', caption: 'Convert soon' },
          { key: 'overdue' },
          { key: 'failed_payment', hidden: true },
        ],
        tabs: [{ key: 'pending_quote', hidden: true }, { key: 'overdue', label: 'Late' }],
        items: { impact: 'Amount at Risk' },
      },
    });
    expect(screen.getByRole('heading', { level: 1, name: 'Exceptions Desk' })).toBeInTheDocument();
    expect(screen.getByText('Ops')).toBeInTheDocument();
    await screen.findByText('Late (2)');
    expect(ids('kpis')).toEqual(['expiring_trial', 'overdue', 'pending_quote', 'pending_approval']);
    expect(el('kpis.expiring_trial')).toHaveTextContent('Trials Ending1Convert soon');
    expect(el('kpis.failed_payment')).toBeNull();
    expect(ids('tabs')).toEqual(['overdue', 'all', 'failed_payment', 'expiring_trial', 'pending_approval']);
    expect(screen.getAllByText('Amount at Risk').length).toBeGreaterThan(0);
  });
});
