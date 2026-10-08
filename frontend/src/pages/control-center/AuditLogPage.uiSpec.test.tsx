/**
 * The Audit Log page honours its visual-editor spec (appUi/specs/audit_log.json) and renders
 * exactly its built-in UI without configuration. Rendered against the preview sample-data adapter.
 */
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from '../../services/apiClient';
import { previewAdapter } from '../../platform/uiPreview/sampleData';
import { ToastProvider } from '../../components/common/Toast';
import { UiConfigOverride, type UiSelection } from '../../appUi/UiConfigContext';
import type { PageConfigs } from '../../appUi/registry';
import { AuditLogPage } from './AuditLogPage';

const selection: UiSelection = { selectedId: null, select: () => undefined };

function renderPage(pages?: PageConfigs) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const page: ReactNode = pages ? (
    <UiConfigOverride pages={pages} selection={selection}>
      <AuditLogPage />
    </UiConfigOverride>
  ) : (
    <AuditLogPage />
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/control-center/audit-log']}>
        <ToastProvider>{page}</ToastProvider>
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

describe('AuditLogPage visual-editor spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    const { container } = renderPage();
    expect(await screen.findByText('INVOICE_VOIDED')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Immutable Audit Trail');
    expect(screen.getByText('SOC 2 / ISO Compliance')).toBeInTheDocument();
    expect(screen.getByText('Append-Only Financial Ledger Active')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Search actor, entity, IP...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'All Subsystems' })).toBeInTheDocument();
    expect(headers()).toEqual(['Timestamp', 'Actor', 'Action', 'Affected Entity', 'Status', 'IP Address', 'Details']);
    // Outside the editor the DOM carries no selection hooks.
    expect(container.querySelector('[data-ui-id]')).toBeNull();
  });

  it('relabels the header, a column and a subsystem tab', async () => {
    renderPage({
      audit_log: {
        header: { title: 'Compliance Ledger', badge: 'ISO 27001' },
        columns: [{ key: 'actor', label: 'User' }],
        subsystems: [{ key: 'invoice', label: 'Billing documents' }],
      },
    });
    await screen.findByText('INVOICE_VOIDED');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Compliance Ledger');
    expect(screen.getByText('ISO 27001')).toBeInTheDocument();
    expect(headers()).toContain('User');
    expect(headers()).not.toContain('Actor');
    expect(screen.getByRole('button', { name: 'Billing documents' })).toBeInTheDocument();
  });

  it('hides a column (header and cells) and keeps colSpan in step', async () => {
    renderPage({ audit_log: { columns: [{ key: 'ip_address', hidden: true }] } });
    await screen.findByText('INVOICE_VOIDED');
    expect(headers()).not.toContain('IP Address');
    expect(screen.queryByText('203.0.113.24')).toBeNull();
    const firstRow = screen.getAllByRole('row')[1];
    expect(within(firstRow).getAllByRole('cell')).toHaveLength(6);
  });

  it('reorders columns and body cells together', async () => {
    const { container } = renderPage({
      audit_log: { columns: [{ key: 'action' }, { key: 'status' }], subsystems: [{ key: 'import' }] },
    });
    await screen.findByText('INVOICE_VOIDED');
    expect(ids(container, 'audit_log.columns.')).toEqual([
      'audit_log.columns.action', 'audit_log.columns.status', 'audit_log.columns.timestamp',
      'audit_log.columns.actor', 'audit_log.columns.entity', 'audit_log.columns.ip_address', 'audit_log.columns.details',
    ]);
    const cells = within(screen.getAllByRole('row')[1]).getAllByRole('cell');
    expect(cells[0]).toHaveTextContent('INVOICE_VOIDED');
    expect(cells[1]).toHaveTextContent('Success');
    expect(ids(container, 'audit_log.subsystems.')[0]).toBe('audit_log.subsystems.import');
  });
});
