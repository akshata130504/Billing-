import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, FileText, Users, Repeat, BarChart3, BookOpen } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import type { BadgeVariant } from '../../utils/format';
import { formatMoney, humanize } from '../../utils/format';
import type { ApiError } from '../../types/api';
import type {
  AIActionDraftStatus,
  AIActionType,
  AIRequestMode,
  AIRequestStatus,
  AISourceReference,
  AIWritingPurpose,
  AIWritingTone,
} from '../../types/ai';

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------

export const MODE_LABELS: Record<AIRequestMode, string> = {
  query: 'Ask',
  draft: 'Draft an action',
  writing: 'Writing assistant',
};

export const MODE_BADGE: Record<AIRequestMode, BadgeVariant> = {
  query: 'info',
  draft: 'primary',
  writing: 'neutral',
};

export const REQUEST_STATUS_BADGE: Record<AIRequestStatus, BadgeVariant> = {
  queued: 'neutral',
  running: 'info',
  completed: 'success',
  failed: 'danger',
};

export const DRAFT_STATUS_BADGE: Record<AIActionDraftStatus, BadgeVariant> = {
  proposed: 'neutral',
  validated: 'info',
  approved: 'primary',
  executed: 'success',
  rejected: 'danger',
  expired: 'warning',
};

export const ACTION_TYPE_LABELS: Record<AIActionType, { label: string; description: string }> = {
  credit_note: {
    label: 'Credit note',
    description: 'Drafts a credit note for a customer (optionally against an invoice). Executed through the credit service only after you confirm.',
  },
};

export const PURPOSE_LABELS: Record<AIWritingPurpose, { label: string; description: string }> = {
  payment_reminder: {
    label: 'Payment reminder',
    description: 'Subject + body referencing an invoice number, amount due and due date.',
  },
  custom: {
    label: 'Custom note',
    description: 'A short note built around your instructions, addressed to the customer.',
  },
};

export const TONE_LABELS: Record<AIWritingTone, string> = {
  neutral: 'Neutral',
  friendly: 'Friendly',
  firm: 'Firm',
};

/** Prompts derived from the intents the backend classifier actually recognises. */
export const EXAMPLE_QUESTIONS: { label: string; prompt: string }[] = [
  { label: 'Outstanding balance', prompt: 'What is our total outstanding receivable balance?' },
  { label: 'Overdue count', prompt: 'How many invoices are overdue right now?' },
  {
    label: 'Overdue beyond average',
    prompt: 'Which invoices are overdue beyond our average late-payment cycle?',
  },
  { label: 'MRR', prompt: 'What is our MRR from active recurring subscriptions?' },
];

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/**
 * The backend's ValidationAppError for drafts returns `details.fields.draft` as a
 * string[] (not the Record<string,string> the shared ApiError type suggests), so
 * flatten whatever shape arrives into a list of messages.
 */
export function extractValidationMessages(err: unknown): string[] {
  const apiErr = err as Partial<ApiError> | undefined;
  const fields = apiErr?.details?.fields as Record<string, unknown> | undefined;
  if (!fields) return [];
  const out: string[] = [];
  Object.values(fields).forEach((v) => {
    if (Array.isArray(v)) v.forEach((m) => typeof m === 'string' && out.push(m));
    else if (typeof v === 'string') out.push(v);
  });
  return out;
}

export function errorMessage(err: unknown, fallback = 'Something went wrong.'): string {
  const apiErr = err as Partial<ApiError> | undefined;
  return apiErr?.message || fallback;
}

// ---------------------------------------------------------------------------
// Source references → in-app links
// ---------------------------------------------------------------------------

interface SourceTarget {
  to: string | null;
  icon: ReactNode;
}

export function sourceTarget(src: AISourceReference): SourceTarget {
  const iconCls = 'w-3.5 h-3.5';
  switch (src.source_type) {
    case 'invoice':
      return { to: src.source_id ? `/invoices/${src.source_id}` : '/invoices', icon: <FileText className={iconCls} /> };
    case 'customer':
      return { to: src.source_id ? `/customers/${src.source_id}` : '/customers', icon: <Users className={iconCls} /> };
    case 'subscription':
      return {
        to: src.source_id ? `/subscriptions/${src.source_id}` : '/subscriptions',
        icon: <Repeat className={iconCls} />,
      };
    case 'invoice_report':
      return { to: '/invoices?status=overdue', icon: <FileText className={iconCls} /> };
    case 'receivable_summary':
      return { to: '/collections/invoices', icon: <BarChart3 className={iconCls} /> };
    case 'mrr_report':
      return { to: '/subscriptions', icon: <Repeat className={iconCls} /> };
    default:
      return { to: null, icon: <BookOpen className={iconCls} /> };
  }
}

export function SourceChips({ sources }: { sources: AISourceReference[] }) {
  if (!sources.length) return null;
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">Sources</div>
      <ul className="flex flex-wrap gap-2">
        {sources.map((src, i) => {
          const { to, icon } = sourceTarget(src);
          const inner = (
            <>
              <span className="text-slate-400">{icon}</span>
              <span className="font-medium text-slate-800">{src.label}</span>
              {src.snippet && <span className="text-slate-400 hidden sm:inline">· {src.snippet}</span>}
              {to && <ExternalLink className="w-3 h-3 text-slate-400" />}
            </>
          );
          const cls =
            'inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 bg-slate-50 max-w-full';
          return (
            <li key={`${src.source_type}-${src.source_id ?? i}`} className="max-w-full">
              {to ? (
                <Link to={to} className={`${cls} hover:border-brand-300 hover:bg-brand-50 transition-colors`}>
                  {inner}
                </Link>
              ) : (
                <span className={cls}>{inner}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Structured answer data
// ---------------------------------------------------------------------------

const MONEY_KEYS = /balance|mrr|total|amount|revenue/i;

export function formatDataValue(key: string, value: unknown, currency: string): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') {
    return MONEY_KEYS.test(key) && !/count|days/i.test(key) ? formatMoney(value, currency) : String(value);
  }
  if (typeof value === 'string') {
    if (MONEY_KEYS.test(key) && !/count|days/i.test(key) && /^-?\d+(\.\d+)?$/.test(value)) {
      return formatMoney(value, currency);
    }
    return value;
  }
  return JSON.stringify(value);
}

export function DataFacts({ data, currency }: { data: Record<string, unknown>; currency: string }) {
  const entries = Object.entries(data);
  if (!entries.length) return null;
  return (
    <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      {entries.map(([k, v]) => (
        <div key={k} className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
          <dt className="text-[11px] font-medium text-slate-500 truncate">{humanize(k)}</dt>
          <dd className="text-sm font-semibold text-slate-900 mt-0.5 truncate tabular-nums">
            {formatDataValue(k, v, currency)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ModeBadge({ mode }: { mode: AIRequestMode }) {
  return <Badge variant={MODE_BADGE[mode]}>{MODE_LABELS[mode]}</Badge>;
}

/** Shared textarea styling — no common Textarea component exists yet. */
export const TEXTAREA_CLS =
  'block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 shadow-subtle transition-colors hover:border-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-400 resize-y';

export const FIELD_LABEL_CLS = 'block text-xs font-medium text-slate-700 mb-1.5';

/**
 * /ai/* timestamps come back as naive ISO strings ("2026-09-08T17:58:33.375739") that are
 * actually UTC. JS would parse those as local time, so tag them before formatting.
 */
export function asUtc(ts: string | null | undefined): string | null {
  if (!ts) return null;
  return /(Z|[+-]\d{2}:?\d{2})$/.test(ts) ? ts : `${ts}Z`;
}
