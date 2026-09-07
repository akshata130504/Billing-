import { Plus, UserPlus } from 'lucide-react';
import { useToast } from '../../components/common/Toast';

export function QuickActionsCard() {
  const { showToast } = useToast();

  const handleAction = (title: string, phase: string) => {
    showToast('info', title, `${title} workflow scheduled in ${phase}.`);
  };

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-3.5">
      <h3 className="text-sm font-bold text-slate-900 tracking-tight">
        Quick Actions
      </h3>

      <div className="space-y-2">
        {/* Primary Action Button */}
        <button
          type="button"
          onClick={() => handleAction('Create Invoice', 'Phase 2')}
          className="w-full py-2.5 px-4 bg-brand-600 hover:bg-brand-700 active:bg-brand-800 text-white font-semibold text-xs rounded-xl shadow-xs flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
        >
          <Plus className="w-4 h-4 stroke-[2.5]" />
          <span>Create Invoice</span>
        </button>

        {/* Secondary Outline Buttons */}
        <button
          type="button"
          onClick={() => handleAction('Create Quote', 'Phase 2')}
          className="w-full py-2.5 px-4 bg-white hover:bg-slate-50 text-slate-700 font-medium text-xs rounded-xl border border-slate-200 hover:border-slate-300 flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
        >
          <Plus className="w-3.5 h-3.5 text-slate-500" />
          <span>Create Quote</span>
        </button>

        <button
          type="button"
          onClick={() => handleAction('Record Payment', 'Phase 3')}
          className="w-full py-2.5 px-4 bg-white hover:bg-slate-50 text-slate-700 font-medium text-xs rounded-xl border border-slate-200 hover:border-slate-300 flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
        >
          <Plus className="w-3.5 h-3.5 text-slate-500" />
          <span>Record Payment</span>
        </button>

        <button
          type="button"
          onClick={() => handleAction('Add Customer', 'Phase 1')}
          className="w-full py-2.5 px-4 bg-white hover:bg-slate-50 text-slate-700 font-medium text-xs rounded-xl border border-slate-200 hover:border-slate-300 flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
        >
          <UserPlus className="w-3.5 h-3.5 text-slate-500" />
          <span>Add Customer</span>
        </button>

        <button
          type="button"
          onClick={() => handleAction('Create Subscription', 'Phase 4')}
          className="w-full py-2.5 px-4 bg-white hover:bg-slate-50 text-slate-700 font-medium text-xs rounded-xl border border-slate-200 hover:border-slate-300 flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
        >
          <Plus className="w-3.5 h-3.5 text-slate-500" />
          <span>Create Subscription</span>
        </button>
      </div>
    </div>
  );
}
