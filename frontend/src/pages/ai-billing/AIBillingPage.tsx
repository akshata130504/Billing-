import { useCallback, useEffect, useState } from 'react';
import {
  Sparkles,
  MessageSquareText,
  FilePlus2,
  PenLine,
  History,
  ShieldCheck,
  Database,
  Lock,
  RefreshCw,
} from 'lucide-react';
import { aiService } from '../../services/aiService';
import type { AIHistoryItem, AIRequestMode } from '../../types/ai';
import { Button } from '../../components/common/Button';
import { StatCard } from '../../components/common/StatCard';
import { Badge } from '../../components/common/Badge';
import { useAuth } from '../../hooks/useAuth';
import { formatRelative, humanize } from '../../utils/format';
import { cn } from '../../utils/cn';
import { AskPanel } from './AskPanel';
import { DraftPanel } from './DraftPanel';
import { WritingPanel } from './WritingPanel';
import { HistoryPanel } from './HistoryPanel';
import { MODE_LABELS, REQUEST_STATUS_BADGE, asUtc } from './aiUi';

type Tab = 'ask' | 'draft' | 'writing' | 'history';

const TABS: { id: Tab; label: string; hint: string; icon: typeof Sparkles; financeOnly?: boolean }[] = [
  { id: 'ask', label: 'Ask', hint: 'Grounded answers with sources', icon: MessageSquareText },
  { id: 'draft', label: 'Draft an action', hint: 'Propose → validate → confirm', icon: FilePlus2, financeOnly: true },
  { id: 'writing', label: 'Writing assistant', hint: 'Reminders and notes', icon: PenLine },
  { id: 'history', label: 'History', hint: 'Every request, logged', icon: History },
];

const TAB_MODE: Record<Exclude<Tab, 'history'>, AIRequestMode> = { ask: 'query', draft: 'draft', writing: 'writing' };

