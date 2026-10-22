import { useExpenses } from '../ExpensesContext';
import { formatINR } from '../format';
import { Repeat, Calendar, CheckCircle2, IndianRupee } from 'lucide-react';
import { formatPerCurrency } from '../../../services/dashboardSummaryService';

export function RecurringSummary() {
  const { recurringSummary } = useExpenses();

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl px-4 py-3 shadow-2xs">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 divide-y md:divide-y-0 md:divide-x divide-slate-100">
        {/* Active Profiles */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center shrink-0">
            <Repeat className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-slate-500 block uppercase tracking-wider">
              Active Profiles
            </span>
            <span className="text-base font-bold text-slate-900 tracking-tight">
              {recurringSummary.activeProfiles}
            </span>
          </div>
        </div>

        {/* Monthly Recurring Cost */}
        <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4">
          <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center shrink-0">
            <IndianRupee className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-slate-500 block uppercase tracking-wider">
              Monthly Recurring Cost
            </span>
            <span className="text-base font-bold text-slate-900 tracking-tight">
              {formatPerCurrency(recurringSummary.monthlyRecurring, (r) => String(r.amount), (amount, currency) => formatINR(Number(amount), currency), 'INR')}
            </span>
          </div>
        </div>

        {/* Billable Recurring */}
        <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-emerald-700 block uppercase tracking-wider">
              Billable Recurring
            </span>
            <span className="text-base font-bold text-emerald-900 tracking-tight">
              {formatPerCurrency(recurringSummary.billableRecurring, (r) => String(r.amount), (amount, currency) => formatINR(Number(amount), currency), 'INR')}
            </span>
          </div>
        </div>

        {/* Next Run */}
        <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4">
          <div className="w-8 h-8 rounded-lg bg-sky-50 text-sky-600 flex items-center justify-center shrink-0">
            <Calendar className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-sky-700 block uppercase tracking-wider">
              Next Run
            </span>
            <span className="text-xs font-bold text-slate-800 tracking-tight truncate block">
              {recurringSummary.nextRun}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
