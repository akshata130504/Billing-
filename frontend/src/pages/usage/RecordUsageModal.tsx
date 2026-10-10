import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { fieldErrors } from '../../services/apiClient';
import { customerService } from '../../services/customerService';
import { meterService } from '../../services/meterService';
import { subscriptionService } from '../../services/subscriptionService';
import type { CustomerOut, SubscriptionOut } from '../../types/api';
import type { RecordedUsageEvent, UsageMeterOut } from '../../types/meters';
import { humanize } from '../../utils/format';
import {
  AGGREGATION_LABELS,
  datetimeLocalToIso,
  newIdempotencyKey,
  toDatetimeLocalValue,
} from './usageUtils';

interface RecordUsageModalProps {
  isOpen: boolean;
  onClose: () => void;
  meters: UsageMeterOut[];
  /** Pre-selects a meter when opened from the meter detail view. */
  initialMeterCode?: string | null;
  /** Idempotency keys already recorded this session, used to flag replays. */
  knownKeys: ReadonlySet<string>;
  onRecorded: (recorded: RecordedUsageEvent) => void;
}

export function RecordUsageModal({
  isOpen,
  onClose,
  meters,
  initialMeterCode,
  knownKeys,
  onRecorded,
}: RecordUsageModalProps) {
  const { showToast } = useToast();

  const [customers, setCustomers] = useState<CustomerOut[]>([]);
  const [customersLoading, setCustomersLoading] = useState(false);
  const [subscriptions, setSubscriptions] = useState<SubscriptionOut[]>([]);
  const [subsLoading, setSubsLoading] = useState(false);

  const [meterCode, setMeterCode] = useState('');
  const [customerId, setCustomerId] = useState('');
  const [subscriptionId, setSubscriptionId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [timestamp, setTimestamp] = useState(toDatetimeLocalValue());
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey());
  const [properties, setProperties] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const activeMeters = useMemo(() => meters.filter((m) => m.is_active), [meters]);
  const selectedMeter = useMemo(() => meters.find((m) => m.code === meterCode) ?? null, [meters, meterCode]);

  // Reset the form each time the dialog opens.
  useEffect(() => {
    if (!isOpen) return;
    setMeterCode(initialMeterCode ?? activeMeters[0]?.code ?? '');
    setCustomerId('');
    setSubscriptionId('');
    setQuantity('');
    setTimestamp(toDatetimeLocalValue());
    setIdempotencyKey(newIdempotencyKey());
    setProperties('');
    setErrors({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, initialMeterCode]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setCustomersLoading(true);
    customerService
      .list({ page_size: 100, sort: 'display_name' })
      .then((res) => {
        if (!cancelled) setCustomers(res.items ?? []);
      })
      .catch((err: any) => {
        if (!cancelled) showToast('error', err?.message || 'Failed to load customers');
      })
      .finally(() => {
        if (!cancelled) setCustomersLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, showToast]);

  useEffect(() => {
    setSubscriptionId('');
    if (!isOpen || !customerId) {
      setSubscriptions([]);
      return;
    }
    let cancelled = false;
    setSubsLoading(true);
    subscriptionService
      .list({ customer_id: customerId, page_size: 100 })
      .then((res) => {
        if (!cancelled) setSubscriptions(res.items ?? []);
      })
      .catch(() => {
        if (!cancelled) setSubscriptions([]);
      })
      .finally(() => {
        if (!cancelled) setSubsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, customerId]);

  const validate = (): { ok: boolean; props: Record<string, unknown> | null } => {
    const next: Record<string, string> = {};
    if (!meterCode) next.meter_code = 'Choose a meter.';
    if (!customerId) next.customer_id = 'Choose a customer.';
    const q = Number(quantity);
    if (!quantity.trim() || !Number.isFinite(q)) next.quantity = 'Enter a numeric quantity.';
    else if (q <= 0) next.quantity = 'Quantity must be greater than 0.';
    if (!idempotencyKey.trim()) next.idempotency_key = 'Idempotency key is required.';
    else if (idempotencyKey.trim().length > 128) next.idempotency_key = 'Key must be 128 characters or fewer.';
    if (timestamp && !datetimeLocalToIso(timestamp)) next.timestamp = 'Enter a valid date and time.';

    let props: Record<string, unknown> | null = null;
    if (properties.trim()) {
      try {
        const parsed: unknown = JSON.parse(properties);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          props = parsed as Record<string, unknown>;
        } else {
          next.properties = 'Properties must be a JSON object, e.g. {"region": "ap-south-1"}.';
        }
      } catch {
        next.properties = 'Properties is not valid JSON.';
      }
    }
    setErrors(next);
    return { ok: Object.keys(next).length === 0, props };
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const { ok, props } = validate();
    if (!ok || !selectedMeter) return;
    const key = idempotencyKey.trim();
    const customer = customers.find((c) => c.id === customerId);
    const subscription = subscriptions.find((s) => s.id === subscriptionId) ?? null;
    try {
      setSaving(true);
      const event = await meterService.recordEvent({
        meter_code: selectedMeter.code,
        customer_id: customerId,
        quantity: quantity.trim(),
        idempotency_key: key,
        subscription_id: subscriptionId || null,
        timestamp: datetimeLocalToIso(timestamp),
        properties: props,
      });
      // The endpoint is idempotent: a re-used key returns the original event untouched.
      const replayed = knownKeys.has(key) || Number(event.quantity) !== Number(quantity);
      onRecorded({
        event,
        meter_code: selectedMeter.code,
        meter_name: selectedMeter.name,
        unit_name: selectedMeter.unit_name,
        customer_label: customer ? `${customer.display_name} (${customer.customer_number})` : customerId,
        subscription_label: subscription ? subscription.subscription_number : null,
        replayed,
        recorded_at: new Date().toISOString(),
        source: 'single',
      });
      if (replayed) {
        showToast(
          'warning',
          'Duplicate idempotency key',
          'The server already had an event with this key and returned the original unchanged.'
        );
      } else {
        showToast(
          'success',
          'Usage recorded',
          `${quantity.trim()} ${selectedMeter.unit_name} on ${selectedMeter.name}${customer ? ` for ${customer.display_name}` : ''}.`
        );
      }
      onClose();
    } catch (err: any) {
      const fe = fieldErrors(err);
      if (Object.keys(fe).length) setErrors(fe);
      showToast('error', err?.message || 'Failed to record usage');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Record Usage"
      description="Post a single usage event. Events are idempotent on (meter, idempotency key)."
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select
            label="Meter"
            required
            value={meterCode}
            onChange={(e) => setMeterCode(e.target.value)}
            placeholder={activeMeters.length ? 'Select a meter' : 'No active meters'}
            options={activeMeters.map((m) => ({ value: m.code, label: `${m.name} (${m.code})` }))}
            error={errors.meter_code}
            helperText={
              selectedMeter
                ? `${AGGREGATION_LABELS[selectedMeter.aggregation_type].label} of ${selectedMeter.unit_name}`
                : undefined
            }
          />
          <Select
            label="Customer"
            required
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            placeholder={customersLoading ? 'Loading customers…' : customers.length ? 'Select a customer' : 'No customers found'}
            options={customers.map((c) => ({ value: c.id, label: `${c.display_name} (${c.customer_number})` }))}
            error={errors.customer_id}
            disabled={customersLoading}
          />
        </div>

        <Select
          label="Subscription"
          value={subscriptionId}
          onChange={(e) => setSubscriptionId(e.target.value)}
          disabled={!customerId || subsLoading}
          helperText={
            !customerId
              ? 'Optional. Choose a customer first to link usage to one of their subscriptions.'
              : subsLoading
                ? 'Loading subscriptions…'
                : subscriptions.length
                  ? 'Optional. Linking a subscription lets the usage be rated in its billing cycle.'
                  : 'This customer has no subscriptions; the event will be recorded against the customer only.'
          }
        >
          <option value="">Not linked to a subscription</option>
          {subscriptions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.subscription_number} · {s.plan.name} · {humanize(s.status)}
            </option>
          ))}
        </Select>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label={`Quantity${selectedMeter ? ` (${selectedMeter.unit_name})` : ''}`}
            required
            type="number"
            inputMode="decimal"
            step="any"
            min="0"
            placeholder="e.g. 125.5"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            error={errors.quantity}
          />
          <Input
            label="Timestamp"
            type="datetime-local"
            value={timestamp}
            onChange={(e) => setTimestamp(e.target.value)}
            error={errors.timestamp}
            helperText="When the usage happened. Defaults to now; sent as UTC."
          />
        </div>

        <div>
          <Input
            label="Idempotency key"
            required
            value={idempotencyKey}
            maxLength={128}
            onChange={(e) => setIdempotencyKey(e.target.value)}
            error={errors.idempotency_key}
            className="font-mono text-xs"
            trailingIcon={
              <button
                type="button"
                onClick={() => setIdempotencyKey(newIdempotencyKey())}
                className="pointer-events-auto p-1 rounded text-slate-400 hover:text-brand-600 hover:bg-slate-100"
                title="Generate a new key"
                aria-label="Generate a new idempotency key"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            }
            helperText="Auto-generated. Re-sending the same key for this meter never creates a second event."
          />
        </div>

        <div>
          <label htmlFor="record-usage-properties" className="block text-xs font-medium text-slate-700 mb-1.5">Properties (JSON, optional)</label>
          <textarea
            id="record-usage-properties"
            rows={3}
            spellCheck={false}
            placeholder='{"region": "ap-south-1", "endpoint": "/v1/search"}'
            value={properties}
            onChange={(e) => setProperties(e.target.value)}
            className="w-full px-3 py-2 text-xs font-mono bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:outline-none"
          />
          {errors.properties && <p className="mt-1.5 text-xs text-rose-600">{errors.properties}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
          <Button variant="ghost" size="sm" type="button" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" isLoading={saving} disabled={!activeMeters.length}>
            Record Usage
          </Button>
        </div>
      </form>
    </Modal>
  );
}
