import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  BadgeIndianRupee,
  CheckCircle2,
  Clock,
  CreditCard,
  ExternalLink,
  FileText,
  Pencil,
  Plus,
  RefreshCw,
  Repeat,
  Search,
  ShieldCheck,
  Siren,
  Star,
  TrendingUp,
  PauseCircle,
} from 'lucide-react';
import { dunningService } from '../../services/dunningService';
import { customerService } from '../../services/customerService';
import type {
  DunningCase,
  DunningCaseStatus,
  DunningMetrics,
  DunningPolicy,
  ExpiringCardNotice,
} from '../../types/dunning';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { StatCard } from '../../components/common/StatCard';
import { LoadingState } from '../../components/common/LoadingState';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatDate, formatDateTime, formatMoney, formatPercent, formatRelative, humanize } from '../../utils/format';
import { DunningCaseDrawer } from './DunningCaseDrawer';
import { DunningPolicyModal } from './DunningPolicyModal';
import {
  ACTIVE_CASE_STATUSES,
  CASE_STATUS_ORDER,
  FINAL_ACTION_CONFIG,
  caseStatusBadge,
  caseStatusLabel,
} from './dunningUi';

type TabId = 'cases' | 'policies' | 'cards';

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'cases', label: 'Cases', icon: <Siren className="w-3.5 h-3.5" /> },
  { id: 'policies', label: 'Policies', icon: <ShieldCheck className="w-3.5 h-3.5" /> },
  { id: 'cards', label: 'Expiring Cards', icon: <CreditCard className="w-3.5 h-3.5" /> },
];

const CARD_WINDOWS = [30, 60, 90];

interface Loadable<T> {
  data: T;
  loading: boolean;
  error: string | null;
}

