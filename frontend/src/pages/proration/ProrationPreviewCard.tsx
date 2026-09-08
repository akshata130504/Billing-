import { ArrowRight, CalendarClock, Info } from 'lucide-react';
import type { SubscriptionChangePreviewOut, ProrationEffectiveType } from '../../types/proration';
import { Badge } from '../../components/common/Badge';
import { LoadingSpinner } from '../../components/common/LoadingState';
import { cn } from '../../utils/cn';
import { formatMoney, formatDate, parseMoney } from '../../utils/format';
import { changeTypeLabel, changeTypeVariant, formatQuantity } from './prorationLabels';

interface ProrationPreviewCardProps {
  preview: SubscriptionChangePreviewOut | null;
  loading: boolean;
  error: string | null;
  effectiveType: ProrationEffectiveType;
  currency: string;
  /** True when the form does not describe any change (same plan, same quantity). */
  isNoop: boolean;
}

function Row({
  label,
  value,
  hint,
  tone = 'neutral',
  emphasis = false,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'neutral' | 'credit' | 'charge';
  emphasis?: boolean;
}) {
  return (
    <div className={cn('flex items-start justify-between gap-4 py-2.5', emphasis && 'pt-3')}>
      <div className="min-w-0">
        <div className={cn('text-xs', emphasis ? 'font-semibold text-slate-900' : 'font-medium text-slate-700')}>{label}</div>
        {hint && <div className="text-[11px] text-slate-400 mt-0.5">{hint}</div>}
      </div>
      <div
        className={cn(
          'tabular-nums shrink-0',
          emphasis ? 'text-lg font-bold' : 'text-sm font-semibold',
          tone === 'credit' && 'text-emerald-700',
          tone === 'charge' && 'text-slate-900',
          tone === 'neutral' && 'text-slate-900'
        )}
      >
        {value}
      </div>
    </div>
  );
}

