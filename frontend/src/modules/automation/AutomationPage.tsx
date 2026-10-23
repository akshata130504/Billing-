import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Workflow,
  RefreshCw,
  Plus,
  Zap,
  CalendarClock,
  Activity,
  CheckCircle2,
  XCircle,
  Search,
  Pencil,
  Trash2,
  FlaskConical,
  Play,
  ChevronDown,
  ChevronRight,
  Mail,
  Webhook,
  PenLine,
  ScrollText,
} from 'lucide-react';
import { automationService } from '../../services/automationService';
import type {
  AutomationAction,
  AutomationLog,
  AutomationLogStatus,
  AutomationRule,
  AutomationSchedule,
} from '../../types/automation';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { StatCard } from '../../components/common/StatCard';
import { LoadingState } from '../../components/common/LoadingState';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime, formatRelative, humanize } from '../../utils/format';
import { cn } from '../../utils/cn';
import { RuleEditorModal } from './RuleEditorModal';
import { RuleTestModal } from './RuleTestModal';
import { ScheduleEditorModal } from './ScheduleEditorModal';
import { usePageSpec } from '../../appUi/usePageSpec';
import {
  ACTION_TYPE_LABELS,
  FREQUENCY_LABELS,
  LOG_ACTION_TYPE_LABELS,
  LOG_STATUS_LABELS,
  LOG_STATUS_VARIANT,
  MODULE_OPTIONS,
  TRIGGER_EVENT_LABELS,
  asUtc,
  describeConditions,
  isToday,
} from './constants';

type Tab = 'rules' | 'schedules' | 'logs';

const FILTER_SELECT_CLS =
  'px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500';

const LOGS_LIMIT = 500;

// ---------------------------------------------------------------------------
// Small presentational helpers
// ---------------------------------------------------------------------------

function ToggleSwitch({
  checked,
  disabled,
  busy,
  onChange,
  label,
}: {
  checked: boolean;
  disabled?: boolean;
  busy?: boolean;
  onChange: (next: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled || busy}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1',
        checked ? 'bg-emerald-500' : 'bg-slate-300',
        (disabled || busy) && 'opacity-60 cursor-not-allowed'
      )}
    >
      <span
        className={cn(
          'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
          checked ? 'translate-x-4' : 'translate-x-0'
        )}
      />
    </button>
  );
}

function ActionIcon({ type }: { type: string }) {
  const cls = 'w-3.5 h-3.5';
  if (type === 'email_alert') return <Mail className={cls} />;
  if (type === 'webhook') return <Webhook className={cls} />;
  if (type === 'field_update') return <PenLine className={cls} />;
  return <Zap className={cls} />;
}

function ActionsSummary({ actions }: { actions: AutomationAction[] }) {
  if (actions.length === 0) return <span className="text-xs italic text-slate-400">No actions</span>;
  const sorted = [...actions].sort((a, b) => a.execution_order - b.execution_order);
  return (
    <div className="flex flex-wrap gap-1.5">
      {sorted.map((a) => (
        <span
          key={a.id}
          title={a.name}
          className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700"
        >
          <ActionIcon type={a.action_type} />
          {ACTION_TYPE_LABELS[a.action_type] ?? humanize(a.action_type)}
        </span>
      ))}
    </div>
  );
}

