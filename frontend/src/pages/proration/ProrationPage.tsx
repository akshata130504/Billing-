import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Repeat, Scale, CalendarClock, CheckCircle2, ReceiptText, ExternalLink } from 'lucide-react';
import type { PlanOut, SubscribablePlanOption, SubscriptionOut } from '../../types/api';
import type { SubscriptionChangeOut } from '../../types/proration';
import { subscriptionService } from '../../services/subscriptionService';
import { catalogService } from '../../services/catalogService';
import { prorationService } from '../../services/prorationService';
import { StatCard, type StatCardProps } from '../../components/common/StatCard';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { useAuth } from '../../hooks/useAuth';
import { useToast } from '../../components/common/Toast';
import { formatMoney, formatDate, humanize, statusVariant, parseMoney } from '../../utils/format';
import { ProrationExplainerCard } from './ProrationExplainerCard';
import { SubscriptionPicker } from './SubscriptionPicker';
import { ChangePlanner } from './ChangePlanner';
import { ChangeHistoryTable } from './ChangeHistoryTable';
import { formatQuantity, intervalLabel } from './prorationLabels';
import { usePageSpec } from '../../appUi/usePageSpec';
import type { EditableProps } from '../../appUi/UiConfigContext';

const PAGE_SIZE = 50;

