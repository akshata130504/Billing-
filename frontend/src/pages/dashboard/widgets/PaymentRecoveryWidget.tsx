import { RotateCcw, CheckCircle2, AlertTriangle, TrendingUp } from 'lucide-react';
import { mockPaymentRecovery } from '../mockDashboardData';

export function PaymentRecoveryWidget() {
  const recovery = mockPaymentRecovery;

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            Payment Recovery (Smart Dunning)
          </h3>
          <p className="text-xs text-slate-400">
            Automated payment retry & failed invoice reclamation
          </p>
        </div>
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
          <TrendingUp className="w-3 h-3" />
          {recovery.rateImprovement}
        </span>
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
            {recovery.failedPaymentsAmount}
          </span>
          <span className="text-[10px] text-slate-400 block mt-0.5">
            {recovery.failedCount} transaction failures
          </span>
        </div>

        {/* Retry Scheduled */}
        <div className="p-3.5 rounded-xl border border-amber-200/80 bg-amber-50/30">
          <div className="flex items-center gap-2 text-amber-700 text-xs font-bold">
            <RotateCcw className="w-4 h-4 text-amber-500" />
            <span>Retry Scheduled</span>
          </div>
          <span className="text-base font-bold text-slate-900 tabular-nums block mt-2">
            {recovery.retryScheduledAmount}
          </span>
          <span className="text-[10px] text-slate-400 block mt-0.5">
            {recovery.retryCount} auto-retries queued
          </span>
        </div>

        {/* Recovered Payments */}
        <div className="p-3.5 rounded-xl border border-emerald-200/80 bg-emerald-50/30">
          <div className="flex items-center gap-2 text-emerald-700 text-xs font-bold">
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            <span>Recovered</span>
          </div>
          <span className="text-base font-bold text-slate-900 tabular-nums block mt-2">
            {recovery.recoveredPaymentsAmount}
          </span>
          <span className="text-[10px] text-slate-400 block mt-0.5">
            {recovery.recoveredCount} salvaged accounts
          </span>
        </div>

        {/* Recovery Rate */}
        <div className="p-3.5 rounded-xl border border-blue-200/80 bg-blue-50/30">
          <div className="flex items-center gap-2 text-brand-700 text-xs font-bold">
            <TrendingUp className="w-4 h-4 text-brand-500" />
            <span>Recovery Rate</span>
          </div>
          <span className="text-xl font-bold text-brand-700 tabular-nums block mt-1.5">
            {recovery.recoveryRate}
          </span>
          <span className="text-[10px] text-emerald-600 font-semibold block mt-0.5">
            Industry benchmark: 62%
          </span>
        </div>
      </div>
    </div>
  );
}
