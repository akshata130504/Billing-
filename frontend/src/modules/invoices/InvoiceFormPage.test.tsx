import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InvoiceFormPage } from './InvoiceFormPage';
import { planPricingService } from '../../services/planPricingService';
import { catalogCpqService } from '../../services/catalogCpqService';
import { invoiceService } from '../../services/invoiceService';
import { quoteService } from '../../services/quoteService';

const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }));

vi.mock('../../services/planPricingService', () => ({
  planPricingService: {
    getPlans: vi.fn(),
    calculatePrice: vi.fn(),
  },
}));

vi.mock('../../services/catalogCpqService', () => ({
  catalogCpqService: {
    listOfferings: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    getOffering: vi.fn(),
  },
}));

vi.mock('../../components/common/CustomerCombobox', () => ({
  CustomerCombobox: ({ onChange }: { onChange: (id: string) => void }) => (
    <button type="button" onClick={() => onChange('cust-1')}>
      pick-customer
    </button>
  ),
}));

vi.mock('../../services/customerService', () => ({
  customerService: {
    list: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    get: vi.fn(),
    create: vi.fn(),
  },
}));

vi.mock('../../services/invoiceService', () => ({
  invoiceService: {
    getInvoice: vi.fn(),
    createInvoice: vi.fn(),
    updateInvoice: vi.fn(),
    sendInvoice: vi.fn(),
  },
}));

vi.mock('../../services/quoteService', () => ({
  quoteService: {
    getSupplyPreview: vi.fn(),
  },
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast }),
}));

const mockedPricing = vi.mocked(planPricingService);

function plan(id: string, pricing_model: string, base_price: number) {
  return {
    id,
    name: `Plan ${id}`,
    description: `Plan ${id} description`,
    pricing_model,
    base_price,
    tax_rate_pct: 18,
  } as any;
}

