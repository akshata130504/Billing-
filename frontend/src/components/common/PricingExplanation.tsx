import { Fragment } from 'react';
import { HelpCircle } from 'lucide-react';

/**
 * Staff-only view of a line's stored `pricing_explanation`. Catalog lines store the pricing
 * simulator's explanation as a JSON string; show it as labelled values in a collapsed
 * "Pricing details" disclosure instead of the raw JSON. Plain-text explanations stay as text.
 */

const LABELS: Record<string, string> = {
  catalog_base_price: 'Catalog base price',
  price_book_adjustment: 'Price book adjustment',
  effective_unit_price: 'Effective unit price',
  tier_explanation: 'Tier',
  subtotal_pre_discount: 'Subtotal before discount',
  net_line_amount: 'Net line amount',
  total_line_amount: 'Line total',
};

function label(key: string): string {
  if (LABELS[key]) return LABELS[key];
  const text = key.replace(/_pct$/, '').replace(/_/g, ' ').trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '-';
  if (Array.isArray(value)) return value.map((v) => formatValue('', v)).join(', ');
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== null && v !== undefined && v !== '')
      .map(([k, v]) => `${label(k)}: ${formatValue(k, v)}`)
      .join('; ');
  }
  const text = String(value);
  return key.endsWith('_pct') ? `${text}%` : text;
}

/** Labelled rows for a JSON object explanation, or null when it is plain text. */
export function pricingExplanationRows(raw: string): Array<[string, string]> | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== 'object') return null;
  return Object.entries(parsed as Record<string, unknown>)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => [label(k), formatValue(k, v)]);
}

export function PricingExplanation({ value }: { value?: string | null }) {
  if (!value) return null;
  const rows = pricingExplanationRows(value);
  if (!rows) {
    return (
      <div className="mt-1 flex items-center gap-1 text-xs text-indigo-600 bg-indigo-50/70 px-2 py-0.5 rounded w-fit">
        <HelpCircle className="w-3.5 h-3.5" />
        <span>{value}</span>
      </div>
    );
  }
  if (rows.length === 0) return null;
  return (
    <details className="mt-1 text-xs w-fit max-w-md">
      <summary className="inline-flex items-center gap-1 cursor-pointer text-indigo-600 hover:text-indigo-800 select-none">
        <HelpCircle className="w-3.5 h-3.5" />
        Pricing details
      </summary>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 bg-indigo-50/70 px-2 py-1.5 rounded text-gray-700">
        {rows.map(([k, v]) => (
          <Fragment key={k}>
            <dt className="text-gray-500">{k}</dt>
            <dd className="text-gray-800">{v}</dd>
          </Fragment>
        ))}
      </dl>
    </details>
  );
}
