import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PublicAutopay } from '../../types/api';

const getAutopay = vi.fn();
const confirmAutopay = vi.fn();
vi.mock('../../services/publicService', () => ({
  publicService: { getAutopay: (...a: unknown[]) => getAutopay(...a), confirmAutopay: (...a: unknown[]) => confirmAutopay(...a) },
}));

let lastOptions: RazorpayCheckoutOptions | null = null;
const open = vi.fn();
vi.mock('./razorpayLoader', () => ({
  loadRazorpayCheckout: () =>
    Promise.resolve(
      class {
        constructor(options: RazorpayCheckoutOptions) {
          lastOptions = options;
        }
        open = open;
        close = vi.fn();
        on = vi.fn();
      }
    ),
}));

import { AutopayAuthorizePage, cycleLabel } from './AutopayAuthorizePage';

const VIEW: PublicAutopay = {
  status: 'created',
  can_authorize: true,
  organization_name: 'Acme Pvt Ltd',
  plan_name: 'Pro',
  subscription_number: 'SUB-000001',
  amount: '1180.00',
  currency: 'INR',
  period: 'monthly',
  interval: 1,
  total_count: 120,
  start_at: '2026-11-15T04:30:00+00:00',
  authorized_at: null,
  gateway_subscription_id: 'sub_TEST000000001',
  key_id: 'rzp_test_key',
  prefill: { name: 'Ravi', email: 'ravi@example.test', contact: '+919999999999' },
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/autopay/tok123']}>
      <Routes>
        <Route path="/autopay/:token" element={<AutopayAuthorizePage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('AutopayAuthorizePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    lastOptions = null;
  });

  it('labels the cycle', () => {
    expect(cycleLabel('monthly', 1)).toBe('every month');
    expect(cycleLabel('monthly', 3)).toBe('every 3 months');
    expect(cycleLabel('yearly', 1)).toBe('every year');
  });

  it('opens Razorpay Checkout for the subscription (not an order) and lets the server decide', async () => {
    getAutopay.mockResolvedValue(VIEW);
    confirmAutopay.mockResolvedValue({ ...VIEW, status: 'authenticated', can_authorize: false });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /set up autopay/i }));
    await waitFor(() => expect(open).toHaveBeenCalled());
    expect(lastOptions?.subscription_id).toBe('sub_TEST000000001');
    expect(lastOptions?.order_id).toBeUndefined();
    expect(lastOptions?.key).toBe('rzp_test_key');

    lastOptions?.handler({
      razorpay_payment_id: 'pay_1',
      razorpay_subscription_id: 'sub_TEST000000001',
      razorpay_signature: 'sig',
      razorpay_order_id: '',
    });
    expect(await screen.findByText('AutoPay is set up')).toBeInTheDocument();
    expect(confirmAutopay).toHaveBeenCalledWith('tok123', {
      razorpay_payment_id: 'pay_1',
      razorpay_subscription_id: 'sub_TEST000000001',
      razorpay_signature: 'sig',
    });
  });

  it('does not claim success while Razorpay has not confirmed the mandate', async () => {
    getAutopay.mockResolvedValue(VIEW);
    confirmAutopay.mockResolvedValue({ ...VIEW, status: 'created' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /set up autopay/i }));
    await waitFor(() => expect(open).toHaveBeenCalled());
    lastOptions?.handler({ razorpay_payment_id: 'pay_1', razorpay_signature: 'sig', razorpay_order_id: '' });
    expect(await screen.findByText('Waiting for confirmation')).toBeInTheDocument();
    expect(screen.queryByText('AutoPay is set up')).not.toBeInTheDocument();
  });

  it('shows a dead link instead of a button when the request cannot be authorised', async () => {
    getAutopay.mockResolvedValue({ ...VIEW, status: 'cancelled', can_authorize: false, key_id: null, gateway_subscription_id: null });
    renderPage();
    expect(await screen.findByText('This AutoPay request is cancelled')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /set up autopay/i })).not.toBeInTheDocument();
  });
});
