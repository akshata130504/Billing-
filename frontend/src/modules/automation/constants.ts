import type {
  AutomationActionType,
  AutomationConditions,
  AutomationLogStatus,
  AutomationTriggerEvent,
  ConditionClause,
  ConditionOperator,
  ConditionScalar,
  ConditionValue,
  ScheduleFrequency,
} from '../../types/automation';
import type { BadgeProps } from '../../components/common/Badge';

type BadgeVariant = NonNullable<BadgeProps['variant']>;

// --- Enum labels -----------------------------------------------------------

export const TRIGGER_EVENT_LABELS: Record<AutomationTriggerEvent, string> = {
  created: 'Record created',
  updated: 'Record updated',
  status_changed: 'Status changed',
  payment_failed: 'Payment failed',
  payment_succeeded: 'Payment succeeded',
  invoice_overdue: 'Invoice overdue',
};

export const TRIGGER_EVENT_OPTIONS = (Object.keys(TRIGGER_EVENT_LABELS) as AutomationTriggerEvent[]).map(
  (value) => ({ value, label: TRIGGER_EVENT_LABELS[value] })
);

export const ACTION_TYPE_LABELS: Record<AutomationActionType, string> = {
  email_alert: 'Email alert',
  webhook: 'Webhook',
  field_update: 'Field update',
};

export const ACTION_TYPE_OPTIONS = (Object.keys(ACTION_TYPE_LABELS) as AutomationActionType[]).map(
  (value) => ({ value, label: ACTION_TYPE_LABELS[value] })
);

/** Configuration keys read by customization_service.execute_automation_action. */
export const ACTION_CONFIG_FIELDS: Record<
  AutomationActionType,
  { key: string; label: string; placeholder: string; type?: 'text' | 'email' | 'url' | 'textarea'; required?: boolean }[]
> = {
  email_alert: [
    { key: 'recipient', label: 'Recipient', placeholder: 'Defaults to the customer email on the event', type: 'email' },
    { key: 'subject', label: 'Subject', placeholder: 'Automation Alert: <rule name>' },
    { key: 'body', label: 'Body', placeholder: 'Message body sent to the recipient', type: 'textarea' },
  ],
  webhook: [
    { key: 'url', label: 'Destination URL', placeholder: 'https://example.com/hooks/billing', type: 'url', required: true },
    { key: 'secret', label: 'Signing secret', placeholder: 'Leave blank to generate one (shown once after saving)' },
  ],
  field_update: [
    { key: 'field', label: 'Field', placeholder: 'notes (supported on invoices, customers, subscriptions)', required: true },
    { key: 'value', label: 'New value', placeholder: 'e.g. Flagged: payment at risk', required: true },
  ],
};

/** Modules the automation engine dispatches events for. */
export const MODULE_OPTIONS = [
  { value: 'invoice', label: 'Invoices' },
  { value: 'subscription', label: 'Subscriptions' },
  { value: 'customer', label: 'Customers' },
  { value: 'payment', label: 'Payments' },
  { value: 'quote', label: 'Quotes' },
];

export const FREQUENCY_LABELS: Record<ScheduleFrequency, string> = {
  hourly: 'Hourly',
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
};

export const FREQUENCY_OPTIONS = (Object.keys(FREQUENCY_LABELS) as ScheduleFrequency[]).map((value) => ({
  value,
  label: FREQUENCY_LABELS[value],
}));

/**
 * Target actions the backend can execute (customization_service.SCHEDULE_TARGET_ACTIONS).
 * run_billing_jobs is handled by the platform scheduler for every organization, so a manual
 * run is logged as "skipped" rather than a fake success.
 */
export const TARGET_ACTION_SUGGESTIONS = [
  { value: 'export_reports', label: 'Export month-to-date KPI snapshot' },
  { value: 'send_dunning_reminders', label: 'Run dunning retries & reminders' },
  { value: 'run_billing_jobs', label: 'Run billing jobs (platform-managed)' },
];

export const LOG_STATUS_LABELS: Record<AutomationLogStatus, string> = {
  success: 'Success',
  failed: 'Failed',
  skipped: 'Skipped',
};

export const LOG_STATUS_VARIANT: Record<AutomationLogStatus, BadgeVariant> = {
  success: 'success',
  failed: 'danger',
  skipped: 'neutral',
};

