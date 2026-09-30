import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { LogIn, ShieldAlert } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { Modal } from '../../components/common/Modal';
import { PageHeader } from '../../components/common/PageHeader';
import { useToast } from '../../components/common/Toast';
import { consoleApi, type OrganizationSummary } from '../consoleApi';
import {
  REQUESTABLE_SCOPES,
  SCOPE_NAMES,
  TENANT_APP_ORIGIN,
  grantsApi,
  handOffGrant,
  type AccessGrant,
  type GrantRequestBody,
} from '../grantsApi';
import { PlatformApiError } from '../platformApi';
import { ADMIN, useConsole } from './ConsoleContext';
import { StepUpDialog } from './StepUpDialog';
import { formatDateTime } from './ui';

const STATUS_VARIANT: Record<string, 'warning' | 'success' | 'danger' | 'neutral' | 'info'> = {
  pending: 'warning', approved: 'info', active: 'success', denied: 'neutral', cancelled: 'neutral', revoked: 'danger', expired: 'neutral',
};

/** Request, enter and end scoped, time-limited access to ONE tenant (Support and Administrators). */
export function GrantRequestDialog({ isOpen, onClose, onDone, organization, emergency = false }: {
  isOpen: boolean;
  onClose: () => void;
  onDone: (g: AccessGrant) => void;
  organization?: { id: string; name: string } | null;
  emergency?: boolean;
}) {
  const [org, setOrg] = useState<{ id: string; name: string } | null>(organization ?? null);
  const [search, setSearch] = useState('');
  const [results, setResults] = useState<OrganizationSummary[]>([]);
  const [scopes, setScopes] = useState<string[]>(['READ_CUSTOMERS']);
  const [minutes, setMinutes] = useState(emergency ? 30 : 60);
  const [reason, setReason] = useState('');
  const [ticket, setTicket] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setOrg(organization ?? null);
    setScopes(emergency ? ['READ_INVOICES'] : ['READ_CUSTOMERS']);
    setMinutes(emergency ? 30 : 60);
    setReason('');
    setTicket('');
    setError(null);
  }, [isOpen, organization, emergency]);

  const find = async (e: FormEvent) => {
    e.preventDefault();
    try {
      setResults((await consoleApi.organizations({ q: search.trim(), page_size: 8 })).items);
    } catch {
      setResults([]);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!org) return;
    setBusy(true);
    setError(null);
    const body: GrantRequestBody = { organization_id: org.id, scopes, duration_minutes: minutes, reason: reason.trim(), ticket_ref: ticket.trim() };
    try {
      onDone(emergency ? await grantsApi.requestEmergency(body) : await grantsApi.request(body));
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'The request failed.');
    } finally {
      setBusy(false);
    }
  };

  const max = emergency ? 60 : 240;
  const valid = org && reason.trim().length >= 20 && ticket.trim().length >= 2 && minutes >= 5 && minutes <= max;
  return (
    <Modal isOpen={isOpen} onClose={() => !busy && onClose()} size="lg"
      title={emergency ? 'Emergency access (break-glass)' : 'Request tenant access'}
      description={emergency
        ? 'For incidents where the tenant Owner cannot be reached. A DIFFERENT Platform Administrator must approve. Read-only, at most 60 minutes.'
        : 'The tenant Owner must approve. Access is read-only, limited to the areas you choose, and ends automatically.'}>
      <div className="space-y-4">
        {org ? (
          <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm">
            <span>Organization: <strong>{org.name}</strong></span>
            {!organization && <button type="button" className="text-brand-600 underline" onClick={() => setOrg(null)}>Change</button>}
          </div>
        ) : (
          <form onSubmit={find} className="space-y-2" role="search">
            <label className="block text-xs font-medium text-slate-600" htmlFor="grant-org-search">Organization</label>
            <div className="flex gap-2">
              <input id="grant-org-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name, slug or id"
                className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              <Button type="submit" size="sm" variant="outline">Find</Button>
            </div>
            <ul className="divide-y divide-slate-100">
              {results.map((o) => (
                <li key={o.id}>
                  <button type="button" onClick={() => setOrg({ id: o.id, name: o.name })} className="w-full px-2 py-1.5 text-left text-sm hover:bg-slate-50">
                    {o.name} <span className="text-xs text-slate-500">{o.slug}</span>
                  </button>
                </li>
              ))}
            </ul>
          </form>
        )}
        <form onSubmit={submit} className="space-y-4" aria-label="Access request">
          <fieldset>
            <legend className="text-xs font-medium text-slate-600">Areas (read-only; organization profile is always included)</legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {REQUESTABLE_SCOPES.map((s) => (
                <label key={s.value} className="inline-flex items-center gap-2 text-sm text-slate-700">
                  <input type="checkbox" checked={scopes.includes(s.value)}
                    onChange={(e) => setScopes(e.target.checked ? [...scopes, s.value] : scopes.filter((x) => x !== s.value))} />
                  {s.label}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-xs font-medium text-slate-600">
              Duration (minutes, max {max})
              <input type="number" min={5} max={max} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </label>
            <label className="text-xs font-medium text-slate-600">
              {emergency ? 'Incident reference' : 'Ticket reference'}
              <input value={ticket} onChange={(e) => setTicket(e.target.value)} maxLength={100} required
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </label>
          </div>
          <label className="block text-xs font-medium text-slate-600">
            Reason (at least 20 characters; shown to the tenant)
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} maxLength={2000} required
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          </label>
          {error && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" size="sm" variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
            <Button type="submit" size="sm" variant={emergency ? 'danger' : 'primary'} isLoading={busy} disabled={!valid}>
              {emergency ? 'Request emergency access' : 'Send request to the Owner'}
            </Button>
          </div>
        </form>
      </div>
    </Modal>
  );
}

export function AccessGrantsPage() {
  const { me, hasRole } = useConsole();
  const { showToast } = useToast();
  const isAdmin = hasRole(ADMIN);
  const [grants, setGrants] = useState<AccessGrant[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [requesting, setRequesting] = useState<'normal' | 'emergency' | null>(null);
  const [stepUp, setStepUp] = useState<{ title: string; run: () => Promise<void> } | null>(null);
  const [revoking, setRevoking] = useState<AccessGrant | null>(null);
  const [reviewing, setReviewing] = useState<AccessGrant | null>(null);
  const [text, setText] = useState('');

  const load = useCallback(async () => {
    setError(null);
    try {
      setGrants((await grantsApi.list()).items);
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load access grants.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** Run a step-up-protected call; if the server wants a fresh code, ask for it and retry once. */
  const withStepUp = async (title: string, run: () => Promise<void>) => {
    try {
      await run();
    } catch (err) {
      if (err instanceof PlatformApiError && err.code === 'STEP_UP_REQUIRED') {
        setStepUp({ title, run });
        return;
      }
      showToast('error', 'That did not work', err instanceof PlatformApiError ? err.message : undefined);
    }
  };

  const enter = (grant: AccessGrant) => {
    if (!TENANT_APP_ORIGIN) {
      showToast('error', 'Tenant app origin is not configured (VITE_TENANT_APP_ORIGIN).');
      return;
    }
    // Opened synchronously on the click (popup blockers); the token follows by postMessage.
    const win = window.open(`${TENANT_APP_ORIGIN}/platform-access`, `rooman-platform-access-${grant.id}`);
    if (!win) {
      showToast('error', 'Allow pop-ups for the platform console to enter the tenant.');
      return;
    }
    void withStepUp('Enter tenant', async () => {
      const result = await grantsApi.enter(grant.id);
      handOffGrant(win, result.token);
      showToast('success', `Entered ${result.organization.name}`, 'The tenant workspace opened in a new tab.');
      void load();
    });
  };

  const act = async (fn: () => Promise<unknown>, title: string) => {
    try {
      await fn();
      showToast('success', title);
      void load();
    } catch (err) {
      showToast('error', 'That did not work', err instanceof PlatformApiError ? err.message : undefined);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tenant access grants"
        subtitle="Scoped, read-only, time-limited access to one tenant - approved by its Owner (or, in an emergency, by a second Platform Administrator)."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setRequesting('normal')}>Request access</Button>
            {isAdmin && <Button size="sm" variant="danger" onClick={() => setRequesting('emergency')}><ShieldAlert className="mr-1 h-4 w-4" />Emergency access</Button>}
          </div>
        }
      />
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!grants && !error && <LoadingState message="Loading access grants..." />}
      {grants && grants.length === 0 && (
        <EmptyState title="No access grants" description={isAdmin ? 'No platform staff have requested tenant access.' : 'You have not requested tenant access.'} />
      )}
      {grants && grants.length > 0 && (
        <ul className="space-y-3">
          {grants.map((g) => {
            const mine = g.requested_by?.id === me.staff.id;
            const open = g.status === 'approved' || g.status === 'active';
            return (
              <li key={g.id} className={`rounded-xl border bg-white p-4 shadow-sm ${g.is_emergency ? 'border-rose-300' : 'border-slate-200'}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <Link to={`/organizations/${g.organization_id}`} className="text-sm font-semibold text-slate-900 hover:text-brand-600">{g.organization_name}</Link>
                    <p className="text-xs text-slate-500">
                      {g.requested_by?.full_name}{mine ? ' (you)' : ''} · ticket {g.ticket_ref} · {g.requested_duration_minutes} min · requested {formatDateTime(g.created_at)}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {g.is_emergency && <Badge variant="danger">Emergency</Badge>}
                    {g.review_overdue && <Badge variant="warning">Review overdue</Badge>}
                    <Badge variant={STATUS_VARIANT[g.status] ?? 'neutral'} dot>{g.status}</Badge>
                  </div>
                </div>
                <p className="mt-2 text-sm text-slate-700">{g.reason}</p>
                <div className="mt-2 flex flex-wrap gap-1">{g.scopes.map((s) => <Badge key={s} size="sm" variant="neutral">{SCOPE_NAMES[s] ?? s}</Badge>)}</div>
                <p className="mt-2 text-xs text-slate-500">
                  {g.approved_by ? `Approved by ${g.approved_by.full_name}${g.approved_by.kind === 'platform_staff' ? ' (platform)' : ' (tenant Owner)'} ${formatDateTime(g.approved_at)}. ` : ''}
                  {g.expires_at ? `Ends ${formatDateTime(g.expires_at)}. ` : ''}
                  {g.request_count ? `${g.request_count} request(s). ` : ''}
                  {g.revoke_reason ? `Revoked: ${g.revoke_reason}. ` : ''}{g.denied_reason ? `Denied: ${g.denied_reason}. ` : ''}
                  {g.reviewed_at ? `Reviewed ${formatDateTime(g.reviewed_at)}.` : ''}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {mine && open && <Button size="sm" onClick={() => enter(g)}><LogIn className="mr-1 h-4 w-4" />Enter tenant</Button>}
                  {mine && g.status === 'pending' && <Button size="sm" variant="outline" onClick={() => void act(() => grantsApi.cancel(g.id), 'Request cancelled')}>Cancel request</Button>}
                  {(mine || isAdmin) && open && (
                    <Button size="sm" variant="danger" onClick={() => { setRevoking(g); setText(''); }}>Revoke</Button>
                  )}
                  {isAdmin && g.is_emergency && g.status === 'pending' && !mine && (
                    <Button size="sm" variant="danger" onClick={() => void withStepUp('Approve emergency access', async () => {
                      await grantsApi.approveEmergency(g.id);
                      showToast('success', 'Emergency access approved');
                      void load();
                    })}>Approve (second administrator)</Button>
                  )}
                  {isAdmin && g.is_emergency && g.approved_at && !g.reviewed_at && (
                    <Button size="sm" variant="outline" onClick={() => { setReviewing(g); setText(''); }}>Record review</Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <GrantRequestDialog isOpen={requesting !== null} emergency={requesting === 'emergency'} onClose={() => setRequesting(null)}
        onDone={(g) => { setRequesting(null); showToast('success', g.is_emergency ? 'Emergency request sent for second approval' : 'Request sent to the tenant Owner'); void load(); }} />
      <StepUpDialog isOpen={stepUp !== null} title={stepUp?.title ?? ''} onClose={() => setStepUp(null)}
        onVerified={async () => { const run = stepUp?.run; setStepUp(null); if (run) await withStepUp('Confirm', run); }} />
      <Modal isOpen={revoking !== null} onClose={() => setRevoking(null)} title="Revoke access" size="sm">
        <div className="space-y-3">
          <label className="block text-xs font-medium text-slate-600">Reason (at least 10 characters)
            <input value={text} onChange={(e) => setText(e.target.value)} maxLength={300} className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          </label>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="outline" onClick={() => setRevoking(null)}>Cancel</Button>
            <Button size="sm" variant="danger" disabled={text.trim().length < 10}
              onClick={() => { const g = revoking!; setRevoking(null); void act(() => grantsApi.revoke(g.id, text.trim()), 'Access revoked'); }}>Revoke now</Button>
          </div>
        </div>
      </Modal>
      <Modal isOpen={reviewing !== null} onClose={() => setReviewing(null)} title="Post-incident review" size="md">
        <div className="space-y-3">
          <label className="block text-xs font-medium text-slate-600">What happened, what was accessed, and was it justified? (at least 20 characters)
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={4000} className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          </label>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="outline" onClick={() => setReviewing(null)}>Cancel</Button>
            <Button size="sm" disabled={text.trim().length < 20}
              onClick={() => { const g = reviewing!; setReviewing(null); void act(() => grantsApi.review(g.id, text.trim()), 'Review recorded'); }}>Save review</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
