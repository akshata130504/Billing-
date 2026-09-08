// ---------------------------------------------------------------------------
// Dunning management — mirrors backend/app/schemas/dunning.py
// ---------------------------------------------------------------------------

export type DunningFinalAction = 'unpaid' | 'cancel_and_void' | 'suspend';

export type DunningCaseStatus =
  | 'open'
  | 'retry_scheduled'
  | 'retrying'
  | 'recovered'
  | 'paused'
  | 'stopped'
  | 'exhausted'
  | 'finalized';

export type DunningAttemptStatus = 'scheduled' | 'processing' | 'succeeded' | 'failed' | 'skipped';

// --- Policies ---------------------------------------------------------------

export interface DunningPolicyBase {
  name: string;
  description: string | null;
  is_default: boolean;
  is_active: boolean;
  applies_to_autocharge: boolean;
  /** Money string ("1000.00") or null. Segments policies by minimum invoice amount. */
  min_amount: string | null;
  /** 1..3 */
  max_retries: number;
  /** Days between retries, max 3 entries; sum must be <= total_span_days. */
  retry_intervals_days: number[];
  /** <= 30 */
  total_span_days: number;
  notify_on_failure: boolean;
  notify_on_retry: boolean;
  notify_on_success: boolean;
  first_ach_immediate_cancel: boolean;
  final_action: DunningFinalAction;
  /** 1..60 */
  non_autocharge_grace_days: number;
}

export interface DunningPolicy extends DunningPolicyBase {
  id: string;
  organization_id: string;
  created_at: string;
  updated_at: string;
}

export type DunningPolicyCreate = DunningPolicyBase;

export type DunningPolicyUpdate = Partial<DunningPolicyBase>;

// --- Cases ------------------------------------------------------------------

export interface DunningAttempt {
  id: string;
  attempt_number: number;
  scheduled_at: string;
  executed_at: string | null;
  status: DunningAttemptStatus;
  payment_attempt_id: string | null;
  error_code: string | null;
  error_message: string | null;
  notification_sent: boolean;
  created_at: string;
}

export interface DunningCommunication {
  id: string;
  recipient_email: string;
  subject: string;
  /** failure | retry | success | final_notice | card_expiry */
  template_type: string;
  body_preview: string | null;
  sent_at: string;
}

export interface DunningCase {
  id: string;
  case_number: string;
  policy_id: string;
  customer_id: string;
  subscription_id: string | null;
  invoice_id: string;
  status: DunningCaseStatus;
  trigger_reason: string;
  amount_due: string;
  currency: string;
  attempt_count: number;
  max_attempts: number;
  next_retry_at: string | null;
  paused_at: string | null;
  pause_reason: string | null;
  stopped_at: string | null;
  stop_reason: string | null;
  recovered_at: string | null;
  recovered_by_payment_id: string | null;
  finalized_at: string | null;
  final_action_taken: string | null;
  created_at: string;
  updated_at: string;
}

export interface DunningCaseDetail extends DunningCase {
  policy: DunningPolicy | null;
  customer_name: string | null;
  invoice_number: string | null;
  attempts: DunningAttempt[];
  communications: DunningCommunication[];
}

export interface DunningCaseListParams {
  status?: DunningCaseStatus;
  customer_id?: string;
}

export interface DunningCasePauseIn {
  reason?: string | null;
}

export interface DunningCaseStopIn {
  reason?: string | null;
  apply_final_action?: boolean;
}

export interface ReactivateSubscriptionResponse {
  status: string;
  message: string;
  subscription_id: string;
}

// --- Metrics & pre-dunning ---------------------------------------------------

export interface DunningMetrics {
  total_cases: number;
  active_cases: number;
  recovered_cases: number;
  exhausted_cases: number;
  paused_cases: number;
  stopped_cases: number;
  recovery_rate_pct: number;
  total_amount_at_risk: string;
  total_amount_recovered: string;
  currency: string;
}

export interface ExpiringCardNotice {
  payment_method_id: string;
  customer_id: string;
  customer_email: string;
  card_last4: string;
  card_brand: string | null;
  expiry_month: number;
  expiry_year: number;
  days_until_expiry: number;
  notification_sent: boolean;
}
