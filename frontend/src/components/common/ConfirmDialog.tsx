import type { ReactNode } from 'react';
import { AlertTriangle, HelpCircle } from 'lucide-react';
import { Modal } from './Modal';
import { Button } from './Button';

export interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title: string;
  /** Short explanation shown under the title. */
  description?: string;
  /** Optional extra content (e.g. a reason input). */
  children?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'danger';
  isLoading?: boolean;
  /** Disable the confirm button (e.g. required reason missing). */
  confirmDisabled?: boolean;
}

export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  children,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  isLoading = false,
  confirmDisabled = false,
}: ConfirmDialogProps) {
  const isDanger = variant === 'danger';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} disabled={isLoading}>
            {cancelLabel}
          </Button>
          <Button
            variant={isDanger ? 'danger' : 'primary'}
            size="sm"
            onClick={() => void onConfirm()}
            isLoading={isLoading}
            disabled={confirmDisabled}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="flex items-start gap-3.5">
        <div
          className={
            isDanger
              ? 'p-2.5 rounded-xl bg-rose-50 text-rose-600 border border-rose-100 shrink-0'
              : 'p-2.5 rounded-xl bg-blue-50 text-brand-600 border border-blue-100 shrink-0'
          }
        >
          {isDanger ? <AlertTriangle className="w-5 h-5" /> : <HelpCircle className="w-5 h-5" />}
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          {description && <p className="text-sm text-slate-600 leading-relaxed">{description}</p>}
          {children}
        </div>
      </div>
    </Modal>
  );
}
