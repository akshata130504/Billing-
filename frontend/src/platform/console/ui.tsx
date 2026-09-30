import type { ReactNode } from 'react';
import { Badge } from '../../components/common/Badge';
import { STATUS_LABELS, type OrgStatus } from '../consoleApi';
import { ROLE_LABELS, type PlatformRole } from '../platformApi';

const STATUS_VARIANTS: Record<OrgStatus, 'success' | 'warning' | 'danger' | 'neutral'> = {
  active: 'success',
  suspended: 'warning',
  pending_deletion: 'danger',
  deleted: 'neutral',
};

export function StatusBadge({ status }: { status: OrgStatus }) {
  return (
    <Badge variant={STATUS_VARIANTS[status] ?? 'neutral'} dot>
      {STATUS_LABELS[status] ?? status}
    </Badge>
  );
}

export function RoleBadge({ role }: { role: PlatformRole }) {
  return <Badge variant={role === 'platform_administrator' ? 'primary' : 'info'}>{ROLE_LABELS[role] ?? role}</Badge>;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleDateString(undefined, { dateStyle: 'medium' });
}

export function Section({ title, description, actions, children }: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
        </div>
        {actions}
      </header>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-slate-900">{children}</dd>
    </div>
  );
}

export function Stat({ label, value, hint, tone = 'default' }: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: 'default' | 'success' | 'warning' | 'danger';
}) {
  const tones = {
    default: 'text-slate-900',
    success: 'text-emerald-700',
    warning: 'text-amber-700',
    danger: 'text-rose-700',
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${tones[tone]}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function StateDot({ ok, label }: { ok: boolean | null; label: string }) {
  const color = ok === null ? 'bg-slate-300' : ok ? 'bg-emerald-500' : 'bg-rose-500';
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-700">
      <span className={`h-2.5 w-2.5 rounded-full ${color}`} aria-hidden="true" />
      {label}
    </span>
  );
}

export function humanizeAction(action: string): string {
  return action
    .replace(/^PLATFORM_/, '')
    .toLowerCase()
    .replace(/_/g, ' ')
    .replace(/^\w/, (c) => c.toUpperCase());
}
