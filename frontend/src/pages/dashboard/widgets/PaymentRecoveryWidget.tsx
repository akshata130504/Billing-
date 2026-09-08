import { Bell, CheckCircle2, AlertTriangle, TrendingUp } from 'lucide-react';
import type { DashboardRecovery } from '../../../types';
import { formatMoney, formatNumber, parseMoney } from '../../../utils/format';

export interface PaymentRecoveryWidgetProps {
  recovery: DashboardRecovery;
  currency: string;
}

export function PaymentRecoveryWidget({ recovery, currency }: PaymentRecoveryWidgetProps) {
  const failedAmount = parseMoney(recovery.failed_amount) || 0;
  const recoveredAmount = parseMoney(recovery.recovered_amount) || 0;
  const base = failedAmount + recoveredAmount;
  const recoveryRatePct = base > 0 ? (recoveredAmount / base) * 100 : 0;

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            Payment Recovery (Dunning)
          </h3>
          <p className="text-xs text-slate-400">
            Failed payment retries & reminder-driven collections
          </p>
        </div>
      </div>

      {/* 4 Cards Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Failed Payments */}
        <div className="p-3.5 rounded-xl border border-rose-200/80 bg-rose-50/30">
          <div className="flex items-center gap-2 text-rose-700 text-xs font-bold">
            <AlertTriangle className="w-4 h-4 text-rose-500" />
            <span>Failed Payments</span>
          </div>
          <span className="text-base font-bold text-slate-900 tabular-nums block mt-2">
            {formatMoney(recovery.failed_amount, currency)}
          </span>
          <span className="text-[10px] text-slate-400 block mt-0.5">
            {formatNumber(recovery.failed_payments)} transaction failures
          </span>
        </div>

        {/* Reminders Sent */}
        <div className="p-3.5 rounded-xl border border-amber-200/80 bg-amber-50/30">
          <div className="flex items-center gap-2 text-amber-700 text-xs font-bold">
            <Bell className="w-4 h-4 text-amber-500" />
            <span>Reminders Sent</span>
          </div>
          <span className="text-base font-bold text-slate-900 tabular-nums block mt-2">
            {formatNumber(recovery.reminders_sent)}
          </span>
          <span className="text-[10px] text-slate-400 block mt-0.5">
            dunning reminders this period
          </span>
        </div>

        {/* Recovered Payments */}
        <div className="p-3.5 rounded-xl border border-emerald-200/80 bg-emerald-50/30">
          <div className="flex items-center gap-2 text-emerald-700 text-xs font-bold">
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            <span>Recovered</span>
          </div>
          <span className="text-base font-bold text-slate-900 tabular-nums block mt-2">
            {formatMoney(recovery.recovered_amount, currency)}
          </span>
        </div>

        {/* Recovery Rate */}
        <div className="p-3.5 rounded-xl border border-blue-200/80 bg-blue-50/30">
          <div className="flex items-center gap-2 text-brand-700 text-xs font-bold">
            <TrendingUp className="w-4 h-4 text-brand-500" />
            <span>Recovery Rate</span>
          </div>
          <span className="text-xl font-bold text-brand-700 tabular-nums block mt-1.5">
            {base > 0 ? `${recoveryRatePct.toFixed(1)}%` : '—'}
          </span>
        </div>
      </div>
    </div>
  );
}
