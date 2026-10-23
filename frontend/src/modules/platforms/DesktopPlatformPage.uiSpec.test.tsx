/**
 * Platforms > Desktop honours its own visual-editor spec (appUi/specs/desktop.json), independently
 * of the Mobile page that shares its component. Rendered against the preview sample-data adapter.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, screen, within } from '@testing-library/react';
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from '../../services/apiClient';
import { previewAdapter } from '../../platform/uiPreview/sampleData';
import { DesktopPlatformPage } from './DesktopPlatformPage';
import { columnHeaders, renderPlatformPage, uiIds } from './platformUiSpecTestUtils';

const renderPage = (pages?: Parameters<typeof renderPlatformPage>[2]) =>
  renderPlatformPage(<DesktopPlatformPage />, '/platforms/desktop', pages);

let originalAdapter: AxiosRequestConfig['adapter'];
beforeEach(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = previewAdapter;
});
afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
});

describe('DesktopPlatformPage visual-editor spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    const { container } = renderPage();
    expect(await screen.findByText('Finance workstation')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Desktop');
    expect(screen.getByText(/^Windows and macOS shells/)).toBeInTheDocument();
    expect(screen.getByText('Windows · macOS')).toBeInTheDocument();
    expect(screen.getByText('2 of 2 · your devices in this organization')).toBeInTheDocument();
    expect(screen.getByText('Sign in on desktop')).toBeInTheDocument();
    expect(columnHeaders()).toEqual(['Device', 'Platform', 'App version', 'Last seen', 'Registered', 'Status', 'Actions']);
    expect(container.querySelector('[data-ui-id]')).toBeNull();
  });

  it('uses its own configuration, not the mobile page\'s', async () => {
    renderPage({
      mobile: { header: { title: 'Phones' } },
      desktop: {
        header: { title: 'Workstations' },
        stats: [{ key: 'active', label: 'Online lately' }],
        columns: [{ key: 'last_seen', label: 'Last check-in' }],
      },
    });
    await screen.findByText('Finance workstation');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Workstations');
    expect(screen.getByText('Online lately')).toBeInTheDocument();
    expect(columnHeaders()).toContain('Last check-in');
    expect(screen.queryByText('Phones')).toBeNull();
  });

  it('hides a column (header and cells)', async () => {
    renderPage({ desktop: { columns: [{ key: 'actions', hidden: true }] } });
    await screen.findByText('Finance workstation');
    expect(columnHeaders()).not.toContain('Actions');
    expect(screen.queryByRole('button', { name: /Revoke/ })).toBeNull();
    expect(within(screen.getAllByRole('row')[1]).getAllByRole('cell')).toHaveLength(6);
  });

  it('reorders stat cards and columns', async () => {
    const { container } = renderPage({
      desktop: { stats: [{ key: 'active' }, { key: 'revoked' }], columns: [{ key: 'platform' }] },
    });
    await screen.findByText('Finance workstation');
    expect(uiIds(container, 'desktop.stats.')).toEqual(['desktop.stats.active', 'desktop.stats.revoked', 'desktop.stats.registered']);
    expect(columnHeaders()[0]).toBe('Platform');
    expect(within(screen.getAllByRole('row')[1]).getAllByRole('cell')[0]).toHaveTextContent('Windows');
  });
});
