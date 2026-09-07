import { useState, useMemo } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import {
  AlertTriangle,
  Clock,
  CreditCard,
  FileText,
  RefreshCw,
  Send,
  ExternalLink,
  ShieldAlert,
  Search,
  CheckCircle2,
  Calendar,
} from 'lucide-react';

export type ActionCategory = 'all' | 'overdue' | 'failed_payment' | 'expiring_trial' | 'pending_quote';

export interface ActionItem {
  id: string;
  category: 'overdue' | 'failed_payment' | 'expiring_trial' | 'pending_quote';
  title: string;
  description: string;
  amount?: string;
  account: string;
  dueInfo: string;
  urgency: 'critical' | 'high' | 'medium';
  actionLabel: string;
  actionType: 'reminder' | 'retry' | 'convert' | 'review';
}

const initialActionItems: ActionItem[] = [
  {
    id: 'ACT-001',
    category: 'overdue',
    title: 'Invoice #INV-2026-0087 Overdue (Hyperion FinTech)',
    description: 'Payment terms Net 30 exceeded by 14 days. Outstanding balance requires collection follow-up.',
    amount: '₹42,000.00',
    account: 'Hyperion FinTech Ltd',
    dueInfo: '14 days overdue',
    urgency: 'critical',
    actionLabel: 'Send Reminder',
    actionType: 'reminder',
  },
  {
    id: 'ACT-002',
    category: 'failed_payment',
    title: 'Card Payment Decline on Razorpay (Solaria Robotics)',
    description: 'Insufficient funds returned on recurring mandate attempt #2. Automated retry scheduled.',
    amount: '₹18,500.00',
    account: 'Solaria Robotics Corp',
    dueInfo: 'Failed 3 hours ago',
    urgency: 'critical',
    actionLabel: 'Retry Payment',
    actionType: 'retry',
  },
  {
    id: 'ACT-003',
    category: 'expiring_trial',
    title: 'Enterprise Subscription Trial Expiring in 24h',
    description: 'Vanguard Biometrics completed 13 of 14 trial days. 8 active seats utilized during evaluation.',
    amount: '₹65,000.00 / yr',
    account: 'Vanguard Biometrics',
    dueInfo: 'Expires tomorrow',
    urgency: 'high',
    actionLabel: 'Convert Trial',
    actionType: 'convert',
  },
  {
    id: 'ACT-004',
    category: 'pending_quote',
    title: 'Quote #QT-2026-0034 Awaiting Client E-Signature',
    description: 'Custom tiered plan quote sent to Nexus Global Logistics awaiting decision before expiry.',
    amount: '₹84,000.00',
    account: 'Nexus Global Logistics',
    dueInfo: 'Sent 3 days ago',
    urgency: 'medium',
    actionLabel: 'Review Quote',
    actionType: 'review',
  },
  {
    id: 'ACT-005',
    category: 'overdue',
    title: 'Invoice #INV-2026-0091 Overdue (Orbit Retail)',
    description: 'Invoice past 7 days due date. First automated dunning notice sent without response.',
    amount: '₹26,750.00',
    account: 'Orbit Retail India',
    dueInfo: '7 days overdue',
    urgency: 'high',
    actionLabel: 'Send Reminder',
    actionType: 'reminder',
  },
  {
    id: 'ACT-006',
    category: 'failed_payment',
    title: 'UPI Mandate Execution Failed (Zeta Health)',
    description: 'Auto-debit mandate expired on customer bank end. Notification required to update VPA.',
    amount: '₹12,200.00',
    account: 'Zeta Health Systems',
    dueInfo: 'Failed yesterday',
    urgency: 'high',
    actionLabel: 'Retry Payment',
    actionType: 'retry',
  },
  {
    id: 'ACT-007',
    category: 'pending_quote',
    title: 'Quote #QT-2026-0041 High-Volume Addon Proposal',
    description: 'Special discount term sheet pending CFO counter-signature for Acme Cloud Dynamics.',
    amount: '₹1,20,000.00',
    account: 'Acme Cloud Dynamics',
    dueInfo: 'Expires in 48h',
    urgency: 'medium',
    actionLabel: 'Review Quote',
    actionType: 'review',
  },
];