function priceResponse(unit_rate: number, pricing_model = 'tiered') {
  return {
    unit_rate,
    pricing_model,
    pricing_explanation: `rate ${unit_rate}`,
    subtotal: 0,
    total_amount: 0,
  };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <InvoiceFormPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const qtyInput = () => document.querySelector('input[type="number"][min="1"]') as HTMLInputElement;
const rateInput = () => document.querySelector('input[type="number"][step="0.01"][min="0"]') as HTMLInputElement;
const lineAmount = () => (screen.getByText('Amount', { selector: 'span' }).nextElementSibling as HTMLElement).textContent;
const planSelect = () => screen.getAllByRole('combobox').find((el) => el.tagName === 'SELECT' && (el as HTMLSelectElement).options[0]?.text.startsWith('-- Choose')) as HTMLSelectElement;

async function selectPlan(id: string) {
  await waitFor(() => expect(screen.getByText(`Plan: Plan ${id}`, { exact: false })).toBeInTheDocument());
  await act(async () => {
    fireEvent.change(planSelect(), { target: { value: `plan:${id}` } });
  });
}

describe('<InvoiceFormPage /> line item quantity editing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps the rate and recomputes the amount when quantity changes on a flat plan', async () => {
    mockedPricing.getPlans.mockResolvedValue({ items: [plan('p1', 'flat', 100)], total: 1 } as any);
    mockedPricing.calculatePrice.mockResolvedValue(priceResponse(100, 'flat'));
    renderPage();
    await selectPlan('p1');
    await waitFor(() => expect(rateInput().value).toBe('100'));

    await act(async () => {
      fireEvent.change(qtyInput(), { target: { value: '3' } });
    });

    expect(qtyInput().value).toBe('3');
    expect(rateInput().value).toBe('100');
    // 3 x 100 x 1.18 (18% tax)
    expect(lineAmount()).toContain('354');
    // 'flat' (lowercase, as sent by the backend) must not trigger re-pricing.
    expect(mockedPricing.calculatePrice).toHaveBeenCalledTimes(1);
  });

  it('applies tiered pricing for the latest quantity and ignores stale responses', async () => {
    mockedPricing.getPlans.mockResolvedValue({ items: [plan('p2', 'tiered', 100)], total: 1 } as any);
    mockedPricing.calculatePrice.mockResolvedValueOnce(priceResponse(100));
    renderPage();
    await selectPlan('p2');
    await waitFor(() => expect(rateInput().value).toBe('100'));

    const forFive = deferred<ReturnType<typeof priceResponse>>();
    const forTen = deferred<ReturnType<typeof priceResponse>>();
    mockedPricing.calculatePrice.mockReturnValueOnce(forFive.promise).mockReturnValueOnce(forTen.promise);

    await act(async () => {
      fireEvent.change(qtyInput(), { target: { value: '5' } });
    });
    await act(async () => {
      fireEvent.change(qtyInput(), { target: { value: '10' } });
    });
    expect(qtyInput().value).toBe('10');

    await act(async () => {
      forTen.resolve(priceResponse(80));
    });
    await act(async () => {
      forFive.resolve(priceResponse(90)); // stale: priced for qty 5
    });

    expect(qtyInput().value).toBe('10');
    expect(rateInput().value).toBe('80');
    // 10 x 80 x 1.18
    expect(lineAmount()).toContain('944');
  });

  it('never blanks the rate when the pricing call fails', async () => {
    mockedPricing.getPlans.mockResolvedValue({ items: [plan('p3', 'tiered', 50)], total: 1 } as any);
    mockedPricing.calculatePrice.mockResolvedValueOnce(priceResponse(50));
    renderPage();
    await selectPlan('p3');
    await waitFor(() => expect(rateInput().value).toBe('50'));

    mockedPricing.calculatePrice.mockRejectedValueOnce(new Error('boom'));
    await act(async () => {
      fireEvent.change(qtyInput(), { target: { value: '4' } });
    });

    expect(qtyInput().value).toBe('4');
    expect(rateInput().value).toBe('50');
  });

  it('keeps a typed rate when the quantity of a tiered line changes (BUG-13)', async () => {
    mockedPricing.getPlans.mockResolvedValue({ items: [plan('p4', 'tiered', 100)], total: 1 } as any);
    mockedPricing.calculatePrice.mockResolvedValue(priceResponse(100));
    renderPage();
    await selectPlan('p4');
    await waitFor(() => expect(rateInput().value).toBe('100'));

    await act(async () => {
      fireEvent.change(rateInput(), { target: { value: '75.5' } });
    });
    mockedPricing.calculatePrice.mockResolvedValue(priceResponse(80));
    await act(async () => {
      fireEvent.change(qtyInput(), { target: { value: '10' } });
    });

    expect(qtyInput().value).toBe('10');
    expect(rateInput().value).toBe('75.5');
    expect(mockedPricing.calculatePrice).toHaveBeenCalledTimes(1);
  });

  it('starts an added line as a blank custom item', async () => {
    mockedPricing.getPlans.mockResolvedValue({ items: [plan('p5', 'flat', 100)], total: 1 } as any);
    mockedPricing.calculatePrice.mockResolvedValue(priceResponse(100, 'flat'));
    renderPage();
    await selectPlan('p5');
    await waitFor(() => expect(rateInput().value).toBe('100'));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Add (Another )?(Line|Item|Row)/i }));
    });
    const selects = screen
      .getAllByRole('combobox')
      .filter((el) => el.tagName === 'SELECT' && (el as HTMLSelectElement).options[0]?.text.startsWith('-- Choose')) as HTMLSelectElement[];
    expect(selects).toHaveLength(2);
    expect(selects[1].value).toBe('');
  });
});

