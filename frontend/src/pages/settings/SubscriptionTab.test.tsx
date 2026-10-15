import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ApiError, MemberRole, PlatformSubscriptionInfo, TrialInfo } from '../../types/api';
import type { CheckoutSession, PublicPlan } from '../../services/platformSubscriptionService';

let auth: {
  role: MemberRole;
  trial: TrialInfo | null;
  subscription: PlatformSubscriptionInfo | null;
};
const refreshMe = vi.fn();

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    trial: auth.trial,
    subscription: auth.subscription,
    membership: { id: 'm-1', role: auth.role, status: 'active', joined_at: null },
    serverClockOffsetMs: 0,
    refreshMe,
  }),
}));

const listPlans = vi.fn();
const listSandboxPlans = vi.fn();
const startCheckout = vi.fn();
const verifyCheckout = vi.fn();
vi.mock('../../services/platformSubscriptionService', () => ({
  platformSubscriptionService: {
    listPlans: () => listPlans(),
    listSandboxPlans: () => listSandboxPlans(),
    listReceipts: () => Promise.resolve({ items: [], total: 0, page: 1, page_size: 25, total_pages: 0 }),
    receiptPdfUrl: (id: string) => `/api/v1/plan-subscription/receipts/${id}/pdf`,
    startCheckout: (code: string) => startCheckout(code),
    verifyCheckout: (body: unknown) => verifyCheckout(body),
  },
}));

/** Stands in for Checkout.js: records what the page opened it with; never talks to Razorpay. */
const rzp = {
  options: null as RazorpaySubscriptionCheckoutOptions | null,
  instances: 0,
  open: vi.fn(),
  failedHandler: null as ((e: RazorpayPaymentFailedEvent) => void) | null,
};
class FakeRazorpay {
  constructor(options: RazorpaySubscriptionCheckoutOptions) {
    rzp.options = options;
    rzp.instances += 1;
  }
  open() {
    rzp.open();
  }
  close() {}
  on(_event: 'payment.failed', handler: (e: RazorpayPaymentFailedEvent) => void) {
    rzp.failedHandler = handler;
  }
}
const loadRazorpay = vi.fn();
vi.mock('../public/razorpayLoader', () => ({ loadRazorpayCheckout: () => loadRazorpay() }));

import { SubscriptionTab } from './SubscriptionTab';
import { formatInterval, formatPlanPrice, hasPaidPlan, seatLabel, taxLabel } from './subscriptionDisplay';

// --- fixtures ------------------------------------------------------------------------------------

function plan(overrides: Partial<PublicPlan> = {}): PublicPlan {
  return {
    code: 'starter',
    name: 'Starter',
    description: 'For small teams getting started.',
    bundles: [{ key: 'foundation', label: 'Foundation', description: 'Customers, products, invoices and payments.' }],
    modules: [
      { key: 'customers', label: 'Customers', base: true },
      { key: 'quotes', label: 'Quotes & CPQ', base: false },
    ],
    price: { amount_minor: 79900, currency: 'INR', interval: 'month', interval_count: 1 },
    tax_treatment: 'exclusive',
    seat_limit: 3,
    purchasable: true,
    ...overrides,
  };
}

const GROWTH = plan({ code: 'growth', name: 'Growth', price: { amount_minor: 129900, currency: 'INR', interval: 'month', interval_count: 1 }, seat_limit: 5 });

function session(overrides: Partial<CheckoutSession> = {}): CheckoutSession {
  return {
    checkout_attempt_id: 'att-1',
    razorpay_key_id: 'rzp_test_UiDummyKey',
    razorpay_subscription_id: 'sub_UiDummy123',
    expires_at: '2026-10-13T12:30:00Z',
    reused: false,
    plan: {
      code: 'starter', name: 'Starter', description: '', amount_minor: 79900, currency: 'INR',
      interval: 'month', interval_count: 1, tax_treatment: 'exclusive', seat_limit: 3,
    },
    prefill: { name: 'Asha Owner', email: 'owner@example.test' },
    organization_name: 'Acme',
    ...overrides,
  };
}

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

