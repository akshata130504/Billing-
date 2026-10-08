import type { AxiosRequestConfig } from 'axios';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiClient } from '../../services/apiClient';
import { previewAdapter } from '../../platform/uiPreview/sampleData';
import { UiConfigOverride } from '../../appUi/UiConfigContext';
import type { PageConfigs } from '../../appUi/registry';
import { BillingCalendarPage } from './BillingCalendarPage';

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
          <BillingCalendarPage />
        </UiConfigOverride>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const texts = (prefix: string) =>
  Array.from(document.querySelectorAll(`[data-ui-id^="billing_calendar.${prefix}."]`)).map((el) => el.textContent);

describe('BillingCalendarPage visual-editor spec', () => {
  it('renders the built-in text with no configuration', async () => {
    renderPage();
    expect(screen.getByRole('heading', { level: 1, name: 'Billing Calendar' })).toBeInTheDocument();
    expect(screen.getByText('Schedule & Planning')).toBeInTheDocument();
    expect(texts('tabs')).toEqual(['All Events', 'Invoices Due', 'Renewals', 'Expiring Trials', 'Expiring Quotes']);
    expect(await screen.findByRole('heading', { name: 'Upcoming Agenda (6)' }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText('Chronological')).toBeInTheDocument();
    expect(texts('weekdays')).toEqual(['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']);
  });

  it('applies relabels, hidden tabs and tab order; weekday order stays fixed', async () => {
    renderPage({
      billing_calendar: {
        header: { title: 'Billing Schedule' },
        agenda: { title: 'Coming Up', caption: 'By date' },
        tabs: [{ key: 'quote_expiry', label: 'Quotes' }, { key: 'all' }, { key: 'trial_ending', hidden: true }],
        weekdays: [{ key: 'mon', label: 'Lun' }, { key: 'sun', label: 'Dim' }],
      },
    });
    expect(screen.getByRole('heading', { level: 1, name: 'Billing Schedule' })).toBeInTheDocument();
    expect(texts('tabs')).toEqual(['Quotes', 'All Events', 'Invoices Due', 'Renewals']);
    expect(await screen.findByRole('heading', { name: 'Coming Up (6)' }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText('By date')).toBeInTheDocument();
    expect(texts('weekdays')).toEqual(['Dim', 'Lun', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']);
  });
});
