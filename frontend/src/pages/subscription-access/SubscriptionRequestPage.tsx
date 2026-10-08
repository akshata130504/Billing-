/**
 * Free trial -> subscription request (modules, seats, billing cycle) -> Rooman review.
 *
 * Shown as a page (/subscription) during the trial and once active, and as the whole screen once
 * the trial has ended (routes/index.tsx). Owners and Admins submit; everyone sees the state. The
 * API enforces every rule (roles, one open request, seat minimum, valid modules); this form only
 * helps fill it in.
 */
import { useMemo, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Clock, Loader2, LogOut, Send, XCircle } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Card } from '../../components/common/Card';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { PageHeader } from '../../components/common/PageHeader';
import { useToast } from '../../components/common/Toast';
import { dependents, moduleLabel, trialDaysLeft, withRequirements } from '../../entitlements';
import { useAuth } from '../../hooks/useAuth';
import { errorSummary } from '../../services/apiClient';
import {
  subscriptionAccessService,
  type BillingCycle,
  type SubscriptionRequestOut,
  type SubscriptionState,
} from '../../services/subscriptionAccessService';
import { formatDate, formatDateTime } from '../../utils/format';

export const SUBSCRIPTION_STATE_KEY = ['subscription-requests'] as const;

const CYCLES: Array<{ value: BillingCycle; label: string }> = [
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'annual', label: 'Annual' },
];

const STATUS_BADGE: Record<SubscriptionRequestOut['status'], { label: string; variant: 'warning' | 'success' | 'danger' | 'neutral' }> = {
  submitted: { label: 'Waiting for review', variant: 'warning' },
  approved: { label: 'Approved', variant: 'success' },
  rejected: { label: 'Not approved', variant: 'danger' },
  withdrawn: { label: 'Withdrawn', variant: 'neutral' },
};

function cycleLabel(cycle: string | null | undefined): string {
  return CYCLES.find((c) => c.value === cycle)?.label ?? cycle ?? '';
}

export function SubscriptionRequestPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Organization"
        title="Subscription"
        subtitle="Choose the modules and user seats your organization needs. Rooman reviews every request."
      />
      <SubscriptionRequestPanel />
    </div>
  );
}

/** Full-screen version once the trial has ended: the only thing the organization can do. */
export function TrialExpiredScreen({ organizationName, onLogout }: { organizationName: string; onLogout: () => void }) {
  return (
    <div className="min-h-screen bg-slate-50 px-4 py-8 sm:py-12">
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="rounded-2xl border border-amber-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <Clock className="mt-0.5 h-6 w-6 shrink-0 text-amber-600" aria-hidden="true" />
            <div className="min-w-0">
              <h1 className="text-xl font-bold text-slate-900">Your free trial has ended</h1>
              <p className="mt-1 text-sm text-slate-600">
                Your data in <span className="font-semibold text-slate-800">{organizationName}</span> is kept safe.
                Request a subscription to continue; Rooman will review it and email you once it is active.
              </p>
            </div>
          </div>
        </div>
        <SubscriptionRequestPanel />
        <div className="flex justify-center">
          <Button variant="outline" onClick={onLogout}>
            <LogOut className="mr-2 h-4 w-4" aria-hidden="true" />
            Sign Out
          </Button>
        </div>
      </div>
    </div>
  );
}

export function SubscriptionRequestPanel() {
  const query = useQuery({ queryKey: SUBSCRIPTION_STATE_KEY, queryFn: subscriptionAccessService.state });
  if (query.isLoading) return <LoadingState message="Loading your subscription..." />;
  if (query.isError || !query.data) {
    return <ErrorState title="Could not load your subscription" message={errorSummary(query.error)} onRetry={() => void query.refetch()} />;
  }
  return <SubscriptionStateView state={query.data} />;
}

function SubscriptionStateView({ state }: { state: SubscriptionState }) {
  const { hasRole } = useAuth();
  const { access, current_request: current, history } = state;
  const canRequest = access.status === 'trial' || access.status === 'trial_expired';
  const past = history.filter((r) => r.id !== current?.id);
  return (
    <div className="space-y-6">
      <AccessSummary state={state} />
      {current ? (
        <OpenRequestCard request={current} canWithdraw={hasRole('admin')} />
      ) : canRequest ? (
        hasRole('admin') ? (
          <RequestForm state={state} />
        ) : (
          <Card className="p-5 text-sm text-slate-600">
            Ask your organization Owner or an Admin to request a subscription.
          </Card>
        )
      ) : null}
      {past.length > 0 && <RequestHistory requests={past} />}
    </div>
  );
}

