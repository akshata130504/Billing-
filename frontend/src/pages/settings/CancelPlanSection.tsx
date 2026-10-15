import { useRef, useState } from 'react';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { Button } from '../../components/common/Button';
import { toApiError } from '../../services/apiClient';
import { platformSubscriptionService, type CancelPlanMode } from '../../services/platformSubscriptionService';
import type { PlatformSubscriptionInfo } from '../../types/api';
import { formatDate, formatDateTime } from '../../utils/format';
import type { CheckoutNotice } from './useSubscriptionCheckout';

interface Props {
  subscription: PlatformSubscriptionInfo;
  isOwner: boolean;
  refreshMe: () => Promise<unknown>;
  onNotice: (notice: CheckoutNotice) => void;
}

const FAILURE_TONE: Record<string, CheckoutNotice['tone']> = {
  CANCELLATION_UNCONFIRMED: 'warning',
  CANCELLATION_ALREADY_SCHEDULED: 'info',
  NOT_IN_PAID_PERIOD: 'info',
};

/**
 * Owner-only cancellation of the organization's paid plan. The server cancels at Razorpay first and changes
 * the plan only once Razorpay confirms; the page then re-reads /auth/me. Razorpay accepts one cancellation per
 * subscription and has no way to undo it, so the dialog says so before the Owner confirms.
 */
export function CancelPlanSection({ subscription, isOwner, refreshMe, onNotice }: Props) {
  const pastDue = subscription.state === 'past_due';
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<CancelPlanMode>(pastDue ? 'immediately' : 'at_period_end');
  const [submitting, setSubmitting] = useState(false);
  const inFlight = useRef(false);

  const paid = subscription.state === 'active' || pastDue;
  if (!isOwner || !paid) return null;

  if (subscription.cancel_at_period_end) {
    return (
      <p className="text-sm text-slate-600" data-testid="cancellation-scheduled-note">
        Your cancellation is scheduled and cannot be undone. To keep using Rooman Billing after{' '}
        {formatDate(subscription.current_period_end)}, choose a plan again once that date has passed.
      </p>
    );
  }

  const submit = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setSubmitting(true);
    try {
      const result = await platformSubscriptionService.cancelPlan(mode);
      await refreshMe().catch(() => undefined);
      setOpen(false);
      onNotice({
        tone: 'success',
        title: result.status === 'scheduled' ? 'Cancellation scheduled' : 'Plan cancelled',
        message:
          result.status === 'scheduled'
            ? `${result.message} Access ends on ${formatDateTime(result.effective_at)}.`
            : result.message,
      });
    } catch (err) {
      const error = toApiError(err);
      const code = typeof error.details?.code === 'string' ? error.details.code : error.code;
      setOpen(false);
      onNotice({ tone: FAILURE_TONE[code] ?? 'error', title: 'Plan not cancelled', message: error.message });
      if (code === 'CANCELLATION_ALREADY_SCHEDULED' || code === 'SUBSCRIPTION_INACTIVE') void refreshMe().catch(() => undefined);
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-2xs">
      <h2 className="text-base font-bold text-slate-900">Cancel plan</h2>
      <p className="mt-1 text-sm text-slate-600">
        Stop your plan at the end of the current billing period or right away. Your organization&apos;s data is
        kept either way.
      </p>
      <Button className="mt-4" variant="outline" onClick={() => setOpen(true)} disabled={submitting}>
        Cancel plan
      </Button>

      <ConfirmDialog
        isOpen={open}
        onClose={() => !submitting && setOpen(false)}
        onConfirm={submit}
        title="Cancel your plan?"
        description="Razorpay accepts one cancellation per subscription and it cannot be undone."
        confirmLabel={mode === 'immediately' ? 'Cancel now' : 'Cancel at period end'}
        cancelLabel="Keep my plan"
        variant="danger"
        isLoading={submitting}
      >
        <fieldset className="mt-3 space-y-3" aria-label="When should the plan end?">
          <label className={`flex gap-3 rounded-lg border p-3 ${pastDue ? 'opacity-50' : 'cursor-pointer'}`}>
            <input
              type="radio"
              name="cancel-mode"
              value="at_period_end"
              checked={mode === 'at_period_end'}
              disabled={pastDue}
              onChange={() => setMode('at_period_end')}
            />
            <span className="text-sm">
              <span className="font-semibold text-slate-900">At the end of the current period</span>
              <span className="block text-slate-600">
                {pastDue
                  ? 'Not available while a payment is overdue.'
                  : `Your plan keeps working until ${formatDate(subscription.current_period_end)}. After that the organization becomes read-only until you choose a plan again.`}
              </span>
            </span>
          </label>
          <label className="flex cursor-pointer gap-3 rounded-lg border p-3">
            <input
              type="radio"
              name="cancel-mode"
              value="immediately"
              checked={mode === 'immediately'}
              onChange={() => setMode('immediately')}
            />
            <span className="text-sm">
              <span className="font-semibold text-slate-900">Immediately</span>
              <span className="block text-slate-600">
                Access ends now and the organization becomes read-only. The rest of the current period is not
                refunded automatically.
              </span>
            </span>
          </label>
        </fieldset>
      </ConfirmDialog>
    </div>
  );
}
