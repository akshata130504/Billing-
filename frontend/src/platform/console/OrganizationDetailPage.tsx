import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Lock } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { PageHeader } from '../../components/common/PageHeader';
import { Pagination } from '../../components/common/Pagination';
import { useToast } from '../../components/common/Toast';
import {
  ACTION_LABELS,
  TICKET_REQUIRED,
  consoleApi,
  type AuditEntry,
  type LifecycleAction,
  type OrganizationDetail,
  type Page,
} from '../consoleApi';
import { PlatformApiError } from '../platformApi';
import { ActionDialog } from './ActionDialog';
import { Field, Section, StatusBadge, formatDate, formatDateTime, humanizeAction } from './ui';

const ACTION_COPY: Record<LifecycleAction, { description: string; notes: (org: OrganizationDetail) => string[]; danger?: boolean }> = {
  suspend: {
    description: 'Stops all billing automation for this organization. Tenant sign-in and data are not changed.',
    notes: () => [
      'No renewals, trial charges, dunning retries, reminder emails or recurring expenses will run.',
      'Payment webhooks for money already captured are still recorded.',
    ],
    danger: true,
  },
  reactivate: {
    description: 'Returns the organization to Active. Billing automation stays paused until an administrator resumes it.',
    notes: (org) => [
      'Nothing that fell due during the suspension is replayed automatically.',
      ...(org.lifecycle.renewals_waiting > 0
        ? [`${org.lifecycle.renewals_waiting} subscription renewal(s) are already due and would bill once automation is resumed.`]
        : []),
    ],
  },
  schedule_deletion: {
    description: 'Moves the organization to Pending deletion. Nothing is deleted now; the waiting period can be cancelled.',
    notes: () => ['Billing automation stops immediately.', 'The actual purge is a separate, later step and is not available in this console.'],
    danger: true,
  },
  cancel_deletion: {
    description: 'Cancels the scheduled deletion. The organization returns to Suspended.',
    notes: () => [],
  },
  pause_jobs: {
    description: 'Pauses billing automation for this organization only. Its status does not change.',
    notes: () => ['Scheduled renewals, charges and reminders stop until automation is resumed.'],
    danger: true,
  },
  resume_jobs: {
    description: 'Lets the billing scheduler process this organization again on its next run.',
    notes: (org) =>
      org.lifecycle.renewals_waiting > 0
        ? [`${org.lifecycle.renewals_waiting} subscription renewal(s) are due and will be invoiced on the next scheduler run. Confirm with the tenant first.`]
        : ['No renewals are currently waiting.'],
    danger: true,
  },
};

