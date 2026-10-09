import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TrialInfo } from '../../types/api';

let auth: { trial: TrialInfo | null; serverClockOffsetMs: number };
const refreshMe = vi.fn();

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ trial: auth.trial, serverClockOffsetMs: auth.serverClockOffsetMs, refreshMe }),
}));

import { TrialBanner, formatTimeLeft } from './TrialBanner';

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

function renderBanner() {
  return render(
    <MemoryRouter>
      <TrialBanner />
    </MemoryRouter>,
  );
}

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
