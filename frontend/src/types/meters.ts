// ---------------------------------------------------------------------------
// Usage / Metering types — mirrors backend/app/schemas/meters.py
// ---------------------------------------------------------------------------

export type AggregationType = 'sum' | 'max' | 'count' | 'last';
export type UsageEventStatus = 'accepted' | 'rejected' | 'corrected';
export type UsageAggregateStatus = 'open' | 'calculated' | 'finalized';

export const AGGREGATION_TYPES: AggregationType[] = ['sum', 'max', 'count', 'last'];

export interface UsageMeterOut {
  id: string;
  /** Lower-cased by the backend on create. */
  code: string;
  name: string;
  unit_name: string;
  aggregation_type: AggregationType;
  description: string | null;
  is_active: boolean;
  /** Flat per-unit usage rate (decimal string); null = unpriced, usage rates at 0. */
  unit_price?: string | number | null;
  created_at: string;
}

export interface UsageMeterCreateIn {
  code: string;
  name: string;
  unit_name?: string;
  aggregation_type?: AggregationType;
  description?: string | null;
  unit_price?: string | null;
}

export interface UsageMeterUpdateIn {
  name?: string;
  unit_name?: string;
  description?: string | null;
  unit_price?: string | null;
  is_active?: boolean;
}

export interface BillingCycleOut {
  id: string;
  subscription_id: string;
  cycle_number: number;
  period_start: string;
  period_end: string;
  /** open | finalized | invoiced | cancelled */
  status: string;
  invoice_id: string | null;
  finalized_at: string | null;
}

export interface UsageEventIn {
  /** Meter code (the backend also accepts a meter id here). */
  meter_code: string;
  customer_id: string;
  /** Decimal > 0, serialised as string. */
  quantity: string | number;
  idempotency_key: string;
  subscription_id?: string | null;
  /** ISO-8601 datetime; defaults to server "now" when omitted. */
  timestamp?: string | null;
  properties?: Record<string, unknown> | null;
}

export interface UsageEventBatchIn {
  events: UsageEventIn[];
}

export interface UsageEventOut {
  id: string;
  meter_id: string;
  customer_id: string;
  subscription_id: string | null;
  /** Decimal string with 4 fraction digits, e.g. "125.5000". */
  quantity: string;
  timestamp: string;
  idempotency_key: string;
  status: UsageEventStatus;
  created_at: string;
  /** Labels returned by the history list (GET /meters/events) only. */
  customer_name?: string | null;
  subscription_number?: string | null;
}

/** Filters for the usage history endpoints; dates are inclusive organization-local days. */
export interface UsageHistoryQuery {
  meter_id?: string;
  customer_id?: string;
  subscription_id?: string;
  date_from?: string;
  date_to?: string;
}

/** Per-meter running total of recorded (accepted) usage over a period. */
export interface UsageMeterSummaryOut {
  meter_id: string;
  meter_code: string;
  meter_name: string;
  unit_name: string;
  aggregation_type: AggregationType;
  event_count: number;
  /** Decimal string, aggregated per the meter's aggregation type. */
  total_quantity: string;
  last_event_at: string | null;
}

export interface UsageAggregateOut {
  id: string;
  meter_id: string;
  subscription_id: string;
  billing_cycle_id: string | null;
  period_start: string;
  period_end: string;
  total_quantity: string;
  /** Money string ("12.50"). */
  rated_amount: string;
  status: UsageAggregateStatus;
  finalized_at: string | null;
  invoice_id: string | null;
}

/**
 * A usage event with the labels the UI needs to render it - either one posted
 * from the page this session or one loaded from the history endpoint.
 */
export interface RecordedUsageEvent {
  event: UsageEventOut;
  meter_code: string;
  meter_name: string;
  unit_name: string;
  customer_label: string;
  subscription_label: string | null;
  /** True when the server returned an existing event for a re-used idempotency key. */
  replayed: boolean;
  recorded_at: string;
  source: 'single' | 'batch' | 'history';
}
