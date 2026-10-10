import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ExpensesProvider } from '../ExpensesContext';
import { ExpenseSummary } from './ExpenseSummary';
import { expenseService } from '../../../services/expenseService';
import { addDays, todayIso } from '../../../utils/format';
import type { Expense } from '../types';

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

function expense(over: Partial<Expense>): Expense {
  return {
    id: 'EXP-1',
    name: 'Expense',
    date: todayIso(),
    category: 'Travel',
    amount: 0,
    currency: 'INR',
    billable: false,
    paymentMethod: 'Cash',
    paidBy: 'Ops',
    status: 'recorded',
    createdAt: '2026-01-01T00:00:00Z',
    ...over,
  };
}

/** The value shown under a KPI label. */
const kpiValue = (label: string) => screen.getByText(label).nextElementSibling?.textContent;

describe('<ExpenseSummary />', () => {
  beforeEach(() => {
    vi.mocked(expenseService.listRecurring).mockResolvedValue([]);
  });

  it('counts every non-cancelled expense dated this month under "Incurred This Month" (BUG-20)', async () => {
    const thisMonth = todayIso();
    const lastMonth = `${addDays(`${thisMonth.slice(0, 7)}-01`, -1)}`;
    vi.mocked(expenseService.list).mockResolvedValue([
      // Non-billable and recorded: the cards previously counted only billable, un-invoiced ones.
      expense({ id: 'a', amount: 1180.4 }),
      expense({ id: 'b', amount: 1180.4, billable: true, status: 'invoiced' }),
      expense({ id: 'c', amount: 1180.4, status: 'reimbursed' }),
      expense({ id: 'd', amount: 500, status: 'cancelled' }),
      expense({ id: 'e', amount: 700, date: lastMonth }),
    ]);
    render(
      <ExpensesProvider>
        <ExpenseSummary />
      </ExpensesProvider>
    );
    expect(await screen.findByText('₹3,541.20')).toBeInTheDocument();
    expect(kpiValue('Incurred This Month')).toBe('₹3,541.20');
    // Totals keep paise (BUG-29): 3 x 1180.40 + 500 + 700.
    expect(kpiValue('Total Expenses')).toBe('₹4,741.20');
  });
});
