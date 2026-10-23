import React, { useEffect, useState } from 'react';
import { Modal } from '../../components/common/Modal';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { useToast } from '../../components/common/Toast';
import { automationService } from '../../services/automationService';
import type {
  AutomationSchedule,
  AutomationScheduleCreate,
  AutomationScheduleUpdate,
  ScheduleFrequency,
} from '../../types/automation';
import { FREQUENCY_OPTIONS, TARGET_ACTION_SUGGESTIONS } from './constants';

export interface ScheduleEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  schedule: AutomationSchedule | null;
  onSaved: (schedule: AutomationSchedule) => void;
}

const TARGET_LIST_ID = 'automation-target-action-suggestions';

export function ScheduleEditorModal({ isOpen, onClose, schedule, onSaved }: ScheduleEditorModalProps) {
  const { showToast } = useToast();
  const isEdit = Boolean(schedule);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [frequency, setFrequency] = useState<ScheduleFrequency>('daily');
  const [cron, setCron] = useState('');
  const [targetAction, setTargetAction] = useState('run_billing_jobs');
  const [enabled, setEnabled] = useState(true);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setFieldErrors({});
    if (schedule) {
      setName(schedule.name);
      setDescription(schedule.description ?? '');
      setFrequency(schedule.frequency);
      setCron(schedule.cron_expression ?? '');
      setTargetAction(schedule.target_action);
      setEnabled(schedule.is_active && schedule.status === 'active');
    } else {
      setName('');
      setDescription('');
      setFrequency('daily');
      setCron('');
      setTargetAction('run_billing_jobs');
      setEnabled(true);
    }
  }, [isOpen, schedule]);

  const validate = (): boolean => {
    const errors: Record<string, string> = {};
    if (!name.trim()) errors.name = 'Name is required.';
    if (!targetAction.trim()) errors.target_action = 'Target action is required.';
    else if (!/^[a-z0-9_.:-]+$/i.test(targetAction.trim()))
      errors.target_action = 'Use letters, numbers, underscores, dots or dashes only.';
    if (cron.trim() && cron.trim().split(/\s+/).length !== 5)
      errors.cron_expression = 'Cron expressions need 5 fields (minute hour day month weekday).';
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    setSaving(true);
    try {
      let saved: AutomationSchedule;
      if (schedule) {
        const body: AutomationScheduleUpdate = {
          name: name.trim(),
          description: description.trim() || null,
          frequency,
          cron_expression: cron.trim() || null,
          target_action: targetAction.trim(),
          status: enabled ? 'active' : 'paused',
          is_active: enabled,
        };
        saved = await automationService.updateSchedule(schedule.id, body);
        showToast('success', 'Schedule updated', `"${saved.name}" has been saved.`);
      } else {
        const body: AutomationScheduleCreate = {
          name: name.trim(),
          description: description.trim() || null,
          frequency,
          cron_expression: cron.trim() || null,
          target_action: targetAction.trim(),
          status: enabled ? 'active' : 'paused',
          is_active: enabled,
        };
        saved = await automationService.createSchedule(body);
        showToast('success', 'Schedule created', `"${saved.name}" runs ${saved.frequency}.`);
      }
      onSaved(saved);
      onClose();
    } catch (err: any) {
      const fields = err?.details?.fields;
      if (fields && typeof fields === 'object') setFieldErrors((prev) => ({ ...prev, ...fields }));
      showToast('error', isEdit ? 'Could not update schedule' : 'Could not create schedule', err?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? `Edit schedule: ${schedule?.name ?? ''}` : 'New schedule'}
      description="Schedules run a target action on a recurring cadence. The next run is computed from the frequency."
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Schedule name"
            required
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Nightly billing run"
            error={fieldErrors.name}
          />
          <Select
            label="Frequency"
            required
            value={frequency}
            onChange={(e) => setFrequency(e.target.value as ScheduleFrequency)}
            options={FREQUENCY_OPTIONS}
            error={fieldErrors.frequency}
          />
          <div>
            <Input
              label="Target action"
              required
              maxLength={100}
              list={TARGET_LIST_ID}
              value={targetAction}
              onChange={(e) => setTargetAction(e.target.value)}
              placeholder="run_billing_jobs"
              error={fieldErrors.target_action}
              helperText={fieldErrors.target_action ? undefined : 'Identifier of the job to run. Pick a suggestion or enter your own.'}
            />
            <datalist id={TARGET_LIST_ID}>
              {TARGET_ACTION_SUGGESTIONS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </datalist>
          </div>
          <Input
            label="Cron expression"
            maxLength={50}
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            placeholder="Optional, e.g. 0 2 * * *"
            error={fieldErrors.cron_expression}
            helperText={fieldErrors.cron_expression ? undefined : 'Optional override recorded alongside the frequency.'}
          />
          <div className="md:col-span-2">
            <Input
              label="Description"
              maxLength={255}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional note for your team"
              error={fieldErrors.description}
            />
          </div>
        </div>

        <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer select-none">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Schedule is enabled
          <span className="text-xs text-slate-400">(paused schedules cannot be triggered)</span>
        </label>

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
          <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" size="sm" isLoading={saving}>
            {isEdit ? 'Save changes' : 'Create schedule'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
