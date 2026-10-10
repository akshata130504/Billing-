import { FileEdit, Send, CreditCard, AlertTriangle, CheckCircle2, ChevronRight } from 'lucide-react';
import type { DashboardPipeline, PipelineBucket } from '../../../types';
import { formatMoney, parseMoney } from '../../../utils/format';
import { formatPerCurrency } from '../../../services/dashboardSummaryService';

export interface BillingPipelineWidgetProps {
  /** Card title (configurable in the Super Admin visual editor). */
  title?: string;
  pipeline: DashboardPipeline;
  currency: string;
}

type StageKey = keyof DashboardPipeline;

const STAGES: { key: StageKey; title: string; description: string; countLabel: string }[] = [
  { key: 'draft', title: 'Draft', description: 'Invoices drafted but not yet sent', countLabel: 'Draft' },
  { key: 'sent', title: 'Sent', description: 'Issued and awaiting payment', countLabel: 'Active' },
  { key: 'partially_paid', title: 'Partially Paid', description: 'Part of the balance collected', countLabel: 'Active' },
  { key: 'overdue', title: 'Overdue', description: 'Past due date, still unpaid', countLabel: 'Active' },
  { key: 'paid_this_period', title: 'Paid (This Period)', description: 'Fully reconciled revenue', countLabel: 'Settled' },
];

const STAGE_ICON: Record<StageKey, JSX.Element> = {
  draft: <FileEdit className="w-4 h-4 text-slate-500" />,
  sent: <Send className="w-4 h-4 text-brand-600" />,
  partially_paid: <CreditCard className="w-4 h-4 text-amber-600" />,
  overdue: <AlertTriangle className="w-4 h-4 text-rose-600" />,
  paid_this_period: <CheckCircle2 className="w-4 h-4 text-emerald-600" />,
};

const STAGE_COLOR: Record<StageKey, string> = {
  draft: 'border-slate-200 bg-slate-50/60',
  sent: 'border-brand-200 bg-blue-50/40',
  partially_paid: 'border-amber-200 bg-amber-50/40',
  overdue: 'border-rose-200 bg-rose-50/40',
  paid_this_period: 'border-emerald-200 bg-emerald-50/40',
};

/** Per-currency amounts of a bucket ("₹1,000.00 · AED 433.36"); never one summed figure. */
function bucketAmount(bucket: PipelineBucket, currency: string): string {
  const rows = bucket.by_currency?.length ? bucket.by_currency : [{ currency, count: bucket.count, amount: bucket.amount }];
  return formatPerCurrency(rows, (r) => r.amount, (a, c) => formatMoney(a, c), currency);
}

export function BillingPipelineWidget({ pipeline, currency, title = 'Billing Pipeline' }: BillingPipelineWidgetProps) {
  const totals: Record<string, number> = {};
  for (const stage of STAGES) {
    const bucket = pipeline[stage.key];
    const rows = bucket.by_currency?.length ? bucket.by_currency : [{ currency, amount: bucket.amount }];
    for (const row of rows) totals[row.currency] = (totals[row.currency] || 0) + (parseMoney(row.amount) || 0);
  }
  const totalRows = Object.entries(totals)
    .sort(([a], [b]) => (a === currency ? -1 : b === currency ? 1 : a.localeCompare(b)))
    .map(([cur, amount]) => ({ currency: cur, amount: String(amount) }));

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            {title}
          </h3>
          <p className="text-xs text-slate-400">
            Invoice status breakdown, draft through paid
          </p>
        </div>
        <span className="text-xs font-semibold text-slate-500">
          Total: <strong className="text-slate-900">{formatPerCurrency(totalRows, (r) => r.amount, (a, c) => formatMoney(a, c), currency)}</strong>
        </span>
      </div>

      {/* Visual Pipeline Stages */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 relative">
        {STAGES.map((stage, idx) => {
          const bucket: PipelineBucket = pipeline[stage.key];
          return (
            <div
              key={stage.key}
              className={`p-4 rounded-xl border relative flex flex-col justify-between transition-all hover:shadow-xs ${STAGE_COLOR[stage.key]}`}
            >
              <div>
                <div className="flex items-center justify-between">
                  <div className="p-2 rounded-lg bg-white shadow-subtle border border-slate-100">
                    {STAGE_ICON[stage.key]}
                  </div>
                  <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-700">
                    {bucket.count} {stage.countLabel}
                  </span>
                </div>

                <div className="mt-3">
                  <h4 className="text-xs font-bold text-slate-900 tracking-tight">
                    {stage.title}
                  </h4>
                  <span className="text-base font-bold text-slate-900 tabular-nums block mt-0.5">
                    {bucketAmount(bucket, currency)}
                  </span>
                </div>
              </div>

              <p className="text-[10px] text-slate-500 mt-2 font-medium">
                {stage.description}
              </p>

              {idx < STAGES.length - 1 && (
                <div className="hidden lg:flex absolute -right-2.5 top-1/2 -translate-y-1/2 z-10 w-5 h-5 rounded-full bg-white border border-slate-200 items-center justify-center text-slate-400 shadow-subtle">
                  <ChevronRight className="w-3 h-3" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
