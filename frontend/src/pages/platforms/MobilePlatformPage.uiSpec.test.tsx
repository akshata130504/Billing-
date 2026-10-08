/**
 * Platforms > Mobile honours its own visual-editor spec (appUi/specs/mobile.json) and renders
 * exactly its built-in UI without configuration. Rendered against the preview sample-data adapter.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, screen, within } from '@testing-library/react';
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from '../../services/apiClient';
import { previewAdapter } from '../../platform/uiPreview/sampleData';
import { MobilePlatformPage } from './MobilePlatformPage';
import { columnHeaders, renderPlatformPage, uiIds } from './platformUiSpecTestUtils';

const renderPage = (pages?: Parameters<typeof renderPlatformPage>[2]) =>
  renderPlatformPage(<MobilePlatformPage />, '/platforms/mobile', pages);

let originalAdapter: AxiosRequestConfig['adapter'];
beforeEach(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = previewAdapter;
});
afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
});

describe('MobilePlatformPage visual-editor spec', { timeout: 20000 }, () => {
  it('renders the built-in UI without configuration', async () => {
    const { container } = renderPage();
    expect(await screen.findByText("Asha's iPhone")).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Mobile');
    expect(screen.getByText(/^iOS and Android companion clients/)).toBeInTheDocument();
    expect(screen.getAllByText('Registered devices')).toHaveLength(2); // stat card + section title
    expect(screen.getByText('iOS · Android')).toBeInTheDocument();
    expect(screen.getByText('Active (30 days)')).toBeInTheDocument();
    expect(screen.getByText('3 of 3 · your devices in this organization')).toBeInTheDocument();
    expect(screen.getByText('Native sign-in flow')).toBeInTheDocument();
    expect(columnHeaders()).toEqual(['Device', 'Platform', 'App version', 'Last seen', 'Registered', 'Status', 'Actions']);
    // Desktop devices are not listed on the mobile page.
    expect(screen.queryByText('Finance workstation')).toBeNull();
    expect(container.querySelector('[data-ui-id]')).toBeNull();
  });

  it('relabels the header, a stat card (caption with {platforms}) and a column', async () => {
    renderPage({
      mobile: {
        header: { title: 'Phones & tablets', eyebrow: 'Apps' },
        stats: [{ key: 'registered', label: 'Enrolled', caption: 'On {platforms}' }],
        columns: [{ key: 'app_version', label: 'Build' }],
        connection: { sign_in_title: 'How apps sign in' },
      },
    });
    await screen.findByText("Asha's iPhone");
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Phones & tablets');
    expect(screen.getByText('Apps')).toBeInTheDocument();
    expect(screen.getByText('Enrolled')).toBeInTheDocument();
    expect(screen.getByText('On iOS · Android')).toBeInTheDocument();
    expect(columnHeaders()).toContain('Build');
    expect(screen.getByText('How apps sign in')).toBeInTheDocument();
  });

  it('hides a stat card and a column (header and cells)', async () => {
    renderPage({ mobile: { stats: [{ key: 'revoked', hidden: true }], columns: [{ key: 'registered', hidden: true }] } });
    await screen.findByText("Asha's iPhone");
    expect(screen.queryByText('Records kept for audit; identifiers cannot be re-used')).toBeNull();
    expect(columnHeaders()).not.toContain('Registered');
    expect(within(screen.getAllByRole('row')[1]).getAllByRole('cell')).toHaveLength(6);
  });

  it('reorders stat cards, and columns with their body cells', async () => {
    const { container } = renderPage({
      mobile: { stats: [{ key: 'revoked' }], columns: [{ key: 'status' }, { key: 'device' }] },
    });
    await screen.findByText("Asha's iPhone");
    expect(uiIds(container, 'mobile.stats.')).toEqual(['mobile.stats.revoked', 'mobile.stats.registered', 'mobile.stats.active']);
    expect(columnHeaders().slice(0, 3)).toEqual(['Status', 'Device', 'Platform']);
    const cells = within(screen.getAllByRole('row')[1]).getAllByRole('cell');
    expect(cells[0]).toHaveTextContent('Trusted');
    expect(cells[1]).toHaveTextContent("Asha's iPhone");
  });
});
