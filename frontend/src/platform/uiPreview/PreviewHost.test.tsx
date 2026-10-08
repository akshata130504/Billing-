import type { AxiosRequestConfig } from 'axios';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { apiClient } from '../../services/apiClient';
import type { PageConfigs, PageKey } from '../../appUi/registry';
import type { RenderMessage } from './protocol';

// PreviewHost installs the sample-data adapter at module load; keep the original for other files.
let originalAdapter: AxiosRequestConfig['adapter'];
let PreviewHost: typeof import('./PreviewHost').PreviewHost;
let previewAdapter: typeof import('./sampleData').previewAdapter;

beforeAll(async () => {
  originalAdapter = apiClient.defaults.adapter;
  ({ PreviewHost } = await import('./PreviewHost'));
  ({ previewAdapter } = await import('./sampleData'));
}, 30000);
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});

let postMessage: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  sessionStorage.clear();
  // In jsdom window.parent === window, so the host's messages to its parent land here.
  postMessage = vi.spyOn(window, 'postMessage').mockImplementation(() => undefined);
});

function send(page: PageKey, pages: PageConfigs, opts: { origin?: string; source?: Window | null; selectedId?: string | null } = {}) {
  const data: RenderMessage = { type: 'rb-ui-preview:render', page, pages, selectedId: opts.selectedId ?? null };
  act(() => {
    window.dispatchEvent(new MessageEvent('message', {
      data,
      origin: opts.origin ?? window.location.origin,
      source: opts.source === undefined ? window.parent : opts.source,
    }));
  });
}

const selectCalls = () =>
  postMessage.mock.calls.filter(([m]) => (m as { type?: string }).type === 'rb-ui-preview:select').map(([m, origin]) => [m, origin]);

describe('PreviewHost', { timeout: 20000 }, () => {
  it('installs the read-only preview adapter', async () => {
    expect(apiClient.defaults.adapter).toBe(previewAdapter);
    await expect(apiClient.post('/customers', { display_name: 'x' })).rejects.toMatchObject({ status: 403, code: 'PREVIEW_READ_ONLY' });
    await expect(apiClient.delete('/invoices/1')).rejects.toMatchObject({ status: 403 });
  });

  it('announces itself to the parent and waits for a render message', () => {
    render(<PreviewHost />);
    expect(screen.getByText('Loading preview…')).toBeInTheDocument();
    expect(postMessage).toHaveBeenCalledWith({ type: 'rb-ui-preview:ready' }, window.location.origin);
  });

  it('ignores render messages from another origin or window', () => {
    render(<PreviewHost />);
    send('customers', {}, { origin: 'https://evil.example' });
    expect(screen.getByText('Loading preview…')).toBeInTheDocument();
    send('customers', {}, { source: null });
    expect(screen.getByText('Loading preview…')).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new MessageEvent('message', { data: { type: 'rb-ui-preview:render', page: 'customers' }, origin: window.location.origin, source: window }));
    });
    expect(screen.getByText('Loading preview…')).toBeInTheDocument();
  });

  it('renders the real customers page with sample data and the draft configuration', async () => {
    render(<PreviewHost />);
    send('customers', {
      customers: { header: { title: 'Clients' }, columns: [{ key: 'customer', label: 'Client' }] },
      navigation: { sections: [{ key: 'workspace', items: [{ key: 'customers', label: 'Accounts' }] }] },
    }, { selectedId: 'customers.header' });
    expect(await screen.findByText('Sunrise Foods')).toBeInTheDocument();
    const heading = screen.getByRole('heading', { name: 'Clients' });
    expect(heading).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader')[0]).toHaveTextContent('Client');
    expect(screen.getByRole('link', { name: 'Accounts' })).toBeInTheDocument();
    // The selected component is outlined; others are just marked as selectable.
    const header = heading.closest('[data-ui-id]') as HTMLElement;
    expect(header).toHaveAttribute('data-ui-id', 'customers.header');
    expect(header.style.outline).toContain('2px solid');
  });

  it('reports clicks on configurable components and cancels every interaction', async () => {
    render(<PreviewHost />);
    send('customers', { customers: { header: { title: 'Clients' } } });
    expect(await screen.findByText('Sunrise Foods')).toBeInTheDocument();

    // A click on the heading selects the header group.
    expect(fireEvent.click(screen.getByRole('heading', { name: 'Clients' }))).toBe(false); // default prevented
    expect(selectCalls()).toEqual([[{ type: 'rb-ui-preview:select', id: 'customers.header' }, window.location.origin]]);

    // A sidebar link click selects the item but does not navigate.
    const link = screen.getByRole('link', { name: 'Invoices' });
    expect(fireEvent.click(link)).toBe(false);
    expect(selectCalls().at(-1)![0]).toEqual({ type: 'rb-ui-preview:select', id: 'nav.item.invoices' });

    // A customer row (which normally opens the customer) selects the columns group instead.
    fireEvent.click(screen.getByText('Sunrise Foods'));
    expect(selectCalls().at(-1)![0]).toEqual({ type: 'rb-ui-preview:select', id: 'customers.columns' });

    // Action buttons (here "New Customer", inside the header) only select their component: no navigation.
    const newCustomer = screen.getByRole('button', { name: /New Customer/ });
    expect(fireEvent.click(newCustomer)).toBe(false);
    expect(selectCalls().at(-1)![0]).toEqual({ type: 'rb-ui-preview:select', id: 'customers.header' });
    expect(screen.getByText('Sunrise Foods')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Clients' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('switches page when the editor sends another page', async () => {
    render(<PreviewHost />);
    send('customers', {});
    expect(await screen.findByText('Sunrise Foods')).toBeInTheDocument();
    send('invoices', { invoices: { header: { title: 'Bills' } } });
    expect(await screen.findByRole('heading', { level: 1, name: 'Bills' })).toBeInTheDocument();
    expect(await screen.findByText('INV-1048')).toBeInTheDocument();
    const main = screen.getByRole('main');
    expect(within(main).queryByRole('heading', { name: 'Customers' })).not.toBeInTheDocument();
  });
});
