import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlatformSubscriptionInfo, TrialInfo } from '../../types/api';
import type { PublicPlanCatalog } from '../../services/platformSubscriptionService';

let auth: { trial: TrialInfo | null; serverClockOffsetMs: number; subscription?: PlatformSubscriptionInfo | null };
const refreshMe = vi.fn();

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    trial: auth.trial,
    subscription: auth.subscription ?? null,
    serverClockOffsetMs: auth.serverClockOffsetMs,
    refreshMe,
  }),
}));

/** What GET /public/plans returned (undefined: still loading or failed). */
let catalog: PublicPlanCatalog | undefined;
const plansEnabled = vi.fn();
vi.mock('../../hooks/usePublicPlans', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../hooks/usePublicPlans')>()),
  usePublicPlans: (enabled = true) => {
    plansEnabled(enabled);
    return { data: enabled ? catalog : undefined };
  },
}));

const PURCHASABLE: PublicPlanCatalog = {
  catalog_version: 1,
  plans: [{
    code: 'starter', name: 'Starter', description: '', bundles: [], modules: [],
    price: { amount_minor: 79900, currency: 'INR', interval: 'month', interval_count: 1 },
    tax_treatment: 'exclusive', seat_limit: 3, purchasable: true,
  }],
};
const NOTHING_PUBLISHED: PublicPlanCatalog = { catalog_version: 1, plans: [] };

import { TrialBanner, formatTimeLeft, isPlansPage } from './TrialBanner';

const NOW = new Date('2026-10-09T10:00:00.000Z').getTime();

function trial(secondsLeft: number, state: TrialInfo['state'] = 'trialing'): TrialInfo {
  return {
    state,
    trial_started_at: new Date(NOW - 60_000).toISOString(),
    trial_ends_at: new Date(NOW + secondsLeft * 1000).toISOString(),
    server_time: new Date(NOW).toISOString(),
    seconds_remaining: Math.max(0, secondsLeft),
  };
}

function renderBanner(path = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <TrialBanner />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  catalog = PURCHASABLE;
  plansEnabled.mockReset();
});

describe('TrialBanner', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
    auth = { trial: trial(12 * 60), serverClockOffsetMs: 0 };
    refreshMe.mockReset();
    refreshMe.mockResolvedValue(null);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the time left with a View Plans link while the trial runs', () => {
    renderBanner();
    expect(screen.getByRole('status')).toHaveTextContent('Your free trial ends in 12 minutes');
    expect(screen.getByRole('link', { name: 'View Plans' })).toHaveAttribute('href', '/settings/subscription');
    expect(screen.queryByText(/trial has ended/i)).not.toBeInTheDocument();
  });

  it('counts down as time passes', () => {
    renderBanner();
    expect(screen.getByRole('status')).toHaveTextContent('12 minutes');
    act(() => {
      vi.advanceTimersByTime(7 * 60_000);
    });
    expect(screen.getByRole('status')).toHaveTextContent('Your free trial ends in 5 minutes');
    act(() => {
      vi.advanceTimersByTime(4 * 60_000 + 30_000);
    });
    expect(screen.getByRole('status')).toHaveTextContent('30 seconds');
  });

  it('uses the server clock, not the browser clock', () => {
    // The browser thinks it is 5 minutes later than the server: it must not shorten the countdown.
    auth = { trial: trial(10 * 60), serverClockOffsetMs: -5 * 60_000 };
    renderBanner();
    expect(screen.getByRole('status')).toHaveTextContent('15 minutes');
  });

  it('shows the ended message and a View Plans link once the trial has expired', () => {
    auth = { trial: trial(-10, 'trial_expired'), serverClockOffsetMs: 0 };
    renderBanner();
    const banner = screen.getByRole('status');
    expect(banner).toHaveTextContent('Your free trial has ended.');
    expect(banner).toHaveTextContent("Your organization's data is safe and preserved.");
    expect(banner).toHaveTextContent('Choose a plan to continue using Rooman Billing.');
    expect(screen.getByRole('link', { name: 'View Plans' })).toHaveAttribute('href', '/settings/subscription');
    expect(refreshMe).not.toHaveBeenCalled(); // already known to be expired
  });

  it('flips to the ended state when the clock reaches zero and re-reads the server once', () => {
    auth = { trial: trial(3), serverClockOffsetMs: 0 };
    renderBanner();
    expect(screen.getByRole('status')).toHaveTextContent('3 seconds');
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(screen.getByRole('status')).toHaveTextContent('Your free trial has ended.');
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(refreshMe).toHaveBeenCalledTimes(1);
  });

  it('renders nothing for an organization without a trial', () => {
    auth = { trial: null, serverClockOffsetMs: 0 };
    const { container } = renderBanner();
    expect(container).toBeEmptyDOMElement();
  });
});