function AccessSummary({ state }: { state: SubscriptionState }) {
  const { access } = state;
  const days = trialDaysLeft(access.trial_ends_at);
  let title: string;
  let detail: string;
  if (access.status === 'trial') {
    title = 'Free trial';
    detail = `Every module is open until ${formatDateTime(access.trial_ends_at)}${days !== null && days > 0 ? ` (${days} day${days === 1 ? '' : 's'} left)` : ''}.`;
  } else if (access.status === 'trial_expired') {
    title = 'Trial ended';
    detail = `Your trial ended on ${formatDateTime(access.trial_ends_at)}.`;
  } else if (access.module_access === 'unrestricted') {
    title = 'Full access';
    detail = 'Your organization has every module.';
  } else {
    title = 'Active subscription';
    detail = `${access.modules.length} module${access.modules.length === 1 ? '' : 's'}: ${access.modules.map(moduleLabel).join(', ')}.`;
  }
  return (
    <Card className="p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <p className="mt-1 text-sm text-slate-600 break-words">{detail}</p>
        </div>
        <div className="shrink-0 text-sm text-slate-600">
          <span className="font-semibold text-slate-900">{access.seats_used}</span>
          {access.seat_limit !== null ? ` of ${access.seat_limit}` : ''} user seat{access.seats_used === 1 && access.seat_limit === null ? '' : 's'} in use
        </div>
      </div>
    </Card>
  );
}

