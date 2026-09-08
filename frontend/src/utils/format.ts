import type { BadgeProps } from '../components/common/Badge';

export type BadgeVariant = NonNullable<BadgeProps['variant']>;

// ---------------------------------------------------------------------------
// Money
// ---------------------------------------------------------------------------

const currencyFormatters = new Map<string, Intl.NumberFormat>();

function currencyFormatter(currency: string, minimumFractionDigits = 2): Intl.NumberFormat {
  const key = `${currency}:${minimumFractionDigits}`;
  let fmt = currencyFormatters.get(key);
  if (!fmt) {
    try {
      fmt = new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency,
        minimumFractionDigits,
        maximumFractionDigits: 2,
      });
    } catch {
      fmt = new Intl.NumberFormat('en-IN', {
        minimumFractionDigits,
        maximumFractionDigits: 2,
      });
    }
    currencyFormatters.set(key, fmt);
  }
  return fmt;
}

/** Parses a contract money string ("1250.00") or number; returns NaN if invalid. */
export function parseMoney(amount: string | number | null | undefined): number {
  if (amount === null || amount === undefined) return NaN;
  // A whitespace-only field is "no value", not zero — Number('  ') is 0.
  if (typeof amount === 'string' && amount.trim() === '') return NaN;
  const n = typeof amount === 'number' ? amount : Number(amount);
  return Number.isFinite(n) ? n : NaN;
}

/** formatMoney("1250.00") → "₹1,250.00" (en-IN grouping). */
export function formatMoney(
  amount: string | number | null | undefined,
  currency = 'INR',
  options: { compact?: boolean } = {}
): string {
  const n = parseMoney(amount);
  if (Number.isNaN(n)) return '—';
  if (options.compact && Math.abs(n) >= 100000) {
    // Indian short scale: lakh / crore. The sign goes before the symbol
    // ("-₹1.50 L"), never between it and the digits.
    const sign = n < 0 ? '-' : '';
    const magnitude = Math.abs(n);
    if (magnitude >= 10000000) return `${sign}${currencySymbol(currency)}${(magnitude / 10000000).toFixed(2)} Cr`;
    return `${sign}${currencySymbol(currency)}${(magnitude / 100000).toFixed(2)} L`;
  }
  return currencyFormatter(currency).format(n);
}

export function currencySymbol(currency = 'INR'): string {
  try {
    const parts = new Intl.NumberFormat('en-IN', { style: 'currency', currency }).formatToParts(1);
    return parts.find((p) => p.type === 'currency')?.value ?? currency;
  } catch {
    return currency;
  }
}

/** Serialises a number the way the API expects money: 2 decimals, string. */
export function toMoneyString(value: number | string): string {
  const n = parseMoney(value);
  if (Number.isNaN(n)) return '0.00';
  // toFixed rounds the binary double, so 2.675 -> "2.67" and 1.005 -> "1.00",
  // under-stating money on exact half-paise. Round on the decimal representation
  // instead so half-way values go up, matching the backend's ROUND_HALF_UP.
  const scaled = Number(`${n}e2`);
  const rounded = Math.sign(scaled) * Math.round(Math.abs(scaled));
  return (Number(`${rounded}e-2`)).toFixed(2);
}

/** formatPercent("12.5") → "12.5%" */
export function formatPercent(value: string | number | null | undefined, digits = 1): string {
  const n = parseMoney(value);
  if (Number.isNaN(n)) return '—';
  return `${n.toFixed(digits).replace(/\.0+$/, '')}%`;
}

export function formatNumber(value: number | string | null | undefined): string {
  const n = parseMoney(value);
  if (Number.isNaN(n)) return '—';
  return new Intl.NumberFormat('en-IN').format(n);
}

// ---------------------------------------------------------------------------
// Dates
// ---------------------------------------------------------------------------

function toDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  // Plain YYYY-MM-DD: interpret as a local calendar date to avoid TZ shifts.
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const d = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

const DATE_FMT = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
const DATETIME_FMT = new Intl.DateTimeFormat('en-IN', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});
const MONTH_FMT = new Intl.DateTimeFormat('en-IN', { month: 'short', year: 'numeric' });

