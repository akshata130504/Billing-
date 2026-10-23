import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanModal } from './PlanModal';

describe('<PlanModal /> dialog, limits and overflow', () => {
  it('renders as an accessible dialog portaled to document.body and closes on Escape', () => {
    const onClose = vi.fn();
    const { container } = render(<PlanModal isOpen onClose={onClose} onSave={vi.fn()} />);
    const dialog = screen.getByRole('dialog', { name: 'Create New Pricing Plan' });
    expect(document.body.contains(dialog)).toBe(true);
    expect(container.contains(dialog)).toBe(false);
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('rejects a base price above the maximum and does not save', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<PlanModal isOpen onClose={vi.fn()} onSave={onSave} />);
    const nameInput = document.body.querySelector('input[type="text"]') as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: 'Valid Plan Name' } });
    const basePrice = document.body.querySelectorAll('input[type="number"]')[0] as HTMLInputElement;
    expect(basePrice.max).toBe('999999999999.99');
    fireEvent.change(basePrice, { target: { value: '1000000000000' } });
    fireEvent.submit(basePrice.closest('form')!);
    expect(await screen.findByText(/Base price cannot exceed 999,999,999,999.99/)).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('clamps the preview quantity to 1,000,000 and keeps huge totals wrapped without NaN/exponent text', () => {
    render(<PlanModal isOpen onClose={vi.fn()} onSave={vi.fn()} />);
    const inputs = document.body.querySelectorAll('input[type="number"]');
    const basePrice = inputs[0] as HTMLInputElement;
    const qty = inputs[inputs.length - 1] as HTMLInputElement;
    expect(qty.max).toBe('1000000');

    fireEvent.change(basePrice, { target: { value: '999999999999.99' } });
    fireEvent.change(qty, { target: { value: '123456789012345' } });
    expect(qty.value).toBe('1000000');

    const total = screen.getByText('Final Total Amount').nextElementSibling as HTMLElement;
    const subtotal = screen.getByText('Calculated Subtotal').nextElementSibling as HTMLElement;
    for (const el of [total, subtotal]) {
      expect(el.className).toContain('break-all');
      expect(el.parentElement!.className).toContain('min-w-0');
      expect(el.textContent).not.toMatch(/NaN|Infinity|e\+/i);
    }
  });
});