function RequestForm({ state }: { state: SubscriptionState }) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const { refreshMe } = useAuth();
  const optional = state.modules.filter((m) => !m.base);
  const base = state.modules.filter((m) => m.base);
  const minSeats = Math.max(1, state.access.seats_used);
  const [selected, setSelected] = useState<string[]>([]);
  const [seats, setSeats] = useState<string>(String(Math.max(minSeats, 5)));
  const [cycle, setCycle] = useState<BillingCycle>('annual');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);

  const seatsNumber = Number(seats);
  const seatsValid = Number.isInteger(seatsNumber) && seatsNumber >= minSeats && seatsNumber <= 10000;
  const chosen = useMemo(() => new Set(selected), [selected]);

  const toggle = (key: string) => {
    setSelected((prev) => {
      if (prev.includes(key)) {
        const drop = new Set([key, ...dependents(key)]);
        return prev.filter((k) => !drop.has(k));
      }
      return withRequirements([...prev, key]);
    });
  };

  const submit = useMutation({
    mutationFn: () =>
      subscriptionAccessService.submit({ modules: selected, seats: seatsNumber, billing_cycle: cycle, notes: notes.trim() || null }),
    onSuccess: async () => {
      showToast('success', 'Request sent', 'Rooman will review it and email you the decision.');
      await queryClient.invalidateQueries({ queryKey: SUBSCRIPTION_STATE_KEY });
      void refreshMe();
    },
    onError: (err) => setError(errorSummary(err)),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!seatsValid) {
      setError(`Enter between ${minSeats} and 10000 user seats.`);
      return;
    }
    submit.mutate();
  };

  return (
    <Card className="p-5">
      <form onSubmit={onSubmit} className="space-y-6" aria-label="Request a subscription">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Request a subscription</h2>
          <p className="mt-1 text-sm text-slate-600">
            Always included: {base.map((m) => m.label).join(', ')}.
          </p>
        </div>

        <fieldset>
          <legend className="text-sm font-semibold text-slate-800">Additional modules</legend>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {optional.map((m) => (
              <label
                key={m.key}
                className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 p-3 hover:border-indigo-300 has-[:checked]:border-indigo-400 has-[:checked]:bg-indigo-50/40"
              >
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 shrink-0 rounded border-slate-300 text-indigo-600"
                  checked={chosen.has(m.key)}
                  onChange={() => toggle(m.key)}
                  name="modules"
                  value={m.key}
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-slate-900">{m.label}</span>
                  <span className="block text-xs text-slate-500">{m.description}</span>
                  {m.requires.length > 0 && (
                    <span className="block text-xs text-slate-500">Includes {m.requires.map(moduleLabel).join(', ')}.</span>
                  )}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="sub-seats" className="text-sm font-semibold text-slate-800">User seats</label>
            <input
              id="sub-seats"
              type="number"
              inputMode="numeric"
              min={minSeats}
              max={10000}
              step={1}
              required
              value={seats}
              onChange={(e) => setSeats(e.target.value)}
              aria-describedby="sub-seats-help"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <p id="sub-seats-help" className="mt-1 text-xs text-slate-500">
              Members and pending invitations count. You have {state.access.seats_used} now.
            </p>
          </div>
          <fieldset>
            <legend className="text-sm font-semibold text-slate-800">Billing cycle</legend>
            <div className="mt-1 flex flex-wrap gap-2">
              {CYCLES.map((c) => (
                <label key={c.value} className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm has-[:checked]:border-indigo-400 has-[:checked]:bg-indigo-50/40">
                  <input type="radio" name="billing_cycle" value={c.value} checked={cycle === c.value} onChange={() => setCycle(c.value)} />
                  {c.label}
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <div>
          <label htmlFor="sub-notes" className="text-sm font-semibold text-slate-800">Notes for Rooman (optional)</label>
          <textarea
            id="sub-notes"
            rows={3}
            maxLength={1000}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </div>

        {error && (
          <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
            {error}
          </p>
        )}

        <div className="flex justify-end">
          <Button type="submit" disabled={submit.isPending}>
            {submit.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="mr-2 h-4 w-4" aria-hidden="true" />}
            Send request
          </Button>
        </div>
      </form>
    </Card>
  );
}

function RequestSummary({ request }: { request: SubscriptionRequestOut }) {
  const approved = request.status === 'approved';
  const modules = approved && request.approved_modules ? request.approved_modules : request.modules;
  const seats = approved && request.approved_seats ? request.approved_seats : request.seats;
  const cycle = approved && request.approved_billing_cycle ? request.approved_billing_cycle : request.billing_cycle;
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
      <div className="sm:col-span-3">
        <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Additional modules</dt>
        <dd className="text-slate-800 break-words">{modules.length ? modules.map(moduleLabel).join(', ') : 'None (core modules only)'}</dd>
      </div>
      <div>
        <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">User seats</dt>
        <dd className="text-slate-800">{seats}</dd>
      </div>
      <div>
        <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Billing cycle</dt>
        <dd className="text-slate-800">{cycleLabel(cycle)}</dd>
      </div>
      <div>
        <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Requested</dt>
        <dd className="text-slate-800">{formatDate(request.created_at)}</dd>
      </div>
    </dl>
  );
}

function OpenRequestCard({ request, canWithdraw }: { request: SubscriptionRequestOut; canWithdraw: boolean }) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const withdraw = useMutation({
    mutationFn: () => subscriptionAccessService.withdraw(request.id),
    onSuccess: async () => {
      showToast('success', 'Request withdrawn', 'You can send a new request.');
      await queryClient.invalidateQueries({ queryKey: SUBSCRIPTION_STATE_KEY });
    },
    onError: (err) => showToast('error', 'Could not withdraw', errorSummary(err)),
  });
  return (
    <Card className="p-5">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-amber-600" aria-hidden="true" />
            <h2 className="text-base font-semibold text-slate-900">Your request is waiting for Rooman review</h2>
          </div>
          <Badge variant="warning">{STATUS_BADGE.submitted.label}</Badge>
        </div>
        <RequestSummary request={request} />
        {canWithdraw && (
          <div className="flex justify-end">
            <Button variant="outline" disabled={withdraw.isPending} onClick={() => withdraw.mutate()}>
              Withdraw request
            </Button>
          </div>
        )}
      </div>
    </Card>
  );
}

function RequestHistory({ requests }: { requests: SubscriptionRequestOut[] }) {
  return (
    <Card className="p-5">
      <h2 className="text-base font-semibold text-slate-900">Earlier requests</h2>
      <ul className="mt-3 divide-y divide-slate-100">
        {requests.map((r) => {
          const badge = STATUS_BADGE[r.status];
          const Icon = r.status === 'approved' ? CheckCircle2 : r.status === 'rejected' ? XCircle : Clock;
          return (
            <li key={r.id} className="py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="flex items-center gap-2 text-sm text-slate-700">
                  <Icon className="h-4 w-4 text-slate-400" aria-hidden="true" />
                  {formatDate(r.created_at)}
                </span>
                <Badge variant={badge.variant}>{badge.label}</Badge>
              </div>
              <div className="mt-2">
                <RequestSummary request={r} />
              </div>
              {r.decision_reason && (
                <p className="mt-2 text-sm text-slate-600 break-words">
                  <span className="font-semibold">Rooman:</span> {r.decision_reason}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
