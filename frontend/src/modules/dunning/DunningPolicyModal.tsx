import React, { useEffect, useMemo, useState } from 'react';
import { Modal } from '../../components/common/Modal';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { useToast } from '../../components/common/Toast';
import { fieldErrors } from '../../services/apiClient';
import { dunningService } from '../../services/dunningService';
import type { DunningFinalAction, DunningPolicy, DunningPolicyCreate } from '../../types/dunning';
import { FINAL_ACTION_CONFIG } from './dunningUi';

export interface DunningPolicyModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** When provided the modal edits this policy, otherwise it creates a new one. */
  policy: DunningPolicy | null;
  onSaved: (policy: DunningPolicy) => void;
}

interface PolicyFormState {
  name: string;
  description: string;
  is_default: boolean;
  is_active: boolean;
  applies_to_autocharge: boolean;
  min_amount: string;
  retry_intervals: string[]; // 1..3 entries, kept as strings for controlled inputs
  total_span_days: string;
  notify_on_failure: boolean;
  notify_on_retry: boolean;
  notify_on_success: boolean;
  first_ach_immediate_cancel: boolean;
  final_action: DunningFinalAction;
  non_autocharge_grace_days: string;
}

const DEFAULT_FORM: PolicyFormState = {
  name: '',
  description: '',
  is_default: false,
  is_active: true,
  applies_to_autocharge: true,
  min_amount: '',
  retry_intervals: ['3', '5', '7'],
  total_span_days: '30',
  notify_on_failure: true,
  notify_on_retry: true,
  notify_on_success: true,
  first_ach_immediate_cancel: true,
  final_action: 'unpaid',
  non_autocharge_grace_days: '15',
};

function fromPolicy(policy: DunningPolicy): PolicyFormState {
  return {
    name: policy.name,
    description: policy.description ?? '',
    is_default: policy.is_default,
    is_active: policy.is_active,
    applies_to_autocharge: policy.applies_to_autocharge,
    min_amount: policy.min_amount ?? '',
    retry_intervals: (policy.retry_intervals_days.length ? policy.retry_intervals_days : [3]).map(String),
    total_span_days: String(policy.total_span_days),
    notify_on_failure: policy.notify_on_failure,
    notify_on_retry: policy.notify_on_retry,
    notify_on_success: policy.notify_on_success,
    first_ach_immediate_cancel: policy.first_ach_immediate_cancel,
    final_action: policy.final_action,
    non_autocharge_grace_days: String(policy.non_autocharge_grace_days),
  };
}

const FINAL_ACTION_OPTIONS = (Object.keys(FINAL_ACTION_CONFIG) as DunningFinalAction[]).map((value) => ({
  value,
  label: FINAL_ACTION_CONFIG[value].label,
}));

function Checkbox({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-2.5 cursor-pointer select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
      />
      <span className="min-w-0">
        <span className="block text-sm text-slate-800">{label}</span>
        {hint && <span className="block text-xs text-slate-500 mt-0.5">{hint}</span>}
      </span>
    </label>
  );
}

