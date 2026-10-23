import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, History, RefreshCw } from 'lucide-react';
import { aiService } from '../../services/aiService';
import type { AIHistoryItem, AIRequestMode } from '../../types/ai';
import { AI_REQUEST_MODES } from '../../types/ai';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { formatDateTime, formatRelative, humanize } from '../../utils/format';
import { MODE_LABELS, ModeBadge, REQUEST_STATUS_BADGE, asUtc, errorMessage } from './aiUi';

interface HistoryPanelProps {
  /** Bumps when another panel completes a request, so the log refreshes. */
  refreshKey: number;
}

export function HistoryPanel({ refreshKey }: HistoryPanelProps) {
  const [items, setItems] = useState<AIHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<AIRequestMode | ''>('');
  const [limit, setLimit] = useState(50);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await aiService.history({ mode: mode || undefined, limit });
      setItems(res);
    } catch (err: any) {
      setError(errorMessage(err, 'Could not load AI history.'));
    } finally {
      setLoading(false);
    }
  }, [mode, limit]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
        <div className="flex items-center bg-slate-100 p-1 rounded-lg border border-slate-200 w-fit">
          {(['', ...AI_REQUEST_MODES] as (AIRequestMode | '')[]).map((m) => (
            <button
              key={m || 'all'}
              type="button"
              onClick={() => setMode(m)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                mode === m ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {m ? MODE_LABELS[m] : 'All'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {[25, 50, 100, 200].map((n) => (
              <option key={n} value={n}>
                Last {n}
              </option>
            ))}
          </select>
          <Button variant="outline" size="sm" onClick={() => void load()} leadingIcon={<RefreshCw className="w-3.5 h-3.5" />}>
            Refresh
          </Button>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {loading ? (
          <div className="py-16">
            <LoadingState message="Loading AI activity…" />
          </div>
        ) : error ? (
          <div className="p-5">
            <ErrorState title="Could not load history" message={error} onRetry={() => void load()} />
          </div>
        ) : items.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={<History className="w-6 h-6 stroke-1" />}
              title={mode ? `No ${MODE_LABELS[mode].toLowerCase()} requests yet` : 'No AI activity yet'}
              description="Every question, draft and writing request made in this organisation is logged here with its outcome."
              className="border-slate-200"
            />
          </div>
        ) : (
          <table className="w-full text-left text-sm text-slate-600">
            <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200 sticky top-0">
              <tr>
                <th className="px-5 py-3 w-8" />
                <th className="px-3 py-3">Mode</th>
                <th className="px-3 py-3">Prompt</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-5 py-3 text-right">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((item) => {
                const open = expanded === item.id;
                return (
                  <HistoryRow key={item.id} item={item} open={open} onToggle={() => setExpanded(open ? null : item.id)} />
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function HistoryRow({ item, open, onToggle }: { item: AIHistoryItem; open: boolean; onToggle: () => void }) {
  return (
    <>
      <tr onClick={onToggle} className="hover:bg-slate-50/70 transition-colors cursor-pointer">
        <td className="px-5 py-3 text-slate-400">
          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </td>
        <td className="px-3 py-3">
          <ModeBadge mode={item.mode} />
        </td>
        <td className="px-3 py-3 max-w-md">
          <div className="text-slate-900 truncate">{item.prompt}</div>
        </td>
        <td className="px-3 py-3">
          <Badge variant={REQUEST_STATUS_BADGE[item.status]} dot>
            {humanize(item.status)}
          </Badge>
        </td>
        <td className="px-5 py-3 text-right whitespace-nowrap">
          <div className="text-slate-700">{formatRelative(asUtc(item.created_at))}</div>
          <div className="text-[11px] text-slate-400">{formatDateTime(asUtc(item.created_at))}</div>
        </td>
      </tr>
      {open && (
        <tr className="bg-slate-50/60">
          <td />
          <td colSpan={4} className="px-3 pb-4 pt-1">
            <div className="grid sm:grid-cols-2 gap-3">
              <div className="rounded-lg border border-slate-200 bg-white p-3">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1">Prompt</div>
                <p className="text-sm text-slate-800 whitespace-pre-wrap">{item.prompt}</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-3">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
                  {item.mode === 'writing' ? 'Generated text' : item.mode === 'draft' ? 'Outcome' : 'Answer'}
                </div>
                {item.answer ? (
                  <p className="text-sm text-slate-800 whitespace-pre-wrap">{item.answer}</p>
                ) : item.mode === 'draft' ? (
                  <p className="text-sm text-slate-500">
                    {item.status === 'failed' ? 'Draft was rejected at validation.' : 'Draft was validated and stored for confirmation.'}
                  </p>
                ) : (
                  <p className="text-sm text-slate-400 italic">No response recorded.</p>
                )}
              </div>
            </div>
            <div className="mt-2 text-[11px] text-slate-400 font-mono">
              request {item.id} · conversation {item.conversation_id}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
