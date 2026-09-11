import { useState } from 'react';
import { AlertCircle, Clock, AlertTriangle, FileText, ClipboardCheck, CheckCircle2 } from 'lucide-react';
import type { ActionCategory, ActionItem } from '../../../types';
import { formatMoney } from '../../../utils/format';
import { useToast } from '../../../components/common/Toast';

export interface ActionCenterWidgetProps {
  items: ActionItem[];
}

const FILTERS: { key: 'all' | ActionCategory; label: string }[] = [
  { key: 'all', label: 'All Attention' },
  { key: 'overdue', label: 'Overdue Invoices' },
  { key: 'failed_payment', label: 'Failed Payments' },
  { key: 'expiring_trial', label: 'Expiring Trials' },
  { key: 'pending_quote', label: 'Pending Quotes' },
  { key: 'pending_approval', label: 'Pending Approvals' },
];

const ACTION_LABELS: Record<ActionItem['suggested_action'], string> = {
  send_reminder: 'Send Reminder',
  retry_payment: 'Retry Payment',
  convert_trial: 'Convert Trial',
  review_quote: 'Review Quote',
  review_approval: 'Review Approval',
};

export function ActionCenterWidget({ items }: ActionCenterWidgetProps) {
  const [filter, setFilter] = useState<'all' | ActionCategory>('all');
  const { showToast } = useToast();

  const filteredItems = items.filter((item) => filter === 'all' || item.category === filter);

  const handleAction = (_item: ActionItem) => {
    showToast(
      'info',
      'Not wired up yet',
      'Quick actions from the dashboard aren\'t connected to the backend yet — open the relevant record to continue.'
    );
  };

  const getCategoryBadge = (category: ActionItem['category']) => {
    switch (category) {
      case 'overdue':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#F9D9E8] text-[#D81B60] border border-[#F3B8D4]">
            <AlertCircle className="w-3 h-3" />
            Overdue
          </span>
        );
      case 'failed_payment':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#FCEBD9] text-[#C05621] border border-[#F7D7B5]">
            <AlertTriangle className="w-3 h-3" />
            Failed Payment
          </span>
        );
      case 'expiring_trial':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#E8EBFC] text-[#25247A] border border-[#D0D7F9]">
            <Clock className="w-3 h-3" />
            Trial Expiring
          </span>
        );
      case 'pending_quote':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#E9E8FA] text-[#3F51C9] border border-[#D0D7F9]">
            <FileText className="w-3 h-3" />
            Pending Quote
          </span>
        );
      case 'pending_approval':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#E9E8FA] text-[#25247A] border border-[#D0D7F9]">
            <ClipboardCheck className="w-3 h-3" />
            Pending Approval
          </span>
        );
    }
  };

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            Action Center
          </h3>
          {items.length > 0 && (
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#F9D9E8] text-[#D81B60]">
              {items.length} Item{items.length === 1 ? '' : 's'}
            </span>
          )}
        </div>
        <p className="text-xs text-slate-400">
          Items requiring operator intervention
        </p>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto text-xs pb-1 border-b border-slate-100">
        {FILTERS.map((t) => (
          <button
            key={t.key}
            onClick={() => setFilter(t.key)}
            className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
              filter === t.key
                ? 'bg-[#25247A] text-white shadow-xs'
                : 'text-slate-600 hover:bg-[#F7F8FC]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Item List */}
      {filteredItems.length === 0 ? (
        <div className="py-8 flex flex-col items-center gap-2 text-center">
          <CheckCircle2 className="w-6 h-6 text-emerald-500" />
          <p className="text-xs text-slate-400">
            {items.length === 0 ? "You're all caught up." : 'Nothing matches this filter.'}
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {filteredItems.map((item) => (
            <div
              key={item.id}
              className="p-3 rounded-xl border border-slate-200/80 hover:border-slate-300 hover:bg-slate-50/50 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3"
            >
              <div className="space-y-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  {getCategoryBadge(item.category)}
                  <span className="text-xs font-bold text-slate-900 truncate">
                    {item.title}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 line-clamp-1">
                  {item.description}
                </p>
                <p className="text-[10px] text-slate-400">{item.due_info}</p>
              </div>

              <div className="flex items-center gap-3 shrink-0 self-end sm:self-center">
                {item.amount && (
                  <span className="text-xs font-bold text-slate-900 tabular-nums">
                    {formatMoney(item.amount)}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => handleAction(item)}
                  className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1.5 rounded-lg bg-[#E8EBFC] text-[#25247A] border border-[#D0D7F9] hover:bg-[#25247A] hover:text-white transition-colors cursor-pointer"
                >
                  <span>{ACTION_LABELS[item.suggested_action]}</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
