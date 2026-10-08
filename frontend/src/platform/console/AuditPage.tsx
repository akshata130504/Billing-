import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../../components/common/Button';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { PageHeader } from '../../components/common/PageHeader';
import { Pagination } from '../../components/common/Pagination';
import { Badge } from '../../components/common/Badge';
import { consoleApi, type AuditEntry, type AuditQuery, type Page } from '../consoleApi';
import { PlatformApiError } from '../platformApi';
import { formatDateTime, humanizeAction } from './ui';

const PAGE_SIZE = 50;
const RESULT_VARIANT: Record<string, 'success' | 'danger' | 'warning' | 'neutral'> = {
  success: 'success',
  failure: 'danger',
  denied: 'warning',
};

/** Platform audit log (Platform Administrator). Append-only: nothing here edits or deletes. */
export function AuditPage() {
  const [filters, setFilters] = useState<AuditQuery>({});
  const [draft, setDraft] = useState<AuditQuery>({});
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<AuditEntry> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await consoleApi.audit({ ...filters, page, page_size: PAGE_SIZE }));
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load the audit log.');
    }
  }, [filters, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const apply = (e: FormEvent) => {
    e.preventDefault();
    setPage(1);
    setFilters({
      q: draft.q?.trim() || undefined,
      action: draft.action?.trim().toUpperCase() || undefined,
      result: draft.result || undefined,
      organization_id: draft.organization_id?.trim() || undefined,
      staff_id: draft.staff_id?.trim() || undefined,
      target_type: draft.target_type?.trim() || undefined,
      target_id: draft.target_id?.trim() || undefined,
      since: draft.since ? new Date(draft.since).toISOString() : undefined,
      until: draft.until ? new Date(draft.until).toISOString() : undefined,
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Platform audit log" subtitle="Every platform sign-in, security event, staff change and lifecycle action. Append-only - entries cannot be edited or deleted." />

      <form onSubmit={apply} className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-2 lg:grid-cols-4" aria-label="Filter audit log">
        <label className="text-xs font-medium text-slate-600 sm:col-span-2">
          Search
          <input value={draft.q ?? ''} onChange={(e) => setDraft({ ...draft, q: e.target.value })} placeholder="Action, staff email, organization, reason or ticket"
            maxLength={100} className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" />
        </label>
        <label className="text-xs font-medium text-slate-600">
          From
          <input type="datetime-local" value={draft.since ?? ''} onChange={(e) => setDraft({ ...draft, since: e.target.value })}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" />
        </label>
        <label className="text-xs font-medium text-slate-600">
          To
          <input type="datetime-local" value={draft.until ?? ''} onChange={(e) => setDraft({ ...draft, until: e.target.value })}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" />
        </label>
        <label className="text-xs font-medium text-slate-600">
          Action
          <input value={draft.action ?? ''} onChange={(e) => setDraft({ ...draft, action: e.target.value })} placeholder="e.g. ORGANIZATION_SUSPENDED"
            className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" />
        </label>
        <label className="text-xs font-medium text-slate-600">
          Result
          <select value={draft.result ?? ''} onChange={(e) => setDraft({ ...draft, result: e.target.value })}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2 text-sm">
            <option value="">Any</option>
            <option value="success">Success</option>
            <option value="failure">Failure</option>
            <option value="denied">Denied</option>
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Organization id
          <input value={draft.organization_id ?? ''} onChange={(e) => setDraft({ ...draft, organization_id: e.target.value })}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" />
        </label>
        <label className="text-xs font-medium text-slate-600">
          Staff id
          <input value={draft.staff_id ?? ''} onChange={(e) => setDraft({ ...draft, staff_id: e.target.value })}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" />
        </label>
        <label className="text-xs font-medium text-slate-600">
          Target type
          <select value={draft.target_type ?? ''} onChange={(e) => setDraft({ ...draft, target_type: e.target.value })}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2 text-sm">
            <option value="">Any</option>
            <option value="organization">Organization</option>
            <option value="platform_staff">Platform staff</option>
            <option value="website_page">Website page</option>
            <option value="app_ui_page">App UI page (visual editor)</option>
            <option value="access_grant">Access grant</option>
          </select>
        </label>
        <label className="text-xs font-medium text-slate-600">
          Target id
          <input value={draft.target_id ?? ''} onChange={(e) => setDraft({ ...draft, target_id: e.target.value })}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" />
        </label>
        <div className="flex items-end gap-2">
          <Button type="submit" size="sm">Apply</Button>
          <Button type="button" size="sm" variant="outline" onClick={() => { setDraft({}); setFilters({}); setPage(1); }}>Clear</Button>
        </div>
      </form>

      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!data && !error && <LoadingState message="Loading audit log..." />}
      {data && !error && (
        data.items.length === 0 ? (
          <EmptyState title="No audit entries" description="Nothing matches these filters." />
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <ul className="divide-y divide-slate-100">
              {data.items.map((entry) => (
                <li key={entry.id} className="px-4 py-3">
                  <button type="button" className="w-full text-left" aria-expanded={open === entry.id} onClick={() => setOpen(open === entry.id ? null : entry.id)}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-slate-900">{humanizeAction(entry.action)}</span>
                        <Badge variant={RESULT_VARIANT[entry.result] ?? 'neutral'} size="sm">{entry.result}</Badge>
                      </div>
                      <span className="text-xs text-slate-500">{formatDateTime(entry.occurred_at)}</span>
                    </div>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {entry.staff_email_snapshot ?? 'unknown staff'}
                      {entry.staff_role_snapshot ? ` · ${entry.staff_role_snapshot.replace(/_/g, ' ')}` : ''}
                      {entry.organization_name_snapshot ? ` · ${entry.organization_name_snapshot}` : ''}
                      {entry.ticket_ref ? ` · ticket ${entry.ticket_ref}` : ''}
                    </p>
                    {entry.reason && <p className="mt-1 text-sm text-slate-700">{entry.reason}</p>}
                  </button>
                  {open === entry.id && (
                    <dl className="mt-3 grid gap-2 rounded-lg bg-slate-50 p-3 text-xs sm:grid-cols-2">
                      <div><dt className="font-medium text-slate-500">Action code</dt><dd className="font-mono text-slate-800">{entry.action}</dd></div>
                      <div><dt className="font-medium text-slate-500">Target</dt><dd className="text-slate-800">{entry.target_type ? `${entry.target_type} ${entry.target_id ?? ''}` : '-'}</dd></div>
                      <div>
                        <dt className="font-medium text-slate-500">Organization</dt>
                        <dd className="text-slate-800">
                          {entry.organization_id ? <Link className="text-brand-600 hover:underline" to={`/organizations/${entry.organization_id}`}>{entry.organization_id}</Link> : '-'}
                        </dd>
                      </div>
                      <div><dt className="font-medium text-slate-500">IP / device</dt><dd className="break-all text-slate-800">{entry.ip_address ?? '-'} · {entry.user_agent ?? '-'}</dd></div>
                      {entry.details && (
                        <div className="sm:col-span-2">
                          <dt className="font-medium text-slate-500">Details</dt>
                          <dd><pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all font-mono text-slate-800">{JSON.stringify(entry.details, null, 2)}</pre></dd>
                        </div>
                      )}
                    </dl>
                  )}
                </li>
              ))}
            </ul>
            <div className="border-t border-slate-100 px-4 py-3">
              <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} itemLabel="entries" />
            </div>
          </div>
        )
      )}
    </div>
  );
}
