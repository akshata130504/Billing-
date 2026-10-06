import { Fragment, useMemo, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Banknote,
  CalendarClock,
  CheckCircle2,
  Clock3,
  CreditCard,
  Download,
  Info,
  Layers,
  LineChart,
  Package,
  Percent,
  ReceiptText,
  RefreshCw,
  Repeat,
  Sparkles,
  TrendingUp,
  Users,
  Wallet,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/common/Card';
import { Button } from '../../components/common/Button';
import { Select } from '../../components/common/Select';
import { Input } from '../../components/common/Input';
import { StatCard } from '../../components/common/StatCard';
import { LoadingState, LoadingSpinner } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { EmptyState } from '../../components/common/EmptyState';
import { PageHeader } from '../../components/common/PageHeader';
import { useToast } from '../../components/common/Toast';
import { SimpleLineChart } from '../../components/common/charts/SimpleLineChart';
import { SimpleBarChart } from '../../components/common/charts/SimpleBarChart';
import { reportsService } from '../../services/reportsService';
import { subscriptionService } from '../../services/subscriptionService';
import { toApiError } from '../../services/apiClient';
import { downloadAuthenticated } from '../../services/download';
import { queryKeys } from '../../hooks/queries';
import { formatMoney, formatNumber, formatPercent, humanize, parseMoney } from '../../utils/format';
import { cn } from '../../utils/cn';
import { AGING_BUCKET_LABELS, PAYMENT_METHOD_LABELS, formatReportPeriod } from '../reports/reportsUi';
import type { SubscriptionSummaryOut } from '../../types/api';
import type {
  CustomerAnalyticsOut,
  InvoicedVsCollectedPoint,
  InvoiceAnalyticsOut,
  PaymentAnalyticsOut,
  ReceivablesAnalyticsOut,
  ReportExportSection,
  ReportKPIs,
  ReportRangeKey,
  ReportRangeParams,
  RevenueAnalyticsOut,
} from '../../types/reports';
import {
  REVENUE_RANGE_OPTIONS,
  type Insight,
  type InsightTone,
  type SubscriptionMix,
} from '../../types/revenueIntelligence';
import { usePageSpec } from '../../appUi/usePageSpec';
import type { EditableProps } from '../../appUi/UiConfigContext';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isRange(value: string | null): value is ReportRangeKey {
  return REVENUE_RANGE_OPTIONS.some((r) => r.value === value);
}

function rangeLabel(range: ReportRangeKey): string {
  return REVENUE_RANGE_OPTIONS.find((r) => r.value === range)?.label ?? humanize(range);
}

function num(value: string | number | null | undefined): number {
  const n = parseMoney(value);
  return Number.isNaN(n) ? 0 : n;
}

function methodLabel(method: string): string {
  return PAYMENT_METHOD_LABELS[method] ?? humanize(method);
}

function pct(part: number, whole: number): number {
  return whole > 0 ? (part / whole) * 100 : 0;
}

/**
 * The live /subscriptions/summary payload differs from the shared type (see
 * types/revenueIntelligence.ts). Read every field defensively and derive ARR
 * from MRR when the API does not report it.
 */
function toSubscriptionMix(raw: SubscriptionSummaryOut): SubscriptionMix {
  const live = raw as Partial<SubscriptionSummaryOut> & { renewing_soon_count?: number };
  const mrr = num(live.total_mrr);
  const reportedArr = parseMoney(live.total_arr);
  const arrDerived = Number.isNaN(reportedArr);
  return {
    total: live.total_subscriptions ?? 0,
    active: live.active_count ?? 0,
    trialing: live.trialing_count ?? 0,
    paused: live.paused_count ?? 0,
    pastDue: live.past_due_count ?? 0,
    cancelled: live.cancelled_count ?? 0,
    renewingSoon: live.renewing_soon_count ?? live.expiring_soon_count ?? 0,
    mrr,
    arr: arrDerived ? mrr * 12 : reportedArr,
    arrDerived,
  };
}

const TONE_RANK: Record<InsightTone, number> = { critical: 0, caution: 1, positive: 2, neutral: 3 };

/**
 * Plain-English observations derived strictly from the loaded figures. Every
 * number quoted here comes from the API responses — nothing is estimated.
 */
function buildInsights(input: {
  range: string;
  kpis: ReportKPIs;
  revenue?: RevenueAnalyticsOut;
  receivables?: ReceivablesAnalyticsOut;
  payments?: PaymentAnalyticsOut;
  customers?: CustomerAnalyticsOut;
  mix?: SubscriptionMix;
}): Insight[] {
  const { range, kpis, revenue, receivables, payments, customers, mix } = input;
  const out: Insight[] = [];

  const invoiced = num(kpis.total_invoiced);
  const collected = num(kpis.total_collected);
  const outstanding = num(kpis.outstanding_receivables);
  const overdue = num(kpis.overdue_receivables);
  const rate = kpis.collection_rate === null ? null : num(kpis.collection_rate);

  // Collection performance
  if (invoiced <= 0) {
    out.push({
      id: 'collection-none',
      tone: 'neutral',
      title: `Nothing was invoiced in ${range}`,
      detail:
        'Collection rate cannot be computed until at least one invoice is issued in this range. Widen the range or issue invoices to see collection performance.',
    });
  } else if (rate !== null) {
    const uncollected = Math.max(invoiced - collected, 0);
    if (rate >= 90) {
      out.push({
        id: 'collection-strong',
        tone: 'positive',
        title: `Collection rate is ${formatPercent(rate)}`,
        detail: `${formatMoney(collected)} of ${formatMoney(invoiced)} invoiced in ${range} has been collected.`,
      });
    } else if (rate >= 70) {
      out.push({
        id: 'collection-ok',
        tone: 'neutral',
        title: `Collection rate is ${formatPercent(rate)}`,
        detail: `${formatMoney(uncollected)} of ${formatMoney(invoiced)} invoiced in ${range} is still uncollected.`,
      });
    } else {
      out.push({
        id: 'collection-weak',
        tone: 'caution',
        title: `Collection rate is only ${formatPercent(rate)}`,
        detail: `${formatMoney(uncollected)} of ${formatMoney(invoiced)} invoiced in ${range} has not been collected yet.`,
      });
    }
  }

  // Receivables health
  if (overdue > 0) {
    const overdueBuckets = (receivables?.outstanding_by_aging ?? []).filter((b) => b.bucket !== 'current' && num(b.amount) > 0);
    const largest = overdueBuckets.reduce<(typeof overdueBuckets)[number] | null>(
      (acc, b) => (acc === null || num(b.amount) > num(acc.amount) ? b : acc),
      null
    );
    const overdueCount = overdueBuckets.reduce((sum, b) => sum + b.count, 0);
    out.push({
      id: 'overdue',
      tone: pct(overdue, outstanding) >= 50 ? 'critical' : 'caution',
      title: `${formatMoney(overdue)} is overdue`,
      detail:
        `${formatPercent(pct(overdue, outstanding), 0)} of the ${formatMoney(outstanding)} outstanding is past due` +
        (overdueCount > 0 ? ` across ${formatNumber(overdueCount)} ${overdueCount === 1 ? 'invoice' : 'invoices'}` : '') +
        (largest ? `; the largest slice (${formatMoney(largest.amount)}) sits in the ${AGING_BUCKET_LABELS[largest.bucket]} bucket.` : '.'),
    });
  } else if (outstanding > 0) {
    out.push({
      id: 'no-overdue',
      tone: 'positive',
      title: 'No overdue receivables',
      detail: `All ${formatMoney(outstanding)} outstanding is still within payment terms.`,
    });
  } else if (invoiced > 0) {
    out.push({
      id: 'fully-collected',
      tone: 'positive',
      title: 'Nothing outstanding',
      detail: 'Every invoice issued has been settled — there are no open receivables.',
    });
  }

  // Revenue momentum
  if (revenue && revenue.revenue_over_time.length >= 2) {
    const series = revenue.revenue_over_time;
    const last = series[series.length - 1];
    const prev = series[series.length - 2];
    const lastAmt = num(last.amount);
    const prevAmt = num(prev.amount);
    if (prevAmt > 0 && lastAmt > 0) {
      const change = ((lastAmt - prevAmt) / prevAmt) * 100;
      out.push({
        id: 'momentum',
        tone: change >= 0 ? 'positive' : 'caution',
        title: `Revenue ${change >= 0 ? 'up' : 'down'} ${formatPercent(Math.abs(change), 0)} in ${formatReportPeriod(last.period)}`,
        detail: `${formatMoney(lastAmt)} recognised in ${formatReportPeriod(last.period)} versus ${formatMoney(prevAmt)} in ${formatReportPeriod(prev.period)}.`,
      });
    } else if (prevAmt > 0 && lastAmt === 0) {
      out.push({
        id: 'momentum-gap',
        tone: 'caution',
        title: `No revenue recognised yet in ${formatReportPeriod(last.period)}`,
        detail: `${formatMoney(prevAmt)} was recognised in ${formatReportPeriod(prev.period)}; the current period has nothing so far.`,
      });
    }
  }

  // Customer concentration
  if (revenue && revenue.revenue_by_customer.length > 0) {
    const rows = revenue.revenue_by_customer;
    const sum = rows.reduce((acc, r) => acc + num(r.amount), 0);
    const top = rows[0];
    const topShare = pct(num(top.amount), sum);
    if (sum > 0 && topShare >= 50) {
      out.push({
        id: 'concentration',
        tone: 'caution',
        title: `${top.customer.display_name} drives ${formatPercent(topShare, 0)} of revenue`,
        detail: `${formatMoney(top.amount)} of the ${formatMoney(sum)} recognised among your top customers in ${range} comes from a single account.`,
      });
    } else if (sum > 0 && rows.length >= 3 && topShare < 35) {
      out.push({
        id: 'diversified',
        tone: 'positive',
        title: 'Revenue is well diversified',
        detail: `Your largest customer, ${top.customer.display_name}, accounts for ${formatPercent(topShare, 0)} of top-customer revenue in ${range}.`,
      });
    }
  }

  // Recurring revenue
  if (mix) {
    if (mix.total === 0) {
      out.push({
        id: 'mrr-none',
        tone: 'neutral',
        title: 'No subscriptions yet',
        detail: 'MRR is ₹0 because no subscriptions exist. Recurring revenue will appear here once the first subscription is activated.',
      });
    } else {
      const parts: string[] = [];
      if (mix.trialing > 0) parts.push(`${formatNumber(mix.trialing)} trialing`);
      if (mix.renewingSoon > 0) parts.push(`${formatNumber(mix.renewingSoon)} renewing soon`);
      if (mix.paused > 0) parts.push(`${formatNumber(mix.paused)} paused`);
      out.push({
        id: 'mrr',
        tone: mix.active > 0 ? 'positive' : 'neutral',
        title: `MRR is ${formatMoney(mix.mrr)} from ${formatNumber(mix.active)} active ${mix.active === 1 ? 'subscription' : 'subscriptions'}`,
        detail:
          `Annualised that is ${formatMoney(mix.arr)}${mix.arrDerived ? ' (MRR × 12)' : ''}.` +
          (parts.length > 0 ? ` Also ${parts.join(', ')}.` : ''),
      });
      if (mix.pastDue > 0) {
        out.push({
          id: 'past-due-subs',
          tone: 'caution',
          title: `${formatNumber(mix.pastDue)} ${mix.pastDue === 1 ? 'subscription is' : 'subscriptions are'} past due`,
          detail: 'Past-due subscriptions put recurring revenue at risk of churn until payment is recovered.',
        });
      }
    }
  }

  // Refunds
  if (payments && num(payments.refund_amount) > 0) {
    const gross = num(payments.total_payments);
    out.push({
      id: 'refunds',
      tone: 'caution',
      title: `${formatMoney(payments.refund_amount)} refunded in ${range}`,
      detail: `Net collected is ${formatMoney(payments.net_collected)}${gross > 0 ? `, ${formatPercent(pct(num(payments.net_collected), gross), 0)} of the ${formatMoney(gross)} gross payments` : ''}.`,
    });
  }

  // Payment velocity
  if (receivables && receivables.average_days_to_payment !== null) {
    const days = receivables.average_days_to_payment;
    out.push({
      id: 'dso',
      tone: days <= 15 ? 'positive' : days <= 30 ? 'neutral' : 'caution',
      title: `Customers pay in ${days.toFixed(1)} days on average`,
      detail:
        days <= 15
          ? 'Invoices in this range were settled quickly.'
          : days <= 30
            ? 'Payment velocity is within a typical 30-day cycle.'
            : 'Payments are taking longer than a 30-day cycle; consider tighter reminder cadences.',
    });
  }

  // Customer base
  if (customers) {
    if (customers.total_customers === 0) {
      out.push({
        id: 'customers-none',
        tone: 'neutral',
        title: 'No customers yet',
        detail: 'Add customers and issue invoices to start building revenue history.',
      });
    } else if (customers.customers_with_outstanding_balance > 0) {
      out.push({
        id: 'customers-owing',
        tone: 'neutral',
        title: `${formatNumber(customers.customers_with_outstanding_balance)} of ${formatNumber(customers.total_customers)} customers carry a balance`,
        detail: `${formatNumber(customers.active_customers)} ${customers.active_customers === 1 ? 'customer is' : 'customers are'} active in ${range}.`,
      });
    } else {
      out.push({
        id: 'customers-clear',
        tone: 'positive',
        title: `None of your ${formatNumber(customers.total_customers)} customers owe anything`,
        detail: `${formatNumber(customers.active_customers)} ${customers.active_customers === 1 ? 'customer was' : 'customers were'} active in ${range}.`,
      });
    }
  }

  return out.sort((a, b) => TONE_RANK[a.tone] - TONE_RANK[b.tone]);
}

// ---------------------------------------------------------------------------
// Building blocks
// ---------------------------------------------------------------------------

function Section({
  title,
  description,
  icon,
  exportSection,
  onExport,
  isExporting,
  className,
  edit,
  children,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  exportSection?: ReportExportSection;
  onExport?: (section: ReportExportSection) => void;
  isExporting?: boolean;
  className?: string;
  /** Visual-editor selection props. */
  edit?: EditableProps;
  children: ReactNode;
}) {
  return (
    <Card className={className} {...edit}>
      <CardHeader>
        <div className="min-w-0">
          <CardTitle className="flex items-center gap-2">
            {icon}
            {title}
          </CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        {exportSection && onExport && (
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<Download className="w-3.5 h-3.5" />}
            isLoading={isExporting}
            onClick={() => onExport(exportSection)}
          >
            CSV
          </Button>
        )}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

/** Renders a dependent query's loading / error state, or its data. */
function Resolved<T>({
  query,
  children,
  loadingMessage = 'Loading...',
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  loadingMessage?: string;
}) {
  if (query.isPending) return <LoadingState message={loadingMessage} className="py-8" />;
  if (query.isError) {
    return (
      <ErrorState
        className="py-6"
        message={toApiError(query.error).message}
        onRetry={() => void query.refetch()}
      />
    );
  }
  return <>{children(query.data as T)}</>;
}

/** Grouped column chart: invoiced vs collected per period. */
function InvoicedVsCollectedColumns({ data }: { data: InvoicedVsCollectedPoint[] }) {
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  const width = 600;
  const height = 220;
  const padTop = 18;
  const padBottom = 24;
  const chartHeight = height - padTop - padBottom;
  const groupGap = 12;
  const groupWidth = Math.max((width - groupGap * (data.length + 1)) / data.length, 8);
  const barWidth = Math.max((groupWidth - 4) / 2, 3);
  const maxVal = Math.max(1, ...data.map((d) => Math.max(num(d.invoiced), num(d.collected))));
  const active = activeIdx !== null ? data[activeIdx] : null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-4 text-[11px] text-slate-600">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm bg-brand-500" /> Invoiced
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" /> Collected
        </span>
        {active && (
          <span className="ml-auto font-medium text-slate-900 tabular-nums">
            {formatReportPeriod(active.period)} · <span className="text-brand-600">{formatMoney(active.invoiced)}</span> ·{' '}
            <span className="text-emerald-600">{formatMoney(active.collected)}</span>
          </span>
        )}
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height }}>
        <line x1={0} y1={padTop + chartHeight} x2={width} y2={padTop + chartHeight} stroke="#F1F5F9" strokeWidth="1" />
        {data.map((d, i) => {
          const x = groupGap + i * (groupWidth + groupGap);
          const inv = num(d.invoiced);
          const col = num(d.collected);
          const invH = Math.max((inv / maxVal) * chartHeight, inv > 0 ? 2 : 0);
          const colH = Math.max((col / maxVal) * chartHeight, col > 0 ? 2 : 0);
          const isActive = activeIdx === i;
          const showLabel = data.length <= 12 || i === 0 || i === data.length - 1;
          return (
            <g key={d.period} onMouseEnter={() => setActiveIdx(i)} onMouseLeave={() => setActiveIdx(null)} className="cursor-default">
              <rect x={x} y={padTop} width={groupWidth} height={chartHeight} fill={isActive ? '#F8FAFC' : 'transparent'} rx={4} />
              <rect x={x + 1} y={padTop + chartHeight - invH} width={barWidth} height={invH} rx={2} fill="#2563EB" opacity={isActive ? 1 : 0.85} />
              <rect x={x + 3 + barWidth} y={padTop + chartHeight - colH} width={barWidth} height={colH} rx={2} fill="#059669" opacity={isActive ? 1 : 0.85} />
              {showLabel && (
                <text x={x + groupWidth / 2} y={height - 6} textAnchor="middle" className="text-[10px] fill-slate-400 font-medium">
                  {formatReportPeriod(d.period)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function MetricRow({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2 border-b border-slate-100 last:border-0">
      <div className="min-w-0">
        <p className="text-xs font-medium text-slate-600">{label}</p>
        {hint && <p className="text-[11px] text-slate-400">{hint}</p>}
      </div>
      <span className="text-sm font-bold text-slate-900 tabular-nums shrink-0">{value}</span>
    </div>
  );
}

const MIX_ROWS: { key: keyof Pick<SubscriptionMix, 'active' | 'trialing' | 'renewingSoon' | 'paused' | 'pastDue' | 'cancelled'>; label: string; color: string }[] = [
  { key: 'active', label: 'Active', color: 'bg-emerald-500' },
  { key: 'trialing', label: 'Trialing', color: 'bg-sky-500' },
  { key: 'renewingSoon', label: 'Renewing soon', color: 'bg-brand-500' },
  { key: 'paused', label: 'Paused', color: 'bg-amber-500' },
  { key: 'pastDue', label: 'Past due', color: 'bg-rose-500' },
  { key: 'cancelled', label: 'Cancelled', color: 'bg-slate-400' },
];

function SubscriptionMixPanel({ mix }: { mix: SubscriptionMix }) {
  if (mix.total === 0) {
    return (
      <EmptyState
        className="border-0 py-6"
        icon={<Repeat className="w-6 h-6 stroke-1" />}
        title="No subscriptions yet"
        description="MRR and the subscription mix will populate once the first subscription is created."
        action={
          <Link to="/subscriptions" className="text-xs font-semibold text-brand-600 hover:text-brand-700 inline-flex items-center gap-1">
            Go to subscriptions <ArrowRight className="w-3 h-3" />
          </Link>
        }
      />
    );
  }
  const rows = MIX_ROWS.filter((r) => mix[r.key] > 0);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-slate-50 border border-slate-100 p-3">
          <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wide">MRR</p>
          <p className="mt-1 text-lg font-bold text-slate-900 tabular-nums">{formatMoney(mix.mrr)}</p>
        </div>
        <div className="rounded-lg bg-slate-50 border border-slate-100 p-3">
          <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wide">ARR{mix.arrDerived ? ' (MRR × 12)' : ''}</p>
          <p className="mt-1 text-lg font-bold text-slate-900 tabular-nums">{formatMoney(mix.arr)}</p>
        </div>
      </div>
      <div className="space-y-2.5">
        {rows.map((r) => {
          const count = mix[r.key];
          const share = pct(count, mix.total);
          return (
            <div key={r.key}>
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="font-medium text-slate-700">{r.label}</span>
                <span className="text-slate-500 tabular-nums">
                  {formatNumber(count)} · {formatPercent(share, 0)}
                </span>
              </div>
              <div className="w-full h-1.5 rounded-full bg-slate-100 overflow-hidden">
                <div className={cn('h-full rounded-full', r.color)} style={{ width: `${Math.max(share, 2)}%` }} />
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-slate-400">
        {formatNumber(mix.total)} {mix.total === 1 ? 'subscription' : 'subscriptions'} in total. Bars show the share of subscriptions in each status.
      </p>
    </div>
  );
}

const TONE_STYLE: Record<InsightTone, { icon: typeof Info; iconClass: string; border: string }> = {
  critical: { icon: AlertTriangle, iconClass: 'text-rose-600 bg-rose-50', border: 'border-l-rose-500' },
  caution: { icon: AlertTriangle, iconClass: 'text-amber-600 bg-amber-50', border: 'border-l-amber-500' },
  positive: { icon: CheckCircle2, iconClass: 'text-emerald-600 bg-emerald-50', border: 'border-l-emerald-500' },
  neutral: { icon: Info, iconClass: 'text-slate-500 bg-slate-100', border: 'border-l-slate-300' },
};

function InsightsPanel({ insights }: { insights: Insight[] }) {
  const ui = usePageSpec('revenue_intelligence');
  if (insights.length === 0) {
    return (
      <EmptyState
        className="border-0 py-6"
        icon={<Sparkles className="w-6 h-6 stroke-1" />}
        title={ui.text('insights', 'empty_title')}
        description={ui.text('insights', 'empty_description')}
      />
    );
  }
  return (
    <ul className="space-y-2.5">
      {insights.map((insight) => {
        const style = TONE_STYLE[insight.tone];
        const Icon = style.icon;
        return (
          <li key={insight.id} className={cn('flex gap-3 rounded-lg border border-slate-200/90 border-l-[3px] bg-white px-3.5 py-3', style.border)}>
            <span className={cn('shrink-0 w-7 h-7 rounded-full flex items-center justify-center', style.iconClass)}>
              <Icon className="w-3.5 h-3.5" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-slate-900 leading-snug">{insight.title}</p>
              <p className="mt-0.5 text-[11px] text-slate-500 leading-relaxed">{insight.detail}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function TopCustomersTable({
  revenue,
  receivables,
}: {
  revenue: RevenueAnalyticsOut;
  receivables?: ReceivablesAnalyticsOut;
}) {
  const ui = usePageSpec('revenue_intelligence');
  const rows = revenue.revenue_by_customer;
  if (rows.length === 0) {
    return (
      <EmptyState
        className="border-0 py-6"
        icon={<Users className="w-6 h-6 stroke-1" />}
        title="No customer revenue in this range"
        description="Customers appear here ranked by recognised revenue once invoices are issued to them."
      />
    );
  }
  const total = rows.reduce((acc, r) => acc + num(r.amount), 0);
  const outstandingById = new Map((receivables?.top_customers_by_outstanding ?? []).map((r) => [r.customer.id, r.amount]));
  const columns = ui.shown('customer_columns');
  const headerClass: Record<string, string> = {
    rank: 'px-4 py-2.5 w-8',
    customer: 'px-4 py-2.5',
    revenue: 'px-4 py-2.5 text-right',
    share: 'px-4 py-2.5 text-right',
    outstanding: 'px-4 py-2.5 text-right',
  };
  const cells: Record<string, (row: (typeof rows)[number], i: number) => ReactNode> = {
    rank: (_row, i) => <td className="px-4 py-2.5 text-slate-400 tabular-nums">{i + 1}</td>,
    customer: (row) => (
      <td className="px-4 py-2.5">
        <Link to={`/customers/${row.customer.id}`} className="font-semibold text-slate-900 hover:text-brand-600">
          {row.customer.display_name}
        </Link>
        <p className="text-[11px] text-slate-500">{row.customer.customer_number}</p>
      </td>
    ),
    revenue: (row) => <td className="px-4 py-2.5 text-right tabular-nums font-semibold text-slate-900">{formatMoney(row.amount)}</td>,
    share: (row) => {
      const share = pct(num(row.amount), total);
      return (
        <td className="px-4 py-2.5 text-right">
          <div className="inline-flex items-center gap-2">
            <span className="hidden sm:block w-16 h-1.5 rounded-full bg-slate-100 overflow-hidden">
              <span className="block h-full rounded-full bg-brand-500" style={{ width: `${Math.max(share, 2)}%` }} />
            </span>
            <span className="tabular-nums text-slate-600">{formatPercent(share, 0)}</span>
          </div>
        </td>
      );
    },
    outstanding: (row) => {
      const outstanding = outstandingById.get(row.customer.id);
      return (
        <td className={cn('px-4 py-2.5 text-right tabular-nums', outstanding && num(outstanding) > 0 ? 'text-amber-700 font-semibold' : 'text-slate-400')}>
          {outstanding ? formatMoney(outstanding) : '—'}
        </td>
      );
    },
  };
  return (
    <div className="overflow-x-auto border border-slate-100 rounded-lg">
      <table className="w-full text-xs text-left">
        <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200/80">
          <tr {...ui.edit('customer_columns')}>
            {columns.map((col) => (
              <th key={col.key} className={headerClass[col.key]} {...ui.edit(`customer_columns.${col.key}`)}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row, i) => (
            <tr key={row.customer.id} className="hover:bg-slate-50/60">
              {columns.map((col) => <Fragment key={col.key}>{cells[col.key]?.(row, i)}</Fragment>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function RevenueIntelligencePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [exportingSection, setExportingSection] = useState<ReportExportSection | null>(null);
  const ui = usePageSpec('revenue_intelligence');

  const rawRange = searchParams.get('range');
  const range: ReportRangeKey = isRange(rawRange) ? rawRange : 'this_year';
  const start = searchParams.get('start') ?? '';
  const end = searchParams.get('end') ?? '';
  const isCustomIncomplete = range === 'custom' && (!start || !end);
  const enabled = !isCustomIncomplete;

  const params: ReportRangeParams = useMemo(
    () => (range === 'custom' ? { range, start: start || undefined, end: end || undefined } : { range }),
    [range, start, end]
  );
  const label = range === 'custom' && start && end ? `${start} to ${end}` : rangeLabel(range).toLowerCase();

  const updateParams = (mutate: (p: URLSearchParams) => void) => {
    const p = new URLSearchParams(searchParams);
    mutate(p);
    setSearchParams(p, { replace: true });
  };
  const selectRange = (next: ReportRangeKey) =>
    updateParams((p) => {
      p.set('range', next);
      if (next !== 'custom') {
        p.delete('start');
        p.delete('end');
      }
    });
  const setStart = (value: string) => updateParams((p) => (value ? p.set('start', value) : p.delete('start')));
  const setEnd = (value: string) => updateParams((p) => (value ? p.set('end', value) : p.delete('end')));

  const kpisQuery = useQuery({ queryKey: queryKeys.reports.dashboard(params), queryFn: () => reportsService.dashboard(params), enabled });
  const revenueQuery = useQuery({ queryKey: queryKeys.reports.revenue(params), queryFn: () => reportsService.revenue(params), enabled });
  const receivablesQuery = useQuery({ queryKey: queryKeys.reports.receivables(params), queryFn: () => reportsService.receivables(params), enabled });
  const paymentsQuery = useQuery({ queryKey: queryKeys.reports.payments(params), queryFn: () => reportsService.payments(params), enabled });
  const customersQuery = useQuery({ queryKey: queryKeys.reports.customers(params), queryFn: () => reportsService.customers(params), enabled });
  const invoicesQuery = useQuery<InvoiceAnalyticsOut>({ queryKey: queryKeys.reports.invoices(params), queryFn: () => reportsService.invoices(params), enabled });
  const mixQuery = useQuery({
    queryKey: [...queryKeys.subscriptions.all, 'summary'] as const,
    queryFn: async () => toSubscriptionMix(await subscriptionService.summary()),
  });

  const allQueries = [kpisQuery, revenueQuery, receivablesQuery, paymentsQuery, customersQuery, invoicesQuery, mixQuery];
  const isRefreshing = allQueries.some((q) => q.isFetching);

  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.reports.all });
    void queryClient.invalidateQueries({ queryKey: [...queryKeys.subscriptions.all, 'summary'] });
  };

  const runExport = async (section: ReportExportSection) => {
    setExportingSection(section);
    try {
      const filename = `rooman_revenue_${section}_${range}_${Date.now()}.csv`;
      await downloadAuthenticated(reportsService.exportUrl(section, params), filename);
      showToast('success', 'Export complete', `Exported ${humanize(section)} to CSV.`);
    } catch (err) {
      showToast('error', 'Export failed', toApiError(err).message);
    } finally {
      setExportingSection(null);
    }
  };

  const insights = useMemo(
    () =>
      kpisQuery.data
        ? buildInsights({
            range: label,
            kpis: kpisQuery.data,
            revenue: revenueQuery.data,
            receivables: receivablesQuery.data,
            payments: paymentsQuery.data,
            customers: customersQuery.data,
            mix: mixQuery.data,
          })
        : [],
    [label, kpisQuery.data, revenueQuery.data, receivablesQuery.data, paymentsQuery.data, customersQuery.data, mixQuery.data]
  );

  const hasAnyData =
    (invoicesQuery.data?.total_count ?? 0) > 0 ||
    (mixQuery.data?.total ?? 0) > 0 ||
    num(kpisQuery.data?.total_collected) > 0;

  // ---- Render --------------------------------------------------------------

  let body: ReactNode;
  if (isCustomIncomplete) {
    body = (
      <EmptyState
        icon={<CalendarClock className="w-6 h-6 stroke-1" />}
        title={ui.text('empty', 'custom_title')}
        description={ui.text('empty', 'custom_description')}
      />
    );
  } else if (kpisQuery.isPending) {
    body = <LoadingState message="Crunching revenue figures..." />;
  } else if (kpisQuery.isError) {
    body = <ErrorState message={toApiError(kpisQuery.error).message} onRetry={() => void kpisQuery.refetch()} />;
  } else {
    const kpis = kpisQuery.data;
    const mix = mixQuery.data;
    const avgDays = receivablesQuery.data?.average_days_to_payment ?? null;

    body = (
      <>
        {/* KPI row */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4" {...ui.edit('kpis')}>
          {ui.render('kpis', {
            mrr: (item, edit) => (
              <div {...edit} className="flex">
                <StatCard
                  className="flex-1"
                  title={item.label}
                  value={mix ? formatMoney(mix.mrr) : mixQuery.isError ? '—' : '…'}
                  comparisonText={mix ? `${formatNumber(mix.active)} active ${mix.active === 1 ? 'subscription' : 'subscriptions'}` : mixQuery.isError ? 'Subscription summary unavailable' : undefined}
                  icon={<Repeat className="w-4 h-4" />}
                />
              </div>
            ),
            arr: (item, edit) => (
              <div {...edit} className="flex">
                <StatCard
                  className="flex-1"
                  // The "(MRR × 12)" qualifier is factual (ARR derived from MRR), so it stays code-controlled.
                  title={mix?.arrDerived === false ? item.label : `${item.label} (MRR × 12)`}
                  value={mix ? formatMoney(mix.arr) : mixQuery.isError ? '—' : '…'}
                  comparisonText={mix ? 'Annualised recurring revenue' : undefined}
                  icon={<TrendingUp className="w-4 h-4" />}
                />
              </div>
            ),
            net_revenue: (item, edit) => (
              <div {...edit} className="flex">
                <StatCard
                  className="flex-1"
                  title={item.label}
                  value={formatMoney(kpis.net_revenue)}
                  comparisonText={`Gross ${formatMoney(kpis.total_revenue)}`}
                  icon={<Banknote className="w-4 h-4" />}
                />
              </div>
            ),
            collection_rate: (item, edit) => (
              <div {...edit} className="flex">
                <StatCard
                  className="flex-1"
                  title={item.label}
                  value={formatPercent(kpis.collection_rate)}
                  comparisonText={
                    kpis.collection_rate === null
                      ? 'Nothing invoiced in this range'
                      : `${formatMoney(kpis.total_collected)} of ${formatMoney(kpis.total_invoiced)}`
                  }
                  icon={<Percent className="w-4 h-4" />}
                />
              </div>
            ),
            outstanding: (item, edit) => (
              <div {...edit} className="flex">
                <StatCard
                  className="flex-1"
                  title={item.label}
                  value={formatMoney(kpis.outstanding_receivables)}
                  comparisonText={num(kpis.outstanding_receivables) > 0 ? 'Open receivables' : 'No open receivables'}
                  icon={<Wallet className="w-4 h-4" />}
                />
              </div>
            ),
            overdue: (item, edit) => (
              <div {...edit} className="flex">
                <StatCard
                  className="flex-1"
                  title={item.label}
                  value={formatMoney(kpis.overdue_receivables)}
                  comparisonText={
                    num(kpis.overdue_receivables) > 0
                      ? `${formatPercent(pct(num(kpis.overdue_receivables), num(kpis.outstanding_receivables)), 0)} of outstanding`
                      : 'Nothing past due'
                  }
                  isPositive={num(kpis.overdue_receivables) === 0}
                  icon={<AlertTriangle className="w-4 h-4" />}
                />
              </div>
            ),
            avg_days: (item, edit) => (
              <div {...edit} className="flex">
                <StatCard
                  className="flex-1"
                  title={item.label}
                  value={avgDays === null ? '—' : `${avgDays.toFixed(1)} days`}
                  comparisonText={avgDays === null ? 'No paid invoices in this range' : 'From issue to full payment'}
                  icon={<Clock3 className="w-4 h-4" />}
                />
              </div>
            ),
            total_invoiced: (item, edit) => (
              <div {...edit} className="flex">
                <StatCard
                  className="flex-1"
                  title={item.label}
                  value={formatMoney(kpis.total_invoiced)}
                  comparisonText={
                    invoicesQuery.data
                      ? `${formatNumber(invoicesQuery.data.total_count)} ${invoicesQuery.data.total_count === 1 ? 'invoice' : 'invoices'}`
                      : undefined
                  }
                  icon={<ReceiptText className="w-4 h-4" />}
                />
              </div>
            ),
          })}
        </div>

        {!hasAnyData && !invoicesQuery.isPending && !mixQuery.isPending && (
          <EmptyState
            icon={<LineChart className="w-6 h-6 stroke-1" />}
            title={ui.text('empty', 'no_activity_title', { range: label })}
            description={ui.text('empty', 'no_activity_description')}
            action={
              range !== 'last_12_months' ? (
                <Button variant="outline" size="sm" onClick={() => selectRange('last_12_months')}>
                  Show last 12 months
                </Button>
              ) : undefined
            }
          />
        )}

        {/* Revenue trend + insights */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <Section
            className="xl:col-span-2"
            title={ui.text('revenue_trend', 'title')}
            description={ui.text('revenue_trend', 'description', { unit: revenueQuery.data?.granularity === 'day' ? 'day' : 'month', range: label })}
            edit={ui.edit('revenue_trend')}
            icon={<TrendingUp className="w-4 h-4 text-brand-600" />}
            exportSection="revenue_over_time"
            onExport={runExport}
            isExporting={exportingSection === 'revenue_over_time'}
          >
            <Resolved query={revenueQuery} loadingMessage="Loading revenue trend...">
              {(data) => {
                const series = data.revenue_over_time.map((p) => ({ period: p.period, value: num(p.amount) }));
                const total = series.reduce((acc, p) => acc + p.value, 0);
                if (series.length === 0) {
                  return <EmptyState className="border-0 py-6" title="No periods in range" description="Revenue is plotted once the range covers at least one period." />;
                }
                return (
                  <div className="space-y-3">
                    <div className="flex items-baseline gap-2">
                      <span className="text-2xl font-bold text-slate-900 tabular-nums">{formatMoney(total)}</span>
                      <span className="text-xs text-slate-500">recognised across {formatNumber(series.length)} {series.length === 1 ? 'period' : 'periods'}</span>
                    </div>
                    <SimpleLineChart data={series} height={220} formatPeriod={formatReportPeriod} />
                    {total === 0 && (
                      <p className="text-[11px] text-slate-400">Every period in this range is ₹0 — no revenue has been recognised yet.</p>
                    )}
                  </div>
                );
              }}
            </Resolved>
          </Section>

          <Section
            title={ui.text('insights', 'title')}
            description={ui.text('insights', 'description')}
            edit={ui.edit('insights')}
            icon={<Sparkles className="w-4 h-4 text-brand-600" />}
          >
            <InsightsPanel insights={insights} />
          </Section>
        </div>

        {/* Invoiced vs collected */}
        <Section
          title={ui.text('invoiced_vs_collected', 'title')}
          description={ui.text('invoiced_vs_collected', 'description')}
          edit={ui.edit('invoiced_vs_collected')}
          icon={<BarChart3 className="w-4 h-4 text-brand-600" />}
          exportSection="invoiced_vs_collected"
          onExport={runExport}
          isExporting={exportingSection === 'invoiced_vs_collected'}
        >
          <Resolved query={revenueQuery} loadingMessage="Loading billing vs collections...">
            {(data) =>
              data.invoiced_vs_collected.length === 0 ? (
                <EmptyState className="border-0 py-6" title="Nothing invoiced yet" description="Invoiced and collected amounts appear here once invoices exist for this range." />
              ) : (
                <InvoicedVsCollectedColumns data={data.invoiced_vs_collected} />
              )
            }
          </Resolved>
        </Section>

        {/* Plan / product / aging */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Section
            title={ui.text('revenue_by_plan', 'title')}
            edit={ui.edit('revenue_by_plan')}
            icon={<Layers className="w-4 h-4 text-brand-600" />}
            exportSection="revenue_by_plan"
            onExport={runExport}
            isExporting={exportingSection === 'revenue_by_plan'}
          >
            <Resolved query={revenueQuery} loadingMessage="Loading plans...">
              {(data) => {
                const rows = data.revenue_by_plan.map((r) => ({ label: r.name, value: num(r.revenue) }));
                return rows.length === 0 ? (
                  <EmptyState className="border-0 py-6" title="No plan revenue" description="No subscription plan was billed in this range." />
                ) : (
                  <SimpleBarChart data={rows} />
                );
              }}
            </Resolved>
          </Section>

          <Section
            title={ui.text('revenue_by_product', 'title')}
            edit={ui.edit('revenue_by_product')}
            icon={<Package className="w-4 h-4 text-brand-600" />}
            exportSection="revenue_by_product"
            onExport={runExport}
            isExporting={exportingSection === 'revenue_by_product'}
          >
            <Resolved query={revenueQuery} loadingMessage="Loading products...">
              {(data) => {
                const rows = data.revenue_by_product.map((r) => ({ label: r.name, value: num(r.revenue) }));
                return rows.length === 0 ? (
                  <EmptyState className="border-0 py-6" title="No product revenue" description="No product line items were billed in this range." />
                ) : (
                  <SimpleBarChart data={rows} color="#7C3AED" />
                );
              }}
            </Resolved>
          </Section>

          <Section
            title={ui.text('aging', 'title')}
            description={ui.text('aging', 'description')}
            edit={ui.edit('aging')}
            icon={<Wallet className="w-4 h-4 text-brand-600" />}
            exportSection="outstanding_by_aging"
            onExport={runExport}
            isExporting={exportingSection === 'outstanding_by_aging'}
          >
            <Resolved query={receivablesQuery} loadingMessage="Loading aging...">
              {(data) => {
                const totalOutstanding = data.outstanding_by_aging.reduce((acc, b) => acc + num(b.amount), 0);
                if (totalOutstanding === 0) {
                  return <EmptyState className="border-0 py-6" title="Nothing outstanding" description="There are no unpaid invoices to age." />;
                }
                return (
                  <SimpleBarChart
                    color="#D97706"
                    data={data.outstanding_by_aging.map((b) => ({ label: `${AGING_BUCKET_LABELS[b.bucket]} (${b.count})`, value: num(b.amount) }))}
                  />
                );
              }}
            </Resolved>
          </Section>
        </div>

        {/* Customers + subscription mix */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <Section
            className="xl:col-span-2"
            title={ui.text('top_customers', 'title')}
            description={ui.text('top_customers', 'description')}
            edit={ui.edit('top_customers')}
            icon={<Users className="w-4 h-4 text-brand-600" />}
            exportSection="revenue_by_customer"
            onExport={runExport}
            isExporting={exportingSection === 'revenue_by_customer'}
          >
            <Resolved query={revenueQuery} loadingMessage="Loading customers...">
              {(data) => <TopCustomersTable revenue={data} receivables={receivablesQuery.data} />}
            </Resolved>
          </Section>

          <Section
            title={ui.text('subscription_mix', 'title')}
            description={ui.text('subscription_mix', 'description')}
            edit={ui.edit('subscription_mix')}
            icon={<Repeat className="w-4 h-4 text-brand-600" />}
          >
            <Resolved query={mixQuery} loadingMessage="Loading subscriptions...">
              {(data) => <SubscriptionMixPanel mix={data} />}
            </Resolved>
          </Section>
        </div>

        {/* Cash summary */}
        <Section
          title={ui.text('cash_summary', 'title')}
          description={ui.text('cash_summary', 'description', { range: label })}
          edit={ui.edit('cash_summary')}
          icon={<CreditCard className="w-4 h-4 text-brand-600" />}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
            <Resolved query={paymentsQuery} loadingMessage="Loading payments...">
              {(p) => (
                <div>
                  <MetricRow label={ui.text('cash_summary', 'gross_payments')} value={formatMoney(p.total_payments)} hint={`${formatNumber(p.payment_count)} ${p.payment_count === 1 ? 'payment' : 'payments'}`} />
                  <MetricRow label={ui.text('cash_summary', 'refunds')} value={formatMoney(p.refund_amount)} />
                  <MetricRow label={ui.text('cash_summary', 'net_collected')} value={formatMoney(p.net_collected)} />
                  <MetricRow
                    label={ui.text('cash_summary', 'top_method')}
                    value={p.method_breakdown.length > 0 ? methodLabel([...p.method_breakdown].sort((a, b) => num(b.amount) - num(a.amount))[0].method) : '—'}
                  />
                </div>
              )}
            </Resolved>
            <Resolved query={customersQuery} loadingMessage="Loading customers...">
              {(c) => (
                <div>
                  <MetricRow label={ui.text('cash_summary', 'total_customers')} value={formatNumber(c.total_customers)} />
                  <MetricRow label={ui.text('cash_summary', 'active_customers')} value={formatNumber(c.active_customers)} hint={ui.text('cash_summary', 'active_customers_hint')} />
                  <MetricRow label={ui.text('cash_summary', 'with_balance')} value={formatNumber(c.customers_with_outstanding_balance)} />
                  <MetricRow
                    label={ui.text('cash_summary', 'average_invoice')}
                    value={formatMoney(kpis.average_invoice_value)}
                    hint={kpis.average_invoice_value === null ? 'No invoices in range' : undefined}
                  />
                </div>
              )}
            </Resolved>
          </div>
        </Section>
      </>
    );
  }

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        eyebrow={<span {...ui.edit('header')}>{ui.text('header', 'eyebrow')}</span>}
        title={<span {...ui.edit('header')}>{ui.text('header', 'title')}</span>}
        subtitle={<span {...ui.edit('header')}>{ui.text('header', 'subtitle')}</span>}
        actions={
          <div className="flex items-center gap-2">
            <Link
              to={`/reports?range=${range}${range === 'custom' && start && end ? `&start=${start}&end=${end}` : ''}`}
              className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700 px-2"
            >
              Detailed reports <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <Button
              variant="outline"
              size="sm"
              leadingIcon={isRefreshing ? <LoadingSpinner size="sm" className="text-slate-500" /> : <RefreshCw className="w-3.5 h-3.5" />}
              disabled={isRefreshing || isCustomIncomplete}
              onClick={refreshAll}
            >
              Refresh
            </Button>
          </div>
        }
      />

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="w-full sm:w-56">
              <Select
                aria-label="Date range"
                value={range}
                onChange={(e) => selectRange(e.target.value as ReportRangeKey)}
                options={REVENUE_RANGE_OPTIONS}
              />
            </div>
            {range === 'custom' && (
              <div className="flex items-center gap-2">
                <Input type="date" value={start} max={end || undefined} onChange={(e) => setStart(e.target.value)} aria-label="Start date" />
                <span className="text-xs text-slate-400 shrink-0">to</span>
                <Input type="date" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} aria-label="End date" />
              </div>
            )}
            {isCustomIncomplete ? (
              <span className="text-xs text-amber-600 font-medium">Select both a start and end date.</span>
            ) : (
              <span className="text-xs text-slate-500 sm:ml-auto">
                Showing figures for <span className="font-semibold text-slate-700">{label}</span>. MRR and ARR reflect today&apos;s subscriptions.
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {body}
    </div>
  );
}
