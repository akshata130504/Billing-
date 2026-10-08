import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';
import { UiConfigOverride, UiConfigProvider, applyTheme, usePageUi, useUiEditable } from './UiConfigContext';

const VARS = ['--brand-500', '--brand-600', '--brand-700', '--sidebar-bg', '--sidebar-active'];

function clearVars() {
  for (const v of VARS) document.documentElement.style.removeProperty(v);
}

beforeEach(clearVars);
afterEach(clearVars);

describe('applyTheme', () => {
  it('sets valid #RRGGBB colours as CSS variables', () => {
    applyTheme({ brand_600: '#112233', sidebar_background: '#abcdef', sidebar_active: '#ABCDEF' });
    const style = document.documentElement.style;
    expect(style.getPropertyValue('--brand-600')).toBe('#112233');
    expect(style.getPropertyValue('--sidebar-bg')).toBe('#abcdef');
    expect(style.getPropertyValue('--sidebar-active')).toBe('#ABCDEF');
    expect(style.getPropertyValue('--brand-500')).toBe('');
  });

  it('removes variables that are no longer configured', () => {
    applyTheme({ brand_600: '#112233' });
    applyTheme(undefined);
    expect(document.documentElement.style.getPropertyValue('--brand-600')).toBe('');
    applyTheme({ brand_700: '#010203' });
    applyTheme({});
    expect(document.documentElement.style.getPropertyValue('--brand-700')).toBe('');
  });

  it('ignores invalid values', () => {
    applyTheme({
      brand_500: 'red',
      brand_600: 'url(x)',
      brand_700: '#123',
      sidebar_background: '#1234567',
      sidebar_active: '#11223g; background: url(x)',
    });
    for (const v of VARS) expect(document.documentElement.style.getPropertyValue(v)).toBe('');
  });

  it('applies to a given root element', () => {
    const el = document.createElement('div');
    applyTheme({ brand_500: '#000000' }, el);
    expect(el.style.getPropertyValue('--brand-500')).toBe('#000000');
    expect(document.documentElement.style.getPropertyValue('--brand-500')).toBe('');
  });
});

function Probe() {
  const customers = usePageUi('customers');
  const invoices = usePageUi('invoices');
  return (
    <div>
      <span data-testid="title">{customers.header?.title ?? 'default'}</span>
      <span data-testid="invoices">{JSON.stringify(invoices)}</span>
    </div>
  );
}

describe('UiConfigProvider', () => {
  it('fetches /ui-config and exposes it to children, applying the theme', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        pages: { customers: { header: { title: 'Clients' } }, theme: { brand_600: '#445566' } },
        versions: {},
        etag: 'e1',
      },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <UiConfigProvider>
          <Probe />
        </UiConfigProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId('title')).toHaveTextContent('default');
    expect(await screen.findByText('Clients')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/ui-config');
    expect(screen.getByTestId('invoices')).toHaveTextContent('{}');
    await waitFor(() => expect(document.documentElement.style.getPropertyValue('--brand-600')).toBe('#445566'));
  });

  it('keeps the defaults when the request fails', async () => {
    const get = vi.spyOn(apiClient, 'get').mockRejectedValue(new Error('offline'));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <UiConfigProvider>
          <Probe />
        </UiConfigProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2), { timeout: 4000 }); // provider retries once
    expect(screen.getByTestId('title')).toHaveTextContent('default');
  });

  it('usePageUi outside any provider returns no overrides', () => {
    render(<Probe />);
    expect(screen.getByTestId('title')).toHaveTextContent('default');
  });
});

function Editable({ id }: { id: string }) {
  const editable = useUiEditable();
  return <div data-testid={id} {...editable(id)}>x</div>;
}

describe('useUiEditable', () => {
  it('returns no props outside the editor override', () => {
    render(<Editable id="customers.header" />);
    const el = screen.getByTestId('customers.header');
    expect(el).not.toHaveAttribute('data-ui-id');
    expect(el.getAttribute('style')).toBeNull();
  });

  it('returns no props inside an override without a selection API', () => {
    render(
      <UiConfigOverride pages={{}}>
        <Editable id="customers.header" />
      </UiConfigOverride>,
    );
    expect(screen.getByTestId('customers.header')).not.toHaveAttribute('data-ui-id');
  });

  it('marks elements and outlines the selected one inside the override', () => {
    const selection = { selectedId: 'customers.header', select: vi.fn() };
    render(
      <UiConfigOverride pages={{ theme: { sidebar_active: '#101010' } }} selection={selection}>
        <Editable id="customers.header" />
        <Editable id="customers.stat.total" />
      </UiConfigOverride>,
    );
    const selected = screen.getByTestId('customers.header');
    const other = screen.getByTestId('customers.stat.total');
    expect(selected).toHaveAttribute('data-ui-id', 'customers.header');
    expect(selected.style.outline).toContain('2px solid');
    expect(other).toHaveAttribute('data-ui-id', 'customers.stat.total');
    expect(other.style.outline).toBe('');
    expect(other.style.cursor).toBe('pointer');
    expect(document.documentElement.style.getPropertyValue('--sidebar-active')).toBe('#101010');
  });
});