export function ActionCenterPage() {
  const { showToast } = useToast();
  const [items, setItems] = useState<ActionItem[]>(initialActionItems);
  const [selectedCategory, setSelectedCategory] = useState<ActionCategory>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const matchesCategory = selectedCategory === 'all' || item.category === selectedCategory;
      const matchesSearch =
        !searchQuery.trim() ||
        item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.account.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.description.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesCategory && matchesSearch;
    });
  }, [items, selectedCategory, searchQuery]);

  const stats = useMemo(() => {
    const overdue = items.filter((i) => i.category === 'overdue').length;
    const failed = items.filter((i) => i.category === 'failed_payment').length;
    const trials = items.filter((i) => i.category === 'expiring_trial').length;
    const quotes = items.filter((i) => i.category === 'pending_quote').length;
    return { overdue, failed, trials, quotes, total: items.length };
  }, [items]);

  const handleExecuteAction = (item: ActionItem) => {
    setActionInProgress(item.id);

    setTimeout(() => {
      setActionInProgress(null);

      switch (item.actionType) {
        case 'reminder':
          showToast('success', 'Reminder Dispatched', `Automated payment reminder and invoice PDF sent to ${item.account}.`);
          break;
        case 'retry':
          showToast('success', 'Gateway Retry Triggered', `Direct debit retry instruction submitted for ${item.account}.`);
          break;
        case 'convert':
          showToast('info', 'Trial Checkout Link', `Enterprise upgrade portal link generated and emailed to ${item.account}.`);
          break;
        case 'review':
          showToast('info', 'Quote Review', `Opening quote document for ${item.account}.`);
          break;
      }
    }, 450);
  };

  const handleDismiss = (id: string, title: string) => {
    setItems((prev) => prev.filter((i) => i.id !== id));
    showToast('info', 'Item Resolved', `Marked "${title}" as handled.`);
  };

  const getUrgencyBadge = (urgency: ActionItem['urgency']) => {
    switch (urgency) {
      case 'critical':
        return <Badge variant="danger" size="sm">Critical Attention</Badge>;
      case 'high':
        return <Badge variant="warning" size="sm">High Priority</Badge>;
      case 'medium':
        return <Badge variant="primary" size="sm">Medium Priority</Badge>;
    }
  };

  const getCategoryIcon = (category: ActionItem['category']) => {
    switch (category) {
      case 'overdue':
        return <AlertTriangle className="w-4 h-4 text-rose-600" />;
      case 'failed_payment':
        return <CreditCard className="w-4 h-4 text-amber-600" />;
      case 'expiring_trial':
        return <Clock className="w-4 h-4 text-blue-600" />;
      case 'pending_quote':
        return <FileText className="w-4 h-4 text-purple-600" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              Control Center
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              Operator Cockpit
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-rose-600" />
            Action Center
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Triage urgent operational exceptions requiring immediate billing admin intervention, payment retries, and customer follow-ups.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<RefreshCw className="w-3.5 h-3.5" />}
            onClick={() => {
              setItems(initialActionItems);
              showToast('info', 'Refreshed', 'Action Center items refreshed.');
            }}
          >
            Refresh Feed
          </Button>
        </div>
      </div>

      {/* Metric Counters */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div
          onClick={() => setSelectedCategory('overdue')}
          className={`p-4 rounded-xl border transition-all cursor-pointer ${
            selectedCategory === 'overdue'
              ? 'bg-rose-50/70 border-rose-300 shadow-xs'
              : 'bg-white border-slate-200/90 hover:border-slate-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Overdue Invoices</span>
            <span className="p-1.5 rounded-lg bg-rose-50 text-rose-600">
              <AlertTriangle className="w-4 h-4" />
            </span>
          </div>
          <p className="text-xl font-bold text-slate-900 mt-2">{stats.overdue}</p>
          <p className="text-[11px] text-rose-600 font-medium mt-0.5">Requires reminder notice</p>
        </div>

        <div
          onClick={() => setSelectedCategory('failed_payment')}
          className={`p-4 rounded-xl border transition-all cursor-pointer ${
            selectedCategory === 'failed_payment'
              ? 'bg-amber-50/70 border-amber-300 shadow-xs'
              : 'bg-white border-slate-200/90 hover:border-slate-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Failed Payments</span>
            <span className="p-1.5 rounded-lg bg-amber-50 text-amber-600">
              <CreditCard className="w-4 h-4" />
            </span>
          </div>
          <p className="text-xl font-bold text-slate-900 mt-2">{stats.failed}</p>
          <p className="text-[11px] text-amber-600 font-medium mt-0.5">Payment gateway retry</p>
        </div>

        <div
          onClick={() => setSelectedCategory('expiring_trial')}
          className={`p-4 rounded-xl border transition-all cursor-pointer ${
            selectedCategory === 'expiring_trial'
              ? 'bg-blue-50/70 border-blue-300 shadow-xs'
              : 'bg-white border-slate-200/90 hover:border-slate-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Expiring Trials</span>
            <span className="p-1.5 rounded-lg bg-blue-50 text-blue-600">
              <Clock className="w-4 h-4" />
            </span>
          </div>
          <p className="text-xl font-bold text-slate-900 mt-2">{stats.trials}</p>
          <p className="text-[11px] text-blue-600 font-medium mt-0.5">Ready for paid upgrade</p>
        </div>

        <div
          onClick={() => setSelectedCategory('pending_quote')}
          className={`p-4 rounded-xl border transition-all cursor-pointer ${
            selectedCategory === 'pending_quote'
              ? 'bg-purple-50/70 border-purple-300 shadow-xs'
              : 'bg-white border-slate-200/90 hover:border-slate-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Pending Quotes</span>
            <span className="p-1.5 rounded-lg bg-purple-50 text-purple-600">
              <FileText className="w-4 h-4" />
            </span>
          </div>
          <p className="text-xl font-bold text-slate-900 mt-2">{stats.quotes}</p>
          <p className="text-[11px] text-purple-600 font-medium mt-0.5">Awaiting customer e-sign</p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            {/* Category Tabs */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
              {[
                { key: 'all', label: `All Attention (${stats.total})` },
                { key: 'overdue', label: `Overdue Invoices (${stats.overdue})` },
                { key: 'failed_payment', label: `Failed Payments (${stats.failed})` },
                { key: 'expiring_trial', label: `Expiring Trials (${stats.trials})` },
                { key: 'pending_quote', label: `Pending Quotes (${stats.quotes})` },
              ].map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setSelectedCategory(tab.key as ActionCategory)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors cursor-pointer ${
                    selectedCategory === tab.key
                      ? 'bg-slate-900 text-white shadow-xs'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Filter by account or title..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 outline-none focus:bg-white transition-colors"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Action Items List */}
      <div className="space-y-3">
        {filteredItems.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto mb-3">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">All Clear! No Pending Urgent Items</h3>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                No items match the selected filter. Any high-urgency exceptions will immediately surface in this cockpit.
              </p>
            </CardContent>
          </Card>
        ) : (
          filteredItems.map((item) => (
            <Card key={item.id} className="hover:border-slate-300 transition-colors">
              <CardContent className="p-4 sm:p-5">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  {/* Left info */}
                  <div className="flex items-start gap-3.5 flex-1 min-w-0">
                    <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 shrink-0 mt-0.5">
                      {getCategoryIcon(item.category)}
                    </div>

                    <div className="space-y-1 flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-bold text-slate-900">
                          {item.account}
                        </span>
                        <span className="text-slate-300">•</span>
                        {getUrgencyBadge(item.urgency)}
                        <span className="text-slate-300">•</span>
                        <span className="text-[11px] font-medium text-slate-500 flex items-center gap-1">
                          <Calendar className="w-3 h-3 text-slate-400" />
                          {item.dueInfo}
                        </span>
                      </div>

                      <h4 className="text-sm font-semibold text-slate-900 leading-snug">
                        {item.title}
                      </h4>
                      <p className="text-xs text-slate-600 leading-relaxed">
                        {item.description}
                      </p>
                    </div>
                  </div>

                  {/* Right Actions & Amount */}
                  <div className="flex items-center justify-between lg:justify-end gap-4 border-t lg:border-t-0 pt-3 lg:pt-0 border-slate-100 shrink-0">
                    {item.amount && (
                      <div className="text-left lg:text-right">
                        <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                          Impact Value
                        </span>
                        <span className="text-sm font-bold text-slate-900 tabular-nums">
                          {item.amount}
                        </span>
                      </div>
                    )}

                    <div className="flex items-center gap-2">
                      <Button
                        variant="primary"
                        size="sm"
                        isLoading={actionInProgress === item.id}
                        leadingIcon={
                          item.actionType === 'reminder' ? (
                            <Send className="w-3.5 h-3.5" />
                          ) : item.actionType === 'retry' ? (
                            <RefreshCw className="w-3.5 h-3.5" />
                          ) : (
                            <ExternalLink className="w-3.5 h-3.5" />
                          )
                        }
                        onClick={() => handleExecuteAction(item)}
                      >
                        {item.actionLabel}
                      </Button>

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDismiss(item.id, item.title)}
                        title="Dismiss / Mark resolved"
                      >
                        Resolve
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
