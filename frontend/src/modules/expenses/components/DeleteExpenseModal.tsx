import { AlertTriangle } from 'lucide-react';

interface DeleteExpenseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  itemName: string;
  description?: string;
}

export function DeleteExpenseModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  itemName,
  description,
}: DeleteExpenseModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-150 p-6">
        <div className="flex items-start gap-3.5">
          <div className="w-10 h-10 rounded-full bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-600 shrink-0">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-bold text-slate-900">{title}</h3>
            <p className="text-xs text-slate-600 mt-1">
              Are you sure you want to delete <span className="font-semibold text-slate-900">"{itemName}"</span>?
            </p>
            <p className="text-[11px] text-slate-400 mt-1.5 leading-relaxed">
              {description ||
                'This will remove the expense from all financial ledgers and customer billing records. This action cannot be undone.'}
            </p>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              onConfirm();
              onClose();
            }}
            className="px-3.5 py-1.5 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-2xs transition-colors"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
