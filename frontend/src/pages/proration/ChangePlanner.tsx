import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Zap, Lock } from 'lucide-react';
import type { PlanOut, SubscriptionOut } from '../../types/api';
import type {
  ProrationEffectiveType,
  SubscriptionChangeOut,
  SubscriptionChangePreviewIn,
  SubscriptionChangePreviewOut,
} from '../../types/proration';
import { prorationService } from '../../services/prorationService';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { useToast } from '../../components/common/Toast';
import { formatMoney, formatDate, todayIso } from '../../utils/format';
import { ProrationPreviewCard } from './ProrationPreviewCard';
import { EFFECTIVE_TYPE_LABELS, changeTypeLabel, formatQuantity, intervalLabel } from './prorationLabels';

interface ChangePlannerProps {
  subscription: SubscriptionOut;
  plans: PlanOut[];
  plansLoading: boolean;
  canApply: boolean;
  onApplied: (change: SubscriptionChangeOut) => void;
}

const EFFECTIVE_OPTIONS: { value: ProrationEffectiveType; label: string }[] = [
  { value: 'immediate', label: EFFECTIVE_TYPE_LABELS.immediate },
  { value: 'end_of_term', label: EFFECTIVE_TYPE_LABELS.end_of_term },
  { value: 'scheduled', label: EFFECTIVE_TYPE_LABELS.scheduled },
];

const EFFECTIVE_HELP: Record<ProrationEffectiveType, string> = {
  immediate: 'Plan and quantity update now. Credit and charge are prorated from today.',
  end_of_term: 'Recorded as a scheduled change and applied on the period end date. No proration is billed.',
  scheduled: 'Applied now, with the credit and charge calculated from the chosen date inside the current period.',
};