export function OrganizationDetailPage() {
  const { organizationId = '' } = useParams();
  const { showToast } = useToast();
  const [org, setOrg] = useState<OrganizationDetail | null>(null);
  const [activity, setActivity] = useState<Page<AuditEntry> | null>(null);
  const [activityPage, setActivityPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [action, setAction] = useState<LifecycleAction | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setOrg(await consoleApi.organization(organizationId));
    } catch (err) {
      if (err instanceof PlatformApiError && err.status === 404) setNotFound(true);
      else setError(err instanceof PlatformApiError ? err.message : 'Could not load this organization.');
    }
  }, [organizationId]);

  const loadActivity = useCallback(async () => {
    try {
      setActivity(await consoleApi.organizationActivity(organizationId, activityPage));
    } catch {
      setActivity(null);
    }
  }, [organizationId, activityPage]);

  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    void loadActivity();
  }, [loadActivity]);

  if (notFound) {
    return (
      <div className="space-y-6">
        <PageHeader title="Organization" backTo={{ to: '/organizations', label: 'Organizations' }} />
        <EmptyState title="Organization not found" description="It may have been removed, or the link is wrong." />
      </div>
    );
  }
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!org) return <LoadingState message="Loading organization..." />;

  const life = org.lifecycle;
  const copy = action ? ACTION_COPY[action] : null;

  return (
    <div className="space-y-6">
      <PageHeader
        backTo={{ to: '/organizations', label: 'Organizations' }}
        title={<span className="flex flex-wrap items-center gap-3">{org.name} <StatusBadge status={org.status} /></span>}
        subtitle={`${org.slug} · ${org.id}`}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Section title="Overview">
            <dl className="grid gap-4 sm:grid-cols-2">
              <Field label="Name">{org.name}</Field>
              <Field label="Identifier">{org.slug}</Field>
              <Field label="Created">{formatDateTime(org.created_at)}</Field>
              <Field label="Last updated">{formatDateTime(org.updated_at)}</Field>
              <Field label="Country">{org.country ?? '-'}</Field>
              <Field label="Time zone">{org.timezone ?? '-'}</Field>
              <Field label="Owner contact">
                {org.owners.length === 0 ? '-' : org.owners.map((o) => <div key={o.email}>{o.full_name} · {o.email}</div>)}
              </Field>
            </dl>
          </Section>

          <Section title="Lifecycle" description="Every change needs a reason and is recorded in the platform audit.">
            <dl className="grid gap-4 sm:grid-cols-2">
              <Field label="Status"><StatusBadge status={life.status} /></Field>
              <Field label="Billing automation">
                {life.automation_running ? <span className="text-emerald-700">Running</span> : <span className="text-amber-700">Paused</span>}
              </Field>
              <Field label="Last change">{formatDateTime(life.status_changed_at)}</Field>
              <Field label="Changed by">{life.status_changed_by ? `${life.status_changed_by.full_name} (${life.status_changed_by.email})` : '-'}</Field>
              <Field label="Reason">{life.status_reason ?? '-'}</Field>
              <Field label="Deletion scheduled for">{formatDate(life.deletion_scheduled_for)}</Field>
              <Field label="Renewals waiting">{life.renewals_waiting}</Field>
            </dl>
            <div className="mt-5 flex flex-wrap gap-2">
              {org.allowed_actions.length === 0 && (
                <p className="flex items-center gap-2 text-sm text-slate-500">
                  <Lock className="h-4 w-4" aria-hidden="true" /> Your platform role cannot change this organization's lifecycle.
                </p>
              )}
              {org.allowed_actions.map((a) => (
                <Button
                  key={a}
                  size="sm"
                  variant={ACTION_COPY[a].danger ? 'danger' : 'outline'}
                  onClick={() => setAction(a)}
                >
                  {ACTION_LABELS[a]}
                </Button>
              ))}
            </div>
          </Section>

          <Section title="Platform activity" description="Platform audit entries about this organization (read-only).">
            {!activity ? (
              <LoadingState message="Loading activity..." />
            ) : activity.items.length === 0 ? (
              <EmptyState title="No platform activity yet" description="Views and lifecycle changes appear here." />
            ) : (
              <>
                <ol className="divide-y divide-slate-100">
                  {activity.items.map((entry) => (
                    <li key={entry.id} className="py-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-medium text-slate-900">{humanizeAction(entry.action)}</p>
                        <span className="text-xs text-slate-500">{formatDateTime(entry.occurred_at)}</span>
                      </div>
                      <p className="text-xs text-slate-500">
                        {entry.staff_email_snapshot ?? 'unknown'} · {entry.result}
                        {entry.ticket_ref ? ` · ticket ${entry.ticket_ref}` : ''}
                      </p>
                      {entry.reason && <p className="mt-1 text-sm text-slate-700">{entry.reason}</p>}
                    </li>
                  ))}
                </ol>
                <div className="mt-3">
                  <Pagination page={activity.page} pageSize={activity.page_size} total={activity.total} onPageChange={setActivityPage} itemLabel="entries" />
                </div>
              </>
            )}
          </Section>
        </div>

        <div className="space-y-6">
          <Section title="Members" description="Counts only.">
            <dl className="grid grid-cols-3 gap-3">
              <Field label="Active">{org.members.active}</Field>
              <Field label="Invited">{org.members.invited}</Field>
              <Field label="Deactivated">{org.members.deactivated}</Field>
            </dl>
            <dl className="mt-4 grid grid-cols-2 gap-3">
              {Object.entries(org.members.by_role).map(([role, count]) => (
                <Field key={role} label={role.charAt(0).toUpperCase() + role.slice(1)}>{count}</Field>
              ))}
            </dl>
          </Section>
          <Section title="Security">
            <dl className="grid gap-3">
              <Field label="Members with two-factor sign-in">{org.security.members_with_two_factor} of {org.security.active_members}</Field>
              <Field label="Live tenant sessions">{org.security.live_tenant_sessions}</Field>
            </dl>
          </Section>
          <Section title="Tenant data access">
            <p className="text-sm text-slate-600">
              Platform staff cannot open this organization's customers, invoices or payments. Scoped, time-limited
              access grants approved by the tenant are a future capability and are not available yet.
            </p>
          </Section>
        </div>
      </div>

      {action && copy && (
        <ActionDialog
          isOpen
          title={`${ACTION_LABELS[action]}: ${org.name}`}
          description={copy.description}
          notes={copy.notes(org)}
          danger={copy.danger}
          requireTicket={TICKET_REQUIRED.has(action)}
          confirmLabel={ACTION_LABELS[action].replace(' organization', '')}
          onClose={() => setAction(null)}
          onSubmit={(body) => consoleApi.lifecycle(org.id, action, body)}
          onDone={() => {
            showToast('success', `${ACTION_LABELS[action]} done`, org.name);
            setAction(null);
            void load();
            setActivityPage(1);
            void loadActivity();
          }}
        />
      )}
    </div>
  );
}
