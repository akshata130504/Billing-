import { Fragment, type ReactNode } from 'react';
import { Search, Repeat } from 'lucide-react';
import type { SubscriptionOut } from '../../types/api';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { LoadingState } from '../../components/common/LoadingState';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { cn } from '../../utils/cn';
import { formatMoney, formatDate, humanize, statusVariant } from '../../utils/format';
import { formatQuantity, intervalLabel } from './prorationLabels';
import { usePageSpec } from '../../appUi/usePageSpec';

/** Columns whose header is right-aligned (their cells align themselves). */
const RIGHT_ALIGNED = new Set(['quantity', 'recurring', 'action']);

interface SubscriptionPickerProps {
  subscriptions: SubscriptionOut[];
  selectedId: string | null;
  loading: boolean;
  error: string | null;
  searchQuery: string;
  onSearchChange: (value: string) => void;
  onSearchSubmit: () => void;
  onSelect: (subscription: SubscriptionOut) => void;
  onRetry: () => void;
  canCreate: boolean;
  onCreateNew: () => void;
}

export function SubscriptionPicker({
  subscriptions,
  selectedId,
  loading,
  error,
  searchQuery,
  onSearchChange,
  onSearchSubmit,
  onSelect,
  onRetry,
  canCreate,
  onCreateNew,
}: SubscriptionPickerProps) {
  const ui = usePageSpec('proration');
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearchSubmit();
  };

  const columns = ui.shown('columns');
  const pickerCells: Record<string, (sub: SubscriptionOut, isSelected: boolean) => ReactNode> = {
    subscription: (sub, isSelected) => (
      <td className="py-3 px-4">
        <div className={cn('font-semibold', isSelected ? 'text-brand-700' : 'text-slate-900')}>
          {sub.subscription_number}
        </div>
        <div className="text-[11px] text-slate-400 mt-0.5">Started {formatDate(sub.start_date)}</div>
      </td>
    ),
    customer: (sub) => (
      <td className="py-3 px-4">
        <div className="font-medium text-slate-800">{sub.customer.display_name}</div>
        <div className="text-[11px] text-slate-400 mt-0.5">{sub.customer.customer_number}</div>
      </td>
    ),
    plan: (sub) => (
      <td className="py-3 px-4">
        <div className="font-medium text-slate-800">{sub.plan.name}</div>
        <div className="text-[11px] text-slate-400 mt-0.5">
          {formatMoney(sub.plan.unit_amount, sub.plan.currency)} / {intervalLabel(sub.plan.billing_interval, sub.plan.interval_count)}
        </div>
      </td>
    ),
    quantity: (sub) => (
      <td className="py-3 px-4 text-right tabular-nums">{formatQuantity(sub.quantity)}</td>
    ),
    period: (sub) => (
      <td className="py-3 px-4 whitespace-nowrap">
        {formatDate(sub.current_period_start)} <span className="text-slate-400">→</span>{' '}
        {formatDate(sub.current_period_end)}
      </td>
    ),
    recurring: (sub) => (
      <td className="py-3 px-4 text-right tabular-nums font-medium text-slate-900">
        {formatMoney(sub.subtotal ?? sub.mrr, sub.currency ?? sub.plan.currency)}
      </td>
    ),
    status: (sub) => (
      <td className="py-3 px-4">
        <Badge variant={statusVariant(sub.status)} size="sm" dot>
          {humanize(sub.status)}
        </Badge>
      </td>
    ),
    action: (sub, isSelected) => (
      <td className="py-3 px-4 text-right">
        <Button
          size="sm"
          variant={isSelected ? 'primary' : 'outline'}
          className="text-xs py-1 px-3 h-7 font-medium whitespace-nowrap"
          onClick={(e) => {
            e.stopPropagation();
            onSelect(sub);
          }}
        >
          Change Plan
        </Button>
      </td>
    ),
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div {...ui.edit('picker')}>
          <h2 className="text-sm font-semibold text-slate-900 tracking-tight">{ui.text('picker', 'title')}</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {ui.text('picker', 'description')}
          </p>
        </div>
        <form onSubmit={handleSubmit} className="flex items-center gap-2 shrink-0">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search number, customer, plan..."
              className="pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 w-64 text-slate-900 placeholder:text-slate-400"
            />
          </div>
          <Button type="submit" variant="outline" size="sm">
            Search
          </Button>
        </form>
      </div>

      {loading ? (
        <LoadingState message="Loading eligible subscriptions..." className="py-10" />
      ) : error ? (
        <div className="p-4">
          <ErrorState title="Could not load subscriptions" message={error} onRetry={onRetry} />
        </div>
      ) : subscriptions.length === 0 ? (
        <div className="p-4" {...ui.edit('picker')}>
          <EmptyState
            icon={<Repeat className="w-6 h-6 stroke-1" />}
            title={searchQuery ? ui.text('picker', 'no_match_title') : ui.text('picker', 'empty_title')}
            description={searchQuery ? ui.text('picker', 'no_match') : ui.text('picker', 'empty')}
            action={
              canCreate && !searchQuery ? (
                <Button variant="primary" size="sm" onClick={onCreateNew}>
                  New subscription
                </Button>
              ) : undefined
            }
          />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50/80 text-slate-600 font-semibold border-b border-slate-200 uppercase tracking-wider text-[11px]" {...ui.edit('columns')}>
                {columns.map((col) => (
                  <th key={col.key} className={`py-3 px-4${RIGHT_ALIGNED.has(col.key) ? ' text-right' : ''}`} {...ui.edit(`columns.${col.key}`)}>
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {subscriptions.map((sub) => {
                const isSelected = sub.id === selectedId;
                return (
                  <tr
                    key={sub.id}
                    onClick={() => onSelect(sub)}
                    className={cn(
                      'cursor-pointer transition-colors',
                      isSelected ? 'bg-brand-50/70 hover:bg-brand-50' : 'hover:bg-slate-50/70'
                    )}
                    aria-selected={isSelected}
                  >
                    {columns.map((col) => <Fragment key={col.key}>{pickerCells[col.key]?.(sub, isSelected)}</Fragment>)}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