export function AIBillingPage() {
  const { hasRole } = useAuth();
  const canDraft = hasRole('finance');

  const [tab, setTab] = useState<Tab>('ask');
  const [refreshKey, setRefreshKey] = useState(0);
  const [recent, setRecent] = useState<AIHistoryItem[]>([]);
  const [recentLoading, setRecentLoading] = useState(true);

  const loadRecent = useCallback(async () => {
    setRecentLoading(true);
    try {
      setRecent(await aiService.history({ limit: 200 }));
    } catch {
      // The side rail is auxiliary; the History tab surfaces load errors with a retry.
    } finally {
      setRecentLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent, refreshKey]);

  const bump = () => setRefreshKey((k) => k + 1);

  const counts = recent.reduce(
    (acc, r) => {
      acc.total += 1;
      acc[r.mode] += 1;
      if (r.status === 'failed') acc.failed += 1;
      return acc;
    },
    { total: 0, query: 0, draft: 0, writing: 0, failed: 0 }
  );

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-1">
            <Sparkles className="w-4 h-4" />
            Insights
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">AI in Billing</h1>
          <p className="text-sm text-slate-500 mt-1 max-w-2xl">
            Ask questions answered from your live invoices and subscriptions, draft credit notes that only post after you confirm,
            and generate reminder text you can edit. Every request is logged and cites its sources.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={bump} leadingIcon={<RefreshCw className="w-4 h-4" />}>
            Refresh
          </Button>
        </div>
      </div>

      {/* KPI cards — derived from the tenant's AI activity log */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Requests logged" value={recentLoading ? '…' : counts.total} icon={<History className="w-4 h-4" />} />
        <StatCard title="Questions answered" value={recentLoading ? '…' : counts.query} icon={<MessageSquareText className="w-4 h-4" />} />
        <StatCard title="Action drafts" value={recentLoading ? '…' : counts.draft} icon={<FilePlus2 className="w-4 h-4" />} />
        <StatCard title="Texts generated" value={recentLoading ? '…' : counts.writing} icon={<PenLine className="w-4 h-4" />} />
      </div>

      {/* Three-panel shell: rail · workspace */}
      <div className="grid lg:grid-cols-12 gap-6 items-start">
        <aside className="lg:col-span-3 space-y-4 lg:sticky lg:top-6">
          <nav className="bg-white rounded-xl border border-slate-200 shadow-sm p-2 space-y-1">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              const locked = t.financeOnly && !canDraft;
              const count = t.id === 'history' ? counts.total : counts[TAB_MODE[t.id as Exclude<Tab, 'history'>]];
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={cn(
                    'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors',
                    active ? 'bg-brand-50 text-brand-700' : 'text-slate-700 hover:bg-slate-50'
                  )}
                >
                  <span
                    className={cn(
                      'w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border',
                      active ? 'bg-white border-brand-200 text-brand-600' : 'bg-slate-50 border-slate-200 text-slate-500'
                    )}
                  >
                    <Icon className="w-4 h-4" />
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className="flex items-center gap-1.5 text-sm font-semibold">
                      {t.label}
                      {locked && <Lock className="w-3 h-3 text-slate-400" />}
                    </span>
                    <span className={cn('block text-[11px] truncate', active ? 'text-brand-600/80' : 'text-slate-400')}>{t.hint}</span>
                  </span>
                  {!recentLoading && count > 0 && (
                    <span className={cn('text-[11px] font-semibold tabular-nums px-1.5 py-0.5 rounded-md', active ? 'bg-white text-brand-700' : 'bg-slate-100 text-slate-500')}>
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">How it works</div>
            <ul className="space-y-2.5 text-xs text-slate-600 leading-relaxed">
              <li className="flex gap-2">
                <Database className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                <span>
                  Answers are computed directly from this organisation's billing tables — outstanding receivables, overdue
                  invoices, late-payment cycle and MRR — and cite the records used.
                </span>
              </li>
              <li className="flex gap-2">
                <ShieldCheck className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                <span>
                  The assistant never writes to the ledger. Drafts are validated, expire after 30 minutes, and are executed
                  through the standard credit-note service only when a Finance user confirms.
                </span>
              </li>
              <li className="flex gap-2">
                <Lock className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                <span>
                  Runs on Rooman's in-house deterministic engine — no data is sent to an external model provider.
                </span>
              </li>
            </ul>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
            <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Recent activity</span>
              <button type="button" onClick={() => setTab('history')} className="text-[11px] font-medium text-brand-600 hover:text-brand-700">
                View all
              </button>
            </div>
            {recentLoading ? (
              <div className="px-4 py-6 text-xs text-slate-400 text-center">Loading…</div>
            ) : recent.length === 0 ? (
              <div className="px-4 py-6 text-xs text-slate-400 text-center">Nothing logged yet.</div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {recent.slice(0, 5).map((r) => (
                  <li key={r.id} className="px-4 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-medium text-slate-500">{MODE_LABELS[r.mode]}</span>
                      <Badge variant={REQUEST_STATUS_BADGE[r.status]} size="sm">
                        {humanize(r.status)}
                      </Badge>
                    </div>
                    <div className="text-xs text-slate-800 truncate mt-0.5">{r.prompt}</div>
                    <div className="text-[10px] text-slate-400 mt-0.5">{formatRelative(asUtc(r.created_at))}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        <section className="lg:col-span-9 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col min-h-[560px] lg:h-[calc(100vh-22rem)] lg:min-h-[560px]">
          {tab === 'ask' && <AskPanel onActivity={bump} />}
          {tab === 'draft' && (
            <div className="overflow-y-auto h-full">
              <DraftPanel onActivity={bump} />
            </div>
          )}
          {tab === 'writing' && (
            <div className="overflow-y-auto h-full">
              <WritingPanel onActivity={bump} />
            </div>
          )}
          {tab === 'history' && <HistoryPanel refreshKey={refreshKey} />}
        </section>
      </div>
    </div>
  );
}
