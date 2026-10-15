/**
 * Rooman's own plan billing: subscriptions, checkout attempts, the platform webhook ledger and the items that need
 * a person. Everything shown is the application's stored state (no Razorpay call). The only action records the
 * resolution of a payment-review case (bookkeeping, with a step-up); it never changes a payment, checkout,
 * subscription or access. Platform Administrator and Platform Operations only - the server enforces it.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Select } from '../../components/common/Select';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { PageHeader } from '../../components/common/PageHeader';
import { Pagination } from '../../components/common/Pagination';
import { formatMoney } from '../../utils/format';
import {
  billingApi,
  type BillingPage,
  type CheckoutAttemptRow,
  type CheckoutFilter,
  type PlatformSubscriptionRow,
  NOTIFICATION_KIND_LABELS,
  RESOLUTION_CATEGORY_LABELS,
  type NotificationFilter,
  type NotificationKind,
  type NotificationPage,
  type NotificationRow,
  type ReviewFilter,
  type ReviewItem,
  type ReviewQueuePage,
  type ReviewResolutionCategory,
  type SubscriptionFilter,
  type WebhookEventRow,
  type WebhookFilter,
} from '../billingApi';
import { PlatformApiError } from '../platformApi';
import { ActionDialog } from './ActionDialog';
import { Section, formatDateTime } from './ui';

type Variant = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';
type Tab = 'subscriptions' | 'checkouts' | 'webhooks' | 'review' | 'email';

const TABS: Array<{ value: Tab; label: string }> = [
  { value: 'subscriptions', label: 'Subscriptions' },
  { value: 'checkouts', label: 'Checkout attempts' },
  { value: 'webhooks', label: 'Webhook ledger' },
  { value: 'review', label: 'Needs review' },
  { value: 'email', label: 'Email delivery' },
];

const NOTIFICATION_BADGES: Record<string, { label: string; variant: Variant }> = {
  pending: { label: 'Pending', variant: 'info' },
  sent: { label: 'Sent to SMTP', variant: 'success' },
  failed: { label: 'Failed', variant: 'danger' },
  superseded: { label: 'Not sent (superseded)', variant: 'neutral' },
};

const SUBSCRIPTION_BADGES: Record<string, { label: string; variant: Variant }> = {
  active: { label: 'Active', variant: 'success' },
  cancellation_scheduled: { label: 'Cancellation scheduled', variant: 'warning' },
  past_due: { label: 'Past due', variant: 'danger' },
  cancelled: { label: 'Cancelled', variant: 'neutral' },
  expired: { label: 'Expired', variant: 'neutral' },
  trialing: { label: 'Trial', variant: 'info' },
  trial_expired: { label: 'Trial ended', variant: 'neutral' },
  invalid: { label: 'Invalid record', variant: 'danger' },
};

const CHECKOUT_BADGES: Record<string, { label: string; variant: Variant }> = {
  pending: { label: 'Starting', variant: 'info' },
  created: { label: 'Waiting for payment', variant: 'info' },
  unknown: { label: 'Outcome unknown', variant: 'warning' },
  authorized: { label: 'Authorized, not charged', variant: 'warning' },
  completed: { label: 'Completed', variant: 'success' },
  failed: { label: 'Failed', variant: 'danger' },
  expired: { label: 'Expired', variant: 'neutral' },
};

const WEBHOOK_BADGES: Record<string, { label: string; variant: Variant }> = {
  processed: { label: 'Processed', variant: 'success' },
  ignored: { label: 'Ignored', variant: 'neutral' },
  needs_review: { label: 'Needs review', variant: 'danger' },
};

const REVIEW_LABELS: Record<string, string> = {
  checkout_review: 'Payment needs review',
  webhook_needs_review: 'Webhook could not be applied',
  checkout_unknown: 'Checkout outcome unknown',
  checkout_authorized_stuck: 'Authorized but never charged',
};

function StateBadge({ map, value }: { map: Record<string, { label: string; variant: Variant }>; value: string }) {
  const badge = map[value] ?? { label: value, variant: 'neutral' as Variant };
  return <Badge variant={badge.variant}>{badge.label}</Badge>;
}

function money(amountMinor: number | null, currency: string | null): string {
  return amountMinor == null || !currency ? '—' : formatMoney(amountMinor / 100, currency);
}

function interval(unit: string | null, count: number | null): string {
  if (!unit) return '—';
  return count && count > 1 ? `every ${count} ${unit}s` : `per ${unit}`;
}

function Mono({ children }: { children: ReactNode }) {
  return <span className="font-mono text-xs text-slate-600 break-all">{children || '—'}</span>;
}

function OrgLink({ id, name }: { id: string | null; name: string | null }) {
  if (!id) return <span className="text-slate-400">—</span>;
  return (
    <Link to={`/organizations/${id}`} className="font-medium text-slate-900 hover:text-brand-600">
      {name || id}
    </Link>
  );
}

/** Shared loading / error / page state for one filtered, paginated list. */
function usePaged<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async () => {
    setError(null);
    setData(null);
    try {
      setData(await load());
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not load this view.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    void run();
  }, [run]);
  return { data, error, retry: () => void run() };
}

