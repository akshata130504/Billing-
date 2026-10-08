import { useMemo, useState, type ReactNode } from 'react';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import {
  BarChart3,
  Wallet,
  TrendingUp,
  ReceiptText,
  CreditCard,
  Users,
  Package,
  Clock3,
  AlertTriangle,
  Percent,
  Calculator,
  Download,
  CalendarClock,
  Banknote,
  RefreshCcw,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Select } from '../../components/common/Select';
import { Input } from '../../components/common/Input';
import { StatCard } from '../../components/common/StatCard';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { EmptyState } from '../../components/common/EmptyState';
import { PageHeader } from '../../components/common/PageHeader';
import { useToast } from '../../components/common/Toast';
import { SimpleLineChart } from '../../components/common/charts/SimpleLineChart';
import { SimpleBarChart } from '../../components/common/charts/SimpleBarChart';
import { reportsService, downloadAuthenticated, toApiError } from '../../services';
import { queryKeys } from '../../hooks/queries';
import {
  formatMoney,
  formatNumber,
  formatPercent,
  humanize,
  parseMoney,
  statusVariant,
} from '../../utils/format';
import { AGING_BUCKET_LABELS, PAYMENT_METHOD_LABELS, PRICING_MODEL_LABELS, formatReportPeriod } from './reportsUi';
import { usePageSpec } from '../../appUi/usePageSpec';
import type {
  CustomerAmount,
  CustomerAnalyticsOut,
  InvoiceAnalyticsOut,
  NamedAmount,
  PaymentAnalyticsOut,
  ProductAnalyticsOut,
  QuantitySold,
  ReceivablesAnalyticsOut,
  ReportExportSection,
  ReportKPIs,
  ReportRangeKey,
  ReportRangeParams,
  RevenueAnalyticsOut,
} from '../../types/reports';

// ---------------------------------------------------------------------------
// Static config
// ---------------------------------------------------------------------------

type ReportTab = 'overview' | 'revenue' | 'receivables' | 'invoices' | 'payments' | 'customers' | 'products';

const TAB_ICONS: Record<string, typeof BarChart3> = {
  overview: BarChart3,
  revenue: TrendingUp,
  receivables: Wallet,
  invoices: ReceiptText,
  payments: CreditCard,
  customers: Users,
  products: Package,
};

const TABS: { key: ReportTab; label: string; icon: typeof BarChart3 }[] = [
  { key: 'overview', label: 'Overview', icon: BarChart3 },
  { key: 'revenue', label: 'Revenue', icon: TrendingUp },
  { key: 'receivables', label: 'Receivables', icon: Wallet },
  { key: 'invoices', label: 'Invoices', icon: ReceiptText },
  { key: 'payments', label: 'Payments', icon: CreditCard },
  { key: 'customers', label: 'Customers', icon: Users },
  { key: 'products', label: 'Products', icon: Package },
];

const RANGE_OPTIONS: { value: ReportRangeKey; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'this_week', label: 'This Week' },
  { value: 'this_month', label: 'This Month' },
  { value: 'last_month', label: 'Last Month' },
  { value: 'this_quarter', label: 'This Quarter' },
  { value: 'this_year', label: 'This Year' },
  { value: 'last_12_months', label: 'Last 12 Months' },
  { value: 'custom', label: 'Custom Range' },
];

function isTab(value: string | null): value is ReportTab {
  return TABS.some((t) => t.key === value);
}

function isRange(value: string | null): value is ReportRangeKey {
  return RANGE_OPTIONS.some((r) => r.value === value);
}

// ---------------------------------------------------------------------------
// Shared building blocks
// ---------------------------------------------------------------------------

