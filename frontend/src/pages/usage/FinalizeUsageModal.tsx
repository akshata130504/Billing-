import React, { useEffect, useMemo, useState } from 'react';
import { Info } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { meterService } from '../../services/meterService';
import { subscriptionService } from '../../services/subscriptionService';
import type { SubscriptionOut } from '../../types/api';
import type { UsageAggregateOut, UsageMeterOut } from '../../types/meters';
import { formatDate, formatMoney, humanize } from '../../utils/format';
import { formatQuantity } from './usageUtils';

interface FinalizeUsageModalProps {
  isOpen: boolean;
  onClose: () => void;
  meters: UsageMeterOut[];
  onFinalized: (aggregate: UsageAggregateOut, subscription: SubscriptionOut | null) => void;
}

export function FinalizeUsageModal({ isOpen, onClose, meters, onFinalized }: FinalizeUsageModalProps) {
  const { showToast } = useToast();
  const [subscriptions, setSubscriptions] = useState<SubscriptionOut[]>([]);
  const [subsLoading, setSubsLoading] = useState(false);
  const [subscriptionId, setSubscriptionId] = useState('');
  const [cycleId, setCycleId] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<UsageAggregateOut | null>(null);

  // The backend rates the first meter (alphabetical by name) — surface that so the outcome is predictable.
  const ratedMeter = useMemo(
    () => [...meters].sort((a, b) => a.name.localeCompare(b.name))[0] ?? null,
    [meters]
  );
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!subscriptionId) next.subscription_id = 'Choose a subscription.';
    if (!cycleId.trim()) next.cycle_id = 'Enter the billing cycle id.';
    setErrors(next);
    if (Object.keys(next).length) return;
    try {
      setSubmitting(true);
      const agg = await meterService.finalizeCycleUsage(subscriptionId, cycleId.trim());
      setResult(agg);
      onFinalized(agg, selectedSub);
      showToast(
        'success',
        'Usage finalised',
        `${formatQuantity(agg.total_quantity)} ${ratedMeter?.unit_name ?? ''} rated at ${formatMoney(agg.rated_amount)} for ${formatDate(agg.period_start)} – ${formatDate(agg.period_end)}.`
      );
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
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 text-sm">
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">Period</dt>
              <dd className="mt-1 text-slate-900">
                {formatDate(result.period_start)} – {formatDate(result.period_end)}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">Status</dt>
              <dd className="mt-1 text-slate-900">{humanize(result.status)}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">Total quantity</dt>
              <dd className="mt-1 text-slate-900 tabular-nums">
                {formatQuantity(result.total_quantity)} {ratedMeter?.unit_name ?? ''}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">Rated amount</dt>
              <dd className="mt-1 text-slate-900 font-semibold tabular-nums">
                {formatMoney(result.rated_amount, selectedSub?.currency ?? 'INR')}
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">Aggregate ID</dt>
              <dd className="mt-1 font-mono text-xs text-slate-700 break-all">{result.id}</dd>
            </div>
          </dl>
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
          <Input
            label="Billing cycle ID"
            required
            placeholder="UUID of the billing cycle to finalise"
            value={cycleId}
            onChange={(e) => setCycleId(e.target.value)}
            error={errors.cycle_id}
            className="font-mono text-xs"
            helperText="Billing cycles are not yet exposed by the subscription API, so the cycle id must be entered manually."
          />

          <div className="flex items-start gap-3 rounded-lg border border-blue-100 bg-blue-50/70 px-4 py-3 text-xs text-slate-700 leading-relaxed">
            <Info className="w-4 h-4 text-brand-600 mt-0.5 shrink-0" />
            <div className="space-y-1">
              <p>
                Rates{' '}
                {ratedMeter ? (
                  <>
                    <span className="font-semibold">{ratedMeter.name}</span> ({ratedMeter.code}, {humanize(ratedMeter.aggregation_type)}{' '}
                    of {ratedMeter.unit_name})
                  </>
                ) : (
                  'the organisation’s primary meter'
                )}{' '}
                for events linked to the chosen subscription within the cycle period.
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
