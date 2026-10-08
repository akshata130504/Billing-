import { Fragment, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Activity,
  ChevronRight,
  Gauge,
  Layers,
  Lock,
  Plus,
  PlusCircle,
  RefreshCw,
  Repeat,
  Search,
  Sigma,
  Upload,
  Zap,
} from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { StatCard, type StatCardProps } from '../../components/common/StatCard';
import { useAuth } from '../../hooks/useAuth';
import { meterService } from '../../services/meterService';
import type { SubscriptionOut } from '../../types/api';
import {
  AGGREGATION_TYPES,
  type AggregationType,
  type RecordedUsageEvent,
  type UsageAggregateOut,
  type UsageMeterOut,
} from '../../types/meters';
import { formatDate, formatDateTime, formatMoney, humanize } from '../../utils/format';
import { BatchImportModal } from './BatchImportModal';
import { FinalizeUsageModal } from './FinalizeUsageModal';
import { MeterDetailModal } from './MeterDetailModal';
import { NewMeterModal } from './NewMeterModal';
import { RecordUsageModal } from './RecordUsageModal';
import { AGGREGATION_LABELS, formatQuantity, normaliseApiTimestamp } from './usageUtils';
import { usePageSpec } from '../../appUi/usePageSpec';
import type { EditableProps } from '../../appUi/UiConfigContext';

/** Meter-table columns whose header is right-aligned (their cells align themselves). */
const METER_RIGHT_ALIGNED = new Set(['session_usage', 'actions']);

interface SessionAggregate {
  aggregate: UsageAggregateOut;
  subscription_label: string;
  currency: string;
}

type StatusFilter = 'all' | 'active' | 'inactive';

