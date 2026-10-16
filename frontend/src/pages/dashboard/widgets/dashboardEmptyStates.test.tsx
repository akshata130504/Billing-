import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PaymentStatusWidget } from './PaymentStatusWidget';
import { RevenueOverviewWidget } from './RevenueOverviewWidget';

// QA (new-bugs PDF, "Overview - Dashboard"): a brand-new organization must see empty states, not
// figures. The API returns 12 zero months for a new org, which used to draw an empty bar chart.
describe('dashboard widgets for an organization with no billing data', () => {
  const zeroTrend = Array.from({ length: 12 }, (_, i) => ({
    label: `M${i + 1} 2026`, invoiced: '0.00', revenue: '0.00',
  }));

  it('shows the revenue empty state when every month is zero', () => {
    render(<RevenueOverviewWidget revenue={{ trend: zeroTrend } as never} />);
    expect(screen.getByText('No revenue data available for this period.')).toBeInTheDocument();
  });

  it('draws the chart once there is any revenue', () => {
    const trend = zeroTrend.map((t, i) => (i === 11 ? { ...t, invoiced: '1180.00' } : t));
    render(<RevenueOverviewWidget revenue={{ trend } as never} />);
    expect(screen.queryByText('No revenue data available for this period.')).toBeNull();
  });

  it('labels the draft-invoice slice "Draft", not "Cancelled", and shows zero counts', () => {
    render(<PaymentStatusWidget pipeline={{ draft: { count: 2 } } as never} />);
    expect(screen.getByText('Draft')).toBeInTheDocument();
    expect(screen.queryByText('Cancelled')).toBeNull();
  });
});
