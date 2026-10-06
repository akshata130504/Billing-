/**
 * The Data Migration page honours its visual-editor spec (appUi/specs/data_migration.json) and
 * renders exactly its built-in UI without configuration. Rendered against the preview adapter.
 */
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from '../../services/apiClient';
import { previewAdapter } from '../../platform/uiPreview/sampleData';
import { AuthContext, type AuthContextValue } from '../../hooks/useAuth';
import { ToastProvider } from '../../components/common/Toast';
import { UiConfigOverride, type UiSelection } from '../../appUi/UiConfigContext';
import type { PageConfigs } from '../../appUi/registry';
import { DataMigrationPage } from './DataMigrationPage';

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

const selection: UiSelection = { selectedId: null, select: () => undefined };

function renderPage(pages?: PageConfigs) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const page: ReactNode = pages ? (
    <UiConfigOverride pages={pages} selection={selection}>
      <DataMigrationPage />
    </UiConfigOverride>
  ) : (
    <DataMigrationPage />
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/control-center/migration']}>
        <AuthContext.Provider value={fakeAuth}>
          <ToastProvider>{page}</ToastProvider>
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const headers = () => screen.getAllByRole('columnheader').map((th) => th.textContent);
const ids = (container: HTMLElement, prefix: string) =>
  Array.from(container.querySelectorAll(`[data-ui-id^="${prefix}"]`)).map((el) => el.getAttribute('data-ui-id'));

let originalAdapter: AxiosRequestConfig['adapter'];
beforeEach(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = previewAdapter;
});
afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
});

describe('DataMigrationPage visual-editor spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    const { container } = renderPage();
    expect(await screen.findByText('customers_sample.csv')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Data Migration & Onboarding');
    expect(screen.getByText('Self-Service Import')).toBeInTheDocument();
    expect(screen.getByText('1. Select Target Data Model')).toBeInTheDocument();
    expect(screen.getByText('Drop your CSV file here, or browse')).toBeInTheDocument();
    expect(screen.getByText('Required columns for Customers:')).toBeInTheDocument();
    expect(screen.getByText('Recent Imports')).toBeInTheDocument();
    expect(headers()).toEqual(['Entity', 'File', 'Status', 'Imported', 'Failed', 'Total', 'When']);
    expect(container.querySelector('[data-ui-id]')).toBeNull();
  });

  it('relabels the header, a data model card (with its caption) and a column', async () => {
    renderPage({
      data_migration: {
        header: { title: 'Bring your data', badge: 'CSV import' },
        entities: [{ key: 'customers', label: 'Clients', caption: 'Your client list.' }],
        columns: [{ key: 'file', label: 'CSV file' }],
      },
    });
    await screen.findByText('customers_sample.csv');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Bring your data');
    expect(screen.getByText('CSV import')).toBeInTheDocument();
    expect(screen.getByText('Clients')).toBeInTheDocument();
    expect(screen.getByText('Your client list.')).toBeInTheDocument();
    // The selected model's configured name follows into the schema hint.
    expect(screen.getByText('Required columns for Clients:')).toBeInTheDocument();
    expect(headers()).toContain('CSV file');
  });

  it('hides a history column (header and cells)', async () => {
    renderPage({ data_migration: { columns: [{ key: 'failed', hidden: true }] } });
    await screen.findByText('customers_sample.csv');
    expect(headers()).not.toContain('Failed');
    expect(within(screen.getAllByRole('row')[1]).getAllByRole('cell')).toHaveLength(6);
  });

  it('reorders history columns and body cells together; the data model order is fixed', async () => {
    const { container } = renderPage({
      data_migration: {
        columns: [{ key: 'file' }, { key: 'entity' }],
        entities: [{ key: 'plans' }, { key: 'customers' }],
      },
    });
    await screen.findByText('customers_sample.csv');
    expect(headers().slice(0, 3)).toEqual(['File', 'Entity', 'Status']);
    const cells = within(screen.getAllByRole('row')[1]).getAllByRole('cell');
    expect(cells[0]).toHaveTextContent('plans_sample.csv');
    expect(cells[1]).toHaveTextContent('plans');
    expect(ids(container, 'data_migration.entities.')).toEqual([
      'data_migration.entities.customers', 'data_migration.entities.products', 'data_migration.entities.plans',
    ]);
  });
});