export function UsageMeteringPage() {
  const { hasRole } = useAuth();
  const canManageMeters = hasRole('admin'); // POST /meters requires admin
  const canFinalize = hasRole('finance'); // finalize-usage requires finance
  const canRecord = true; // event ingestion is open to every authenticated member
  const ui = usePageSpec('usage');

  const [meters, setMeters] = useState<UsageMeterOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [aggregationFilter, setAggregationFilter] = useState<'all' | AggregationType>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

  // In-session activity (the API has no endpoint for listing events or aggregates).
  const [sessionEvents, setSessionEvents] = useState<RecordedUsageEvent[]>([]);
  const [sessionAggregates, setSessionAggregates] = useState<SessionAggregate[]>([]);

  // Dialogs
  const [newMeterOpen, setNewMeterOpen] = useState(false);
  const [recordOpen, setRecordOpen] = useState(false);
  const [recordMeterCode, setRecordMeterCode] = useState<string | null>(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const [finalizeOpen, setFinalizeOpen] = useState(false);
  const [detailMeter, setDetailMeter] = useState<UsageMeterOut | null>(null);

  const loadMeters = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await meterService.list();
      setMeters(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load usage meters');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMeters();
  }, [loadMeters]);

  const filteredMeters = useMemo(() => {
    const q = search.trim().toLowerCase();
    return meters.filter((m) => {
      if (aggregationFilter !== 'all' && m.aggregation_type !== aggregationFilter) return false;
      if (statusFilter === 'active' && !m.is_active) return false;
      if (statusFilter === 'inactive' && m.is_active) return false;
      if (!q) return true;
      return (
        m.name.toLowerCase().includes(q) ||
        m.code.toLowerCase().includes(q) ||
        m.unit_name.toLowerCase().includes(q) ||
        (m.description ?? '').toLowerCase().includes(q)
      );
    });
  }, [meters, search, aggregationFilter, statusFilter]);

  const activeCount = useMemo(() => meters.filter((m) => m.is_active).length, [meters]);
  const aggregationTypesInUse = useMemo(() => {
    const set = new Set<AggregationType>(meters.map((m) => m.aggregation_type));
    return AGGREGATION_TYPES.filter((t) => set.has(t));
  }, [meters]);
  const sessionEventCount = useMemo(() => sessionEvents.filter((r) => !r.replayed).length, [sessionEvents]);
  const eventsPerMeter = useMemo(() => {
    const map = new Map<string, { count: number; total: number }>();
    sessionEvents.forEach((r) => {
      if (r.replayed) return;
      const cur = map.get(r.event.meter_id) ?? { count: 0, total: 0 };
      cur.count += 1;
      cur.total += Number(r.event.quantity) || 0;
      map.set(r.event.meter_id, cur);
    });
    return map;
  }, [sessionEvents]);
  const knownKeys = useMemo(() => new Set(sessionEvents.map((r) => r.event.idempotency_key)), [sessionEvents]);
  const meterById = useMemo(() => new Map(meters.map((m) => [m.id, m])), [meters]);

  const openRecord = (meterCode?: string | null) => {
    setRecordMeterCode(meterCode ?? null);
    setDetailMeter(null);
    setRecordOpen(true);
  };

  const handleRecorded = (items: RecordedUsageEvent | RecordedUsageEvent[]) => {
    const list = Array.isArray(items) ? items : [items];
    setSessionEvents((prev) => {
      const seen = new Set(prev.map((r) => r.event.id));
      const fresh = list.filter((r) => !seen.has(r.event.id));
      return [...fresh, ...prev];
    });
  };

  const handleFinalized = (aggregates: UsageAggregateOut[], subscription: SubscriptionOut | null) => {
    if (aggregates.length === 0) return;
    const added = aggregates.map((aggregate) => ({
      aggregate,
      subscription_label: subscription
        ? `${subscription.subscription_number} · ${subscription.customer.display_name}`
        : aggregate.subscription_id,
      currency: subscription?.currency ?? 'INR',
    }));
    const addedIds = new Set(aggregates.map((a) => a.id));
    setSessionAggregates((prev) => [...added, ...prev.filter((a) => !addedIds.has(a.aggregate.id))]);
  };

  const hasFilters = search.trim() !== '' || aggregationFilter !== 'all' || statusFilter !== 'all';

  const columns = ui.shown('columns');
  const meterCells: Record<string, (m: UsageMeterOut, usage: { count: number; total: number } | undefined) => ReactNode> = {
    meter: (m) => (
      <td className="px-5 py-4">
        <div className="font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">{m.name}</div>
        {m.description && (
          <div className="text-xs text-slate-400 mt-0.5 max-w-xs truncate" title={m.description}>
            {m.description}
          </div>
        )}
      </td>
    ),
    code: (m) => (
      <td className="px-5 py-4">
        <code className="text-xs font-mono bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">{m.code}</code>
      </td>
    ),
    unit: (m) => (
      <td className="px-5 py-4 text-slate-700">{m.unit_name}</td>
    ),
    aggregation: (m) => (
      <td className="px-5 py-4">
        <Badge variant="info" title={AGGREGATION_LABELS[m.aggregation_type].hint}>
          {AGGREGATION_LABELS[m.aggregation_type].label}
        </Badge>
      </td>
    ),
    session_usage: (m, usage) => (
      <td className="px-5 py-4 text-right tabular-nums">
        {usage ? (
          <div>
            <div className="font-medium text-slate-900">
              {formatQuantity(usage.total)} {m.unit_name}
            </div>
            <div className="text-xs text-slate-400">
              {usage.count} event{usage.count === 1 ? '' : 's'}
            </div>
          </div>
        ) : (
          <span className="text-slate-400">—</span>
        )}
      </td>
    ),
    status: (m) => (
      <td className="px-5 py-4">
        <Badge variant={m.is_active ? 'success' : 'neutral'} dot>
          {m.is_active ? 'Active' : 'Inactive'}
        </Badge>
      </td>
    ),
    created: (m) => (
      <td className="px-5 py-4 text-slate-500 whitespace-nowrap">{formatDate(normaliseApiTimestamp(m.created_at))}</td>
    ),
    actions: (m) => (
      <td className="px-5 py-4 text-right">
        <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
          {canRecord && (
            <Button
              variant="ghost"
              size="sm"
              className="text-xs"
              disabled={!m.is_active}
              onClick={() => openRecord(m.code)}
            >
              Record
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            className="text-xs flex items-center gap-1"
            onClick={() => setDetailMeter(m)}
          >
            <span>Details</span>
            <ChevronRight className="w-3 h-3" />
          </Button>
        </div>
      </td>
    ),
  };
  const eventColumns = ui.shown('event_columns');
  const eventCells: Record<string, (r: RecordedUsageEvent) => ReactNode> = {
    meter: (r) => (
      <td className="px-5 py-3">
        <div className="font-medium text-slate-900">{r.meter_name}</div>
        <div className="text-xs text-slate-400 font-mono">{r.meter_code}</div>
      </td>
    ),
    customer: (r) => (
      <td className="px-5 py-3">
        <div className="text-slate-700">{r.customer_label}</div>
        {r.subscription_label && <div className="text-xs text-slate-400">{r.subscription_label}</div>}
      </td>
    ),
    quantity: (r) => (
      <td className="px-5 py-3 text-right tabular-nums font-medium text-slate-900 whitespace-nowrap">
        {formatQuantity(r.event.quantity)} {r.unit_name}
      </td>
    ),
    timestamp: (r) => (
      <td className="px-5 py-3 whitespace-nowrap">{formatDateTime(normaliseApiTimestamp(r.event.timestamp))}</td>
    ),
    key: (r) => (
      <td className="px-5 py-3 font-mono text-xs text-slate-500 max-w-[9rem] truncate" title={r.event.idempotency_key}>
        {r.event.idempotency_key}
      </td>
    ),
    status: (r) => (
      <td className="px-5 py-3">
        <div className="flex items-center gap-1.5">
          <Badge variant={r.replayed ? 'warning' : r.event.status === 'accepted' ? 'success' : 'danger'}>
            {r.replayed ? 'Duplicate' : humanize(r.event.status)}
          </Badge>
          {r.source === 'batch' && (
            <Badge variant="neutral" size="sm">
              batch
            </Badge>
          )}
        </div>
      </td>
    ),
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="min-w-0" {...ui.edit('header')}>
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-1">
            <Repeat className="w-4 h-4" />
            {ui.text('header', 'eyebrow')}
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{ui.text('header', 'title')}</h1>
          <p className="text-sm text-slate-500 mt-1 max-w-xl">
            {ui.text('header', 'subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0 flex-nowrap overflow-x-auto pb-1 sm:pb-0">
          <Button variant="outline" size="sm" onClick={() => loadMeters()} leadingIcon={<RefreshCw className="w-4 h-4" />}>
            Refresh
          </Button>
          {canFinalize && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setFinalizeOpen(true)}
              disabled={meters.length === 0}
              leadingIcon={<Lock className="w-4 h-4" />}
            >
              Finalize cycle
            </Button>
          )}
          {canRecord && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setBatchOpen(true)}
                disabled={meters.length === 0}
                leadingIcon={<Upload className="w-4 h-4" />}
              >
                Batch import
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => openRecord()}
                disabled={activeCount === 0}
                leadingIcon={<PlusCircle className="w-4 h-4" />}
              >
                Record usage
              </Button>
            </>
          )}
          {canManageMeters && (
            <Button variant="primary" size="sm" onClick={() => setNewMeterOpen(true)} leadingIcon={<Plus className="w-4 h-4" />}>
              New Meter
            </Button>
          )}
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" {...ui.edit('kpis')}>
        {ui.render('kpis', {
          meters: (item, edit) => (
            <UsageKpi edit={edit} title={item.label} value={loading ? '—' : meters.length} icon={<Gauge className="w-4 h-4" />} />
          ),
          active: (item, edit) => (
            <UsageKpi
              edit={edit}
              title={item.label}
              value={loading ? '—' : activeCount}
              comparisonText={!loading && meters.length ? `${meters.length - activeCount} inactive` : undefined}
              icon={<Zap className="w-4 h-4" />}
            />
          ),
          events: (item, edit) => (
            <UsageKpi
              edit={edit}
              title={item.label}
              value={sessionEventCount}
              comparisonText={sessionEventCount ? 'this session' : 'none yet this session'}
              icon={<Activity className="w-4 h-4" />}
            />
          ),
          aggregations: (item, edit) => (
            <UsageKpi
              edit={edit}
              title={item.label}
              value={loading ? '—' : aggregationTypesInUse.length}
              comparisonText={
                aggregationTypesInUse.length ? aggregationTypesInUse.map((t) => AGGREGATION_LABELS[t].label).join(' · ') : undefined
              }
              icon={<Sigma className="w-4 h-4" />}
            />
          ),
        })}
      </div>

      {/* Filters */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex flex-col md:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search meters by name, code, unit or description..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-colors"
            />
          </div>
          <div className="flex items-center gap-2 w-full md:w-auto">
            <select
              value={aggregationFilter}
              onChange={(e) => setAggregationFilter(e.target.value as 'all' | AggregationType)}
              className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Aggregations</option>
              {AGGREGATION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {AGGREGATION_LABELS[t].label}
                </option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
        </div>
      </div>

      {/* Meters table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-16">
            <LoadingState message="Loading usage meters..." />
          </div>
        ) : error ? (
          <ErrorState title="Could not load meters" message={error} onRetry={loadMeters} className="rounded-none border-0" />
        ) : meters.length === 0 ? (
          <div {...ui.edit('empty')}>
            <EmptyState
              className="border-0 rounded-none"
              icon={<Gauge className="w-8 h-8 text-slate-400" />}
              title={ui.text('empty', 'no_meters_title')}
              description={canManageMeters ? ui.text('empty', 'no_meters_admin') : ui.text('empty', 'no_meters_member')}
              action={
                canManageMeters ? (
                  <Button variant="primary" size="sm" onClick={() => setNewMeterOpen(true)} leadingIcon={<Plus className="w-4 h-4" />}>
                    Create first meter
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : filteredMeters.length === 0 ? (
          <div {...ui.edit('empty')}>
            <EmptyState
              className="border-0 rounded-none"
              icon={<Search className="w-8 h-8 text-slate-400" />}
              title={ui.text('empty', 'no_match_title')}
              description={ui.text('empty', 'no_match')}
              action={
                hasFilters ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSearch('');
                      setAggregationFilter('all');
                      setStatusFilter('all');
                    }}
                  >
                    Clear filters
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                <tr {...ui.edit('columns')}>
                  {columns.map((col) => (
                    <th
                      key={col.key}
                      className={`px-5 py-3.5${METER_RIGHT_ALIGNED.has(col.key) ? ' text-right' : ''}`}
                      {...ui.edit(`columns.${col.key}`)}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredMeters.map((m) => {
                  const usage = eventsPerMeter.get(m.id);
                  return (
                    <tr
                      key={m.id}
                      className="hover:bg-slate-50/70 transition-colors cursor-pointer group"
                      onClick={() => setDetailMeter(m)}
                    >
                      {columns.map((col) => <Fragment key={col.key}>{meterCells[col.key]?.(m, usage)}</Fragment>)}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Session activity */}
      {!loading && !error && meters.length > 0 && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200">
              <div {...ui.edit('events')}>
                <h2 className="text-sm font-semibold text-slate-900">{ui.text('events', 'title')}</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {ui.text('events', 'description')}
                </p>
              </div>
              {sessionEvents.length > 0 && (
                <Button variant="ghost" size="sm" className="text-xs" onClick={() => setSessionEvents([])}>
                  Clear
                </Button>
              )}
            </div>
            {sessionEvents.length === 0 ? (
              <div {...ui.edit('events')}>
                <EmptyState
                  className="border-0 rounded-none py-10"
                  icon={<Activity className="w-6 h-6 text-slate-400" />}
                  title={ui.text('events', 'empty_title')}
                  description={ui.text('events', 'empty')}
                  action={
                    canRecord && activeCount > 0 ? (
                      <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" onClick={() => setBatchOpen(true)} leadingIcon={<Upload className="w-3.5 h-3.5" />}>
                          Batch import
                        </Button>
                        <Button variant="primary" size="sm" onClick={() => openRecord()} leadingIcon={<PlusCircle className="w-3.5 h-3.5" />}>
                          Record usage
                        </Button>
                      </div>
                    ) : undefined
                  }
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-slate-600">
                  <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                    <tr {...ui.edit('event_columns')}>
                      {eventColumns.map((col) => (
                        <th
                          key={col.key}
                          className={`px-5 py-3${col.key === 'quantity' ? ' text-right' : ''}`}
                          {...ui.edit(`event_columns.${col.key}`)}
                        >
                          {col.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {sessionEvents.map((r) => (
                      <tr key={r.event.id} className="hover:bg-slate-50/70">
                        {eventColumns.map((col) => <Fragment key={col.key}>{eventCells[col.key]?.(r)}</Fragment>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200">
              <div {...ui.edit('cycles')}>
                <h2 className="text-sm font-semibold text-slate-900">{ui.text('cycles', 'title')}</h2>
                <p className="text-xs text-slate-500 mt-0.5">{ui.text('cycles', 'description')}</p>
              </div>
              {canFinalize && sessionAggregates.length > 0 && (
                <Button variant="ghost" size="sm" className="text-xs" onClick={() => setFinalizeOpen(true)}>
                  Finalize
                </Button>
              )}
            </div>
            {sessionAggregates.length === 0 ? (
              <div {...ui.edit('cycles')}>
                <EmptyState
                  className="border-0 rounded-none py-10"
                  icon={<Layers className="w-6 h-6 text-slate-400" />}
                  title={ui.text('cycles', 'empty_title')}
                  description={canFinalize ? ui.text('cycles', 'empty_finance') : ui.text('cycles', 'empty_member')}
                  action={
                    canFinalize ? (
                      <Button variant="outline" size="sm" onClick={() => setFinalizeOpen(true)} leadingIcon={<Lock className="w-3.5 h-3.5" />}>
                        Finalize cycle
                      </Button>
                    ) : undefined
                  }
                />
              </div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {sessionAggregates.map(({ aggregate, subscription_label, currency }) => {
                  const meter = meterById.get(aggregate.meter_id);
                  return (
                    <li key={aggregate.id} className="px-5 py-4 space-y-1.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-slate-900 truncate" title={subscription_label}>
                          {subscription_label}
                        </span>
                        <Badge variant={aggregate.status === 'finalized' ? 'success' : 'warning'}>{humanize(aggregate.status)}</Badge>
                      </div>
                      <div className="text-xs text-slate-500">
                        {formatDate(aggregate.period_start)} – {formatDate(aggregate.period_end)}
                        {meter ? ` · ${meter.name}` : ''}
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-700 tabular-nums">
                          {formatQuantity(aggregate.total_quantity)} {meter?.unit_name ?? ''}
                        </span>
                        <span className="font-semibold text-slate-900 tabular-nums">{formatMoney(aggregate.rated_amount, currency)}</span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Dialogs */}
      <NewMeterModal
        isOpen={newMeterOpen}
        onClose={() => setNewMeterOpen(false)}
        onCreated={(meter) => {
          setMeters((prev) => [...prev, meter].sort((a, b) => a.name.localeCompare(b.name)));
        }}
      />
      <RecordUsageModal
        isOpen={recordOpen}
        onClose={() => setRecordOpen(false)}
        meters={meters}
        initialMeterCode={recordMeterCode}
        knownKeys={knownKeys}
        onRecorded={handleRecorded}
      />
      <BatchImportModal
        isOpen={batchOpen}
        onClose={() => setBatchOpen(false)}
        meters={meters}
        knownKeys={knownKeys}
        onRecorded={handleRecorded}
      />
      <FinalizeUsageModal
        isOpen={finalizeOpen}
        onClose={() => setFinalizeOpen(false)}
        meters={meters}
        onFinalized={handleFinalized}
      />
      <MeterDetailModal
        meter={detailMeter}
        isOpen={detailMeter !== null}
        onClose={() => setDetailMeter(null)}
        sessionEvents={detailMeter ? sessionEvents.filter((r) => r.event.meter_id === detailMeter.id) : []}
        sessionAggregates={detailMeter ? sessionAggregates.filter((a) => a.aggregate.meter_id === detailMeter.id).map((a) => a.aggregate) : []}
        canRecord={canRecord}
        onRecordUsage={(m) => openRecord(m.code)}
      />
    </div>
  );
}

/** A StatCard the visual-editor preview can select (StatCard itself takes no extra props). */
function UsageKpi({ edit, ...card }: { edit: EditableProps } & StatCardProps) {
  return (
    <div className="flex" {...edit}>
      <StatCard className="flex-1" {...card} />
    </div>
  );
}
