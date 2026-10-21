import { useCallback, useEffect, useState } from 'react';
import { Copy, Repeat, XCircle } from 'lucide-react';
import { subscriptionService } from '../../services/subscriptionService';
import type { ApiError, AutopayMandate, AutopayStatus, AutopayStatusOut } from '../../types/api';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { useToast } from '../../components/common/Toast';
import { formatDate, formatMoney } from '../../utils/format';
import { cycleLabel } from '../public/AutopayAuthorizePage';

const STATUS: Record<AutopayStatus, { label: string; variant: 'success' | 'warning' | 'danger' | 'neutral' | 'info' }> = {
  created: { label: 'Waiting for customer', variant: 'warning' },
  authenticated: { label: 'Authorised', variant: 'success' },
  active: { label: 'Active', variant: 'success' },
  pending: { label: 'Charge failed - retrying', variant: 'warning' },
  halted: { label: 'Halted', variant: 'danger' },
  paused: { label: 'Paused', variant: 'neutral' },
  cancelled: { label: 'Cancelled', variant: 'neutral' },
  completed: { label: 'Completed', variant: 'neutral' },
  expired: { label: 'Link expired', variant: 'neutral' },
};
const LIVE = new Set<AutopayStatus>(['created', 'authenticated', 'active', 'pending', 'halted', 'paused']);

/** UPI AutoPay / e-mandate (Razorpay Subscriptions) for one subscription. */
export function AutopayCard({ subscriptionId, canWrite }: { subscriptionId: string; canWrite: boolean }) {
  const { showToast } = useToast();
  const [state, setState] = useState<AutopayStatusOut | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);

  const load = useCallback(async () => {
    try {
      setState(await subscriptionService.getAutopay(subscriptionId));
    } catch {
      setState(null);
    }
  }, [subscriptionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const setup = async () => {
    setBusy(true);
    try {
      const mandate: AutopayMandate = await subscriptionService.setupAutopay(subscriptionId);
      setLink(mandate.authorization_link);
      showToast('success', 'AutoPay link ready', 'Send it to the customer to authorise the mandate.');
      await load();
    } catch (err) {
      showToast('error', 'AutoPay could not be set up', (err as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    try {
      await subscriptionService.cancelAutopay(subscriptionId);
      setLink(null);
      showToast('success', 'AutoPay stopped', 'No further automatic charges will be made.');
      await load();
    } catch (err) {
      showToast('error', 'AutoPay could not be stopped', (err as ApiError).message);
    } finally {
      setBusy(false);
      setConfirmStop(false);
    }
  };

  const copy = async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      showToast('success', 'Link copied');
    } catch {
      showToast('error', 'Copy failed', link);
    }
  };

  if (!state) return null;
  const mandate = state.mandate;
  const live = mandate ? LIVE.has(mandate.status) : false;

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 space-y-3" data-testid="autopay-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Repeat className="w-4 h-4 text-brand-600" />
            UPI AutoPay / e-mandate
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Razorpay collects each billing cycle automatically and retries failed charges.
          </p>
        </div>
        {mandate && <Badge variant={STATUS[mandate.status].variant} size="sm">{STATUS[mandate.status].label}</Badge>}
      </div>

      {mandate && live && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
          <dt className="text-slate-500">Amount</dt>
          <dd className="text-slate-900 font-medium">
            {formatMoney(mandate.amount, mandate.currency)} {cycleLabel(mandate.period, mandate.interval)}
          </dd>
          <dt className="text-slate-500">Charges made</dt>
          <dd className="text-slate-900">{mandate.paid_count} of {mandate.total_count}</dd>
          {(mandate.charge_at || mandate.start_at) && (
            <>
              <dt className="text-slate-500">Next charge</dt>
              <dd className="text-slate-900">{formatDate(mandate.charge_at || mandate.start_at)}</dd>
            </>
          )}
          {mandate.last_error && (
            <>
              <dt className="text-slate-500">Last failure</dt>
              <dd className="text-rose-700">{mandate.last_error}</dd>
            </>
          )}
        </dl>
      )}

      {!live && !state.eligible && state.reason && <p className="text-xs text-slate-500">{state.reason}</p>}

      {link && (
        <div className="flex items-center gap-2 rounded-lg border border-brand-100 bg-brand-50/50 px-3 py-2">
          <code className="flex-1 truncate text-[11px] text-slate-700">{link}</code>
          <Button variant="outline" size="sm" onClick={() => void copy()} leadingIcon={<Copy className="w-3.5 h-3.5" />}>
            Copy
          </Button>
        </div>
      )}

      {canWrite && (
        <div className="flex flex-wrap gap-2">
          {(state.eligible && (!mandate || !live || mandate.status === 'created')) && (
            <Button size="sm" isLoading={busy} onClick={() => void setup()} leadingIcon={<Repeat className="w-3.5 h-3.5" />}>
              {mandate?.status === 'created' ? 'New authorisation link' : 'Set up AutoPay'}
            </Button>
          )}
          {live && (
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => setConfirmStop(true)}
              leadingIcon={<XCircle className="w-3.5 h-3.5" />}
            >
              Stop AutoPay
            </Button>
          )}
        </div>
      )}

      <ConfirmDialog
        isOpen={confirmStop}
        onClose={() => setConfirmStop(false)}
        onConfirm={() => void stop()}
        title="Stop AutoPay?"
        description="The Razorpay mandate is cancelled immediately and no further automatic charges are made. The subscription itself is not changed."
        confirmLabel="Stop AutoPay"
        variant="danger"
        isLoading={busy}
      />
    </div>
  );
}
