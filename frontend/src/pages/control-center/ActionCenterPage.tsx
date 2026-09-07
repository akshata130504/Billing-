import { useState } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import {
  AlertTriangle,
  Clock,
  CreditCard,
  FileText,
  CheckCircle2,
  RefreshCw,
  Send,
  ExternalLink,
  ShieldAlert,
} from 'lucide-react';

interface ActionItem {
  id: string;
  category: 'invoice' | 'payment' | 'trial' | 'quote' | 'reconciliation';
  title: string;
  description: string;
  amount?: string;
  dueInfo: string;
  urgency: 'high' | 'medium' | 'low';
  actionType: 'reminder' | 'retry' | 'review_quote' | 'review_exception';
  actionLabel: string;
}

const mockActionItems: ActionItem[] = [
  {
    id: 'ACT-001',
    category: 'invoice',
    title: 'Invoice #INV-2026-0842 Overdue (Acme Corp)',
    description: 'Payment terms Net 30 exceeded by 14 days. Balance remains uncollected.',
    amount: '$14,200.00',
    dueInfo: '14 days overdue',
    urgency: 'high',
    actionType: 'reminder',
    actionLabel: 'Send Reminder',
  },
  {
    id: 'ACT-002',
    category: 'payment',
    title: 'Payment Gateway Decline (Stripe #ch_3092)',
    description: 'Card declined (insufficient_funds). Customer in Dunning stage 2 of 4.',
    amount: '$3,450.00',
    dueInfo: 'Failed 3 hrs ago',
    urgency: 'high',
    actionType: 'retry',
    actionLabel: 'Retry Payment',
  },
  {
    id: 'ACT-003',
    category: 'quote',
    title: 'Enterprise CPQ Quote #Q-7019 Awaiting Approval',
    description: 'Requires finance review due to 22% volume discount threshold override.',
    amount: '$68,500.00',
    dueInfo: 'Created yesterday',
    urgency: 'medium',
    actionType: 'review_quote',
    actionLabel: 'Review Quote',
  },
  {
    id: 'ACT-004',
    category: 'trial',
    title: 'Trial Expiration in 24 Hours (TechNova Solutions)',
    description: '14-day enterprise trial ending soon. High product engagement score (92%).',
    amount: 'Potential $4,800/yr',
    dueInfo: 'Expires tomorrow at 5 PM',
    urgency: 'medium',
    actionType: 'reminder',
    actionLabel: 'Send Conversion Offer',
  },
  {
    id: 'ACT-005',
    category: 'reconciliation',
    title: 'Unreconciled Bank Wire Settlement ($19,850.00)',
    description: 'Wire received from HDFC account with ambiguous customer reference code.',
    amount: '$19,850.00',
    dueInfo: 'Received 2 days ago',
    urgency: 'low',
    actionType: 'review_exception',
    actionLabel: 'Review Exception',
  },
  {
    id: 'ACT-006',
    category: 'payment',
    title: 'Webhook Signature Mismatch on Razorpay Order',
    description: 'Order #order_Nx8402 callback failed integrity validation check.',
    amount: '$1,290.00',
    dueInfo: 'Triggered 5 hrs ago',
    urgency: 'high',
    actionType: 'review_exception',
    actionLabel: 'Review Exception',
  },
];

