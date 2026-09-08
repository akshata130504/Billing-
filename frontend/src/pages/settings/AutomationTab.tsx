import { useState, type FormEvent, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircle2,
  PauseCircle,
  Plus,
  Power,
  Trash2,
  XCircle,
  Zap,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { Modal } from '../../components/common/Modal';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { DataTable, type Column } from '../../components/common/DataTable';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { useToast } from '../../components/common/Toast';
import { automationService } from '../../services/automationService';
import { toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime, humanize, statusVariant } from '../../utils/format';
import type {
  AutomationAction,
  AutomationActionType,
  AutomationCondition,
  AutomationConditionField,
  AutomationConditionOp,
  AutomationExecutionOut,
  AutomationRuleOut,
  AutomationTrigger,
} from '../../types/automation';
import { ReadOnlyNotice } from './settingsShared';

const TRIGGERS: { value: AutomationTrigger; label: string }[] = [
  { value: 'invoice_overdue', label: 'Invoice overdue' },
  { value: 'invoice_due_soon', label: 'Invoice due soon' },
  { value: 'quote_expiring', label: 'Quote expiring' },
  { value: 'payment_received', label: 'Payment received' },
  { value: 'payment_failed', label: 'Payment failed' },
  { value: 'customer_created', label: 'Customer created' },
  { value: 'quote_accepted', label: 'Quote accepted' },
  { value: 'invoice_created', label: 'Invoice created' },
];

const CONDITION_FIELDS: { value: AutomationConditionField; label: string }[] = [
  { value: 'amount', label: 'Amount' },
  { value: 'days_overdue', label: 'Days overdue' },
  { value: 'status', label: 'Status' },
  { value: 'payment_method', label: 'Payment method' },
  { value: 'customer_segment', label: 'Customer segment' },
];

const CONDITION_OPS: { value: AutomationConditionOp; label: string }[] = [
  { value: 'eq', label: 'equals' },
  { value: 'ne', label: 'not equals' },
  { value: 'gt', label: 'greater than' },
  { value: 'gte', label: 'greater than or equal to' },
  { value: 'lt', label: 'less than' },
  { value: 'lte', label: 'less than or equal to' },
  { value: 'contains', label: 'contains' },
];

const ACTION_TYPES: { value: AutomationActionType; label: string }[] = [
  { value: 'create_activity', label: 'Create activity' },
  { value: 'create_reminder', label: 'Create reminder' },
  { value: 'send_email', label: 'Send email' },
  { value: 'update_collection_status', label: 'Update collection status' },
  { value: 'create_approval_task', label: 'Create approval task' },
];

const NUMERIC_FIELDS: string[] = ['amount', 'days_overdue'];

/** Which param inputs to render for each action type. Kept intentionally simple. */
const ACTION_PARAM_FIELDS: Record<AutomationActionType, { key: string; label: string; placeholder?: string }[]> = {
  create_activity: [
    { key: 'activity_type', label: 'Activity type', placeholder: 'e.g. reminder' },
    { key: 'note', label: 'Note', placeholder: 'Optional note' },
  ],
  create_reminder: [{ key: 'note', label: 'Note', placeholder: 'Optional note' }],
  send_email: [
    { key: 'subject', label: 'Subject', placeholder: 'Email subject' },
    { key: 'body', label: 'Body', placeholder: 'Email body' },
  ],
  update_collection_status: [{ key: 'status', label: 'Status', placeholder: 'e.g. in_follow_up' }],
  create_approval_task: [{ key: 'note', label: 'Note', placeholder: 'Optional note' }],
};

interface ConditionRow {
  field: AutomationConditionField;
  op: AutomationConditionOp;
  value: string;
}

interface ActionRow {
  action: AutomationActionType;
  params: Record<string, string>;
}

function emptyConditionRow(): ConditionRow {
  return { field: 'amount', op: 'gt', value: '' };
}

function emptyActionRow(): ActionRow {
  return { action: 'create_activity', params: {} };
}

function resultPreview(result: unknown): string {
  if (result === null || result === undefined) return '—';
  try {
    const text = JSON.stringify(result);
    return text.length > 140 ? `${text.slice(0, 140)}…` : text;
  } catch {
    return String(result);
  }
}

export function AutomationTab() {
  const { hasRole } = useAuth();
  const canEdit = hasRole('admin');
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [rulesPage, setRulesPage] = useState(1);
  const [executionsPage, setExecutionsPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [ruleToDelete, setRuleToDelete] = useState<AutomationRuleOut | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const dashboard = useQuery({
    queryKey: queryKeys.automation.dashboard(),
    queryFn: automationService.dashboard,
  });

  const rulesParams = { page: rulesPage, page_size: 10 };
  const rules = useQuery({
    queryKey: queryKeys.automation.rules(rulesParams),
    queryFn: () => automationService.listRules(rulesParams),
  });

  const executionsParams = { page: executionsPage, page_size: 10 };
  const executions = useQuery({
    queryKey: queryKeys.automation.executions(executionsParams),
    queryFn: () => automationService.listExecutions(executionsParams),
  });

  const invalidateAll = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.automation.all });
  };

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      automationService.setRuleActive(id, { is_active }),
    onMutate: ({ id }) => setTogglingId(id),
    onSuccess: (updated) => {
      invalidateAll();
      showToast(
        'success',
        updated.is_active ? 'Rule enabled' : 'Rule paused',
        `"${updated.name}" is now ${updated.is_active ? 'active' : 'paused'}.`
      );
    },
    onError: (err) => showToast('error', 'Could not update rule', toApiError(err).message),
    onSettled: () => setTogglingId(null),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => automationService.deleteRule(id),
    onSuccess: () => {
      invalidateAll();
      showToast('success', 'Rule deleted', ruleToDelete ? `"${ruleToDelete.name}" was removed.` : undefined);
      setRuleToDelete(null);
    },
    onError: (err) => showToast('error', 'Could not delete rule', toApiError(err).message),
  });

  const ruleColumns: Column<AutomationRuleOut>[] = [
    {
      key: 'name',
      title: 'Rule',
      render: (rule) => (
        <div>
          <div className="font-medium text-slate-900">{rule.name}</div>
          <div className="text-xs text-slate-400 mt-0.5">
            {rule.conditions.length} condition{rule.conditions.length === 1 ? '' : 's'} ·{' '}
            {rule.actions.length} action{rule.actions.length === 1 ? '' : 's'}
          </div>
        </div>
      ),
    },
    {
      key: 'trigger',
      title: 'Trigger',
      render: (rule) => <span className="text-slate-600">{humanize(rule.trigger)}</span>,
    },
    {
      key: 'is_active',
      title: 'Status',
      render: (rule) => (
        <Badge variant={rule.is_active ? 'success' : 'neutral'} size="sm" dot>
          {rule.is_active ? 'Active' : 'Paused'}
        </Badge>
      ),
    },
    {
      key: 'created_by',
      title: 'Created by',
      render: (rule) => <span className="text-slate-500">{rule.created_by?.full_name ?? '—'}</span>,
    },
    {
      key: 'actions',
      title: '',
      align: 'right',
      render: (rule) =>
        canEdit ? (
          <div className="flex items-center justify-end gap-1.5">
            <Button
              variant="outline"
              size="sm"
              isLoading={togglingId === rule.id}
              onClick={() => toggleMutation.mutate({ id: rule.id, is_active: !rule.is_active })}
              leadingIcon={
                rule.is_active ? <PauseCircle className="w-3.5 h-3.5" /> : <Power className="w-3.5 h-3.5" />
              }
            >
              {rule.is_active ? 'Pause' : 'Enable'}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setRuleToDelete(rule)}
              leadingIcon={<Trash2 className="w-3.5 h-3.5 text-rose-500" />}
              aria-label={`Delete ${rule.name}`}
            />
          </div>
        ) : (
          <span className="text-xs text-slate-300">—</span>
        ),
    },
  ];

  const executionColumns: Column<AutomationExecutionOut>[] = [
    {
      key: 'trigger',
      title: 'Trigger',
      render: (exec) => <span className="text-slate-700">{humanize(exec.trigger)}</span>,
    },
    {
      key: 'triggered_at',
      title: 'Triggered at',
      render: (exec) => <span className="text-slate-500">{formatDateTime(exec.triggered_at)}</span>,
    },
    {
      key: 'status',
      title: 'Status',
      render: (exec) => (
        <Badge variant={statusVariant(exec.status)} size="sm" dot>
          {humanize(exec.status)}
        </Badge>
      ),
    },
    {
      key: 'result',
      title: 'Result / error',
      render: (exec) =>
        exec.status === 'failed' ? (
          <p className="text-xs text-rose-600 max-w-md truncate">{exec.error ?? 'Unknown error'}</p>
        ) : (
          <pre className="text-[11px] text-slate-500 bg-slate-50 border border-slate-100 rounded px-1.5 py-1 max-w-md overflow-hidden text-ellipsis whitespace-nowrap">
            {resultPreview(exec.result)}
          </pre>
        ),
    },
  ];

  return (
    <div className="space-y-5">
      {!canEdit && <ReadOnlyNotice what="automation rules" />}

      {/* Dashboard tiles */}
      {dashboard.isPending ? (
        <LoadingState message="Loading automation dashboard..." />
      ) : dashboard.isError ? (
        <ErrorState message={toApiError(dashboard.error).message} onRetry={() => void dashboard.refetch()} />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Tile icon={<CheckCircle2 className="w-4 h-4" />} label="Active rules" value={dashboard.data.active_rules} />
          <Tile icon={<PauseCircle className="w-4 h-4" />} label="Paused rules" value={dashboard.data.paused_rules} />
          <Tile icon={<XCircle className="w-4 h-4" />} label="Failed executions" value={dashboard.data.failed_executions} tone="danger" />
          <Tile
            icon={<Zap className="w-4 h-4" />}
            label="Success rate"
            value={
              dashboard.data.success_rate === null
                ? 'No executions yet'
                : `${(dashboard.data.success_rate * 100).toFixed(0)}%`
            }
          />
        </div>
      )}

      {/* Rules */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Rules</CardTitle>
            <p className="text-xs text-slate-500 mt-0.5">
              Automatically act when a billing event happens — no conditions means the rule always fires.
            </p>
          </div>
          {canEdit && (
            <Button size="sm" leadingIcon={<Plus className="w-4 h-4" />} onClick={() => setCreateOpen(true)}>
              Create rule
            </Button>
          )}
        </CardHeader>
        <CardContent className="p-0">
          {rules.isPending ? (
            <LoadingState message="Loading rules..." />
          ) : rules.isError ? (
            <ErrorState message={toApiError(rules.error).message} onRetry={() => void rules.refetch()} />
          ) : (
            <div className="p-0">
              <DataTable
                columns={ruleColumns}
                data={rules.data.items}
                keyExtractor={(r) => r.id}
                emptyMessage="No automation rules yet"
                emptySubtext={canEdit ? 'Create your first rule to automate a repetitive action.' : 'No rules have been created yet.'}
                page={rules.data.page}
                pageSize={rules.data.page_size}
                total={rules.data.total}
                onPageChange={setRulesPage}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Execution history */}
      <Card>
        <CardHeader className="block">
          <CardTitle>Execution history</CardTitle>
          <p className="text-xs text-slate-500 mt-0.5">Every time a rule fired, whether it succeeded, and why it failed.</p>
        </CardHeader>
        <CardContent className="p-0">
          {executions.isPending ? (
            <LoadingState message="Loading executions..." />
          ) : executions.isError ? (
            <ErrorState message={toApiError(executions.error).message} onRetry={() => void executions.refetch()} />
          ) : (
            <DataTable
              columns={executionColumns}
              data={executions.data.items}
              keyExtractor={(e) => e.id}
              emptyMessage="No executions yet"
              emptySubtext="Executions appear here once a rule's trigger fires."
              page={executions.data.page}
              pageSize={executions.data.page_size}
              total={executions.data.total}
              onPageChange={setExecutionsPage}
            />
          )}
        </CardContent>
      </Card>

      {canEdit && (
        <CreateRuleModal
          isOpen={createOpen}
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            invalidateAll();
          }}
        />
      )}

      <ConfirmDialog
        isOpen={ruleToDelete !== null}
        onClose={() => setRuleToDelete(null)}
        onConfirm={() => {
          if (ruleToDelete) deleteMutation.mutate(ruleToDelete.id);
        }}
        title="Delete this rule?"
        description={ruleToDelete ? `"${ruleToDelete.name}" will stop firing immediately. This cannot be undone.` : undefined}
        confirmLabel="Delete rule"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}

