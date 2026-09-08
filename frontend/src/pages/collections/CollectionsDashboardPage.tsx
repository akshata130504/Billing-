import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  CalendarClock,
  Clock3,
  ListChecks,
  ReceiptText,
  ScrollText,
  TrendingUp,
  Users,
  Wallet,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { StatCard } from '../../components/common/StatCard';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { EmptyState } from '../../components/common/EmptyState';
import { PageHeader } from '../../components/common/PageHeader';
import { collectionsService } from '../../services/collectionsService';
import { toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { formatDate, formatMoney, formatRelative, parseMoney } from '../../utils/format';
import { AGING_BUCKET_LABELS, ACTIVITY_TYPE_LABELS, COLLECTION_STATUS_LABELS, COLLECTION_STATUS_VARIANTS } from './collectionsUi';

export function CollectionsDashboardPage() {
  const dashboardQuery = useQuery({
    queryKey: queryKeys.collections.dashboard(),
    queryFn: collectionsService.dashboard,
  });

  if (dashboardQuery.isPending) {
    return <LoadingState message="Loading collections dashboard..." className="py-16" />;
  }

  if (dashboardQuery.isError) {
    return (
      <ErrorState
        message={toApiError(dashboardQuery.error).message}
        onRetry={() => void dashboardQuery.refetch()}
      />
    );
  }

  const data = dashboardQuery.data;
  const kpis = data.kpis;
  const maxAgingAmount = Math.max(1, ...data.aging_summary.map((b) => parseMoney(b.amount) || 0));
  const maxPipelineAmount = Math.max(1, ...data.pipeline.map((p) => parseMoney(p.amount) || 0));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Revenue"
        title="Collections"
        subtitle="Track outstanding balances, follow up on overdue invoices, and monitor collection performance across every customer."
      />

      {/* KPI tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
        <StatCard
          title="Total Outstanding"
          value={formatMoney(kpis.total_outstanding)}
          icon={<Wallet className="w-4 h-4" />}
        />
        <StatCard
          title="Overdue Amount"
          value={formatMoney(kpis.overdue_amount)}
          icon={<Clock3 className="w-4 h-4" />}
        />
        <StatCard
          title="Current (Not Due)"
          value={formatMoney(kpis.current_due)}
          icon={<ReceiptText className="w-4 h-4" />}
        />
        <StatCard
          title="Due in 7 Days"
          value={formatMoney(kpis.due_in_7_days)}
          icon={<CalendarClock className="w-4 h-4" />}
        />
        <StatCard
          title="Due in 30 Days"
          value={formatMoney(kpis.due_in_30_days)}
          icon={<CalendarClock className="w-4 h-4" />}
        />
        <StatCard
          title="Collection Rate"
          value={kpis.collection_rate === null ? 'N/A' : `${Number(kpis.collection_rate).toFixed(1)}%`}
          comparisonText={kpis.collection_rate === null ? 'Nothing invoiced in the last 30 days' : 'Last 30 days'}
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <StatCard
          title="Overdue Invoices"
          value={kpis.overdue_invoice_count}
          icon={<ListChecks className="w-4 h-4" />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Aging summary */}
        <Card>
          <CardHeader>
            <CardTitle>Aging Summary</CardTitle>
            <Link to="/collections/invoices" className="text-xs font-medium text-brand-600 hover:text-brand-700 inline-flex items-center gap-1">
              View invoices <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.aging_summary.length === 0 ? (
              <p className="text-xs text-slate-400 py-4 text-center">No aging data available.</p>
            ) : (
              data.aging_summary.map((bucket) => {
                const amount = parseMoney(bucket.amount) || 0;
                const pct = Math.round((amount / maxAgingAmount) * 100);
                return (
                  <div key={bucket.bucket}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="font-medium text-slate-700">{AGING_BUCKET_LABELS[bucket.bucket]}</span>
                      <span className="text-slate-500">
                        <span className="font-semibold text-slate-900">{formatMoney(bucket.amount)}</span>{' '}
                        &middot; {bucket.count} invoice{bucket.count === 1 ? '' : 's'}
                      </span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-brand-500"
                        style={{ width: `${Math.max(pct, amount > 0 ? 3 : 0)}%` }}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>

        {/* Collection pipeline */}
        <Card>
          <CardHeader>
            <CardTitle>Collection Pipeline</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.pipeline.length === 0 ? (
              <p className="text-xs text-slate-400 py-4 text-center">No pipeline data available.</p>
            ) : (
              data.pipeline.map((entry) => {
                const amount = parseMoney(entry.amount) || 0;
                const pct = Math.round((amount / maxPipelineAmount) * 100);
                return (
                  <div key={entry.status}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <Badge variant={COLLECTION_STATUS_VARIANTS[entry.status]} size="sm">
                        {COLLECTION_STATUS_LABELS[entry.status]}
                      </Badge>
                      <span className="text-slate-500">
                        <span className="font-semibold text-slate-900">{formatMoney(entry.amount)}</span>{' '}
                        &middot; {entry.count} invoice{entry.count === 1 ? '' : 's'}
                      </span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-slate-400"
                        style={{ width: `${Math.max(pct, amount > 0 ? 3 : 0)}%` }}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top overdue customers */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="w-4 h-4 text-brand-600" /> Top Overdue Customers
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {data.top_overdue_customers.length === 0 ? (
              <EmptyState
                className="border-0 rounded-none"
                title="No overdue customers"
                description="No customer currently has an overdue balance."
              />
            ) : (
              <div className="divide-y divide-slate-100">
                {data.top_overdue_customers.map((row) => (
                  <Link
                    key={row.customer.id}
                    to={`/customers/${row.customer.id}`}
                    className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-slate-50/70 transition-colors"
                  >
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-slate-900 truncate">{row.customer.display_name}</p>
                      <p className="text-[11px] text-slate-500">
                        {row.invoice_count} invoice{row.invoice_count === 1 ? '' : 's'} outstanding
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-xs font-bold text-rose-600 tabular-nums">{formatMoney(row.overdue_amount)}</p>
                      <p className="text-[11px] text-slate-400 tabular-nums">{formatMoney(row.outstanding_amount)} total</p>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Upcoming due invoices */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CalendarClock className="w-4 h-4 text-brand-600" /> Upcoming Due Invoices
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {data.upcoming_due_invoices.length === 0 ? (
              <EmptyState
                className="border-0 rounded-none"
                title="Nothing coming due"
                description="No invoices are due in the near future."
              />
            ) : (
              <div className="divide-y divide-slate-100">
                {data.upcoming_due_invoices.map((row) => (
                  <Link
                    key={row.id}
                    to={`/collections/invoices/${row.id}`}
                    className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-slate-50/70 transition-colors"
                  >
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-slate-900 truncate">{row.invoice_number}</p>
                      <p className="text-[11px] text-slate-500 truncate">{row.customer.display_name}</p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-xs font-bold text-slate-900 tabular-nums">{formatMoney(row.amount_due)}</p>
                      <p className="text-[11px] text-slate-400">Due {formatDate(row.due_date)}</p>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent activity */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ScrollText className="w-4 h-4 text-brand-600" /> Recent Activity
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {data.recent_activities.length === 0 ? (
            <EmptyState
              className="border-0 rounded-none"
              title="No collection activity yet"
              description="Activities like reminders, calls and notes logged against invoices will show up here."
            />
          ) : (
            <div className="divide-y divide-slate-100">
              {data.recent_activities.map((activity) => (
                <Link
                  key={activity.id}
                  to={`/collections/invoices/${activity.invoice_id}`}
                  className="flex items-start justify-between gap-3 px-5 py-3 hover:bg-slate-50/70 transition-colors"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge variant="neutral" size="sm">
                        {ACTIVITY_TYPE_LABELS[activity.activity_type]}
                      </Badge>
                      {activity.created_by && (
                        <span className="text-[11px] text-slate-400">by {activity.created_by.full_name}</span>
                      )}
                    </div>
                    {activity.note && (
                      <p className="text-xs text-slate-600 mt-1 line-clamp-2">{activity.note}</p>
                    )}
                  </div>
                  <span className="text-[11px] text-slate-400 shrink-0 whitespace-nowrap">
                    {formatRelative(activity.activity_at)}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
