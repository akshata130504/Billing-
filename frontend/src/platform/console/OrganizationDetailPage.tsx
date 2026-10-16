import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
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
  type TenantAdmin,
} from '../consoleApi';
import { PlatformApiError } from '../platformApi';
import { ActionDialog } from './ActionDialog';
import { EntitlementsPanel } from './EntitlementsPanel';
import { ProvisionAdminDialog } from './ProvisionAdminDialog';
import { GrantRequestDialog } from './AccessGrantsPage';
import { ADMIN, useConsole } from './ConsoleContext';
import { Field, Section, StatusBadge, formatDate, formatDateTime, humanizeAction } from './ui';

const ACTION_COPY: Record<LifecycleAction, { description: string; notes: (org: OrganizationDetail) => string[]; danger?: boolean }> = {
  approve: {
    description: 'Approves this organization for Rooman Billing. Tenant users will gain full access to their workspace.',
    notes: () => ['The organization status transitions from Pending Approval to Active.', 'Billing automation is enabled.'],
  },
  reject: {
    description: 'Rejects this organization registration. A mandatory explanation must be provided and will be shown to the tenant Owner.',
    notes: () => ['The organization status transitions to Rejected.', 'Tenant users will see this rejection explanation when attempting to access the workspace.'],
    danger: true,
  },
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
  revoke_sessions: {
    description: "Signs every tenant user and customer-portal user out of this organization. They can sign in again.",
    notes: () => ['Only this organization\'s sessions end; users keep their accounts, roles and passwords.'],
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
  const { hasRole } = useConsole();
  const [requestingAccess, setRequestingAccess] = useState(false);
  const [org, setOrg] = useState<OrganizationDetail | null>(null);
  const [activity, setActivity] = useState<Page<AuditEntry> | null>(null);
  const [activityPage, setActivityPage] = useState(1);
  const [history, setHistory] = useState<Page<AuditEntry> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [action, setAction] = useState<LifecycleAction | null>(null);
  const [admins, setAdmins] = useState<TenantAdmin[] | null>(null);
  const [provisioning, setProvisioning] = useState(false);
  const [adminAction, setAdminAction] = useState<{
    action: 'deactivate' | 'reactivate' | 'revoke_sessions';
    admin: TenantAdmin;
  } | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setOrg(await consoleApi.organization(organizationId));
    } catch (err) {
      if (err instanceof PlatformApiError && err.status === 404) setNotFound(true);
      else setError(err instanceof PlatformApiError ? err.message : 'Could not load this organization.');
    }
  }, [organizationId]);

  const loadAdmins = useCallback(async () => {
    if (!hasRole(ADMIN)) return;
    try {
      setAdmins(await consoleApi.tenantAdmins(organizationId));
    } catch {
      setAdmins(null);
    }
  }, [organizationId, hasRole]);

  const loadActivity = useCallback(async () => {
    try {
      const [all, lifecycle] = await Promise.all([
        consoleApi.organizationActivity(organizationId, activityPage),
        consoleApi.organizationActivity(organizationId, 1, true),
      ]);
      setActivity(all);
      setHistory(lifecycle);
    } catch {
      setActivity(null);
      setHistory(null);
    }
  }, [organizationId, activityPage]);

  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    void loadAdmins();
  }, [loadAdmins]);
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

      {org.status === 'pending_approval' && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h3 className="text-base font-semibold text-amber-900">Organization Pending Super Admin Approval</h3>
              <p className="mt-1 text-sm text-amber-700">
                This newly registered organization requires Super Admin review and approval before tenant users can access Rooman Billing.
              </p>
              <div className="mt-2 text-xs text-amber-800">
                Requested by: <span className="font-medium">{org.owners.length > 0 ? `${org.owners[0].full_name} (${org.owners[0].email})` : 'Tenant Owner'}</span> · Registered: {formatDateTime(org.created_at)}
              </div>
            </div>
            {hasRole(ADMIN) && (
              <div className="flex gap-2">
                <Button size="sm" variant="danger" onClick={() => setAction('reject')}>
                  Reject Organization
                </Button>
                <Button size="sm" variant="primary" onClick={() => setAction('approve')}>
                  Approve Organization
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

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
                {life.automation_running
                  ? <span className="text-emerald-700">Running</span>
                  : <span className="text-amber-700">{life.automation_label ?? 'Paused'}</span>}
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

          {hasRole(ADMIN) && (
            <Section
              title="Tenant Administrators"
              description="Admin accounts for this tenant. Owner accounts are protected and cannot be deactivated or downgraded."
              actions={org.status === 'active' && org.module_access === 'entitled'
                ? <Button size="sm" onClick={() => setProvisioning(true)}>Create Admin</Button>
                : undefined}
            >
              <ProvisionAdminDialog
                isOpen={provisioning}
                organizationId={org.id}
                organizationName={org.name}
                onClose={() => setProvisioning(false)}
                onProvisioned={() => void loadAdmins()}
              />
              {!admins ? (
                <LoadingState message="Loading tenant administrators..." />
              ) : admins.length === 0 ? (
                <p className="text-sm text-slate-500">No administrators found.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-xs font-semibold text-slate-500">
                        <th className="pb-2">Name & Email</th>
                        <th className="pb-2">Role</th>
                        <th className="pb-2">Status</th>
                        <th className="pb-2">2FA</th>
                        <th className="pb-2">Live Sessions</th>
                        <th className="pb-2 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {admins.map((admin) => (
                        <tr key={admin.membership_id} className="text-slate-800">
                          <td className="py-2.5">
                            <div className="font-medium text-slate-900">{admin.full_name}</div>
                            <div className="text-xs text-slate-500">{admin.email}</div>
                          </td>
                          <td className="py-2.5">
                            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${admin.role === 'owner' ? 'bg-purple-50 text-purple-700 border border-purple-200' : 'bg-blue-50 text-blue-700 border border-blue-200'}`}>
                              {admin.role === 'owner' ? 'Owner (Protected)' : 'Admin'}
                            </span>
                          </td>
                          <td className="py-2.5">
                            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${admin.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                              {admin.status}
                            </span>
                          </td>
                          <td className="py-2.5 text-xs text-slate-600">
                            {admin.has_2fa ? 'Enabled' : 'Disabled'}
                          </td>
                          <td className="py-2.5 text-xs text-slate-600">
                            {admin.live_sessions}
                          </td>
                          <td className="py-2.5 text-right">
                            {admin.role === 'owner' ? (
                              <span className="text-xs italic text-slate-400">Protected</span>
                            ) : (
                              <div className="flex justify-end gap-1.5">
                                {admin.status === 'active' ? (
                                  <>
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className="text-xs px-2 py-1 h-auto"
                                      onClick={() => setAdminAction({ action: 'revoke_sessions', admin })}
                                    >
                                      Revoke Sessions
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="danger"
                                      className="text-xs px-2 py-1 h-auto"
                                      onClick={() => setAdminAction({ action: 'deactivate', admin })}
                                    >
                                      Deactivate
                                    </Button>
                                  </>
                                ) : admin.status === 'deactivated' ? (
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="text-xs px-2 py-1 h-auto text-emerald-700 hover:bg-emerald-50"
                                    onClick={() => setAdminAction({ action: 'reactivate', admin })}
                                  >
                                    Reactivate
                                  </Button>
                                ) : (
                                  // BUG-32: an invited Admin has not accepted yet; reactivating would skip acceptance.
                                  <span className="text-xs italic text-slate-400">Invitation pending</span>
                                )}
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Section>
          )}

          <Section title="Lifecycle history" description="Status changes, refused attempts, automation pauses and session revocations.">
            {!history ? (
              <LoadingState message="Loading history..." />
            ) : history.items.length === 0 ? (
              <p className="text-sm text-slate-500">No lifecycle changes yet.</p>
            ) : (
              <ol className="relative ml-2 space-y-4 border-l border-slate-200 pl-5">
                {history.items.map((entry) => (
                  <li key={entry.id}>
                    <span className={`absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full ${entry.result === 'success' ? 'bg-brand-600' : 'bg-amber-500'}`} aria-hidden="true" />
                    <p className="text-sm font-medium text-slate-900">{humanizeAction(entry.action)}{entry.result !== 'success' ? ` (${entry.result})` : ''}</p>
                    <p className="text-xs text-slate-500">
                      {formatDateTime(entry.occurred_at)} · {entry.staff_email_snapshot ?? 'unknown'}{entry.ticket_ref ? ` · ticket ${entry.ticket_ref}` : ''}
                    </p>
                    {entry.reason && <p className="mt-0.5 text-sm text-slate-700">{entry.reason}</p>}
                  </li>
                ))}
              </ol>
            )}
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
          <EntitlementsPanel organizationId={org.id} status={org.status} />
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
          <Section title="Documents" description="Counts only - records and amounts are never shown.">
            <dl className="grid grid-cols-2 gap-3">
              {Object.entries(org.documents).map(([key, count]) => (
                <Field key={key} label={key.replace(/_count$/, '').replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()) + 's'}>{count}</Field>
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
              Platform staff cannot open this organization's customers, invoices or payments without an access grant:
              scoped, read-only and time-limited, approved by the organization's Owner.
            </p>
            {hasRole(ADMIN, 'platform_support') && (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => setRequestingAccess(true)}>Request access</Button>
                <Link to="/access-grants" className="self-center text-sm font-medium text-brand-600 hover:underline">Access grants</Link>
              </div>
            )}
          </Section>
        </div>
      </div>

      <GrantRequestDialog isOpen={requestingAccess} organization={{ id: org.id, name: org.name }}
        onClose={() => setRequestingAccess(false)}
        onDone={() => { setRequestingAccess(false); showToast('success', 'Request sent to the tenant Owner'); }} />
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
      {adminAction && (
        <ActionDialog
          isOpen
          title={`${adminAction.action === 'deactivate' ? 'Deactivate' : adminAction.action === 'reactivate' ? 'Reactivate' : 'Revoke Sessions'}: ${adminAction.admin.email}`}
          description={`Organization: ${org.name}. Target admin: ${adminAction.admin.full_name} (${adminAction.admin.email}).`}
          notes={[
            adminAction.action === 'deactivate'
              ? 'The tenant Admin account will be deactivated and all active sessions will be terminated immediately.'
              : adminAction.action === 'reactivate'
              ? 'The tenant Admin account will be restored to active.'
              : 'All active sessions for this tenant Admin in this organization will be terminated.',
          ]}
          danger={adminAction.action !== 'reactivate'}
          confirmLabel={adminAction.action === 'deactivate' ? 'Deactivate Admin' : adminAction.action === 'reactivate' ? 'Reactivate Admin' : 'Revoke Sessions'}
          onClose={() => setAdminAction(null)}
          onSubmit={(body) => {
            if (adminAction.action === 'deactivate') {
              return consoleApi.deactivateTenantAdmin(org.id, adminAction.admin.user_id, body);
            } else if (adminAction.action === 'reactivate') {
              return consoleApi.reactivateTenantAdmin(org.id, adminAction.admin.user_id, body);
            } else {
              return consoleApi.revokeTenantAdminSessions(org.id, adminAction.admin.user_id, body);
            }
          }}
          onDone={(res) => {
            showToast('success', res.message);
            setAdminAction(null);
            void loadAdmins();
            void loadActivity();
          }}
        />
      )}
    </div>
  );
}