describe('<InvoiceFormPage /> line item selection switching', () => {
  const offering = {
    id: 'o1',
    name: 'Product o1',
    description: 'Product o1 description',
    sku: 'SKU-O1',
    type: 'product',
    base_price: 250,
    tax_rate_pct: 12,
    pricing_model: 'flat',
    pricing_tiers: [],
  };
  const planA = { ...plan('pA', 'tiered', 100), tax_rate_pct: 5 };
  const planB = { ...plan('pB', 'tiered', 200), tax_rate_pct: 28 };

  const nameInput = () => screen.getByPlaceholderText(/Item Name/) as HTMLInputElement;
  const descInput = () => screen.getByPlaceholderText(/Description \/ notes/) as HTMLInputElement;
  const taxSelect = () =>
    screen.getAllByRole('combobox').find((el) => (el as HTMLSelectElement).options[0]?.text === '0%') as HTMLSelectElement;
  const choose = async (value: string) => {
    await act(async () => {
      fireEvent.change(planSelect(), { target: { value } });
    });
  };
  const save = async () => {
    fireEvent.click(screen.getByText('pick-customer'));
    await act(async () => {
      fireEvent.click(screen.getByText('Save as Draft'));
    });
  };
  const lastItems = () => {
    const calls = vi.mocked(invoiceService.createInvoice).mock.calls;
    expect(calls).toHaveLength(1);
    return (calls[0][0] as any).items as any[];
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockedPricing.getPlans.mockResolvedValue({ items: [planA, planB], total: 2 } as any);
    vi.mocked(catalogCpqService.listOfferings).mockResolvedValue({ items: [offering], total: 1 } as any);
    mockedPricing.calculatePrice.mockReset();
    mockedPricing.calculatePrice.mockImplementation((async ({ plan_id }: any) =>
      priceResponse(plan_id === 'pA' ? 100 : 200)) as any);
    vi.mocked(invoiceService.createInvoice).mockResolvedValue({ id: 'inv-1' } as any);
  });

  it('Plan A -> Plan B shows only B and submits only B', async () => {
    renderPage();
    await selectPlan('pA');
    await waitFor(() => expect(rateInput().value).toBe('100'));
    expect(taxSelect().value).toBe('5');
    await choose('plan:pB');
    await waitFor(() => expect(rateInput().value).toBe('200'));

    expect(nameInput().value).toBe('Plan pB');
    expect(descInput().value).toBe('Plan pB description');
    expect(taxSelect().value).toBe('28');
    expect(screen.getByText('rate 200')).toBeInTheDocument();
    expect(screen.queryByText('rate 100')).not.toBeInTheDocument();
    expect(planSelect().value).toBe('plan:pB');

    await save();
    expect(lastItems()).toEqual([
      {
        offering_id: 'pB',
        plan_id: undefined,
        description: 'Plan pB description',
        quantity: 1,
        unit_price: 200,
        tax_rate_pct: 28,
        pricing_explanation: 'rate 200',
      },
    ]);
  });

  it('Plan A -> Select clears everything and keeps quantity', async () => {
    renderPage();
    await selectPlan('pA');
    await waitFor(() => expect(rateInput().value).toBe('100'));
    await act(async () => {
      fireEvent.change(qtyInput(), { target: { value: '4' } });
    });
    await choose('');

    expect(nameInput().value).toBe('');
    expect(descInput().value).toBe('');
    expect(rateInput().value).toBe('0');
    expect(taxSelect().value).toBe('18');
    expect(qtyInput().value).toBe('4');
    expect(planSelect().value).toBe('');
    expect(screen.queryByText(/^rate /)).not.toBeInTheDocument();

    fireEvent.change(nameInput(), { target: { value: 'Consulting' } });
    await save();
    expect(lastItems()).toEqual([
      {
        offering_id: undefined,
        plan_id: undefined,
        description: 'Consulting',
        quantity: 4,
        unit_price: 0,
        tax_rate_pct: 18,
        pricing_explanation: undefined,
      },
    ]);
  });

  it('Plan A -> Plan B -> Plan A restores A only', async () => {
    renderPage();
    await selectPlan('pA');
    await waitFor(() => expect(rateInput().value).toBe('100'));
    await choose('plan:pB');
    await waitFor(() => expect(rateInput().value).toBe('200'));
    await choose('plan:pA');
    await waitFor(() => expect(rateInput().value).toBe('100'));

    expect(nameInput().value).toBe('Plan pA');
    expect(taxSelect().value).toBe('5');
    expect(screen.getByText('rate 100')).toBeInTheDocument();
    await save();
    expect(lastItems()[0]).toMatchObject({ offering_id: 'pA', unit_price: 100, tax_rate_pct: 5, pricing_explanation: 'rate 100' });
    expect(lastItems()[0].plan_id).toBeUndefined();
  });

  it('Plan -> Product (offering) uses only the offering data and ids', async () => {
    renderPage();
    await selectPlan('pA');
    await waitFor(() => expect(rateInput().value).toBe('100'));
    await choose('offering:o1');

    expect(nameInput().value).toBe('Product o1');
    expect(descInput().value).toBe('Product o1 description');
    expect(rateInput().value).toBe('250');
    expect(taxSelect().value).toBe('12');
    expect(planSelect().value).toBe('offering:o1');
    expect(screen.queryByText('rate 100')).not.toBeInTheDocument();

    await save();
    expect(lastItems()).toEqual([
      {
        offering_id: 'o1',
        plan_id: undefined,
        description: 'Product o1 description',
        quantity: 1,
        unit_price: 250,
        tax_rate_pct: 12,
        pricing_explanation: 'Base Catalog Price',
      },
    ]);
  });

  it('Plan -> Custom then typing custom text and rate submits the custom data only', async () => {
    renderPage();
    await selectPlan('pA');
    await waitFor(() => expect(rateInput().value).toBe('100'));
    await choose('');
    fireEvent.change(nameInput(), { target: { value: 'Custom work' } });
    fireEvent.change(descInput(), { target: { value: 'two days' } });
    fireEvent.change(rateInput(), { target: { value: '75' } });

    await save();
    expect(lastItems()).toEqual([
      {
        offering_id: undefined,
        plan_id: undefined,
        description: 'Custom work - two days',
        quantity: 1,
        unit_price: 75,
        tax_rate_pct: 18,
        pricing_explanation: undefined,
      },
    ]);
  });

  it('quantity and tax edits after switching apply to the current selection', async () => {
    renderPage();
    await selectPlan('pA');
    await waitFor(() => expect(rateInput().value).toBe('100'));
    await choose('plan:pB');
    await waitFor(() => expect(rateInput().value).toBe('200'));
    await act(async () => {
      fireEvent.change(qtyInput(), { target: { value: '3' } });
    });
    await waitFor(() => expect(rateInput().value).toBe('200'));
    await act(async () => {
      fireEvent.change(taxSelect(), { target: { value: '12' } });
    });

    await save();
    expect(lastItems()).toEqual([
      {
        offering_id: 'pB',
        plan_id: undefined,
        description: 'Plan pB description',
        quantity: 3,
        unit_price: 200,
        tax_rate_pct: 12,
        pricing_explanation: 'rate 200',
      },
    ]);
  });

  it('ignores a late pricing response for A after switching to B', async () => {
    const late = deferred<ReturnType<typeof priceResponse>>();
    mockedPricing.calculatePrice.mockReset();
    mockedPricing.calculatePrice.mockReturnValueOnce(late.promise as any);
    mockedPricing.calculatePrice.mockResolvedValueOnce(priceResponse(200));
    renderPage();
    await selectPlan('pA');
    await choose('plan:pB');
    await waitFor(() => expect(rateInput().value).toBe('200'));

    await act(async () => {
      late.resolve(priceResponse(999));
    });

    expect(rateInput().value).toBe('200');
    expect(nameInput().value).toBe('Plan pB');
    expect(screen.queryByText('rate 999')).not.toBeInTheDocument();
  });

  it('ignores a late pricing response for A after switching to Select', async () => {
    const late = deferred<ReturnType<typeof priceResponse>>();
    mockedPricing.calculatePrice.mockReset();
    mockedPricing.calculatePrice.mockReturnValueOnce(late.promise as any);
    renderPage();
    await selectPlan('pA');
    await choose('');

    await act(async () => {
      late.resolve(priceResponse(999));
    });

    expect(rateInput().value).toBe('0');
    expect(nameInput().value).toBe('');
    expect(screen.queryByText('rate 999')).not.toBeInTheDocument();
  });

  it('ignores a late response for A after A -> Select -> A (same id, new selection)', async () => {
    const late = deferred<ReturnType<typeof priceResponse>>();
    mockedPricing.calculatePrice.mockReset();
    mockedPricing.calculatePrice.mockReturnValueOnce(late.promise as any);
    mockedPricing.calculatePrice.mockResolvedValueOnce(priceResponse(100));
    renderPage();
    await selectPlan('pA');
    await choose('');
    await choose('plan:pA');
    await waitFor(() => expect(rateInput().value).toBe('100'));
    await act(async () => {
      late.resolve(priceResponse(999));
    });
    expect(rateInput().value).toBe('100');
  });
});

