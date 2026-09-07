import { useState } from 'react';
import { AlertCircle, Clock, AlertTriangle, FileText, ArrowRight } from 'lucide-react';
import { mockActionCenterItems, ActionCenterItem } from '../mockDashboardData';
import { useToast } from '../../../components/common/Toast';

export function ActionCenterWidget() {
  const [filter, setFilter] = useState<'all' | 'overdue' | 'failed_payment' | 'expiring_trial' | 'pending_quote'>('all');
  const { showToast } = useToast();

  const filteredItems = mockActionCenterItems.filter(
    (item) => filter === 'all' || item.category === filter
  );

  const handleAction = (item: ActionCenterItem) => {
    switch (item.category) {
      case 'overdue':
        showToast('success', 'Reminder Dispatched', `Automated payment notification sent to ${item.account}`);
        break;
      case 'failed_payment':
        showToast('info', 'Retry Triggered', `Gateway retry initiated for ${item.account}`);
        break;
      case 'expiring_trial':
        showToast('info', 'Trial Conversion', `Initiated enterprise upgrade checkout for ${item.account}`);
        break;
      case 'pending_quote':
        showToast('info', 'Quote Viewed', `Opening proposal for ${item.account}`);
        break;
    }
  };

  const getCategoryBadge = (category: ActionCenterItem['category']) => {
    switch (category) {
      case 'overdue':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
            <AlertCircle className="w-3 h-3" />
            Overdue
          </span>
        );
      case 'failed_payment':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
            <AlertTriangle className="w-3 h-3" />
            Failed Payment
          </span>
        );
      case 'expiring_trial':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
            <Clock className="w-3 h-3" />
            Trial Expiring
          </span>
        );
      case 'pending_quote':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200">
            <FileText className="w-3 h-3" />
            Pending Quote
          </span>
        );
    }
  };

  const getActionLabel = (category: ActionCenterItem['category']) => {
    switch (category) {
      case 'overdue':
        return 'Send Reminder';
      case 'failed_payment':
        return 'Retry Payment';
      case 'expiring_trial':
        return 'Convert Trial';
      case 'pending_quote':
        return 'Review Quote';
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
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700">
            {mockActionCenterItems.length} Urgent Items
          </span>
        </div>
        <p className="text-xs text-slate-400">
          Items requiring operator intervention
        </p>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto text-xs pb-1 border-b border-slate-100">
        {[
          { key: 'all', label: 'All Attention' },
          { key: 'overdue', label: 'Overdue Invoices' },
          { key: 'failed_payment', label: 'Failed Payments' },
          { key: 'expiring_trial', label: 'Expiring Trials' },
          { key: 'pending_quote', label: 'Pending Quotes' },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setFilter(t.key as typeof filter)}
            className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
              filter === t.key
                ? 'bg-slate-900 text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Item List */}
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
            </div>

            <div className="flex items-center gap-3 shrink-0 self-end sm:self-center">
              {item.amount && (
                <span className="text-xs font-bold text-slate-900 tabular-nums">
                  {item.amount}
                </span>
              )}
              <button
                type="button"
                onClick={() => handleAction(item)}
                className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1.5 rounded-lg bg-brand-50 text-brand-700 border border-blue-200/70 hover:bg-brand-600 hover:text-white transition-colors cursor-pointer"
              >
                <span>{getActionLabel(item.category)}</span>
                <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
