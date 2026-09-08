import type { ReactNode } from 'react';
import { Globe, Mail, Phone, ReceiptText } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { EmptyState } from '../../components/common/EmptyState';
import type { LineItemOut } from '../../types/api';
import { cn } from '../../utils/cn';
import { formatMoney, formatNumber, formatPercent, humanize, initials, statusVariant } from '../../utils/format';

// ---------------------------------------------------------------------------
// Header: organisation identity + document number/status
// ---------------------------------------------------------------------------

interface OrgHeaderProps {
  orgName: string;
  legalName?: string | null;
  logoUrl?: string | null;
  docLabel: string;
  docNumber: string;
  status: string;
  /** Optional right-aligned actions (e.g. Download PDF). */
  actions?: ReactNode;
}

export function OrgHeader({ orgName, legalName, logoUrl, docLabel, docNumber, status, actions }: OrgHeaderProps) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex items-center gap-3 min-w-0">
        {logoUrl ? (
          <img
            src={logoUrl}
            alt={`${orgName} logo`}
            className="h-12 w-12 rounded-xl object-contain border border-slate-200 bg-white shrink-0"
          />
        ) : (
          <div className="h-12 w-12 rounded-xl bg-brand-50 text-brand-700 border border-blue-100 flex items-center justify-center text-sm font-bold shrink-0">
            {initials(orgName)}
          </div>
        )}
        <div className="min-w-0">
          <p className="text-base font-bold text-slate-900 truncate">{orgName}</p>
          {legalName && legalName !== orgName && (
            <p className="text-xs text-slate-500 truncate">{legalName}</p>
          )}
        </div>
      </div>
      <div className="flex flex-col items-start sm:items-end gap-2 shrink-0">
        <div className="flex items-center gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{docLabel}</p>
          <Badge variant={statusVariant(status)} dot>
            {humanize(status)}
          </Badge>
        </div>
        <p className="text-lg font-bold text-slate-900 tabular-nums tracking-tight">{docNumber}</p>
        {actions}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Key/value meta grid (dates, customer, period…)
// ---------------------------------------------------------------------------

export interface MetaItem {
  label: string;
  value: ReactNode;
  /** Colour the value (e.g. overdue). */
  tone?: 'default' | 'danger' | 'success';
}

