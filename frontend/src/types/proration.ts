// ---------------------------------------------------------------------------
// Proration / subscription changes
// Source of truth: backend/app/schemas/proration.py, backend/app/models/proration.py
// ---------------------------------------------------------------------------

export type SubscriptionChangeType =
  | 'upgrade'
  | 'downgrade'
  | 'quantity_change'
  | 'addon_change'
  | 'cancellation';

export type SubscriptionChangeStatus = 'previewed' | 'scheduled' | 'applied' | 'cancelled' | 'failed';

/**
 * `immediate`   – apply now; prorate from today.
 * `end_of_term` – record a scheduled change that takes effect on the current period end (no mid-cycle proration).
 * `scheduled`   – apply now, but calculate credit/charge from the supplied `effective_date` within the current period.
 */
export type ProrationEffectiveType = 'immediate' | 'end_of_term' | 'scheduled';

export interface SubscriptionChangePreviewIn {
  target_plan_id?: string | null;
  /** Decimal as string ("6") or number; must be > 0. */
  target_quantity?: string | number | null;
  /** YYYY-MM-DD. Clamped to the current billing period by the server. */
  effective_date?: string | null;
}

export interface ProrationPlanRef {
  id: string;
  name: string;
  unit_amount: string;
}

export interface SubscriptionChangePreviewOut {
  subscription_id: string;
  change_type: SubscriptionChangeType | string;
  old_plan: ProrationPlanRef;
  new_plan: ProrationPlanRef;
  old_quantity: string;
  new_quantity: string;
  /** Per-cycle rate billed today / after the change (FLAT = one unit; tiers re-priced). */
  old_total_rate?: string;
  new_total_rate?: string;
  period_start: string;
  period_end: string;
  effective_date: string;
  total_days: number;
  days_used: number;
  days_remaining: number;
  /** Unused portion of the old rate credited back. */
  unused_credit: string;
  /** Remaining portion of the new rate charged. */
  remaining_charge: string;
  /** remaining_charge − unused_credit. >0 invoice, <0 credit note. */
  net_amount: string;
  explanation: string;
}

export interface SubscriptionChangeApplyIn extends SubscriptionChangePreviewIn {
  effective_type?: ProrationEffectiveType;
}

export interface SubscriptionChangeOut {
  id: string;
  subscription_id: string;
  change_type: SubscriptionChangeType;
  status: SubscriptionChangeStatus;
  effective_type: ProrationEffectiveType;
  effective_date: string;
  target_plan_id: string | null;
  /** Decimal string, e.g. "5.000". */
  target_quantity: string | null;
  old_plan_amount: string;
  new_plan_amount: string;
  prorated_credit: string;
  prorated_charge: string;
  net_amount: string;
  invoice_id: string | null;
  credit_note_id: string | null;
  applied_at: string | null;
  created_at: string;
}
