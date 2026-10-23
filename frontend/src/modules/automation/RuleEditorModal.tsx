import React, { useEffect, useMemo, useState } from 'react';
import { Plus, Trash2, ArrowUp, ArrowDown, Info } from 'lucide-react';
import { Modal } from '../../components/common/Modal';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { Badge } from '../../components/common/Badge';
import { useToast } from '../../components/common/Toast';
import { automationService } from '../../services/automationService';
import type {
  ActionConfiguration,
  AutomationActionInput,
  AutomationActionType,
  AutomationRule,
  AutomationRuleCreate,
  AutomationRuleUpdate,
  AutomationTriggerEvent,
  ConditionOperator,
} from '../../types/automation';
import {
  ACTION_CONFIG_FIELDS,
  ACTION_TYPE_LABELS,
  ACTION_TYPE_OPTIONS,
  MODULE_OPTIONS,
  OPERATOR_OPTIONS,
  TRIGGER_EVENT_OPTIONS,
  conditionsToRows,
  newRowId,
  rowsToConditions,
  type ConditionRow,
} from './constants';

interface ActionRow extends AutomationActionInput {
  id: string;
}

export interface RuleEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** When provided the modal edits this rule; otherwise it creates a new one. */
  rule: AutomationRule | null;
  onSaved: (rule: AutomationRule) => void;
}

const FIELD_LABEL = 'block text-xs font-medium text-slate-700 mb-1.5';
const INPUT_CLS =
  'block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500';

function emptyAction(order: number): ActionRow {
  return { id: newRowId(), action_type: 'email_alert', name: '', configuration: {}, execution_order: order };
}

