import { useMemo, useState, type ComponentType } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { useToast } from '../../components/common/Toast';
import { controlCenterService, invoiceService, toApiError } from '../../services';
import { queryKeys } from '../../hooks/queries';
import type { ActionCategory, ActionItem } from '../../types/api';
import {
  AlertTriangle,
  Clock,
  CreditCard,
  FileText,
  RefreshCw,
  Send,
  ExternalLink,
  ShieldAlert,
  ShieldCheck,
  Search,
  CheckCircle2,
  Calendar,
} from 'lucide-react';
import { usePageSpec, type ItemRenderer } from '../../appUi/usePageSpec';

type CategoryFilter = 'all' | ActionCategory;

/** Metric card styling per category; labels, captions, order and visibility come from the page spec. */
const KPI_STYLES: Record<ActionCategory, { icon: ComponentType<{ className?: string }>; active: string; chip: string; caption: string }> = {
  overdue: { icon: AlertTriangle, active: 'bg-rose-50/70 border-rose-300 shadow-xs', chip: 'bg-rose-50 text-rose-600', caption: 'text-rose-600' },
  failed_payment: { icon: CreditCard, active: 'bg-amber-50/70 border-amber-300 shadow-xs', chip: 'bg-amber-50 text-amber-600', caption: 'text-amber-600' },
  expiring_trial: { icon: Clock, active: 'bg-blue-50/70 border-blue-300 shadow-xs', chip: 'bg-blue-50 text-blue-600', caption: 'text-blue-600' },
  pending_quote: { icon: FileText, active: 'bg-purple-50/70 border-purple-300 shadow-xs', chip: 'bg-purple-50 text-purple-600', caption: 'text-purple-600' },
  pending_approval: { icon: ShieldCheck, active: 'bg-teal-50/70 border-teal-300 shadow-xs', chip: 'bg-teal-50 text-teal-600', caption: 'text-teal-600' },
};
const KPI_KEYS = Object.keys(KPI_STYLES) as ActionCategory[];

