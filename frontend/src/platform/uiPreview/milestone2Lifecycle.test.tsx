import type { AxiosRequestConfig } from 'axios';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { apiClient } from '../../services/apiClient';
import type { PageConfigs, PageKey } from '../../appUi/registry';
import type { RenderMessage } from './protocol';
import { PreviewHost } from './PreviewHost';
import { PREVIEW_READ_ONLY_MESSAGE, previewAdapter } from './sampleData';

const main = () => within(document.querySelector('main')!);

let originalAdapter: AxiosRequestConfig['adapter'];
let postMessageSpy: ReturnType<typeof vi.spyOn>;

beforeAll(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = previewAdapter;
}, 30000);

afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});

beforeEach(() => {
  sessionStorage.clear();
  postMessageSpy = vi.spyOn(window, 'postMessage').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
});

function sendRender(page: PageKey, pages: PageConfigs = {}, selectedId: string | null = null) {
  const data: RenderMessage = { type: 'rb-ui-preview:render', page, pages, selectedId };
  act(() => {
    window.dispatchEvent(
      new MessageEvent('message', {
        data,
        origin: window.location.origin,
        source: window.parent,
      })
    );
  });
}

async function setupPreview(page: PageKey, pages: PageConfigs = {}) {
  render(<PreviewHost />);
  await screen.findByText('Loading preview…');
  sendRender(page, pages);
}

