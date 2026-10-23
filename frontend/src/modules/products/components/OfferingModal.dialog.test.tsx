import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { OfferingModal } from './OfferingModal';

describe('OfferingModal dialog', () => {
  it('renders nothing when closed', () => {
    render(<OfferingModal isOpen={false} onClose={vi.fn()} onSave={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens as an accessible dialog in document.body with the shared blurred backdrop and closes on Escape', () => {
    const onClose = vi.fn();
    const { container } = render(<OfferingModal isOpen onClose={onClose} onSave={vi.fn()} />);
    const dialog = screen.getByRole('dialog', { name: 'Create Commercial Offering' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(document.body.contains(dialog)).toBe(true);
    expect(container.contains(dialog)).toBe(false);
    expect(screen.getByTestId('modal-backdrop').className).toContain('backdrop-blur-sm');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