export function ActionCenterPage() {
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [resolvedIds, setResolvedIds] = useState<string[]>([]);
  const { showToast } = useToast();

  const handleAction = (item: ActionItem) => {
    setResolvedIds((prev) => [...prev, item.id]);
    showToast('success', 'Action Triggered', `${item.actionLabel} initiated for ${item.id}.`);
  };

  const filteredItems = mockActionItems
    .filter((item) => !resolvedIds.includes(item.id))
    .filter((item) => activeCategory === 'all' || item.category === activeCategory);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              Control Center
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              Cross-Module Operations
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Action Center
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            One centralized operational cockpit for high-priority billing exceptions, overdue collections, failed payments, and urgent action items.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<RefreshCw className="w-3.5 h-3.5" />}
            onClick={() => {
              setResolvedIds([]);
              showToast('info', 'Refreshed', 'Action Center tasks synchronized.');
            }}
          >
            Reset Queue
          </Button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-rose-50 text-rose-600 border border-rose-100 shrink-0">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs text-slate-500 font-medium">Critical Attention Items</p>
              <h3 className="text-xl font-bold text-slate-900 mt-0.5">
                {filteredItems.filter((i) => i.urgency === 'high').length}
              </h3>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-50 text-amber-600 border border-amber-100 shrink-0">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs text-slate-500 font-medium">Pending Approvals & Trials</p>
              <h3 className="text-xl font-bold text-slate-900 mt-0.5">
                {filteredItems.filter((i) => i.urgency === 'medium').length}
              </h3>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-emerald-50 text-emerald-600 border border-emerald-100 shrink-0">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs text-slate-500 font-medium">Resolved in Session</p>
              <h3 className="text-xl font-bold text-slate-900 mt-0.5">{resolvedIds.length}</h3>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {[
          { id: 'all', label: 'All Actions' },
          { id: 'invoice', label: 'Overdue Invoices' },
          { id: 'payment', label: 'Failed Payments' },
          { id: 'quote', label: 'Quote Approvals' },
          { id: 'trial', label: 'Expiring Trials' },
          { id: 'reconciliation', label: 'Reconciliation' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveCategory(tab.id)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-colors whitespace-nowrap cursor-pointer ${
              activeCategory === tab.id
                ? 'bg-brand-600 text-white shadow-xs'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Action Items List */}
      <div className="space-y-3">
        {filteredItems.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
              <h3 className="text-sm font-bold text-slate-900">All Action Items Resolved</h3>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                No outstanding exceptions or overdue tasks require immediate human attention in this queue.
              </p>
            </CardContent>
          </Card>
        ) : (
          filteredItems.map((item) => (
            <Card key={item.id} className="hover:border-slate-300 transition-colors">
              <CardContent className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-start gap-3.5 min-w-0">
                  <div
                    className={`p-2.5 rounded-xl border shrink-0 ${
                      item.urgency === 'high'
                        ? 'bg-rose-50 text-rose-600 border-rose-100'
                        : item.urgency === 'medium'
                        ? 'bg-amber-50 text-amber-600 border-amber-100'
                        : 'bg-blue-50 text-brand-600 border-blue-100'
                    }`}
                  >
                    {item.category === 'invoice' && <FileText className="w-5 h-5" />}
                    {item.category === 'payment' && <CreditCard className="w-5 h-5" />}
                    {item.category === 'trial' && <Clock className="w-5 h-5" />}
                    {item.category === 'quote' && <FileText className="w-5 h-5" />}
                    {item.category === 'reconciliation' && <AlertTriangle className="w-5 h-5" />}
                  </div>

                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-xs sm:text-sm font-bold text-slate-900 truncate">
                        {item.title}
                      </h3>
                      <Badge
                        variant={
                          item.urgency === 'high'
                            ? 'danger'
                            : item.urgency === 'medium'
                            ? 'warning'
                            : 'neutral'
                        }
                        size="sm"
                      >
                        {item.dueInfo}
                      </Badge>
                    </div>
                    <p className="text-xs text-slate-500 mt-1">{item.description}</p>
                    {item.amount && (
                      <p className="text-xs font-semibold text-slate-700 mt-1">
                        Impact: <span className="text-slate-900">{item.amount}</span>
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => handleAction(item)}
                    leadingIcon={
                      item.actionType === 'reminder' ? (
                        <Send className="w-3.5 h-3.5" />
                      ) : item.actionType === 'retry' ? (
                        <RefreshCw className="w-3.5 h-3.5" />
                      ) : (
                        <ExternalLink className="w-3.5 h-3.5" />
                      )
                    }
                  >
                    {item.actionLabel}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
