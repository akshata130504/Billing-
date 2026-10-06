import type { AxiosRequestConfig } from 'axios';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiClient } from '../../services/apiClient';
import { previewAdapter } from '../../platform/uiPreview/sampleData';
import { UiConfigOverride } from '../../appUi/UiConfigContext';
import type { PageConfigs } from '../../appUi/registry';
import { ActivityPage } from './ActivityPage';

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
        <UiConfigOverride pages={pages} selection={selection}>
          <ActivityPage />
        </UiConfigOverride>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const filterLabels = () =>
  within(screen.getByRole('tablist', { name: 'Activity category' }))
    .getAllByRole('tab')
    .map((t) => t.textContent);

describe('ActivityPage visual-editor spec', () => {
  it('renders the built-in text with no configuration', async () => {
    renderPage();
    expect(screen.getByRole('heading', { level: 1, name: 'Activity' })).toBeInTheDocument();
    expect(screen.getByText('Insights')).toBeInTheDocument();
    expect(
      screen.getByText('A chronological feed of everything that happens in your organization, derived from the audit log.')
    ).toBeInTheDocument();
    expect(filterLabels()).toEqual(['All activity', 'Billing', 'Customers', 'Payments', 'System']);
    expect(await screen.findByText('Invoice sent')).toBeInTheDocument();
    expect(await screen.findByText('You have reached the beginning of the log.')).toBeInTheDocument();
  });

  it('applies relabels, hidden filters and order', async () => {
    renderPage({
      activity: {
        header: { title: 'Audit Feed', eyebrow: 'Logs' },
        feed: { end_of_log: 'That is everything.' },
        filters: [
          { key: 'payments', label: 'Money In' },
          { key: 'all' },
          { key: 'system', hidden: true },
        ],
      },
    });
    expect(screen.getByRole('heading', { level: 1, name: 'Audit Feed' })).toBeInTheDocument();
    expect(screen.getByText('Logs')).toBeInTheDocument();
    expect(filterLabels()).toEqual(['Money In', 'All activity', 'Billing', 'Customers']);
    expect(document.querySelector('[data-ui-id="activity.filters.system"]')).toBeNull();
    expect(await screen.findByText('That is everything.')).toBeInTheDocument();
  });
});
