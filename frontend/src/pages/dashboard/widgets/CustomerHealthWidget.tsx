import { HeartPulse } from 'lucide-react';
import { mockCustomerHealth } from '../mockDashboardData';

export function CustomerHealthWidget() {
  const health = mockCustomerHealth;

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <HeartPulse className="w-4 h-4 text-emerald-600" />
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            Customer Health
          </h3>
        </div>
        <span className="text-xs text-slate-400">
          1,420 Active Client Accounts
        </span>
      </div>

      {/* Segmented Progress Bar */}
      <div className="w-full h-3 rounded-full overflow-hidden flex bg-slate-100 p-0.5 gap-0.5">
        <div
          style={{ width: `${health.healthy.percentage}%` }}
          className="bg-emerald-500 rounded-l-full h-full"
          title={`Healthy: ${health.healthy.percentage}%`}
        />
        <div
          style={{ width: `${health.needsAttention.percentage}%` }}
          className="bg-amber-400 h-full"
          title={`Needs Attention: ${health.needsAttention.percentage}%`}
        />
        <div
          style={{ width: `${health.atRisk.percentage}%` }}
          className="bg-orange-500 h-full"
          title={`At Risk: ${health.atRisk.percentage}%`}
        />
        <div
          style={{ width: `${health.churned.percentage}%` }}
          className="bg-rose-500 rounded-r-full h-full"
          title={`Churned: ${health.churned.percentage}%`}
        />
      </div>

      {/* Health Breakdown Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        {/* Healthy */}
        <div className="p-3 rounded-xl bg-emerald-50/50 border border-emerald-100/80">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span className="text-xs font-bold text-emerald-900">Healthy</span>
          </div>
          <div className="mt-2">
            <span className="text-lg font-bold text-slate-900 tabular-nums">
              {health.healthy.count}
            </span>
            <span className="text-[11px] text-emerald-700 font-semibold ml-1">
              ({health.healthy.percentage}%)
            </span>
          </div>
          <span className="text-[10px] text-slate-500 mt-1 block">
            MRR: {health.healthy.mrr}
          </span>
        </div>

        {/* Needs Attention */}
        <div className="p-3 rounded-xl bg-amber-50/50 border border-amber-100/80">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            <span className="text-xs font-bold text-amber-900">Needs Attention</span>
          </div>
          <div className="mt-2">
            <span className="text-lg font-bold text-slate-900 tabular-nums">
              {health.needsAttention.count}
            </span>
            <span className="text-[11px] text-amber-700 font-semibold ml-1">
              ({health.needsAttention.percentage}%)
            </span>
          </div>
          <span className="text-[10px] text-slate-500 mt-1 block">
            MRR: {health.needsAttention.mrr}
          </span>
        </div>

        {/* At Risk */}
        <div className="p-3 rounded-xl bg-orange-50/50 border border-orange-100/80">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-orange-500" />
            <span className="text-xs font-bold text-orange-900">At Risk</span>
          </div>
          <div className="mt-2">
            <span className="text-lg font-bold text-slate-900 tabular-nums">
              {health.atRisk.count}
            </span>
            <span className="text-[11px] text-orange-700 font-semibold ml-1">
              ({health.atRisk.percentage}%)
            </span>
          </div>
          <span className="text-[10px] text-slate-500 mt-1 block">
            MRR: {health.atRisk.mrr}
          </span>
        </div>

        {/* Churned */}
        <div className="p-3 rounded-xl bg-rose-50/50 border border-rose-100/80">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            <span className="text-xs font-bold text-rose-900">Churned</span>
          </div>
          <div className="mt-2">
            <span className="text-lg font-bold text-slate-900 tabular-nums">
              {health.churned.count}
            </span>
            <span className="text-[11px] text-rose-700 font-semibold ml-1">
              ({health.churned.percentage}%)
            </span>
          </div>
          <span className="text-[10px] text-slate-500 mt-1 block">
            Lost: {health.churned.mrr}
          </span>
        </div>
      </div>
    </div>
  );
}
