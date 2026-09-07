import { useExpenses } from '../ExpensesContext';
import { formatINR } from '../mockExpenses';
import { Receipt, CheckCircle, Wallet, Clock } from 'lucide-react';

export function ExpenseSummary() {
  const { summary } = useExpenses();

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl px-4 py-3 shadow-2xs">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 divide-y md:divide-y-0 md:divide-x divide-slate-100">
        {/* Total Expenses */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center shrink-0">
            <Wallet className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-slate-500 block uppercase tracking-wider">
              Total Expenses
            </span>
            <span className="text-base font-bold text-slate-900 tracking-tight">
              {formatINR(summary.total)}
            </span>
          </div>
        </div>

        {/* Billable */}
        <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
            <CheckCircle className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-emerald-700 block uppercase tracking-wider">
              Billable
            </span>
            <span className="text-base font-bold text-emerald-900 tracking-tight">
              {formatINR(summary.billable)}
            </span>
          </div>
        </div>

        {/* Non-Billable */}
        <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4">
          <div className="w-8 h-8 rounded-lg bg-slate-50 text-slate-600 flex items-center justify-center shrink-0">
            <Receipt className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-slate-500 block uppercase tracking-wider">
              Non-Billable
            </span>
            <span className="text-base font-bold text-slate-800 tracking-tight">
              {formatINR(summary.nonBillable)}
            </span>
          </div>
        </div>

        {/* Pending */}
        <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4">
          <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center shrink-0">
            <Clock className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-amber-700 block uppercase tracking-wider">
              Pending
            </span>
            <span className="text-base font-bold text-amber-900 tracking-tight">
              {formatINR(summary.pending)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
