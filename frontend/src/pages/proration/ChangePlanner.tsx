import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Lock, TrendingUp, TrendingDown, Sliders, Eye, RotateCcw } from 'lucide-react';
import type { SubscribablePlanOption, SubscriptionOut } from '../../types/api';
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
import { cn } from '../../utils/cn';
import { formatMoney, formatDate, todayIso } from '../../utils/format';
import { ProrationPreviewCard } from './ProrationPreviewCard';
import { changeTypeLabel, formatQuantity, intervalLabel } from './prorationLabels';

export type ChangeWorkflowType = 'upgrade' | 'downgrade' | 'resize';

interface ChangePlannerProps {
  subscription: SubscriptionOut;
  /** GET /subscriptions/plan-options: legacy plans and Plans & Pricing / Catalog plan offerings. */
  planOptions: SubscribablePlanOption[];
  plansLoading: boolean;
  canApply: boolean;
  onApplied: (change: SubscriptionChangeOut) => void;
  onCancel?: () => void;
}

const EFFECTIVE_OPTIONS: { value: ProrationEffectiveType; label: string }[] = [
  { value: 'immediate', label: 'Immediately' },
  { value: 'end_of_term', label: 'End of term' },
];

const EFFECTIVE_HELP: Record<string, string> = {
  immediate: 'Plan and quantity update now. Credit and charge are prorated from today.',
  end_of_term: 'Recorded as a scheduled change and applied on the period end date. No proration is billed today.',
};

/** Select value for a plan option; legacy plan and offering ids live in different tables. */
const optionKey = (o: Pick<SubscribablePlanOption, 'source' | 'id'>) => `${o.source}:${o.id}`;

/** The option the subscription is on today (an offering subscription bills through a linked plan). */
function currentOptionKey(subscription: SubscriptionOut): string {
  const { plan } = subscription;
  return plan.source === 'offering' && plan.offering_id
    ? optionKey({ source: 'offering', id: plan.offering_id })
    : optionKey({ source: 'plan', id: plan.id });
}

/**
 * Plans the subscription can move to: same currency and same billing frequency (so the
 * price comparison is like for like), upgrades priced above the current plan, downgrades
 * below; nearest price first.
 */
export function changeCandidates(
  subscription: SubscriptionOut,
  options: SubscribablePlanOption[],
  workflow: 'upgrade' | 'downgrade'
): SubscribablePlanOption[] {
  const current = currentOptionKey(subscription);
  const currency = (subscription.currency ?? subscription.plan.currency ?? '').toUpperCase();
  const currentPrice = Number(subscription.plan.unit_amount);
  return options
    .filter((o) => {
      if (!o.is_active || optionKey(o) === current) return false;
      if ((o.currency || '').toUpperCase() !== currency) return false;
      if (o.billing_interval !== subscription.plan.billing_interval) return false;
      if ((o.interval_count || 1) !== (subscription.plan.interval_count || 1)) return false;
      const price = Number(o.unit_amount);
      if (!Number.isFinite(price) || !Number.isFinite(currentPrice)) return false;
      return workflow === 'upgrade' ? price > currentPrice : price < currentPrice;
    })
    .sort((a, b) =>
      workflow === 'upgrade'
        ? Number(a.unit_amount) - Number(b.unit_amount)
        : Number(b.unit_amount) - Number(a.unit_amount)
    );
}