export function ChangePlanner({ subscription, plans, plansLoading, canApply, onApplied }: ChangePlannerProps) {
  const { showToast } = useToast();
  const currency = subscription.currency ?? subscription.plan.currency ?? 'INR';

  const [targetPlanId, setTargetPlanId] = useState<string>(subscription.plan.id);
  const [quantity, setQuantity] = useState<string>(String(subscription.quantity));
  const [effectiveType, setEffectiveType] = useState<ProrationEffectiveType>('immediate');
  const [effectiveDate, setEffectiveDate] = useState<string>(todayIso());

  const [preview, setPreview] = useState<SubscriptionChangePreviewOut | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [applying, setApplying] = useState(false);

  // Reset the form whenever a different subscription is selected (or its terms change after apply).
  useEffect(() => {
    setTargetPlanId(subscription.plan.id);
    setQuantity(String(subscription.quantity));
    setEffectiveType('immediate');
    setEffectiveDate(todayIso());
    setPreview(null);
    setPreviewError(null);
  }, [subscription.id, subscription.plan.id, subscription.quantity]);

  const quantityNumber = Number(quantity);
  const quantityValid = quantity.trim() !== '' && Number.isFinite(quantityNumber) && quantityNumber > 0;
  const quantityError = quantity.trim() !== '' && !quantityValid ? 'Quantity must be greater than zero' : undefined;

  const dateWithinPeriod =
    effectiveType !== 'scheduled' ||
    (effectiveDate >= subscription.current_period_start && effectiveDate <= subscription.current_period_end);
  const dateError =
    effectiveType === 'scheduled' && effectiveDate && !dateWithinPeriod
      ? `Must fall within the current period (${formatDate(subscription.current_period_start)} – ${formatDate(subscription.current_period_end)})`
      : undefined;

  const isNoop = targetPlanId === subscription.plan.id && quantityValid && quantityNumber === subscription.quantity;
  const formValid = quantityValid && targetPlanId !== '' && (effectiveType !== 'scheduled' || (Boolean(effectiveDate) && dateWithinPeriod));

  // Plans grouped so the current plan is obvious; other currencies are shown but flagged.
  const planOptions = useMemo(() => {
    const sorted = [...plans].sort((a, b) => {
      if (a.id === subscription.plan.id) return -1;
      if (b.id === subscription.plan.id) return 1;
      return Number(a.unit_amount) - Number(b.unit_amount);
    });
    const opts = sorted.map((p) => ({
      value: p.id,
      label: `${p.name} — ${formatMoney(p.unit_amount, p.currency)} / ${intervalLabel(p.billing_interval, p.interval_count)}${
        p.id === subscription.plan.id ? ' (current)' : ''
      }${p.currency !== currency ? ` · ${p.currency}` : ''}`,
    }));
    // Ensure the current plan is selectable even if it has been archived.
    if (!plans.some((p) => p.id === subscription.plan.id)) {
      opts.unshift({
        value: subscription.plan.id,
        label: `${subscription.plan.name} — ${formatMoney(subscription.plan.unit_amount, subscription.plan.currency)} / ${intervalLabel(
          subscription.plan.billing_interval,
          subscription.plan.interval_count
        )} (current)`,
      });
    }
    return opts;
  }, [plans, subscription, currency]);

  const buildBody = useCallback((): SubscriptionChangePreviewIn => {
    const body: SubscriptionChangePreviewIn = {};
    if (targetPlanId && targetPlanId !== subscription.plan.id) body.target_plan_id = targetPlanId;
    if (quantityValid && quantityNumber !== subscription.quantity) body.target_quantity = quantity.trim();
    if (effectiveType === 'scheduled' && effectiveDate) body.effective_date = effectiveDate;
    return body;
  }, [targetPlanId, quantity, quantityValid, quantityNumber, effectiveType, effectiveDate, subscription]);

  // Live preview, debounced.
  const requestSeq = useRef(0);
  useEffect(() => {
    if (!formValid || isNoop) {
      setPreview(null);
      setPreviewError(null);
      setPreviewLoading(false);
      return;
    }
    const seq = ++requestSeq.current;
    setPreviewLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const data = await prorationService.preview(subscription.id, buildBody());
        if (seq !== requestSeq.current) return;
        setPreview(data);
        setPreviewError(null);
      } catch (err: any) {
        if (seq !== requestSeq.current) return;
        setPreviewError(err?.details?.fields?.target_quantity || err?.message || 'Could not calculate proration');
      } finally {
        if (seq === requestSeq.current) setPreviewLoading(false);
      }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [subscription.id, buildBody, formValid, isNoop]);

  const handleApply = async () => {
    if (!preview) return;
    try {
      setApplying(true);
      const change = await prorationService.apply(subscription.id, {
        ...buildBody(),
        effective_type: effectiveType,
      });
      const label = changeTypeLabel(change.change_type);
      if (change.status === 'scheduled') {
        showToast('success', `${label} scheduled`, `Takes effect on ${formatDate(change.effective_date)} for ${subscription.subscription_number}.`);
      } else {
        const net = Number(change.net_amount);
        const detail =
          net > 0
            ? `Prorated invoice of ${formatMoney(change.net_amount, currency)} raised.`
            : net < 0
            ? `Credit note of ${formatMoney(Math.abs(net), currency)} issued.`
            : 'No net adjustment was billed.';
        showToast('success', `${label} applied`, `${subscription.subscription_number} updated. ${detail}`);
      }
      setConfirmOpen(false);
      onApplied(change);
    } catch (err: any) {
      showToast('error', 'Change not applied', err?.message || 'The server rejected the change.');
    } finally {
      setApplying(false);
    }
  };

  const selectedPlan = plans.find((p) => p.id === targetPlanId);
  const confirmSummary = preview
    ? effectiveType === 'end_of_term'
      ? `${subscription.subscription_number} will move to ${preview.new_plan.name} × ${formatQuantity(preview.new_quantity)} on ${formatDate(
          subscription.current_period_end
        )}. Nothing is billed until then.`
      : `${subscription.subscription_number} moves to ${preview.new_plan.name} × ${formatQuantity(preview.new_quantity)} effective ${formatDate(
          preview.effective_date
        )}. Net adjustment ${Number(preview.net_amount) >= 0 ? 'charged' : 'credited'}: ${formatMoney(
          Math.abs(Number(preview.net_amount)),
          currency
        )}.`
    : '';

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 tracking-tight">Plan a change</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            The preview updates as you edit. Nothing is saved until you apply the change.
          </p>
        </div>
        {!canApply && (
          <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1">
            <Lock className="w-3.5 h-3.5" />
            Preview only — finance role required to apply
          </span>
        )}
      </div>

      <div className="p-5 grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Form */}
        <div className="lg:col-span-2 space-y-4">
          <Select
            label="Target plan"
            value={targetPlanId}
            onChange={(e) => setTargetPlanId(e.target.value)}
            options={planOptions}
            disabled={plansLoading}
            helperText={
              plansLoading
                ? 'Loading plans...'
                : selectedPlan && selectedPlan.currency !== currency
                ? `This plan bills in ${selectedPlan.currency}; the subscription is in ${currency}.`
                : selectedPlan && selectedPlan.billing_interval !== subscription.plan.billing_interval
                ? `Billing interval changes from ${intervalLabel(subscription.plan.billing_interval)} to ${intervalLabel(selectedPlan.billing_interval)}.`
                : undefined
            }
          />
          <Input
            label="Quantity"
            type="number"
            min={1}
            step={1}
            inputMode="numeric"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            error={quantityError}
            helperText={quantityError ? undefined : `Currently ${formatQuantity(subscription.quantity)}`}
          />
          <Select
            label="Takes effect"
            value={effectiveType}
            onChange={(e) => setEffectiveType(e.target.value as ProrationEffectiveType)}
            options={EFFECTIVE_OPTIONS}
            helperText={EFFECTIVE_HELP[effectiveType]}
          />
          {effectiveType === 'scheduled' && (
            <Input
              label="Proration date"
              type="date"
              value={effectiveDate}
              min={subscription.current_period_start}
              max={subscription.current_period_end}
              onChange={(e) => setEffectiveDate(e.target.value)}
              error={dateError}
              helperText={dateError ? undefined : `Current period ${formatDate(subscription.current_period_start)} – ${formatDate(subscription.current_period_end)}`}
              required
            />
          )}
          {effectiveType === 'end_of_term' && (
            <div className="text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
              Scheduled for <span className="font-semibold text-slate-900">{formatDate(subscription.current_period_end)}</span>. You can
              cancel it from the history below until it runs.
            </div>
          )}

          <div className="pt-2 flex items-center gap-2">
            <Button
              variant="primary"
              leadingIcon={<Zap className="w-4 h-4" />}
              disabled={!canApply || !preview || previewLoading || isNoop || !formValid || Boolean(previewError)}
              onClick={() => setConfirmOpen(true)}
            >
              {effectiveType === 'end_of_term' ? 'Schedule change' : 'Apply change'}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setTargetPlanId(subscription.plan.id);
                setQuantity(String(subscription.quantity));
                setEffectiveType('immediate');
                setEffectiveDate(todayIso());
              }}
              disabled={isNoop && effectiveType === 'immediate'}
            >
              Reset
            </Button>
          </div>
        </div>

        {/* Preview */}
        <div className="lg:col-span-3">
          <ProrationPreviewCard
            preview={preview}
            loading={previewLoading}
            error={previewError}
            effectiveType={effectiveType}
            currency={currency}
            isNoop={isNoop || !formValid}
          />
        </div>
      </div>

      <ConfirmDialog
        isOpen={confirmOpen}
        onClose={() => !applying && setConfirmOpen(false)}
        onConfirm={handleApply}
        title={effectiveType === 'end_of_term' ? 'Schedule this change?' : 'Apply this change now?'}
        description={confirmSummary}
        confirmLabel={effectiveType === 'end_of_term' ? 'Schedule' : 'Apply change'}
        isLoading={applying}
      >
        {preview && effectiveType !== 'end_of_term' && (
          <dl className="text-xs bg-slate-50 border border-slate-200 rounded-lg divide-y divide-slate-200">
            <div className="flex justify-between px-3 py-2">
              <dt className="text-slate-500">Credit note</dt>
              <dd className="font-semibold text-emerald-700 tabular-nums">{formatMoney(preview.unused_credit, currency)}</dd>
            </div>
            <div className="flex justify-between px-3 py-2">
              <dt className="text-slate-500">Prorated invoice</dt>
              <dd className="font-semibold text-slate-900 tabular-nums">{formatMoney(preview.remaining_charge, currency)}</dd>
            </div>
            <div className="flex justify-between px-3 py-2">
              <dt className="text-slate-700 font-medium">Net</dt>
              <dd className="font-bold text-slate-900 tabular-nums">{formatMoney(preview.net_amount, currency)}</dd>
            </div>
          </dl>
        )}
      </ConfirmDialog>
    </div>
  );
}
