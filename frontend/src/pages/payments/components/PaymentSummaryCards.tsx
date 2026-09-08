import { usePayments } from '../PaymentsContext';
import { formatINR } from '../mockPayments';
import { CheckCircle2, Clock, RotateCcw, CreditCard } from 'lucide-react';

export function PaymentSummaryCards() {
  const { summary } = usePayments();

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl px-4 py-3.5 shadow-2xs">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 divide-y md:divide-y-0 md:divide-x divide-slate-100">
        {/* Total Collected */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-slate-500 block uppercase tracking-wider">
              Total Collected
            </span>
            <span className="text-base font-bold text-slate-900 tracking-tight">
              {formatINR(summary.totalCollected)}
            </span>
          </div>
        </div>

        {/* Pending / Processing */}
        <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4">
          <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center shrink-0">
            <Clock className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-amber-700 block uppercase tracking-wider">
              Pending / Processing
            </span>
            <span className="text-base font-bold text-amber-900 tracking-tight">
              {formatINR(summary.pendingProcessing)}
            </span>
          </div>
        </div>

        {/* Refunded */}
        <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4">
          <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
            <RotateCcw className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-slate-500 block uppercase tracking-wider">
              Total Refunded
            </span>
            <span className="text-base font-bold text-slate-800 tracking-tight">
              {formatINR(summary.totalRefunded)}
            </span>
          </div>
        </div>

        {/* Unapplied / Customer Credit */}
        <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4">
          <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
            <CreditCard className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-blue-700 block uppercase tracking-wider">
              Unapplied / Credit
            </span>
            <span className="text-base font-bold text-blue-900 tracking-tight">
              {formatINR(summary.unappliedCredit)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
