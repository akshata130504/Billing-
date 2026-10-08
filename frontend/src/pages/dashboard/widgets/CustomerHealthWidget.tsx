import { HeartPulse } from 'lucide-react';
import type { DashboardCustomerHealth } from '../../../types';
import { formatNumber } from '../../../utils/format';

export interface CustomerHealthWidgetProps {
  /** Card title (configurable in the Super Admin visual editor). */
  title?: string;
  health: DashboardCustomerHealth;
}

// Subscription-status buckets only (churn fields are rates/derived, not buckets).
type HealthKey = 'active' | 'trialing' | 'past_due' | 'paused' | 'cancelled_this_period';

const BUCKETS: { key: HealthKey; label: string; dot: string; bg: string; text: string; bar: string }[] = [
  { key: 'active', label: 'Active', dot: 'bg-emerald-500', bg: 'bg-emerald-50/50 border-emerald-100/80', text: 'text-emerald-900', bar: 'bg-emerald-500' },
  { key: 'trialing', label: 'Trialing', dot: 'bg-sky-500', bg: 'bg-sky-50/50 border-sky-100/80', text: 'text-sky-900', bar: 'bg-sky-500' },
  { key: 'past_due', label: 'Past Due', dot: 'bg-rose-500', bg: 'bg-rose-50/50 border-rose-100/80', text: 'text-rose-900', bar: 'bg-rose-500' },
  { key: 'paused', label: 'Paused', dot: 'bg-amber-400', bg: 'bg-amber-50/50 border-amber-100/80', text: 'text-amber-900', bar: 'bg-amber-400' },
  { key: 'cancelled_this_period', label: 'Cancelled', dot: 'bg-slate-400', bg: 'bg-slate-50/70 border-slate-200/80', text: 'text-slate-700', bar: 'bg-slate-400' },
];

export function CustomerHealthWidget({ health, title = 'Customer Health' }: CustomerHealthWidgetProps) {
  const total = BUCKETS.reduce((sum, b) => sum + health[b.key], 0);
  const pct = (count: number) => (total > 0 ? Math.round((count / total) * 100) : 0);

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <HeartPulse className="w-4 h-4 text-emerald-600" />
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            {title}
          </h3>
        </div>
        <span className="text-xs text-slate-400">
          {formatNumber(total)} Subscription{total === 1 ? '' : 's'}
        </span>
      </div>

      {/* Segmented Progress Bar */}
      {total > 0 && (
        <div className="w-full h-3 rounded-full overflow-hidden flex bg-slate-100 p-0.5 gap-0.5">
          {BUCKETS.map((b) => (
            <div
              key={b.key}
              style={{ width: `${pct(health[b.key])}%` }}
              className={`${b.bar} h-full first:rounded-l-full last:rounded-r-full`}
              title={`${b.label}: ${pct(health[b.key])}%`}
            />
          ))}
        </div>
      )}

      {/* Health Breakdown Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
        {BUCKETS.map((b) => (
          <div key={b.key} className={`p-3 rounded-xl border ${b.bg}`}>
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${b.dot}`} />
              <span className={`text-xs font-bold ${b.text}`}>{b.label}</span>
            </div>
            <div className="mt-2">
              <span className="text-lg font-bold text-slate-900 tabular-nums">
                {formatNumber(health[b.key])}
              </span>
              <span className="text-[11px] text-slate-500 font-semibold ml-1">
                ({pct(health[b.key])}%)
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
