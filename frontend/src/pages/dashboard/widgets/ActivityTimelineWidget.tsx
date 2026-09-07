import { useState } from 'react';
import { ActivityItem, ActivityCategory } from '../../../types';
import { mockActivityTimeline } from '../mockDashboardData';
import { Receipt, Users, CreditCard, Cpu, ArrowRight } from 'lucide-react';

export function ActivityTimelineWidget() {
  const [activeCategory, setActiveCategory] = useState<ActivityCategory>('all');

  const filtered = mockActivityTimeline.filter(
    (item) => activeCategory === 'all' || item.category === activeCategory
  );

  const getCategoryIcon = (category: ActivityItem['category']) => {
    switch (category) {
      case 'billing':
        return <Receipt className="w-3.5 h-3.5 text-blue-600" />;
      case 'customers':
        return <Users className="w-3.5 h-3.5 text-purple-600" />;
      case 'payments':
        return <CreditCard className="w-3.5 h-3.5 text-emerald-600" />;
      case 'system':
      default:
        return <Cpu className="w-3.5 h-3.5 text-amber-600" />;
    }
  };

  const getCategoryBg = (category: ActivityItem['category']) => {
    switch (category) {
      case 'billing':
        return 'bg-blue-50 border-blue-100';
      case 'customers':
        return 'bg-purple-50 border-purple-100';
      case 'payments':
        return 'bg-emerald-50 border-emerald-100';
      case 'system':
      default:
        return 'bg-amber-50 border-amber-100';
    }
  };

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            Recent Activity Timeline
          </h3>
          <p className="text-xs text-slate-400">
            Real-time audit log across all system subsystems
          </p>
        </div>

        {/* Filter Chips */}
        <div className="flex items-center gap-1 overflow-x-auto text-xs">
          {(
            [
              { key: 'all', label: 'All' },
              { key: 'billing', label: 'Billing' },
              { key: 'customers', label: 'Customers' },
              { key: 'payments', label: 'Payments' },
              { key: 'system', label: 'System' },
            ] as const
          ).map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveCategory(tab.key)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium capitalize transition-colors ${
                activeCategory === tab.key
                  ? 'bg-slate-900 text-white shadow-xs'
                  : 'text-slate-500 hover:bg-slate-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Timeline List */}
      <div className="space-y-3.5 pt-1 relative">
        {filtered.length === 0 ? (
          <div className="py-8 text-center text-xs text-slate-400">
            No events found in &ldquo;{activeCategory}&rdquo;
          </div>
        ) : (
          filtered.map((item, idx) => (
            <div key={item.id} className="flex items-start gap-3 relative">
              {/* Vertical connector line */}
              {idx < filtered.length - 1 && (
                <div className="absolute left-3.5 top-7 bottom-0 w-px bg-slate-100 -mb-3.5" />
              )}

              {/* Icon */}
              <div
                className={`w-7 h-7 rounded-xl border flex items-center justify-center shrink-0 z-10 ${getCategoryBg(
                  item.category
                )}`}
              >
                {getCategoryIcon(item.category)}
              </div>

              {/* Body */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <h4 className="text-xs font-bold text-slate-900 truncate">
                    {item.title}
                  </h4>
                  <span className="text-[10px] text-slate-400 shrink-0 font-medium">
                    {item.timestamp}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                  {item.description}
                </p>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer View Full Audit Trail */}
      <div className="pt-2 border-t border-slate-100 flex justify-end">
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700"
        >
          <span>View Full Audit Trail</span>
          <ArrowRight className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}