export function DunningPolicyModal({ isOpen, onClose, policy, onSaved }: DunningPolicyModalProps) {
  const { showToast } = useToast();
  const isEdit = Boolean(policy);

  const [form, setForm] = useState<PolicyFormState>(DEFAULT_FORM);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setForm(policy ? fromPolicy(policy) : DEFAULT_FORM);
    setErrors({});
  }, [isOpen, policy]);

  const set = <K extends keyof PolicyFormState>(key: K, value: PolicyFormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const intervals = useMemo(
    () => form.retry_intervals.map((v) => parseInt(v, 10)).filter((n) => Number.isFinite(n)),
    [form.retry_intervals]
  );
  const intervalSum = intervals.reduce((acc, n) => acc + n, 0);
  const spanDays = parseInt(form.total_span_days, 10);

  // Cumulative day offsets for the schedule preview ("Day 3 → Day 8 → Day 15").
  const schedulePreview = useMemo(() => {
    let running = 0;
    return intervals.map((n) => {
      running += n;
      return running;
    });
  }, [intervals]);

  const setRetryCount = (count: number) => {
    const next = [...form.retry_intervals];
    while (next.length < count) next.push(String(DEFAULT_FORM.retry_intervals[next.length] ?? 5));
    set('retry_intervals', next.slice(0, count));
  };

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    if (!form.name.trim()) next.name = 'Policy name is required.';
    if (form.name.trim().length > 100) next.name = 'Keep the name under 100 characters.';
    if (form.description.length > 255) next.description = 'Keep the description under 255 characters.';
    if (form.retry_intervals.length < 1 || form.retry_intervals.length > 3) {
      next.retry_intervals = 'Configure between 1 and 3 retries.';
    }
    form.retry_intervals.forEach((v, i) => {
      const n = parseInt(v, 10);
      if (!Number.isFinite(n) || n < 1) next.retry_intervals = `Retry ${i + 1} must wait at least 1 day.`;
    });
    if (!Number.isFinite(spanDays) || spanDays < 1 || spanDays > 30) {
      next.total_span_days = 'Total span must be between 1 and 30 days.';
    } else if (intervalSum > spanDays) {
      next.retry_intervals = `Retry intervals add up to ${intervalSum} days, which exceeds the ${spanDays}-day span.`;
    }
    const grace = parseInt(form.non_autocharge_grace_days, 10);
    if (!Number.isFinite(grace) || grace < 1 || grace > 60) {
      next.non_autocharge_grace_days = 'Grace period must be between 1 and 60 days.';
    }
    if (form.min_amount.trim() !== '') {
      const amt = Number(form.min_amount);
      if (!Number.isFinite(amt) || amt < 0) next.min_amount = 'Enter a valid non-negative amount.';
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    const payload: DunningPolicyCreate = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      is_default: form.is_default,
      is_active: form.is_active,
      applies_to_autocharge: form.applies_to_autocharge,
      min_amount: form.min_amount.trim() === '' ? null : Number(form.min_amount).toFixed(2),
      max_retries: intervals.length,
      retry_intervals_days: intervals,
      total_span_days: spanDays,
      notify_on_failure: form.notify_on_failure,
      notify_on_retry: form.notify_on_retry,
      notify_on_success: form.notify_on_success,
      first_ach_immediate_cancel: form.first_ach_immediate_cancel,
      final_action: form.final_action,
      non_autocharge_grace_days: parseInt(form.non_autocharge_grace_days, 10),
    };

    try {
      setSaving(true);
      const saved = policy
        ? await dunningService.updatePolicy(policy.id, payload)
        : await dunningService.createPolicy(payload);
      showToast('success', policy ? 'Policy updated' : 'Policy created', `"${saved.name}" is ready to use.`);
      onSaved(saved);
      onClose();
    } catch (err: any) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length) setErrors((prev) => ({ ...prev, ...fields }));
      showToast('error', policy ? 'Could not update policy' : 'Could not create policy', err?.message);
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    'w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-brand-500 focus:outline-none';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? `Edit policy: ${policy?.name ?? ''}` : 'New dunning policy'}
      description="Define how failed payments are retried, who gets notified, and what happens when retries are exhausted."
      size="lg"
      footer={
        <>
          <Button variant="outline" size="sm" type="button" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" form="dunning-policy-form" isLoading={saving}>
            {isEdit ? 'Save changes' : 'Create policy'}
          </Button>
        </>
      }
    >
      <form id="dunning-policy-form" onSubmit={handleSubmit} className="space-y-6 max-h-[70vh] overflow-y-auto pr-1">
        {/* Identity */}
        <section className="space-y-4">
          <Input
            label="Policy name"
            required
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="e.g. High-value accounts recovery"
            error={errors.name}
            maxLength={100}
          />
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1.5">Description</label>
            <textarea
              rows={2}
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
              placeholder="When this policy should apply and what it does."
              className={inputClass}
              maxLength={255}
            />
            {errors.description && <p className="mt-1 text-xs text-rose-600 font-medium">{errors.description}</p>}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Checkbox
              label="Default policy"
              hint="Used when no other policy matches. Setting this demotes the current default."
              checked={form.is_default}
              onChange={(v) => set('is_default', v)}
            />
            <Checkbox
              label="Active"
              hint="Inactive policies are never applied to new cases."
              checked={form.is_active}
              onChange={(v) => set('is_active', v)}
            />
          </div>
        </section>

        {/* Targeting */}
        <section className="space-y-4 pt-4 border-t border-slate-100">
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Applies to</h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Checkbox
              label="Autocharge invoices"
              hint="Off = manual / non-autocharge past-due invoices."
              checked={form.applies_to_autocharge}
              onChange={(v) => set('applies_to_autocharge', v)}
            />
            <Input
              label="Minimum invoice amount"
              type="number"
              min={0}
              step="0.01"
              inputMode="decimal"
              value={form.min_amount}
              onChange={(e) => set('min_amount', e.target.value)}
              placeholder="Any amount"
              helperText="Optional. Higher minimums win when several policies match."
              error={errors.min_amount}
            />
          </div>
        </section>

        {/* Retry schedule */}
        <section className="space-y-4 pt-4 border-t border-slate-100">
          <div className="flex items-center justify-between gap-4">
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Retry schedule</h4>
            <span className={`text-xs font-medium ${intervalSum > spanDays ? 'text-rose-600' : 'text-slate-500'}`}>
              {intervalSum} of {Number.isFinite(spanDays) ? spanDays : '—'} days used
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Select
              label="Number of retries"
              value={String(form.retry_intervals.length)}
              onChange={(e) => setRetryCount(parseInt(e.target.value, 10))}
              options={[
                { value: '1', label: '1 retry' },
                { value: '2', label: '2 retries' },
                { value: '3', label: '3 retries' },
              ]}
            />
            <Input
              label="Total span (days)"
              type="number"
              min={1}
              max={30}
              value={form.total_span_days}
              onChange={(e) => set('total_span_days', e.target.value)}
              helperText="Maximum 30 days."
              error={errors.total_span_days}
            />
            <Input
              label="Manual invoice grace (days)"
              type="number"
              min={1}
              max={60}
              value={form.non_autocharge_grace_days}
              onChange={(e) => set('non_autocharge_grace_days', e.target.value)}
              helperText="Before dunning non-autocharge invoices."
              error={errors.non_autocharge_grace_days}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {form.retry_intervals.map((value, idx) => (
              <Input
                key={idx}
                label={`Retry ${idx + 1} — wait (days)`}
                type="number"
                min={1}
                max={30}
                value={value}
                onChange={(e) => {
                  const next = [...form.retry_intervals];
                  next[idx] = e.target.value;
                  set('retry_intervals', next);
                }}
                helperText={schedulePreview[idx] !== undefined ? `Runs on day ${schedulePreview[idx]}` : undefined}
              />
            ))}
          </div>
          {errors.retry_intervals && <p className="text-xs text-rose-600 font-medium">{errors.retry_intervals}</p>}
          {schedulePreview.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-600">
              <span className="font-medium text-slate-700">Timeline:</span>
              <span className="px-2 py-0.5 rounded-md bg-slate-100 border border-slate-200">Payment fails</span>
              {schedulePreview.map((day, i) => (
                <React.Fragment key={i}>
                  <span className="text-slate-400">→</span>
                  <span className="px-2 py-0.5 rounded-md bg-blue-50 text-brand-700 border border-blue-100">
                    Retry {i + 1} · day {day}
                  </span>
                </React.Fragment>
              ))}
              <span className="text-slate-400">→</span>
              <span className="px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-100">
                {FINAL_ACTION_CONFIG[form.final_action].label}
              </span>
            </div>
          )}
        </section>

        {/* Outcome */}
        <section className="space-y-4 pt-4 border-t border-slate-100">
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">When retries are exhausted</h4>
          <Select
            label="Final action"
            value={form.final_action}
            onChange={(e) => set('final_action', e.target.value as DunningFinalAction)}
            options={FINAL_ACTION_OPTIONS}
            helperText={FINAL_ACTION_CONFIG[form.final_action].description}
          />
          <Checkbox
            label="Cancel immediately on first ACH / bank-debit failure"
            hint="Bank debits rarely recover on retry; skip the retry ladder for them."
            checked={form.first_ach_immediate_cancel}
            onChange={(v) => set('first_ach_immediate_cancel', v)}
          />
        </section>

        {/* Notifications */}
        <section className="space-y-3 pt-4 border-t border-slate-100">
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Customer notifications</h4>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Checkbox
              label="On payment failure"
              checked={form.notify_on_failure}
              onChange={(v) => set('notify_on_failure', v)}
            />
            <Checkbox label="Before each retry" checked={form.notify_on_retry} onChange={(v) => set('notify_on_retry', v)} />
            <Checkbox
              label="On successful recovery"
              checked={form.notify_on_success}
              onChange={(v) => set('notify_on_success', v)}
            />
          </div>
        </section>
      </form>
    </Modal>
  );
}
