import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, Mail, UserPlus, UserX } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { Modal } from '../../components/common/Modal';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { useToast } from '../../components/common/Toast';
import { organizationService } from '../../services/organizationService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { useAuth } from '../../hooks/useAuth';
import { formatDate, formatDateTime, initials, ROLE_LABELS, statusVariant } from '../../utils/format';
import type { InviteRequest, InviteResponse, MemberRole, TeamMember } from '../../types/api';
import { ReadOnlyNotice, SettingsSection, type FieldErrors } from './settingsShared';
import { validateEmail } from '../../utils/validation';

const ROLES: MemberRole[] = ['viewer', 'finance', 'admin', 'owner'];

const ROLE_HELP: Record<MemberRole, string> = {
  viewer: 'Read-only access to every module.',
  finance: 'Create and edit customers, quotes, invoices, subscriptions and payments.',
  admin: 'Everything Finance can do, plus settings, team, approvals and refunds.',
  owner: 'Full control, including granting the Owner role.',
};

export function TeamTab({ canEdit }: { canEdit: boolean }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { user, membership, hasRole } = useAuth();
  const isOwner = hasRole('owner');

  const team = useQuery({
    queryKey: queryKeys.organization.team(),
    queryFn: organizationService.listTeam,
  });

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteResult, setInviteResult] = useState<InviteResponse | null>(null);
  const [deactivating, setDeactivating] = useState<TeamMember | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.organization.team() });

  const roleMutation = useMutation({
    mutationFn: ({ id, role }: { id: string; role: MemberRole }) =>
      organizationService.updateMemberRole(id, role),
    onSuccess: (member) => {
      void invalidate();
      showToast('success', 'Role updated', `${member.user.full_name} is now ${ROLE_LABELS[member.role]}.`);
    },
    onError: (err) => showToast('error', 'Could not change role', toApiError(err).message),
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => organizationService.deactivateMember(id),
    onSuccess: () => {
      void invalidate();
      setDeactivating(null);
      showToast('success', 'Member deactivated', 'Their sessions for this organization were revoked.');
    },
    onError: (err) => showToast('error', 'Could not deactivate', toApiError(err).message),
  });

  const handleInvited = (result: InviteResponse, resent = false) => {
    setInviteOpen(false);
    setInviteResult(result.invite_url ? result : null);
    void invalidate();
    showToast(
      result.invite_url ? 'warning' : 'success',
      result.invite_url ? 'Invitation Created (Action Required)' : resent ? 'Invitation Resent' : 'Invitation Sent',
      result.invite_url
        ? `Email could not be delivered to ${result.user.email}. Share the invitation link shown above.`
        : `An invitation email was sent to ${result.user.email}.`
    );
  };

  // BUG-34: re-inviting the same email rotates the link and resets its expiry (the old link stops working).
  const resendMutation = useMutation({
    mutationFn: (m: TeamMember) =>
      organizationService.invite({ email: m.user.email, role: m.role, full_name: m.user.full_name }),
    onSuccess: (result) => handleInvited(result, true),
    onError: (err) => showToast('error', 'Could not resend the invitation', toApiError(err).message),
  });

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showToast('success', 'Copied', 'Invitation link copied to clipboard.');
    } catch {
      showToast('warning', 'Copy failed', 'Select the link and copy it manually.');
    }
  };

  const members = team.data ?? [];
  const activeOwners = members.filter((m) => m.role === 'owner' && m.status === 'active').length;

  return (
    <div className="space-y-5">
      {!canEdit && <ReadOnlyNotice what="team membership" />}

      <SettingsSection
        title="Members"
        description="People with access to this organization and their roles."
      >
        {canEdit && (
          <div className="flex justify-end -mt-1">
            <Button size="sm" onClick={() => setInviteOpen(true)} leadingIcon={<UserPlus className="w-3.5 h-3.5" />}>
              Invite member
            </Button>
          </div>
        )}

        {inviteResult?.invite_url && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 space-y-2">
            <p className="text-xs text-amber-800 leading-relaxed">
              Email delivery is not configured on this server, so the invitation for{' '}
              <span className="font-semibold">{inviteResult.user.email}</span> was not emailed. Share
              this link with them directly — it expires {formatDateTime(inviteResult.invite_expires_at)}.
            </p>
            <div className="flex items-stretch gap-2">
              <input
                readOnly
                value={inviteResult.invite_url}
                onFocus={(e) => e.currentTarget.select()}
                className="flex-1 min-w-0 rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-mono text-slate-700"
                aria-label="Invitation link"
              />
              <Button type="button" variant="outline" onClick={() => void copy(inviteResult.invite_url ?? '')} leadingIcon={<Copy className="w-3.5 h-3.5" />}>
                Copy
              </Button>
            </div>
            <button type="button" onClick={() => setInviteResult(null)} className="text-[11px] text-amber-700 underline">
              Dismiss
            </button>
          </div>
        )}

        {team.isPending ? (
          <LoadingState message="Loading team..." className="py-8" />
        ) : team.isError ? (
          <ErrorState message={toApiError(team.error).message} onRetry={() => void team.refetch()} />
        ) : (
          <div className="overflow-x-auto -mx-5">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="text-xs font-semibold text-slate-500 uppercase tracking-wider text-left border-b border-slate-100">
                  <th className="py-2 px-5">Member</th>
                  <th className="py-2 px-3">Role</th>
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3">Joined</th>
                  {canEdit && <th className="py-2 px-5 text-right">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {members.map((m) => {
                  const isSelf = m.user.id === user?.id || m.id === membership?.id;
                  const isDeactivated = m.status === 'deactivated';
                  const lastOwner = m.role === 'owner' && activeOwners <= 1;
                  const canChangeRole = canEdit && !isSelf && !isDeactivated && (isOwner || m.role !== 'owner');
                  const canDeactivate = canEdit && !isSelf && !isDeactivated && (isOwner || m.role !== 'owner') && !lastOwner;
                  return (
                    <tr key={m.id} className={isDeactivated ? 'opacity-60' : undefined}>
                      <td className="py-3 px-5">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-8 h-8 rounded-full bg-slate-100 text-slate-600 text-xs font-semibold flex items-center justify-center shrink-0 overflow-hidden">
                            {m.user.avatar_url ? (
                              <img
                                src={m.user.avatar_url}
                                alt={m.user.full_name || m.user.email}
                                className="w-full h-full object-cover"
                                onError={(e) => {
                                  (e.target as HTMLElement).style.display = 'none';
                                }}
                              />
                            ) : (
                              initials(m.user.full_name, m.user.email[0]?.toUpperCase())
                            )}
                          </div>
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-slate-900 truncate">
                              {m.user.full_name || m.user.email}
                              {isSelf && <span className="ml-1.5 text-[10px] text-slate-400 font-normal">(you)</span>}
                            </p>
                            <p className="text-xs text-slate-500 truncate">{m.user.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        {canChangeRole ? (
                          <Select
                            aria-label={`Role for ${m.user.email}`}
                            value={m.role}
                            disabled={roleMutation.isPending}
                            onChange={(e) => roleMutation.mutate({ id: m.id, role: e.target.value as MemberRole })}
                            options={ROLES.filter((r) => isOwner || r !== 'owner').map((r) => ({ value: r, label: ROLE_LABELS[r] }))}
                            className="py-1.5 text-xs w-32"
                          />
                        ) : (
                          <Badge variant={m.role === 'owner' ? 'primary' : 'neutral'} size="sm">
                            {ROLE_LABELS[m.role]}
                          </Badge>
                        )}
                      </td>
                      <td className="py-3 px-3">
                        <Badge variant={statusVariant(m.status)} size="sm" dot>
                          {m.status}
                        </Badge>
                        {m.status === 'invited' && m.invite_expires_at && (
                          <p className="text-[10px] text-slate-400 mt-1">Expires {formatDate(m.invite_expires_at)}</p>
                        )}
                      </td>
                      <td className="py-3 px-3 text-xs text-slate-500 whitespace-nowrap">
                        {m.accepted_at ? formatDate(m.accepted_at) : m.invited_by ? `Invited by ${m.invited_by.full_name}` : '—'}
                      </td>
                      {canEdit && (
                        <td className="py-3 px-5 text-right">
                          {m.status === 'invited' && !isSelf && (isOwner || m.role !== 'owner') && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => resendMutation.mutate(m)}
                              disabled={resendMutation.isPending}
                              leadingIcon={<Mail className="w-3.5 h-3.5" />}
                            >
                              Resend invitation
                            </Button>
                          )}
                          {canDeactivate && (
                            <Button variant="ghost" size="sm" className="text-rose-600 hover:bg-rose-50" onClick={() => setDeactivating(m)} leadingIcon={<UserX className="w-3.5 h-3.5" />}>
                              Deactivate
                            </Button>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
                {members.length === 0 && (
                  <tr>
                    <td colSpan={canEdit ? 5 : 4} className="py-8 text-center text-xs text-slate-400">
                      No members found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </SettingsSection>

      <SettingsSection title="Roles">
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          {ROLES.map((r) => (
            <div key={r} className="rounded-lg border border-slate-200 bg-slate-50/60 px-3.5 py-2.5">
              <dt className="font-semibold text-slate-800">{ROLE_LABELS[r]}</dt>
              <dd className="text-slate-500 mt-0.5 leading-relaxed">{ROLE_HELP[r]}</dd>
            </div>
          ))}
        </dl>
      </SettingsSection>

      <InviteMemberModal
        isOpen={inviteOpen}
        onClose={() => setInviteOpen(false)}
        canGrantOwner={isOwner}
        onCopy={copy}
        onInvited={(result) => handleInvited(result)}
      />

      <ConfirmDialog
        isOpen={deactivating !== null}
        onClose={() => setDeactivating(null)}
        onConfirm={() => {
          if (deactivating) deactivateMutation.mutate(deactivating.id);
        }}
        title="Deactivate member?"
        description={
          deactivating
            ? `${deactivating.user.full_name || deactivating.user.email} will lose access to this organization immediately and their active sessions will be signed out.`
            : undefined
        }
        confirmLabel="Deactivate"
        variant="danger"
        isLoading={deactivateMutation.isPending}
      />
    </div>
  );
}

function InviteMemberModal({
  isOpen,
  onClose,
  canGrantOwner,
  onInvited,
  onCopy,
}: {
  isOpen: boolean;
  onClose: () => void;
  canGrantOwner: boolean;
  onInvited: (result: InviteResponse) => void;
  onCopy: (text: string) => void;
}) {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [role, setRole] = useState<MemberRole>('finance');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pendingResult, setPendingResult] = useState<InviteResponse | null>(null);

  const mutation = useMutation({
    mutationFn: (body: InviteRequest) => organizationService.invite(body),
    onSuccess: (result) => {
      setEmail('');
      setFullName('');
      setRole('finance');
      setErrors({});
      setFormError(null);
      if (result.invite_url) {
        setPendingResult(result);
      } else {
        onInvited(result);
      }
    },
    onError: (err) => {
      const fields = fieldErrors(err);
      setErrors(fields);
      setFormError(Object.keys(fields).length === 0 ? toApiError(err).message : null);
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setErrors({});
    setFormError(null);
    const emailError = validateEmail(email, { required: true });
    if (emailError) {
      setErrors({ email: emailError });
      return;
    }
    const body: InviteRequest = { email: email.trim(), role };
    if (fullName.trim()) body.full_name = fullName.trim();
    mutation.mutate(body);
  };

  const handleDone = () => {
    const res = pendingResult;
    setPendingResult(null);
    if (res) onInvited(res);
    else onClose();
  };

  if (pendingResult?.invite_url) {
    return (
      <Modal
        isOpen={isOpen}
        onClose={handleDone}
        title="Invitation Link Ready"
        description="Outbound email delivery is not configured or reachable on this server. Share this link directly with the user so they can join."
        size="sm"
        footer={
          <Button variant="primary" size="sm" onClick={handleDone}>
            Done
          </Button>
        }
      >
        <div className="space-y-3">
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3.5 space-y-2.5">
            <p className="text-xs text-amber-900 leading-relaxed font-medium">
              Copy and send this link to <span className="font-bold">{pendingResult.user.email}</span> to accept their{' '}
              <span className="font-bold">{ROLE_LABELS[pendingResult.role]}</span> invitation:
            </p>
            <div className="flex items-stretch gap-2">
              <input
                readOnly
                value={pendingResult.invite_url}
                onFocus={(e) => e.currentTarget.select()}
                className="flex-1 min-w-0 rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-mono text-slate-700 select-all"
                aria-label="Invitation link"
              />
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={() => void onCopy(pendingResult.invite_url ?? '')}
                leadingIcon={<Copy className="w-3.5 h-3.5" />}
              >
                Copy
              </Button>
            </div>
          </div>
          <p className="text-[11px] text-slate-500 leading-snug">
            Tip: To send invitations automatically via email, configure your SMTP server in <strong>Settings &gt; Integrations &gt; Email (SMTP)</strong>.
          </p>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Invite a team member"
      description="They will receive an email with a link to join. If email is not configured, a link is shown for you to share."
      size="sm"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button size="sm" type="submit" form="invite-member-form" isLoading={mutation.isPending} leadingIcon={<Mail className="w-3.5 h-3.5" />}>
            Send invitation
          </Button>
        </>
      }
    >
      <form id="invite-member-form" onSubmit={submit} className="space-y-4" noValidate>
        {formError && (
          <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-700 font-medium">
            {formError}
          </div>
        )}
        <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} autoFocus />
        <Input label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.full_name} helperText="Optional — used in the invitation." />
        <Select
          label="Role"
          value={role}
          onChange={(e) => setRole(e.target.value as MemberRole)}
          error={errors.role}
          options={ROLES.filter((r) => canGrantOwner || r !== 'owner').map((r) => ({ value: r, label: ROLE_LABELS[r] }))}
          helperText={ROLE_HELP[role]}
        />
      </form>
    </Modal>
  );
}
