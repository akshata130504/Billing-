import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  X,
  PauseCircle,
  PlayCircle,
  StopCircle,
  Zap,
  RotateCcw,
  Mail,
  CreditCard,
  CheckCircle2,
  XCircle,
  Clock,
  ExternalLink,
  FileText,
  User,
  Repeat,
  ShieldCheck,
} from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { useToast } from '../../components/common/Toast';
import { dunningService } from '../../services/dunningService';
import type { DunningAttempt, DunningCaseDetail, DunningCommunication } from '../../types/dunning';
import { formatDateTime, formatMoney, formatRelative, humanize } from '../../utils/format';
import {
  ACTIVE_CASE_STATUSES,
  ATTEMPT_STATUS_CONFIG,
  COMMUNICATION_TEMPLATE_LABELS,
  FINAL_ACTION_CONFIG,
  TERMINAL_CASE_STATUSES,
  caseStatusBadge,
  caseStatusLabel,
} from './dunningUi';

export interface DunningCaseDrawerProps {
  caseId: string | null;
  onClose: () => void;
  /** Finance+ can pause/resume/stop/retry/reactivate. */
  canAct: boolean;
  /** Called after any successful mutation so the parent can refresh list + metrics. */
  onChanged: () => void;
}

type PendingAction = 'pause' | 'resume' | 'stop' | 'retry' | 'reactivate' | null;

type TimelineEntry =
  | { kind: 'attempt'; at: string; attempt: DunningAttempt }
  | { kind: 'communication'; at: string; communication: DunningCommunication };

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 border-b border-slate-100 last:border-b-0">
      <span className="text-xs font-medium text-slate-500 shrink-0">{label}</span>
      <span className="text-sm text-slate-800 text-right min-w-0">{children}</span>
    </div>
  );
}

