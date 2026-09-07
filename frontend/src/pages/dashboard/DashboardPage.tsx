import { useState } from 'react';
import {
  DollarSign,
  Receipt,
  Users,
  AlertTriangle,
  Calendar,
  ChevronDown,
  ArrowUp,
  ArrowDown,
  SlidersHorizontal,
} from 'lucide-react';
import { mockDashboardMetrics } from './mockDashboardData';
import { RevenueIntelligenceWidget } from './widgets/RevenueIntelligenceWidget';
import { ActionCenterWidget } from './widgets/ActionCenterWidget';
import { BillingPipelineWidget } from './widgets/BillingPipelineWidget';
import { CustomerHealthWidget } from './widgets/CustomerHealthWidget';
import { PaymentRecoveryWidget } from './widgets/PaymentRecoveryWidget';
import { RecentTransactionsWidget } from './widgets/RecentTransactionsWidget';
import { ActivityTimelineWidget } from './widgets/ActivityTimelineWidget';
import { CustomizeDashboardModal } from './widgets/CustomizeDashboardModal';
import { DateRangeFilter, WidgetVisibilityState } from '../../types';
import { useToast } from '../../components/common/Toast';

export function DashboardPage() {
  const { showToast } = useToast();

  // Date Range Filter State
  const [dateFilter, setDateFilter] = useState<DateRangeFilter>('30_days');
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

  const dateFilterLabels: Record<DateRangeFilter, string> = {
    today: 'Today',
    '7_days': 'Last 7 Days',
    '30_days': 'Last 30 Days',
    '3_months': 'Last 3 Months',
    '12_months': 'Last 12 Months',
    custom: 'Custom Range',
  };

  const statIcons = [
    <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
      <DollarSign className="w-5 h-5" />
    </div>,
    <div className="w-10 h-10 rounded-xl bg-blue-50 text-brand-600 flex items-center justify-center shrink-0">
      <Receipt className="w-5 h-5" />
    </div>,
    <div className="w-10 h-10 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center shrink-0">
      <Users className="w-5 h-5" />
    </div>,
    <div className="w-10 h-10 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
      <AlertTriangle className="w-5 h-5" />
    </div>,
  ];

  return (
    <div className="space-y-6">
      {/* Top Header Controls: Greeting, Date Filter, Customize */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
              Welcome back, Akshata!
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
                  {(
                    [
                      'today',
                      '7_days',
                      '30_days',
                      '3_months',
                      '12_months',
                      'custom',
                    ] as const
                  ).map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => {
                        setDateFilter(option);
                        setDateDropdownOpen(false);
                        showToast('info', 'Filter Updated', `Dashboard recalculating for ${dateFilterLabels[option]}`);
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
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-200/90 rounded-xl hover:bg-slate-50 shadow-2xs transition-colors cursor-pointer"
          >
            <SlidersHorizontal className="w-3.5 h-3.5 text-slate-500" />
            <span>Customize Dashboard</span>
          </button>
        </div>
      </div>

      {/* 4 Core Financial KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {mockDashboardMetrics.map((metric, idx) => (
          <div
            key={metric.title}
            className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm flex flex-col justify-between"
          >
            <div className="flex items-center gap-3">
              {statIcons[idx]}
              <div className="min-w-0">
                <span className="text-xs font-medium text-slate-500 block truncate">
                  {metric.title}
                </span>
                <span className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight tabular-nums block mt-0.5 truncate">
                  {metric.value}
                </span>
              </div>
            </div>

            <div className="mt-4 flex items-center gap-1.5 text-xs">
              <span
                className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md font-bold text-[11px] shrink-0 ${
                  metric.isPositive
                    ? 'bg-emerald-50 text-emerald-600'
                    : 'bg-rose-50 text-rose-600'
                }`}
              >
                {metric.isPositive ? (
                  <ArrowUp className="w-3 h-3 stroke-[3]" />
                ) : (
                  <ArrowDown className="w-3 h-3 stroke-[3]" />
                )}
                {metric.change}
              </span>
              <span className="text-slate-400 text-[11px] truncate">
                {metric.comparisonText}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Main Dashboard Widgets (Orchestrated by Customization Visibility) */}
      <div className="space-y-6">
        {/* Row 1: Revenue Intelligence (7 cols) & Action Center (5 cols) */}
        {(visibility.revenueIntelligence || visibility.actionCenter) && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {visibility.revenueIntelligence && (
              <div
                className={
                  visibility.actionCenter ? 'lg:col-span-7' : 'lg:col-span-12'
                }
              >
                <RevenueIntelligenceWidget />
              </div>
            )}
            {visibility.actionCenter && (
              <div
                className={
                  visibility.revenueIntelligence
                    ? 'lg:col-span-5'
                    : 'lg:col-span-12'
                }
              >
                <ActionCenterWidget />
              </div>
            )}
          </div>
        )}

        {/* Row 2: Billing Pipeline (Full width flow) */}
        {visibility.billingPipeline && (
          <div>
            <BillingPipelineWidget />
          </div>
        )}

        {/* Row 3: Customer Health (6 cols) & Payment Recovery (6 cols) */}
        {(visibility.customerHealth || visibility.paymentRecovery) && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {visibility.customerHealth && (
              <div
                className={
                  visibility.paymentRecovery ? 'lg:col-span-6' : 'lg:col-span-12'
                }
              >
                <CustomerHealthWidget />
              </div>
            )}
            {visibility.paymentRecovery && (
              <div
                className={
                  visibility.customerHealth ? 'lg:col-span-6' : 'lg:col-span-12'
                }
              >
                <PaymentRecoveryWidget />
              </div>
            )}
          </div>
        )}

        {/* Row 4: Recent Transactions (7 cols) & Recent Activity Timeline (5 cols) */}
        {(visibility.recentTransactions || visibility.activityTimeline) && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {visibility.recentTransactions && (
              <div
                className={
                  visibility.activityTimeline ? 'lg:col-span-7' : 'lg:col-span-12'
                }
              >
                <RecentTransactionsWidget />
              </div>
            )}
            {visibility.activityTimeline && (
              <div
                className={
                  visibility.recentTransactions ? 'lg:col-span-5' : 'lg:col-span-12'
                }
              >
                <ActivityTimelineWidget />
              </div>
            )}
          </div>
        )}
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
