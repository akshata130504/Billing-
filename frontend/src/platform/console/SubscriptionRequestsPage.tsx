/**
 * Subscription requests from trial organizations. Every platform role can read the queue; only a
 * Platform Administrator can approve (as requested, or with modified modules / seats / billing
 * cycle) or reject, with a reason and a password step-up. The server enforces all of it.
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../../components/common/Button';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { Modal } from '../../components/common/Modal';
import { PageHeader } from '../../components/common/PageHeader';
import { Badge } from '../../components/common/Badge';
import { BASE_MODULE_KEYS, OPTIONAL_MODULES, dependents, moduleLabel, withRequirements } from '../../entitlements';
import {
  consoleApi,
  type BillingCycle,
  type PlatformSubscriptionRequest,
  type SubscriptionRequestStatus,
} from '../consoleApi';
import { PlatformApiError } from '../platformApi';
import { ActionDialog } from './ActionDialog';
import { ProvisionAdminDialog } from './ProvisionAdminDialog';
import { ADMIN, useConsole } from './ConsoleContext';
import { Section, StatusBadge, formatDateTime } from './ui';

type Filter = SubscriptionRequestStatus | 'all';

const FILTERS: Array<{ value: Filter; label: string }> = [
  { value: 'submitted', label: 'Waiting' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'withdrawn', label: 'Withdrawn' },
  { value: 'all', label: 'All' },
];

const CYCLE_LABELS: Record<BillingCycle, string> = { monthly: 'Monthly', quarterly: 'Quarterly', annual: 'Annual' };

const REQUEST_BADGES: Record<SubscriptionRequestStatus, { label: string; variant: 'warning' | 'success' | 'danger' | 'neutral' }> = {
  submitted: { label: 'Waiting for review', variant: 'warning' },
  approved: { label: 'Approved', variant: 'success' },
  rejected: { label: 'Rejected', variant: 'danger' },
  withdrawn: { label: 'Withdrawn', variant: 'neutral' },
};

function modulesText(keys: string[]): string {
  return keys.length ? keys.map(moduleLabel).join(', ') : 'Core modules only';
}

export function SubscriptionRequestsPage() {
  const { hasRole } = useConsole();
  const isAdmin = hasRole(ADMIN);
  const [filter, setFilter] = useState<Filter>('submitted');
  const [items, setItems] = useState<PlatformSubscriptionRequest[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<PlatformSubscriptionRequest | null>(null);
  const [provisioning, setProvisioning] = useState<PlatformSubscriptionRequest | null>(null);
  const [provisioned, setProvisioned] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setError(null);
    setItems(null);
    try {
      const page = await consoleApi.subscriptionRequests(filter);
      setItems(page.items);
      setTotal(page.total);
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load subscription requests.');
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Subscription requests"
        subtitle="Trial organizations asking for modules and user seats. Approving activates the organization; its Owner keeps their account and role."
      />
      <div role="tablist" aria-label="Request status" className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            role="tab"
            aria-selected={filter === f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-full border px-3 py-1.5 text-sm font-medium ${
              filter === f.value ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {!isAdmin && (
        <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          You can view requests. Only a Platform Administrator can approve or reject them.
        </p>
      )}
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!items && !error && <LoadingState message="Loading requests..." />}
      {items && (
        <Section title={`${total} request${total === 1 ? '' : 's'}`}>
          {items.length === 0 ? (
            <EmptyState title="Nothing here" description="Requests appear when a trial organization asks for a subscription." />
          ) : (
            <ul className="divide-y divide-slate-100">
              {items.map((r) => (
                <li key={r.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link to={`/organizations/${r.organization_id}`} className="font-semibold text-slate-900 hover:text-brand-600">
                        {r.organization_name}
                      </Link>
                      <StatusBadge status={r.organization_status} />
                      <Badge variant={REQUEST_BADGES[r.status].variant}>{REQUEST_BADGES[r.status].label}</Badge>
                    </div>
                    <p className="text-sm text-slate-700 break-words">
                      <span className="font-medium">Modules:</span> {modulesText(r.status === 'approved' ? r.approved_modules ?? r.modules : r.modules)}
                    </p>
                    <p className="text-sm text-slate-700">
                      <span className="font-medium">Seats:</span> {r.status === 'approved' ? r.approved_seats ?? r.seats : r.seats}{' '}
                      <span className="text-slate-500">({r.seats_used} in use)</span> ·{' '}
                      <span className="font-medium">Billing:</span>{' '}
                      {CYCLE_LABELS[r.status === 'approved' ? r.approved_billing_cycle ?? r.billing_cycle : r.billing_cycle]}
                    </p>
                    <p className="text-xs text-slate-500 break-words">
                      Requested {formatDateTime(r.created_at)}
                      {r.requested_by_email ? ` by ${r.requested_by_name ?? ''} <${r.requested_by_email}>` : ''}
                      {r.trial_ends_at ? ` · trial ends ${formatDateTime(r.trial_ends_at)}` : ''}
                    </p>
                    {r.notes && <p className="text-sm text-slate-600 break-words">“{r.notes}”</p>}
                    {r.decision_reason && (
                      <p className="text-sm text-slate-600 break-words">
                        <span className="font-medium">Decision:</span> {r.decision_reason}
                      </p>
                    )}
                  </div>
                  {isAdmin && r.status === 'submitted' && (
                    <Button size="sm" onClick={() => setReviewing(r)} className="self-start">
                      Review
                    </Button>
                  )}
                  {isAdmin && r.status === 'approved' && (
                    <div className="flex flex-col items-start gap-1 self-start sm:items-end">
                      <Button size="sm" onClick={() => setProvisioning(r)}>Create Admin</Button>
                      {provisioned[r.organization_id] && (
                        <span className="text-xs text-emerald-700">{provisioned[r.organization_id]}</span>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}
      {provisioning && (
        <ProvisionAdminDialog
          isOpen
          organizationId={provisioning.organization_id}
          organizationName={provisioning.organization_name}
          onClose={() => setProvisioning(null)}
          onProvisioned={(a) => setProvisioned((prev) => ({
            ...prev,
            [a.organization_id]: `Admin invited: ${a.email}${a.email_delivered ? ' (invitation sent)' : ' (email not delivered)'}`,
          }))}
        />
      )}
      {reviewing && (
        <ReviewDialog
          request={reviewing}
          onClose={() => setReviewing(null)}
          onDone={() => {
            setReviewing(null);
            void load();
          }}
        />
      )}
    </div>
  );
}

function ReviewDialog({ request, onClose, onDone }: { request: PlatformSubscriptionRequest; onClose: () => void; onDone: () => void }) {
  const [modules, setModules] = useState<string[]>(request.modules);
  const [seats, setSeats] = useState(String(request.seats));
  const [cycle, setCycle] = useState<BillingCycle>(request.billing_cycle);
  const [action, setAction] = useState<'approve' | 'reject' | null>(null);

  const seatsNumber = Number(seats);
  const seatsValid = Number.isInteger(seatsNumber) && seatsNumber >= Math.max(1, request.seats_used) && seatsNumber <= 10000;
  const modified =
    modules.join(',') !== request.modules.join(',') || seatsNumber !== request.seats || cycle !== request.billing_cycle;

  const toggle = (key: string) =>
    setModules((prev) => {
      if (prev.includes(key)) {
        const drop = new Set([key, ...dependents(key)]);
        return prev.filter((k) => !drop.has(k));
      }
      return withRequirements([...prev, key]);
    });

  return (
    <>
      <Modal isOpen={action === null} onClose={onClose} title={`Review ${request.organization_name}`} description="Approve as requested, or change modules, seats or billing cycle before approving." size="lg">
        <div className="space-y-5">
          <p className="text-sm text-slate-600">Always included: {BASE_MODULE_KEYS.map(moduleLabel).join(', ')}.</p>
          <fieldset>
            <legend className="text-sm font-semibold text-slate-800">Additional modules</legend>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {OPTIONAL_MODULES.map((m) => (
                <label key={m.key} className="flex items-start gap-2 rounded-lg border border-slate-200 p-2 text-sm">
                  <input type="checkbox" className="mt-0.5" checked={modules.includes(m.key)} onChange={() => toggle(m.key)} />
                  <span>
                    {m.label}
                    {request.modules.includes(m.key) ? <span className="ml-1 text-xs text-slate-500">(requested)</span> : null}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="review-seats" className="text-sm font-semibold text-slate-800">User seats</label>
              <input
                id="review-seats"
                type="number"
                min={Math.max(1, request.seats_used)}
                max={10000}
                value={seats}
                onChange={(e) => setSeats(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              <p className="mt-1 text-xs text-slate-500">Requested {request.seats}; {request.seats_used} in use now.</p>
            </div>
            <div>
              <label htmlFor="review-cycle" className="text-sm font-semibold text-slate-800">Billing cycle</label>
              <select
                id="review-cycle"
                value={cycle}
                onChange={(e) => setCycle(e.target.value as BillingCycle)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                {(Object.keys(CYCLE_LABELS) as BillingCycle[]).map((c) => (
                  <option key={c} value={c}>{CYCLE_LABELS[c]}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
            <Button variant="danger" size="sm" onClick={() => setAction('reject')}>Reject</Button>
            <Button size="sm" disabled={!seatsValid} onClick={() => setAction('approve')}>
              {modified ? 'Approve with changes' : 'Approve'}
            </Button>
          </div>
        </div>
      </Modal>
      <ActionDialog
        isOpen={action === 'approve'}
        title="Approve subscription"
        description={`${request.organization_name} becomes active with the modules and seats below.`}
        confirmLabel="Approve"
        notes={[
          `Modules: ${modulesText(modules)}`,
          `User seats: ${seatsNumber} · Billing: ${CYCLE_LABELS[cycle]}`,
          'The Owner keeps their account and is emailed a sign-in link (no password).',
        ]}
        onClose={() => setAction(null)}
        onSubmit={(body) =>
          consoleApi.approveSubscriptionRequest(request.id, { modules, seats: seatsNumber, billing_cycle: cycle, reason: body.reason })
        }
        onDone={onDone}
      />
      <ActionDialog
        isOpen={action === 'reject'}
        title="Reject subscription request"
        description={`${request.organization_name} stays on its trial state and can send a new request.`}
        confirmLabel="Reject"
        danger
        notes={['The Owner is emailed the reason.']}
        onClose={() => setAction(null)}
        onSubmit={(body) => consoleApi.rejectSubscriptionRequest(request.id, { reason: body.reason })}
        onDone={onDone}
      />
    </>
  );
}
