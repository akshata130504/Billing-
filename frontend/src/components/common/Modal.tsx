import React, { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../../utils/cn';
import { X } from 'lucide-react';

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface ModalShellProps {
  onClose: () => void;
  /** id of the element that labels the dialog (aria-labelledby) */
  labelledBy: string;
  /** classes for the dialog card (width, background, max-height, ...) */
  className?: string;
  /** classes added to the full-screen overlay container */
  containerClassName?: string;
  children: React.ReactNode;
}

/**
 * Shared modal shell: portals to document.body with ONE consistent blurred backdrop
 * above the sidebar/header, role=dialog + aria-modal, Escape / backdrop-click close,
 * body scroll lock, focus move-in/restore and a Tab focus trap.
 * Mount it only while the dialog is open.
 */
export function ModalShell({ onClose, labelledBy, className, containerClassName, children }: ModalShellProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    if (dialog && !dialog.contains(document.activeElement)) dialog.focus();
    return () => {
      previouslyFocused?.focus?.();
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCloseRef.current();
        return;
      }
      if (e.key === 'Tab' && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const atStart = document.activeElement === first || document.activeElement === dialogRef.current;
        if (e.shiftKey && atStart) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Prevent the page behind the dialog from scrolling while it is open
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  return createPortal(
    <div
      className={cn(
        'fixed inset-0 z-[60] flex items-center justify-center p-4 overflow-y-auto',
        containerClassName
      )}
    >
      {/* Backdrop */}
      <div
        data-testid="modal-backdrop"
        className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm transition-opacity"
        onClick={() => onCloseRef.current()}
        aria-hidden="true"
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        className={cn('relative z-10 focus:outline-none', className)}
      >
        {children}
      </div>
    </div>,
    document.body
  );
}

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

export function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: ModalProps) {
  const titleId = useId();

  if (!isOpen) return null;

  const sizeClasses = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
  };

  return (
    <ModalShell
      onClose={onClose}
      labelledBy={titleId}
      className={cn(
        'w-full bg-white rounded-xl shadow-modal border border-slate-200 overflow-hidden transform transition-all',
        sizeClasses[size]
      )}
    >
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-100 flex items-start justify-between gap-4">
        <div>
          <h3 id={titleId} className="text-base font-semibold text-slate-900 leading-6">
            {title}
          </h3>
          {description && <p className="mt-1 text-xs text-slate-500">{description}</p>}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500"
          aria-label="Close dialog"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Content */}
      <div className="px-6 py-5">{children}</div>

      {/* Footer */}
      {footer && (
        <div className="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-2.5">
          {footer}
        </div>
      )}
    </ModalShell>
  );
}
