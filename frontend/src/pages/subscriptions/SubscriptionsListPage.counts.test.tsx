import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const svc = vi.hoisted(() => ({ summary: vi.fn(), list: vi.fn() }));
vi.mock('../../services/subscriptionService', () => ({ subscriptionService: svc }));
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ hasRole: () => true }) }));

import { ToastProvider } from '../../components/common/Toast';
import { SubscriptionsListPage } from './SubscriptionsListPage';

const SUMMARY = {
  total_subscriptions: 2, active_count: 1, trialing_count: 0, paused_count: 0, past_due_count: 0,
  cancelled_count: 0, draft_count: 1, renewing_soon_count: 0, expiring_soon_count: 0,
  trial_expiring_soon_count: 0, auto_renew_enabled_count: 1, total_mrr: '100.00', arr: '1200.00',
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <SubscriptionsListPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const tab = (label: string) => screen.getByRole('button', { name: new RegExp(`^${label}`) });

// QA (new-bugs PDF, "Subscriptions List"): the Draft tab showed no count although a draft existed.
describe('SubscriptionsListPage tab counts', () => {
  beforeEach(() => {
    svc.summary.mockResolvedValue(SUMMARY);
    svc.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, pages: 0 });
  });

  it('shows every tab count, including the Draft tab and tabs whose count is zero', async () => {
    renderPage();
    expect(await within(tab('Draft')).findByText('1')).toBeInTheDocument();
    expect(within(tab('Active')).getByText('1')).toBeInTheDocument();
    expect(within(tab('Paused')).getByText('0')).toBeInTheDocument();
  });
});
