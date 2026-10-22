import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ExpenseTable } from './ExpenseTable';
import type { Expense } from '../types';

const expense: Expense = {
  id: 'EXP-1',
  name: 'Cloud hosting',
  date: '2026-01-15',
  category: 'Cloud Services',
  amount: 1200,
  currency: 'INR',
  billable: true,
  paymentMethod: 'Corporate Card',
  paidBy: 'Ops',
  status: 'billable',
  createdAt: '2026-01-15T00:00:00Z',
};

function renderTable(handlers: Partial<Record<'onDuplicate' | 'onDelete' | 'onAddToInvoice', ReturnType<typeof vi.fn>>> = {}) {
  const props = {
    expenses: [expense],
    viewMode: 'list' as const,
    onEdit: vi.fn(),
    onDuplicate: handlers.onDuplicate ?? vi.fn(),
    onDelete: handlers.onDelete ?? vi.fn(),
    onAddToInvoice: handlers.onAddToInvoice ?? vi.fn(),
    onRecordNew: vi.fn(),
  };
  return render(
    <MemoryRouter initialEntries={['/expenses']}>
      <Routes>
        <Route path="/expenses" element={<ExpenseTable {...props} />} />
        <Route path="/expenses/:id" element={<div>expense detail page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ExpenseTable row actions menu', () => {
  it('renders the menu in a body portal so the table container cannot clip it', () => {
    const { container } = renderTable();
    fireEvent.click(screen.getByTitle('More Actions'));
    const menu = screen.getByRole('menu');
    expect(container.contains(menu)).toBe(false);
    expect(document.body.contains(menu)).toBe(true);
    expect(menu.className).toContain('fixed');
  });

  it('runs the action without navigating to the row detail page', () => {
    const onDuplicate = vi.fn();
    renderTable({ onDuplicate });
    fireEvent.click(screen.getByTitle('More Actions'));
    fireEvent.click(screen.getByText('Duplicate'));
    expect(onDuplicate).toHaveBeenCalledWith('EXP-1');
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.queryByText('expense detail page')).toBeNull();
  });

  it('closes on scroll (a fixed menu would otherwise drift from its button)', () => {
    renderTable();
    fireEvent.click(screen.getByTitle('More Actions'));
    expect(screen.getByRole('menu')).toBeTruthy();
    fireEvent.scroll(window);
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.queryByText('expense detail page')).toBeNull();
  });
});
