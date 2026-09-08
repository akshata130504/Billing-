import type { AgingBucket } from '../../types/reports';

export const AGING_BUCKET_LABELS: Record<AgingBucket, string> = {
  current: 'Current',
  '1_30': '1-30 Days',
  '31_60': '31-60 Days',
  '61_90': '61-90 Days',
  '90_plus': '90+ Days',
};

export const PAYMENT_METHOD_LABELS: Record<string, string> = {
  razorpay: 'Razorpay',
  bank_transfer: 'Bank Transfer',
  upi: 'UPI',
  card: 'Card',
  cash: 'Cash',
  cheque: 'Cheque',
  other: 'Other',
};

export const PRICING_MODEL_LABELS: Record<string, string> = {
  flat: 'Flat',
  per_unit: 'Per Unit',
};

/**
 * Formats a report period string for display. Periods come back as either
 * 'YYYY-MM-DD' (day granularity) or 'YYYY-MM' (month granularity) — detect
 * which and format accordingly rather than threading granularity everywhere.
 */
export function formatReportPeriod(period: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(period)) {
    const [y, m, d] = period.split('-').map(Number);
    return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short' }).format(
      new Date(y, m - 1, d)
    );
  }
  if (/^\d{4}-\d{2}$/.test(period)) {
    const [y, m] = period.split('-').map(Number);
    return new Intl.DateTimeFormat('en-IN', { month: 'short', year: 'numeric' }).format(
      new Date(y, m - 1, 1)
    );
  }
  return period;
}