export function RuleEditorModal({ isOpen, onClose, rule, onSaved }: RuleEditorModalProps) {
  const { showToast } = useToast();
  const isEdit = Boolean(rule);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [module, setModule] = useState('invoice');
  const [triggerEvent, setTriggerEvent] = useState<AutomationTriggerEvent>('created');
  const [isActive, setIsActive] = useState(true);
  const [conditionRows, setConditionRows] = useState<ConditionRow[]>([]);
  const [actions, setActions] = useState<ActionRow[]>([]);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setFieldErrors({});
    if (rule) {
      setName(rule.name);
      setDescription(rule.description ?? '');
      setModule(rule.module);
      setTriggerEvent(rule.trigger_event);
      setIsActive(rule.is_active);
      setConditionRows(conditionsToRows(rule.conditions));
      setActions(
        [...rule.actions]
          .sort((a, b) => a.execution_order - b.execution_order)
          .map((a) => ({
            id: a.id,
            action_type: a.action_type,
            name: a.name,
            configuration: a.configuration ?? {},
            execution_order: a.execution_order,
          }))
      );
    } else {
      setName('');
      setDescription('');
      setModule('invoice');
      setTriggerEvent('created');
      setIsActive(true);
      setConditionRows([]);
      setActions([emptyAction(1)]);
    }
  }, [isOpen, rule]);

  const moduleOptions = useMemo(() => {
    if (MODULE_OPTIONS.some((o) => o.value === module)) return MODULE_OPTIONS;
    return [...MODULE_OPTIONS, { value: module, label: module }];
  }, [module]);

  // --- Conditions ---------------------------------------------------------
  const addCondition = () =>
    setConditionRows((rows) => [...rows, { id: newRowId(), field: '', operator: 'eq', value: '' }]);
  const updateCondition = (id: string, patch: Partial<ConditionRow>) =>
    setConditionRows((rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const removeCondition = (id: string) => setConditionRows((rows) => rows.filter((r) => r.id !== id));

  // --- Actions ------------------------------------------------------------
  const addAction = () => setActions((list) => [...list, emptyAction(list.length + 1)]);
  const updateAction = (id: string, patch: Partial<ActionRow>) =>
    setActions((list) => list.map((a) => (a.id === id ? { ...a, ...patch } : a)));
  const updateActionConfig = (id: string, key: string, value: string) =>
    setActions((list) =>
      list.map((a) => {
        if (a.id !== id) return a;
        const configuration: ActionConfiguration = { ...a.configuration };
        if (value === '') delete configuration[key];
        else configuration[key] = value;
        return { ...a, configuration };
      })
    );
  const removeAction = (id: string) => setActions((list) => list.filter((a) => a.id !== id));
  const moveAction = (index: number, dir: -1 | 1) =>
    setActions((list) => {
      const next = [...list];
      const target = index + dir;
      if (target < 0 || target >= next.length) return list;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });

  // --- Validation & submit ------------------------------------------------
  const validate = (): boolean => {
    const errors: Record<string, string> = {};
    if (!name.trim()) errors.name = 'Name is required.';
    if (!module.trim()) errors.module = 'Module is required.';
    conditionRows.forEach((r) => {
      if (!r.field.trim()) errors[`cond-${r.id}`] = 'Field is required.';
    });
    if (!isEdit) {
      actions.forEach((a) => {
        if (!a.name.trim()) errors[`action-${a.id}`] = 'Action name is required.';
        ACTION_CONFIG_FIELDS[a.action_type]
          .filter((f) => f.required)
          .forEach((f) => {
            const v = a.configuration[f.key];
            if (v === undefined || v === '') errors[`action-${a.id}-${f.key}`] = `${f.label} is required.`;
          });
      });
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    setSaving(true);
    try {
      const conditions = rowsToConditions(conditionRows);
      let saved: AutomationRule;
      if (rule) {
        const body: AutomationRuleUpdate = {
          name: name.trim(),
          description: description.trim() || null,
          module: module.trim(),
          trigger_event: triggerEvent,
          conditions,
          is_active: isActive,
        };
        saved = await automationService.updateRule(rule.id, body);
        showToast('success', 'Rule updated', `"${saved.name}" has been saved.`);
      } else {
        const body: AutomationRuleCreate = {
          name: name.trim(),
          description: description.trim() || null,
          module: module.trim(),
          trigger_event: triggerEvent,
          conditions,
          is_active: isActive,
          actions: actions.map((a, i) => ({
            action_type: a.action_type,
            name: a.name.trim(),
            configuration: a.configuration,
            execution_order: i + 1,
          })),
        };
        saved = await automationService.createRule(body);
        showToast('success', 'Rule created', `"${saved.name}" is ${saved.is_active ? 'active' : 'paused'}.`);
      }
      onSaved(saved);
      onClose();
    } catch (err: any) {
      const fields = err?.details?.fields;
      if (fields && typeof fields === 'object') setFieldErrors((prev) => ({ ...prev, ...fields }));
      showToast('error', isEdit ? 'Could not update rule' : 'Could not create rule', err?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? `Edit rule: ${rule?.name ?? ''}` : 'New automation rule'}
      description="Rules listen for domain events and run their actions when every condition matches."
      size="xl"
    >
      <form onSubmit={handleSubmit} className="space-y-6 max-h-[70vh] overflow-y-auto pr-1 -mr-1">
        {/* Basics */}
        <section className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Rule name"
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Alert finance on overdue invoices"
              error={fieldErrors.name}
            />
            <Select
              label="Module"
              required
              value={module}
              onChange={(e) => setModule(e.target.value)}
              options={moduleOptions}
              error={fieldErrors.module}
            />
            <Select
              label="Trigger event"
              required
              value={triggerEvent}
              onChange={(e) => setTriggerEvent(e.target.value as AutomationTriggerEvent)}
              options={TRIGGER_EVENT_OPTIONS}
              error={fieldErrors.trigger_event}
            />
            <Input
              label="Description"
              maxLength={255}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional note for your team"
              error={fieldErrors.description}
            />
          </div>
          <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer select-none">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
            />
            Rule is enabled
          </label>
        </section>

        {/* Conditions */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-semibold text-slate-900">Conditions</h4>
              <p className="text-xs text-slate-500 mt-0.5">
                All conditions must match the event payload. Leave empty to match every event.
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={addCondition} leadingIcon={<Plus className="w-3.5 h-3.5" />}>
              Add condition
            </Button>
          </div>

          {conditionRows.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-4 text-xs text-slate-500 text-center">
              No conditions — this rule fires on every <span className="font-medium">{module}</span> event of this type.
            </div>
          ) : (
            <div className="space-y-2">
              {conditionRows.map((row) => (
                <div key={row.id} className="grid grid-cols-12 gap-2 items-start">
                  <div className="col-span-12 sm:col-span-4">
                    <input
                      type="text"
                      value={row.field}
                      onChange={(e) => updateCondition(row.id, { field: e.target.value })}
                      placeholder="Field, e.g. total"
                      className={INPUT_CLS}
                      aria-label="Condition field"
                    />
                    {fieldErrors[`cond-${row.id}`] && (
                      <p className="mt-1 text-xs text-rose-600">{fieldErrors[`cond-${row.id}`]}</p>
                    )}
                  </div>
                  <div className="col-span-6 sm:col-span-3">
                    <select
                      value={row.operator}
                      onChange={(e) => updateCondition(row.id, { operator: e.target.value as ConditionOperator })}
                      className={INPUT_CLS}
                      aria-label="Condition operator"
                    >
                      {OPERATOR_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-span-5 sm:col-span-4">
                    <input
                      type="text"
                      value={row.value}
                      onChange={(e) => updateCondition(row.id, { value: e.target.value })}
                      placeholder={row.operator === 'in' ? 'a, b, c' : 'Value'}
                      className={INPUT_CLS}
                      aria-label="Condition value"
                    />
                  </div>
                  <div className="col-span-1 flex justify-end">
                    <button
                      type="button"
                      onClick={() => removeCondition(row.id)}
                      className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                      aria-label="Remove condition"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
              <p className="text-[11px] text-slate-400">
                Numbers and true/false are stored as typed values; use commas to list values for “is one of”.
              </p>
            </div>
          )}
        </section>

        {/* Actions */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-semibold text-slate-900">Actions</h4>
              <p className="text-xs text-slate-500 mt-0.5">Run in order when the rule matches.</p>
            </div>
            {!isEdit && (
              <Button type="button" variant="outline" size="sm" onClick={addAction} leadingIcon={<Plus className="w-3.5 h-3.5" />}>
                Add action
              </Button>
            )}
          </div>

          {isEdit && (
            <div className="flex items-start gap-2 rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 text-xs text-blue-800">
              <Info className="w-4 h-4 mt-0.5 shrink-0" />
              <span>
                Actions are fixed once a rule is created. To change them, delete this rule and create a new one with
                the updated actions.
              </span>
            </div>
          )}

          {actions.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-4 text-xs text-slate-500 text-center">
              No actions — the rule will be evaluated and logged, but nothing will run.
            </div>
          ) : (
            <div className="space-y-3">
              {actions.map((action, index) => {
                const fields = ACTION_CONFIG_FIELDS[action.action_type];
                return (
                  <div key={action.id} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white text-xs font-semibold">
                          {index + 1}
                        </span>
                        <Badge variant="info" size="sm">
                          {ACTION_TYPE_LABELS[action.action_type]}
                        </Badge>
                      </div>
                      {!isEdit && (
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => moveAction(index, -1)}
                            disabled={index === 0}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-white disabled:opacity-30 transition-colors"
                            aria-label="Move up"
                          >
                            <ArrowUp className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => moveAction(index, 1)}
                            disabled={index === actions.length - 1}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-white disabled:opacity-30 transition-colors"
                            aria-label="Move down"
                          >
                            <ArrowDown className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => removeAction(action.id)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                            aria-label="Remove action"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <Select
                        label="Action type"
                        value={action.action_type}
                        disabled={isEdit}
                        onChange={(e) =>
                          updateAction(action.id, {
                            action_type: e.target.value as AutomationActionType,
                            configuration: {},
                          })
                        }
                        options={ACTION_TYPE_OPTIONS}
                      />
                      <Input
                        label="Action name"
                        required={!isEdit}
                        disabled={isEdit}
                        maxLength={100}
                        value={action.name}
                        onChange={(e) => updateAction(action.id, { name: e.target.value })}
                        placeholder="e.g. Notify finance team"
                        error={fieldErrors[`action-${action.id}`]}
                      />
                      {fields.map((f) => {
                        const raw = action.configuration[f.key];
                        const value = raw === undefined || raw === null ? '' : String(raw);
                        const error = fieldErrors[`action-${action.id}-${f.key}`];
                        if (f.type === 'textarea') {
                          return (
                            <div key={f.key} className="md:col-span-2">
                              <label className={FIELD_LABEL}>{f.label}</label>
                              <textarea
                                rows={2}
                                disabled={isEdit}
                                value={value}
                                onChange={(e) => updateActionConfig(action.id, f.key, e.target.value)}
                                placeholder={f.placeholder}
                                className={`${INPUT_CLS} disabled:bg-slate-50 disabled:text-slate-400`}
                              />
                            </div>
                          );
                        }
                        return (
                          <Input
                            key={f.key}
                            label={f.label}
                            type={f.type ?? 'text'}
                            required={Boolean(f.required) && !isEdit}
                            disabled={isEdit}
                            value={value}
                            onChange={(e) => updateActionConfig(action.id, f.key, e.target.value)}
                            placeholder={f.placeholder}
                            error={error}
                          />
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200 sticky bottom-0 bg-white">
          <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" size="sm" isLoading={saving}>
            {isEdit ? 'Save changes' : 'Create rule'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