function trial(state: TrialInfo['state'], secondsLeft: number): TrialInfo {
  const now = Date.now();
  return {
    state,
    trial_started_at: new Date(now - 86_400_000).toISOString(),
    trial_ends_at: new Date(now + secondsLeft * 1000).toISOString(),
    server_time: new Date(now).toISOString(),
    seconds_remaining: Math.max(0, secondsLeft),
  };
}

function conflict(code: string, message: string, extra: Record<string, unknown> = {}): ApiError {
  return { code: 'CONFLICT', message, status: 409, details: { code, ...extra } };
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SubscriptionTab />
    </QueryClientProvider>,
  );
}

async function cards() {
  return screen.findAllByTestId('plan-card');
}

beforeEach(() => {
  auth = { role: 'owner', trial: null, subscription: null };
  refreshMe.mockReset().mockResolvedValue(null);
  listPlans.mockReset().mockResolvedValue({ catalog_version: 1, plans: [plan(), GROWTH] });
  listSandboxPlans.mockReset().mockResolvedValue({ catalog_version: 1, plans: [] }); // sandbox off by default
  startCheckout.mockReset().mockResolvedValue(session());
  verifyCheckout.mockReset();
  loadRazorpay.mockReset().mockResolvedValue(FakeRazorpay);
  rzp.options = null;
  rzp.instances = 0;
  rzp.open.mockReset();
  rzp.failedHandler = null;
});

// --- catalog and display -------------------------------------------------------------------------

describe('plan catalog', () => {
  it('shows only the server catalog: price from paise, interval, tax label, seats, bundles and modules', async () => {
    renderTab();
    const [starter] = await cards();
    expect(within(starter).getByRole('heading', { name: 'Starter' })).toBeInTheDocument();
    expect(within(starter).getByText('₹799.00')).toBeInTheDocument();
    expect(within(starter).getByText('per month')).toBeInTheDocument();
    expect(within(starter).getByText('Plus applicable taxes')).toBeInTheDocument();
    expect(within(starter).getByText('Up to 3 users')).toBeInTheDocument();
    expect(within(starter).getByText('Foundation')).toBeInTheDocument();
    expect(within(starter).getByText('Quotes & CPQ')).toBeInTheDocument();
    expect(screen.queryByText(/GST/)).not.toBeInTheDocument(); // never inferred
    expect(screen.queryByText(/To be announced|Plan 1|features$/)).not.toBeInTheDocument(); // no placeholders
  });

  it('labels tax only from tax_treatment', async () => {
    listPlans.mockResolvedValue({
      catalog_version: 1,
      plans: [plan({ tax_treatment: 'inclusive' }), plan({ code: 'odd', name: 'Odd', tax_treatment: 'something-else' })],
    });
    renderTab();
    const [inclusive, odd] = await cards();
    expect(within(inclusive).getByText('Inclusive of applicable taxes')).toBeInTheDocument();
    expect(within(odd).queryByText(/tax/i)).not.toBeInTheDocument();
  });

  it('says plans will be announced soon when nothing is published, with no buttons', async () => {
    listPlans.mockResolvedValue({ catalog_version: 1, plans: [] });
    renderTab();
    expect(await screen.findByText('Plans will be announced soon.')).toBeInTheDocument();
    expect(screen.queryAllByTestId('plan-card')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /Choose/ })).not.toBeInTheDocument();
  });

  it('offers a retry when the catalog cannot be loaded', async () => {
    listPlans.mockRejectedValueOnce({ code: 'NETWORK_ERROR', message: 'offline' });
    renderTab();
    expect(await screen.findByText('Plans could not be loaded')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /try again|retry/i }));
    expect(await cards()).toHaveLength(2);
  });
});

