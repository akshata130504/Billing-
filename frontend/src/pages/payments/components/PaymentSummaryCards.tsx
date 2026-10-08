import { usePayments } from '../PaymentsContext';
import { CheckCircle2, Clock, RotateCcw, CreditCard } from 'lucide-react';
import { formatMoney } from '../../../utils/format';
import { usePageSpec } from '../../../appUi/usePageSpec';

export function PaymentSummaryCards() {
  const ui = usePageSpec('payments');
  const { summary, filters, total } = usePayments();

  // The totals honour the active filters, so say so rather than implying they
  // are always organization-wide.
  const isFiltered =
    filters.searchQuery.trim() !== '' ||
    filters.statusTab !== 'all' ||
    filters.customer !== 'all' ||
    filters.paymentMethod !== 'all' ||
    filters.status !== 'all';

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl px-4 py-3.5 shadow-2xs">
      {isFiltered && (
        <p className="text-[10.5px] text-slate-400 mb-2.5">
          Totals cover the {total} payment{total === 1 ? '' : 's'} matching the current filters.
        </p>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 divide-y md:divide-y-0 md:divide-x divide-slate-100" {...ui.edit('kpis')}>
        {ui.render('kpis', {
          collected: (item, edit) => (
            <div className="flex items-center gap-3" {...edit}>
              <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
                <CheckCircle2 className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-medium text-slate-500 block uppercase tracking-wider">
                  {item.label}
                </span>
                <span className="text-base font-bold text-slate-900 tracking-tight">
                  {formatMoney(summary.totalCollected)}
                </span>
                {item.caption && <span className="text-[10px] text-slate-400 block">{item.caption}</span>}
              </div>
            </div>
          ),
          pending: (item, edit) => (
            <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4" {...edit}>
              <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center shrink-0">
                <Clock className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-medium text-amber-700 block uppercase tracking-wider">
                  {item.label}
                </span>
                <span className="text-base font-bold text-amber-900 tracking-tight">
                  {formatMoney(summary.pendingProcessing)}
                </span>
                {item.caption && <span className="text-[10px] text-slate-400 block">{item.caption}</span>}
              </div>
            </div>
          ),
          refunded: (item, edit) => (
            <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4" {...edit}>
              <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
                <RotateCcw className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-medium text-slate-500 block uppercase tracking-wider">
                  {item.label}
                </span>
                <span className="text-base font-bold text-slate-800 tracking-tight">
                  {formatMoney(summary.totalRefunded)}
                </span>
                {item.caption && <span className="text-[10px] text-slate-400 block">{item.caption}</span>}
              </div>
            </div>
          ),
          failed: (item, edit) => (
            <div className="flex items-center gap-3 pt-3 md:pt-0 md:pl-4" {...edit}>
              <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
                <CreditCard className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <span className="text-[11px] font-medium text-blue-700 block uppercase tracking-wider">
                  {item.label}
                </span>
                <span className="text-base font-bold text-blue-900 tracking-tight">
                  {formatMoney(summary.unappliedCredit)}
                </span>
                {item.caption && <span className="text-[10px] text-slate-400 block">{item.caption}</span>}
              </div>
            </div>
          ),
        })}
      </div>
    </div>
  );
}
