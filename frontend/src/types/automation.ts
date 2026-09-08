import type { PageParams, UserRef } from './api';

export type AutomationTrigger =
  | 'invoice_overdue'
  | 'invoice_due_soon'
  | 'quote_expiring'
  | 'payment_received'
  | 'payment_failed'
  | 'customer_created'
  | 'quote_accepted'
  | 'invoice_created';

export type AutomationExecutionStatus = 'success' | 'failed';

export type AutomationConditionOp = 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'contains';

export type AutomationConditionField =
  | 'amount'
  | 'days_overdue'
  | 'status'
  | 'payment_method'
  | 'customer_segment';

export interface AutomationCondition {
  field: string;
  op: string;
  value: string | number;
}

export type AutomationActionType =
  | 'create_activity'
  | 'create_reminder'
  | 'send_email'
  | 'update_collection_status'
  | 'create_approval_task';

export interface AutomationAction {
  action: string;
  params?: Record<string, unknown>;
}

export interface AutomationRuleOut {
  id: string;
  name: string;
  trigger: AutomationTrigger;
  conditions: AutomationCondition[];
  actions: AutomationAction[];
  is_active: boolean;
  created_by: UserRef | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationRuleIn {
  name: string;
  trigger: AutomationTrigger;
  conditions: AutomationCondition[];
  actions: AutomationAction[];
}

export interface AutomationRuleActiveIn {
  is_active: boolean;
}

export interface AutomationExecutionOut {
  id: string;
  rule_id: string;
  trigger: AutomationTrigger;
  triggered_at: string;
  status: AutomationExecutionStatus;
  result: unknown;
  error: string | null;
}

export interface AutomationDashboardOut {
  active_rules: number;
  paused_rules: number;
  failed_executions: number;
  total_executions: number;
  success_rate: number | null;
}

export interface AutomationRuleListParams extends PageParams {
  is_active?: boolean;
}

export interface AutomationExecutionListParams extends PageParams {
  rule_id?: string;
}
