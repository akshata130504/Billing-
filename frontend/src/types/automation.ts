// ---------------------------------------------------------------------------
// Automation module types — mirrors backend/app/schemas/customization.py
// (AutomationRule*, AutomationAction*, AutomationLog*, AutomationSchedule*)
// ---------------------------------------------------------------------------

export type AutomationTriggerEvent =
  | 'created'
  | 'updated'
  | 'status_changed'
  | 'payment_failed'
  | 'payment_succeeded'
  | 'invoice_overdue';

export type AutomationActionType = 'email_alert' | 'webhook' | 'field_update';

export type AutomationLogStatus = 'success' | 'failed' | 'skipped';

export type ScheduleFrequency = 'hourly' | 'daily' | 'weekly' | 'monthly';

/** Backend stores this as a free string; only these two values are used. */
export type ScheduleStatus = 'active' | 'paused';

// --- Conditions ------------------------------------------------------------

/** Operators understood by customization_service._condition_matches. */
export type ConditionOperator = 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'in';

export type ConditionScalar = string | number | boolean | null;
export type ConditionValue = ConditionScalar | ConditionScalar[];

export interface ConditionClause {
  operator: ConditionOperator;
  value: ConditionValue;
}

/**
 * `conditions` JSON on a rule: `{ field: <clause> }`. A bare scalar value is
 * treated by the backend as an implicit equality check.
 */
export type AutomationConditions = Record<string, ConditionClause | ConditionValue>;

// --- Actions ---------------------------------------------------------------

export type ActionConfiguration = Record<string, unknown>;

export interface AutomationActionInput {
  action_type: AutomationActionType;
  name: string;
  configuration: ActionConfiguration;
  execution_order: number;
}

export interface AutomationAction extends AutomationActionInput {
  id: string;
  rule_id: string;
  organization_id: string;
  created_at: string;
  updated_at: string;
}

// --- Rules -----------------------------------------------------------------

export interface AutomationRule {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  module: string;
  trigger_event: AutomationTriggerEvent;
  conditions: AutomationConditions;
  is_active: boolean;
  actions: AutomationAction[];
  created_at: string;
  updated_at: string;
  /** action_id -> webhook signing secret; populated ONLY in the create response (shown once). */
  revealed_signing_secrets?: Record<string, string> | null;
}

export interface AutomationRuleCreate {
  name: string;
  description?: string | null;
  module: string;
  trigger_event: AutomationTriggerEvent;
  conditions: AutomationConditions;
  is_active: boolean;
  actions: AutomationActionInput[];
}

/** PUT /automation/rules/{id} — note: actions cannot be changed via update. */
export interface AutomationRuleUpdate {
  name?: string;
  description?: string | null;
  module?: string;
  trigger_event?: AutomationTriggerEvent;
  conditions?: AutomationConditions;
  is_active?: boolean;
}

export interface AutomationRuleTestRequest {
  event_data: Record<string, unknown>;
}

export interface AutomationRuleTestResult {
  rule_id: string;
  matches: boolean;
  would_execute_actions: string[];
}

export interface AutomationRulesParams {
  module?: string;
}

// --- Logs ------------------------------------------------------------------

export interface AutomationLog {
  id: string;
  organization_id: string;
  /** email_alert | webhook | field_update | schedule | rule_evaluation */
  action_type: string;
  name: string;
  entity_type: string;
  entity_id: string | null;
  status: AutomationLogStatus;
  occurred_at: string;
  details: Record<string, unknown> | null;
  error_message: string | null;
}

export interface AutomationLogsParams {
  entity_type?: string;
  status?: AutomationLogStatus;
  limit?: number;
}

// --- Schedules -------------------------------------------------------------

export interface AutomationSchedule {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  frequency: ScheduleFrequency;
  cron_expression: string | null;
  target_action: string;
  status: ScheduleStatus | string;
  is_active: boolean;
  last_executed_on: string | null;
  next_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationScheduleCreate {
  name: string;
  description?: string | null;
  frequency: ScheduleFrequency;
  cron_expression?: string | null;
  target_action: string;
  status?: ScheduleStatus;
  is_active?: boolean;
}

export interface AutomationScheduleUpdate {
  name?: string;
  description?: string | null;
  frequency?: ScheduleFrequency;
  cron_expression?: string | null;
  target_action?: string;
  status?: ScheduleStatus;
  is_active?: boolean;
}

export interface ScheduleTriggerResult {
  schedule_id: string;
  executed_at: string;
  target_action: string;
  result: Record<string, unknown>;
}

export interface StatusMessageResponse {
  status: string;
  message: string;
}