export function ProrationPreviewCard({ preview, loading, error, effectiveType, currency, isNoop }: ProrationPreviewCardProps) {
  const shell = 'bg-slate-50/70 rounded-xl border border-slate-200 h-full';

  if (isNoop) {
    return (
      <div className={cn(shell, 'flex flex-col items-center justify-center text-center p-8')}>
        <div className="p-3 rounded-full bg-white border border-slate-200 text-slate-400 mb-3">
          <Info className="w-5 h-5" />
        </div>
        <p className="text-sm font-semibold text-slate-800">Nothing to preview yet</p>
        <p className="text-xs text-slate-500 mt-1 max-w-xs leading-relaxed">
          Pick a different plan or adjust the quantity to see the prorated credit, charge and net amount.
        </p>
      </div>
    );
  }

  if (loading && !preview) {
    return (
      <div className={cn(shell, 'flex flex-col items-center justify-center p-8')}>
        <LoadingSpinner />
        <p className="mt-3 text-xs font-medium text-slate-500">Calculating proration...</p>
      </div>
    );
  }

  if (error && !preview) {
    return (
      <div className="bg-rose-50/60 rounded-xl border border-rose-200 p-5 h-full">
        <p className="text-sm font-semibold text-rose-900">Preview unavailable</p>
        <p className="text-xs text-rose-700 mt-1 leading-relaxed">{error}</p>
      </div>
    );
  }

  if (!preview) return null;

  const net = parseMoney(preview.net_amount);
  const netPositive = net > 0;
  const netNegative = net < 0;
  const isEndOfTerm = effectiveType === 'end_of_term';
  const oldRate = parseMoney(preview.old_plan.unit_amount) * parseMoney(preview.old_quantity);
  const newRate = parseMoney(preview.new_plan.unit_amount) * parseMoney(preview.new_quantity);
  const usedPct = preview.total_days > 0 ? Math.min(100, Math.round((preview.days_used / preview.total_days) * 100)) : 0;

  return (
    <div className={cn(shell, 'relative overflow-hidden', loading && 'opacity-70 transition-opacity')}>
      {loading && (
        <div className="absolute top-3 right-3">
          <LoadingSpinner size="sm" />
        </div>
      )}

      <div className="px-5 py-4 border-b border-slate-200 bg-white/60">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant={changeTypeVariant(preview.change_type)} size="sm">
            {changeTypeLabel(preview.change_type)}
          </Badge>
          {error && <span className="text-[11px] text-rose-600 font-medium">{error}</span>}
        </div>
        <div className="mt-3 flex items-center gap-3 text-sm">
          <div className="min-w-0">
            <div className="font-semibold text-slate-900 truncate">{preview.old_plan.name}</div>
            <div className="text-[11px] text-slate-500 tabular-nums">
              {formatQuantity(preview.old_quantity)} × {formatMoney(preview.old_plan.unit_amount, currency)} ={' '}
              {formatMoney(oldRate, currency)}
            </div>
          </div>
          <ArrowRight className="w-4 h-4 text-slate-400 shrink-0" />
          <div className="min-w-0">
            <div className="font-semibold text-brand-700 truncate">{preview.new_plan.name}</div>
            <div className="text-[11px] text-slate-500 tabular-nums">
              {formatQuantity(preview.new_quantity)} × {formatMoney(preview.new_plan.unit_amount, currency)} ={' '}
              {formatMoney(newRate, currency)}
            </div>
          </div>
        </div>
      </div>

      <div className="px-5 py-4">
        {/* Period usage */}
        <div className="flex items-center justify-between text-[11px] text-slate-500 mb-1.5">
          <span>{formatDate(preview.period_start)}</span>
          <span className="inline-flex items-center gap-1 font-medium text-slate-700">
            <CalendarClock className="w-3.5 h-3.5" />
            {isEndOfTerm ? 'Effective at period end' : `Effective ${formatDate(preview.effective_date)}`}
          </span>
          <span>{formatDate(preview.period_end)}</span>
        </div>
        <div className="h-2 rounded-full bg-slate-200 overflow-hidden flex">
          <div className="h-full bg-slate-400" style={{ width: `${isEndOfTerm ? 100 : usedPct}%` }} />
          <div className="h-full bg-brand-500 flex-1" />
        </div>
        <div className="flex items-center justify-between text-[11px] text-slate-500 mt-1.5 tabular-nums">
          <span>
            {isEndOfTerm ? preview.total_days : preview.days_used} of {preview.total_days} days used
          </span>
          <span>{isEndOfTerm ? 0 : preview.days_remaining} days remaining</span>
        </div>

        {isEndOfTerm ? (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50/70 p-3.5">
            <p className="text-xs font-semibold text-amber-900">No mid-cycle proration</p>
            <p className="text-xs text-amber-800 mt-1 leading-relaxed">
              The change will be scheduled and applied on {formatDate(preview.period_end)}. The current period is billed as-is;
              from the next period the subscription renews at {formatMoney(newRate, currency)} per cycle.
            </p>
          </div>
        ) : (
          <div className="mt-3 divide-y divide-slate-200">
            <Row
              label="Unused credit on current plan"
              hint={`${formatMoney(oldRate, currency)} × ${preview.days_remaining} ÷ ${preview.total_days} days`}
              value={`− ${formatMoney(preview.unused_credit, currency)}`}
              tone="credit"
            />
            <Row
              label="Prorated charge for new plan"
              hint={`${formatMoney(newRate, currency)} × ${preview.days_remaining} ÷ ${preview.total_days} days`}
              value={`+ ${formatMoney(preview.remaining_charge, currency)}`}
              tone="charge"
            />
            <Row
              label={netPositive ? 'Customer owes now' : netNegative ? 'Customer is credited' : 'Net adjustment'}
              hint={
                netPositive
                  ? 'A prorated invoice is raised; the credit note is offset against it automatically.'
                  : netNegative
                  ? 'A credit note for the difference is issued to the customer.'
                  : 'Credit and charge cancel out; no invoice or credit note is raised.'
              }
              value={formatMoney(Math.abs(net), currency)}
              emphasis
            />
          </div>
        )}
      </div>
    </div>
  );
}
