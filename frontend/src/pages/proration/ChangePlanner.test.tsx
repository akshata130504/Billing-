/**
 * The upgrade / downgrade picker offers Catalog and Plans & Pricing plan offerings (BUG-42) and a
 * single "Preview Change" click never sends a second identical preview request (BUG-57).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { SubscribablePlanOption, SubscriptionOut } from '../../types/api';
import { prorationService } from '../../services/prorationService';
import { listPreviewSubscriptions } from '../../platform/uiPreview/fixtures/trials';
import { ChangePlanner, changeCandidates } from './ChangePlanner';

vi.mock('../../services/prorationService', () => ({
  prorationService: { preview: vi.fn(), apply: vi.fn(), list: vi.fn(), cancel: vi.fn() },
}));
vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

const mocked = vi.mocked(prorationService);

const option = (over: Partial<SubscribablePlanOption>): SubscribablePlanOption => ({
  id: 'x', source: 'plan', plan_id: null, offering_id: null, name: 'X', code: 'X', product_name: '',
  billing_interval: 'monthly', interval_count: 1, pricing_model: 'flat', unit_amount: '0.00', currency: 'INR',
  tax_rate_pct: '18.00', trial_days: 0, pricing_tiers: [], is_active: true, ...over,
});

// The subscription is on the legacy Starter plan: 999.00 INR / month.
const subscription: SubscriptionOut = listPreviewSubscriptions(new URLSearchParams()).items.find(
  (s) => s.plan.id === 'plan-starter',
)!;

const OPTIONS: SubscribablePlanOption[] = [
  option({ id: 'plan-starter', plan_id: 'plan-starter', name: 'Starter', unit_amount: '999.00' }),
  option({ id: 'plan-growth', plan_id: 'plan-growth', name: 'Growth', unit_amount: '2499.00' }),
  option({ id: 'off-pro', source: 'offering', offering_id: 'off-pro', name: 'Catalog Pro', unit_amount: '4999.00' }),
  option({ id: 'off-lite', source: 'offering', offering_id: 'off-lite', name: 'Catalog Lite', unit_amount: '499.00' }),
  option({ id: 'off-yearly', source: 'offering', offering_id: 'off-yearly', name: 'Yearly Pro', unit_amount: '99999.00', billing_interval: 'yearly' }),
  option({ id: 'off-usd', source: 'offering', offering_id: 'off-usd', name: 'Dollar Pro', unit_amount: '5000.00', currency: 'USD' }),
  option({ id: 'off-off', source: 'offering', offering_id: 'off-off', name: 'Retired Pro', unit_amount: '3000.00', is_active: false }),
];

const PREVIEW = {
  subscription_id: subscription.id, change_type: 'upgrade',
  old_plan: { id: 'plan-starter', name: 'Starter', unit_amount: '999.00' },
  new_plan: { id: 'linked-pro', name: 'Catalog Pro', unit_amount: '4999.00' },
  old_quantity: '1', new_quantity: '1', period_start: '2026-10-01', period_end: '2026-11-01', effective_date: '2026-10-10',
  total_days: 31, days_used: 9, days_remaining: 22, unused_credit: '709.00', remaining_charge: '3547.00',
  net_amount: '2838.00', explanation: 'Upgrade',
};

function renderPlanner() {
  return render(
    <ChangePlanner subscription={subscription} planOptions={OPTIONS} plansLoading={false} canApply onApplied={() => undefined} />,
  );
}

const pickerOptions = () =>
  within(screen.getByLabelText(/New plan/)).getAllByRole('option').map((o) => o.textContent ?? '');

beforeEach(() => {
  mocked.preview.mockReset();
  mocked.preview.mockResolvedValue(PREVIEW as any);
});
afterEach(cleanup);

describe('ChangePlanner plan picker (BUG-42)', () => {
  it('ranks same-currency, same-frequency active plans by price', () => {
    expect(changeCandidates(subscription, OPTIONS, 'upgrade').map((o) => o.name)).toEqual(['Growth', 'Catalog Pro']);
    expect(changeCandidates(subscription, OPTIONS, 'downgrade').map((o) => o.name)).toEqual(['Catalog Lite']);
  });

  it('lists plan offerings for upgrade and downgrade, not only the current plan', () => {
    renderPlanner();
    const upgrade = pickerOptions();
    expect(upgrade).toHaveLength(3);
    expect(upgrade[0]).toContain('(Current)');
    expect(upgrade[1]).toContain('Growth');
    expect(upgrade[2]).toContain('Catalog Pro');

    fireEvent.click(screen.getByRole('button', { name: /Downgrade/ }));
    const downgrade = pickerOptions();
    expect(downgrade).toHaveLength(2);
    expect(downgrade[1]).toContain('Catalog Lite');
    expect(downgrade[1]).toContain('(Downgrade)');
  });

  it('previews an offering with target_offering_id', async () => {
    renderPlanner();
    fireEvent.change(screen.getByLabelText(/New plan/), { target: { value: 'offering:off-pro' } });
    await waitFor(() => expect(mocked.preview).toHaveBeenCalled());
    expect(mocked.preview).toHaveBeenLastCalledWith(subscription.id, { target_offering_id: 'off-pro' });
  });

  it('previews a legacy plan with target_plan_id', async () => {
    renderPlanner();
    fireEvent.change(screen.getByLabelText(/New plan/), { target: { value: 'plan:plan-growth' } });
    await waitFor(() => expect(mocked.preview).toHaveBeenCalled());
    expect(mocked.preview).toHaveBeenLastCalledWith(subscription.id, { target_plan_id: 'plan-growth' });
  });
});

describe('ChangePlanner preview de-duplication (BUG-57)', () => {
  it('sends one request when Preview Change is clicked after the live preview', async () => {
    renderPlanner();
    fireEvent.change(screen.getByLabelText(/New plan/), { target: { value: 'offering:off-pro' } });
    await waitFor(() => expect(mocked.preview).toHaveBeenCalledTimes(1));
    const button = await screen.findByRole('button', { name: 'Preview Change' });
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);
    await new Promise((r) => setTimeout(r, 450));
    expect(mocked.preview).toHaveBeenCalledTimes(1);
  });

  it('sends one request when Preview Change is clicked before the live preview fires', async () => {
    renderPlanner();
    fireEvent.change(screen.getByLabelText(/New plan/), { target: { value: 'offering:off-pro' } });
    fireEvent.click(screen.getByRole('button', { name: 'Preview Change' }));
    await new Promise((r) => setTimeout(r, 450));
    expect(mocked.preview).toHaveBeenCalledTimes(1);
  });
});
