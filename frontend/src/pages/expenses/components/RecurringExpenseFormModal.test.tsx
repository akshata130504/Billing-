import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RecurringExpenseFormModal } from './RecurringExpenseFormModal';

vi.mock('../../../hooks/useAuth', () => ({ useAuth: () => ({ user: { full_name: 'Tester' } }) }));
vi.mock('../useCustomerProjects', () => ({
  useCustomerProjects: () => ({ projects: [], loading: false, error: null }),
}));
vi.mock('../../../components/common/CustomerCombobox', () => ({
  CustomerCombobox: () => <div data-testid="customer-combobox" />,
}));

describe('<RecurringExpenseFormModal />', () => {
  it('renders nothing when closed', () => {
    render(<RecurringExpenseFormModal isOpen={false} onClose={vi.fn()} onSave={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens as an accessible dialog in document.body with the shared blurred backdrop', () => {
    const { container } = render(<RecurringExpenseFormModal isOpen onClose={vi.fn()} onSave={vi.fn()} />);
    const dialog = screen.getByRole('dialog', { name: 'New Recurring Expense' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(document.body.contains(dialog)).toBe(true);
    expect(container.contains(dialog)).toBe(false);
    expect(dialog.className).toContain('max-h-[90vh]');
    expect(screen.getByTestId('modal-backdrop').className).toContain('backdrop-blur-sm');
  });

  it('closes on Escape and backdrop click', () => {
    const onClose = vi.fn();
    render(<RecurringExpenseFormModal isOpen onClose={onClose} onSave={vi.fn()} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    fireEvent.click(screen.getByTestId('modal-backdrop'));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
