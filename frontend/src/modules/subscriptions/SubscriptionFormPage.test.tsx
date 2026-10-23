import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SubscriptionFormPage, DEFAULT_TRIAL_DAYS } from './SubscriptionFormPage';
import { subscriptionService } from '../../services/subscriptionService';
import { customerService } from '../../services/customerService';

vi.mock('../../services/subscriptionService', () => ({
  subscriptionService: {
    planOptions: vi.fn(),
    create: vi.fn(),
  },
}));

vi.mock('../../services/customerService', () => ({
  customerService: { list: vi.fn() },
}));

vi.mock('../../services/planPricingService', () => ({
  planPricingService: { calculatePrice: vi.fn() },
}));

vi.mock('./NewPlanModal', () => ({ NewPlanModal: () => null }));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

const mockedSubs = vi.mocked(subscriptionService);

// A plan with NO default trial: the bug was that the Trial Center form then created an ACTIVE subscription.
const noTrialPlan = {
  id: 'plan-1',
  source: 'plan',
  plan_id: 'plan-1',
  offering_id: null,
  name: 'Basic',
  code: 'BASIC',
  product_name: '',
  billing_interval: 'monthly',
  interval_count: 1,
  pricing_model: 'flat',
  unit_amount: '1000.00',
  currency: 'INR',
  tax_rate_pct: '18.00',
  trial_days: 0,
  pricing_tiers: [],
  is_active: true,
} as any;

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <SubscriptionFormPage />
    </MemoryRouter>
  );
}

describe('<SubscriptionFormPage /> trial mode (Trial Center "New Trial")', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // vite.config sets restoreMocks, so implementations are (re)installed per test.
    vi.mocked(customerService).list.mockResolvedValue({
      items: [{ id: 'cust-1', display_name: 'Acme', customer_number: 'C-1', currency: 'INR', tax_exempt: false }],
      total: 1,
    } as any);
    mockedSubs.planOptions.mockResolvedValue([noTrialPlan]);
    mockedSubs.create.mockResolvedValue({ id: 'sub-1', subscription_number: 'SUB-000001' } as any);
  });

  it('defaults to a 14 day trial and submits a trialing subscription', async () => {
    renderAt('/subscriptions/new?trial=1');

    expect(await screen.findByRole('heading', { name: /start new trial/i })).toBeInTheDocument();
    const trialInput = screen.getByLabelText(/trial period/i) as HTMLInputElement;
    expect(trialInput.value).toBe(String(DEFAULT_TRIAL_DAYS));

    fireEvent.click(screen.getByRole('button', { name: /start trial/i }));

    await waitFor(() => expect(mockedSubs.create).toHaveBeenCalledTimes(1));
    const payload = mockedSubs.create.mock.calls[0][0];
    expect(payload.status).toBe('trialing');
    expect(payload.trial_days).toBe(14);
    expect(payload.generate_first_invoice).toBe(false);
  });

  it('blocks a trial with 0 days and shows a clear message', async () => {
    const { container } = renderAt('/subscriptions/new?trial=1');
    const trialInput = (await screen.findByLabelText(/trial period/i)) as HTMLInputElement;

    fireEvent.change(trialInput, { target: { value: '0' } });
    // Submit the form directly (jsdom does not enforce the input's min / required).
    fireEvent.submit(container.querySelector('form')!);

    expect((await screen.findAllByText(/at least 1 day/i)).length).toBeGreaterThan(0);
    expect(mockedSubs.create).not.toHaveBeenCalled();
  });

  it('keeps the regular create flow unchanged without ?trial=1', async () => {
    renderAt('/subscriptions/new');

    expect(await screen.findByRole('heading', { name: /create new subscription/i })).toBeInTheDocument();
    expect((screen.getByLabelText(/trial period/i) as HTMLInputElement).value).toBe('0');

    fireEvent.click(screen.getByRole('button', { name: /create subscription contract/i }));
    await waitFor(() => expect(mockedSubs.create).toHaveBeenCalledTimes(1));
    const payload = mockedSubs.create.mock.calls[0][0];
    expect(payload.status).toBe('active');
    expect(payload.trial_days).toBe(0);
  });
});