export function ActionCenterPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const ui = usePageSpec('action_center');
  const [selectedCategory, setSelectedCategory] = useState<CategoryFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const query = useQuery({
    queryKey: queryKeys.controlCenter.actionCenter(),
    queryFn: controlCenterService.actionCenter,
  });

  const reminderMutation = useMutation({
    mutationFn: (invoiceId: string) => invoiceService.sendReminder(invoiceId),
    onSuccess: () => {
      showToast('success', 'Reminder Dispatched', 'Automated payment reminder and invoice PDF sent to the customer.');
      void queryClient.invalidateQueries({ queryKey: queryKeys.controlCenter.actionCenter() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.invoices.all });
    },
    onError: (err) => showToast('error', 'Reminder Failed', toApiError(err).message),
  });

  const items = query.data?.items ?? [];
  const counts = query.data?.counts;

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const matchesCategory = selectedCategory === 'all' || item.category === selectedCategory;
      const q = searchQuery.trim().toLowerCase();
      const matchesSearch =
        !q ||
        item.title.toLowerCase().includes(q) ||
        (item.customer?.display_name ?? '').toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q);
      return matchesCategory && matchesSearch;
    });
  }, [items, selectedCategory, searchQuery]);

  const stats = useMemo(
    () => ({
      overdue: counts?.overdue ?? 0,
      failed_payment: counts?.failed_payment ?? 0,
      expiring_trial: counts?.expiring_trial ?? 0,
      pending_quote: counts?.pending_quote ?? 0,
      pending_approval: counts?.pending_approval ?? 0,
      total: items.length,
    }),
    [counts, items.length]
  );

  const kpiRenderers: Record<string, ItemRenderer> = Object.fromEntries(
    KPI_KEYS.map((key): [string, ItemRenderer] => {
      const style = KPI_STYLES[key];
      const Icon = style.icon;
      return [
        key,
        (item, edit) => (
          <div
            {...edit}
            onClick={() => setSelectedCategory(key)}
            className={`p-4 rounded-xl border transition-all cursor-pointer ${
              selectedCategory === key ? style.active : 'bg-white border-slate-200/90 hover:border-slate-300'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">{item.label}</span>
              <span className={`p-1.5 rounded-lg ${style.chip}`}>
                <Icon className="w-4 h-4" />
              </span>
            </div>
            <p className="text-xl font-bold text-slate-900 mt-2">{stats[key]}</p>
            <p className={`text-[11px] font-medium mt-0.5 ${style.caption}`}>{item.caption}</p>
          </div>
        ),
      ];
    })
  );

  const handleExecuteAction = (item: ActionItem) => {
    switch (item.suggested_action) {
      case 'send_reminder':
        reminderMutation.mutate(item.entity_id);
        break;
      case 'retry_payment':
        navigate(`/payments/${item.entity_id}`);
        break;
      case 'convert_trial':
        navigate(`/subscriptions/${item.entity_id}`);
        break;
      case 'review_quote':
        navigate(`/quotes/${item.entity_id}`);
        break;
      case 'review_approval':
        navigate('/control-center/approvals');
        break;
    }
  };

  const getActionLabel = (item: ActionItem): string => {
    switch (item.suggested_action) {
      case 'send_reminder':
        return 'Send Reminder';
      case 'retry_payment':
        return 'View Payment';
      case 'convert_trial':
        return 'Convert Trial';
      case 'review_quote':
        return 'Review Quote';
      case 'review_approval':
        return 'Review Approval';
    }
  };

  const getActionIcon = (item: ActionItem) => {
    switch (item.suggested_action) {
      case 'send_reminder':
        return <Send className="w-3.5 h-3.5" />;
      case 'retry_payment':
        return <RefreshCw className="w-3.5 h-3.5" />;
      default:
        return <ExternalLink className="w-3.5 h-3.5" />;
    }
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
      case 'pending_approval':
        return <ShieldCheck className="w-4 h-4 text-teal-600" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div {...ui.edit('header')}>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              {ui.text('header', 'eyebrow')}
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              {ui.text('header', 'badge')}
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-rose-600" />
            {ui.text('header', 'title')}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            {ui.text('header', 'subtitle')}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<RefreshCw className="w-3.5 h-3.5" />}
            onClick={() => void query.refetch()}
          >
            Refresh Feed
          </Button>
        </div>
      </div>

      {query.isPending ? (
        <LoadingState message="Loading action items..." />
      ) : query.isError ? (
        <ErrorState message={toApiError(query.error).message} onRetry={() => void query.refetch()} />
      ) : (
        <>
          {/* Metric Counters */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4" {...ui.edit('kpis')}>
            {ui.render('kpis', kpiRenderers)}
          </div>

          {/* Filter and Search Bar */}
          <Card>
            <CardContent className="p-4">
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                {/* Category Tabs */}
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0" {...ui.edit('tabs')}>
                  {ui.shown('tabs').map((item) => ({
                    key: item.key,
                    label: `${item.label} (${item.key === 'all' ? stats.total : stats[item.key as ActionCategory]})`,
                  })).map((tab) => (
                    <button
                      key={tab.key}
                      {...ui.edit(`tabs.${tab.key}`)}
                      type="button"
                      onClick={() => setSelectedCategory(tab.key as CategoryFilter)}
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
              <Card {...ui.edit('empty')}>
                <CardContent className="py-12 text-center">
                  <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto mb-3">
                    <CheckCircle2 className="w-6 h-6" />
                  </div>
                  <h3 className="text-sm font-bold text-slate-900">{ui.text('empty', 'title')}</h3>
                  <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                    {ui.text('empty', 'description')}
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
                              {item.customer?.display_name ?? '—'}
                            </span>
                            <span className="text-slate-300">•</span>
                            {getUrgencyBadge(item.urgency)}
                            <span className="text-slate-300">•</span>
                            <span className="text-[11px] font-medium text-slate-500 flex items-center gap-1">
                              <Calendar className="w-3 h-3 text-slate-400" />
                              {item.due_info}
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
                            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block" {...ui.edit('items')}>
                              {ui.text('items', 'impact')}
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
                            isLoading={
                              item.suggested_action === 'send_reminder' &&
                              reminderMutation.isPending &&
                              reminderMutation.variables === item.entity_id
                            }
                            leadingIcon={getActionIcon(item)}
                            onClick={() => handleExecuteAction(item)}
                          >
                            {getActionLabel(item)}
                          </Button>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
