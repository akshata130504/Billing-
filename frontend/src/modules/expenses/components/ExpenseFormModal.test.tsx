import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ExpenseFormModal } from './ExpenseFormModal';

vi.mock('../../../hooks/useAuth', () => ({ useAuth: () => ({ user: { full_name: 'Tester' } }) }));
vi.mock('../useCustomerProjects', () => ({
  useCustomerProjects: () => ({ projects: [], loading: false, error: null }),
}));
vi.mock('../../../components/common/CustomerCombobox', () => ({
  CustomerCombobox: () => <div data-testid="customer-combobox" />,
}));

describe('<ExpenseFormModal />', () => {
  it('renders nothing when closed', () => {
    render(<ExpenseFormModal isOpen={false} onClose={vi.fn()} onSave={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens as an accessible dialog in document.body with the shared blurred backdrop', () => {
    const { container } = render(<ExpenseFormModal isOpen onClose={vi.fn()} onSave={vi.fn()} />);
    const dialog = screen.getByRole('dialog', { name: 'Record Expense' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(document.body.contains(dialog)).toBe(true);
    expect(container.contains(dialog)).toBe(false);
    expect(dialog.className).toContain('max-h-[90vh]');
    const backdrop = screen.getByTestId('modal-backdrop');
    expect(backdrop.className).toContain('backdrop-blur-sm');
    expect(backdrop.className).toContain('inset-0');
  });

  it('closes on Escape and backdrop click, and locks body scroll while open', () => {
    const onClose = vi.fn();
    const { unmount } = render(<ExpenseFormModal isOpen onClose={onClose} onSave={vi.fn()} />);
    expect(document.body.style.overflow).toBe('hidden');
    fireEvent.keyDown(window, { key: 'Escape' });
    fireEvent.click(screen.getByTestId('modal-backdrop'));
    expect(onClose).toHaveBeenCalledTimes(2);
    unmount();
    expect(document.body.style.overflow).not.toBe('hidden');
  });

  it('associates every field with its label (BUG-22)', () => {
    render(<ExpenseFormModal isOpen onClose={vi.fn()} onSave={vi.fn()} />);
    for (const label of [/^Expense Name/, /^Expense Date/, /^Category/, /^Amount/, /^Currency/, /^Paid By/, /^Payment Method/]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getByLabelText(/^Category/).tagName).toBe('SELECT');
    expect(screen.getByLabelText(/^Amount/)).toHaveAttribute('type', 'number');
  });
});

