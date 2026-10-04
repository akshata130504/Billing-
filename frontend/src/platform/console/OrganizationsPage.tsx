import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Search } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { PageHeader } from '../../components/common/PageHeader';
import { Pagination } from '../../components/common/Pagination';
import { STATUS_LABELS, consoleApi, type DirectoryQuery, type OrgStatus, type OrganizationSummary, type Page } from '../consoleApi';
import { PlatformApiError } from '../platformApi';
import { StatusBadge, formatDate } from './ui';

const PAGE_SIZE = 25;
const SORTS: { value: NonNullable<DirectoryQuery['sort']>; label: string }[] = [
  { value: 'created_at', label: 'Created' },
  { value: 'updated_at', label: 'Updated' },
  { value: 'name', label: 'Name' },
  { value: 'status', label: 'Status' },
];

export function OrganizationsPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const status = (params.get('status') ?? '') as OrgStatus | '';
  const sort = (params.get('sort') ?? 'created_at') as NonNullable<DirectoryQuery['sort']>;
  const direction = (params.get('direction') ?? 'desc') as 'asc' | 'desc';
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1);

  const [search, setSearch] = useState(q);
  const [data, setData] = useState<Page<OrganizationSummary> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)));
    if (!('page' in changes)) next.delete('page');
    setParams(next, { replace: true });
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await consoleApi.organizations({ q, status, sort, direction, page, page_size: PAGE_SIZE }));
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load organizations.');
    } finally {
      setLoading(false);
    }
  }, [q, status, sort, direction, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const submitSearch = (e: FormEvent) => {
    e.preventDefault();
    update({ q: search.trim() });
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Organizations" subtitle="Tenant directory - metadata only. Financial and customer records are never shown here." />

      <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:flex-row md:items-end">
        <form onSubmit={submitSearch} className="flex flex-1 gap-2" role="search">
          <label className="sr-only" htmlFor="org-search">Search organizations</label>
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <input
              id="org-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              maxLength={100}
              placeholder="Search by name, slug or id"
              className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
            />
          </div>
          <Button type="submit" size="sm">Search</Button>
        </form>
        <div className="flex flex-wrap gap-2">
          <label className="text-xs font-medium text-slate-600">
            Status
            <select
              aria-label="Filter by status"
              value={status}
              onChange={(e) => update({ status: e.target.value })}
              className="mt-1 block rounded-lg border border-slate-300 px-2 py-2 text-sm"
            >
              <option value="">All statuses</option>
              {(Object.keys(STATUS_LABELS) as OrgStatus[]).map((s) => (
                <option key={s} value={s}>{STATUS_LABELS[s]}</option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Sort by
            <select
              aria-label="Sort by"
              value={sort}
              onChange={(e) => update({ sort: e.target.value })}
              className="mt-1 block rounded-lg border border-slate-300 px-2 py-2 text-sm"
            >
              {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Order
            <select
              aria-label="Sort order"
              value={direction}
              onChange={(e) => update({ direction: e.target.value })}
              className="mt-1 block rounded-lg border border-slate-300 px-2 py-2 text-sm"
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </label>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {loading && !data && <LoadingState message="Loading organizations..." />}
      {data && !error && (
        data.items.length === 0 ? (
          <EmptyState
            title="No organizations found"
            description={q || status ? 'No organization matches these filters.' : 'No tenants have signed up yet.'}
          />
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <tr>
                    <th scope="col" className="px-4 py-3">Organization</th>
                    <th scope="col" className="px-4 py-3">Status</th>
                    <th scope="col" className="hidden px-4 py-3 md:table-cell">Members</th>
                    <th scope="col" className="hidden px-4 py-3 sm:table-cell">Created</th>
                    <th scope="col" className="hidden px-4 py-3 lg:table-cell">Updated</th>
                    <th scope="col" className="hidden px-4 py-3 lg:table-cell">Automation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((org) => (
                    <tr key={org.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <Link to={`/organizations/${org.id}`} className="font-medium text-slate-900 hover:text-brand-600">
                          {org.name}
                        </Link>
                        <p className="text-xs text-slate-500">{org.slug}</p>
                      </td>
                      <td className="px-4 py-3"><StatusBadge status={org.status} /></td>
                      <td className="hidden px-4 py-3 text-slate-700 md:table-cell">{org.member_count}</td>
                      <td className="hidden px-4 py-3 text-slate-700 sm:table-cell">{formatDate(org.created_at)}</td>
                      <td className="hidden px-4 py-3 text-slate-700 lg:table-cell">{formatDate(org.updated_at)}</td>
                      <td className="hidden px-4 py-3 lg:table-cell">
                        {org.status === 'active' && !org.jobs_paused ? (
                          <span className="text-emerald-700">Running</span>
                        ) : (
                          <span className="text-amber-700">Paused</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t border-slate-100 px-4 py-3">
              <Pagination
                page={data.page}
                pageSize={data.page_size}
                total={data.total}
                onPageChange={(p) => update({ page: String(p) })}
                itemLabel="organizations"
              />
            </div>
          </div>
        )
      )}
    </div>
  );
}
