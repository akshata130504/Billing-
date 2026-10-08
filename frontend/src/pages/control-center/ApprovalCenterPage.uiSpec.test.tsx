import type { AxiosRequestConfig } from 'axios';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiClient } from '../../services/apiClient';
import { previewAdapter } from '../../platform/uiPreview/sampleData';
import { ToastProvider } from '../../components/common/Toast';
import { UiConfigOverride } from '../../appUi/UiConfigContext';
import type { PageConfigs } from '../../appUi/registry';
import { ApprovalCenterPage } from './ApprovalCenterPage';

const auth = vi.hoisted(() => ({ admin: true }));
vi.mock('../../hooks/useAuth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../hooks/useAuth')>();
  return { ...actual, useAuth: () => ({ hasRole: () => auth.admin }) };
});

let originalAdapter: AxiosRequestConfig['adapter'];
beforeAll(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = previewAdapter;
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
afterEach(() => {
  cleanup();
  auth.admin = true;
});

const selection = { selectedId: null, select: () => undefined };

function renderPage(pages: PageConfigs = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <UiConfigOverride pages={pages} selection={selection}>
            <ApprovalCenterPage />
          </UiConfigOverride>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const tabIds = () =>
  Array.from(document.querySelectorAll('[data-ui-id^="approvals.tabs."]')).map((el) => el.getAttribute('data-ui-id'));

describe('ApprovalCenterPage visual-editor spec', () => {
  it('renders the built-in text with no configuration', async () => {
    renderPage();
    expect(screen.getByRole('heading', { level: 1, name: 'Approval Center' })).toBeInTheDocument();
    expect(screen.getByText('Governance & Compliance')).toBeInTheDocument();
    expect(await screen.findByText('2 Pending Decisions')).toBeInTheDocument();
    expect(await screen.findByText('Pending Review (2)')).toBeInTheDocument();
    expect(tabIds()).toEqual(['approvals.tabs.pending', 'approvals.tabs.approved', 'approvals.tabs.rejected', 'approvals.tabs.all']);
    expect(await screen.findByText('25% discount on Growth plan annual quote')).toBeInTheDocument();
  });

  it('applies relabels, hidden tabs and order', async () => {
    auth.admin = false;
    renderPage({
      approvals: {
        header: { title: 'Sign-off Queue', pending: '{count} awaiting you' },
        notice: { read_only: 'Ask an admin to decide.' },
        tabs: [{ key: 'all', label: 'Everything' }, { key: 'pending', label: 'To Review' }, { key: 'rejected', hidden: true }],
      },
    });
    expect(screen.getByRole('heading', { level: 1, name: 'Sign-off Queue' })).toBeInTheDocument();
    expect(await screen.findByText('2 awaiting you')).toBeInTheDocument();
    expect(await screen.findByText('To Review (2)')).toBeInTheDocument();
    expect(screen.getByText('Everything')).toBeInTheDocument();
    expect(screen.getByText('Ask an admin to decide.')).toBeInTheDocument();
    expect(tabIds()).toEqual(['approvals.tabs.all', 'approvals.tabs.pending', 'approvals.tabs.approved']);
    expect(screen.queryByText('Rejected')).toBeNull();
  });
});