describe('display helpers', () => {
  it('formats catalog prices and intervals', () => {
    expect(formatPlanPrice(79900, 'INR')).toBe('₹799.00');
    expect(formatPlanPrice(129950, 'INR')).toBe('₹1,299.50');
    expect(formatInterval('month', 1)).toBe('per month');
    expect(formatInterval('month', 3)).toBe('every 3 months');
    expect(formatInterval('year', 1)).toBe('per year');
    expect(seatLabel(1)).toBe('Up to 1 user');
    expect(seatLabel(10)).toBe('Up to 10 users');
  });

  it('never guesses a tax label', () => {
    expect(taxLabel('exclusive')).toBe('Plus applicable taxes');
    expect(taxLabel('inclusive')).toBe('Inclusive of applicable taxes');
    expect(taxLabel(null)).toBeNull();
    expect(taxLabel('gst')).toBeNull();
  });

  it('treats active and past_due as already paying', () => {
    expect(hasPaidPlan(paid())).toBe(true);
    expect(hasPaidPlan(paid({ state: 'past_due' }))).toBe(true);
    for (const state of ['cancelled', 'expired', 'invalid'] as const) expect(hasPaidPlan(paid({ state }))).toBe(false);
    expect(hasPaidPlan(null)).toBe(false);
  });
});

// --- who may buy, and when ----------------------------------------------------------------------