export const LOG_ACTION_TYPE_LABELS: Record<string, string> = {
  email_alert: 'Email alert',
  webhook: 'Webhook',
  field_update: 'Field update',
  schedule: 'Schedule',
  rule_evaluation: 'Rule evaluation',
  function: 'Function',
};

// --- Conditions <-> editable rows -----------------------------------------

export const OPERATOR_OPTIONS: { value: ConditionOperator; label: string }[] = [
  { value: 'eq', label: 'equals' },
  { value: 'neq', label: 'does not equal' },
  { value: 'gt', label: 'greater than' },
  { value: 'gte', label: 'greater or equal' },
  { value: 'lt', label: 'less than' },
  { value: 'lte', label: 'less or equal' },
  { value: 'in', label: 'is one of' },
];

export const OPERATOR_LABELS: Record<ConditionOperator, string> = OPERATOR_OPTIONS.reduce(
  (acc, o) => ({ ...acc, [o.value]: o.label }),
  {} as Record<ConditionOperator, string>
);

export const OPERATOR_SYMBOLS: Record<ConditionOperator, string> = {
  eq: '=',
  neq: '≠',
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
  in: 'in',
};

export interface ConditionRow {
  id: string;
  field: string;
  operator: ConditionOperator;
  /** Raw text as typed; parsed on save. Comma-separated for `in`. */
  value: string;
}

let rowSeq = 0;
export function newRowId(): string {
  rowSeq += 1;
  return `row-${Date.now()}-${rowSeq}`;
}

function isClause(v: unknown): v is ConditionClause {
  return typeof v === 'object' && v !== null && !Array.isArray(v) && 'operator' in v;
}

function scalarToText(v: ConditionScalar): string {
  if (v === null) return '';
  return String(v);
}

function valueToText(v: ConditionValue): string {
  if (Array.isArray(v)) return v.map(scalarToText).join(', ');
  return scalarToText(v);
}

/** Loose parsing: numbers and booleans become typed so `eq` matches event payloads. */
export function parseScalar(text: string): ConditionScalar {
  const t = text.trim();
  if (t === '') return '';
  if (t === 'true') return true;
  if (t === 'false') return false;
  if (t === 'null') return null;
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t);
  return t;
}

export function conditionsToRows(conditions: AutomationConditions | null | undefined): ConditionRow[] {
  if (!conditions) return [];
  return Object.entries(conditions).map(([field, raw]) => {
    if (isClause(raw)) {
      return { id: newRowId(), field, operator: raw.operator, value: valueToText(raw.value) };
    }
    return { id: newRowId(), field, operator: 'eq', value: valueToText(raw as ConditionValue) };
  });
}

export function rowsToConditions(rows: ConditionRow[]): AutomationConditions {
  const out: AutomationConditions = {};
  rows.forEach((row) => {
    const field = row.field.trim();
    if (!field) return;
    const value: ConditionValue =
      row.operator === 'in'
        ? row.value
            .split(',')
            .map((s) => s.trim())
            .filter((s) => s !== '')
            .map(parseScalar)
        : parseScalar(row.value);
    out[field] = { operator: row.operator, value };
  });
  return out;
}

/** Human-readable summary of a rule's conditions for table cells. */
export function describeConditions(conditions: AutomationConditions | null | undefined): string[] {
  return conditionsToRows(conditions).map((r) => `${r.field} ${OPERATOR_SYMBOLS[r.operator]} ${r.value || '""'}`);
}

/** Builds a sample event payload from a rule's conditions so tests start from a matching shape. */
export function sampleEventFromConditions(conditions: AutomationConditions | null | undefined): Record<string, unknown> {
  const sample: Record<string, unknown> = {};
  conditionsToRows(conditions).forEach((row) => {
    if (row.operator === 'in') {
      const first = row.value.split(',')[0] ?? '';
      sample[row.field] = parseScalar(first);
    } else {
      sample[row.field] = parseScalar(row.value);
    }
  });
  return sample;
}

// --- Timestamps -------------------------------------------------------------

/**
 * The API returns naive UTC timestamps (no `Z`) for most fields. JS parses
 * those as local time, so we pin them to UTC before formatting.
 */
export function asUtc(value: string | null | undefined): string | null {
  if (!value) return null;
  return /(Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
}

export function isToday(value: string | null | undefined): boolean {
  const iso = asUtc(value);
  if (!iso) return false;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
  );
}
