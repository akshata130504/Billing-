import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ApiError, PlatformSubscriptionInfo } from '../../types/api';

const cancelPlan = vi.fn();
vi.mock('../../services/platformSubscriptionService', () => ({
  platformSubscriptionService: { cancelPlan: (mode: string) => cancelPlan(mode) },
}));

import { CancelPlanSection } from './CancelPlanSection';

const refreshMe = vi.fn();
const onNotice = vi.fn();

function paid(overrides: Partial<PlatformSubscriptionInfo> = {}): PlatformSubscriptionInfo {
  return {
    state: 'active',
    plan_code: 'starter',
    billing_interval: 'month',
    billing_interval_count: 1,
    current_period_start: '2026-10-01T12:00:00Z',
    current_period_end: '2026-11-01T12:00:00Z',
    cancel_at_period_end: false,
    grace_period_end: null,
    writable: true,
    ...overrides,
  };
}

function renderSection(subscription = paid(), isOwner = true) {
  return render(<CancelPlanSection subscription={subscription} isOwner={isOwner} refreshMe={refreshMe} onNotice={onNotice} />);
}

async function openDialog() {
  await userEvent.click(screen.getByRole('button', { name: 'Cancel plan' }));
  return screen.findByRole('dialog');
}

beforeEach(() => {
  cancelPlan.mockReset();
  refreshMe.mockReset().mockResolvedValue(null);
  onNotice.mockReset();
});

describe('CancelPlanSection', () => {
  it('is not offered to members other than the Owner', () => {
    const { container } = renderSection(paid(), false);
    expect(container).toBeEmptyDOMElement();
  });

  it.each(['cancelled', 'expired', 'invalid'] as const)('is not offered for a %s plan', (state) => {
    const { container } = renderSection(paid({ state, writable: false }));
    expect(container).toBeEmptyDOMElement();
  });

  it('asks for confirmation and explains both options before anything is sent', async () => {
    renderSection();
    const dialog = await openDialog();
    expect(within(dialog).getByText(/cannot be undone/)).toBeInTheDocument();
    expect(within(dialog).getByText(/keeps working until 01 Nov 2026/)).toBeInTheDocument();
    expect(within(dialog).getByText(/not refunded automatically/)).toBeInTheDocument();
    expect(within(dialog).getByRole('radio', { name: /At the end of the current period/ })).toBeChecked();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Keep my plan' }));
    expect(cancelPlan).not.toHaveBeenCalled();
  });

  it('schedules the cancellation at period end and re-reads /auth/me', async () => {
    cancelPlan.mockResolvedValue({ status: 'scheduled', effective_at: '2026-11-01T12:00:00Z', already: false,
      message: 'Your plan is cancelled at the end of the current billing period. It keeps working until then.' });
    renderSection();
    const dialog = await openDialog();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel at period end' }));
    await waitFor(() => expect(cancelPlan).toHaveBeenCalledWith('at_period_end'));
    expect(refreshMe).toHaveBeenCalledTimes(1);
    expect(onNotice).toHaveBeenCalledWith(expect.objectContaining({ tone: 'success', title: 'Cancellation scheduled' }));
    expect(onNotice.mock.calls[0][0].message).toMatch(/Access ends on 01 Nov 2026/);
  });

  it('cancels immediately when the Owner chooses it', async () => {
    cancelPlan.mockResolvedValue({ status: 'cancelled', effective_at: '2026-10-13T10:00:00Z', already: false, message: 'Your plan is cancelled.' });
    renderSection();
    const dialog = await openDialog();
    await userEvent.click(within(dialog).getByRole('radio', { name: /Immediately/ }));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel now' }));
    await waitFor(() => expect(cancelPlan).toHaveBeenCalledWith('immediately'));
    expect(onNotice).toHaveBeenCalledWith(expect.objectContaining({ tone: 'success', title: 'Plan cancelled' }));
  });

  it('offers only immediate cancellation while a payment is overdue', async () => {
    renderSection(paid({ state: 'past_due', grace_period_end: '2026-11-08T12:00:00Z' }));
    const dialog = await openDialog();
    expect(within(dialog).getByRole('radio', { name: /At the end of the current period/ })).toBeDisabled();
    expect(within(dialog).getByRole('radio', { name: /Immediately/ })).toBeChecked();
  });

  it('reports an unconfirmed cancellation without claiming success', async () => {
    const error: ApiError = { code: 'CANCELLATION_UNCONFIRMED', status: 503,
      message: 'We could not confirm the cancellation with Razorpay. Nothing has changed yet; please try again in a moment.' };
    cancelPlan.mockRejectedValue(error);
    renderSection();
    const dialog = await openDialog();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel at period end' }));
    await waitFor(() => expect(onNotice).toHaveBeenCalled());
    expect(onNotice.mock.calls[0][0]).toMatchObject({ tone: 'warning', title: 'Plan not cancelled' });
    expect(onNotice.mock.calls[0][0].message).toMatch(/Nothing has changed/);
    expect(refreshMe).not.toHaveBeenCalled();
  });

  it('ignores a second confirmation while the first is in flight', async () => {
    let release: (v: unknown) => void = () => undefined;
    cancelPlan.mockImplementation(() => new Promise((resolve) => { release = resolve; }));
    renderSection();
    const dialog = await openDialog();
    const confirm = within(dialog).getByRole('button', { name: 'Cancel at period end' });
    await userEvent.click(confirm);
    await userEvent.click(confirm).catch(() => undefined);
    expect(cancelPlan).toHaveBeenCalledTimes(1);
    release({ status: 'scheduled', effective_at: '2026-11-01T12:00:00Z', already: false, message: 'ok' });
    await waitFor(() => expect(onNotice).toHaveBeenCalledTimes(1));
  });

  it('explains that a scheduled cancellation cannot be undone, and offers no undo or resume', () => {
    renderSection(paid({ cancel_at_period_end: true }));
    expect(screen.getByTestId('cancellation-scheduled-note')).toHaveTextContent('cannot be undone');
    expect(screen.getByTestId('cancellation-scheduled-note')).toHaveTextContent('01 Nov 2026');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