describe('authorization and state', () => {
  it('gives the Owner an enabled button for a purchasable plan', async () => {
    renderTab();
    const [starter] = await cards();
    expect(within(starter).getByRole('button', { name: 'Choose Starter' })).toBeEnabled();
  });

  it.each<MemberRole>(['admin', 'finance', 'viewer'])('%s sees plans but no purchase button', async (role) => {
    auth.role = role;
    renderTab();
    await cards();
    expect(screen.getByText('Ask your organization Owner to choose a plan.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Choose/ })).not.toBeInTheDocument();
  });

  it('never enables a plan the server marks not purchasable', async () => {
    listPlans.mockResolvedValue({ catalog_version: 1, plans: [plan({ purchasable: false })] });
    renderTab();
    const [starter] = await cards();
    expect(within(starter).getByRole('button', { name: 'Not available yet' })).toBeDisabled();
    expect(within(starter).queryByRole('button', { name: /Choose/ })).not.toBeInTheDocument();
  });

  it('blocks a second purchase while a paid plan is active', async () => {
    auth.subscription = paid();
    renderTab();
    const [starter, growth] = await cards();
    expect(within(starter).getByRole('button', { name: 'Current plan' })).toBeDisabled();
    expect(within(growth).getByRole('button', { name: 'Choose Growth' })).toBeDisabled();
    expect(screen.getByText(/already has a paid plan/)).toBeInTheDocument();
    await userEvent.click(within(growth).getByRole('button', { name: 'Choose Growth' })).catch(() => undefined);
    expect(startCheckout).not.toHaveBeenCalled();
  });

  it('blocks a second purchase while a payment is overdue', async () => {
    auth.subscription = paid({ state: 'past_due', grace_period_end: '2026-11-08T12:00:00Z' });
    renderTab();
    const [, growth] = await cards();
    expect(within(growth).getByRole('button', { name: 'Choose Growth' })).toBeDisabled();
  });

  it('lets the Owner choose again once the plan has ended', async () => {
    auth.subscription = paid({ state: 'expired', writable: false });
    renderTab();
    const [starter] = await cards();
    expect(within(starter).getByRole('button', { name: 'Choose Starter' })).toBeEnabled();
  });
});

describe('status card', () => {
  const status = () => screen.getByTestId('subscription-status');

  it('counts down a running trial', async () => {
    auth.trial = trial('trialing', 3 * 86_400);
    renderTab();
    expect(status()).toHaveTextContent('Free trial');
    expect(status()).toHaveTextContent('Your free trial ends in 3 days.');
  });

  it('explains an ended trial calmly', () => {
    auth.trial = trial('trial_expired', -60);
    renderTab();
    expect(status()).toHaveTextContent('Your free trial has ended');
    expect(status()).toHaveTextContent("Your organization's data is safe and preserved.");
  });

  it('shows the active plan with its period end', async () => {
    auth.subscription = paid();
    renderTab();
    await cards();
    expect(status()).toHaveTextContent('Starter plan is active');
    expect(status()).toHaveTextContent('Current billing period ends on 01 Nov 2026.');
  });

  it('shows a scheduled cancellation', () => {
    auth.subscription = paid({ cancel_at_period_end: true });
    renderTab();
    expect(status()).toHaveTextContent('cancellation scheduled');
    expect(status()).toHaveTextContent('stays active until 01 Nov 2026 and will not renew');
  });

  it('shows an overdue payment with the grace deadline', () => {
    auth.subscription = paid({ state: 'past_due', grace_period_end: '2026-11-08T12:00:00Z' });
    renderTab();
    expect(status()).toHaveTextContent('Payment overdue');
    expect(status()).toHaveTextContent(/keep working until 08 Nov 2026/);
  });

  it.each(['cancelled', 'expired', 'invalid'] as const)('is calm about a %s plan', (state) => {
    auth.subscription = paid({ state, writable: false });
    renderTab();
    expect(status()).toHaveTextContent('Your plan is not active');
    expect(status()).toHaveTextContent('data is safe and preserved');
  });

  it('asks the user to choose a plan once one can be bought', async () => {
    auth.trial = trial('trial_expired', -60);
    renderTab();
    await cards();
    expect(status()).toHaveTextContent('Choose a plan to continue using Rooman Billing.');
  });

  it('keeps the countdown live on this page (the global banner is hidden here)', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
    try {
      auth.trial = trial('trialing', 90);
      renderTab();
      expect(status()).toHaveTextContent('Your free trial ends in 2 minutes.');
      act(() => {
        vi.advanceTimersByTime(45_000);
      });
      expect(status()).toHaveTextContent('Your free trial ends in 45 seconds.');
      act(() => {
        vi.advanceTimersByTime(50_000);
      });
      expect(status()).toHaveTextContent('Your free trial has ended');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('before any plan can be bought', () => {
  const status = () => screen.getByTestId('subscription-status');

  it('shows the ended trial once, without inviting a choice, and keeps the empty state', async () => {
    listPlans.mockResolvedValue({ catalog_version: 1, plans: [] });
    auth.trial = trial('trial_expired', -60);
    renderTab();
    expect(await screen.findByText('Plans will be announced soon.')).toBeInTheDocument();
    expect(status()).toHaveTextContent('Your free trial has ended');
    expect(status()).toHaveTextContent("Your organization's data is safe and preserved.");
    expect(screen.queryByText(/Choose a plan/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/Plans will be announced soon/)).toHaveLength(1);
    expect(screen.getAllByText(/data is safe and preserved/)).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /Choose|View Plans/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /View Plans/ })).not.toBeInTheDocument();
  });

  it('does not invite a choice for an inactive plan either', async () => {
    listPlans.mockResolvedValue({ catalog_version: 1, plans: [] });
    auth.subscription = paid({ state: 'expired', writable: false });
    renderTab();
    await screen.findByText('Plans will be announced soon.');
    expect(status()).toHaveTextContent('Your plan is not active');
    expect(status()).not.toHaveTextContent('Choose a plan');
  });

  it('treats published plans that are not purchasable the same way', async () => {
    listPlans.mockResolvedValue({ catalog_version: 1, plans: [plan({ purchasable: false })] });
    auth.trial = trial('trial_expired', -60);
    renderTab();
    await cards();
    expect(status()).not.toHaveTextContent('Choose a plan');
    expect(screen.getByRole('button', { name: 'Not available yet' })).toBeDisabled();
  });
});

// --- checkout ------------------------------------------------------------------------------------

describe('checkout', () => {
  async function choose(name = 'Choose Starter') {
    const button = await screen.findByRole('button', { name });
    await userEvent.click(button);
  }

  it('opens Razorpay with the server key and subscription and nothing the browser made up', async () => {
    renderTab();
    await choose();
    await waitFor(() => expect(rzp.open).toHaveBeenCalledTimes(1));
    expect(startCheckout).toHaveBeenCalledWith('starter');
    const options = rzp.options as unknown as Record<string, unknown>;
    expect(options.key).toBe('rzp_test_UiDummyKey');
    expect(options.subscription_id).toBe('sub_UiDummy123');
    expect(options).not.toHaveProperty('amount');
    expect(options).not.toHaveProperty('order_id');
    expect(options.prefill).toEqual({ name: 'Asha Owner', email: 'owner@example.test' });
  });

  it('sends only the three callback fields, shows the server result and re-reads /auth/me', async () => {
    verifyCheckout.mockResolvedValue({ status: 'active', message: 'Payment confirmed. Your plan is active.', plan_code: 'starter' });
    renderTab();
    await choose();
    await waitFor(() => expect(rzp.open).toHaveBeenCalled());
    await act(async () => {
      rzp.options!.handler({
        razorpay_payment_id: 'pay_UiDummy1',
        razorpay_subscription_id: 'sub_UiDummy123',
        razorpay_signature: 'abc123',
        // Anything else Checkout.js might add is not forwarded.
        ...({ razorpay_order_id: 'order_x', plan: 'business' } as object),
      } as RazorpaySubscriptionCheckoutSuccess);
    });
    await waitFor(() => expect(screen.getByTestId('checkout-notice')).toHaveTextContent('Payment confirmed. Your plan is active.'));
    expect(verifyCheckout).toHaveBeenCalledWith({
      razorpay_payment_id: 'pay_UiDummy1',
      razorpay_subscription_id: 'sub_UiDummy123',
      razorpay_signature: 'abc123',
    });
    expect(refreshMe).toHaveBeenCalledTimes(1);
  });

  it('shows a pending confirmation as pending, not as active', async () => {
    verifyCheckout.mockResolvedValue({ status: 'pending', message: 'Razorpay has your authorization; we are waiting.', plan_code: 'starter' });
    renderTab();
    await choose();
    await waitFor(() => expect(rzp.open).toHaveBeenCalled());
    await act(async () => {
      rzp.options!.handler({ razorpay_payment_id: 'pay_1', razorpay_subscription_id: 'sub_UiDummy123', razorpay_signature: 'ab' });
    });
    const notice = await screen.findByTestId('checkout-notice');
    expect(notice).toHaveTextContent('Waiting for Razorpay');
    expect(notice).not.toHaveTextContent('Plan active');
  });

  it('ignores a second click while a checkout is starting', async () => {
    let release: (s: CheckoutSession) => void = () => undefined;
    startCheckout.mockImplementation(() => new Promise<CheckoutSession>((resolve) => { release = resolve; }));
    renderTab();
    const [starter, growth] = await cards();
    const button = within(starter).getByRole('button', { name: 'Choose Starter' });
    await userEvent.click(button);
    await userEvent.click(button).catch(() => undefined);
    expect(within(growth).getByRole('button', { name: 'Choose Growth' })).toBeDisabled();
    expect(startCheckout).toHaveBeenCalledTimes(1);
    await act(async () => release(session()));
    await waitFor(() => expect(rzp.open).toHaveBeenCalledTimes(1));
    expect(rzp.instances).toBe(1);
  });

  it('a closed Razorpay window grants nothing and frees the buttons', async () => {
    renderTab();
    await choose();
    await waitFor(() => expect(rzp.open).toHaveBeenCalled());
    await act(async () => rzp.options!.modal!.ondismiss!());
    expect(await screen.findByTestId('checkout-notice')).toHaveTextContent('Checkout closed');
    expect(screen.getByTestId('checkout-notice')).toHaveTextContent('your plan has not changed');
    expect(verifyCheckout).not.toHaveBeenCalled();
    expect(refreshMe).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Choose Starter' })).toBeEnabled();
  });

  it('a failed payment inside Razorpay is reported without unlocking anything', async () => {
    renderTab();
    await choose();
    await waitFor(() => expect(rzp.open).toHaveBeenCalled());
    await act(async () => rzp.failedHandler!({ error: { description: 'Card declined by bank' } }));
    expect(screen.getByTestId('checkout-notice')).toHaveTextContent('Card declined by bank');
    expect(verifyCheckout).not.toHaveBeenCalled();
    expect(refreshMe).not.toHaveBeenCalled();
  });

  it('reports another open checkout with its expiry and does not open Razorpay', async () => {
    startCheckout.mockRejectedValue(
      conflict('CHECKOUT_IN_PROGRESS', 'A checkout for another plan is still open.', { plan_code: 'growth', expires_at: '2026-10-13T12:30:00Z' }),
    );
    renderTab();
    await choose();
    const notice = await screen.findByTestId('checkout-notice');
    expect(notice).toHaveTextContent('Another checkout is open');
    expect(notice).toHaveTextContent('13 Oct 2026');
    expect(loadRazorpay).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Choose Starter' })).toBeEnabled();
  });

  it('re-reads the catalog when the plan is no longer available', async () => {
    startCheckout.mockRejectedValue(conflict('PLAN_NOT_AVAILABLE', 'This plan is not available.'));
    renderTab();
    await choose();
    expect(await screen.findByTestId('checkout-notice')).toHaveTextContent('Plan not available');
    await waitFor(() => expect(listPlans).toHaveBeenCalledTimes(2));
  });

  it('re-reads /auth/me when the server says a plan is already active', async () => {
    startCheckout.mockRejectedValue(conflict('SUBSCRIPTION_ALREADY_ACTIVE', 'Your organization already has a paid plan.'));
    renderTab();
    await choose();
    expect(await screen.findByTestId('checkout-notice')).toHaveTextContent('already has a paid plan');
    expect(refreshMe).toHaveBeenCalledTimes(1);
    expect(rzp.instances).toBe(0);
  });

  it.each(['CHECKOUT_NOT_READY', 'CHECKOUT_UNAVAILABLE', 'GATEWAY_NOT_CONFIGURED', 'LIVE_CHECKOUT_DISABLED'])(
    'explains %s as checkout being unavailable', async (code) => {
      startCheckout.mockRejectedValue({ code, message: 'internal wording', status: 503 });
      renderTab();
      await choose();
      expect(await screen.findByTestId('checkout-notice')).toHaveTextContent('Plan checkout is not available right now');
      expect(rzp.instances).toBe(0);
    },
  );

  it('reports a delayed confirmation without claiming the plan is active', async () => {
    verifyCheckout.mockRejectedValue({ code: 'PAYMENT_CONFIRMATION_DELAYED', message: 'Delayed', status: 503 });
    renderTab();
    await choose();
    await waitFor(() => expect(rzp.open).toHaveBeenCalled());
    await act(async () => {
      rzp.options!.handler({ razorpay_payment_id: 'pay_1', razorpay_subscription_id: 'sub_UiDummy123', razorpay_signature: 'ab' });
    });
    expect(await screen.findByTestId('checkout-notice')).toHaveTextContent('Razorpay has not confirmed the payment yet');
    expect(refreshMe).not.toHaveBeenCalled();
  });

  it('reports a rejected signature and changes nothing', async () => {
    verifyCheckout.mockRejectedValue({ code: 'PAYMENT_SIGNATURE_INVALID', message: 'bad', status: 400 });
    renderTab();
    await choose();
    await waitFor(() => expect(rzp.open).toHaveBeenCalled());
    await act(async () => {
      rzp.options!.handler({ razorpay_payment_id: 'pay_1', razorpay_subscription_id: 'sub_UiDummy123', razorpay_signature: 'ab' });
    });
    expect(await screen.findByRole('alert')).toHaveTextContent('Your plan has not changed');
    expect(refreshMe).not.toHaveBeenCalled();
  });

  it('recovers when Checkout.js cannot be loaded', async () => {
    loadRazorpay.mockRejectedValue(new Error('Could not load Razorpay Checkout. Check your connection and try again.'));
    renderTab();
    await choose();
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load Razorpay Checkout');
    expect(screen.getByRole('button', { name: 'Choose Starter' })).toBeEnabled();
  });
});

// --- sandbox TEST plan ---------------------------------------------------------------------------

const SANDBOX_PLAN = plan({
  code: 'sandbox_foundation',
  name: 'Sandbox Test Plan (Foundation)',
  description: 'TEST MODE ONLY - not a commercial offer.',
  price: { amount_minor: 100, currency: 'INR', interval: 'month', interval_count: 1 },
  tax_treatment: null,
  sandbox: true,
});

describe('sandbox test plan', () => {
  const sandboxSection = () => screen.findByTestId('sandbox-plans');

  beforeEach(() => {
    listPlans.mockResolvedValue({ catalog_version: 2, plans: [] }); // commercial plans are all drafts
    listSandboxPlans.mockResolvedValue({ catalog_version: 2, plans: [SANDBOX_PLAN] });
  });

  it('is not shown while the server does not allow the sandbox', async () => {
    listSandboxPlans.mockResolvedValue({ catalog_version: 2, plans: [] });
    renderTab();
    await screen.findByText('Plans will be announced soon.');
    expect(screen.queryByTestId('sandbox-plans')).not.toBeInTheDocument();
    expect(screen.queryByText(/TEST MODE/)).not.toBeInTheDocument();
  });

  it('is not shown when the sandbox list cannot be loaded', async () => {
    listSandboxPlans.mockRejectedValue({ code: 'NETWORK_ERROR', message: 'offline' });
    renderTab();
    await screen.findByText('Plans will be announced soon.');
    expect(screen.queryByTestId('sandbox-plans')).not.toBeInTheDocument();
  });

  it('is labelled TEST MODE - NOT A COMMERCIAL OFFER, apart from the commercial plans', async () => {
    renderTab();
    const section = await sandboxSection();
    expect(within(section).getAllByText('TEST MODE — NOT A COMMERCIAL OFFER').length).toBeGreaterThanOrEqual(2);
    const card = within(section).getByTestId('sandbox-plan-card');
    expect(within(card).getByText('₹1.00')).toBeInTheDocument();
    expect(within(card).queryByText(/tax/i)).not.toBeInTheDocument();
    // The commercial area still says nothing can be bought, and lists no plan cards.
    expect(screen.getByText('Plans will be announced soon.')).toBeInTheDocument();
    expect(screen.queryAllByTestId('plan-card')).toHaveLength(0);
    expect(screen.getByTestId('subscription-status')).not.toHaveTextContent('Choose a plan');
  });

  it('never shows draft commercial plans, even next to the sandbox plan', async () => {
    renderTab();
    await sandboxSection();
    expect(screen.queryByText(/Starter|Growth|Business/)).not.toBeInTheDocument();
    expect(screen.queryByText(/₹799|₹1,299|₹1,799/)).not.toBeInTheDocument();
  });

  it('a sandbox entry in the public list is ignored (commercial and sandbox never mix)', async () => {
    listPlans.mockResolvedValue({ catalog_version: 2, plans: [SANDBOX_PLAN] });
    listSandboxPlans.mockResolvedValue({ catalog_version: 2, plans: [] });
    renderTab();
    expect(await screen.findByText('Plans will be announced soon.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Choose/ })).not.toBeInTheDocument();
  });

  it('lets the Owner run a test purchase through the normal checkout', async () => {
    startCheckout.mockResolvedValue(session({
      plan: { code: 'sandbox_foundation', name: 'Sandbox Test Plan (Foundation)', description: '', amount_minor: 100,
        currency: 'INR', interval: 'month', interval_count: 1, tax_treatment: null, seat_limit: 3, sandbox: true },
    }));
    verifyCheckout.mockResolvedValue({ status: 'pending', message: 'Razorpay has your authorization; we are waiting.', plan_code: 'sandbox_foundation' });
    renderTab();
    const section = await sandboxSection();
    await userEvent.click(within(section).getByRole('button', { name: 'Choose Sandbox Test Plan (Foundation)' }));
    await waitFor(() => expect(rzp.open).toHaveBeenCalledTimes(1));
    expect(startCheckout).toHaveBeenCalledWith('sandbox_foundation');
    expect(rzp.options).not.toHaveProperty('amount');
    await act(async () => {
      rzp.options!.handler({ razorpay_payment_id: 'pay_1', razorpay_subscription_id: 'sub_UiDummy123', razorpay_signature: 'ab' });
    });
    expect(await screen.findByTestId('checkout-notice')).toHaveTextContent('Waiting for Razorpay'); // not "active"
  });

  it.each<MemberRole>(['admin', 'finance', 'viewer'])('%s sees the sandbox plan but cannot buy it', async (role) => {
    auth.role = role;
    renderTab();
    const section = await sandboxSection();
    expect(within(section).getByText('Only the organization Owner can run a test purchase.')).toBeInTheDocument();
    expect(within(section).queryByRole('button')).not.toBeInTheDocument();
  });

  it('is not purchasable until the server says checkout is ready', async () => {
    listSandboxPlans.mockResolvedValue({ catalog_version: 2, plans: [{ ...SANDBOX_PLAN, purchasable: false }] });
    renderTab();
    const section = await sandboxSection();
    expect(within(section).getByRole('button', { name: 'Not available yet' })).toBeDisabled();
  });

  it('labels an active sandbox subscription as test mode', async () => {
    auth.subscription = paid({ plan_code: 'sandbox_foundation', sandbox: true });
    renderTab();
    const section = await sandboxSection();
    const status = screen.getByTestId('subscription-status');
    expect(status).toHaveTextContent('TEST MODE — NOT A COMMERCIAL OFFER');
    expect(status).toHaveTextContent('Sandbox Test Plan (Foundation) is active');
    expect(within(section).getByRole('button', { name: 'Current plan' })).toBeDisabled();
  });
});

describe('plan cancellation on the page', () => {
  it('shows the Owner a Cancel plan action for a paid plan', async () => {
    auth.subscription = paid();
    renderTab();
    await cards();
    expect(screen.getByRole('button', { name: 'Cancel plan' })).toBeEnabled();
  });

  it.each<MemberRole>(['admin', 'finance', 'viewer'])('does not show it to %s', async (role) => {
    auth.role = role;
    auth.subscription = paid();
    renderTab();
    await cards();
    expect(screen.queryByRole('button', { name: 'Cancel plan' })).not.toBeInTheDocument();
  });

  it('does not show it during a trial or without a plan', async () => {
    auth.trial = trial('trialing', 3 * 86_400);
    renderTab();
    await cards();
    expect(screen.queryByRole('button', { name: 'Cancel plan' })).not.toBeInTheDocument();
  });
});

describe('payment receipts on the page', () => {
  it.each<MemberRole>(['owner', 'admin', 'finance'])('shows the receipts section to %s', async (role) => {
    auth.role = role;
    renderTab();
    expect(await screen.findByRole('heading', { name: 'Payment receipts' })).toBeInTheDocument();
  });

  it('does not show receipts to a viewer', async () => {
    auth.role = 'viewer';
    renderTab();
    await screen.findAllByTestId('plan-card');
    expect(screen.queryByRole('heading', { name: 'Payment receipts' })).not.toBeInTheDocument();
  });
});
