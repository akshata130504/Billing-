import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ShieldAlert } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';
import { SCOPE_LABELS, platformAccessService, type PlatformAccessGrant } from '../../services/platformAccessService';

const STATUS_VARIANT: Record<string, 'warning' | 'success' | 'danger' | 'neutral' | 'info'> = {
  pending: 'warning', approved: 'info', active: 'success', denied: 'neutral', cancelled: 'neutral', revoked: 'danger', expired: 'neutral',
};

const when = (v: string | null) => (v ? new Date(v).toLocaleString() : '-');

/**
 * Settings > Platform access: Rooman platform support can only see this organization's data with
 * a request an Owner approves here - scoped, read-only and time-limited. Owners approve or deny;
 * Owners and Admins can revoke at any time. Every access is listed in the audit log.
 */
export function PlatformAccessTab() {
  const { hasRole } = useAuth();
  const isOwner = hasRole('owner');
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState<{ grant: PlatformAccessGrant; action: 'deny' | 'revoke' } | null>(null);
  const [reason, setReason] = useState('');
  const grants = useQuery({ queryKey: ['platform-access'], queryFn: platformAccessService.list });

  const done = (title: string) => {
    showToast('success', title);
    setConfirm(null);
    setReason('');
    void queryClient.invalidateQueries({ queryKey: ['platform-access'] });
    void queryClient.invalidateQueries({ queryKey: ['platform-access-active'] });
  };
  const failed = (err: unknown) => showToast('error', 'That did not work', toApiError(err).message);
  const approve = useMutation({ mutationFn: platformAccessService.approve, onSuccess: () => done('Access approved'), onError: failed });
  const decide = useMutation({
    mutationFn: ({ grant, action }: { grant: PlatformAccessGrant; action: 'deny' | 'revoke' }) =>
      action === 'deny' ? platformAccessService.deny(grant.id, reason || undefined) : platformAccessService.revoke(grant.id, reason || undefined),
    onSuccess: (_d, v) => done(v.action === 'deny' ? 'Request denied' : 'Access revoked'),
    onError: failed,
  });

  if (grants.isPending) return <LoadingState message="Loading platform access..." />;
  if (grants.isError) return <ErrorState message={toApiError(grants.error).message} onRetry={() => void grants.refetch()} />;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs">
        <h2 className="text-base font-semibold text-slate-900">Platform access</h2>
        <p className="mt-1 text-sm text-slate-600">
          Rooman platform support cannot see your data unless an Owner approves a request here. Access is read-only,
          limited to the areas listed, and ends automatically. Owners and Admins can revoke it at any time, and every
          view is recorded in your audit log.
        </p>
      </div>
      {grants.data.length === 0 ? (
        <EmptyState title="No platform access requests" description="Requests from Rooman support will appear here for approval." />
      ) : (
        <ul className="space-y-3">
          {grants.data.map((g) => {
            const open = g.status === 'approved' || g.status === 'active';
            return (
              <li key={g.id} className={`rounded-xl border bg-white p-4 shadow-2xs ${g.is_emergency ? 'border-rose-300' : 'border-slate-200'}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      {g.requested_by?.full_name ?? 'Rooman platform staff'}
                      <span className="ml-2 font-normal text-slate-500">{g.requested_by?.role?.replace(/_/g, ' ')}</span>
                    </p>
                    <p className="text-xs text-slate-500">Ticket {g.ticket_ref} · requested {when(g.created_at)} · {g.requested_duration_minutes} min</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {g.is_emergency && <Badge variant="danger"><ShieldAlert className="mr-1 inline h-3 w-3" />Emergency</Badge>}
                    <Badge variant={STATUS_VARIANT[g.status] ?? 'neutral'} dot>{g.status}</Badge>
                  </div>
                </div>
                <p className="mt-2 text-sm text-slate-700">{g.reason}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {g.scopes.map((s) => <Badge key={s} variant="neutral" size="sm">{SCOPE_LABELS[s] ?? s}</Badge>)}
                </div>
                <p className="mt-2 text-xs text-slate-500">
                  {g.approved_at ? `Approved ${when(g.approved_at)}${g.approved_by ? ` by ${g.approved_by.full_name}` : ''}. ` : ''}
                  {g.expires_at ? `Ends ${when(g.expires_at)}. ` : ''}
                  {g.request_count ? `${g.request_count} view(s) so far. ` : ''}
                  {g.revoke_reason ? `Revoked: ${g.revoke_reason}. ` : ''}
                  {g.denied_reason ? `Denied: ${g.denied_reason}.` : ''}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {isOwner && g.status === 'pending' && !g.is_emergency && (
                    <>
                      <Button size="sm" onClick={() => approve.mutate(g.id)} isLoading={approve.isPending}>Approve</Button>
                      <Button size="sm" variant="outline" onClick={() => setConfirm({ grant: g, action: 'deny' })}>Deny</Button>
                    </>
                  )}
                  {(open || g.status === 'pending') && (
                    <Button size="sm" variant="danger" onClick={() => setConfirm({ grant: g, action: 'revoke' })}>Revoke now</Button>
                  )}
                </div>
                {confirm?.grant.id === g.id && (
                  <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <label className="text-xs font-medium text-slate-600" htmlFor={`reason-${g.id}`}>
                      {confirm.action === 'deny' ? 'Reason for denying (optional)' : 'Reason for revoking (optional)'}
                    </label>
                    <input id={`reason-${g.id}`} value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)}
                      className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
                    <div className="mt-2 flex gap-2">
                      <Button size="sm" variant="danger" onClick={() => decide.mutate(confirm)} isLoading={decide.isPending}>
                        {confirm.action === 'deny' ? 'Deny request' : 'Revoke access'}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirm(null)}>Cancel</Button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
