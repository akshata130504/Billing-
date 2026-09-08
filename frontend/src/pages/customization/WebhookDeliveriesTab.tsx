import { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock, Eye, RefreshCw, Search, Webhook } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Modal } from '../../components/common/Modal';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { EmptyState } from '../../components/common/EmptyState';
import { useToast } from '../../components/common/Toast';
import { customizationService } from '../../services/customizationService';
import { toApiError } from '../../services/apiClient';
import { formatDateTime, formatRelative, humanize, type BadgeVariant } from '../../utils/format';
import { cn } from '../../utils/cn';
import type { WebhookDelivery, WebhookDeliveryStatus } from '../../types/customization';
import { TabHeader, type Resource } from './shared';

interface WebhookDeliveriesTabProps {
  resource: Resource<WebhookDelivery>;
  /** finance / admin / owner may retry failed deliveries. */
  canRetry: boolean;
}

type StatusFilter = 'all' | WebhookDeliveryStatus;

const STATUS_META: Record<string, { label: string; variant: BadgeVariant }> = {
  pending: { label: 'Pending', variant: 'warning' },
  delivered: { label: 'Delivered', variant: 'success' },
  failed: { label: 'Failed', variant: 'danger' },
};

function statusMeta(status: string): { label: string; variant: BadgeVariant } {
  return STATUS_META[status] ?? { label: humanize(status), variant: 'neutral' };
}

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function WebhookDeliveriesTab({ resource, canRetry }: WebhookDeliveriesTabProps) {
  const { showToast } = useToast();
  const { items, loading, error, reload, replace } = resource;

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [search, setSearch] = useState('');
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [inspecting, setInspecting] = useState<WebhookDelivery | null>(null);

  const counts = useMemo(() => {
    const c = { pending: 0, delivered: 0, failed: 0 };
    items.forEach((d) => {
      if (d.status in c) c[d.status as keyof typeof c] += 1;
    });
    return c;
  }, [items]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((d) => {
      if (statusFilter !== 'all' && d.status !== statusFilter) return false;
      if (!q) return true;
      return (
        d.event_type.toLowerCase().includes(q) ||
        d.destination_url.toLowerCase().includes(q) ||
        (d.error_message ?? '').toLowerCase().includes(q)
      );
    });
  }, [items, statusFilter, search]);

  const handleRetry = async (d: WebhookDelivery) => {
    setRetryingId(d.id);
    try {
      const updated = await customizationService.retryWebhookDelivery(d.id);
      replace(updated, (a, b) => a.id === b.id);
      const meta = statusMeta(updated.status);
      if (updated.status === 'delivered') {
        showToast('success', 'Webhook delivered', `${updated.event_type} reached ${hostOf(updated.destination_url)} (HTTP ${updated.response_status_code ?? '—'}).`);
      } else {
        showToast(
          'warning',
          `Retry ${meta.label.toLowerCase()}`,
          updated.error_message || `Attempt ${updated.attempt_count} did not succeed.`
        );
      }
    } catch (err: any) {
      showToast('error', 'Could not retry delivery', toApiError(err).message);
    } finally {
      setRetryingId(null);
    }
  };

  const FILTERS: { key: StatusFilter; label: string; count: number; icon?: typeof Clock }[] = [
    { key: 'all', label: 'All', count: items.length },
    { key: 'failed', label: 'Failed', count: counts.failed, icon: AlertTriangle },
    { key: 'pending', label: 'Pending', count: counts.pending, icon: Clock },
    { key: 'delivered', label: 'Delivered', count: counts.delivered, icon: CheckCircle2 },
  ];

  return (
    <div className="space-y-5">
      <TabHeader
        title="Webhook deliveries"
        description="Every outbound webhook fired by an automation rule, with the endpoint response. Failed deliveries can be retried; the payload is re-signed with your webhook secret on each attempt."
        actions={
          <Button variant="outline" size="sm" onClick={() => void reload()} isLoading={loading} leadingIcon={<RefreshCw className="w-3.5 h-3.5" />}>
            Refresh
          </Button>
        }
      />

      {loading && items.length === 0 ? (
        <LoadingState message="Loading webhook deliveries..." />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Webhook className="w-6 h-6 stroke-1" />}
          title="No webhook deliveries yet"
          description="Deliveries appear here once an automation rule with a webhook action fires. Set up rules under Automation to start sending events to your systems."
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
          {/* Filter bar */}
          <div className="px-4 py-3 border-b border-slate-100 flex flex-col lg:flex-row lg:items-center gap-3 justify-between">
            <div className="flex items-center gap-1 overflow-x-auto" role="tablist" aria-label="Filter deliveries by status">
              {FILTERS.map((f) => {
                const active = statusFilter === f.key;
                const Icon = f.icon;
                return (
                  <button
                    key={f.key}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setStatusFilter(f.key)}
                    className={cn(
                      'inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors',
                      active ? 'bg-brand-50 text-brand-700 font-semibold' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    )}
                  >
                    {Icon && <Icon className={cn('w-3.5 h-3.5', active ? 'text-brand-600' : 'text-slate-400')} />}
                    {f.label}
                    <span className={cn('tabular-nums px-1.5 rounded-full text-[11px]', active ? 'bg-white text-brand-700' : 'bg-slate-100 text-slate-500')}>
                      {f.count}
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="relative w-full lg:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="search"
                placeholder="Search event, endpoint or error..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 focus:bg-white transition-colors"
              />
            </div>
          </div>

          {filtered.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-sm font-medium text-slate-700">No deliveries match</p>
              <p className="text-xs text-slate-400 mt-0.5">Try another status or clear the search.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm min-w-[900px]">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    <th className="py-3.5 px-4">Event</th>
                    <th className="py-3.5 px-4">Endpoint</th>
                    <th className="py-3.5 px-4">Status</th>
                    <th className="py-3.5 px-4 text-center">Attempts</th>
                    <th className="py-3.5 px-4">Last error</th>
                    <th className="py-3.5 px-4">Time</th>
                    <th className="py-3.5 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filtered.map((d) => {
                    const meta = statusMeta(d.status);
                    const retrying = retryingId === d.id;
                    const canRetryThis = canRetry && d.status !== 'delivered';
                    return (
                      <tr key={d.id} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-3.5 px-4">
                          <code className="text-xs font-mono bg-slate-100 text-slate-800 px-1.5 py-0.5 rounded">{d.event_type}</code>
                        </td>
                        <td className="py-3.5 px-4 max-w-[220px]">
                          <div className="font-medium text-slate-900 truncate" title={d.destination_url}>
                            {hostOf(d.destination_url)}
                          </div>
                          <div className="text-[11px] text-slate-400 truncate" title={d.destination_url}>
                            {d.destination_url}
                          </div>
                        </td>
                        <td className="py-3.5 px-4">
                          <div className="flex items-center gap-2">
                            <Badge variant={meta.variant} size="sm" dot>
                              {meta.label}
                            </Badge>
                            {d.response_status_code !== null && (
                              <span className="text-[11px] font-mono text-slate-500">HTTP {d.response_status_code}</span>
                            )}
                          </div>
                        </td>
                        <td className="py-3.5 px-4 text-center tabular-nums text-slate-700">{d.attempt_count}</td>
                        <td className="py-3.5 px-4 max-w-xs">
                          {d.error_message ? (
                            <span className="text-xs text-rose-700 line-clamp-2" title={d.error_message}>
                              {d.error_message}
                            </span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                        <td className="py-3.5 px-4 text-xs text-slate-500 whitespace-nowrap">
                          <div title={formatDateTime(d.delivered_at ?? d.created_at)}>
                            {formatRelative(d.delivered_at ?? d.created_at)}
                          </div>
                          {d.delivered_at && <div className="text-[11px] text-slate-400">delivered</div>}
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <div className="inline-flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="!px-2"
                              onClick={() => setInspecting(d)}
                              aria-label="View payload and response"
                            >
                              <Eye className="w-3.5 h-3.5" />
                            </Button>
                            {canRetryThis && (
                              <Button
                                variant="outline"
                                size="sm"
                                isLoading={retrying}
                                onClick={() => void handleRetry(d)}
                                leadingIcon={<RefreshCw className="w-3.5 h-3.5" />}
                              >
                                Retry
                              </Button>
                            )}
                          </div>
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

      <Modal
        isOpen={!!inspecting}
        onClose={() => setInspecting(null)}
        title={inspecting ? `Delivery: ${inspecting.event_type}` : 'Delivery'}
        description={inspecting ? `${inspecting.destination_url} · ${formatDateTime(inspecting.created_at)}` : undefined}
        size="lg"
        footer={
          <>
            {inspecting && canRetry && inspecting.status !== 'delivered' && (
              <Button
                variant="outline"
                size="sm"
                className="mr-auto"
                isLoading={retryingId === inspecting.id}
                onClick={async () => {
                  await handleRetry(inspecting);
                  setInspecting(null);
                }}
                leadingIcon={<RefreshCw className="w-3.5 h-3.5" />}
              >
                Retry now
              </Button>
            )}
            <Button size="sm" onClick={() => setInspecting(null)}>
              Close
            </Button>
          </>
        }
      >
        {inspecting && (
          <div className="space-y-4">
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div>
                <dt className="text-slate-500">Status</dt>
                <dd className="mt-1">
                  <Badge variant={statusMeta(inspecting.status).variant} size="sm" dot>
                    {statusMeta(inspecting.status).label}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Response code</dt>
                <dd className="mt-1 font-mono text-slate-800">{inspecting.response_status_code ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Attempts</dt>
                <dd className="mt-1 font-medium text-slate-800">{inspecting.attempt_count}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Delivered at</dt>
                <dd className="mt-1 text-slate-800">{formatDateTime(inspecting.delivered_at)}</dd>
              </div>
            </dl>
            {inspecting.error_message && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-800">
                <span className="font-semibold">Error: </span>
                {inspecting.error_message}
              </div>
            )}
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Payload</p>
              <pre className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs font-mono text-slate-800 overflow-auto max-h-64 whitespace-pre-wrap break-all">
                {JSON.stringify(inspecting.payload, null, 2)}
              </pre>
            </div>
            {inspecting.response_body && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Response body</p>
                <pre className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs font-mono text-slate-800 overflow-auto max-h-48 whitespace-pre-wrap break-all">
                  {inspecting.response_body}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