/** formatDate("2026-09-07") → "07 Sep 2026" */
export function formatDate(value: string | Date | null | undefined): string {
  const d = toDate(value);
  return d ? DATE_FMT.format(d) : '—';
}

/** formatDateTime("2026-09-07T10:15:00Z") → "07 Sep 2026, 03:45 pm" (local time) */
export function formatDateTime(value: string | Date | null | undefined): string {
  const d = toDate(value);
  return d ? DATETIME_FMT.format(d) : '—';
}

export function formatMonth(value: string | Date | null | undefined): string {
  const d = toDate(value);
  return d ? MONTH_FMT.format(d) : '—';
}

const RELATIVE_FMT = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

/** formatRelative(ts) → "3 hours ago" / "in 2 days" / "yesterday" */
export function formatRelative(value: string | Date | null | undefined, now: Date = new Date()): string {
  const d = toDate(value);
  if (!d) return '—';
  const diffSec = Math.round((d.getTime() - now.getTime()) / 1000);
  const abs = Math.abs(diffSec);
  if (abs < 45) return 'just now';
  if (abs < 3600) return RELATIVE_FMT.format(Math.round(diffSec / 60), 'minute');
  if (abs < 86400) return RELATIVE_FMT.format(Math.round(diffSec / 3600), 'hour');
  if (abs < 86400 * 30) return RELATIVE_FMT.format(Math.round(diffSec / 86400), 'day');
  if (abs < 86400 * 365) return RELATIVE_FMT.format(Math.round(diffSec / (86400 * 30)), 'month');
  return RELATIVE_FMT.format(Math.round(diffSec / (86400 * 365)), 'year');
}

/** Today's date as YYYY-MM-DD (local). */
export function todayIso(): string {
  return toIsoDate(new Date());
}

export function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function addDays(iso: string, days: number): string {
  const d = toDate(iso);
  if (!d) return iso;
  d.setDate(d.getDate() + days);
  return toIsoDate(d);
}

// ---------------------------------------------------------------------------
// Status → Badge variant
// ---------------------------------------------------------------------------

const STATUS_VARIANTS: Record<string, BadgeVariant> = {
  // Invoice
  draft: 'neutral',
  sent: 'primary',
  partially_paid: 'warning',
  paid: 'success',
  overdue: 'danger',
  void: 'neutral',
  // Quote
  pending_approval: 'warning',
  accepted: 'success',
  declined: 'danger',
  expired: 'neutral',
  converted: 'info',
  // Subscription
  trialing: 'info',
  active: 'success',
  past_due: 'danger',
  paused: 'warning',
  cancelled: 'neutral',
  // Payment
  pending: 'warning',
  succeeded: 'success',
  failed: 'danger',
  refunded: 'neutral',
  partially_refunded: 'warning',
  // Reconciliation
  auto_matched: 'success',
  matched: 'success',
  unmatched: 'warning',
  exception: 'danger',
  // Membership / customer
  invited: 'info',
  deactivated: 'neutral',
  inactive: 'neutral',
  // Approvals
  approved: 'success',
  rejected: 'danger',
  // Audit
  success: 'success',
  warning: 'warning',
  denied: 'danger',
  // Imports
  completed: 'success',
  completed_with_errors: 'warning',
  // Refunds
  processed: 'success',
  // Urgency
  critical: 'danger',
  high: 'warning',
  medium: 'info',
  // Activity severity
  normal: 'neutral',
  danger: 'danger',
};

/** Maps any contract status/union value to a Badge variant. */
export function statusVariant(status: string | null | undefined): BadgeVariant {
  if (!status) return 'neutral';
  return STATUS_VARIANTS[status] ?? 'neutral';
}

/** "partially_paid" → "Partially paid" */
export function humanize(value: string | null | undefined): string {
  if (!value) return '—';
  const s = value.replace(/[_-]+/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const ROLE_LABELS: Record<string, string> = {
  owner: 'Owner',
  admin: 'Admin',
  finance: 'Finance',
  viewer: 'Viewer',
};

export function initials(name: string | null | undefined, fallback = '?'): string {
  if (!name) return fallback;
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return fallback;
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
