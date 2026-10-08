import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { PageHeader } from '../../components/common/PageHeader';
import { consoleApi, type Dashboard } from '../consoleApi';
import { PlatformApiError, ROLE_LABELS } from '../platformApi';
import { useConsole } from './ConsoleContext';
import { ADMIN } from './ConsoleContext';
import { Field, Section, Stat, StateDot, StatusBadge, formatDate, formatDateTime, humanizeAction } from './ui';

export function DashboardPage() {
  const { me, hasRole } = useConsole();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await consoleApi.dashboard());
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load the dashboard.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <PageHeader title="Platform dashboard" subtitle="Tenant counts and platform health. No tenant financial or customer data is shown here." />
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!data && !error && <LoadingState message="Loading dashboard..." />}
      {data && (
        <>
          {(data.subscription_requests_pending ?? 0) > 0 && (
            <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <span>
                {data.subscription_requests_pending} subscription request{data.subscription_requests_pending === 1 ? ' is' : 's are'} waiting for review.
              </span>
              <Link to="/subscription-requests" className="font-medium text-amber-900 underline hover:no-underline">
                Review subscription requests
              </Link>
            </div>
          )}
          {(data.organizations.pending_approval ?? 0) > 0 && (
            <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <span>
                {data.organizations.pending_approval} organization{data.organizations.pending_approval === 1 ? ' is' : 's are'} waiting for approval.
              </span>
              <Link to="/organizations?status=pending_approval" className="font-medium text-amber-900 underline hover:no-underline">
                Review pending organizations
              </Link>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-8">
            <Stat label="Organizations" value={data.organizations.total ?? 0} />
            <Stat
              label="Pending approval"
              value={data.organizations.pending_approval ?? 0}
              tone={data.organizations.pending_approval ? 'warning' : 'default'}
              hint="New sign-ups awaiting a Platform Administrator"
            />
            <Stat
              label="Subscription requests"
              value={data.subscription_requests_pending ?? 0}
              tone={data.subscription_requests_pending ? 'warning' : 'default'}
              hint="Trial organizations waiting for a Platform Administrator"
            />
            <Stat label="Active" value={data.organizations.active ?? 0} tone="success" />
            <Stat label="Suspended" value={data.organizations.suspended ?? 0} tone={data.organizations.suspended ? 'warning' : 'default'} />
            <Stat label="Pending deletion" value={data.organizations.pending_deletion ?? 0} tone={data.organizations.pending_deletion ? 'danger' : 'default'} />
            <Stat label="New (7 days)" value={data.created_last_7_days} />
            <Stat label="Automation paused" value={data.organizations.jobs_paused ?? 0} hint="Organizations with billing jobs paused" />
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <Section
                title="Recently created organizations"
                actions={<Link to="/organizations" className="text-sm font-medium text-brand-600 hover:underline">View all</Link>}
              >
                {data.recent_organizations.length === 0 ? (
                  <EmptyState title="No organizations yet" description="Organizations appear here as tenants sign up." />
                ) : (
                  <ul className="divide-y divide-slate-100">
                    {data.recent_organizations.map((org) => (
                      <li key={org.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                        <div className="min-w-0">
                          <Link to={`/organizations/${org.id}`} className="font-medium text-slate-900 hover:text-brand-600">
                            {org.name}
                          </Link>
                          <p className="text-xs text-slate-500">{org.slug} · created {formatDate(org.created_at)}</p>
                        </div>
                        <StatusBadge status={org.status} />
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
              <div className="mt-6">
                <Section
                  title="Recent platform activity"
                  description={hasRole(ADMIN) ? 'Latest platform audit events.' : 'Latest organization lifecycle events.'}
                  actions={hasRole(ADMIN) ? <Link to="/audit" className="text-sm font-medium text-brand-600 hover:underline">Audit log</Link> : undefined}
                >
                  {data.recent_activity.length === 0 ? (
                    <p className="text-sm text-slate-500">No platform activity yet.</p>
                  ) : (
                    <ul className="divide-y divide-slate-100">
                      {data.recent_activity.map((entry) => (
                        <li key={entry.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-slate-900">{humanizeAction(entry.action)}</p>
                            <p className="truncate text-xs text-slate-500">
                              {entry.staff_email_snapshot ?? 'unknown'}
                              {entry.organization_name_snapshot ? ` · ${entry.organization_name_snapshot}` : ''}
                            </p>
                          </div>
                          <span className="text-xs text-slate-500">{formatDateTime(entry.occurred_at)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </Section>
              </div>
            </div>
            <div className="space-y-6">
              <Section
                title="Platform health"
                actions={<Link to="/health" className="text-sm font-medium text-brand-600 hover:underline">Details</Link>}
              >
                <ul className="space-y-2">
                  <li><StateDot ok={data.health.api === 'ok'} label={`API: ${data.health.api}`} /></li>
                  <li><StateDot ok={data.health.database === 'connected'} label={`Database: ${data.health.database}`} /></li>
                  <li><StateDot ok={data.health.migrations === 'at_head'} label={`Migrations: ${data.health.migrations.replace(/_/g, ' ')}`} /></li>
                  <li>
                    <StateDot
                      ok={data.scheduler.status === 'ok' ? true : data.scheduler.enabled ? false : null}
                      label={`Scheduler: ${data.scheduler.status}${data.scheduler.last_finished_at ? `, last run ${formatDateTime(data.scheduler.last_finished_at)}` : ''}`}
                    />
                  </li>
                </ul>
              </Section>
              <Section title="Your session">
                <dl className="grid gap-3">
                  <Field label="Signed in as">{me.staff.full_name} ({me.staff.email})</Field>
                  <Field label="Platform role">{ROLE_LABELS[me.staff.role] ?? me.staff.role}</Field>
                  <Field label="Session ends">{formatDateTime(me.session_expires_at)}</Field>
                  <Field label="Platform staff">{data.staff.active} active of {data.staff.total}</Field>
                </dl>
              </Section>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