function FilterTabs<V extends string>({ label, value, options, onChange }: {
  label: string;
  value: V;
  options: Array<{ value: V; label: string }>;
  onChange: (v: V) => void;
}) {
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-full border px-3 py-1 text-xs font-medium ${
            value === o.value ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function OrgSearch({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [draft, setDraft] = useState(value);
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        onChange(draft.trim());
      }}
    >
      <input
        aria-label="Organization name or id"
        placeholder="Organization name or id"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        maxLength={100}
        className="w-64 rounded-lg border border-slate-200 px-3 py-1.5 text-sm"
      />
      <button type="submit" className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700">
        Filter
      </button>
    </form>
  );
}

function ListFrame<T>({ data, error, retry, emptyTitle, emptyDescription, itemLabel, onPage, children }: {
  data: BillingPage<T> | null;
  error: string | null;
  retry: () => void;
  emptyTitle: string;
  emptyDescription: string;
  itemLabel: string;
  onPage: (page: number) => void;
  children: (items: T[]) => ReactNode;
}) {
  if (error) return <ErrorState message={error} onRetry={retry} />;
  if (!data) return <LoadingState message="Loading..." />;
  if (data.items.length === 0) return <EmptyState title={emptyTitle} description={emptyDescription} />;
  return (
    <>
      <div className="overflow-x-auto">{children(data.items)}</div>
      <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={onPage} itemLabel={itemLabel} />
    </>
  );
}

const TH = 'px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500';
const TD = 'px-3 py-2 align-top text-sm text-slate-700';

// --- tabs -----------------------------------------------------------------------------------------------------

