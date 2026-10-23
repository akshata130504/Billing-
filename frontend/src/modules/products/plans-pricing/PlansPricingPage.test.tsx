import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PlansPricingPage } from './PlansPricingPage';
import { planPricingService } from '../../../services/planPricingService';

vi.mock('../../../services/planPricingService', () => ({
  planPricingService: {
    listPlans: vi.fn(),
    updatePlan: vi.fn(),
    clonePlan: vi.fn(),
    deletePlan: vi.fn(),
    createPlan: vi.fn(),
  },
}));
vi.mock('../../../components/common/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));
vi.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ hasRole: () => true, user: { full_name: 'Tester' } }),
}));

const mocked = vi.mocked(planPricingService);

function plan(over: Record<string, unknown>) {
  return {
    id: 'p1',
    name: 'Plan',
    code: 'P1',
    sku: 'P1',
    pricing_model: 'per_unit',
    base_price: 100,
    currency: 'INR',
    unit: 'seat',
    billing_frequency: 'monthly',
    is_active: true,
    status: 'active',
    pricing_tiers: [],
    ...over,
  } as any;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PlansPricingPage />
    </MemoryRouter>
  );
}

describe('<PlansPricingPage />', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('archived plans have no Edit button but can still be re-activated', async () => {
    mocked.listPlans.mockResolvedValue({
      items: [
        plan({ id: 'a', name: 'Live Plan', is_active: true }),
        plan({ id: 'b', name: 'Old Plan', is_active: false, status: 'archived' }),
      ],
      total: 2,
    } as any);
    mocked.updatePlan.mockResolvedValue({} as any);
    renderPage();

    const oldRow = (await screen.findByText('Old Plan')).closest('tr')!;
    const liveRow = screen.getByText('Live Plan').closest('tr')!;

    expect(oldRow.querySelector('button[title="Edit Plan"]')).toBeNull();
    expect(liveRow.querySelector('button[title="Edit Plan"]')).not.toBeNull();

    const activate = oldRow.querySelector('button[title="Activate Plan"]') as HTMLElement;
    expect(activate).not.toBeNull();
    fireEvent.click(activate);
    await waitFor(() =>
      expect(mocked.updatePlan).toHaveBeenCalledWith('b', { is_active: true, status: 'active' })
    );
  });

  it('wraps huge prices inside the Avg Plan Rate KPI and price cell without NaN/exponent text', async () => {
    mocked.listPlans.mockResolvedValue({
      items: [plan({ id: 'h', name: 'Huge', base_price: 999999999999.99 })],
      total: 1,
    } as any);
    renderPage();

    const kpi = (await screen.findByText('Avg Plan Rate')).nextElementSibling as HTMLElement;
    expect(kpi.className).toContain('break-all');
    expect(kpi.className).toContain('min-w-0');
    expect(kpi.textContent).not.toMatch(/NaN|e\+/i);

    const cell = screen.getByText('Huge').closest('tr')!.querySelector('td.break-all') as HTMLElement;
    expect(cell).not.toBeNull();
    expect(cell.textContent).toContain('9,99,99,99,99,999.99');
    expect(cell.textContent).not.toMatch(/NaN|e\+/i);
  });
});