export function DunningPage() {
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canActOnCases = hasRole('finance');
  const canManagePolicies = hasRole('admin');

  const [tab, setTab] = useState<TabId>('cases');

  // Metrics
  const [metrics, setMetrics] = useState<DunningMetrics | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);

  // Cases
  const [cases, setCases] = useState<Loadable<DunningCase[]>>({ data: [], loading: true, error: null });
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | DunningCaseStatus>('active');
  const [searchQuery, setSearchQuery] = useState('');
  const [customerNames, setCustomerNames] = useState<Record<string, string>>({});
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);

  // Policies
  const [policies, setPolicies] = useState<Loadable<DunningPolicy[]>>({ data: [], loading: true, error: null });
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<DunningPolicy | null>(null);
  const [defaultCandidate, setDefaultCandidate] = useState<DunningPolicy | null>(null);
  const [policyActionId, setPolicyActionId] = useState<string | null>(null);

  // Expiring cards
  const [cards, setCards] = useState<Loadable<ExpiringCardNotice[]>>({ data: [], loading: true, error: null });
  const [cardDays, setCardDays] = useState<number>(30);

  // --- Loaders --------------------------------------------------------------

  const loadMetrics = useCallback(async () => {
    try {
      setMetricsError(null);
      setMetrics(await dunningService.metrics());
    } catch (err: any) {
      setMetricsError(err?.message || 'Failed to load dunning metrics.');
    }
  }, []);

  const loadCases = useCallback(async () => {
    setCases((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const params =
        statusFilter === 'all' || statusFilter === 'active' ? undefined : { status: statusFilter };
      const data = await dunningService.listCases(params);
      setCases({ data, loading: false, error: null });
    } catch (err: any) {
      setCases({ data: [], loading: false, error: err?.message || 'Failed to load dunning cases.' });
    }
  }, [statusFilter]);

  const loadPolicies = useCallback(async () => {
    setPolicies((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await dunningService.listPolicies();
      setPolicies({ data, loading: false, error: null });
    } catch (err: any) {
      setPolicies({ data: [], loading: false, error: err?.message || 'Failed to load dunning policies.' });
    }
  }, []);

  const loadCards = useCallback(async () => {
    setCards((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await dunningService.expiringCards(cardDays);
      setCards({ data, loading: false, error: null });
    } catch (err: any) {
      setCards({ data: [], loading: false, error: err?.message || 'Failed to load expiring cards.' });
    }
  }, [cardDays]);

  // Customer names are not part of the case list payload; enrich from the customer directory (non-blocking).
  const loadCustomerNames = useCallback(async () => {
    try {
      const res = await customerService.list({ page: 1, page_size: 100 });
      const map: Record<string, string> = {};
      res.items.forEach((c) => {
        map[c.id] = c.display_name;
      });
      setCustomerNames(map);
    } catch {
      // Table falls back to customer IDs.
    }
  }, []);

  useEffect(() => {
    loadMetrics();
    loadCustomerNames();
  }, [loadMetrics, loadCustomerNames]);

  useEffect(() => {
    loadCases();
  }, [loadCases]);

  useEffect(() => {
    loadPolicies();
  }, [loadPolicies]);

  useEffect(() => {
    loadCards();
  }, [loadCards]);

  const refreshAll = () => {
    loadMetrics();
    loadCases();
    loadPolicies();
    loadCards();
  };

  const handleCaseChanged = () => {
    loadMetrics();
    loadCases();
  };

  // --- Derived ---------------------------------------------------------------

  const visibleCases = useMemo(() => {
    let list = cases.data;
    if (statusFilter === 'active') list = list.filter((c) => ACTIVE_CASE_STATUSES.includes(c.status));
    const q = searchQuery.trim().toLowerCase();
    if (q) {
      list = list.filter((c) => {
        const name = customerNames[c.customer_id] ?? '';
        return (
          c.case_number.toLowerCase().includes(q) ||
          name.toLowerCase().includes(q) ||
          c.customer_id.toLowerCase().includes(q) ||
          c.invoice_id.toLowerCase().includes(q) ||
          c.trigger_reason.toLowerCase().includes(q)
        );
      });
    }
    return list;
  }, [cases.data, statusFilter, searchQuery, customerNames]);

  const currency = metrics?.currency ?? 'INR';

  // --- Policy actions -----------------------------------------------------------

  const openCreatePolicy = () => {
    setEditingPolicy(null);
    setPolicyModalOpen(true);
  };

  const openEditPolicy = (policy: DunningPolicy) => {
    setEditingPolicy(policy);
    setPolicyModalOpen(true);
  };

  const confirmMakeDefault = async () => {
    if (!defaultCandidate) return;
    try {
      setPolicyActionId(defaultCandidate.id);
      await dunningService.updatePolicy(defaultCandidate.id, { is_default: true, is_active: true });
      showToast('success', 'Default policy updated', `"${defaultCandidate.name}" now applies to new dunning cases.`);
      setDefaultCandidate(null);
      loadPolicies();
    } catch (err: any) {
      showToast('error', 'Could not set default policy', err?.message);
    } finally {
      setPolicyActionId(null);
    }
  };

  const toggleActive = async (policy: DunningPolicy) => {
    try {
      setPolicyActionId(policy.id);
      await dunningService.updatePolicy(policy.id, { is_active: !policy.is_active });
      showToast(
        'success',
        policy.is_active ? 'Policy deactivated' : 'Policy activated',
        `"${policy.name}" is now ${policy.is_active ? 'inactive' : 'active'}.`
      );
      loadPolicies();
    } catch (err: any) {
      showToast('error', 'Could not update policy', err?.message);
    } finally {
      setPolicyActionId(null);
    }
  };

  // --- Render -----------------------------------------------------------------

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-1">
            <Repeat className="w-4 h-4" />
            Subscriptions
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Dunning</h1>
          <p className="text-sm text-slate-500 mt-1">
            Recover failed subscription payments with automated retries, customer notifications, and policy-driven final actions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={refreshAll}
            leadingIcon={<RefreshCw className="w-4 h-4" />}
          >
            Refresh
          </Button>
          {canManagePolicies && (
            <Button
              variant="primary"
              size="sm"
              onClick={openCreatePolicy}
              leadingIcon={<Plus className="w-4 h-4" />}
            >
              New Policy
            </Button>
          )}
        </div>
      </div>

      {/* Metrics */}
      {metricsError ? (
        <ErrorState title="Metrics unavailable" message={metricsError} onRetry={loadMetrics} />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard
            title="Active Cases"
            value={metrics?.active_cases ?? '—'}
            comparisonText={metrics ? `${metrics.total_cases} total cases` : undefined}
            icon={<Siren className="w-4 h-4" />}
          />
          <StatCard
            title="Amount at Risk"
            value={metrics ? formatMoney(metrics.total_amount_at_risk, currency, { compact: true }) : '—'}
            comparisonText="Across open cases"
            icon={<AlertTriangle className="w-4 h-4" />}
          />
          <StatCard
            title="Recovered"
            value={metrics ? formatMoney(metrics.total_amount_recovered, currency, { compact: true }) : '—'}
            comparisonText={metrics ? `${metrics.recovered_cases} cases recovered` : undefined}
            icon={<BadgeIndianRupee className="w-4 h-4" />}
          />
          <StatCard
            title="Recovery Rate"
            value={metrics ? formatPercent(metrics.recovery_rate_pct) : '—'}
            comparisonText="Recovered ÷ closed cases"
            icon={<TrendingUp className="w-4 h-4" />}
          />
          <StatCard
            title="Paused"
            value={metrics?.paused_cases ?? '—'}
            comparisonText="Awaiting manual resume"
            icon={<PauseCircle className="w-4 h-4" />}
          />
          <StatCard
            title="Exhausted"
            value={metrics?.exhausted_cases ?? '—'}
            comparisonText={metrics ? `${metrics.stopped_cases} stopped manually` : undefined}
            icon={<Clock className="w-4 h-4" />}
          />
        </div>
      )}

      {/* Tabs + filters */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 scrollbar-none">
            {TABS.map((t) => {
              const isActive = tab === t.id;
              const count =
                t.id === 'cases'
                  ? metrics?.active_cases
                  : t.id === 'policies'
                    ? policies.data.length
                    : cards.data.length;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 ${
                    isActive
                      ? 'bg-brand-50 text-brand-700 border border-brand-200/60 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50 border border-transparent'
                  }`}
                >
                  {t.icon}
                  {t.label}
                  {count !== undefined && (
                    <span
                      className={`px-1.5 py-0.5 rounded-md text-[10px] tabular-nums ${
                        isActive ? 'bg-white text-brand-700' : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {tab === 'cases' && (
            <div className="flex items-center gap-2 w-full md:w-auto">
              <div className="relative flex-1 md:w-72">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search case, customer, invoice..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-colors"
                />
              </div>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
                className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="active">Active (open, scheduled, retrying)</option>
                <option value="all">All statuses</option>
                {CASE_STATUS_ORDER.map((s) => (
                  <option key={s} value={s}>
                    {caseStatusLabel(s)}
                  </option>
                ))}
              </select>
            </div>
          )}

          {tab === 'cards' && (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-slate-500">Expiring within</span>
              <div className="flex items-center gap-1">
                {CARD_WINDOWS.map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setCardDays(d)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
                      cardDays === d
                        ? 'bg-brand-50 text-brand-700 border-brand-200/60'
                        : 'text-slate-600 hover:bg-slate-50 border-transparent'
                    }`}
                  >
                    {d} days
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Cases tab */}
      {tab === 'cases' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          {cases.loading ? (
            <div className="py-16">
              <LoadingState message="Loading dunning cases..." />
            </div>
          ) : cases.error ? (
            <ErrorState title="Could not load cases" message={cases.error} onRetry={loadCases} className="border-0 rounded-none" />
          ) : visibleCases.length === 0 ? (
            <EmptyState
              className="border-0"
              icon={<CheckCircle2 className="w-8 h-8 text-emerald-500" />}
              title={
                cases.data.length === 0 && statusFilter === 'active'
                  ? 'No active dunning cases'
                  : 'No cases match this filter'
              }
              description={
                cases.data.length === 0 && statusFilter === 'active'
                  ? 'Every autocharge payment is settled. A case opens automatically the moment a subscription charge fails.'
                  : 'Try a different status or clear the search to see more cases.'
              }
              action={
                statusFilter !== 'all' || searchQuery ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setStatusFilter('all');
                      setSearchQuery('');
                    }}
                  >
                    Show all cases
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-600">
                <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                  <tr>
                    <th className="px-5 py-3.5">Case</th>
                    <th className="px-5 py-3.5">Customer</th>
                    <th className="px-5 py-3.5">Invoice</th>
                    <th className="px-5 py-3.5 text-right">Amount Due</th>
                    <th className="px-5 py-3.5">Attempts</th>
                    <th className="px-5 py-3.5">Next Retry</th>
                    <th className="px-5 py-3.5">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {visibleCases.map((c) => {
                    const overdue = c.next_retry_at ? new Date(c.next_retry_at).getTime() < Date.now() : false;
                    return (
                      <tr
                        key={c.id}
                        className="hover:bg-slate-50/70 transition-colors cursor-pointer group"
                        onClick={() => setSelectedCaseId(c.id)}
                      >
                        <td className="px-5 py-4">
                          <div className="font-semibold text-slate-900 font-mono text-xs group-hover:text-blue-600 transition-colors">
                            {c.case_number}
                          </div>
                          <div className="text-xs text-slate-400 mt-0.5">
                            {humanize(c.trigger_reason)} · {formatDate(c.created_at)}
                          </div>
                        </td>
                        <td className="px-5 py-4">
                          <Link
                            to={`/customers/${c.customer_id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="font-medium text-slate-800 hover:text-brand-700 hover:underline"
                          >
                            {customerNames[c.customer_id] ?? (
                              <span className="font-mono text-xs text-slate-500">{c.customer_id.slice(0, 8)}…</span>
                            )}
                          </Link>
                          {c.subscription_id && (
                            <div className="text-xs text-slate-400 mt-0.5 flex items-center gap-1">
                              <Repeat className="w-3 h-3" />
                              Subscription
                            </div>
                          )}
                        </td>
                        <td className="px-5 py-4">
                          <Link
                            to={`/invoices/${c.invoice_id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex items-center gap-1.5 text-brand-700 hover:underline font-medium"
                          >
                            <FileText className="w-3.5 h-3.5" />
                            <span className="font-mono text-xs">{c.invoice_id.slice(0, 8)}…</span>
                            <ExternalLink className="w-3 h-3 text-slate-400" />
                          </Link>
                        </td>
                        <td className="px-5 py-4 text-right font-semibold text-slate-900 tabular-nums">
                          {formatMoney(c.amount_due, c.currency)}
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-2 bg-slate-100 rounded-full overflow-hidden">
                              <div
                                className={`h-full transition-all ${
                                  c.status === 'recovered'
                                    ? 'bg-emerald-500'
                                    : c.status === 'exhausted'
                                      ? 'bg-rose-500'
                                      : 'bg-brand-500'
                                }`}
                                style={{
                                  width: `${c.max_attempts > 0 ? Math.min(100, (c.attempt_count / c.max_attempts) * 100) : 0}%`,
                                }}
                              />
                            </div>
                            <span className="text-xs font-semibold text-slate-700 tabular-nums">
                              {c.attempt_count}/{c.max_attempts}
                            </span>
                          </div>
                        </td>
                        <td className="px-5 py-4 text-xs">
                          {c.next_retry_at && ACTIVE_CASE_STATUSES.includes(c.status) ? (
                            <div className={overdue ? 'text-amber-700 font-medium' : 'text-slate-700'}>
                              <div className="flex items-center gap-1">
                                <Clock className="w-3 h-3 text-slate-400" />
                                {formatRelative(c.next_retry_at)}
                              </div>
                              <div className="text-slate-400 mt-0.5">{formatDateTime(c.next_retry_at)}</div>
                            </div>
                          ) : c.status === 'paused' ? (
                            <span className="text-amber-600">Paused {formatRelative(c.paused_at)}</span>
                          ) : c.status === 'recovered' ? (
                            <span className="text-emerald-600">Recovered {formatRelative(c.recovered_at)}</span>
                          ) : (
                            <span className="text-slate-400 italic">None scheduled</span>
                          )}
                        </td>
                        <td className="px-5 py-4">
                          <Badge variant={caseStatusBadge(c.status)} dot>
                            {caseStatusLabel(c.status)}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Policies tab */}
      {tab === 'policies' && (
        <div>
          {policies.loading ? (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm py-16">
              <LoadingState message="Loading dunning policies..." />
            </div>
          ) : policies.error ? (
            <ErrorState title="Could not load policies" message={policies.error} onRetry={loadPolicies} />
          ) : policies.data.length === 0 ? (
            <EmptyState
              icon={<ShieldCheck className="w-8 h-8 text-slate-400" />}
              title="No dunning policies yet"
              description="A policy defines the retry ladder, customer notifications, and the final action once retries are exhausted."
              action={
                canManagePolicies ? (
                  <Button variant="primary" size="sm" onClick={openCreatePolicy}>
                    <Plus className="w-4 h-4 mr-1.5" />
                    Create first policy
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {policies.data.map((p) => {
                let running = 0;
                const days = p.retry_intervals_days.map((n) => (running += n));
                const busy = policyActionId === p.id;
                return (
                  <div
                    key={p.id}
                    className={`bg-white rounded-xl border shadow-sm overflow-hidden flex flex-col ${
                      p.is_default ? 'border-brand-200' : 'border-slate-200'
                    } ${!p.is_active ? 'opacity-70' : ''}`}
                  >
                    <div className="px-5 py-4 border-b border-slate-100 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="text-sm font-semibold text-slate-900 truncate">{p.name}</h3>
                          {p.is_default && (
                            <Badge variant="primary" size="sm">
                              Default
                            </Badge>
                          )}
                          <Badge variant={p.is_active ? 'success' : 'neutral'} size="sm" dot>
                            {p.is_active ? 'Active' : 'Inactive'}
                          </Badge>
                        </div>
                        <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                          {p.description || 'No description provided.'}
                        </p>
                      </div>
                      {canManagePolicies && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="shrink-0"
                          onClick={() => openEditPolicy(p)}
                          leadingIcon={<Pencil className="w-3.5 h-3.5" />}
                        >
                          Edit
                        </Button>
                      )}
                    </div>

                    <div className="px-5 py-4 space-y-4 flex-1">
                      {/* Schedule */}
                      <div>
                        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                          Retry schedule · {p.total_span_days}-day window
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5 text-xs">
                          <span className="px-2 py-0.5 rounded-md bg-slate-100 border border-slate-200 text-slate-700">
                            Charge fails
                          </span>
                          {days.map((d, i) => (
                            <React.Fragment key={i}>
                              <span className="text-slate-400">→</span>
                              <span className="px-2 py-0.5 rounded-md bg-blue-50 text-brand-700 border border-blue-100">
                                Day {d}
                              </span>
                            </React.Fragment>
                          ))}
                          <span className="text-slate-400">→</span>
                          <span className="px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-100">
                            {FINAL_ACTION_CONFIG[p.final_action]?.label ?? humanize(p.final_action)}
                          </span>
                        </div>
                      </div>

                      <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                        <div>
                          <dt className="text-slate-500">Applies to</dt>
                          <dd className="font-medium text-slate-800 mt-0.5">
                            {p.applies_to_autocharge ? 'Autocharge invoices' : 'Manual invoices'}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-slate-500">Minimum amount</dt>
                          <dd className="font-medium text-slate-800 mt-0.5">
                            {p.min_amount ? formatMoney(p.min_amount, currency) : 'Any amount'}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-slate-500">Manual grace</dt>
                          <dd className="font-medium text-slate-800 mt-0.5">{p.non_autocharge_grace_days} days</dd>
                        </div>
                        <div className="col-span-2 sm:col-span-3">
                          <dt className="text-slate-500">Notifications</dt>
                          <dd className="mt-1 flex flex-wrap gap-1.5">
                            {[
                              ['On failure', p.notify_on_failure],
                              ['Before retry', p.notify_on_retry],
                              ['On recovery', p.notify_on_success],
                              ['ACH: cancel on first failure', p.first_ach_immediate_cancel],
                            ].map(([label, on]) => (
                              <span
                                key={String(label)}
                                className={`px-2 py-0.5 rounded-md border ${
                                  on
                                    ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
                                    : 'bg-slate-50 text-slate-400 border-slate-200 line-through'
                                }`}
                              >
                                {label}
                              </span>
                            ))}
                          </dd>
                        </div>
                      </dl>
                    </div>

                    {canManagePolicies && (
                      <div className="px-5 py-3 bg-slate-50/75 border-t border-slate-100 flex items-center justify-between gap-2 text-xs">
                        <span className="text-slate-400">Updated {formatDate(p.updated_at)}</span>
                        <div className="flex items-center gap-2">
                          <Button variant="ghost" size="sm" onClick={() => toggleActive(p)} isLoading={busy}>
                            {p.is_active ? 'Deactivate' : 'Activate'}
                          </Button>
                          {!p.is_default && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setDefaultCandidate(p)}
                              disabled={busy}
                              leadingIcon={<Star className="w-3.5 h-3.5" />}
                            >
                              Make default
                            </Button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Expiring cards tab */}
      {tab === 'cards' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          {cards.loading ? (
            <div className="py-16">
              <LoadingState message="Checking vaulted cards..." />
            </div>
          ) : cards.error ? (
            <ErrorState title="Could not load expiring cards" message={cards.error} onRetry={loadCards} className="border-0 rounded-none" />
          ) : cards.data.length === 0 ? (
            <EmptyState
              className="border-0"
              icon={<CreditCard className="w-8 h-8 text-emerald-500" />}
              title={`No cards expiring in the next ${cardDays} days`}
              description="Saved customer cards are healthy. Cards nearing expiry appear here so you can nudge customers before a charge fails."
              action={
                cardDays < 90 ? (
                  <Button variant="outline" size="sm" onClick={() => setCardDays(90)}>
                    Look ahead 90 days
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-600">
                <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                  <tr>
                    <th className="px-5 py-3.5">Customer</th>
                    <th className="px-5 py-3.5">Card</th>
                    <th className="px-5 py-3.5">Expires</th>
                    <th className="px-5 py-3.5">Time Left</th>
                    <th className="px-5 py-3.5">Customer Notified</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {cards.data.map((card) => {
                    const urgency = card.days_until_expiry <= 7 ? 'danger' : card.days_until_expiry <= 30 ? 'warning' : 'info';
                    return (
                      <tr key={card.payment_method_id} className="hover:bg-slate-50/70 transition-colors">
                        <td className="px-5 py-4">
                          <Link
                            to={`/customers/${card.customer_id}`}
                            className="font-medium text-slate-900 hover:text-brand-700 hover:underline"
                          >
                            {customerNames[card.customer_id] ?? card.customer_email}
                          </Link>
                          <div className="text-xs text-slate-400 mt-0.5">{card.customer_email}</div>
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <span className="p-1.5 rounded-md bg-slate-100 text-slate-500">
                              <CreditCard className="w-3.5 h-3.5" />
                            </span>
                            <div>
                              <div className="font-medium text-slate-800">
                                {card.card_brand ? humanize(card.card_brand) : 'Card'}{' '}
                                <span className="font-mono text-xs text-slate-500">•••• {card.card_last4}</span>
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-4 font-mono text-xs text-slate-700">
                          {String(card.expiry_month).padStart(2, '0')}/{card.expiry_year}
                        </td>
                        <td className="px-5 py-4">
                          <Badge variant={urgency} size="sm">
                            {card.days_until_expiry <= 0
                              ? 'Expired'
                              : `${card.days_until_expiry} day${card.days_until_expiry === 1 ? '' : 's'}`}
                          </Badge>
                        </td>
                        <td className="px-5 py-4 text-xs">
                          {card.notification_sent ? (
                            <span className="inline-flex items-center gap-1 text-emerald-700 font-medium">
                              <CheckCircle2 className="w-3.5 h-3.5" /> Sent
                            </span>
                          ) : (
                            <span className="text-slate-400">Not yet</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Case detail drawer */}
      <DunningCaseDrawer
        caseId={selectedCaseId}
        onClose={() => setSelectedCaseId(null)}
        canAct={canActOnCases}
        onChanged={handleCaseChanged}
      />

      {/* Policy create / edit */}
      <DunningPolicyModal
        isOpen={policyModalOpen}
        onClose={() => setPolicyModalOpen(false)}
        policy={editingPolicy}
        onSaved={() => loadPolicies()}
      />

      {/* Make default confirmation */}
      <ConfirmDialog
        isOpen={defaultCandidate !== null}
        onClose={() => setDefaultCandidate(null)}
        onConfirm={confirmMakeDefault}
        title="Make this the default policy?"
        description={
          defaultCandidate
            ? `"${defaultCandidate.name}" will apply to every new dunning case that no other policy matches. The current default is demoted.`
            : undefined
        }
        confirmLabel="Set as default"
        isLoading={policyActionId !== null}
      />
    </div>
  );
}