function shortId(id: string | null): string {
  if (!id) return '';
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

function summarizeDetails(details: Record<string, unknown> | null): string {
  if (!details) return '';
  const parts: string[] = [];
  Object.entries(details).forEach(([k, v]) => {
    if (v === null || v === undefined) return;
    if (typeof v === 'object') return;
    parts.push(`${humanize(k)}: ${String(v)}`);
  });
  return parts.slice(0, 3).join(' · ');
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function AutomationPage() {
  const ui = usePageSpec('automation');
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canManage = hasRole('admin');
  const canTrigger = hasRole('finance');

  const [activeTab, setActiveTab] = useState<Tab>('rules');

  // Data
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [revealedSecrets, setRevealedSecrets] = useState<{ name: string; secret: string }[] | null>(null);
  const [schedules, setSchedules] = useState<AutomationSchedule[]>([]);
  const [allLogs, setAllLogs] = useState<AutomationLog[]>([]);
  const [logs, setLogs] = useState<AutomationLog[]>([]);

  // Page-level state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Logs tab state
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [logStatus, setLogStatus] = useState<'all' | AutomationLogStatus>('all');
  const [logEntityType, setLogEntityType] = useState<string>('all');
  const [expandedLogId, setExpandedLogId] = useState<string | null>(null);

  // Filters
  const [ruleSearch, setRuleSearch] = useState('');
  const [ruleModule, setRuleModule] = useState('all');
  const [scheduleSearch, setScheduleSearch] = useState('');

  // Modals / busy flags
  const [ruleModal, setRuleModal] = useState<{ open: boolean; rule: AutomationRule | null }>({ open: false, rule: null });
  const [testRule, setTestRule] = useState<AutomationRule | null>(null);
  const [scheduleModal, setScheduleModal] = useState<{ open: boolean; schedule: AutomationSchedule | null }>({
    open: false,
    schedule: null,
  });
  const [deleteTarget, setDeleteTarget] = useState<
    | { kind: 'rule'; item: AutomationRule }
    | { kind: 'schedule'; item: AutomationSchedule }
    | null
  >(null);
  const [deleting, setDeleting] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  // --- Loading -------------------------------------------------------------
  const loadAll = useCallback(
    async (opts: { silent?: boolean } = {}) => {
      if (opts.silent) setRefreshing(true);
      else setLoading(true);
      setError(null);
      try {
        const [rulesData, schedulesData, logsData] = await Promise.all([
          automationService.listRules(),
          automationService.listSchedules(),
          automationService.listLogs({ limit: LOGS_LIMIT }),
        ]);
        setRules(rulesData);
        setSchedules(schedulesData);
        setAllLogs(logsData);
      } catch (err: any) {
        setError(err?.message || 'Failed to load automation data');
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    []
  );

  const loadLogs = useCallback(async () => {
    setLogsLoading(true);
    setLogsError(null);
    try {
      const data = await automationService.listLogs({
        status: logStatus === 'all' ? undefined : logStatus,
        entity_type: logEntityType === 'all' ? undefined : logEntityType,
        limit: LOGS_LIMIT,
      });
      setLogs(data);
    } catch (err: any) {
      setLogsError(err?.message || 'Failed to load automation logs');
    } finally {
      setLogsLoading(false);
    }
  }, [logStatus, logEntityType]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (activeTab === 'logs') loadLogs();
  }, [activeTab, loadLogs]);

  const refreshEverything = useCallback(async () => {
    await loadAll({ silent: true });
    if (activeTab === 'logs') await loadLogs();
  }, [loadAll, loadLogs, activeTab]);

  // --- Derived ------------------------------------------------------------
  const stats = useMemo(() => {
    const activeRules = rules.filter((r) => r.is_active).length;
    const activeSchedules = schedules.filter((s) => s.is_active && s.status === 'active').length;
    const today = allLogs.filter((l) => isToday(l.occurred_at));
    const successToday = today.filter((l) => l.status === 'success').length;
    const failedToday = today.filter((l) => l.status === 'failed').length;
    return { activeRules, activeSchedules, runsToday: today.length, successToday, failedToday };
  }, [rules, schedules, allLogs]);

  const lastRunByName = useMemo(() => {
    // Logs are newest-first; the first hit per name is the most recent run.
    const map = new Map<string, AutomationLog>();
    allLogs.forEach((l) => {
      if (!map.has(l.name)) map.set(l.name, l);
    });
    return map;
  }, [allLogs]);

  const filteredRules = useMemo(() => {
    const q = ruleSearch.trim().toLowerCase();
    return rules.filter((r) => {
      if (ruleModule !== 'all' && r.module !== ruleModule) return false;
      if (!q) return true;
      return (
        r.name.toLowerCase().includes(q) ||
        (r.description ?? '').toLowerCase().includes(q) ||
        r.module.toLowerCase().includes(q)
      );
    });
  }, [rules, ruleSearch, ruleModule]);

  const filteredSchedules = useMemo(() => {
    const q = scheduleSearch.trim().toLowerCase();
    if (!q) return schedules;
    return schedules.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.target_action.toLowerCase().includes(q) ||
        (s.description ?? '').toLowerCase().includes(q)
    );
  }, [schedules, scheduleSearch]);

  const ruleModuleOptions = useMemo(() => {
    const known = new Set(MODULE_OPTIONS.map((o) => o.value));
    const extras = Array.from(new Set(rules.map((r) => r.module))).filter((m) => !known.has(m));
    return [...MODULE_OPTIONS, ...extras.map((m) => ({ value: m, label: humanize(m) }))];
  }, [rules]);

  const entityTypeOptions = useMemo(
    () => Array.from(new Set(allLogs.map((l) => l.entity_type))).sort(),
    [allLogs]
  );

  // --- Mutations -----------------------------------------------------------
  const handleToggleRule = async (rule: AutomationRule, next: boolean) => {
    setBusyId(rule.id);
    try {
      const updated = await automationService.updateRule(rule.id, { is_active: next });
      setRules((list) => list.map((r) => (r.id === updated.id ? updated : r)));
      showToast('success', next ? 'Rule enabled' : 'Rule paused', `"${updated.name}" is now ${next ? 'active' : 'paused'}.`);
    } catch (err: any) {
      showToast('error', 'Could not update rule', err?.message);
    } finally {
      setBusyId(null);
    }
  };

  const handleToggleSchedule = async (schedule: AutomationSchedule, next: boolean) => {
    setBusyId(schedule.id);
    try {
      const updated = await automationService.updateSchedule(schedule.id, {
        is_active: next,
        status: next ? 'active' : 'paused',
      });
      setSchedules((list) => list.map((s) => (s.id === updated.id ? updated : s)));
      showToast('success', next ? 'Schedule enabled' : 'Schedule paused', `"${updated.name}" is now ${next ? 'active' : 'paused'}.`);
    } catch (err: any) {
      showToast('error', 'Could not update schedule', err?.message);
    } finally {
      setBusyId(null);
    }
  };

  const handleTrigger = async (schedule: AutomationSchedule) => {
    setBusyId(schedule.id);
    try {
      const res = await automationService.triggerSchedule(schedule.id);
      showToast('success', 'Schedule triggered', `${humanize(res.target_action)} ran at ${formatDateTime(asUtc(res.executed_at))}.`);
      await refreshEverything();
    } catch (err: any) {
      showToast('error', 'Could not trigger schedule', err?.message);
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      if (deleteTarget.kind === 'rule') {
        await automationService.deleteRule(deleteTarget.item.id);
        setRules((list) => list.filter((r) => r.id !== deleteTarget.item.id));
        showToast('success', 'Rule deleted', `"${deleteTarget.item.name}" has been removed.`);
      } else {
        await automationService.deleteSchedule(deleteTarget.item.id);
        setSchedules((list) => list.filter((s) => s.id !== deleteTarget.item.id));
        showToast('success', 'Schedule deleted', `"${deleteTarget.item.name}" has been removed.`);
      }
      setDeleteTarget(null);
    } catch (err: any) {
      showToast('error', `Could not delete ${deleteTarget.kind}`, err?.message);
    } finally {
      setDeleting(false);
    }
  };

  const handleRuleSaved = (saved: AutomationRule) => {
    // Webhook signing secrets are returned only in the create response; show them once.
    const revealed = saved.revealed_signing_secrets;
    if (revealed && Object.keys(revealed).length > 0) {
      setRevealedSecrets(
        Object.entries(revealed).map(([actionId, secret]) => ({
          name: saved.actions.find((a) => a.id === actionId)?.name ?? actionId,
          secret,
        })),
      );
    }
    setRules((list) => {
      const exists = list.some((r) => r.id === saved.id);
      return exists ? list.map((r) => (r.id === saved.id ? saved : r)) : [saved, ...list];
    });
  };

  const handleScheduleSaved = (saved: AutomationSchedule) => {
    setSchedules((list) => {
      const exists = list.some((s) => s.id === saved.id);
      const next = exists ? list.map((s) => (s.id === saved.id ? saved : s)) : [...list, saved];
      return next.sort((a, b) => a.name.localeCompare(b.name));
    });
  };

  // --- Render helpers -------------------------------------------------------
  const primaryAction =
    activeTab === 'rules' ? (
      canManage && (
        <Button variant="primary" size="sm" onClick={() => setRuleModal({ open: true, rule: null })} leadingIcon={<Plus className="w-4 h-4" />}>
          New rule
        </Button>
      )
    ) : activeTab === 'schedules' ? (
      canManage && (
        <Button
          variant="primary"
          size="sm"
          onClick={() => setScheduleModal({ open: true, schedule: null })}
          leadingIcon={<Plus className="w-4 h-4" />}
        >
          New schedule
        </Button>
      )
    ) : null;

  const renderRulesTable = () => {
    if (rules.length === 0) {
      return (
        <div {...ui.edit('empty')}>
          <EmptyState
            icon={<Zap className="w-8 h-8 text-slate-400" />}
            title={ui.text('empty', 'none')}
            description="Rules react to billing events — overdue invoices, failed payments, status changes — and run alerts, webhooks or field updates automatically."
            action={
              canManage ? (
                <Button variant="primary" size="sm" onClick={() => setRuleModal({ open: true, rule: null })} leadingIcon={<Plus className="w-4 h-4" />}>
                  Create your first rule
                </Button>
              ) : undefined
            }
          />
        </div>
      );
    }
    if (filteredRules.length === 0) {
      return (
        <EmptyState
          icon={<Search className="w-8 h-8 text-slate-400" />}
          title="No rules match"
          description="Try a different search term or module filter."
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setRuleSearch('');
                setRuleModule('all');
              }}
            >
              Clear filters
            </Button>
          }
        />
      );
    }
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-slate-600">
          <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
            <tr {...ui.edit('columns')}>
              {ui.shown('columns').map((col) => (
                <th
                  key={col.key}
                  className={`px-5 py-3.5 ${col.key === 'manage' ? 'text-right' : ''}`}
                  {...ui.edit(`columns.${col.key}`)}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredRules.map((rule) => {
              const conditions = describeConditions(rule.conditions);
              const lastRun = lastRunByName.get(rule.name);
              return (
                <tr key={rule.id} className="hover:bg-slate-50/70 transition-colors">
                  {ui.shown('columns').map((col) => {
                    if (col.key === 'rule') {
                      return (
                        <td key="rule" className="px-5 py-4 max-w-xs">
                          <div className="font-semibold text-slate-900 truncate">{rule.name}</div>
                          {rule.description && <div className="text-xs text-slate-400 mt-0.5 truncate">{rule.description}</div>}
                        </td>
                      );
                    }
                    if (col.key === 'trigger') {
                      return (
                        <td key="trigger" className="px-5 py-4">
                          <div className="flex flex-col gap-1">
                            <Badge variant="info" size="sm">
                              {humanize(rule.module)}
                            </Badge>
                            <span className="text-xs text-slate-600">{TRIGGER_EVENT_LABELS[rule.trigger_event] ?? humanize(rule.trigger_event)}</span>
                          </div>
                        </td>
                      );
                    }
                    if (col.key === 'conditions') {
                      return (
                        <td key="conditions" className="px-5 py-4 max-w-xs">
                          {conditions.length === 0 ? (
                            <span className="text-xs italic text-slate-400">Any event</span>
                          ) : (
                            <div className="flex flex-wrap gap-1">
                              {conditions.slice(0, 2).map((c) => (
                                <code key={c} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">
                                  {c}
                                </code>
                              ))}
                              {conditions.length > 2 && (
                                <span className="text-[11px] text-slate-400">+{conditions.length - 2} more</span>
                              )}
                            </div>
                          )}
                        </td>
                      );
                    }
                    if (col.key === 'actions') {
                      return (
                        <td key="actions" className="px-5 py-4">
                          <ActionsSummary actions={rule.actions} />
                        </td>
                      );
                    }
                    if (col.key === 'enabled') {
                      return (
                        <td key="enabled" className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <ToggleSwitch
                              checked={rule.is_active}
                              disabled={!canManage}
                              busy={busyId === rule.id}
                              onChange={(next) => handleToggleRule(rule, next)}
                              label={`Toggle rule ${rule.name}`}
                            />
                            <span className={cn('text-xs font-medium', rule.is_active ? 'text-emerald-700' : 'text-slate-400')}>
                              {rule.is_active ? 'On' : 'Off'}
                            </span>
                          </div>
                        </td>
                      );
                    }
                    if (col.key === 'last_run') {
                      return (
                        <td key="last_run" className="px-5 py-4 text-xs whitespace-nowrap">
                          {lastRun ? (
                            <div className="flex flex-col gap-0.5">
                              <span className="text-slate-700" title={formatDateTime(asUtc(lastRun.occurred_at))}>
                                {formatRelative(asUtc(lastRun.occurred_at))}
                              </span>
                              <Badge variant={LOG_STATUS_VARIANT[lastRun.status]} size="sm">
                                {LOG_STATUS_LABELS[lastRun.status]}
                              </Badge>
                            </div>
                          ) : (
                            <span className="italic text-slate-400">Never</span>
                          )}
                        </td>
                      );
                    }
                    if (col.key === 'manage') {
                      return (
                        <td key="manage" className="px-5 py-4 text-right">
                          <div className="flex items-center justify-end gap-1">
                            {canManage && (
                              <>
                                <Button variant="ghost" size="sm" className="text-xs" onClick={() => setTestRule(rule)} leadingIcon={<FlaskConical className="w-3.5 h-3.5" />}>
                                  Test
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="text-xs"
                                  onClick={() => setRuleModal({ open: true, rule })}
                                  leadingIcon={<Pencil className="w-3.5 h-3.5" />}
                                >
                                  Edit
                                </Button>
                                <button
                                  type="button"
                                  onClick={() => setDeleteTarget({ kind: 'rule', item: rule })}
                                  className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                                  aria-label={`Delete rule ${rule.name}`}
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </>
                            )}
                            {!canManage && <span className="text-xs text-slate-400">View only</span>}
                          </div>
                        </td>
                      );
                    }
                    return null;
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  const renderSchedulesTable = () => {
    if (schedules.length === 0) {
      return (
        <EmptyState
          icon={<CalendarClock className="w-8 h-8 text-slate-400" />}
          title="No schedules yet"
          description="Schedules run recurring jobs such as billing runs or report exports on an hourly, daily, weekly or monthly cadence."
          action={
            canManage ? (
              <Button
                variant="primary"
                size="sm"
                onClick={() => setScheduleModal({ open: true, schedule: null })}
                leadingIcon={<Plus className="w-4 h-4" />}
              >
                Create your first schedule
              </Button>
            ) : undefined
          }
        />
      );
    }
    if (filteredSchedules.length === 0) {
      return (
        <EmptyState
          icon={<Search className="w-8 h-8 text-slate-400" />}
          title="No schedules match"
          description="Try a different search term."
          action={
            <Button variant="outline" size="sm" onClick={() => setScheduleSearch('')}>
              Clear search
            </Button>
          }
        />
      );
    }
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-slate-600">
          <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
            <tr>
              <th className="px-5 py-3.5">Schedule</th>
              <th className="px-5 py-3.5">Frequency</th>
              <th className="px-5 py-3.5">Target action</th>
              <th className="px-5 py-3.5">Next run</th>
              <th className="px-5 py-3.5">Last run</th>
              <th className="px-5 py-3.5">Enabled</th>
              <th className="px-5 py-3.5 text-right">Manage</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredSchedules.map((schedule) => {
              const enabled = schedule.is_active && schedule.status === 'active';
              const busy = busyId === schedule.id;
              return (
                <tr key={schedule.id} className="hover:bg-slate-50/70 transition-colors">
                  <td className="px-5 py-4 max-w-xs">
                    <div className="font-semibold text-slate-900 truncate">{schedule.name}</div>
                    {schedule.description && (
                      <div className="text-xs text-slate-400 mt-0.5 truncate">{schedule.description}</div>
                    )}
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex flex-col gap-0.5">
                      <span className="font-medium text-slate-700">{FREQUENCY_LABELS[schedule.frequency] ?? humanize(schedule.frequency)}</span>
                      {schedule.cron_expression && (
                        <code className="font-mono text-[11px] text-slate-500">{schedule.cron_expression}</code>
                      )}
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">
                      {schedule.target_action}
                    </code>
                  </td>
                  <td className="px-5 py-4 text-xs whitespace-nowrap">
                    {schedule.next_date && enabled ? (
                      <div className="flex flex-col gap-0.5">
                        <span className="text-slate-700">{formatDateTime(asUtc(schedule.next_date))}</span>
                        <span className="text-slate-400">{formatRelative(asUtc(schedule.next_date))}</span>
                      </div>
                    ) : (
                      <span className="italic text-slate-400">{enabled ? 'Not scheduled' : 'Paused'}</span>
                    )}
                  </td>
                  <td className="px-5 py-4 text-xs whitespace-nowrap">
                    {schedule.last_executed_on ? (
                      <span className="text-slate-700" title={formatDateTime(asUtc(schedule.last_executed_on))}>
                        {formatRelative(asUtc(schedule.last_executed_on))}
                      </span>
                    ) : (
                      <span className="italic text-slate-400">Never</span>
                    )}
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <ToggleSwitch
                        checked={enabled}
                        disabled={!canManage}
                        busy={busy}
                        onChange={(next) => handleToggleSchedule(schedule, next)}
                        label={`Toggle schedule ${schedule.name}`}
                      />
                      <span className={cn('text-xs font-medium', enabled ? 'text-emerald-700' : 'text-slate-400')}>
                        {enabled ? 'On' : 'Off'}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {canTrigger && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-xs"
                          disabled={!enabled || busy}
                          isLoading={busy}
                          onClick={() => handleTrigger(schedule)}
                          leadingIcon={<Play className="w-3.5 h-3.5" />}
                          title={enabled ? 'Run this schedule now' : 'Enable the schedule to run it'}
                        >
                          Run now
                        </Button>
                      )}
                      {canManage && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-xs"
                            onClick={() => setScheduleModal({ open: true, schedule })}
                            leadingIcon={<Pencil className="w-3.5 h-3.5" />}
                          >
                            Edit
                          </Button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget({ kind: 'schedule', item: schedule })}
                            className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                            aria-label={`Delete schedule ${schedule.name}`}
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </>
                      )}
                      {!canManage && !canTrigger && <span className="text-xs text-slate-400">View only</span>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  const renderLogsTable = () => {
    if (logsLoading) {
      return (
        <div className="py-16">
          <LoadingState message="Loading automation logs..." />
        </div>
      );
    }
    if (logsError) {
      return <ErrorState title="Could not load logs" message={logsError} onRetry={loadLogs} />;
    }
    if (logs.length === 0) {
      const filtered = logStatus !== 'all' || logEntityType !== 'all';
      return (
        <EmptyState
          icon={<ScrollText className="w-8 h-8 text-slate-400" />}
          title={filtered ? 'No logs match these filters' : 'No automation activity yet'}
          description={
            filtered
              ? 'Try widening the status or entity filters.'
              : 'Every rule evaluation, action and schedule run is recorded here. Trigger a schedule or wait for a rule to fire to see entries.'
          }
          action={
            filtered ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setLogStatus('all');
                  setLogEntityType('all');
                }}
              >
                Clear filters
              </Button>
            ) : schedules.length === 0 && canManage ? (
              <Button variant="primary" size="sm" onClick={() => setActiveTab('schedules')}>
                Set up a schedule
              </Button>
            ) : undefined
          }
        />
      );
    }
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-slate-600">
          <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
            <tr>
              <th className="px-3 py-3.5 w-8" />
              <th className="px-5 py-3.5">Time</th>
              <th className="px-5 py-3.5">Rule / Schedule</th>
              <th className="px-5 py-3.5">Event</th>
              <th className="px-5 py-3.5">Status</th>
              <th className="px-5 py-3.5">Message</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {logs.map((log) => {
              const expanded = expandedLogId === log.id;
              const message = log.error_message || summarizeDetails(log.details);
              return (
                <React.Fragment key={log.id}>
                  <tr
                    className={cn('hover:bg-slate-50/70 transition-colors cursor-pointer', expanded && 'bg-slate-50/70')}
                    onClick={() => setExpandedLogId(expanded ? null : log.id)}
                  >
                    <td className="px-3 py-4 text-slate-400">
                      {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </td>
                    <td className="px-5 py-4 text-xs whitespace-nowrap">
                      <div className="text-slate-700">{formatDateTime(asUtc(log.occurred_at))}</div>
                      <div className="text-slate-400">{formatRelative(asUtc(log.occurred_at))}</div>
                    </td>
                    <td className="px-5 py-4 max-w-xs">
                      <div className="font-semibold text-slate-900 truncate">{log.name}</div>
                      <div className="text-xs text-slate-400 mt-0.5">
                        {LOG_ACTION_TYPE_LABELS[log.action_type] ?? humanize(log.action_type)}
                      </div>
                    </td>
                    <td className="px-5 py-4 text-xs">
                      <div className="text-slate-700">{humanize(log.entity_type)}</div>
                      {log.entity_id && (
                        <code className="font-mono text-[11px] text-slate-400" title={log.entity_id}>
                          {shortId(log.entity_id)}
                        </code>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      <Badge variant={LOG_STATUS_VARIANT[log.status] ?? 'neutral'} dot>
                        {LOG_STATUS_LABELS[log.status] ?? humanize(log.status)}
                      </Badge>
                    </td>
                    <td className="px-5 py-4 max-w-md">
                      {message ? (
                        <span className={cn('text-xs truncate block', log.error_message ? 'text-rose-600' : 'text-slate-600')}>
                          {message}
                        </span>
                      ) : (
                        <span className="text-xs italic text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                  {expanded && (
                    <tr className="bg-slate-50/50">
                      <td colSpan={6} className="px-6 pb-5 pt-1">
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                          <div>
                            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Details</div>
                            {log.details && Object.keys(log.details).length > 0 ? (
                              <pre className="rounded-lg border border-slate-200 bg-white p-3 font-mono text-[11px] text-slate-700 overflow-x-auto max-h-64">
                                {JSON.stringify(log.details, null, 2)}
                              </pre>
                            ) : (
                              <div className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-2 text-xs italic text-slate-400">
                                No payload recorded
                              </div>
                            )}
                          </div>
                          <div className="space-y-3">
                            <div>
                              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Result</div>
                              {log.error_message ? (
                                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 break-words">
                                  {log.error_message}
                                </div>
                              ) : (
                                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
                                  {log.status === 'skipped' ? 'Skipped — conditions were not met.' : 'Completed without errors.'}
                                </div>
                              )}
                            </div>
                            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                              <dt className="text-slate-500">Log ID</dt>
                              <dd className="font-mono text-slate-700 truncate" title={log.id}>
                                {log.id}
                              </dd>
                              <dt className="text-slate-500">Entity ID</dt>
                              <dd className="font-mono text-slate-700 truncate" title={log.entity_id ?? ''}>
                                {log.entity_id ?? '—'}
                              </dd>
                              <dt className="text-slate-500">Occurred at</dt>
                              <dd className="text-slate-700">{formatDateTime(asUtc(log.occurred_at))}</dd>
                            </dl>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
        {logs.length >= LOGS_LIMIT && (
          <div className="px-5 py-3 border-t border-slate-100 text-xs text-slate-400">
            Showing the most recent {LOGS_LIMIT} entries. Narrow the filters to see older activity.
          </div>
        )}
      </div>
    );
  };

  // --- Page ------------------------------------------------------------------
  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4" {...ui.edit('header')}>
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-1">
            <Workflow className="w-4 h-4" />
            {ui.text('header', 'eyebrow')}
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            {ui.text('header', 'title')}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {ui.text('header', 'subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={refreshEverything} isLoading={refreshing} leadingIcon={<RefreshCw className="w-4 h-4" />}>
            Refresh
          </Button>
          {primaryAction}
        </div>
      </div>

      {loading ? (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm py-16">
          <LoadingState message="Loading automation..." />
        </div>
      ) : error ? (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <ErrorState title="Could not load automation" message={error} onRetry={() => loadAll()} />
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" {...ui.edit('kpis')}>
            {ui.render('kpis', {
              active_rules: (item, edit) => (
                <div key="active_rules" {...edit}>
                  <StatCard
                    title={item.label}
                    value={stats.activeRules}
                    comparisonText={`${rules.length} total`}
                    icon={<Zap className="w-4 h-4" />}
                  />
                </div>
              ),
              active_schedules: (item, edit) => (
                <div key="active_schedules" {...edit}>
                  <StatCard
                    title={item.label}
                    value={stats.activeSchedules}
                    comparisonText={`${schedules.length} total`}
                    icon={<CalendarClock className="w-4 h-4" />}
                  />
                </div>
              ),
              runs_today: (item, edit) => (
                <div key="runs_today" {...edit}>
                  <StatCard
                    title={item.label}
                    value={stats.runsToday}
                    comparisonText={`${allLogs.length} in recent history`}
                    icon={<Activity className="w-4 h-4" />}
                  />
                </div>
              ),
              success_rate: (item, edit) => (
                <div key="success_rate" {...edit}>
                  <StatCard
                    title={item.label}
                    value={`${stats.successToday} / ${stats.failedToday}`}
                    change={stats.failedToday > 0 ? `${stats.failedToday} failed` : stats.runsToday > 0 ? 'All succeeded' : undefined}
                    isPositive={stats.failedToday === 0}
                    icon={stats.failedToday > 0 ? <XCircle className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                  />
                </div>
              ),
            })}
          </div>

          {/* Tabs & filters */}
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center bg-slate-100 p-1 rounded-lg border border-slate-200 w-fit" {...ui.edit('tabs')}>
                {ui.shown('tabs').map((tab) => {
                  const count = tab.key === 'rules' ? rules.length : tab.key === 'schedules' ? schedules.length : allLogs.length;
                  return (
                    <button
                      key={tab.key}
                      type="button"
                      onClick={() => setActiveTab(tab.key as Tab)}
                      className={cn(
                        'px-3 py-1.5 text-xs font-semibold rounded-md transition-colors inline-flex items-center gap-1.5',
                        activeTab === tab.key ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                      )}
                      {...ui.edit(`tabs.${tab.key}`)}
                    >
                      {tab.label}
                      <span
                        className={cn(
                          'rounded-full px-1.5 py-0.5 text-[10px] font-semibold',
                          activeTab === tab.key ? 'bg-blue-50 text-blue-700' : 'bg-slate-200 text-slate-600'
                        )}
                      >
                        {count}
                      </span>
                    </button>
                  );
                })}
              </div>

              {activeTab === 'rules' && (
                <div className="flex flex-col sm:flex-row items-center gap-2 w-full md:w-auto">
                  <div className="relative flex-1 w-full sm:w-64">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input
                      type="text"
                      placeholder="Search rules..."
                      value={ruleSearch}
                      onChange={(e) => setRuleSearch(e.target.value)}
                      className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-colors"
                    />
                  </div>
                  <select value={ruleModule} onChange={(e) => setRuleModule(e.target.value)} className={FILTER_SELECT_CLS}>
                    <option value="all">All modules</option>
                    {ruleModuleOptions.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {activeTab === 'schedules' && (
                <div className="relative w-full md:w-72">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search schedules..."
                    value={scheduleSearch}
                    onChange={(e) => setScheduleSearch(e.target.value)}
                    className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-colors"
                  />
                </div>
              )}

              {activeTab === 'logs' && (
                <div className="flex items-center gap-2 w-full md:w-auto">
                  <select
                    value={logStatus}
                    onChange={(e) => setLogStatus(e.target.value as 'all' | AutomationLogStatus)}
                    className={FILTER_SELECT_CLS}
                  >
                    <option value="all">All statuses</option>
                    <option value="success">Success</option>
                    <option value="failed">Failed</option>
                    <option value="skipped">Skipped</option>
                  </select>
                  <select value={logEntityType} onChange={(e) => setLogEntityType(e.target.value)} className={FILTER_SELECT_CLS}>
                    <option value="all">All entities</option>
                    {entityTypeOptions.map((t) => (
                      <option key={t} value={t}>
                        {humanize(t)}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          </div>

          {/* Content */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            {activeTab === 'rules' && renderRulesTable()}
            {activeTab === 'schedules' && renderSchedulesTable()}
            {activeTab === 'logs' && renderLogsTable()}
          </div>
        </>
      )}

      {/* Modals */}
      <RuleEditorModal
        isOpen={ruleModal.open}
        rule={ruleModal.rule}
        onClose={() => setRuleModal({ open: false, rule: null })}
        onSaved={handleRuleSaved}
      />
      <Modal
        isOpen={revealedSecrets !== null}
        onClose={() => setRevealedSecrets(null)}
        title="Webhook signing secrets"
        description="Copy these now - they will not be shown again. Receivers verify X-Rooman-Signature = sha256=HMAC(secret, `${X-Rooman-Timestamp}.${raw body}`)."
        size="lg"
        footer={
          <Button type="button" onClick={() => setRevealedSecrets(null)}>
            I have saved them
          </Button>
        }
      >
        <ul className="space-y-3">
          {(revealedSecrets ?? []).map((item) => (
            <li key={item.name} className="rounded-lg border border-slate-200 p-3">
              <p className="text-xs font-medium text-slate-600 mb-1">{item.name}</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all rounded bg-slate-50 px-2 py-1 text-xs text-slate-800">{item.secret}</code>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    void navigator.clipboard?.writeText(item.secret);
                    showToast('success', 'Copied', 'Signing secret copied to clipboard.');
                  }}
                >
                  Copy
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </Modal>
      <RuleTestModal isOpen={testRule !== null} rule={testRule} onClose={() => setTestRule(null)} />
      <ScheduleEditorModal
        isOpen={scheduleModal.open}
        schedule={scheduleModal.schedule}
        onClose={() => setScheduleModal({ open: false, schedule: null })}
        onSaved={handleScheduleSaved}
      />
      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => (deleting ? undefined : setDeleteTarget(null))}
        onConfirm={handleDelete}
        title={deleteTarget?.kind === 'rule' ? 'Delete automation rule?' : 'Delete schedule?'}
        description={
          deleteTarget
            ? deleteTarget.kind === 'rule'
              ? `"${deleteTarget.item.name}" and its ${deleteTarget.item.actions.length} action(s) will be removed permanently. Past log entries are kept.`
              : `"${deleteTarget.item.name}" will stop running and be removed permanently. Past log entries are kept.`
            : undefined
        }
        confirmLabel="Delete"
        variant="danger"
        isLoading={deleting}
      />
    </div>
  );
}