function Tile({
  icon,
  label,
  value,
  tone = 'default',
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  tone?: 'default' | 'danger';
}) {
  return (
    <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-card">
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500 uppercase tracking-wide">
        <span className={tone === 'danger' ? 'text-rose-500' : 'text-brand-600'}>{icon}</span>
        {label}
      </div>
      <div className={`mt-2 text-xl font-bold tracking-tight ${tone === 'danger' && typeof value === 'number' && value > 0 ? 'text-rose-600' : 'text-slate-900'}`}>
        {value}
      </div>
    </div>
  );
}

function CreateRuleModal({
  isOpen,
  onClose,
  onCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { showToast } = useToast();
  const [name, setName] = useState('');
  const [trigger, setTrigger] = useState<AutomationTrigger>('invoice_overdue');
  const [conditions, setConditions] = useState<ConditionRow[]>([]);
  const [actions, setActions] = useState<ActionRow[]>([emptyActionRow()]);
  const [formError, setFormError] = useState<string | null>(null);

  const reset = () => {
    setName('');
    setTrigger('invoice_overdue');
    setConditions([]);
    setActions([emptyActionRow()]);
    setFormError(null);
  };

  const mutation = useMutation({
    mutationFn: automationService.createRule,
    onSuccess: (rule) => {
      showToast('success', 'Rule created', `"${rule.name}" is now active.`);
      reset();
      onCreated();
    },
    onError: (err) => {
      setFormError(toApiError(err).message);
    },
  });

  const handleClose = () => {
    if (mutation.isPending) return;
    reset();
    onClose();
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!name.trim()) {
      setFormError('Name is required.');
      return;
    }
    if (actions.length === 0) {
      setFormError('At least one action is required.');
      return;
    }

    const builtConditions: AutomationCondition[] = conditions
      .filter((c) => c.value.trim() !== '')
      .map((c) => ({
        field: c.field,
        op: c.op,
        value: NUMERIC_FIELDS.includes(c.field) && !Number.isNaN(Number(c.value)) ? Number(c.value) : c.value,
      }));

    const builtActions: AutomationAction[] = actions.map((a) => {
      const params: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(a.params)) {
        if (value.trim() !== '') params[key] = value;
      }
      return { action: a.action, params: Object.keys(params).length > 0 ? params : undefined };
    });

    mutation.mutate({ name: name.trim(), trigger, conditions: builtConditions, actions: builtActions });
  };

  const addCondition = () => setConditions((prev) => [...prev, emptyConditionRow()]);
  const removeCondition = (index: number) => setConditions((prev) => prev.filter((_, i) => i !== index));
  const updateCondition = (index: number, patch: Partial<ConditionRow>) =>
    setConditions((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const addAction = () => setActions((prev) => [...prev, emptyActionRow()]);
  const removeAction = (index: number) => setActions((prev) => prev.filter((_, i) => i !== index));
  const updateAction = (index: number, patch: Partial<ActionRow>) =>
    setActions((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const updateActionParam = (index: number, key: string, value: string) =>
    setActions((prev) =>
      prev.map((row, i) => (i === index ? { ...row, params: { ...row.params, [key]: value } } : row))
    );

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Create automation rule"
      description="Fires the chosen actions whenever the trigger event happens and every condition matches."
      size="lg"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={handleClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button size="sm" onClick={onSubmit} isLoading={mutation.isPending}>
            Create rule
          </Button>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {formError && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-700">
            {formError}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="Name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Nudge on 7-day overdue"
          />
          <Select
            label="Trigger"
            required
            value={trigger}
            onChange={(e) => setTrigger(e.target.value as AutomationTrigger)}
            options={TRIGGERS.map((t) => ({ value: t.value, label: t.label }))}
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-700">Conditions</span>
            <Button type="button" variant="ghost" size="sm" leadingIcon={<Plus className="w-3.5 h-3.5" />} onClick={addCondition}>
              Add condition
            </Button>
          </div>
          {conditions.length === 0 ? (
            <p className="text-xs text-slate-400 italic">No conditions — this rule fires on every {humanize(trigger).toLowerCase()} event.</p>
          ) : (
            <div className="space-y-2">
              {conditions.map((row, i) => (
                <div key={i} className="flex items-start gap-2">
                  <Select
                    aria-label="Condition field"
                    value={row.field}
                    onChange={(e) => updateCondition(i, { field: e.target.value as AutomationConditionField })}
                    options={CONDITION_FIELDS.map((f) => ({ value: f.value, label: f.label }))}
                    className="w-40 shrink-0"
                  />
                  <Select
                    aria-label="Condition operator"
                    value={row.op}
                    onChange={(e) => updateCondition(i, { op: e.target.value as AutomationConditionOp })}
                    options={CONDITION_OPS.map((o) => ({ value: o.value, label: o.label }))}
                    className="w-48 shrink-0"
                  />
                  <Input
                    aria-label="Condition value"
                    value={row.value}
                    onChange={(e) => updateCondition(i, { value: e.target.value })}
                    placeholder="Value"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removeCondition(i)}
                    aria-label="Remove condition"
                    leadingIcon={<Trash2 className="w-3.5 h-3.5 text-rose-500" />}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-700">
              Actions<span className="text-rose-500 ml-0.5">*</span>
            </span>
            <Button type="button" variant="ghost" size="sm" leadingIcon={<Plus className="w-3.5 h-3.5" />} onClick={addAction}>
              Add action
            </Button>
          </div>
          <div className="space-y-3">
            {actions.map((row, i) => (
              <div key={i} className="rounded-lg border border-slate-200 p-3 space-y-2.5">
                <div className="flex items-center gap-2">
                  <Select
                    aria-label="Action type"
                    value={row.action}
                    onChange={(e) => updateAction(i, { action: e.target.value as AutomationActionType, params: {} })}
                    options={ACTION_TYPES.map((a) => ({ value: a.value, label: a.label }))}
                    className="flex-1"
                  />
                  {actions.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => removeAction(i)}
                      aria-label="Remove action"
                      leadingIcon={<Trash2 className="w-3.5 h-3.5 text-rose-500" />}
                    />
                  )}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {ACTION_PARAM_FIELDS[row.action].map((field) => (
                    <Input
                      key={field.key}
                      aria-label={field.label}
                      label={field.label}
                      value={row.params[field.key] ?? ''}
                      onChange={(e) => updateActionParam(i, field.key, e.target.value)}
                      placeholder={field.placeholder}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </form>
    </Modal>
  );
}

export default AutomationTab;
