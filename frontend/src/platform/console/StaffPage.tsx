import { useCallback, useEffect, useState } from 'react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { Modal } from '../../components/common/Modal';
import { PageHeader } from '../../components/common/PageHeader';
import { useToast } from '../../components/common/Toast';
import { consoleApi, type StaffDetail, type StaffSummary } from '../consoleApi';
import { PlatformApiError } from '../platformApi';
import { ActionDialog } from './ActionDialog';
import { useConsole } from './ConsoleContext';
import { Field, RoleBadge, formatDateTime } from './ui';

type StaffAction = 'deactivate' | 'activate' | 'revoke-sessions';

const ACTIONS: Record<StaffAction, { label: string; description: string; notes: string[]; danger: boolean }> = {
  deactivate: {
    label: 'Deactivate',
    description: 'The staff member can no longer sign in. All of their sessions end immediately.',
    notes: ['You cannot deactivate yourself or the last active Platform Administrator.'],
    danger: true,
  },
  activate: {
    label: 'Reactivate',
    description: 'The staff member can sign in again with their password and authenticator app.',
    notes: ['Sessions that existed before deactivation stay ended.'],
    danger: false,
  },
  'revoke-sessions': {
    label: 'Revoke sessions',
    description: 'Ends every session of this staff member. They must sign in again with their authenticator.',
    notes: [],
    danger: true,
  },
};

/** Platform staff (Platform Administrator only; the server refuses every other role). */
export function StaffPage() {
  const { me } = useConsole();
  const { showToast } = useToast();
  const [staff, setStaff] = useState<StaffSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<StaffDetail | null>(null);
  const [pending, setPending] = useState<{ member: StaffSummary; action: StaffAction } | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setStaff((await consoleApi.staff()).items);
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load platform staff.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = async (member: StaffSummary) => {
    try {
      setSelected(await consoleApi.staffMember(member.id));
    } catch (err) {
      showToast('error', 'Could not load staff member', err instanceof PlatformApiError ? err.message : undefined);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Platform staff"
        subtitle="Rooman staff who operate the platform. New staff, role changes and 2FA resets are done with the server-side bootstrap command, not here."
      />
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!staff && !error && <LoadingState message="Loading staff..." />}
      {staff && staff.length === 0 && <EmptyState title="No platform staff" description="Create the first administrator with the bootstrap command." />}
      {staff && staff.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="px-4 py-3">Staff member</th>
                  <th scope="col" className="px-4 py-3">Role</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="hidden px-4 py-3 md:table-cell">Last sign-in</th>
                  <th scope="col" className="hidden px-4 py-3 md:table-cell">Security</th>
                  <th scope="col" className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {staff.map((member) => {
                  const self = member.id === me.staff.id;
                  return (
                    <tr key={member.id}>
                      <td className="px-4 py-3">
                        <button type="button" onClick={() => void open(member)} className="text-left font-medium text-slate-900 hover:text-brand-600">
                          {member.full_name}{self ? ' (you)' : ''}
                        </button>
                        <p className="text-xs text-slate-500">{member.email}</p>
                      </td>
                      <td className="px-4 py-3"><RoleBadge role={member.role} /></td>
                      <td className="px-4 py-3">
                        {member.is_active ? <Badge variant="success" dot>Active</Badge> : <Badge variant="neutral" dot>Deactivated</Badge>}
                      </td>
                      <td className="hidden px-4 py-3 text-slate-700 md:table-cell">{formatDateTime(member.last_login_at)}</td>
                      <td className="hidden px-4 py-3 md:table-cell">
                        <div className="flex flex-wrap gap-1">
                          <Badge variant={member.two_factor_enrolled ? 'success' : 'danger'} size="sm">
                            {member.two_factor_enrolled ? '2FA on' : '2FA missing'}
                          </Badge>
                          <Badge variant="neutral" size="sm">{member.active_sessions} session(s)</Badge>
                          {member.sign_in_locked && <Badge variant="warning" size="sm">Sign-in locked</Badge>}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap justify-end gap-2">
                          {member.active_sessions > 0 && (
                            <Button size="sm" variant="outline" onClick={() => setPending({ member, action: 'revoke-sessions' })}>
                              Revoke sessions
                            </Button>
                          )}
                          {member.is_active && !self && (
                            <Button size="sm" variant="danger" onClick={() => setPending({ member, action: 'deactivate' })}>Deactivate</Button>
                          )}
                          {!member.is_active && (
                            <Button size="sm" variant="primary" onClick={() => setPending({ member, action: 'activate' })}>Reactivate</Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Modal isOpen={selected !== null} onClose={() => setSelected(null)} title={selected?.full_name ?? ''} description={selected?.email} size="lg">
        {selected && (
          <div className="space-y-4">
            <dl className="grid gap-3 sm:grid-cols-2">
              <Field label="Role"><RoleBadge role={selected.role} /></Field>
              <Field label="Status">{selected.is_active ? 'Active' : `Deactivated ${formatDateTime(selected.deactivated_at)}`}</Field>
              <Field label="Two-factor sign-in">{selected.two_factor_enrolled ? 'Enrolled' : 'Not enrolled'}</Field>
              <Field label="Last sign-in">{formatDateTime(selected.last_login_at)}</Field>
              <Field label="Created">{formatDateTime(selected.created_at)}</Field>
              <Field label="Sign-in throttle">{selected.sign_in_locked ? 'Locked after failed attempts' : 'Normal'}</Field>
            </dl>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Active sessions</h3>
              {selected.sessions.length === 0 ? (
                <p className="mt-1 text-sm text-slate-500">No active sessions.</p>
              ) : (
                <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
                  {selected.sessions.map((s) => (
                    <li key={s.id} className="px-3 py-2 text-sm">
                      <p className="font-medium text-slate-800">{s.user_agent || 'Unknown device'}{s.current ? ' (this session)' : ''}</p>
                      <p className="text-xs text-slate-500">
                        {s.ip_address ?? 'unknown IP'} · started {formatDateTime(s.created_at)} · last used {formatDateTime(s.last_used_at)} · ends {formatDateTime(s.expires_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </Modal>

      {pending && (
        <ActionDialog
          isOpen
          title={`${ACTIONS[pending.action].label}: ${pending.member.full_name}`}
          description={ACTIONS[pending.action].description}
          notes={ACTIONS[pending.action].notes}
          danger={ACTIONS[pending.action].danger}
          confirmLabel={ACTIONS[pending.action].label}
          onClose={() => setPending(null)}
          onSubmit={(body) => consoleApi.staffAction(pending.member.id, pending.action, body)}
          onDone={() => {
            showToast('success', `${ACTIONS[pending.action].label} done`, pending.member.email);
            setPending(null);
            void load();
          }}
        />
      )}
    </div>
  );
}