function SubscriptionsTab() {
  const [status, setStatus] = useState<SubscriptionFilter>('paid');
  const [organization, setOrganization] = useState('');
  const [page, setPage] = useState(1);
  const { data, error, retry } = usePaged(() => billingApi.subscriptions({ status, organization, page }), [status, organization, page]);
  return (
    <Section title={data ? `${data.total} subscription${data.total === 1 ? '' : 's'}` : 'Subscriptions'}
      description="Stored state; the effective state is what access is right now.">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <FilterTabs label="Subscription status" value={status} onChange={(v) => { setStatus(v); setPage(1); }} options={[
          { value: 'paid', label: 'All paid' }, { value: 'active', label: 'Active' },
          { value: 'cancellation_scheduled', label: 'Cancellation scheduled' }, { value: 'past_due', label: 'Past due' },
          { value: 'cancelled', label: 'Cancelled' }, { value: 'expired', label: 'Expired' },
          { value: 'trialing', label: 'Trials' }, { value: 'all', label: 'All' },
        ]} />
        <OrgSearch value={organization} onChange={(v) => { setOrganization(v); setPage(1); }} />
      </div>
      <ListFrame data={data} error={error} retry={retry} onPage={setPage} itemLabel="subscriptions"
        emptyTitle="No subscriptions" emptyDescription="Paid plans appear here once an organization's first payment is verified.">
        {(items: PlatformSubscriptionRow[]) => (
          <table className="min-w-full divide-y divide-slate-100">
            <thead><tr><th className={TH}>Organization</th><th className={TH}>Plan</th><th className={TH}>Status</th><th className={TH}>Amount</th><th className={TH}>Period</th><th className={TH}>Razorpay</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((s) => {
                const shown = s.state === 'active' && s.cancel_at_period_end ? 'cancellation_scheduled' : s.state;
                return (
                  <tr key={s.organization_id} data-testid="subscription-row">
                    <td className={TD}><OrgLink id={s.organization_id} name={s.organization_name} /></td>
                    <td className={TD}>
                      {s.plan_name ?? s.plan_code ?? '—'}
                      {s.sandbox && <span className="ml-2"><Badge variant="warning">Test mode</Badge></span>}
                    </td>
                    <td className={TD}>
                      <StateBadge map={SUBSCRIPTION_BADGES} value={shown} />
                      {s.effective_state !== s.state && (
                        <p className="mt-1 text-xs text-slate-500">Effective now: {SUBSCRIPTION_BADGES[s.effective_state]?.label ?? s.effective_state}</p>
                      )}
                    </td>
                    <td className={TD}>{money(s.amount_minor, s.currency)} <span className="text-xs text-slate-500">{interval(s.billing_interval, s.billing_interval_count)}</span></td>
                    <td className={TD}>
                      <p>{formatDateTime(s.current_period_start)} → {formatDateTime(s.current_period_end)}</p>
                      {s.grace_period_end && <p className="text-xs text-slate-500">Grace until {formatDateTime(s.grace_period_end)}</p>}
                      {s.cancelled_at && <p className="text-xs text-slate-500">Cancelled {formatDateTime(s.cancelled_at)}</p>}
                    </td>
                    <td className={TD}><Mono>{s.provider_subscription_id}</Mono><p className="text-xs text-slate-500">{s.provider_mode ?? ''}{s.provider_paid_count != null ? ` · ${s.provider_paid_count} paid` : ''}</p></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </ListFrame>
    </Section>
  );
}

function CheckoutsTab() {
  const [status, setStatus] = useState<CheckoutFilter>('all');
  const [mode, setMode] = useState('');
  const [organization, setOrganization] = useState('');
  const [page, setPage] = useState(1);
  const { data, error, retry } = usePaged(
    () => billingApi.checkoutAttempts({ status, mode: mode || undefined, organization, page }), [status, mode, organization, page]);
  return (
    <Section title={data ? `${data.total} checkout attempt${data.total === 1 ? '' : 's'}` : 'Checkout attempts'}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <FilterTabs label="Checkout status" value={status} onChange={(v) => { setStatus(v); setPage(1); }} options={[
          { value: 'all', label: 'All' }, { value: 'open', label: 'Open' }, { value: 'authorized', label: 'Authorized' },
          { value: 'unknown', label: 'Unknown' }, { value: 'completed', label: 'Completed' },
          { value: 'failed', label: 'Failed' }, { value: 'expired', label: 'Expired' },
        ]} />
        <div className="flex flex-wrap gap-2">
          <select aria-label="Key mode" value={mode} onChange={(e) => { setMode(e.target.value); setPage(1); }}
            className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm">
            <option value="">Test and live</option><option value="test">Test mode</option><option value="live">Live mode</option>
          </select>
          <OrgSearch value={organization} onChange={(v) => { setOrganization(v); setPage(1); }} />
        </div>
      </div>
      <ListFrame data={data} error={error} retry={retry} onPage={setPage} itemLabel="attempts"
        emptyTitle="No checkout attempts" emptyDescription="An attempt is recorded when an Owner starts buying a plan.">
        {(items: CheckoutAttemptRow[]) => (
          <table className="min-w-full divide-y divide-slate-100">
            <thead><tr><th className={TH}>Organization</th><th className={TH}>Plan</th><th className={TH}>Status</th><th className={TH}>Expected</th><th className={TH}>Times</th><th className={TH}>Razorpay</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((a) => (
                <tr key={a.id} data-testid="checkout-row">
                  <td className={TD}><OrgLink id={a.organization_id} name={a.organization_name} /></td>
                  <td className={TD}>{a.plan_name ?? a.plan_code}{a.sandbox && <span className="ml-2"><Badge variant="warning">Test mode</Badge></span>}</td>
                  <td className={TD}>
                    <div className="flex flex-wrap gap-1">
                      <StateBadge map={CHECKOUT_BADGES} value={a.status} />
                      {a.review_reason && <Badge variant="danger">Needs review</Badge>}
                      {a.webhook_review && <Badge variant="danger">Webhook needs review</Badge>}
                      {a.stuck && <Badge variant="warning">Needs attention</Badge>}
                    </div>
                    {a.review_reason && (
                      <p className="mt-1 text-xs text-rose-700 break-words">
                        {a.review_reason} (flagged {formatDateTime(a.review_flagged_at)})
                      </p>
                    )}
                    {a.last_error && <p className="mt-1 text-xs text-slate-500 break-words">{a.last_error}</p>}
                  </td>
                  <td className={TD}>{money(a.amount_minor, a.currency)} <span className="text-xs text-slate-500">{interval(a.billing_interval, a.billing_interval_count)} · {a.seat_limit} seats · {a.mode}</span></td>
                  <td className={TD}>
                    <p className="text-xs">Created {formatDateTime(a.created_at)}</p>
                    <p className="text-xs text-slate-500">Expires {formatDateTime(a.expires_at)}</p>
                    {a.authorized_at && <p className="text-xs text-slate-500">Authorized {formatDateTime(a.authorized_at)}</p>}
                    {a.completed_at && <p className="text-xs text-slate-500">Completed {formatDateTime(a.completed_at)}</p>}
                  </td>
                  <td className={TD}><Mono>{a.provider_subscription_id}</Mono>{a.provider_payment_id && <p><Mono>{a.provider_payment_id}</Mono></p>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </ListFrame>
    </Section>
  );
}

function WebhooksTab() {
  const [status, setStatus] = useState<WebhookFilter>('all');
  const [organization, setOrganization] = useState('');
  const [page, setPage] = useState(1);
  const { data, error, retry } = usePaged(() => billingApi.webhookEvents({ status, organization, page }), [status, organization, page]);
  return (
    <Section title={data ? `${data.total} webhook event${data.total === 1 ? '' : 's'}` : 'Webhook ledger'}
      description="Signed platform webhooks as recorded (normalized fields only; payloads and signatures are never stored). A redelivered event is answered as a duplicate and not recorded twice.">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <FilterTabs label="Webhook status" value={status} onChange={(v) => { setStatus(v); setPage(1); }} options={[
          { value: 'all', label: 'All' }, { value: 'processed', label: 'Processed' },
          { value: 'ignored', label: 'Ignored' }, { value: 'needs_review', label: 'Needs review' },
        ]} />
        <OrgSearch value={organization} onChange={(v) => { setOrganization(v); setPage(1); }} />
      </div>
      <ListFrame data={data} error={error} retry={retry} onPage={setPage} itemLabel="events"
        emptyTitle="The webhook ledger is empty" emptyDescription="No signed platform webhook has been recorded yet.">
        {(items: WebhookEventRow[]) => (
          <table className="min-w-full divide-y divide-slate-100">
            <thead><tr><th className={TH}>Received</th><th className={TH}>Event</th><th className={TH}>Status</th><th className={TH}>Organization</th><th className={TH}>Razorpay</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((e) => (
                <tr key={e.id} data-testid="webhook-row">
                  <td className={TD}><p className="text-xs">{formatDateTime(e.received_at)}</p>{e.event_created_at && <p className="text-xs text-slate-500">Sent {formatDateTime(e.event_created_at)}</p>}</td>
                  <td className={TD}>{e.event_type}<p><Mono>{e.event_id}</Mono></p></td>
                  <td className={TD}><StateBadge map={WEBHOOK_BADGES} value={e.status} />{e.outcome && <p className="mt-1 text-xs text-slate-500">{e.outcome}</p>}</td>
                  <td className={TD}><OrgLink id={e.organization_id} name={e.organization_name} /></td>
                  <td className={TD}><Mono>{e.provider_subscription_id}</Mono>{e.provider_payment_id && <p><Mono>{e.provider_payment_id}</Mono></p>}<p className="text-xs text-slate-500">{e.mode ?? ''}</p></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </ListFrame>
    </Section>
  );
}

const RESOLVE_NOTES = [
  'Resolving records your review only. It does not approve, refund, retry or change any payment.',
  'The checkout, subscription and the organization’s access stay exactly as they are.',
  'If the same problem is found again later, a new review case opens; this resolution stays in the history.',
];

function reviewTitle(status: ReviewFilter, total: number): string {
  const n = `${total} ${status === 'resolved' ? 'resolved case' : 'item'}${total === 1 ? '' : 's'}`;
  if (status === 'open') return `${n} need${total === 1 ? 's' : ''} review`;
  return status === 'resolved' ? n : `${n} (open and resolved)`;
}

function CaseHistory({ item }: { item: ReviewItem }) {
  if (!item.case_id) return null;
  return (
    <div className="mt-2 space-y-1 text-xs text-slate-500" data-testid="review-history">
      {item.first_reason && item.first_reason !== item.review_reason && (
        <p className="break-words">First finding: {item.first_reason}</p>
      )}
      <p>
        Opened {formatDateTime(item.flagged_at)}
        {item.last_seen_at && <> · last seen {formatDateTime(item.last_seen_at)}</>}
        {item.finding_count != null && <> · {item.finding_count} finding{item.finding_count === 1 ? '' : 's'}</>}
      </p>
      {item.case_status === 'resolved' && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700" data-testid="review-resolution">
          <p>
            <span className="font-medium">
              {item.resolution_category ? RESOLUTION_CATEGORY_LABELS[item.resolution_category] ?? item.resolution_category : 'Resolved'}
            </span>
            <span className="text-xs text-slate-500">
              {' '}· by {item.resolved_by_email ?? 'unknown staff'}
              {item.resolved_by_role && <> ({item.resolved_by_role.replace(/_/g, ' ')})</>}
              {' '}· {formatDateTime(item.resolved_at)}
              {item.resolution_ticket_ref && <> · {item.resolution_ticket_ref}</>}
            </span>
          </p>
          {item.resolution_note && <p className="mt-1 break-words">{item.resolution_note}</p>}
        </div>
      )}
    </div>
  );
}

function ReviewTab() {
  const [status, setStatus] = useState<ReviewFilter>('open');
  const [organization, setOrganization] = useState('');
  const [page, setPage] = useState(1);
  const [resolving, setResolving] = useState<ReviewItem | null>(null);
  const [category, setCategory] = useState<ReviewResolutionCategory | ''>('');
  const { data, error, retry } = usePaged<ReviewQueuePage>(
    () => billingApi.reviewQueue({ status, organization, page }), [status, organization, page]);
  const openResolve = (item: ReviewItem) => {
    setCategory('');
    setResolving(item);
  };
  return (
    <Section title={data ? reviewTitle(status, data.total) : 'Needs review'}
      description="Investigate in the Razorpay dashboard or with the organization, then record what you found. Resolving a case is bookkeeping only: nothing here approves, refunds or changes a payment.">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <FilterTabs label="Review status" value={status} onChange={(v) => { setStatus(v); setPage(1); }} options={[
          { value: 'open', label: 'Open' }, { value: 'resolved', label: 'Resolved' }, { value: 'all', label: 'All' },
        ]} />
        <OrgSearch value={organization} onChange={(v) => { setOrganization(v); setPage(1); }} />
      </div>
      {data && data.untracked_sources.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="untracked-sources">
          <p className="font-semibold">Not listed here (logged and alerted only, not stored yet):</p>
          <ul className="mt-1 list-disc pl-5">{data.untracked_sources.map((s) => <li key={s}>{s}</li>)}</ul>
        </div>
      )}
      <ListFrame data={data} error={error} retry={retry} onPage={setPage} itemLabel="items"
        emptyTitle={status === 'resolved' ? 'No resolved cases' : 'Nothing needs review'}
        emptyDescription={status === 'resolved'
          ? 'No payment review case has been resolved yet.'
          : 'No stored payment review, webhook or checkout record currently needs a person.'}>
        {(items: ReviewItem[]) => (
          <ul className="divide-y divide-slate-100">
            {items.map((i, n) => (
              <li key={i.case_id ?? `${i.source}-${i.checkout_attempt_id ?? i.provider_subscription_id ?? n}`} className="py-3" data-testid="review-row">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={i.case_status === 'resolved' ? 'neutral' : 'danger'}>{REVIEW_LABELS[i.source] ?? i.source}</Badge>
                    {i.case_status && (
                      <Badge variant={i.case_status === 'resolved' ? 'success' : 'warning'}>
                        {i.case_status === 'resolved' ? 'Resolved' : 'Open'}
                      </Badge>
                    )}
                    <OrgLink id={i.organization_id} name={i.organization_name} />
                    <span className="text-xs text-slate-500">{formatDateTime(i.detected_at)}</span>
                  </div>
                  {i.resolvable && i.case_id && (
                    <Button size="sm" variant="outline" onClick={() => openResolve(i)}>Resolve</Button>
                  )}
                </div>
                <p className="mt-1 text-sm text-slate-600">{i.explanation}</p>
                {i.review_reason && (
                  <p className={`mt-1 text-sm break-words ${i.case_status === 'resolved' ? 'text-slate-600' : 'text-rose-700'}`}>
                    {i.case_id ? 'Latest finding' : 'Reason'}: {i.review_reason}
                    {i.checkout_status && <span className="text-xs text-slate-500"> · checkout {i.checkout_status}</span>}
                  </p>
                )}
                <CaseHistory item={i} />
                <p className="mt-1 text-xs text-slate-500">
                  {i.outcome && <>Outcome: {i.outcome} · </>}
                  {i.event_type && <>{i.event_type} · </>}
                  <Mono>{i.provider_subscription_id}</Mono>
                  {i.mode && <> · {i.mode}</>}
                </p>
              </li>
            ))}
          </ul>
        )}
      </ListFrame>
      <ActionDialog<ReviewItem>
        isOpen={resolving !== null}
        title="Resolve payment review"
        description={resolving
          ? `${resolving.organization_name ?? resolving.organization_id ?? 'Unknown organization'}: ${resolving.review_reason ?? resolving.explanation}`
          : ''}
        confirmLabel="Resolve review"
        notes={RESOLVE_NOTES}
        reasonLabel="What did you investigate?"
        reasonPlaceholder="What you checked and what you found (at least 10 characters)"
        extraValid={category !== ''}
        extraFields={(
          <Select
            label="Resolution"
            required
            value={category}
            onChange={(e) => setCategory(e.target.value as ReviewResolutionCategory | '')}
            placeholder="Choose how this was resolved"
            options={(Object.keys(RESOLUTION_CATEGORY_LABELS) as ReviewResolutionCategory[]).map((value) => ({
              value, label: RESOLUTION_CATEGORY_LABELS[value],
            }))}
          />
        )}
        onClose={() => setResolving(null)}
        onSubmit={(body) => billingApi.resolveReviewCase(resolving!.case_id!, { ...body, category: category as ReviewResolutionCategory })}
        onDone={() => {
          setResolving(null);
          retry();
        }}
      />
    </Section>
  );
}

function EmailDeliveryTab() {
  const [status, setStatus] = useState<NotificationFilter>('all');
  const [kind, setKind] = useState<NotificationKind | ''>('');
  const [organization, setOrganization] = useState('');
  const [page, setPage] = useState(1);
  const { data, error, retry } = usePaged<NotificationPage>(
    () => billingApi.notifications({ status, kind, organization, page }), [status, kind, organization, page]);
  const counts = data?.status_counts;
  return (
    <Section title={data ? `${data.total} email${data.total === 1 ? '' : 's'}` : 'Email delivery'}
      description="Rooman's plan emails to customers, as recorded by the delivery job. Read-only: the scheduler sends and retries them. “Sent to SMTP” means Rooman's mail server accepted the message - it does not prove it reached or was read in the customer's inbox.">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <FilterTabs label="Email status" value={status} onChange={(v) => { setStatus(v); setPage(1); }} options={[
          { value: 'all', label: 'All' }, { value: 'failed', label: 'Failed' }, { value: 'pending', label: 'Pending' },
          { value: 'sent', label: 'Sent to SMTP' }, { value: 'superseded', label: 'Superseded' },
        ]} />
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-64">
            <Select
              aria-label="Email type"
              value={kind}
              onChange={(e) => { setKind(e.target.value as NotificationKind | ''); setPage(1); }}
              options={[
                { value: '', label: 'All email types' },
                ...(Object.keys(NOTIFICATION_KIND_LABELS) as NotificationKind[]).map((value) => ({
                  value, label: NOTIFICATION_KIND_LABELS[value],
                })),
              ]}
            />
          </div>
          <OrgSearch value={organization} onChange={(v) => { setOrganization(v); setPage(1); }} />
        </div>
      </div>
      {counts && (
        <p className="mb-3 text-xs text-slate-500" data-testid="email-status-counts">
          {counts.failed} failed · {counts.pending} pending · {counts.sent} sent to SMTP · {counts.superseded} superseded
        </p>
      )}
      <ListFrame data={data} error={error} retry={retry} onPage={setPage} itemLabel="emails"
        emptyTitle={status === 'all' && !kind && !organization ? 'No emails yet' : 'No matching emails'}
        emptyDescription={status === 'all' && !kind && !organization
          ? 'No plan lifecycle email has been queued yet.'
          : 'No email matches these filters.'}>
        {(items: NotificationRow[]) => (
          <table className="min-w-full divide-y divide-slate-100">
            <thead><tr><th className={TH}>Email</th><th className={TH}>Status</th><th className={TH}>Organization</th><th className={TH}>Attempts</th><th className={TH}>Times</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((n) => (
                <tr key={n.id} data-testid="email-row">
                  <td className={TD}>
                    {NOTIFICATION_KIND_LABELS[n.kind as NotificationKind] ?? n.kind}
                    {n.recipient_hint && <p className="text-xs text-slate-500">To {n.recipient_hint}</p>}
                  </td>
                  <td className={TD}>
                    <StateBadge map={NOTIFICATION_BADGES} value={n.status} />
                    {n.error_label && <p className="mt-1 text-xs text-slate-500" data-testid="email-error">{n.error_label}</p>}
                  </td>
                  <td className={TD}><OrgLink id={n.organization_id} name={n.organization_name} /></td>
                  <td className={TD}>{n.attempts}</td>
                  <td className={TD}>
                    <p className="text-xs">Queued {formatDateTime(n.created_at)}</p>
                    <p className="text-xs text-slate-500">Updated {formatDateTime(n.updated_at)}</p>
                    {n.sent_at && <p className="text-xs text-slate-500">Sent to SMTP {formatDateTime(n.sent_at)}</p>}
                    {n.next_attempt_at && <p className="text-xs text-amber-700">Next attempt {formatDateTime(n.next_attempt_at)}</p>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </ListFrame>
    </Section>
  );
}

export function BillingPage() {
  const [tab, setTab] = useState<Tab>('subscriptions');
  return (
    <div className="space-y-6">
      <PageHeader
        title="Plan billing"
        subtitle="Rooman's own plan subscriptions, checkouts, Razorpay webhooks and customer email delivery, as stored by the application. Read-only except for recording payment-review resolutions; tenant payments are not shown here."
      />
      <FilterTabs label="Billing view" value={tab} onChange={setTab} options={TABS} />
      {tab === 'subscriptions' && <SubscriptionsTab />}
      {tab === 'checkouts' && <CheckoutsTab />}
      {tab === 'webhooks' && <WebhooksTab />}
      {tab === 'review' && <ReviewTab />}
      {tab === 'email' && <EmailDeliveryTab />}
    </div>
  );
}