function paidPlan(overrides: Partial<PlatformSubscriptionInfo>): PlatformSubscriptionInfo {
  return {
    state: 'active',
    plan_code: 'starter',
    billing_interval: 'month',
    billing_interval_count: 1,
    current_period_start: '2026-10-01T00:00:00Z',
    current_period_end: '2026-11-01T00:00:00Z',
    cancel_at_period_end: false,
    grace_period_end: null,
    writable: true,
    ...overrides,
  };
}

describe('TrialBanner before any plan can be bought', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
    catalog = NOTHING_PUBLISHED;
    refreshMe.mockReset().mockResolvedValue(null);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('says plans are coming instead of offering View Plans once the trial has ended', () => {
    auth = { trial: trial(-10, 'trial_expired'), serverClockOffsetMs: 0 };
    renderBanner();
    const banner = screen.getByRole('status');
    expect(banner).toHaveTextContent('Your free trial has ended.');
    expect(banner).toHaveTextContent("Your organization's data is safe and preserved.");
    expect(banner).toHaveTextContent('Plans will be announced soon.');
    expect(banner).not.toHaveTextContent('Choose a plan');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('keeps the countdown without a View Plans link during the trial', () => {
    auth = { trial: trial(12 * 60), serverClockOffsetMs: 0 };
    renderBanner();
    expect(screen.getByRole('status')).toHaveTextContent('Your free trial ends in 12 minutes');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('hides View Plans while the catalog is unknown (loading or failed)', () => {
    catalog = undefined;
    auth = { trial: trial(-10, 'trial_expired'), serverClockOffsetMs: 0 };
    renderBanner();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('treats published plans that are not purchasable as nothing to buy', () => {
    catalog = { ...PURCHASABLE, plans: PURCHASABLE.plans.map((p) => ({ ...p, purchasable: false })) };
    auth = { trial: trial(-10, 'trial_expired'), serverClockOffsetMs: 0 };
    renderBanner();
    expect(screen.getByRole('status')).toHaveTextContent('Plans will be announced soon.');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('never advertises a sandbox test plan as a plan to buy', () => {
    catalog = { ...PURCHASABLE, plans: PURCHASABLE.plans.map((p) => ({ ...p, code: 'sandbox_foundation', sandbox: true })) };
    auth = { trial: trial(-10, 'trial_expired'), serverClockOffsetMs: 0 };
    renderBanner();
    expect(screen.getByRole('status')).toHaveTextContent('Plans will be announced soon.');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it.each(['cancelled', 'expired', 'invalid'] as const)('says plans are coming for a %s plan', (state) => {
    auth = { trial: null, serverClockOffsetMs: 0, subscription: paidPlan({ state, writable: false }) };
    renderBanner();
    expect(screen.getByRole('status')).toHaveTextContent('Plans will be announced soon.');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('still links an overdue plan to its subscription status', () => {
    auth = { trial: null, serverClockOffsetMs: 0, subscription: paidPlan({ state: 'past_due', grace_period_end: '2026-11-08T12:00:00Z' }) };
    renderBanner();
    expect(screen.getByRole('link', { name: 'View Subscription' })).toHaveAttribute('href', '/settings/subscription');
  });
});

describe('TrialBanner on the Subscription page', () => {
  beforeEach(() => {
    refreshMe.mockReset().mockResolvedValue(null);
  });

  it.each(['/settings/subscription', '/settings?tab=subscription'])('renders nothing at %s (the status card says it)', (path) => {
    auth = { trial: trial(-10, 'trial_expired'), serverClockOffsetMs: 0 };
    const { container } = renderBanner(path);
    expect(container).toBeEmptyDOMElement();
    expect(plansEnabled).toHaveBeenLastCalledWith(false); // the page loads the catalog itself
  });

  it.each([
    paidPlan({ state: 'past_due', grace_period_end: '2026-11-08T12:00:00Z' }),
    paidPlan({ state: 'expired', writable: false }),
  ])('renders nothing for a $state plan there either', (subscription) => {
    auth = { trial: null, serverClockOffsetMs: 0, subscription };
    const { container } = renderBanner('/settings/subscription');
    expect(container).toBeEmptyDOMElement();
  });

  it('still shows on other settings tabs', () => {
    auth = { trial: trial(-10, 'trial_expired'), serverClockOffsetMs: 0 };
    renderBanner('/settings/profile');
    expect(screen.getByRole('status')).toHaveTextContent('Your free trial has ended.');
  });

  it('recognises the page in both URL forms only', () => {
    expect(isPlansPage('/settings/subscription', '')).toBe(true);
    expect(isPlansPage('/settings/subscription/', '')).toBe(true);
    expect(isPlansPage('/settings', '?tab=subscription')).toBe(true);
    expect(isPlansPage('/settings', '?tab=billing')).toBe(false);
    expect(isPlansPage('/subscriptions', '')).toBe(false);
    expect(isPlansPage('/dashboard', '?tab=subscription')).toBe(false);
  });

  it('does not ask for the catalog while a paid plan is in good standing', () => {
    auth = { trial: null, serverClockOffsetMs: 0, subscription: paidPlan({}) };
    renderBanner();
    expect(plansEnabled).toHaveBeenLastCalledWith(false);
  });
});

describe('TrialBanner for a paid plan', () => {
  beforeEach(() => {
    refreshMe.mockReset();
  });

  it('renders nothing while the plan is active', () => {
    auth = { trial: null, serverClockOffsetMs: 0, subscription: paidPlan({}) };
    const { container } = renderBanner();
    expect(container).toBeEmptyDOMElement();
  });

  it('warns while a payment is overdue, with the grace deadline', () => {
    auth = {
      trial: null,
      serverClockOffsetMs: 0,
      subscription: paidPlan({ state: 'past_due', grace_period_end: '2026-11-08T12:00:00Z' }),
    };
    renderBanner();
    const banner = screen.getByRole('status');
    expect(banner).toHaveTextContent('Your plan payment is overdue.');
    expect(banner).toHaveTextContent(/You can keep working until 08 Nov 2026/);
    expect(screen.getByRole('link', { name: 'View Subscription' })).toHaveAttribute('href', '/settings/subscription');
  });

  it.each(['cancelled', 'expired', 'invalid'] as const)('shows a calm message once the plan is %s', (state) => {
    auth = { trial: null, serverClockOffsetMs: 0, subscription: paidPlan({ state, writable: false }) };
    renderBanner();
    const banner = screen.getByRole('status');
    expect(banner).toHaveTextContent('Your plan is not active.');
    expect(banner).toHaveTextContent("Your organization's data is safe and preserved.");
    expect(screen.getByRole('link', { name: 'View Plans' })).toHaveAttribute('href', '/settings/subscription');
  });
});

describe('formatTimeLeft', () => {
  it.each([
    [45, '45 seconds'],
    [1, '1 second'],
    [60, '1 minute'],
    [61, '2 minutes'],
    [12 * 60, '12 minutes'],
    [90 * 60, '2 hours'],
    [14 * 24 * 3600, '14 days'],
  ])('%s seconds -> %s', (seconds, text) => {
    expect(formatTimeLeft(seconds)).toBe(text);
  });
});
