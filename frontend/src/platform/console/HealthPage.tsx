import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { PageHeader } from '../../components/common/PageHeader';
import { consoleApi, type Health, type Jobs } from '../consoleApi';
import { ADMIN, OPS, useConsole } from './ConsoleContext';
import { PlatformApiError } from '../platformApi';
import { Field, Section, StateDot, formatDateTime } from './ui';

const COUNT_LABELS: Record<string, string> = {
  renewals: 'Renewals',
  trials_converted: 'Trials converted',
  marked_overdue: 'Marked overdue',
  reminders_sent: 'Reminders sent',
  scheduled_changes_applied: 'Scheduled changes applied',
  dunning_recovered: 'Dunning recovered',
  recurring_expenses_processed: 'Recurring expenses',
  skipped_org_inactive: 'Skipped (suspended or paused)',
};

/** Operational status only: no hosts, connection strings, credentials or environment variables. */
export function HealthPage() {
  const { hasRole } = useConsole();
  const canSeeJobs = hasRole(ADMIN, OPS);
  const [health, setHealth] = useState<Health | null>(null);
  const [jobs, setJobs] = useState<Jobs | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setHealth(await consoleApi.health());
      if (canSeeJobs) setJobs(await consoleApi.jobs());
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load health.');
    } finally {
      setLoading(false);
    }
  }, [canSeeJobs]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="System health"
        subtitle="API, database, migrations, scheduler and platform service status."
        actions={<Button size="sm" variant="outline" onClick={() => void load()} isLoading={loading}><RefreshCw className="mr-1 h-4 w-4" />Refresh</Button>}
      />
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!health && !error && <LoadingState message="Checking health..." />}
      {health && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Services">
            <ul className="space-y-3">
              <li><StateDot ok={health.api.status === 'ok'} label={`API: ${health.api.status} (version ${health.api.version}, ${health.api.environment})`} /></li>
              <li><StateDot ok={health.database.status === 'connected'} label={`Database: ${health.database.status}`} /></li>
              <li>
                <StateDot ok={health.migrations.status === 'at_head'} label={`Migrations: ${health.migrations.status.replace(/_/g, ' ')}`} />
                <p className="ml-5 mt-0.5 font-mono text-xs text-slate-500">current {health.migrations.current ?? '-'} · head {health.migrations.head ?? '-'}</p>
              </li>
              <li><StateDot ok={health.integrations.email_configured} label={`Outbound email ${health.integrations.email_configured ? 'configured' : 'not configured'}`} /></li>
              <li><StateDot ok={health.integrations.payments_configured} label={`Payment gateway ${health.integrations.payments_configured ? 'configured' : 'not configured'}`} /></li>
            </ul>
          </Section>
          <Section title="Billing scheduler" description="The scheduler is a separate process; this console can observe it but never run it.">
            <dl className="grid gap-3 sm:grid-cols-2">
              <Field label="Status"><StateDot ok={health.scheduler.status === 'ok' ? true : health.scheduler.enabled ? false : null} label={health.scheduler.status} /></Field>
              <Field label="Enabled">{health.scheduler.enabled ? 'Yes' : 'No'}</Field>
              <Field label="Last finished run">{formatDateTime(health.scheduler.last_finished_at)}</Field>
              <Field label="Interval">{health.scheduler.interval_minutes ? `${health.scheduler.interval_minutes} min` : '-'}</Field>
              <Field label="Errors in last run">{health.scheduler.last_error_count ?? '-'}</Field>
              <Field label="Total runs">{health.scheduler.total_runs ?? 0}</Field>
            </dl>
            {Object.keys(health.scheduler.last_counts).length > 0 && (
              <dl className="mt-4 grid grid-cols-2 gap-2 border-t border-slate-100 pt-4">
                {Object.entries(health.scheduler.last_counts).map(([key, value]) => (
                  <Field key={key} label={COUNT_LABELS[key] ?? key}>{value}</Field>
                ))}
              </dl>
            )}
          </Section>
          {jobs && (
            <Section title="Background jobs" description="Counts only. The console can observe jobs; it can never run, retry or cancel them.">
              <dl className="grid gap-3 sm:grid-cols-2">
                <Field label="Durable jobs failed (24 h)">{jobs.durable_jobs_failed_24h}</Field>
                <Field label="Organizations not running automation">{jobs.organizations_not_running}</Field>
                <Field label="Webhooks received (24 h)">{jobs.webhooks_received_24h}</Field>
                <Field label="Outbox failed">{jobs.outbox.failed ?? 0}</Field>
              </dl>
              <div className="mt-4 grid gap-4 border-t border-slate-100 pt-4 sm:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Durable jobs</p>
                  <dl className="mt-2 grid grid-cols-2 gap-2">
                    {Object.entries(jobs.durable_jobs).map(([k, v]) => <Field key={k} label={k}>{v}</Field>)}
                  </dl>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Outbox events</p>
                  <dl className="mt-2 grid grid-cols-2 gap-2">
                    {Object.entries(jobs.outbox).map(([k, v]) => <Field key={k} label={k}>{v}</Field>)}
                  </dl>
                </div>
              </div>
            </Section>
          )}
          <Section title="Platform service">
            <dl className="grid gap-3 sm:grid-cols-2">
              <Field label="Platform sign-in">{health.platform.auth_enabled ? 'Enabled' : 'Disabled'}</Field>
              <Field label="Step-up window">{health.platform.step_up_minutes} min</Field>
              <Field label="Session idle timeout">{health.platform.session_idle_minutes} min</Field>
              <Field label="Session maximum">{health.platform.session_max_hours} h</Field>
              <Field label="Deletion waiting period">{health.platform.deletion_waiting_days} days</Field>
            </dl>
          </Section>
        </div>
      )}
    </div>
  );
}