export function ProrationPage() {
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const { showToast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const canApply = hasRole('finance');
  const canCancel = hasRole('admin');
  const ui = usePageSpec('proration');

  // Eligible subscriptions (active + trialing)
  const [subscriptions, setSubscriptions] = useState<SubscriptionOut[]>([]);
  const [subsLoading, setSubsLoading] = useState(true);
  const [subsError, setSubsError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // Plans catalogue (names for the change history) and the plans a subscription can move to
  // (legacy plans plus Catalog / Plans & Pricing plan offerings).
  const [plans, setPlans] = useState<PlanOut[]>([]);
  const [planOptions, setPlanOptions] = useState<SubscribablePlanOption[]>([]);
  const [plansLoading, setPlansLoading] = useState(true);

  // Selection + history
  const [selected, setSelected] = useState<SubscriptionOut | null>(null);
  const [changes, setChanges] = useState<SubscriptionChangeOut[]>([]);
  const [changesLoading, setChangesLoading] = useState(false);
  const [changesError, setChangesError] = useState<string | null>(null);

  const fetchSubscriptions = useCallback(async () => {
    try {
      setSubsLoading(true);
      setSubsError(null);
      const search = searchQuery.trim() || undefined;
      const [active, trialing] = await Promise.all([
        subscriptionService.list({ status: 'active', search, page_size: PAGE_SIZE }),
        subscriptionService.list({ status: 'trialing', search, page_size: PAGE_SIZE }),
      ]);
      const merged = [...active.items, ...trialing.items].sort((a, b) =>
        a.subscription_number.localeCompare(b.subscription_number)
      );
      setSubscriptions(merged);
    } catch (err: any) {
      setSubsError(err?.message || 'Failed to load subscriptions');
    } finally {
      setSubsLoading(false);
    }
  }, [searchQuery]);

  const fetchPlans = useCallback(async () => {
    try {
      setPlansLoading(true);
      const [data, options] = await Promise.all([
        catalogService.listPlans({ is_active: true, page_size: 100 }),
        subscriptionService.planOptions(),
      ]);
      setPlans(data.items);
      setPlanOptions(options);
    } catch (err: any) {
      showToast('error', 'Could not load plans', err?.message || 'The plan catalogue is unavailable.');
    } finally {
      setPlansLoading(false);
    }
  }, [showToast]);

  const fetchChanges = useCallback(async (subscriptionId: string) => {
    try {
      setChangesLoading(true);
      setChangesError(null);
      const data = await prorationService.list(subscriptionId);
      setChanges(data);
    } catch (err: any) {
      setChangesError(err?.message || 'Failed to load change history');
    } finally {
      setChangesLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSubscriptions();
  }, [fetchSubscriptions]);

  useEffect(() => {
    fetchPlans();
  }, [fetchPlans]);

  // Deep-link: /proration?subscription=<id> preselects (also used after list reload to keep selection fresh).
  useEffect(() => {
    const wanted = searchParams.get('subscription');
    if (!wanted) return;
    const match = subscriptions.find((s) => s.id === wanted);
    if (match && (!selected || selected.id !== match.id || selected.updated_at !== match.updated_at)) {
      setSelected(match);
    }
  }, [subscriptions, searchParams, selected]);

  useEffect(() => {
    if (selected) fetchChanges(selected.id);
    else setChanges([]);
  }, [selected?.id, fetchChanges]);

  const handleSelect = (sub: SubscriptionOut) => {
    setSelected(sub);
    setSearchParams({ subscription: sub.id }, { replace: true });
  };

  const handleApplied = async (change: SubscriptionChangeOut) => {
    if (!selected) return;
    // Immediate changes mutate the subscription; refresh its terms and the history.
    setChanges((prev) => [change, ...prev]);
    try {
      const fresh = await subscriptionService.get(selected.id);
      setSelected(fresh);
      setSubscriptions((prev) => prev.map((s) => (s.id === fresh.id ? fresh : s)));
    } catch {
      // Non-blocking: history is already updated; the list reload below will catch up.
    }
    fetchChanges(selected.id);
  };

  const handleCancelled = (updated: SubscriptionChangeOut) => {
    setChanges((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  };

  // Stats — cheap: derived from the loaded subscription page and the selected subscription's history.
  const stats = useMemo(() => {
    const scheduled = changes.filter((c) => c.status === 'scheduled');
    const applied = changes.filter((c) => c.status === 'applied');
    const netBilled = applied.reduce((sum, c) => sum + (parseMoney(c.net_amount) || 0), 0);
    return {
      eligible: subscriptions.length,
      scheduled: scheduled.length,
      nextScheduled: scheduled.map((c) => c.effective_date).sort()[0] as string | undefined,
      applied: applied.length,
      netBilled,
    };
  }, [subscriptions, changes]);

  const currency = selected?.currency ?? selected?.plan.currency ?? 'INR';
  const currentRate = selected ? parseMoney(selected.plan.unit_amount) * selected.quantity : 0;

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div {...ui.edit('header')}>
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-1">
            <Repeat className="w-4 h-4" />
            {ui.text('header', 'eyebrow')}
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{ui.text('header', 'title')}</h1>
          <p className="text-sm text-slate-500 mt-1">
            {ui.text('header', 'subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/subscriptions')}
            leadingIcon={<ExternalLink className="w-4 h-4" />}
          >
            All subscriptions
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" {...ui.edit('kpis')}>
        {ui.render('kpis', {
          eligible: (item, edit) => (
            <ProrationKpi
              edit={edit}
              title={item.label}
              value={subsLoading ? '…' : stats.eligible}
              icon={<Repeat className="w-5 h-5" />}
              comparisonText="Active or trialing, changeable mid-cycle"
            />
          ),
          scheduled: (item, edit) => (
            <ProrationKpi
              edit={edit}
              title={item.label}
              value={selected ? (changesLoading ? '…' : stats.scheduled) : '—'}
              icon={<CalendarClock className="w-5 h-5" />}
              comparisonText={
                selected
                  ? stats.nextScheduled
                    ? `Next runs ${formatDate(stats.nextScheduled)}`
                    : 'Nothing pending for this subscription'
                  : 'Select a subscription'
              }
            />
          ),
          applied: (item, edit) => (
            <ProrationKpi
              edit={edit}
              title={item.label}
              value={selected ? (changesLoading ? '…' : stats.applied) : '—'}
              icon={<CheckCircle2 className="w-5 h-5" />}
              comparisonText={selected ? `On ${selected.subscription_number}` : 'Select a subscription'}
            />
          ),
          net_billing: (item, edit) => (
            <ProrationKpi
              edit={edit}
              title={item.label}
              value={selected ? (changesLoading ? '…' : formatMoney(stats.netBilled, currency)) : '—'}
              icon={<ReceiptText className="w-5 h-5" />}
              comparisonText={selected ? 'Invoices minus credit notes from applied changes' : 'Select a subscription'}
            />
          ),
        })}
      </div>

      <ProrationExplainerCard />

      <SubscriptionPicker
        subscriptions={subscriptions}
        selectedId={selected?.id ?? null}
        loading={subsLoading}
        error={subsError}
        searchQuery={searchInput}
        onSearchChange={setSearchInput}
        onSearchSubmit={() => setSearchQuery(searchInput)}
        onSelect={handleSelect}
        onRetry={fetchSubscriptions}
        canCreate={canApply}
        onCreateNew={() => navigate('/subscriptions/new')}
      />

      {selected && (
        <>
          {/* Current terms */}
          <div className="bg-white rounded-xl border border-slate-200/90 shadow-card p-5">
            <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="p-2.5 rounded-xl bg-blue-50 text-brand-600 border border-blue-100 shrink-0">
                  <Scale className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h2 className="text-sm font-semibold text-slate-900 tracking-tight">
                      {selected.subscription_number} · {selected.customer.display_name}
                    </h2>
                    <Badge variant={statusVariant(selected.status)} size="sm" dot>
                      {humanize(selected.status)}
                    </Badge>
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5" {...ui.edit('terms')}>
                    {ui.text('terms', 'description')}
                  </p>
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => navigate(`/subscriptions/${selected.id}`)}>
                View subscription
              </Button>
            </div>
            <dl className="mt-4 grid grid-cols-2 md:grid-cols-5 gap-4 text-xs" {...ui.edit('terms_fields')}>
              {ui.render('terms_fields', {
                plan: (item, edit) => (
                  <div {...edit}>
                    <dt className="text-slate-500 uppercase tracking-wide text-[11px] font-medium">{item.label}</dt>
                    <dd className="mt-1 font-semibold text-slate-900">{selected.plan.name}</dd>
                    <dd className="text-slate-400 text-[11px]">{selected.plan.product_name}</dd>
                  </div>
                ),
                unit_price: (item, edit) => (
                  <div {...edit}>
                    <dt className="text-slate-500 uppercase tracking-wide text-[11px] font-medium">{item.label}</dt>
                    <dd className="mt-1 font-semibold text-slate-900 tabular-nums">
                      {formatMoney(selected.plan.unit_amount, selected.plan.currency)}
                    </dd>
                    <dd className="text-slate-400 text-[11px]">
                      per {intervalLabel(selected.plan.billing_interval, selected.plan.interval_count)}
                    </dd>
                  </div>
                ),
                quantity: (item, edit) => (
                  <div {...edit}>
                    <dt className="text-slate-500 uppercase tracking-wide text-[11px] font-medium">{item.label}</dt>
                    <dd className="mt-1 font-semibold text-slate-900 tabular-nums">{formatQuantity(selected.quantity)}</dd>
                    <dd className="text-slate-400 text-[11px]">{humanize(selected.pricing_model ?? selected.plan.billing_interval)}</dd>
                  </div>
                ),
                rate: (item, edit) => (
                  <div {...edit}>
                    <dt className="text-slate-500 uppercase tracking-wide text-[11px] font-medium">{item.label}</dt>
                    <dd className="mt-1 font-semibold text-slate-900 tabular-nums">{formatMoney(currentRate, currency)}</dd>
                    <dd className="text-slate-400 text-[11px]">before tax, per cycle</dd>
                  </div>
                ),
                period: (item, edit) => (
                  <div {...edit}>
                    <dt className="text-slate-500 uppercase tracking-wide text-[11px] font-medium">{item.label}</dt>
                    <dd className="mt-1 font-semibold text-slate-900 whitespace-nowrap">
                      {formatDate(selected.current_period_start)} → {formatDate(selected.current_period_end)}
                    </dd>
                    <dd className="text-slate-400 text-[11px]">
                      {selected.next_billing_date ? `Next bill ${formatDate(selected.next_billing_date)}` : 'No next billing date'}
                    </dd>
                  </div>
                ),
              })}
            </dl>
          </div>

          <ChangePlanner
            subscription={selected}
            planOptions={planOptions}
            plansLoading={plansLoading}
            canApply={canApply}
            onApplied={handleApplied}
            onCancel={() => {
              setSelected(null);
              setSearchParams({}, { replace: true });
            }}
          />

          <ChangeHistoryTable
            subscriptionId={selected.id}
            subscriptionNumber={selected.subscription_number}
            currency={currency}
            changes={changes}
            loading={changesLoading}
            error={changesError}
            plans={plans}
            canCancel={canCancel}
            onRefresh={() => fetchChanges(selected.id)}
            onCancelled={handleCancelled}
          />
        </>
      )}
    </div>
  );
}

/** A StatCard the visual-editor preview can select (StatCard itself takes no extra props). */
function ProrationKpi({ edit, ...card }: { edit: EditableProps } & StatCardProps) {
  return (
    <div className="flex" {...edit}>
      <StatCard className="flex-1" {...card} />
    </div>
  );
}