/** Renders loading / error / "pick a custom range" states, or the resolved data. */
function QueryBoundary<T>({
  query,
  blocked,
  loadingMessage,
  children,
}: {
  query: UseQueryResult<T>;
  blocked: boolean;
  loadingMessage: string;
  children: (data: T) => ReactNode;
}) {
  if (blocked) {
    return (
      <EmptyState
        icon={<CalendarClock className="w-6 h-6 stroke-1" />}
        title="Choose a custom date range"
        description="Select both a start and end date above to load this report."
      />
    );
  }
  if (query.isPending) return <LoadingState message={loadingMessage} className="py-16" />;
  if (query.isError) {
    return (
      <ErrorState message={toApiError(query.error).message} onRetry={() => void query.refetch()} />
    );
  }
  return <>{children(query.data as T)}</>;
}

function ReportSection({
  title,
  icon,
  exportSection,
  onExport,
  isExporting,
  note,
  children,
}: {
  title: string;
  icon?: ReactNode;
  exportSection?: ReportExportSection;
  onExport?: (section: ReportExportSection) => void;
  isExporting?: boolean;
  note?: string;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {icon}
          {title}
        </CardTitle>
        {exportSection && onExport && (
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<Download className="w-3.5 h-3.5" />}
            isLoading={isExporting}
            onClick={() => onExport(exportSection)}
          >
            Export CSV
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {note && <p className="text-[11px] text-slate-400 mb-3">{note}</p>}
        {children}
      </CardContent>
    </Card>
  );
}

function CustomerAmountList({
  rows,
  emptyTitle,
  emptyDescription,
}: {
  rows: CustomerAmount[];
  emptyTitle: string;
  emptyDescription: string;
}) {
  if (rows.length === 0) {
    return <EmptyState className="border-0 py-6" title={emptyTitle} description={emptyDescription} />;
  }
  return (
    <div className="divide-y divide-slate-100 border border-slate-100 rounded-lg overflow-hidden">
      {rows.map((row) => (
        <div key={row.customer.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-900 truncate">{row.customer.display_name}</p>
            <p className="text-[11px] text-slate-500">{row.customer.customer_number}</p>
          </div>
          <span className="text-xs font-bold text-slate-900 tabular-nums shrink-0">
            {formatMoney(row.amount)}
          </span>
        </div>
      ))}
    </div>
  );
}

function NamedAmountTable({
  rows,
  quantityLabel = 'Qty',
  emptyTitle,
  emptyDescription,
}: {
  rows: NamedAmount[];
  quantityLabel?: string;
  emptyTitle: string;
  emptyDescription: string;
}) {
  if (rows.length === 0) {
    return <EmptyState className="border-0 py-6" title={emptyTitle} description={emptyDescription} />;
  }
  return (
    <div className="overflow-x-auto border border-slate-100 rounded-lg">
      <table className="w-full text-xs text-left">
        <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200/80">
          <tr>
            <th className="px-4 py-2.5">Name</th>
            <th className="px-4 py-2.5 text-right">{quantityLabel}</th>
            <th className="px-4 py-2.5 text-right">Revenue</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={row.id}>
              <td className="px-4 py-2.5 font-medium text-slate-900">{row.name}</td>
              <td className="px-4 py-2.5 text-right tabular-nums text-slate-600">
                {formatNumber(row.quantity)}
              </td>
              <td className="px-4 py-2.5 text-right tabular-nums font-semibold text-slate-900">
                {formatMoney(row.revenue)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function InvoicedVsCollectedChart({ data }: { data: RevenueAnalyticsOut['invoiced_vs_collected'] }) {
  if (data.length === 0) {
    return (
      <EmptyState
        className="border-0 py-6"
        title="Nothing invoiced yet"
        description="Invoiced vs collected amounts will appear here once invoices exist for this range."
      />
    );
  }
  const maxVal = Math.max(
    1,
    ...data.map((d) => Math.max(parseMoney(d.invoiced) || 0, parseMoney(d.collected) || 0))
  );
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 text-[11px]">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-brand-500" /> Invoiced
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" /> Collected
        </span>
      </div>
      <div className="space-y-3">
        {data.map((d) => {
          const invoiced = parseMoney(d.invoiced) || 0;
          const collected = parseMoney(d.collected) || 0;
          return (
            <div key={d.period}>
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="font-medium text-slate-700">{formatReportPeriod(d.period)}</span>
                <span className="text-slate-500">
                  <span className="text-brand-600 font-semibold">{formatMoney(d.invoiced)}</span> ·{' '}
                  <span className="text-emerald-600 font-semibold">{formatMoney(d.collected)}</span>
                </span>
              </div>
              <div className="space-y-1">
                <div className="w-full h-1.5 rounded-full bg-slate-100 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-brand-500"
                    style={{ width: `${Math.max((invoiced / maxVal) * 100, invoiced > 0 ? 2 : 0)}%` }}
                  />
                </div>
                <div className="w-full h-1.5 rounded-full bg-slate-100 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-emerald-500"
                    style={{ width: `${Math.max((collected / maxVal) * 100, collected > 0 ? 2 : 0)}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

function OverviewTab({ data }: { data: ReportKPIs }) {
  const ui = usePageSpec('reports');
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4" {...ui.edit('overview_kpis')}>
      {ui.render('overview_kpis', {
        total_revenue: (item, edit) => (
          <div key="total_revenue" {...edit}>
            <StatCard title={item.label} value={formatMoney(data.total_revenue)} icon={<TrendingUp className="w-4 h-4" />} />
          </div>
        ),
        net_revenue: (item, edit) => (
          <div key="net_revenue" {...edit}>
            <StatCard title={item.label} value={formatMoney(data.net_revenue)} icon={<Banknote className="w-4 h-4" />} />
          </div>
        ),
        total_invoiced: (item, edit) => (
          <div key="total_invoiced" {...edit}>
            <StatCard title={item.label} value={formatMoney(data.total_invoiced)} icon={<ReceiptText className="w-4 h-4" />} />
          </div>
        ),
        total_collected: (item, edit) => (
          <div key="total_collected" {...edit}>
            <StatCard title={item.label} value={formatMoney(data.total_collected)} icon={<CreditCard className="w-4 h-4" />} />
          </div>
        ),
        outstanding: (item, edit) => (
          <div key="outstanding" {...edit}>
            <StatCard title={item.label} value={formatMoney(data.outstanding_receivables)} icon={<Wallet className="w-4 h-4" />} />
          </div>
        ),
        overdue: (item, edit) => (
          <div key="overdue" {...edit}>
            <StatCard title={item.label} value={formatMoney(data.overdue_receivables)} icon={<AlertTriangle className="w-4 h-4" />} />
          </div>
        ),
        collection_rate: (item, edit) => (
          <div key="collection_rate" {...edit}>
            <StatCard
              title={item.label}
              value={formatPercent(data.collection_rate)}
              comparisonText={data.collection_rate === null ? 'Nothing invoiced in this range' : undefined}
              icon={<Percent className="w-4 h-4" />}
            />
          </div>
        ),
        avg_invoice: (item, edit) => (
          <div key="avg_invoice" {...edit}>
            <StatCard
              title={item.label}
              value={formatMoney(data.average_invoice_value)}
              comparisonText={data.average_invoice_value === null ? 'Nothing invoiced in this range' : undefined}
              icon={<Calculator className="w-4 h-4" />}
            />
          </div>
        ),
      })}
    </div>
  );
}

function RevenueTab({
  data,
  onExport,
  exportingSection,
}: {
  data: RevenueAnalyticsOut;
  onExport: (section: ReportExportSection) => void;
  exportingSection: ReportExportSection | null;
}) {
  const revenueOverTime = data.revenue_over_time.map((p) => ({ period: p.period, value: parseMoney(p.amount) || 0 }));
  const byCustomer = data.revenue_by_customer.map((r) => ({ label: r.customer.display_name, value: parseMoney(r.amount) || 0 }));
  const byProduct = data.revenue_by_product.map((r) => ({ label: r.name, value: parseMoney(r.revenue) || 0 }));
  const byPlan = data.revenue_by_plan.map((r) => ({ label: r.name, value: parseMoney(r.revenue) || 0 }));

  return (
    <div className="space-y-6">
      <ReportSection
        title="Revenue Over Time"
        icon={<TrendingUp className="w-4 h-4 text-brand-600" />}
        exportSection="revenue_over_time"
        onExport={onExport}
        isExporting={exportingSection === 'revenue_over_time'}
      >
        {revenueOverTime.length === 0 ? (
          <EmptyState
            className="border-0 py-6"
            title="No revenue yet"
            description="Revenue recognized for this range will appear here once invoices are issued."
          />
        ) : (
          <SimpleLineChart data={revenueOverTime} formatPeriod={formatReportPeriod} />
        )}
      </ReportSection>

      <ReportSection
        title="Invoiced vs Collected"
        icon={<Banknote className="w-4 h-4 text-brand-600" />}
        exportSection="invoiced_vs_collected"
        onExport={onExport}
        isExporting={exportingSection === 'invoiced_vs_collected'}
      >
        <InvoicedVsCollectedChart data={data.invoiced_vs_collected} />
      </ReportSection>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ReportSection
          title="Revenue by Customer"
          icon={<Users className="w-4 h-4 text-brand-600" />}
          exportSection="revenue_by_customer"
          onExport={onExport}
          isExporting={exportingSection === 'revenue_by_customer'}
          note="Top 10 customers by revenue."
        >
          {byCustomer.length === 0 ? (
            <EmptyState className="border-0 py-6" title="No customer revenue yet" description="No invoices billed to a customer in this range." />
          ) : (
            <SimpleBarChart data={byCustomer} />
          )}
        </ReportSection>

        <ReportSection
          title="Revenue by Product"
          icon={<Package className="w-4 h-4 text-brand-600" />}
          exportSection="revenue_by_product"
          onExport={onExport}
          isExporting={exportingSection === 'revenue_by_product'}
        >
          {byProduct.length === 0 ? (
            <EmptyState className="border-0 py-6" title="No product revenue yet" description="No line items billed against a product in this range." />
          ) : (
            <SimpleBarChart data={byProduct} />
          )}
        </ReportSection>
      </div>

      <ReportSection
        title="Revenue by Plan"
        icon={<ReceiptText className="w-4 h-4 text-brand-600" />}
        exportSection="revenue_by_plan"
        onExport={onExport}
        isExporting={exportingSection === 'revenue_by_plan'}
      >
        {byPlan.length === 0 ? (
          <EmptyState className="border-0 py-6" title="No plan revenue yet" description="No line items billed against a subscription plan in this range." />
        ) : (
          <SimpleBarChart data={byPlan} />
        )}
      </ReportSection>
    </div>
  );
}

function ReceivablesTab({
  data,
  onExport,
  exportingSection,
}: {
  data: ReceivablesAnalyticsOut;
  onExport: (section: ReportExportSection) => void;
  exportingSection: ReportExportSection | null;
}) {
  const aging = data.outstanding_by_aging.map((b) => ({
    label: `${AGING_BUCKET_LABELS[b.bucket]} (${b.count})`,
    value: parseMoney(b.amount) || 0,
  }));
  const overdueByDue = data.overdue_by_due_period.map((p) => ({ period: p.period, value: parseMoney(p.amount) || 0 }));
  const collectionTrend = data.collection_rate_trend
    .filter((p) => p.rate !== null)
    .map((p) => ({ period: p.period, value: parseMoney(p.rate) || 0 }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <StatCard
          title="Average Days to Payment"
          value={data.average_days_to_payment === null ? '—' : `${data.average_days_to_payment.toFixed(1)} days`}
          icon={<Clock3 className="w-4 h-4" />}
        />
      </div>

      <ReportSection
        title="Outstanding by Aging"
        icon={<Wallet className="w-4 h-4 text-brand-600" />}
        exportSection="outstanding_by_aging"
        onExport={onExport}
        isExporting={exportingSection === 'outstanding_by_aging'}
      >
        {aging.length === 0 ? (
          <EmptyState className="border-0 py-6" title="Nothing outstanding" description="No unpaid invoices in this range." />
        ) : (
          <SimpleBarChart data={aging} />
        )}
      </ReportSection>

      <ReportSection
        title="Overdue Amount by Due Period"
        icon={<AlertTriangle className="w-4 h-4 text-brand-600" />}
        note="Groups currently-overdue invoices by the period their due date falls in — not a historical day-by-day snapshot of overdue balances."
      >
        {overdueByDue.length === 0 ? (
          <EmptyState className="border-0 py-6" title="Nothing overdue" description="No invoices are currently overdue." />
        ) : (
          <SimpleLineChart data={overdueByDue} color="#E11D48" formatPeriod={formatReportPeriod} />
        )}
      </ReportSection>

      <ReportSection title="Collection Rate Trend" icon={<Percent className="w-4 h-4 text-brand-600" />}>
        {collectionTrend.length === 0 ? (
          <EmptyState className="border-0 py-6" title="No collection data yet" description="Nothing was invoiced in this range to compute a collection rate." />
        ) : (
          <SimpleLineChart
            data={collectionTrend}
            color="#059669"
            formatPeriod={formatReportPeriod}
            formatValue={(v) => formatPercent(v)}
          />
        )}
      </ReportSection>

      <ReportSection
        title="Top Customers by Outstanding"
        icon={<Users className="w-4 h-4 text-brand-600" />}
        exportSection="top_customers_by_outstanding"
        onExport={onExport}
        isExporting={exportingSection === 'top_customers_by_outstanding'}
      >
        <CustomerAmountList
          rows={data.top_customers_by_outstanding}
          emptyTitle="No outstanding balances"
          emptyDescription="No customer currently has an outstanding balance."
        />
      </ReportSection>
    </div>
  );
}

function InvoicesTab({ data }: { data: InvoiceAnalyticsOut }) {
  const statuses = Object.entries(data.by_status);
  const byStatusChart = statuses.map(([status, s]) => ({ label: humanize(status), value: parseMoney(s.amount) || 0 }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4">
        <StatCard title="Total Invoices" value={formatNumber(data.total_count)} icon={<ReceiptText className="w-4 h-4" />} />
        <StatCard title="Average Invoice Amount" value={formatMoney(data.average_invoice_amount)} icon={<Calculator className="w-4 h-4" />} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-brand-600" /> Invoices by Status
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {statuses.length === 0 ? (
            <EmptyState className="border-0 py-6" title="No invoices yet" description="No invoices were issued in this range." />
          ) : (
            <>
              <SimpleBarChart data={byStatusChart} />
              <div className="overflow-x-auto border border-slate-100 rounded-lg">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200/80">
                    <tr>
                      <th className="px-4 py-2.5">Status</th>
                      <th className="px-4 py-2.5 text-right">Count</th>
                      <th className="px-4 py-2.5 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {statuses.map(([status, s]) => (
                      <tr key={status}>
                        <td className="px-4 py-2.5">
                          <Badge variant={statusVariant(status)} size="sm">
                            {humanize(status)}
                          </Badge>
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-slate-600">{formatNumber(s.count)}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums font-semibold text-slate-900">
                          {formatMoney(s.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function PaymentsTab({
  data,
  onExport,
  exportingSection,
}: {
  data: PaymentAnalyticsOut;
  onExport: (section: ReportExportSection) => void;
  exportingSection: ReportExportSection | null;
}) {
  const methodChart = data.method_breakdown.map((m) => ({
    label: PAYMENT_METHOD_LABELS[m.method] ?? humanize(m.method),
    value: parseMoney(m.amount) || 0,
  }));
  const trend = data.trend.map((p) => ({ period: p.period, value: parseMoney(p.amount) || 0 }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
        <StatCard title="Total Payments" value={formatMoney(data.total_payments)} icon={<CreditCard className="w-4 h-4" />} />
        <StatCard title="Payment Count" value={formatNumber(data.payment_count)} icon={<ReceiptText className="w-4 h-4" />} />
        <StatCard title="Refund Amount" value={formatMoney(data.refund_amount)} icon={<RefreshCcw className="w-4 h-4" />} />
        <StatCard title="Net Collected" value={formatMoney(data.net_collected)} icon={<Banknote className="w-4 h-4" />} />
      </div>

      <ReportSection
        title="Payments by Method"
        icon={<CreditCard className="w-4 h-4 text-brand-600" />}
        exportSection="method_breakdown"
        onExport={onExport}
        isExporting={exportingSection === 'method_breakdown'}
      >
        {methodChart.length === 0 ? (
          <EmptyState className="border-0 py-6" title="No payments yet" description="No payments were recorded in this range." />
        ) : (
          <SimpleBarChart data={methodChart} color="#059669" />
        )}
      </ReportSection>

      <ReportSection title="Payment Trend" icon={<TrendingUp className="w-4 h-4 text-brand-600" />}>
        {trend.length === 0 ? (
          <EmptyState className="border-0 py-6" title="No payments yet" description="No payments were recorded in this range." />
        ) : (
          <SimpleLineChart data={trend} color="#059669" formatPeriod={formatReportPeriod} />
        )}
      </ReportSection>
    </div>
  );
}

function CustomersTab({ data }: { data: CustomerAnalyticsOut }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4">
        <StatCard title="Total Customers" value={formatNumber(data.total_customers)} icon={<Users className="w-4 h-4" />} />
        <StatCard title="Active Customers" value={formatNumber(data.active_customers)} icon={<Users className="w-4 h-4" />} />
        <StatCard
          title="With Outstanding Balance"
          value={formatNumber(data.customers_with_outstanding_balance)}
          icon={<Wallet className="w-4 h-4" />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ReportSection title="Top Customers by Revenue" icon={<TrendingUp className="w-4 h-4 text-brand-600" />}>
          <CustomerAmountList
            rows={data.top_customers_by_revenue}
            emptyTitle="No customer revenue yet"
            emptyDescription="No invoices billed to a customer in this range."
          />
        </ReportSection>

        <ReportSection title="Top Customers by Outstanding" icon={<Wallet className="w-4 h-4 text-brand-600" />}>
          <CustomerAmountList
            rows={data.top_customers_by_outstanding}
            emptyTitle="No outstanding balances"
            emptyDescription="No customer currently has an outstanding balance."
          />
        </ReportSection>
      </div>
    </div>
  );
}

function ProductsTab({ data }: { data: ProductAnalyticsOut }) {
  const pricingModelChart = data.revenue_by_pricing_model.map((p) => ({
    label: PRICING_MODEL_LABELS[p.pricing_model] ?? humanize(p.pricing_model),
    value: parseMoney(p.amount) || 0,
  }));

  return (
    <div className="space-y-6">
      <ReportSection title="Best Selling (by Quantity)" icon={<Package className="w-4 h-4 text-brand-600" />}>
        <NamedAmountTable
          rows={data.best_selling}
          quantityLabel="Quantity"
          emptyTitle="No sales yet"
          emptyDescription="No products or plans were sold in this range."
        />
      </ReportSection>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ReportSection title="Revenue by Offering" icon={<ReceiptText className="w-4 h-4 text-brand-600" />}>
          <NamedAmountTable
            rows={data.revenue_by_offering}
            quantityLabel="Quantity"
            emptyTitle="No offering revenue yet"
            emptyDescription="No line items billed against a catalog offering in this range."
          />
        </ReportSection>

        <ReportSection title="Plan Revenue" icon={<CreditCard className="w-4 h-4 text-brand-600" />}>
          <NamedAmountTable
            rows={data.plan_revenue}
            quantityLabel="Quantity"
            emptyTitle="No plan revenue yet"
            emptyDescription="No line items billed against a subscription plan in this range."
          />
        </ReportSection>
      </div>

      <ReportSection title="Revenue by Pricing Model" icon={<Calculator className="w-4 h-4 text-brand-600" />}>
        {pricingModelChart.length === 0 ? (
          <EmptyState className="border-0 py-6" title="No revenue yet" description="No line items billed in this range." />
        ) : (
          <SimpleBarChart data={pricingModelChart} />
        )}
      </ReportSection>

      <ReportSection title="Quantity Sold" icon={<Package className="w-4 h-4 text-brand-600" />}>
        {data.quantity_sold.length === 0 ? (
          <EmptyState className="border-0 py-6" title="No sales yet" description="No products or plans were sold in this range." />
        ) : (
          <div className="overflow-x-auto border border-slate-100 rounded-lg">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200/80">
                <tr>
                  <th className="px-4 py-2.5">Name</th>
                  <th className="px-4 py-2.5 text-right">Quantity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.quantity_sold.map((row: QuantitySold) => (
                  <tr key={row.id}>
                    <td className="px-4 py-2.5 font-medium text-slate-900">{row.name}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-slate-600">{formatNumber(row.quantity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ReportSection>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ReportsPage() {
  const ui = usePageSpec('reports');
  const [searchParams, setSearchParams] = useSearchParams();
  const { showToast } = useToast();
  const [exportingSection, setExportingSection] = useState<ReportExportSection | null>(null);

  const rawTab = searchParams.get('tab');
  const tab: ReportTab = isTab(rawTab) ? rawTab : 'overview';

  const rawRange = searchParams.get('range');
  const range: ReportRangeKey = isRange(rawRange) ? rawRange : 'this_month';
  const start = searchParams.get('start') ?? '';
  const end = searchParams.get('end') ?? '';

  const isCustomIncomplete = range === 'custom' && (!start || !end);

  const params: ReportRangeParams = useMemo(() => {
    if (range === 'custom') return { range, start: start || undefined, end: end || undefined };
    return { range };
  }, [range, start, end]);

  const updateParams = (mutate: (p: URLSearchParams) => void) => {
    const p = new URLSearchParams(searchParams);
    mutate(p);
    setSearchParams(p, { replace: true });
  };

  const selectTab = (next: ReportTab) => updateParams((p) => p.set('tab', next));
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

  const dashboardQuery = useQuery({
    queryKey: queryKeys.reports.dashboard(params),
    queryFn: () => reportsService.dashboard(params),
    enabled: tab === 'overview' && !isCustomIncomplete,
  });
  const revenueQuery = useQuery({
    queryKey: queryKeys.reports.revenue(params),
    queryFn: () => reportsService.revenue(params),
    enabled: tab === 'revenue' && !isCustomIncomplete,
  });
  const receivablesQuery = useQuery({
    queryKey: queryKeys.reports.receivables(params),
    queryFn: () => reportsService.receivables(params),
    enabled: tab === 'receivables' && !isCustomIncomplete,
  });
  const invoicesQuery = useQuery({
    queryKey: queryKeys.reports.invoices(params),
    queryFn: () => reportsService.invoices(params),
    enabled: tab === 'invoices' && !isCustomIncomplete,
  });
  const paymentsQuery = useQuery({
    queryKey: queryKeys.reports.payments(params),
    queryFn: () => reportsService.payments(params),
    enabled: tab === 'payments' && !isCustomIncomplete,
  });
  const customersQuery = useQuery({
    queryKey: queryKeys.reports.customers(params),
    queryFn: () => reportsService.customers(params),
    enabled: tab === 'customers' && !isCustomIncomplete,
  });
  const productsQuery = useQuery({
    queryKey: queryKeys.reports.products(params),
    queryFn: () => reportsService.products(params),
    enabled: tab === 'products' && !isCustomIncomplete,
  });

  const runExport = async (section: ReportExportSection) => {
    setExportingSection(section);
    try {
      const filename = `rooman_billing_report_${section}_${Date.now()}.csv`;
      await downloadAuthenticated(reportsService.exportUrl(section, params), filename);
      showToast('success', 'Export complete', `Exported ${humanize(section)} to CSV.`);
    } catch (err) {
      showToast('error', 'Export failed', toApiError(err).message);
    } finally {
      setExportingSection(null);
    }
  };

  return (
    <div className="space-y-6">
      <div {...ui.edit('header')}>
        <PageHeader
          eyebrow={ui.text('header', 'eyebrow')}
          title={ui.text('header', 'title')}
          subtitle={ui.text('header', 'subtitle')}
        />
      </div>

      {/* Date range picker */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="w-full sm:w-56">
              <Select
                aria-label="Date range"
                value={range}
                onChange={(e) => selectRange(e.target.value as ReportRangeKey)}
                options={RANGE_OPTIONS}
              />
            </div>
            {range === 'custom' && (
              <div className="flex items-center gap-2">
                <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} aria-label="Start date" />
                <span className="text-xs text-slate-400 shrink-0">to</span>
                <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} aria-label="End date" />
              </div>
            )}
            {isCustomIncomplete && (
              <span className="text-xs text-amber-600 font-medium">Select both a start and end date.</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <nav aria-label="Report sections" className="flex items-center gap-1 overflow-x-auto pb-1 border-b border-slate-200" {...ui.edit('tabs')}>
        {ui.shown('tabs').map((t) => {
          const Icon = TAB_ICONS[t.key] || BarChart3;
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => selectTab(t.key as ReportTab)}
              aria-current={active ? 'page' : undefined}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 -mb-px transition-colors cursor-pointer ${
                active
                  ? 'border-brand-600 text-brand-700 font-semibold'
                  : 'border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300'
              }`}
              {...ui.edit(`tabs.${t.key}`)}
            >
              <Icon className={`w-3.5 h-3.5 ${active ? 'text-brand-600' : 'text-slate-400'}`} />
              {t.label}
            </button>
          );
        })}
      </nav>

      {tab === 'overview' && (
        <QueryBoundary query={dashboardQuery} blocked={isCustomIncomplete} loadingMessage="Loading overview...">
          {(data) => <OverviewTab data={data} />}
        </QueryBoundary>
      )}
      {tab === 'revenue' && (
        <QueryBoundary query={revenueQuery} blocked={isCustomIncomplete} loadingMessage="Loading revenue analytics...">
          {(data) => <RevenueTab data={data} onExport={runExport} exportingSection={exportingSection} />}
        </QueryBoundary>
      )}
      {tab === 'receivables' && (
        <QueryBoundary query={receivablesQuery} blocked={isCustomIncomplete} loadingMessage="Loading receivables analytics...">
          {(data) => <ReceivablesTab data={data} onExport={runExport} exportingSection={exportingSection} />}
        </QueryBoundary>
      )}
      {tab === 'invoices' && (
        <QueryBoundary query={invoicesQuery} blocked={isCustomIncomplete} loadingMessage="Loading invoice analytics...">
          {(data) => <InvoicesTab data={data} />}
        </QueryBoundary>
      )}
      {tab === 'payments' && (
        <QueryBoundary query={paymentsQuery} blocked={isCustomIncomplete} loadingMessage="Loading payment analytics...">
          {(data) => <PaymentsTab data={data} onExport={runExport} exportingSection={exportingSection} />}
        </QueryBoundary>
      )}
      {tab === 'customers' && (
        <QueryBoundary query={customersQuery} blocked={isCustomIncomplete} loadingMessage="Loading customer analytics...">
          {(data) => <CustomersTab data={data} />}
        </QueryBoundary>
      )}
      {tab === 'products' && (
        <QueryBoundary query={productsQuery} blocked={isCustomIncomplete} loadingMessage="Loading product analytics...">
          {(data) => <ProductsTab data={data} />}
        </QueryBoundary>
      )}
    </div>
  );
}

export default ReportsPage;
