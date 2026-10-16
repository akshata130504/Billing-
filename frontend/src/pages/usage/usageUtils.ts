import type { AggregationType, RecordedUsageEvent, UsageEventIn, UsageEventOut, UsageMeterOut } from '../../types/meters';
import { newIdempotencyKey } from '../../utils/idempotency';

export const AGGREGATION_LABELS: Record<AggregationType, { label: string; hint: string }> = {
  sum: { label: 'Sum', hint: 'Adds every event quantity in the period (e.g. API calls, GB transferred).' },
  max: { label: 'Max', hint: 'Bills the single highest quantity seen in the period (e.g. peak seats, peak storage).' },
  count: { label: 'Count', hint: 'Bills the number of events, ignoring quantity (e.g. jobs run, logins).' },
  last: { label: 'Last', hint: 'Bills the most recent quantity reported in the period (e.g. current seat count).' },
};

export { newIdempotencyKey };

/** Value for an <input type="datetime-local"> representing the given local time (minute precision). */
export function toDatetimeLocalValue(d: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Converts a datetime-local value to an ISO-8601 UTC string, or null when blank/invalid. */
export function datetimeLocalToIso(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

/** Strips trailing zeros from a decimal string: "125.5000" -> "125.5", "10.0000" -> "10". */
export function formatQuantity(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 4 }).format(n);
}

export interface ParsedBatch {
  events: UsageEventIn[];
  /** Blocking problems: import stays disabled while any exist. */
  errors: string[];
  /** Non-blocking notes (e.g. columns that were ignored). Import is still allowed. */
  warnings: string[];
  format: 'json' | 'csv' | 'empty';
}

export const BATCH_CSV_COLUMNS = [
  'meter_code',
  'customer_id',
  'quantity',
  'idempotency_key',
  'subscription_id',
  'timestamp',
  'properties',
] as const;

function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cur += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      out.push(cur);
      cur = '';
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out.map((s) => s.trim());
}

function normaliseEvent(raw: Record<string, unknown>, rowLabel: string, errors: string[]): UsageEventIn | null {
  const meter_code = String(raw.meter_code ?? raw.meter ?? '').trim();
  const customer_id = String(raw.customer_id ?? '').trim();
  const quantityRaw = raw.quantity;
  const quantity = quantityRaw === undefined || quantityRaw === null ? '' : String(quantityRaw).trim();
  let idempotency_key = String(raw.idempotency_key ?? '').trim();
  const subscription_id = raw.subscription_id ? String(raw.subscription_id).trim() : null;
  const timestampRaw = raw.timestamp ? String(raw.timestamp).trim() : '';

  const rowErrors: string[] = [];
  if (!meter_code) rowErrors.push('meter_code is required');
  if (!customer_id) rowErrors.push('customer_id is required');
  if (!quantity || !Number.isFinite(Number(quantity)) || Number(quantity) <= 0) {
    rowErrors.push('quantity must be a number greater than 0');
  }
  if (!idempotency_key) idempotency_key = newIdempotencyKey();
  if (idempotency_key.length > 128) rowErrors.push('idempotency_key exceeds 128 characters');

  let timestamp: string | null = null;
  if (timestampRaw) {
    const d = new Date(timestampRaw);
    if (Number.isNaN(d.getTime())) rowErrors.push(`timestamp "${timestampRaw}" is not a valid date`);
    else timestamp = d.toISOString();
  }

  let properties: Record<string, unknown> | null = null;
  const propsRaw = raw.properties;
  if (propsRaw !== undefined && propsRaw !== null && propsRaw !== '') {
    if (typeof propsRaw === 'string') {
      try {
        const parsed: unknown = JSON.parse(propsRaw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          properties = parsed as Record<string, unknown>;
        } else {
          rowErrors.push('properties must be a JSON object');
        }
      } catch {
        rowErrors.push('properties is not valid JSON');
      }
    } else if (typeof propsRaw === 'object' && !Array.isArray(propsRaw)) {
      properties = propsRaw as Record<string, unknown>;
    } else {
      rowErrors.push('properties must be a JSON object');
    }
  }

  if (rowErrors.length) {
    errors.push(`${rowLabel}: ${rowErrors.join('; ')}`);
    return null;
  }
  return { meter_code, customer_id, quantity, idempotency_key, subscription_id, timestamp, properties };
}

/**
 * Accepts either JSON (an array of events, or `{ "events": [...] }`) or CSV with a
 * header row using the UsageEventIn field names. Missing idempotency keys are generated.
 */
export function parseBatchInput(text: string): ParsedBatch {
  const trimmed = text.trim();
  if (!trimmed) return { events: [], errors: [], warnings: [], format: 'empty' };
  const errors: string[] = [];
  const warnings: string[] = [];
  const events: UsageEventIn[] = [];

  if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed);
    } catch (err: any) {
      return { events: [], errors: [`Invalid JSON: ${err?.message ?? 'parse error'}`], warnings, format: 'json' };
    }
    const list: unknown = Array.isArray(parsed)
      ? parsed
      : parsed && typeof parsed === 'object' && Array.isArray((parsed as { events?: unknown }).events)
        ? (parsed as { events: unknown[] }).events
        : null;
    if (!list) {
      return { events: [], errors: ['JSON must be an array of events or an object with an "events" array.'], warnings, format: 'json' };
    }
    (list as unknown[]).forEach((item, idx) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) {
        errors.push(`Event ${idx + 1}: must be an object`);
        return;
      }
      const ev = normaliseEvent(item as Record<string, unknown>, `Event ${idx + 1}`, errors);
      if (ev) events.push(ev);
    });
    return { events, errors, warnings, format: 'json' };
  }

  const lines = trimmed.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 2) {
    return { events: [], errors: ['CSV needs a header row and at least one data row.'], warnings, format: 'csv' };
  }
  const header = splitCsvLine(lines[0]).map((h) => h.toLowerCase());
  const known = new Set<string>(BATCH_CSV_COLUMNS);
  const unknown = header.filter((h) => !known.has(h));
  if (!header.includes('meter_code') || !header.includes('customer_id') || !header.includes('quantity')) {
    errors.push('CSV header must include meter_code, customer_id and quantity.');
  }
  if (unknown.length) warnings.push(`Ignoring unknown CSV column(s): ${unknown.join(', ')}`);

  for (let i = 1; i < lines.length; i++) {
    const cells = splitCsvLine(lines[i]);
    const raw: Record<string, unknown> = {};
    header.forEach((h, idx) => {
      if (known.has(h)) raw[h] = cells[idx] ?? '';
    });
    const ev = normaliseEvent(raw, `Row ${i + 1}`, errors);
    if (ev) events.push(ev);
  }
  return { events, errors, warnings, format: 'csv' };
}

/**
 * The meters API returns naive UTC datetimes without a zone suffix
 * ("2026-09-08T17:21:24.387285"). Append "Z" so they are displayed in local time correctly.
 */
export function normaliseApiTimestamp(value: string | null | undefined): string | null {
  if (!value) return null;
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(value) ? `${value}Z` : value;
}

/** A stored event from GET /meters/events, labelled for the events table. */
export function historyRow(ev: UsageEventOut, meter: UsageMeterOut | undefined): RecordedUsageEvent {
  return {
    event: ev,
    meter_code: meter?.code ?? ev.meter_id,
    meter_name: meter?.name ?? ev.meter_id,
    unit_name: meter?.unit_name ?? '',
    customer_label: ev.customer_name || ev.customer_id,
    subscription_label: ev.subscription_number ?? null,
    replayed: false,
    recorded_at: ev.created_at,
    source: 'history',
  };
}