export function DunningCaseDrawer({ caseId, onClose, canAct, onChanged }: DunningCaseDrawerProps) {
  const { showToast } = useToast();
  const isOpen = Boolean(caseId);

  const [detail, setDetail] = useState<DunningCaseDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [pending, setPending] = useState<PendingAction>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [reason, setReason] = useState('');
  const [applyFinalAction, setApplyFinalAction] = useState(true);

  const load = useCallback(async () => {
    if (!caseId) return;
    try {
      setLoading(true);
      setError(null);
      const data = await dunningService.getCase(caseId);
      setDetail(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load dunning case.');
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    if (caseId) {
      setDetail(null);
      load();
    }
  }, [caseId, load]);

  // Escape closes the drawer; lock body scroll while open.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !pending) onClose();
    };
    window.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [isOpen, onClose, pending]);

  const timeline = useMemo<TimelineEntry[]>(() => {
    if (!detail) return [];
    const entries: TimelineEntry[] = [
      ...detail.attempts.map<TimelineEntry>((attempt) => ({
        kind: 'attempt',
        at: attempt.executed_at ?? attempt.scheduled_at,
        attempt,
      })),
      ...detail.communications.map<TimelineEntry>((communication) => ({
        kind: 'communication',
        at: communication.sent_at,
        communication,
      })),
    ];
    return entries.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
  }, [detail]);

  const isActive = detail ? ACTIVE_CASE_STATUSES.includes(detail.status) : false;
  const isTerminal = detail ? TERMINAL_CASE_STATUSES.includes(detail.status) : false;
  const canPause = canAct && isActive;
  const canResume = canAct && detail?.status === 'paused';
  const canStop = canAct && detail !== null && !isTerminal;
  const canRetry = canAct && isActive;
  const canReactivate =
    canAct &&
    detail !== null &&
    Boolean(detail.subscription_id) &&
    (detail.final_action_taken === 'cancel_and_void' ||
      detail.status === 'exhausted' ||
      detail.status === 'finalized');

  const openAction = (action: Exclude<PendingAction, null>) => {
    setReason('');
    setApplyFinalAction(true);
    setPending(action);
  };

  const runAction = async () => {
    if (!detail || !pending) return;
    try {
      setActionLoading(true);
      switch (pending) {
        case 'pause':
          await dunningService.pauseCase(detail.id, { reason: reason.trim() || null });
          showToast('success', 'Case paused', `${detail.case_number} will not retry until resumed.`);
          break;
        case 'resume':
          await dunningService.resumeCase(detail.id);
          showToast('success', 'Case resumed', `${detail.case_number} is scheduled to retry tomorrow.`);
          break;
        case 'stop':
          await dunningService.stopCase(detail.id, {
            reason: reason.trim() || null,
            apply_final_action: applyFinalAction,
          });
          showToast('success', 'Dunning stopped', `${detail.case_number} has been closed.`);
          break;
        case 'retry':
          await dunningService.retryNow(detail.id);
          showToast('success', 'Retry triggered', `An immediate charge attempt was run for ${detail.case_number}.`);
          break;
        case 'reactivate':
          if (detail.subscription_id) {
            const res = await dunningService.reactivateSubscription(detail.subscription_id);
            showToast('success', 'Subscription reactivated', res.message);
          }
          break;
      }
      setPending(null);
      await load();
      onChanged();
    } catch (err: any) {
      showToast('error', 'Action failed', err?.message || 'The server rejected this action.');
    } finally {
      setActionLoading(false);
    }
  };

  if (!isOpen) return null;

  const progressPct = detail && detail.max_attempts > 0 ? Math.min(100, (detail.attempt_count / detail.max_attempts) * 100) : 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs" onClick={onClose} aria-hidden="true" />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Dunning case details"
        className="relative z-10 h-full w-full max-w-2xl bg-white shadow-modal border-l border-slate-200 flex flex-col"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-brand-600 mb-1">Dunning case</div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h3 className="text-base font-semibold text-slate-900 leading-6 font-mono">
                {detail?.case_number ?? '…'}
              </h3>
              {detail && (
                <Badge variant={caseStatusBadge(detail.status)} dot>
                  {caseStatusLabel(detail.status)}
                </Badge>
              )}
            </div>
            {detail && (
              <p className="mt-1 text-xs text-slate-500">
                Opened {formatDateTime(detail.created_at)} · {humanize(detail.trigger_reason)}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500"
            aria-label="Close drawer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {loading && !detail ? (
            <LoadingState message="Loading case details..." />
          ) : error ? (
            <ErrorState title="Could not load this case" message={error} onRetry={load} />
          ) : detail ? (
            <>
              {/* Amount + progress */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/60">
                  <div className="text-xs font-medium text-slate-500 uppercase tracking-wide">Amount due</div>
                  <div className="mt-1.5 text-2xl font-bold text-slate-900 tracking-tight tabular-nums">
                    {formatMoney(detail.amount_due, detail.currency)}
                  </div>
                  {detail.recovered_at && (
                    <div className="mt-1 text-xs text-emerald-700 font-medium">
                      Recovered {formatDateTime(detail.recovered_at)}
                    </div>
                  )}
                </div>
                <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/60">
                  <div className="flex items-center justify-between">
                    <div className="text-xs font-medium text-slate-500 uppercase tracking-wide">Retry attempts</div>
                    <span className="text-xs font-semibold text-slate-700 tabular-nums">
                      {detail.attempt_count} / {detail.max_attempts}
                    </span>
                  </div>
                  <div className="mt-2.5 w-full h-2 bg-slate-200 rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all ${detail.status === 'recovered' ? 'bg-emerald-500' : detail.status === 'exhausted' ? 'bg-rose-500' : 'bg-brand-500'}`}
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                  <div className="mt-2 text-xs text-slate-500 flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-slate-400" />
                    {detail.next_retry_at
                      ? `Next retry ${formatRelative(detail.next_retry_at)} (${formatDateTime(detail.next_retry_at)})`
                      : 'No retry scheduled'}
                  </div>
                </div>
              </div>

              {/* Actions */}
              {canAct && (canPause || canResume || canStop || canRetry || canReactivate) && (
                <div className="flex flex-wrap items-center gap-2">
                  {canRetry && (
                    <Button size="sm" variant="primary" leadingIcon={<Zap className="w-3.5 h-3.5" />} onClick={() => openAction('retry')}>
                      Retry now
                    </Button>
                  )}
                  {canPause && (
                    <Button size="sm" variant="outline" leadingIcon={<PauseCircle className="w-3.5 h-3.5" />} onClick={() => openAction('pause')}>
                      Pause
                    </Button>
                  )}
                  {canResume && (
                    <Button size="sm" variant="primary" leadingIcon={<PlayCircle className="w-3.5 h-3.5" />} onClick={() => openAction('resume')}>
                      Resume
                    </Button>
                  )}
                  {canStop && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-rose-700 border-rose-200 hover:bg-rose-50"
                      leadingIcon={<StopCircle className="w-3.5 h-3.5" />}
                      onClick={() => openAction('stop')}
                    >
                      Stop dunning
                    </Button>
                  )}
                  {canReactivate && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-emerald-700 border-emerald-200 hover:bg-emerald-50"
                      leadingIcon={<RotateCcw className="w-3.5 h-3.5" />}
                      onClick={() => openAction('reactivate')}
                    >
                      Reactivate subscription
                    </Button>
                  )}
                </div>
              )}

              {/* Status notes */}
              {detail.status === 'paused' && (
                <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-sm text-amber-800">
                  <div className="font-semibold text-xs uppercase tracking-wide mb-0.5">Paused {formatRelative(detail.paused_at)}</div>
                  {detail.pause_reason || 'No reason recorded.'}
                </div>
              )}
              {detail.stopped_at && (
                <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-700">
                  <div className="font-semibold text-xs uppercase tracking-wide mb-0.5 text-slate-500">
                    Stopped {formatDateTime(detail.stopped_at)}
                  </div>
                  {detail.stop_reason || 'No reason recorded.'}
                  {detail.final_action_taken && (
                    <div className="mt-1 text-xs text-slate-500">
                      Final action applied: <span className="font-medium text-slate-700">{humanize(detail.final_action_taken)}</span>
                    </div>
                  )}
                </div>
              )}
              {detail.status === 'exhausted' && (
                <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-sm text-rose-800">
                  <div className="font-semibold text-xs uppercase tracking-wide mb-0.5">All retries exhausted</div>
                  {detail.final_action_taken
                    ? `Final action applied: ${humanize(detail.final_action_taken)}.`
                    : 'The final action from the policy is pending.'}
                </div>
              )}

              {/* Linked records */}
              <div>
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Linked records</h4>
                <div className="rounded-xl border border-slate-200 px-4">
                  <DetailRow label="Customer">
                    <Link
                      to={`/customers/${detail.customer_id}`}
                      className="inline-flex items-center gap-1.5 font-medium text-brand-700 hover:underline"
                    >
                      <User className="w-3.5 h-3.5" />
                      {detail.customer_name || detail.customer_id}
                      <ExternalLink className="w-3 h-3 text-slate-400" />
                    </Link>
                  </DetailRow>
                  <DetailRow label="Invoice">
                    <Link
                      to={`/invoices/${detail.invoice_id}`}
                      className="inline-flex items-center gap-1.5 font-medium text-brand-700 hover:underline"
                    >
                      <FileText className="w-3.5 h-3.5" />
                      {detail.invoice_number || detail.invoice_id}
                      <ExternalLink className="w-3 h-3 text-slate-400" />
                    </Link>
                  </DetailRow>
                  <DetailRow label="Subscription">
                    {detail.subscription_id ? (
                      <Link
                        to={`/subscriptions/${detail.subscription_id}`}
                        className="inline-flex items-center gap-1.5 font-medium text-brand-700 hover:underline"
                      >
                        <Repeat className="w-3.5 h-3.5" />
                        <span className="font-mono text-xs">{detail.subscription_id.slice(0, 8)}…</span>
                        <ExternalLink className="w-3 h-3 text-slate-400" />
                      </Link>
                    ) : (
                      <span className="text-slate-400">One-off invoice</span>
                    )}
                  </DetailRow>
                  <DetailRow label="Policy">
                    {detail.policy ? (
                      <span className="inline-flex items-center gap-1.5">
                        <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
                        {detail.policy.name}
                        <span className="text-xs text-slate-500">
                          · {detail.policy.retry_intervals_days.join(' / ')}d · {FINAL_ACTION_CONFIG[detail.policy.final_action].label}
                        </span>
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </DetailRow>
                  {detail.recovered_by_payment_id && (
                    <DetailRow label="Recovered by payment">
                      <Link
                        to={`/payments/${detail.recovered_by_payment_id}`}
                        className="inline-flex items-center gap-1.5 font-medium text-brand-700 hover:underline font-mono text-xs"
                      >
                        {detail.recovered_by_payment_id.slice(0, 8)}…
                        <ExternalLink className="w-3 h-3 text-slate-400" />
                      </Link>
                    </DetailRow>
                  )}
                </div>
              </div>

              {/* Timeline */}
              <div>
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                  Activity timeline
                  <span className="ml-1.5 text-slate-400 font-medium normal-case tracking-normal">
                    ({detail.attempts.length} attempts · {detail.communications.length} emails)
                  </span>
                </h4>
                {timeline.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-slate-300 py-8 text-center">
                    <Clock className="w-6 h-6 text-slate-300 mx-auto mb-2 stroke-1" />
                    <p className="text-sm font-medium text-slate-700">Nothing has happened yet</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Retry attempts and customer emails will appear here as the case progresses.
                    </p>
                  </div>
                ) : (
                  <ol className="relative border-l border-slate-200 ml-3 space-y-5">
                    {timeline.map((entry) => {
                      if (entry.kind === 'attempt') {
                        const a = entry.attempt;
                        const conf = ATTEMPT_STATUS_CONFIG[a.status];
                        const Icon =
                          a.status === 'succeeded' ? CheckCircle2 : a.status === 'failed' ? XCircle : a.status === 'scheduled' ? Clock : CreditCard;
                        const iconColor =
                          a.status === 'succeeded'
                            ? 'bg-emerald-50 text-emerald-600 border-emerald-200'
                            : a.status === 'failed'
                              ? 'bg-rose-50 text-rose-600 border-rose-200'
                              : 'bg-blue-50 text-brand-600 border-blue-200';
                        return (
                          <li key={`a-${a.id}`} className="ml-5 relative">
                            <span
                              className={`absolute -left-[31px] top-0.5 w-6 h-6 rounded-full border flex items-center justify-center ${iconColor}`}
                            >
                              <Icon className="w-3.5 h-3.5" />
                            </span>
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <div className="text-sm font-medium text-slate-900">
                                  Retry attempt #{a.attempt_number}
                                </div>
                                <div className="text-xs text-slate-500 mt-0.5">
                                  {a.executed_at
                                    ? `Executed ${formatDateTime(a.executed_at)}`
                                    : `Scheduled for ${formatDateTime(a.scheduled_at)}`}
                                  {a.notification_sent && ' · customer notified'}
                                </div>
                                {(a.error_code || a.error_message) && (
                                  <div className="mt-1.5 text-xs text-rose-700 bg-rose-50 border border-rose-100 rounded-md px-2 py-1">
                                    {a.error_code && <span className="font-mono font-semibold mr-1.5">{a.error_code}</span>}
                                    {a.error_message}
                                  </div>
                                )}
                              </div>
                              <Badge variant={conf.badge} size="sm">
                                {conf.label}
                              </Badge>
                            </div>
                          </li>
                        );
                      }
                      const c = entry.communication;
                      return (
                        <li key={`c-${c.id}`} className="ml-5 relative">
                          <span className="absolute -left-[31px] top-0.5 w-6 h-6 rounded-full border bg-slate-50 text-slate-500 border-slate-200 flex items-center justify-center">
                            <Mail className="w-3.5 h-3.5" />
                          </span>
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="text-sm font-medium text-slate-900 truncate">{c.subject}</div>
                              <div className="text-xs text-slate-500 mt-0.5">
                                To {c.recipient_email} · {formatDateTime(c.sent_at)}
                              </div>
                              {c.body_preview && (
                                <p className="mt-1.5 text-xs text-slate-600 line-clamp-2">{c.body_preview}</p>
                              )}
                            </div>
                            <Badge variant="neutral" size="sm">
                              {COMMUNICATION_TEMPLATE_LABELS[c.template_type] ?? humanize(c.template_type)}
                            </Badge>
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </div>
            </>
          ) : null}
        </div>
      </aside>

      {/* Confirmations */}
      <ConfirmDialog
        isOpen={pending === 'pause'}
        onClose={() => setPending(null)}
        onConfirm={runAction}
        title="Pause dunning?"
        description="Retries and customer emails stop until you resume. Use this when a customer has promised payment or raised a dispute."
        confirmLabel="Pause case"
        isLoading={actionLoading}
      >
        <textarea
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={255}
          placeholder="Reason (optional, visible to your team)"
          className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:outline-none"
        />
      </ConfirmDialog>

      <ConfirmDialog
        isOpen={pending === 'resume'}
        onClose={() => setPending(null)}
        onConfirm={runAction}
        title="Resume dunning?"
        description="The next retry will be scheduled for tomorrow and the remaining retry ladder continues from there."
        confirmLabel="Resume case"
        isLoading={actionLoading}
      />

      <ConfirmDialog
        isOpen={pending === 'retry'}
        onClose={() => setPending(null)}
        onConfirm={runAction}
        title="Retry the charge now?"
        description="An immediate charge attempt will be made against the customer's saved payment method. This counts toward the retry limit."
        confirmLabel="Retry now"
        isLoading={actionLoading}
      />

      <ConfirmDialog
        isOpen={pending === 'stop'}
        onClose={() => setPending(null)}
        onConfirm={runAction}
        title="Stop dunning for this invoice?"
        description="This closes the case permanently. No further retries or emails will be sent."
        confirmLabel="Stop dunning"
        variant="danger"
        isLoading={actionLoading}
      >
        <textarea
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={255}
          placeholder="Reason (optional)"
          className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-rose-500 focus:outline-none"
        />
        <label className="flex items-start gap-2.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={applyFinalAction}
            onChange={(e) => setApplyFinalAction(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-slate-300 text-rose-600 focus:ring-rose-500"
          />
          <span className="min-w-0">
            <span className="block text-sm text-slate-800">Apply the policy's final action</span>
            <span className="block text-xs text-slate-500 mt-0.5">
              {detail?.policy
                ? `${FINAL_ACTION_CONFIG[detail.policy.final_action].label}: ${FINAL_ACTION_CONFIG[detail.policy.final_action].description}`
                : 'Uses the final action configured on the case policy.'}
            </span>
          </span>
        </label>
      </ConfirmDialog>

      <ConfirmDialog
        isOpen={pending === 'reactivate'}
        onClose={() => setPending(null)}
        onConfirm={runAction}
        title="Reactivate the subscription?"
        description="Restores a dunning-cancelled subscription in-term, without changing its billing cycle. Only cancelled subscriptions can be reactivated."
        confirmLabel="Reactivate"
        isLoading={actionLoading}
      />
    </div>
  );
}
