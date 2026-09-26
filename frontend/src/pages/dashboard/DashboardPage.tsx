import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  FileText,
  IndianRupee,
  CreditCard,
  Clock,
  Calendar,
  ChevronDown,
  ArrowUp,
  SlidersHorizontal,
  Repeat,
  UserMinus,
} from 'lucide-react';
import { controlCenterService } from '../../services/controlCenterService';
import { dashboardSummaryService, formatPerCurrency } from '../../services/dashboardSummaryService';
import { toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { useAuth } from '../../hooks/useAuth';
import { useToast } from '../../components/common/Toast';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { formatMoney, formatPercent, parseMoney } from '../../utils/format';
import { RevenueOverviewWidget } from './widgets/RevenueOverviewWidget';
import { ActionCenterWidget } from './widgets/ActionCenterWidget';
import { BillingPipelineWidget } from './widgets/BillingPipelineWidget';
import { CustomerHealthWidget } from './widgets/CustomerHealthWidget';
import { PaymentRecoveryWidget } from './widgets/PaymentRecoveryWidget';
import { RecentInvoicesWidget } from './widgets/RecentInvoicesWidget';
import { ActivityTimelineWidget } from './widgets/ActivityTimelineWidget';
import { CustomizeDashboardModal } from './widgets/CustomizeDashboardModal';
import { PaymentStatusWidget } from './widgets/PaymentStatusWidget';
import { QuickActionsCard } from './QuickActionsCard';
import { BillingPromoCard } from './widgets/BillingPromoCard';
import type { DashboardRange, WidgetVisibilityState } from '../../types';

export function DashboardPage() {
  const { showToast } = useToast();
  const { user } = useAuth();

  // Date Range Filter State. The backend only understands the five DashboardRange
  // values below; "custom" is a UI-only placeholder until a real custom-range
  // query is implemented.
  const [dateFilter, setDateFilter] = useState<DashboardRange>('30_days');
  const [dateDropdownOpen, setDateDropdownOpen] = useState(false);

  // Customize Dashboard State
  const [customizeOpen, setCustomizeOpen] = useState(false);
  const [visibility, setVisibility] = useState<WidgetVisibilityState>({
    revenueIntelligence: true,
    actionCenter: true,
    billingPipeline: true,
    customerHealth: true,
    paymentRecovery: true,
    recentTransactions: true,
    activityTimeline: true,
  });

  const handleToggleWidget = (key: keyof WidgetVisibilityState) => {
    setVisibility((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleResetWidgets = () => {
    setVisibility({
      revenueIntelligence: true,
      actionCenter: true,
      billingPipeline: true,
      customerHealth: true,
      paymentRecovery: true,
      recentTransactions: true,
      activityTimeline: true,
    });
    showToast('info', 'Reset Layout', 'All dashboard widgets restored to default view.');
  };

  const dateFilterLabels: Record<DashboardRange, string> = {
    today: 'Today',
    '7_days': 'Last 7 Days',
    '30_days': 'Last 30 Days',
    '3_months': 'Last 3 Months',
    '12_months': 'Last 12 Months',
  };

  const summary = useQuery({
    queryKey: queryKeys.controlCenter.dashboard(dateFilter),
    queryFn: () => controlCenterService.dashboard(dateFilter),
  });

  const actionCenter = useQuery({
    queryKey: queryKeys.controlCenter.actionCenter(),
    queryFn: () => controlCenterService.actionCenter(),
  });

  // Server-side, currency-aware counters (invoice counts, collections, receivables).
  // Keyed under 'control-center' so the existing control-center invalidation refreshes it.
  const financial = useQuery({
    queryKey: ['control-center', 'financial-summary', dateFilter] as const,
    queryFn: () => dashboardSummaryService.financial({ range: dateFilter }),
  });

  const firstName = user?.full_name?.trim().split(/\s+/)[0] || 'there';

  if (summary.isPending) {
    return <LoadingState message="Loading your dashboard..." />;
  }
  if (summary.isError) {
    return (
      <ErrorState
        message={toApiError(summary.error).message}
        onRetry={() => void summary.refetch()}
      />
    );
  }

  const { metrics, revenue, pipeline, customer_health, recovery, recent_transactions, activity, currency } =
    summary.data;

  const fin = financial.data;
  // Prefer the server summary (real counts, per-currency money); fall back to the
  // pipeline figures while it loads or if it failed.
  const pipelineInvoiceCount =
    (pipeline?.draft?.count || 0) +
    (pipeline?.sent?.count || 0) +
    (pipeline?.partially_paid?.count || 0) +
    (pipeline?.overdue?.count || 0) +
    (pipeline?.paid_this_period?.count || 0);
  const totalInvoices = fin ? fin.invoices.total_count : pipelineInvoiceCount;
  const overdueInvoices = fin
    ? fin.receivables.reduce((n, r) => n + r.overdue_count, 0)
    : pipeline?.overdue?.count || 0;

  const totalRevNum = parseMoney(metrics?.total_revenue) || 0;
  const paymentsRecvNum = parseMoney(pipeline?.paid_this_period?.amount) || 0;
  const outstandingNum = fin
    ? fin.receivables.reduce((sum, r) => sum + (parseMoney(r.amount_due) || 0), 0)
    : parseMoney(metrics?.outstanding_amount) || 0;
  const paymentsReceivedLabel = fin
    ? formatPerCurrency(fin.payments_collected, (r) => r.net, formatMoney, currency)
    : formatMoney(paymentsRecvNum, currency);
  const paymentsReceivedChange = fin
    ? `${fin.payments_collected.reduce((n, r) => n + r.count, 0)} payments this period`
    : `${pipeline?.paid_this_period?.count || 0} paid this period`;
  const outstandingLabel = fin
    ? formatPerCurrency(fin.receivables, (r) => r.amount_due, formatMoney, currency)
    : formatMoney(outstandingNum, currency);
  const outstandingCount = fin
    ? fin.receivables.reduce((n, r) => n + r.open_count, 0)
    : metrics?.outstanding_count || 0;

  const revChangePct = metrics?.revenue_change_pct
    ? `${metrics.revenue_change_pct}% from last period`
    : 'No prior period data';
  const isRevPositive = !metrics?.revenue_change_pct || !metrics.revenue_change_pct.startsWith('-');

  const mrrCurrency = revenue?.mrr_currency || currency;
  const otherMrr = Object.entries(revenue?.mrr_other_currencies ?? {});
  const mrrChange =
    otherMrr.length > 0
      ? `+ ${otherMrr.map(([cur, amt]) => formatMoney(amt, cur)).join(', ')} in other currencies`
      : revenue?.mrr_change_pct
        ? `${revenue.mrr_change_pct}% from last period`
        : 'No prior period data';
  const churnRate = customer_health?.churn_rate ?? null;
  const churnedCustomers = customer_health?.churned_customers ?? 0;

  const kpiCards = [
    {
      title: 'Total Invoices',
      value: String(totalInvoices),
      change: `${overdueInvoices} overdue`,
      changeColor: overdueInvoices > 0 ? 'text-[#E83E8C]' : 'text-[#10B981]',
      icon: (
        <div className="w-12 h-12 rounded-2xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center shrink-0">
          <FileText className="w-5 h-5 stroke-[2]" />
        </div>
      ),
    },
    {
      title: 'Total Revenue',
      value: formatMoney(totalRevNum, currency),
      change: revChangePct,
      changeColor: isRevPositive ? 'text-[#10B981]' : 'text-[#E83E8C]',
      icon: (
        <div className="w-12 h-12 rounded-full bg-[#DDF4EA] text-[#10B981] flex items-center justify-center shrink-0">
          <IndianRupee className="w-5 h-5 stroke-[2.5]" />
        </div>
      ),
    },
    {
      title: 'Payments Received',
      value: paymentsReceivedLabel,
      change: paymentsReceivedChange,
      changeColor: 'text-[#10B981]',
      icon: (
        <div className="w-12 h-12 rounded-2xl bg-[#F9D9E8] text-[#E83E8C] flex items-center justify-center shrink-0">
          <CreditCard className="w-5 h-5 stroke-[2]" />
        </div>
      ),
    },
    {
      title: 'Outstanding',
      value: outstandingLabel,
      change: `${outstandingCount} unpaid invoices`,
      changeColor: outstandingNum > 0 ? 'text-[#E83E8C]' : 'text-[#10B981]',
      icon: (
        <div className="w-12 h-12 rounded-full bg-[#FCEBD9] text-[#E07A28] flex items-center justify-center shrink-0">
          <Clock className="w-5 h-5 stroke-[2]" />
        </div>
      ),
    },
    {
      title: `MRR (${mrrCurrency})`,
      value: formatMoney(revenue?.mrr ?? 0, mrrCurrency),
      change: mrrChange,
      changeColor:
        otherMrr.length === 0 && revenue?.mrr_change_pct?.startsWith('-') ? 'text-[#E83E8C]' : 'text-[#10B981]',
      icon: (
        <div className="w-12 h-12 rounded-2xl bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center shrink-0">
          <Repeat className="w-5 h-5 stroke-[2]" />
        </div>
      ),
    },
    {
      title: 'Churn Rate',
      value: churnRate !== null ? formatPercent(churnRate, 2) : '—',
      change:
        churnRate !== null
          ? `${churnedCustomers} of ${customer_health?.customers_at_period_start ?? 0} customers lost`
          : 'No customers at period start',
      changeColor: churnedCustomers > 0 ? 'text-[#E83E8C]' : 'text-[#10B981]',
      icon: (
        <div className="w-12 h-12 rounded-full bg-[#F9D9E8] text-[#E83E8C] flex items-center justify-center shrink-0">
          <UserMinus className="w-5 h-5 stroke-[2]" />
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Top Header Controls: Greeting, Date Filter, Customize */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
              Welcome back, {firstName}!
            </h1>
            <span className="text-xl">👋</span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Here&apos;s what&apos;s happening with your billing & revenue operations today.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2.5 self-start lg:self-auto flex-wrap">
          {/* Date Filter Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setDateDropdownOpen((prev) => !prev)}
              className="inline-flex items-center gap-2 px-3 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-200/90 rounded-xl hover:bg-slate-50 shadow-2xs transition-colors cursor-pointer"
            >
              <Calendar className="w-3.5 h-3.5 text-slate-400" />
              <span>{dateFilterLabels[dateFilter]}</span>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </button>

            {dateDropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-20"
                  onClick={() => setDateDropdownOpen(false)}
                />
                <div className="absolute right-0 mt-1.5 w-44 bg-white rounded-xl shadow-modal border border-slate-200 py-1.5 z-30 divide-y divide-slate-100">
                  {(['today', '7_days', '30_days', '3_months', '12_months'] as const).map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => {
                        setDateFilter(option);
                        setDateDropdownOpen(false);
                      }}
                      className={`w-full px-3.5 py-2 text-xs text-left font-medium transition-colors ${
                        dateFilter === option
                          ? 'bg-blue-50 text-brand-700 font-semibold'
                          : 'text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      {dateFilterLabels[option]}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Customize Dashboard Button */}
          <button
            type="button"
            onClick={() => setCustomizeOpen(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-white bg-gradient-to-r from-[#E83E8C] to-[#D81B60] hover:from-[#D81B60] hover:to-[#C2185B] active:opacity-90 rounded-xl shadow-xs transition-all cursor-pointer"
          >
            <SlidersHorizontal className="w-3.5 h-3.5 text-white" />
            <span>Customize Dashboard</span>
          </button>
        </div>
      </div>

      {/* Core Financial KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {kpiCards.map((metric) => (
          <div
            key={metric.title}
            className="bg-white p-5 rounded-2xl border border-[#E7E9F2] shadow-sm flex flex-col justify-between"
          >
            <div className="flex items-center gap-3.5">
              {metric.icon}
              <div className="min-w-0">
                <span className="text-xs font-medium text-[#7B829A] block truncate">
                  {metric.title}
                </span>
                <span className="text-xl sm:text-2xl font-bold text-[#11194F] tracking-tight tabular-nums block mt-0.5 truncate">
                  {metric.value}
                </span>
              </div>
            </div>

            <div className="mt-3.5 flex items-center text-xs">
              <span
                className={`inline-flex items-center gap-1 font-medium text-xs ${metric.changeColor}`}
              >
                <ArrowUp className="w-3.5 h-3.5 stroke-[2.5]" />
                <span>{metric.change}</span>
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Main Dashboard Layout (Left Column: Charts & Tables | Right Column: Payment Status, Quick Actions, Promo & Operations) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column (8 cols): Revenue Overview dual-bar chart + Recent Invoices table */}
        <div className="lg:col-span-8 space-y-6">
          {visibility.revenueIntelligence && (
            <RevenueOverviewWidget revenue={revenue} currency={currency} />
          )}

          {visibility.recentTransactions && (
            <RecentInvoicesWidget transactions={recent_transactions} />
          )}

          {visibility.billingPipeline && (
            <BillingPipelineWidget pipeline={pipeline} currency={currency} />
          )}

          {visibility.customerHealth && (
            <CustomerHealthWidget health={customer_health} />
          )}

          {visibility.paymentRecovery && (
            <PaymentRecoveryWidget recovery={recovery} currency={currency} />
          )}
        </div>

        {/* Right Column (4 cols): Payment Status Donut + Quick Actions + Billing Promo Banner + Operations */}
        <div className="lg:col-span-4 space-y-6">
          {/* Payment Status Donut Chart Card */}
          <PaymentStatusWidget
            pipeline={pipeline}
            metrics={metrics}
            customerHealth={customer_health}
          />

          {/* Quick Actions 2x2 Grid Tile Card */}
          <QuickActionsCard />

          {/* Streamline Your Billing Promo Card */}
          <BillingPromoCard />

          {/* Action Center Widget */}
          {visibility.actionCenter && (
            actionCenter.isPending ? (
              <LoadingState message="Loading action items..." />
            ) : actionCenter.isError ? (
              <ErrorState
                message={toApiError(actionCenter.error).message}
                onRetry={() => void actionCenter.refetch()}
              />
            ) : (
              <ActionCenterWidget items={actionCenter.data.items} />
            )
          )}

          {/* Activity Timeline Widget */}
          {visibility.activityTimeline && (
            <ActivityTimelineWidget activity={activity} />
          )}
        </div>
      </div>

      {/* Customize Dashboard Modal */}
      <CustomizeDashboardModal
        isOpen={customizeOpen}
        onClose={() => setCustomizeOpen(false)}
        visibility={visibility}
        onToggle={handleToggleWidget}
        onReset={handleResetWidgets}
      />
    </div>
  );
}