export function ChangePlanner({
  subscription,
  planOptions,
  plansLoading,
  canApply,
  onApplied,
  onCancel,
}: ChangePlannerProps) {
  const { showToast } = useToast();
  const currency = subscription.currency ?? subscription.plan.currency ?? 'INR';

  const [changeWorkflow, setChangeWorkflow] = useState<ChangeWorkflowType>('upgrade');
  const [targetKey, setTargetKey] = useState<string>(() => currentOptionKey(subscription));
  const [quantity, setQuantity] = useState<string>(String(subscription.quantity));
  const [effectiveType, setEffectiveType] = useState<ProrationEffectiveType>('immediate');
  const [effectiveDate, setEffectiveDate] = useState<string>(todayIso());

  const [preview, setPreview] = useState<SubscriptionChangePreviewOut | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [applying, setApplying] = useState(false);

  const currentKey = currentOptionKey(subscription);

  // Switch workflow and default to the nearest plan in that direction.
  const handleWorkflowChange = (wf: ChangeWorkflowType) => {
    setChangeWorkflow(wf);
    const nearest = wf === 'resize' ? undefined : changeCandidates(subscription, planOptions, wf)[0];
    setTargetKey(nearest ? optionKey(nearest) : currentKey);
  };

  // Reset the form whenever a different subscription is selected
  useEffect(() => {
    setChangeWorkflow('upgrade');
    setTargetKey(currentOptionKey(subscription));
    setQuantity(String(subscription.quantity));
    setEffectiveType('immediate');
    setEffectiveDate(todayIso());
    setPreview(null);
    setPreviewError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subscription.id, subscription.plan.id, subscription.quantity]);

  const quantityNumber = Number(quantity);
  const quantityValid = quantity.trim() !== '' && Number.isFinite(quantityNumber) && quantityNumber > 0;
  const quantityError = quantity.trim() !== '' && !quantityValid ? 'Quantity must be greater than zero' : undefined;

  const isNoop = targetKey === currentKey && quantityValid && quantityNumber === subscription.quantity;
  const formValid = quantityValid && targetKey !== '';

  // The current plan first, then the compatible plans in the chosen direction.
  const candidates = useMemo(
    () => (changeWorkflow === 'resize' ? [] : changeCandidates(subscription, planOptions, changeWorkflow)),
    [subscription, planOptions, changeWorkflow]
  );
  const selectOptions = useMemo(() => {
    const tag = changeWorkflow === 'downgrade' ? ' (Downgrade)' : ' (Upgrade)';
    const current = subscription.plan;
    return [
      {
        value: currentKey,
        label: `${current.name} — ${formatMoney(current.unit_amount, current.currency)} / ${intervalLabel(
          current.billing_interval,
          current.interval_count
        )} (Current)`,
      },
      ...candidates.map((o) => ({
        value: optionKey(o),
        label: `${o.name} — ${formatMoney(o.unit_amount, o.currency)} / ${intervalLabel(
          o.billing_interval ?? current.billing_interval,
          o.interval_count
        )}${tag}`,
      })),
    ];
  }, [candidates, changeWorkflow, currentKey, subscription]);
  const selectedOption = candidates.find((o) => optionKey(o) === targetKey);

  const buildBody = useCallback((): SubscriptionChangePreviewIn => {
    const body: SubscriptionChangePreviewIn = {};
    if (selectedOption) {
      // Catalog / Plans & Pricing plans are offerings; the server resolves their linked plan.
      if (selectedOption.source === 'offering') body.target_offering_id = selectedOption.id;
      else body.target_plan_id = selectedOption.id;
    }
    if (quantityValid && quantityNumber !== subscription.quantity) body.target_quantity = quantity.trim();
    if (effectiveType === 'scheduled' && effectiveDate) body.effective_date = effectiveDate;
    return body;
  }, [selectedOption, quantity, quantityValid, quantityNumber, effectiveType, effectiveDate, subscription]);

  // Live preview calculation, debounced. `previewKey` identifies the request whose result
  // is shown (or in flight), so the Preview Change button never re-sends an identical
  // request the live preview already made.
  const requestSeq = useRef(0);
  const previewKey = useRef<string | null>(null);
  const runPreview = useCallback(
    async (manual: boolean) => {
      const body = buildBody();
      const key = JSON.stringify([subscription.id, subscription.updated_at, body]);
      if (key === previewKey.current) {
        if (manual) showToast('info', 'Proration preview is up to date', 'Showing the latest adjustments and renewal rates.');
        return;
      }
      previewKey.current = key;
      const seq = ++requestSeq.current;
      setPreviewLoading(true);
      try {
        const data = await prorationService.preview(subscription.id, body);
        if (seq !== requestSeq.current) return;
        setPreview(data);
        setPreviewError(null);
        if (manual) showToast('info', 'Proration preview updated', 'Calculated latest adjustments and renewal rates.');
      } catch (err: any) {
        if (seq !== requestSeq.current) return;
        previewKey.current = null; // a failed preview may be retried
        setPreviewError(err?.details?.fields?.target_quantity || err?.message || 'Could not calculate proration');
      } finally {
        if (seq === requestSeq.current) setPreviewLoading(false);
      }
    },
    [buildBody, subscription.id, subscription.updated_at, showToast]
  );

  useEffect(() => {
    if (!formValid || isNoop) {
      ++requestSeq.current; // drop any response still in flight
      previewKey.current = null;
      setPreview(null);
      setPreviewError(null);
      setPreviewLoading(false);
      return;
    }
    const timer = window.setTimeout(() => runPreview(false), 350);
    return () => window.clearTimeout(timer);
  }, [runPreview, formValid, isNoop]);

  // Explicit manual trigger for Preview Change button
  const handleManualPreview = () => {
    if (!formValid || isNoop) return;
    runPreview(true);
  };

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
        showToast(
          'success',
          `${label} scheduled`,
          `Takes effect on ${formatDate(change.effective_date)} for ${subscription.subscription_number}.`
        );
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

  const handleReset = () => {
    setChangeWorkflow('upgrade');
    setTargetKey(currentKey);
    setQuantity(String(subscription.quantity));
    setEffectiveType('immediate');
    setEffectiveDate(todayIso());
    setPreview(null);
    setPreviewError(null);
  };

  const handleCancel = () => {
    if (onCancel) {
      onCancel();
    } else {
      handleReset();
    }
  };

  const applyButtonLabel = useMemo(() => {
    const isEnd = effectiveType === 'end_of_term';
    if (changeWorkflow === 'upgrade') return isEnd ? 'Schedule Upgrade' : 'Apply Upgrade';
    if (changeWorkflow === 'downgrade') return isEnd ? 'Schedule Downgrade' : 'Apply Downgrade';
    return isEnd ? 'Schedule Resize' : 'Apply Resize';
  }, [changeWorkflow, effectiveType]);

  const workflowIcon = useMemo(() => {
    if (changeWorkflow === 'upgrade') return <TrendingUp className="w-4 h-4" />;
    if (changeWorkflow === 'downgrade') return <TrendingDown className="w-4 h-4" />;
    return <Sliders className="w-4 h-4" />;
  }, [changeWorkflow]);

  const workflowTitle = useMemo(() => {
    if (changeWorkflow === 'upgrade') return 'Upgrade';
    if (changeWorkflow === 'downgrade') return 'Downgrade';
    return 'Resize';
  }, [changeWorkflow]);

  const confirmSummary = preview
    ? effectiveType === 'end_of_term'
      ? `${subscription.subscription_number} will move to ${preview.new_plan.name} × ${formatQuantity(
          preview.new_quantity
        )} on ${formatDate(subscription.current_period_end)}. Nothing is billed until then.`
      : `${subscription.subscription_number} moves to ${preview.new_plan.name} × ${formatQuantity(
          preview.new_quantity
        )} effective ${formatDate(preview.effective_date)}. Net adjustment ${
          Number(preview.net_amount) >= 0 ? 'charged' : 'credited'
        }: ${formatMoney(Math.abs(Number(preview.net_amount)), currency)}.`
    : '';

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 tracking-tight">Change Subscription Workflow</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Select a change type, customize the terms, and preview proration before applying.
          </p>
        </div>
        {!canApply && (
          <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 shrink-0">
            <Lock className="w-3.5 h-3.5" />
            Preview only — finance role required to apply
          </span>
        )}
      </div>

      <div className="p-5 grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Form Controls */}
        <div className="lg:col-span-2 space-y-4">
          {/* Change Type Tabs: Upgrade / Downgrade / Resize */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              Change Type
            </label>
            <div className="grid grid-cols-3 gap-1.5 p-1 bg-slate-100/90 border border-slate-200 rounded-xl">
              <button
                type="button"
                onClick={() => handleWorkflowChange('upgrade')}
                className={cn(
                  'flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold transition-all',
                  changeWorkflow === 'upgrade'
                    ? 'bg-white text-emerald-700 shadow-sm border border-emerald-200/60'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
                )}
              >
                <TrendingUp className="w-3.5 h-3.5" />
                Upgrade
              </button>
              <button
                type="button"
                onClick={() => handleWorkflowChange('downgrade')}
                className={cn(
                  'flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold transition-all',
                  changeWorkflow === 'downgrade'
                    ? 'bg-white text-amber-700 shadow-sm border border-amber-200/60'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
                )}
              >
                <TrendingDown className="w-3.5 h-3.5" />
                Downgrade
              </button>
              <button
                type="button"
                onClick={() => handleWorkflowChange('resize')}
                className={cn(
                  'flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-semibold transition-all',
                  changeWorkflow === 'resize'
                    ? 'bg-white text-brand-700 shadow-sm border border-brand-200/60'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
                )}
              >
                <Sliders className="w-3.5 h-3.5" />
                Resize
              </button>
            </div>
          </div>

          {/* Current Plan Summary Card */}
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-slate-500 font-medium">Current Plan:</span>
              <span className="font-semibold text-slate-900">{subscription.plan.name}</span>
            </div>
            <div className="flex items-center justify-between text-slate-600">
              <span>Rate & Quantity:</span>
              <span className="tabular-nums font-medium text-slate-900">
                {formatMoney(subscription.plan.unit_amount, subscription.plan.currency)} × {formatQuantity(subscription.quantity)}
              </span>
            </div>
            <div className="flex items-center justify-between text-slate-500 text-[11px] pt-1 border-t border-slate-200/60">
              <span>Billing Cycle:</span>
              <span>
                {formatDate(subscription.current_period_start)} → {formatDate(subscription.current_period_end)}
              </span>
            </div>
          </div>

          {/* New Plan Selector */}
          {changeWorkflow !== 'resize' ? (
            <Select
              label={`New plan (${workflowTitle})`}
              value={targetKey}
              onChange={(e) => setTargetKey(e.target.value)}
              options={selectOptions}
              disabled={plansLoading}
              helperText={
                plansLoading
                  ? 'Loading plans...'
                  : candidates.length === 0
                  ? `No active ${changeWorkflow === 'upgrade' ? 'higher' : 'lower'}-priced plan in ${currency} billed ${intervalLabel(
                      subscription.plan.billing_interval,
                      subscription.plan.interval_count
                    )}.`
                  : changeWorkflow === 'upgrade'
                  ? 'Select a higher-priced plan to upgrade this subscription.'
                  : 'Select a lower-priced plan to downgrade this subscription.'
              }
            />
          ) : (
            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
                Plan
              </label>
              <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium text-slate-800 flex justify-between items-center">
                <span>{subscription.plan.name} (Retained)</span>
                <span className="text-slate-500 tabular-nums">
                  {formatMoney(subscription.plan.unit_amount, subscription.plan.currency)}
                </span>
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Resizing changes the quantity/seats on the current plan.
              </p>
            </div>
          )}

          {/* Quantity */}
          <Input
            label="Quantity"
            type="number"
            min={1}
            step={1}
            inputMode="numeric"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            error={quantityError}
            helperText={
              quantityError
                ? undefined
                : changeWorkflow === 'resize'
                ? `Currently ${formatQuantity(subscription.quantity)}. Increase or decrease seats/units.`
                : `Currently ${formatQuantity(subscription.quantity)}`
            }
          />

          {/* Effective Date Option: Immediately / End of term */}
          <Select
            label="Effective date"
            value={effectiveType}
            onChange={(e) => setEffectiveType(e.target.value as ProrationEffectiveType)}
            options={EFFECTIVE_OPTIONS}
            helperText={EFFECTIVE_HELP[effectiveType]}
          />

          {effectiveType === 'end_of_term' && (
            <div className="text-xs text-slate-600 bg-amber-50/70 border border-amber-200 rounded-lg px-3 py-2.5">
              Scheduled for renewal on <span className="font-semibold text-slate-900">{formatDate(subscription.current_period_end)}</span>.
              Current cycle is unchanged.
            </div>
          )}

          {/* Actions: Cancel, Preview Change, Apply Upgrade/Downgrade/Resize */}
          <div className="pt-2 flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              leadingIcon={workflowIcon}
              disabled={!canApply || !preview || previewLoading || isNoop || !formValid || Boolean(previewError)}
              onClick={() => setConfirmOpen(true)}
            >
              {applyButtonLabel}
            </Button>

            <Button
              variant="outline"
              leadingIcon={<Eye className="w-4 h-4" />}
              disabled={previewLoading || !formValid || isNoop}
              onClick={handleManualPreview}
            >
              {previewLoading ? 'Calculating...' : 'Preview Change'}
            </Button>

            <Button
              variant="ghost"
              leadingIcon={<RotateCcw className="w-3.5 h-3.5" />}
              onClick={handleCancel}
            >
              Cancel
            </Button>
          </div>
        </div>

        {/* Prominent Proration Preview Card */}
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
        title={effectiveType === 'end_of_term' ? `Schedule ${workflowTitle}?` : `Apply ${workflowTitle} now?`}
        description={confirmSummary}
        confirmLabel={applyButtonLabel}
        isLoading={applying}
      >
        {preview && effectiveType !== 'end_of_term' && (
          <dl className="text-xs bg-slate-50 border border-slate-200 rounded-lg divide-y divide-slate-200">
            <div className="flex justify-between px-3 py-2">
              <dt className="text-slate-500">Unused-plan credit</dt>
              <dd className="font-semibold text-emerald-700 tabular-nums">− {formatMoney(preview.unused_credit, currency)}</dd>
            </div>
            <div className="flex justify-between px-3 py-2">
              <dt className="text-slate-500">New-plan remaining-period charge</dt>
              <dd className="font-semibold text-slate-900 tabular-nums">+ {formatMoney(preview.remaining_charge, currency)}</dd>
            </div>
            <div className="flex justify-between px-3 py-2">
              <dt className="text-slate-700 font-semibold">Net Prorated Charge</dt>
              <dd className="font-bold text-slate-900 tabular-nums">{formatMoney(preview.net_amount, currency)}</dd>
            </div>
          </dl>
        )}
      </ConfirmDialog>
    </div>
  );
}