// --- Archived offerings ------------------------------------------------------------------------------

describe('<InvoiceFormPage /> archived offerings', () => {
  const ACTIVE_CAT = {
    id: 'c1',
    name: 'Product C1',
    description: 'Product C1 description',
    sku: 'C1',
    type: 'product',
    base_price: '200.00',
    tax_rate_pct: '18.00',
    pricing_model: 'per_unit',
    pricing_tiers: null,
    is_active: true,
  };
  const ACTIVE_CAT_2 = { ...ACTIVE_CAT, id: 'c2', name: 'Product C2', description: 'Product C2 description', sku: 'C2' };
  const ARCHIVED = { ...ACTIVE_CAT, id: 'off-archived', name: 'Old Product', description: 'Old Product description', sku: 'OLD', is_active: false };

  const storedInvoice = () => ({
    id: 'inv1',
    invoice_number: 'INV-1',
    customer_id: 'cust-1',
    issue_date: '2026-10-01',
    due_date: '2026-10-31',
    items: [
      { id: 'line-archived', offering_id: 'off-archived', description: 'Old Product', quantity: '2', unit_price: '300.00', tax_rate_pct: '18', pricing_model: 'tiered' },
      { id: 'line-active', offering_id: 'c1', description: 'Product C1', quantity: '1', unit_price: '200.00', tax_rate_pct: '18' },
    ],
  });

  function renderRoute(path: string) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/invoices/new" element={<InvoiceFormPage />} />
            <Route path="/invoices/:id/edit" element={<InvoiceFormPage />} />
            <Route path="*" element={<div>elsewhere</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  const lineSelects = () =>
    screen
      .getAllByRole('combobox')
      .filter((el) => el.tagName === 'SELECT' && (el as HTMLSelectElement).options[0]?.text.startsWith('-- Choose')) as HTMLSelectElement[];
  const quantityInputs = () => Array.from(document.querySelectorAll('input[type="number"][min="1"]')) as HTMLInputElement[];
  type SavedLine = { id?: string; offering_id?: string; quantity?: number };
  const savedLines = (mock: unknown, payloadArg = 1): SavedLine[] =>
    (mock as { mock: { calls: Array<Array<{ items: SavedLine[] }>> } }).mock.calls[0][payloadArg].items;
  const saveDraft = async () => {
    await act(async () => {
      fireEvent.click(screen.getByText('Save as Draft'));
    });
  };

  beforeEach(() => {
    vi.resetAllMocks();
    mockedPricing.getPlans.mockResolvedValue({ items: [plan('p1', 'flat', 100)], total: 1 } as any);
    vi.mocked(catalogCpqService.listOfferings).mockResolvedValue({ items: [ACTIVE_CAT, ACTIVE_CAT_2], total: 2 } as any);
    vi.mocked(catalogCpqService.getOffering).mockResolvedValue(ARCHIVED as any);
    vi.mocked(invoiceService.getInvoice).mockResolvedValue(storedInvoice() as any);
    vi.mocked(invoiceService.updateInvoice).mockResolvedValue({ id: 'inv1' } as any);
    vi.mocked(invoiceService.createInvoice).mockResolvedValue({ id: 'inv2' } as any);
    mockedPricing.calculatePrice.mockResolvedValue(priceResponse(100, 'flat') as any);
  });

  it('requests only active offerings for the pickers', async () => {
    renderRoute('/invoices/new');
    await waitFor(() => expect(lineSelects().length).toBe(1));
    expect(mockedPricing.getPlans).toHaveBeenCalledWith(expect.objectContaining({ is_active: true }));
    expect(catalogCpqService.listOfferings).toHaveBeenCalledWith(expect.objectContaining({ is_active: true }));
    const options = within(lineSelects()[0]).getAllByRole('option').map((o) => o.textContent);
    expect(options.some((t) => t?.includes('Product C1'))).toBe(true);
    expect(options.some((t) => t?.includes('Old Product'))).toBe(false);
  });

  it('keeps an archived line of an existing invoice visible as a disabled "(Archived)" option', async () => {
    renderRoute('/invoices/inv1/edit');
    await waitFor(() => expect(lineSelects().length).toBe(2));
    expect(catalogCpqService.getOffering).toHaveBeenCalledWith('off-archived');
    const archivedSelect = lineSelects()[0];
    expect(archivedSelect.value).toBe('offering:off-archived');
    const option = within(archivedSelect).getByRole('option', { name: /Old Product.*\(Archived\)/ }) as HTMLOptionElement;
    expect(option.disabled).toBe(true);
    // It is not offered to the other line, nor to a newly added one.
    expect(within(lineSelects()[1]).queryByText(/Old Product/)).toBeNull();
    fireEvent.click(screen.getByText('Add Line Item'));
    await waitFor(() => expect(lineSelects().length).toBe(3));
    expect(within(lineSelects()[2]).queryByText(/Old Product/)).toBeNull();
  });

  it('does not silently replace an archived line with a custom item', async () => {
    renderRoute('/invoices/inv1/edit');
    await waitFor(() => expect(lineSelects().length).toBe(2));
    expect((screen.getAllByPlaceholderText(/Item Name/)[0] as HTMLInputElement).value).toBe('Old Product');
    expect(lineSelects()[0].value).not.toBe('');
  });

  it('sends the stored id of retained lines when updating', async () => {
    renderRoute('/invoices/inv1/edit');
    await waitFor(() => expect(lineSelects().length).toBe(2));
    await saveDraft();
    await waitFor(() => expect(invoiceService.updateInvoice).toHaveBeenCalled());
    expect(vi.mocked(invoiceService.updateInvoice).mock.calls[0][0]).toBe('inv1');
    const lines = savedLines(invoiceService.updateInvoice);
    expect(lines[0]).toEqual(expect.objectContaining({ id: 'line-archived', offering_id: 'off-archived' }));
    expect(lines[1]).toEqual(expect.objectContaining({ id: 'line-active', offering_id: 'c1' }));
  });

  it('keeps the id and the stored rate when only the quantity of an archived line is edited', async () => {
    renderRoute('/invoices/inv1/edit');
    await waitFor(() => expect(lineSelects().length).toBe(2));
    fireEvent.change(quantityInputs()[0], { target: { value: '5' } });
    await waitFor(() => expect(quantityInputs()[0].value).toBe('5'));
    // The stored line is "tiered": without the guard this would ask the pricing engine again.
    expect(mockedPricing.calculatePrice).not.toHaveBeenCalled();
    await saveDraft();
    await waitFor(() => expect(invoiceService.updateInvoice).toHaveBeenCalled());
    expect(savedLines(invoiceService.updateInvoice)[0]).toEqual(
      expect.objectContaining({ id: 'line-archived', offering_id: 'off-archived', quantity: 5, unit_price: 300 })
    );
  });

  it('does not send an id for a newly added line', async () => {
    renderRoute('/invoices/inv1/edit');
    await waitFor(() => expect(lineSelects().length).toBe(2));
    fireEvent.click(screen.getByText('Add Line Item'));
    await waitFor(() => expect(lineSelects().length).toBe(3));
    fireEvent.change(screen.getAllByPlaceholderText(/Item Name/)[2], { target: { value: 'Custom thing' } });
    await saveDraft();
    await waitFor(() => expect(invoiceService.updateInvoice).toHaveBeenCalled());
    const lines = savedLines(invoiceService.updateInvoice);
    expect(lines).toHaveLength(3);
    expect(lines[2].id).toBeUndefined();
  });

  it('never sends line ids when creating an invoice', async () => {
    renderRoute('/invoices/new');
    await waitFor(() => expect(lineSelects().length).toBe(1));
    await act(async () => {
      fireEvent.change(lineSelects()[0], { target: { value: 'offering:c1' } });
    });
    fireEvent.click(screen.getByText('pick-customer'));
    await saveDraft();
    await waitFor(() => expect(invoiceService.createInvoice).toHaveBeenCalled());
    const lines = savedLines(invoiceService.createInvoice, 0);
    expect(lines[0].offering_id).toBe('c1');
    expect(lines[0].id).toBeUndefined();
    expect(invoiceService.updateInvoice).not.toHaveBeenCalled();
  });

  it('clears the line id when an existing line is switched to another offering', async () => {
    renderRoute('/invoices/inv1/edit');
    await waitFor(() => expect(lineSelects().length).toBe(2));
    await act(async () => {
      fireEvent.change(lineSelects()[1], { target: { value: 'offering:c2' } });
    });
    await waitFor(() => expect(lineSelects()[1].value).toBe('offering:c2'));
    await saveDraft();
    await waitFor(() => expect(invoiceService.updateInvoice).toHaveBeenCalled());
    const lines = savedLines(invoiceService.updateInvoice);
    expect(lines[0].id).toBe('line-archived');
    expect(lines[1]).toEqual(expect.objectContaining({ offering_id: 'c2' }));
    expect(lines[1].id).toBeUndefined();
  });

  it('shows the pricing 422 as an error and does not keep the offering as a normal priced line', async () => {
    mockedPricing.calculatePrice.mockRejectedValue({
      code: 'VALIDATION_ERROR',
      message: "Offering 'Plan p1' is archived and cannot be priced.",
      status: 422,
    });
    renderRoute('/invoices/new');
    await waitFor(() => expect(lineSelects().length).toBe(1));
    await act(async () => {
      fireEvent.change(lineSelects()[0], { target: { value: 'plan:p1' } });
    });
    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith('error', expect.any(String), expect.stringContaining('archived'))
    );
    expect(lineSelects()[0].value).toBe('');
  });

  it('still only warns when pricing is merely unavailable (unchanged behaviour)', async () => {
    mockedPricing.calculatePrice.mockRejectedValue(new Error('network down'));
    renderRoute('/invoices/new');
    await waitFor(() => expect(lineSelects().length).toBe(1));
    await act(async () => {
      fireEvent.change(lineSelects()[0], { target: { value: 'plan:p1' } });
    });
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('warning', 'Could not calculate price', expect.any(String)));
    expect(lineSelects()[0].value).toBe('plan:p1');
  });
});

