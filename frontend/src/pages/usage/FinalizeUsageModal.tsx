import React, { useEffect, useMemo, useState } from 'react';
import { Info } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Select } from '../../components/common/Select';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { meterService } from '../../services/meterService';
import { subscriptionService } from '../../services/subscriptionService';
import type { SubscriptionOut } from '../../types/api';
import type { BillingCycleOut, UsageAggregateOut, UsageMeterOut } from '../../types/meters';
import { formatDate, formatMoney, humanize } from '../../utils/format';
import { formatQuantity } from './usageUtils';

interface FinalizeUsageModalProps {
  isOpen: boolean;
  onClose: () => void;
  meters: UsageMeterOut[];
  onFinalized: (aggregates: UsageAggregateOut[], subscription: SubscriptionOut | null) => void;
}

export function FinalizeUsageModal({ isOpen, onClose, meters, onFinalized }: FinalizeUsageModalProps) {
  const { showToast } = useToast();
  const [subscriptions, setSubscriptions] = useState<SubscriptionOut[]>([]);
  const [subsLoading, setSubsLoading] = useState(false);
  const [subscriptionId, setSubscriptionId] = useState('');
  const [cycleId, setCycleId] = useState('');
  const [cycles, setCycles] = useState<BillingCycleOut[]>([]);
  const [cyclesLoading, setCyclesLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<UsageAggregateOut[] | null>(null);

  // Every meter with usage in the period is rated, one aggregate each.
  const meterById = useMemo(() => new Map(meters.map((m) => [m.id, m])), [meters]);
  const unitFor = (aggregate: UsageAggregateOut) => meterById.get(aggregate.meter_id)?.unit_name ?? '';
  const selectedSub = useMemo(() => subscriptions.find((s) => s.id === subscriptionId) ?? null, [subscriptions, subscriptionId]);

  useEffect(() => {
    if (!isOpen) return;
    setSubscriptionId('');
    setCycleId('');
    setErrors({});
    setResult(null);
    let cancelled = false;
    setSubsLoading(true);
    subscriptionService
      .list({ page_size: 100 })
      .then((res) => {
        if (!cancelled) setSubscriptions(res.items ?? []);
      })
      .catch((err: any) => {
        if (!cancelled) showToast('error', err?.message || 'Failed to load subscriptions');
      })
      .finally(() => {
        if (!cancelled) setSubsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, showToast]);

  // Load the chosen subscription's billing cycles for the picker (no raw UUID entry).
  useEffect(() => {
    setCycleId('');
    setCycles([]);
    if (!subscriptionId) return;
    let cancelled = false;
    setCyclesLoading(true);
    meterService
      .listBillingCycles(subscriptionId)
      .then((rows) => {
        if (cancelled) return;
        setCycles(rows);
        const firstOpen = rows.find((c) => c.status !== 'finalized');
        if (firstOpen) setCycleId(firstOpen.id);
      })
      .catch((err: any) => {
        if (!cancelled) showToast('error', err?.message || 'Failed to load billing cycles');
      })
      .finally(() => {
        if (!cancelled) setCyclesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [subscriptionId, showToast]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!subscriptionId) next.subscription_id = 'Choose a subscription.';
    if (!cycleId.trim()) next.cycle_id = 'Choose a billing cycle.';
    setErrors(next);
    if (Object.keys(next).length) return;
    try {
      setSubmitting(true);
      const aggregates = await meterService.finalizeCycleUsage(subscriptionId, cycleId.trim());
      setResult(aggregates);
      onFinalized(aggregates, selectedSub);
      if (aggregates.length === 0) {
        showToast('success', 'Nothing to rate', 'No accepted usage events fell in this cycle period.');
      } else {
        const rated = aggregates.reduce((sum, a) => sum + Number(a.rated_amount || 0), 0);
        showToast(
          'success',
          'Usage finalised',
          `${aggregates.length} meter${aggregates.length === 1 ? '' : 's'} rated at ${formatMoney(rated, selectedSub?.currency ?? 'INR')} for ${formatDate(aggregates[0].period_start)} – ${formatDate(aggregates[0].period_end)}.`
        );
      }
    } catch (err: any) {
      showToast('error', err?.message || 'Failed to finalise usage');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Finalize Usage for Billing Cycle"
      description="Aggregates accepted events in the cycle period, rates them, freezes the cycle and updates the subscription's metered item."
      size="lg"
    >
      {result ? (
        <div className="space-y-4">
          {result.length === 0 ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              No accepted usage events fell inside this cycle period, so nothing was rated. The cycle is now frozen.
            </div>
          ) : (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 divide-y divide-emerald-100">
              <div className="flex items-center justify-between px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
                <span>Meter</span>
                <span>Quantity &middot; Rated</span>
              </div>
              {result.map((aggregate) => (
                <div key={aggregate.id} className="flex items-start justify-between gap-4 px-4 py-3 text-sm">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-900 truncate">
                      {meterById.get(aggregate.meter_id)?.name ?? aggregate.meter_id}
                    </p>
                    <p className="text-xs text-slate-500">
                      {formatDate(aggregate.period_start)} – {formatDate(aggregate.period_end)} &middot; {humanize(aggregate.status)}
                    </p>
                  </div>
                  <div className="text-right shrink-0 tabular-nums">
                    <p className="text-slate-900">
                      {formatQuantity(aggregate.total_quantity)} {unitFor(aggregate)}
                    </p>
                    <p className="font-semibold text-slate-900">
                      {formatMoney(aggregate.rated_amount, selectedSub?.currency ?? 'INR')}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="text-xs text-slate-500">
            The rated quantity is now on the subscription's metered line item and will be picked up by the next invoice
            generated for {selectedSub?.subscription_number ?? 'this subscription'}.
          </p>
          <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
            <Button variant="primary" size="sm" onClick={onClose}>
              Done
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <Select
            label="Subscription"
            required
            value={subscriptionId}
            onChange={(e) => setSubscriptionId(e.target.value)}
            disabled={subsLoading}
            placeholder={subsLoading ? 'Loading subscriptions…' : subscriptions.length ? 'Select a subscription' : 'No subscriptions found'}
            options={subscriptions.map((s) => ({
              value: s.id,
              label: `${s.subscription_number} · ${s.customer.display_name} · ${s.plan.name} · ${humanize(s.status)}`,
            }))}
            error={errors.subscription_id}
            helperText={
              selectedSub
                ? `Current period ${formatDate(selectedSub.current_period_start)} – ${formatDate(selectedSub.current_period_end)}`
                : undefined
            }
          />
          <Select
            label="Billing cycle"
            required
            value={cycleId}
            onChange={(e) => setCycleId(e.target.value)}
            disabled={!subscriptionId || cyclesLoading}
            placeholder={
              !subscriptionId
                ? 'Select a subscription first'
                : cyclesLoading
                  ? 'Loading billing cycles…'
                  : cycles.length
                    ? 'Select a billing cycle'
                    : 'No billing cycles yet'
            }
            options={cycles.map((c) => ({
              value: c.id,
              label: `#${c.cycle_number} · ${formatDate(c.period_start)} – ${formatDate(c.period_end)} · ${humanize(c.status)}`,
              disabled: c.status === 'finalized',
            }))}
            error={errors.cycle_id}
            helperText="Usage is aggregated over [period start, period end). Finalized cycles are frozen. The scheduler also finalizes usage automatically at each renewal."
          />

          <div className="flex items-start gap-3 rounded-lg border border-blue-100 bg-blue-50/70 px-4 py-3 text-xs text-slate-700 leading-relaxed">
            <Info className="w-4 h-4 text-brand-600 mt-0.5 shrink-0" />
            <div className="space-y-1">
              <p>
                Rates{' '}
                {meters.length > 0 ? (
                  <>
                    every meter with usage in the period (
                    <span className="font-semibold">{meters.length}</span> defined:{' '}
                    {meters.map((m) => m.name).slice(0, 3).join(', ')}
                    {meters.length > 3 ? ', …' : ''})
                  </>
                ) : (
                  'every meter with usage in the period'
                )}{' '}
                for events linked to the chosen subscription within the cycle period, one invoice line each.
              </p>
              <p>This freezes the cycle: further usage for that period will be rejected.</p>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
            <Button variant="ghost" size="sm" type="button" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" type="submit" isLoading={submitting} disabled={!meters.length}>
              Finalize Usage
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
