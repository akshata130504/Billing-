import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../services/portalCustomerService', () => ({
  portalCustomerService: {
    getPayments: async () => [
      {
        id: 'p1',
        payment_number: 'PAY-000029',
        created_at: '2026-09-26T10:00:00Z',
        amount: '1000.00',
        method: 'bank_transfer',
        gateway: 'manual',
        status: 'partially_refunded',
      },
    ],
    getPaymentMethods: async () => [],
  },
}));

import { PortalPaymentsPage } from './PortalPaymentsPage';

describe('<PortalPaymentsPage />', () => {
  it('shows a readable payment status instead of the raw enum value', async () => {
    render(<PortalPaymentsPage />);

    expect(await screen.findByText('PAY-000029')).toBeInTheDocument();
    expect(screen.getByText('Partially refunded')).toBeInTheDocument();
    expect(screen.queryByText('partially_refunded')).toBeNull();
  });
});
