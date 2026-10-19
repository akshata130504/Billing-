import { Project } from '../types';
import { Modal } from '../../../components/common/Modal';
import { Button } from '../../../components/common/Button';
import { AlertTriangle } from 'lucide-react';

interface DeleteConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  project: Project | null;
}

export function DeleteConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  project,
}: DeleteConfirmModalProps) {
  if (!project) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Delete Project Confirmation"
      size="sm"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => {
              onConfirm();
              onClose();
            }}
          >
            Yes, Delete Project
          </Button>
        </>
      }
    >
      <div className="flex items-start gap-3.5">
        <div className="p-2.5 rounded-xl bg-rose-50 text-rose-600 border border-rose-100 shrink-0">
          <AlertTriangle className="w-5 h-5" />
        </div>
        <div className="space-y-1.5 text-xs text-slate-600">
          <p className="font-medium text-slate-900">
            Are you sure you want to delete <strong className="text-slate-900">{project.name}</strong>?
          </p>
          <p className="leading-relaxed">
            This will remove the project along with its linked billing ledgers and timesheets from the view. This action cannot be reversed.
          </p>
        </div>
      </div>
    </Modal>
  );
}
