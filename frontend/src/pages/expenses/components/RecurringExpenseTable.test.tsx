import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RecurringExpenseTable } from './RecurringExpenseTable';
import type { RecurringExpense } from '../types';

const profile: RecurringExpense = {
  id: 'REC-1',
  name: 'hiii',
  category: 'Software',
  amount: 2000,
  currency: 'INR',
  frequency: 'monthly',
  startDate: '2026-09-17',
  neverEnds: true,
  nextRun: '2026-10-17',
  billable: false,
  paymentMethod: 'Corporate Card',
  paidBy: 'Ops',
  status: 'active',
  createdAt: '2026-09-17T00:00:00Z',
} as RecurringExpense;

function renderTable(onDuplicate = vi.fn()) {
  return render(
    <MemoryRouter>
      <RecurringExpenseTable
        recurringExpenses={[profile]}
        onEdit={vi.fn()}
        onDuplicate={onDuplicate}
        onDelete={vi.fn()}
        onToggleStatus={vi.fn()}
        onNew={vi.fn()}
      />
    </MemoryRouter>,
  );
}

// QA (new-bugs PDF, "Recurring Expenses"): the 3-dot menu was clipped by the table container and
// needed scrolling. It now renders in a body portal, like the expense table's menu.
describe('RecurringExpenseTable row actions menu', () => {
  it('renders the menu outside the table container so it cannot be clipped', () => {
    const { container } = renderTable();
    const toggle = screen.getByTitle('More Actions');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    const menu = screen.getByRole('menu');
    expect(container.contains(menu)).toBe(false);
    expect(document.body.contains(menu)).toBe(true);
    expect(menu.className).toContain('fixed');
    expect(screen.getByTitle('More Actions')).toHaveAttribute('aria-expanded', 'true');
  });

  it('shows every action and runs the chosen one', () => {
    const onDuplicate = vi.fn();
    renderTable(onDuplicate);
    fireEvent.click(screen.getByTitle('More Actions'));
    expect(screen.getByText('Duplicate')).toBeInTheDocument();
    expect(screen.getByText(/Delete Profile/)).toBeInTheDocument();
    fireEvent.click(screen.getByText('Duplicate'));
    expect(onDuplicate).toHaveBeenCalledWith('REC-1');
  });

  it('closes on scroll so the fixed menu never drifts from its button', () => {
    renderTable();
    fireEvent.click(screen.getByTitle('More Actions'));
    fireEvent.scroll(window);
    expect(screen.queryByRole('menu')).toBeNull();
  });
});
