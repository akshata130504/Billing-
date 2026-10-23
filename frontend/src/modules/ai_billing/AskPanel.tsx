import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Sparkles, Send, User, RotateCcw, MessageSquareText } from 'lucide-react';
import { aiService } from '../../services/aiService';
import type { AIQueryResponse } from '../../types/ai';
import { Button } from '../../components/common/Button';
import { EmptyState } from '../../components/common/EmptyState';
import { LoadingSpinner } from '../../components/common/LoadingState';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime } from '../../utils/format';
import { DataFacts, EXAMPLE_QUESTIONS, SourceChips, TEXTAREA_CLS, errorMessage } from './aiUi';

interface Turn {
  id: string;
  prompt: string;
  askedAt: string;
  response: AIQueryResponse | null;
  error: string | null;
}

interface AskPanelProps {
  onActivity?: () => void;
}

export function AskPanel({ onActivity }: AskPanelProps) {
  const { showToast } = useToast();
  const { organization } = useAuth();
  const currency = organization?.default_currency ?? 'INR';

  const [prompt, setPrompt] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [turns.length, isAsking]);

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isAsking) return;
    const turnId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setTurns((prev) => [...prev, { id: turnId, prompt: trimmed, askedAt: new Date().toISOString(), response: null, error: null }]);
    setPrompt('');
    setIsAsking(true);
    try {
      const res = await aiService.ask({ prompt: trimmed, conversation_id: conversationId });
      setConversationId(res.conversation_id);
      setTurns((prev) => prev.map((t) => (t.id === turnId ? { ...t, response: res } : t)));
      onActivity?.();
    } catch (err: any) {
      const message = errorMessage(err, 'The assistant could not answer that question.');
      setTurns((prev) => prev.map((t) => (t.id === turnId ? { ...t, error: message } : t)));
      showToast('error', 'Question failed', message);
    } finally {
      setIsAsking(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    void ask(prompt);
  };

  const resetConversation = () => {
    setTurns([]);
    setConversationId(null);
    setPrompt('');
  };

  return (
    <div className="flex flex-col h-full">
      {/* Thread */}
      <div className="flex-1 min-h-0 overflow-y-auto p-5 space-y-5">
        {turns.length === 0 ? (
          <div className="space-y-5">
            <EmptyState
              icon={<MessageSquareText className="w-6 h-6 stroke-1" />}
              title="Ask a question about your billing data"
              description="Answers are computed from this organisation's live invoices and subscriptions and always cite their sources. Nothing is changed by asking."
              className="border-slate-200"
            />
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                Questions it can answer today
              </div>
              <div className="grid sm:grid-cols-2 gap-2">
                {EXAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q.label}
                    type="button"
                    onClick={() => void ask(q.prompt)}
                    className="text-left rounded-xl border border-slate-200 bg-white px-4 py-3 hover:border-brand-300 hover:bg-brand-50/60 transition-colors group"
                  >
                    <div className="text-[11px] font-semibold text-brand-600 uppercase tracking-wider">{q.label}</div>
                    <div className="text-sm text-slate-700 mt-0.5 group-hover:text-slate-900">{q.prompt}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          turns.map((turn) => (
            <div key={turn.id} className="space-y-3">
              {/* User */}
              <div className="flex items-start gap-3 justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-brand-600 text-white px-4 py-2.5 text-sm shadow-sm">
                  <p className="whitespace-pre-wrap leading-relaxed">{turn.prompt}</p>
                  <div className="text-[10px] text-brand-100 mt-1 text-right">{formatDateTime(turn.askedAt)}</div>
                </div>
                <div className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0 text-slate-500">
                  <User className="w-4 h-4" />
                </div>
              </div>

              {/* Assistant */}
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-brand-50 border border-brand-100 flex items-center justify-center shrink-0 text-brand-600">
                  <Sparkles className="w-4 h-4" />
                </div>
                <div className="max-w-[85%] flex-1 min-w-0">
                  {turn.error ? (
                    <div className="rounded-2xl rounded-tl-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
                      {turn.error}
                    </div>
                  ) : !turn.response ? (
                    <div className="rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 inline-flex items-center gap-2">
                      <LoadingSpinner size="sm" />
                      Checking live billing data…
                    </div>
                  ) : (
                    <div className="rounded-2xl rounded-tl-md border border-slate-200 bg-white shadow-sm overflow-hidden">
                      <div className="px-4 py-3">
                        <p className="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">{turn.response.answer}</p>
                      </div>
                      {(Object.keys(turn.response.data).length > 0 || turn.response.sources.length > 0) && (
                        <div className="px-4 py-3 bg-slate-50/70 border-t border-slate-100 space-y-3">
                          <DataFacts data={turn.response.data} currency={currency} />
                          <SourceChips sources={turn.response.sources} />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Composer */}
      <form onSubmit={handleSubmit} className="border-t border-slate-200 bg-slate-50/60 p-4 space-y-2">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void ask(prompt);
            }
          }}
          rows={2}
          maxLength={2000}
          placeholder="e.g. How many invoices are overdue right now?"
          className={TEXTAREA_CLS}
          disabled={isAsking}
        />
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] text-slate-400">
            Enter to send · Shift+Enter for a new line
            {conversationId && <span className="ml-2 text-slate-300">· thread continues</span>}
          </div>
          <div className="flex items-center gap-2">
            {turns.length > 0 && (
              <Button type="button" variant="ghost" size="sm" onClick={resetConversation} leadingIcon={<RotateCcw className="w-3.5 h-3.5" />}>
                New thread
              </Button>
            )}
            <Button type="submit" size="sm" isLoading={isAsking} disabled={!prompt.trim()} leadingIcon={<Send className="w-3.5 h-3.5" />}>
              Ask
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}
