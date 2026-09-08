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
  created_at: string;
}

export interface UsageMeterCreateIn {
  code: string;
  name: string;
  unit_name?: string;
  aggregation_type?: AggregationType;
  description?: string | null;
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
 * The API has no endpoint that lists usage events, so the page keeps an
 * in-session log of what it recorded. This wraps the server response with the
 * labels the UI needs to render it.
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
  source: 'single' | 'batch';
}
