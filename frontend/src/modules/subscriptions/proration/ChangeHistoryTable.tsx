import { useState } from 'react';
import { History, XCircle, RefreshCw } from 'lucide-react';
import type { PlanOut } from '../../../types/api';
import type { SubscriptionChangeOut } from '../../../types/proration';
import { prorationService } from '../../../services/prorationService';
import { Badge } from '../../../components/common/Badge';
import { Button } from '../../../components/common/Button';
import { ConfirmDialog } from '../../../components/common/ConfirmDialog';
import { LoadingState } from '../../../components/common/LoadingState';
import { ErrorState } from '../../../components/common/ErrorState';
import { EmptyState } from '../../../components/common/EmptyState';
import { useToast } from '../../../components/common/Toast';
import { formatMoney, formatDate, formatDateTime, humanize, parseMoney } from '../../../utils/format';
import { EFFECTIVE_TYPE_LABELS, changeStatusVariant, changeTypeLabel, changeTypeVariant, formatQuantity } from './prorationLabels';

interface ChangeHistoryTableProps {
  subscriptionId: string;
  subscriptionNumber: string;
  currency: string;
  changes: SubscriptionChangeOut[];
  loading: boolean;
  error: string | null;
  plans: PlanOut[];
  canCancel: boolean;
  onRefresh: () => void;
  onCancelled: (change: SubscriptionChangeOut) => void;
}

export function ChangeHistoryTable({
  subscriptionId,
  subscriptionNumber,
  currency,
  changes,
  loading,
  error,
  plans,
  canCancel,
  onRefresh,
  onCancelled,
}: ChangeHistoryTableProps) {
  const { showToast } = useToast();
  const [cancelTarget, setCancelTarget] = useState<SubscriptionChangeOut | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const planName = (id: string | null): string => {
    if (!id) return '—';
    return plans.find((p) => p.id === id)?.name ?? 'Plan';
  };

  const handleCancel = async () => {
    if (!cancelTarget) return;
    try {
      setCancelling(true);
      const updated = await prorationService.cancel(subscriptionId, cancelTarget.id);
      showToast('success', 'Scheduled change cancelled', `${subscriptionNumber} keeps its current terms.`);
      setCancelTarget(null);
      onCancelled(updated);
    } catch (err: any) {
      showToast('error', 'Could not cancel change', err?.message || 'The server rejected the request.');
    } finally {
      setCancelling(false);
    }
  };

  const scheduledCount = changes.filter((c) => c.status === 'scheduled').length;

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 tracking-tight">Change history</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {changes.length === 0
              ? `Every applied and scheduled change for ${subscriptionNumber} is recorded here.`
              : `${changes.length} ${changes.length === 1 ? 'change' : 'changes'}${scheduledCount ? ` · ${scheduledCount} scheduled` : ''}`}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onRefresh} leadingIcon={<RefreshCw className="w-3.5 h-3.5" />} disabled={loading}>
          Refresh
        </Button>
      </div>

      {loading ? (
        <LoadingState message="Loading change history..." className="py-10" />
      ) : error ? (
        <div className="p-4">
          <ErrorState title="Could not load history" message={error} onRetry={onRefresh} />
        </div>
      ) : changes.length === 0 ? (
        <div className="p-4">
          <EmptyState
            icon={<History className="w-6 h-6 stroke-1" />}
            title="No changes yet"
            description="This subscription is still on its original terms. Plan a change above to see the proration preview and apply it."
          />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50/80 text-slate-600 font-semibold border-b border-slate-200 uppercase tracking-wider text-[11px]">
                <th className="py-3 px-4">Type</th>
                <th className="py-3 px-4">Change</th>
                <th className="py-3 px-4">Effective</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Credit</th>
                <th className="py-3 px-4 text-right">Charge</th>
                <th className="py-3 px-4 text-right">Net</th>
                <th className="py-3 px-4">Created</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {changes.map((c) => {
                const net = parseMoney(c.net_amount);
                const isScheduled = c.status === 'scheduled';
                return (
                  <tr key={c.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3 px-4">
                      <Badge variant={changeTypeVariant(c.change_type)} size="sm">
                        {changeTypeLabel(c.change_type)}
                      </Badge>
                    </td>
                    <td className="py-3 px-4">
                      <div className="font-medium text-slate-900">
                        {planName(c.target_plan_id)}
                        {c.target_quantity !== null && (
                          <span className="text-slate-500 font-normal"> × {formatQuantity(c.target_quantity)}</span>
                        )}
                      </div>
                      <div className="text-[11px] text-slate-400 mt-0.5 tabular-nums">
                        {formatMoney(c.old_plan_amount, currency)} → {formatMoney(c.new_plan_amount, currency)} per cycle
                      </div>
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <div className="font-medium text-slate-800">{formatDate(c.effective_date)}</div>
                      <div className="text-[11px] text-slate-400 mt-0.5">{EFFECTIVE_TYPE_LABELS[c.effective_type] ?? humanize(c.effective_type)}</div>
                    </td>
                    <td className="py-3 px-4">
                      <Badge variant={changeStatusVariant(c.status)} size="sm" dot>
                        {humanize(c.status)}
                      </Badge>
                      {c.applied_at && (
                        <div className="text-[11px] text-slate-400 mt-1 whitespace-nowrap">{formatDateTime(c.applied_at)}</div>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums text-emerald-700">
                      {isScheduled || c.status === 'cancelled' ? <span className="text-slate-400">—</span> : formatMoney(c.prorated_credit, currency)}
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums">
                      {isScheduled || c.status === 'cancelled' ? <span className="text-slate-400">—</span> : formatMoney(c.prorated_charge, currency)}
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums font-semibold">
                      {isScheduled || c.status === 'cancelled' ? (
                        <span className="text-slate-400 font-normal">—</span>
                      ) : (
                        <span className={net < 0 ? 'text-emerald-700' : 'text-slate-900'}>
                          {net < 0 ? `− ${formatMoney(Math.abs(net), currency)}` : formatMoney(net, currency)}
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap text-slate-500">{formatDateTime(c.created_at)}</td>
                    <td className="py-3 px-4 text-right">
                      {isScheduled && canCancel ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                          leadingIcon={<XCircle className="w-3.5 h-3.5" />}
                          onClick={() => setCancelTarget(c)}
                        >
                          Cancel
                        </Button>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        isOpen={cancelTarget !== null}
        onClose={() => !cancelling && setCancelTarget(null)}
        onConfirm={handleCancel}
        title="Cancel scheduled change?"
        description={
          cancelTarget
            ? `The ${changeTypeLabel(cancelTarget.change_type).toLowerCase()} to ${planName(cancelTarget.target_plan_id)} × ${formatQuantity(
                cancelTarget.target_quantity
              )} scheduled for ${formatDate(cancelTarget.effective_date)} will not run. ${subscriptionNumber} keeps its current terms.`
            : undefined
        }
        confirmLabel="Cancel change"
        cancelLabel="Keep it"
        variant="danger"
        isLoading={cancelling}
      />
    </div>
  );
}
