import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ExpensesProvider } from '../ExpensesContext';
import { RecurringSummary } from './RecurringSummary';
import { expenseService } from '../../../services/expenseService';
import type { RecurringExpense } from '../types';

vi.mock('../../../services/expenseService', () => ({
  expenseService: { list: vi.fn(), listRecurring: vi.fn() },
}));

vi.mock('../../../services/apiClient', async (orig) => ({
  ...(await orig<typeof import('../../../services/apiClient')>()),
  tokenStorage: { hasSession: () => true },
}));

vi.mock('../../../components/common/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

function recurring(over: Partial<RecurringExpense>): RecurringExpense {
  return {
    id: 'REC-1',
    name: 'Recurring',
    category: 'Software',
    amount: 0,
    currency: 'INR',
    frequency: 'monthly',
    startDate: '2026-01-01',
    neverEnds: true,
    nextRun: '2026-11-01',
    billable: false,
    paymentMethod: 'Card',
    paidBy: 'Ops',
    status: 'active',
    createdAt: '2026-01-01T00:00:00Z',
    ...over,
  } as RecurringExpense;
}

const kpiValue = (label: string) => screen.getByText(label).nextElementSibling?.textContent ?? '';

describe('<RecurringSummary /> with several currencies (BUG-11)', () => {
  it('shows monthly and billable recurring cost per currency, never summed', async () => {
    vi.mocked(expenseService.list).mockResolvedValue([]);
    vi.mocked(expenseService.listRecurring).mockResolvedValue([
      recurring({ id: 'a', amount: 1180.4 }),
      // Yearly USD 1200 -> 100 a month; billable.
      recurring({ id: 'b', amount: 1200, currency: 'USD', frequency: 'yearly', billable: true }),
      recurring({ id: 'c', amount: 367.25, currency: 'AED' }),
      // Paused profiles are not counted.
      recurring({ id: 'd', amount: 999, currency: 'USD', status: 'paused' }),
    ]);
    render(
      <ExpensesProvider>
        <RecurringSummary />
      </ExpensesProvider>
    );

    await waitFor(() => expect(kpiValue('Monthly Recurring Cost')).toContain('$100.00'));
    const monthly = kpiValue('Monthly Recurring Cost');
    expect(monthly).toContain('₹1,180.40');
    expect(monthly).toMatch(/AED\s?367\.25/);
    // Summing the three as rupees would give 1,647.65.
    expect(monthly).not.toContain('1,647.65');
    expect(kpiValue('Billable Recurring')).toBe('$100.00');
    expect(kpiValue('Active Profiles')).toBe('3');
  });
});