// BUG-07: an organization without a GSTIN charges no GST; the preview must agree with the server.
describe('<InvoiceFormPage /> GST preview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedPricing.getPlans.mockResolvedValue({ items: [plan('p1', 'flat', 100)], total: 1 } as any);
    mockedPricing.calculatePrice.mockResolvedValue(priceResponse(100, 'flat'));
  });

  async function pickCustomerAndPlan() {
    renderPage();
    await act(async () => {
      fireEvent.click(screen.getByText('pick-customer'));
    });
    await selectPlan('p1');
    await waitFor(() => expect(rateInput().value).toBe('100'));
    await waitFor(() => expect(quoteService.getSupplyPreview).toHaveBeenCalledWith('cust-1'));
  }

  it('adds no tax and explains why when the organization has no GSTIN', async () => {
    vi.mocked(quoteService.getSupplyPreview).mockResolvedValue({ supply_type: 'intra_state', charges_gst: false });
    await pickCustomerAndPlan();
    const notice = await screen.findByTestId('no-gst-notice');
    expect(notice).toHaveTextContent('no GSTIN');
    expect(within(notice).getByRole('link')).toHaveAttribute('href', '/settings/organization');
    expect(lineAmount()).toContain('100');
    expect(lineAmount()).not.toContain('118');
  });

  it('keeps charging the line tax for a GST-registered organization', async () => {
    vi.mocked(quoteService.getSupplyPreview).mockResolvedValue({ supply_type: 'intra_state', charges_gst: true });
    await pickCustomerAndPlan();
    expect(lineAmount()).toContain('118');
    expect(screen.queryByTestId('no-gst-notice')).not.toBeInTheDocument();
  });
});
