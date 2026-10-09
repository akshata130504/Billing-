import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

let trialState: 'trialing' | 'trial_expired' | null;
const showToast = vi.fn();

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ trial: trialState ? { state: trialState } : null }),
}));
vi.mock('../../components/common/Toast', () => ({ useToast: () => ({ showToast }) }));

import { SubscriptionTab } from './SubscriptionTab';

describe('SubscriptionTab (display only)', () => {
  beforeEach(() => {
    trialState = 'trial_expired';
    showToast.mockReset();
  });

  it('renders the three plan cards with feature limits and monthly / yearly price rows', () => {
    render(<SubscriptionTab />);
    const cards = screen.getAllByTestId('plan-card');
    expect(cards).toHaveLength(3);
    expect(within(cards[0]).getByText('Up to 5 features')).toBeInTheDocument();
    expect(within(cards[1]).getByText('Up to 10 features')).toBeInTheDocument();
    expect(within(cards[2]).getByText('Up to 15-20 features')).toBeInTheDocument();
    for (const card of cards) {
      expect(within(card).getByText('Monthly price')).toBeInTheDocument();
      expect(within(card).getByText('Yearly price')).toBeInTheDocument();
      expect(within(card).getByRole('button', { name: 'Choose Plan' })).toBeInTheDocument();
    }
  });

  it('does not invent prices', () => {
    render(<SubscriptionTab />);
    expect(screen.queryByText(/[₹$]\s?\d/)).not.toBeInTheDocument();
    expect(screen.getAllByText('To be announced')).toHaveLength(6);
  });

  it('explains the ended trial', () => {
    render(<SubscriptionTab />);
    expect(screen.getByText(/Your free trial has ended/)).toBeInTheDocument();
    expect(screen.getByText(/data is safe and preserved/)).toBeInTheDocument();
  });

  it('Choose Plan is a placeholder: it only says plan selection is not available yet', async () => {
    render(<SubscriptionTab />);
    await userEvent.click(screen.getAllByRole('button', { name: 'Choose Plan' })[1]);
    expect(showToast).toHaveBeenCalledTimes(1);
    expect(showToast.mock.calls[0][0]).toBe('info');
    expect(showToast.mock.calls[0][2]).toMatch(/not available yet/i);
  });

  it('still shows the plans during the trial', () => {
    trialState = 'trialing';
    render(<SubscriptionTab />);
    expect(screen.getAllByTestId('plan-card')).toHaveLength(3);
    expect(screen.getByText(/free trial with every feature included/i)).toBeInTheDocument();
  });
});
