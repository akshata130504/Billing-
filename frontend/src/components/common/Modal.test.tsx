import { describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { Modal, ModalShell } from './Modal';

describe('<Modal />', () => {
  it('renders nothing when closed', () => {
    render(
      <Modal isOpen={false} onClose={() => {}} title="Hidden">
        body
      </Modal>
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('portals the dialog into document.body, outside the render container', () => {
    const { container } = render(
      <Modal isOpen onClose={() => {}} title="Portal title">
        <p>content</p>
      </Modal>
    );
    const dialog = screen.getByRole('dialog');
    expect(document.body.contains(dialog)).toBe(true);
    expect(container.contains(dialog)).toBe(false);
  });

  it('exposes role=dialog, aria-modal and aria-labelledby pointing at the title', () => {
    render(
      <Modal isOpen onClose={() => {}} title="Labelled dialog">
        x
      </Modal>
    );
    const dialog = screen.getByRole('dialog', { name: 'Labelled dialog' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    const labelId = dialog.getAttribute('aria-labelledby')!;
    expect(document.getElementById(labelId)).toHaveTextContent('Labelled dialog');
  });

  it('uses one full-viewport blurred backdrop above the app chrome', () => {
    render(
      <Modal isOpen onClose={() => {}} title="Backdrop">
        x
      </Modal>
    );
    const backdrop = screen.getByTestId('modal-backdrop');
    expect(backdrop.className).toContain('fixed');
    expect(backdrop.className).toContain('inset-0');
    expect(backdrop.className).toContain('backdrop-blur-sm');
    expect(backdrop.parentElement!.className).toContain('fixed');
    expect(backdrop.parentElement!.className).toContain('inset-0');
    expect(backdrop.parentElement!.className).toContain('z-[60]');
  });

  it('closes on Escape and on backdrop click', () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen onClose={onClose} title="Close me">
        x
      </Modal>
    );
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('modal-backdrop'));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('does not close when clicking inside the dialog', () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen onClose={onClose} title="Stay">
        <button>inside</button>
      </Modal>
    );
    fireEvent.click(screen.getByText('inside'));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('locks body scroll while open and restores it on close', () => {
    document.body.style.overflow = 'auto';
    const { rerender } = render(
      <Modal isOpen onClose={() => {}} title="Lock">
        x
      </Modal>
    );
    expect(document.body.style.overflow).toBe('hidden');
    rerender(
      <Modal isOpen={false} onClose={() => {}} title="Lock">
        x
      </Modal>
    );
    expect(document.body.style.overflow).toBe('auto');
    document.body.style.overflow = '';
  });

  it('traps Tab / Shift+Tab focus inside the dialog', () => {
    render(
      <Modal isOpen onClose={() => {}} title="Trap" footer={<button>Last</button>}>
        <input aria-label="field" />
      </Modal>
    );
    const closeBtn = screen.getByRole('button', { name: 'Close dialog' });
    const last = screen.getByRole('button', { name: 'Last' });

    last.focus();
    fireEvent.keyDown(document.activeElement!, { key: 'Tab' });
    expect(document.activeElement).toBe(closeBtn);

    closeBtn.focus();
    fireEvent.keyDown(document.activeElement!, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it('moves focus into the dialog and returns it to the opener on close', () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Opener</button>
          <Modal isOpen={open} onClose={() => setOpen(false)} title="Focus">
            x
          </Modal>
        </>
      );
    }
    render(<Harness />);
    const opener = screen.getByText('Opener');
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole('dialog').contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.activeElement).toBe(opener);
  });
});

describe('<ModalShell />', () => {
  it('provides the same portal + aria + Escape behaviour for custom dialogs', () => {
    const onClose = vi.fn();
    const { container } = render(
      <ModalShell onClose={onClose} labelledBy="custom-title" className="w-full">
        <h2 id="custom-title">Custom</h2>
      </ModalShell>
    );
    const dialog = screen.getByRole('dialog', { name: 'Custom' });
    expect(container.contains(dialog)).toBe(false);
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});