export function MetaGrid({ items }: { items: MetaItem[] }) {
  return (
    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{item.label}</dt>
          <dd
            className={cn(
              'mt-1 text-sm font-medium truncate',
              item.tone === 'danger' && 'text-rose-700',
              item.tone === 'success' && 'text-emerald-700',
              (!item.tone || item.tone === 'default') && 'text-slate-900'
            )}
          >
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

// ---------------------------------------------------------------------------
// Address blocks (From / Bill to)
// ---------------------------------------------------------------------------

export function joinAddress(...parts: Array<string | null | undefined>): string[] {
  return parts.map((p) => (p ?? '').trim()).filter(Boolean);
}

interface AddressBlockProps {
  heading: string;
  name: string;
  subName?: string | null;
  lines: string[];
  email?: string | null;
  phone?: string | null;
  website?: string | null;
  /** Tax ids etc. rendered as "Label: value". */
  meta?: Array<{ label: string; value: string | null | undefined }>;
}

export function AddressBlock({ heading, name, subName, lines, email, phone, website, meta }: AddressBlockProps) {
  const metaRows = (meta ?? []).filter((m) => m.value && m.value.trim());
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{heading}</p>
      <p className="mt-1.5 text-sm font-semibold text-slate-900">{name}</p>
      {subName && subName !== name && <p className="text-xs text-slate-600">{subName}</p>}
      {lines.length > 0 && (
        <p className="mt-1 text-xs text-slate-600 leading-relaxed">
          {lines.map((line, i) => (
            <span key={i} className="block">
              {line}
            </span>
          ))}
        </p>
      )}
      {(email || phone || website) && (
        <div className="mt-2 space-y-0.5">
          {email && <ContactLink icon={<Mail className="w-3 h-3" />} href={`mailto:${email}`} label={email} />}
          {phone && <ContactLink icon={<Phone className="w-3 h-3" />} href={`tel:${phone.replace(/\s+/g, '')}`} label={phone} />}
          {website && (
            <ContactLink
              icon={<Globe className="w-3 h-3" />}
              href={/^https?:\/\//i.test(website) ? website : `https://${website}`}
              label={website}
              external
            />
          )}
        </div>
      )}
      {metaRows.length > 0 && (
        <dl className="mt-2 space-y-0.5">
          {metaRows.map((m) => (
            <div key={m.label} className="text-xs text-slate-600">
              <dt className="inline font-medium text-slate-500">{m.label}: </dt>
              <dd className="inline tabular-nums">{m.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

export function ContactLink({
  icon,
  href,
  label,
  external = false,
}: {
  icon: ReactNode;
  href: string;
  label: string;
  external?: boolean;
}) {
  return (
    <a
      href={href}
      className="flex items-center gap-1.5 text-xs text-brand-700 hover:text-brand-800 hover:underline break-all"
      {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
    >
      {icon}
      <span>{label}</span>
    </a>
  );
}

// ---------------------------------------------------------------------------
// Line items
// ---------------------------------------------------------------------------

export function LineItemsTable({ items, currency }: { items: LineItemOut[]; currency: string }) {
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<ReceiptText className="w-6 h-6 stroke-1" />}
        title="No line items"
        description="This document has no billable lines."
      />
    );
  }
  const sorted = [...items].sort((a, b) => a.position - b.position);
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full min-w-[560px] text-sm">
        <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          <tr>
            <th className="px-4 py-2.5 text-left">Description</th>
            <th className="px-4 py-2.5 text-right w-20">Qty</th>
            <th className="px-4 py-2.5 text-right w-32">Unit price</th>
            <th className="px-4 py-2.5 text-right w-20">Tax</th>
            <th className="px-4 py-2.5 text-right w-32">Amount</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {sorted.map((item) => (
            <tr key={item.id}>
              <td className="px-4 py-3 text-slate-900 align-top">{item.description}</td>
              <td className="px-4 py-3 text-right text-slate-700 tabular-nums align-top">{formatNumber(item.quantity)}</td>
              <td className="px-4 py-3 text-right text-slate-700 tabular-nums align-top">
                {formatMoney(item.unit_price, currency)}
              </td>
              <td className="px-4 py-3 text-right text-slate-500 tabular-nums align-top">
                {formatPercent(item.tax_rate_pct)}
              </td>
              <td className="px-4 py-3 text-right font-medium text-slate-900 tabular-nums align-top">
                {formatMoney(item.amount, currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Totals
// ---------------------------------------------------------------------------

export interface TotalRow {
  label: string;
  value: string;
  kind?: 'default' | 'muted' | 'total' | 'due' | 'paid';
}

export function TotalsBlock({ rows }: { rows: TotalRow[] }) {
  return (
    <div className="flex justify-end">
      <dl className="w-full sm:w-80 space-y-1.5">
        {rows.map((row) => {
          const kind = row.kind ?? 'default';
          return (
            <div
              key={row.label}
              className={cn(
                'flex items-center justify-between gap-4',
                kind === 'total' && 'border-t border-slate-200 pt-2 mt-2',
                kind === 'due' && 'border-t border-slate-200 pt-2 mt-2'
              )}
            >
              <dt
                className={cn(
                  'text-sm',
                  kind === 'muted' && 'text-slate-500',
                  kind === 'default' && 'text-slate-600',
                  kind === 'paid' && 'text-emerald-700',
                  kind === 'total' && 'font-semibold text-slate-900',
                  kind === 'due' && 'font-bold text-slate-900'
                )}
              >
                {row.label}
              </dt>
              <dd
                className={cn(
                  'text-sm tabular-nums',
                  kind === 'muted' && 'text-slate-500',
                  kind === 'default' && 'text-slate-900',
                  kind === 'paid' && 'text-emerald-700',
                  kind === 'total' && 'font-semibold text-slate-900',
                  kind === 'due' && 'text-base font-bold text-slate-900'
                )}
              >
                {row.value}
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Notes & terms
// ---------------------------------------------------------------------------

export function NotesBlock({ notes, terms }: { notes: string | null; terms: string | null }) {
  if (!notes && !terms) return null;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {notes && (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Notes</p>
          <p className="mt-1.5 text-sm text-slate-700 whitespace-pre-line leading-relaxed">{notes}</p>
        </div>
      )}
      {terms && (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Terms</p>
          <p className="mt-1.5 text-sm text-slate-700 whitespace-pre-line leading-relaxed">{terms}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status / info panel
// ---------------------------------------------------------------------------

export type PanelTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

const PANEL_TONES: Record<PanelTone, { wrap: string; icon: string; title: string; body: string }> = {
  success: {
    wrap: 'border-emerald-200 bg-emerald-50',
    icon: 'bg-emerald-100 text-emerald-700',
    title: 'text-emerald-900',
    body: 'text-emerald-800',
  },
  warning: {
    wrap: 'border-amber-200 bg-amber-50',
    icon: 'bg-amber-100 text-amber-700',
    title: 'text-amber-900',
    body: 'text-amber-800',
  },
  danger: {
    wrap: 'border-rose-200 bg-rose-50',
    icon: 'bg-rose-100 text-rose-700',
    title: 'text-rose-900',
    body: 'text-rose-800',
  },
  info: {
    wrap: 'border-blue-200 bg-blue-50',
    icon: 'bg-blue-100 text-brand-700',
    title: 'text-slate-900',
    body: 'text-slate-700',
  },
  neutral: {
    wrap: 'border-slate-200 bg-slate-50',
    icon: 'bg-slate-200 text-slate-600',
    title: 'text-slate-900',
    body: 'text-slate-600',
  },
};

interface InfoPanelProps {
  tone: PanelTone;
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  className?: string;
}

export function InfoPanel({ tone, icon, title, children, className }: InfoPanelProps) {
  const t = PANEL_TONES[tone];
  return (
    <div className={cn('rounded-xl border p-4 sm:p-5 flex items-start gap-3.5', t.wrap, className)}>
      <div className={cn('p-2.5 rounded-xl shrink-0', t.icon)}>{icon}</div>
      <div className="min-w-0 flex-1">
        <p className={cn('text-sm font-semibold', t.title)}>{title}</p>
        {children && <div className={cn('mt-1 text-sm leading-relaxed', t.body)}>{children}</div>}
      </div>
    </div>
  );
}
