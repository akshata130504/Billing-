import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InvoiceFormPage } from './InvoiceFormPage';
import { planPricingService } from '../../services/planPricingService';
import { catalogCpqService } from '../../services/catalogCpqService';
import { invoiceService } from '../../services/invoiceService';

vi.mock('../../services/planPricingService', () => ({
  planPricingService: {
    getPlans: vi.fn(),
    calculatePrice: vi.fn(),
  },
}));

vi.mock('../../services/catalogCpqService', () => ({
  catalogCpqService: {
    listOfferings: vi.fn().mockResolvedValue({ items: [], total: 0 }),
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

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
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