describe('Milestone 2 Visual Editor & Preview Lifecycle Verification', { timeout: 30000 }, () => {
  it('blocks all mutating operations (POST, PUT, PATCH, DELETE) with 403 PREVIEW_READ_ONLY', async () => {
    await expect(apiClient.post('/catalog', { name: 'New Product' })).rejects.toMatchObject({
      status: 403,
      code: 'PREVIEW_READ_ONLY',
      message: PREVIEW_READ_ONLY_MESSAGE,
    });
    await expect(apiClient.put('/plans-pricing/1', { name: 'Updated Plan' })).rejects.toMatchObject({
      status: 403,
      code: 'PREVIEW_READ_ONLY',
    });
    await expect(apiClient.patch('/subscriptions/1', { status: 'cancelled' })).rejects.toMatchObject({
      status: 403,
      code: 'PREVIEW_READ_ONLY',
    });
    await expect(apiClient.delete('/expenses/1')).rejects.toMatchObject({
      status: 403,
      code: 'PREVIEW_READ_ONLY',
    });
  });

  it('Products (/catalog): renders real component, handles clicks, reflects live draft overrides', async () => {
    await setupPreview('catalog');
    await waitFor(() => expect(document.querySelector('[data-ui-id="catalog.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="catalog.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'catalog.header' },
      window.location.origin
    );

    sendRender('catalog', {
      catalog: { header: { title: 'Custom Catalog Heading' } },
    });
    expect(await main().findByText('Custom Catalog Heading')).toBeInTheDocument();
  });

  it('Plans (/plans-pricing): renders real component and reflects live draft override', async () => {
    await setupPreview('plans_pricing');
    await waitFor(() => expect(document.querySelector('[data-ui-id="plans_pricing.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="plans_pricing.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'plans_pricing.header' },
      window.location.origin
    );

    sendRender('plans_pricing', {
      plans_pricing: { header: { title: 'Tiered Pricing Models' } },
    });
    expect(await main().findByText('Tiered Pricing Models')).toBeInTheDocument();
  });

  it('Subscriptions (/subscriptions): renders real component and reflects live draft override', async () => {
    await setupPreview('subscriptions');
    await waitFor(() => expect(document.querySelector('[data-ui-id="subscriptions.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="subscriptions.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'subscriptions.header' },
      window.location.origin
    );

    sendRender('subscriptions', {
      subscriptions: { header: { title: 'Active Recurring Contracts' } },
    });
    expect(await main().findByText('Active Recurring Contracts')).toBeInTheDocument();
  });

  it('Quotes (/quotes): renders real component and reflects live draft override', async () => {
    await setupPreview('quotes');
    await waitFor(() => expect(document.querySelector('[data-ui-id="quotes.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="quotes.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'quotes.header' },
      window.location.origin
    );

    sendRender('quotes', {
      quotes: { header: { title: 'Customer Price Quotes' } },
    });
    expect(await main().findByText('Customer Price Quotes')).toBeInTheDocument();
  });

  it('CPQ (/cpq): renders real component and reflects live draft override', async () => {
    await setupPreview('cpq');
    await waitFor(() => expect(document.querySelector('[data-ui-id="cpq.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="cpq.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'cpq.header' },
      window.location.origin
    );

    sendRender('cpq', {
      cpq: { header: { title: 'Configure Price Quote Pipeline' } },
    });
    expect(await main().findByText('Configure Price Quote Pipeline')).toBeInTheDocument();
  });

  it('Payments (/payments): renders real component and reflects live draft override', async () => {
    await setupPreview('payments');
    await waitFor(() => expect(document.querySelector('[data-ui-id="payments.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="payments.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'payments.header' },
      window.location.origin
    );

    sendRender('payments', {
      payments: { header: { title: 'Transactions & Collections' } },
    });
    expect(await main().findByText('Transactions & Collections')).toBeInTheDocument();
  });

  it('Reconciliation (/control-center/reconciliation): renders real component and reflects live draft override', async () => {
    await setupPreview('reconciliation');
    await waitFor(() => expect(document.querySelector('[data-ui-id="reconciliation.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="reconciliation.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'reconciliation.header' },
      window.location.origin
    );

    sendRender('reconciliation', {
      reconciliation: { header: { title: 'Bank Settlement Matching' } },
    });
    expect(await main().findByText('Bank Settlement Matching')).toBeInTheDocument();
  });

  it('Credit Notes (/credit-notes): renders real component and reflects live draft override', async () => {
    await setupPreview('credit_notes');
    await waitFor(() => expect(document.querySelector('[data-ui-id="credit_notes.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="credit_notes.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'credit_notes.header' },
      window.location.origin
    );

    sendRender('credit_notes', {
      credit_notes: { header: { title: 'Adjustment & Credit Vouchers' } },
    });
    expect(await main().findByText('Adjustment & Credit Vouchers')).toBeInTheDocument();
  });

  it('Dunning (/dunning): renders real component and reflects live draft override', async () => {
    await setupPreview('dunning');
    await waitFor(() => expect(document.querySelector('[data-ui-id="dunning.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="dunning.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'dunning.header' },
      window.location.origin
    );

    sendRender('dunning', {
      dunning: { header: { title: 'Automated Dunning Rules' } },
    });
    expect(await main().findByText('Automated Dunning Rules')).toBeInTheDocument();
  });

  it('Collections (/collections): renders real component and reflects live draft override', async () => {
    await setupPreview('collections');
    await waitFor(() => expect(document.querySelector('[data-ui-id="collections.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="collections.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'collections.header' },
      window.location.origin
    );

    sendRender('collections', {
      collections: { header: { title: 'Accounts Receivable Tracking' } },
    });
    expect(await main().findByText('Accounts Receivable Tracking')).toBeInTheDocument();
  });

  it('Expenses (/expenses): renders real component and reflects live draft override', async () => {
    await setupPreview('expenses');
    await waitFor(() => expect(document.querySelector('[data-ui-id="expenses.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="expenses.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'expenses.header' },
      window.location.origin
    );

    sendRender('expenses', {
      expenses: { header: { title: 'Operational Expenditures' } },
    });
    expect(await main().findByText('Operational Expenditures')).toBeInTheDocument();
  });

  it('Projects (/projects): renders real component and reflects live draft override', async () => {
    await setupPreview('projects');
    await waitFor(() => expect(document.querySelector('[data-ui-id="projects.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="projects.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'projects.header' },
      window.location.origin
    );

    sendRender('projects', {
      projects: { header: { title: 'Client Engagements' } },
    });
    expect(await main().findByText('Client Engagements')).toBeInTheDocument();
  });

  it('Timesheets (/timesheets): renders real component and reflects live draft override', async () => {
    await setupPreview('timesheets');
    await waitFor(() => expect(document.querySelector('[data-ui-id="timesheets.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="timesheets.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'timesheets.header' },
      window.location.origin
    );

    sendRender('timesheets', {
      timesheets: { header: { title: 'Logged Work Hours' } },
    });
    expect(await main().findByText('Logged Work Hours')).toBeInTheDocument();
  });

  it('Reports (/reports): renders real component and reflects live draft override', async () => {
    await setupPreview('reports');
    await waitFor(() => expect(document.querySelector('[data-ui-id="reports.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="reports.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'reports.header' },
      window.location.origin
    );

    sendRender('reports', {
      reports: { header: { title: 'Executive Intelligence & Reports' } },
    });
    expect(await main().findByText('Executive Intelligence & Reports')).toBeInTheDocument();
  });

  it('Customization (/customization): renders real component and reflects live draft override', async () => {
    await setupPreview('customization');
    await waitFor(() => expect(document.querySelector('[data-ui-id="customization.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="customization.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'customization.header' },
      window.location.origin
    );

    sendRender('customization', {
      customization: { header: { title: 'Document Branding & Series' } },
    });
    expect(await main().findByText('Document Branding & Series')).toBeInTheDocument();
  });

  it('Automation (/automation): renders real component and reflects live draft override', async () => {
    await setupPreview('automation');
    await waitFor(() => expect(document.querySelector('[data-ui-id="automation.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="automation.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'automation.header' },
      window.location.origin
    );

    sendRender('automation', {
      automation: { header: { title: 'Event Triggers & Automations' } },
    });
    expect(await main().findByText('Event Triggers & Automations')).toBeInTheDocument();
  });

  it('Settings (/settings): renders real component and reflects live draft override', async () => {
    await setupPreview('settings');
    await waitFor(() => expect(document.querySelector('[data-ui-id="settings.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="settings.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'settings.header' },
      window.location.origin
    );

    sendRender('settings', {
      settings: { header: { title: 'Tenant System Preferences' } },
    });
    expect(await main().findByText('Tenant System Preferences')).toBeInTheDocument();
  });

  it('Integrations (/settings?tab=integrations): renders real component and reflects live draft override', async () => {
    await setupPreview('integrations');
    await waitFor(() => expect(document.querySelector('[data-ui-id="integrations.header"]')).toBeInTheDocument());

    const header = document.querySelector('[data-ui-id="integrations.header"]');
    fireEvent.click(header!);
    expect(postMessageSpy).toHaveBeenCalledWith(
      { type: 'rb-ui-preview:select', id: 'integrations.header' },
      window.location.origin
    );

    sendRender('integrations', {
      integrations: { header: { title: 'Connected Third-Party APIs' } },
    });
    expect(await main().findByText('Connected Third-Party APIs')).toBeInTheDocument();
  });
});
