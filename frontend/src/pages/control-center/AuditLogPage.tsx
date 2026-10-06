import { Fragment, useEffect, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { useToast } from '../../components/common/Toast';
import { controlCenterService, downloadAuthenticated, toApiError } from '../../services';
import { queryKeys } from '../../hooks/queries';
import { formatDateTime } from '../../utils/format';
import type { AuditExportFormat, AuditLogOut, AuditLogParams, AuditStatus } from '../../types/api';
import { usePageSpec } from '../../appUi/usePageSpec';
import {
  History,
  Search,
  Download,
  Eye,
  Lock,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

const PAGE_SIZE = 20;

/**
 * Real `entity_type` strings used across the backend services when they call
 * `audit.record(...)` — see backend/app/services/{invoice,quote,payment,
 * customer,catalog,subscription,approval_service,organization_service,
 * auth_service,import_service}.py.
 */
const ENTITY_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'invoice', label: 'Invoices' },
  { value: 'quote', label: 'Quotes' },
  { value: 'subscription', label: 'Subscriptions' },
  { value: 'payment', label: 'Payments' },
  { value: 'customer', label: 'Customers' },
  { value: 'product', label: 'Products' },
  { value: 'plan', label: 'Plans' },
  { value: 'approval', label: 'Approvals' },
  { value: 'membership', label: 'Team Membership' },
  { value: 'organization', label: 'Organization' },
  { value: 'user', label: 'User Accounts' },
  { value: 'import', label: 'Data Imports' },
];

function useDebouncedValue<T>(value: T, delayMs = 400): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function getStatusBadge(status: AuditStatus) {
  switch (status) {
    case 'success':
      return <Badge variant="success" size="sm">Success</Badge>;
    case 'warning':
      return <Badge variant="warning" size="sm">Alert / Warning</Badge>;
    case 'denied':
      return <Badge variant="danger" size="sm">Access Denied</Badge>;
    default:
      return <Badge variant="neutral" size="sm">{status}</Badge>;
  }
}

export function AuditLogPage() {
  const { showToast } = useToast();
  const ui = usePageSpec('audit_log');

  const [page, setPage] = useState(1);
  const [entityType, setEntityType] = useState<string>('all');
  const [actionQuery, setActionQuery] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [selectedEntry, setSelectedEntry] = useState<AuditLogOut | null>(null);
  const [exportingFormat, setExportingFormat] = useState<AuditExportFormat | null>(null);

  const debouncedSearch = useDebouncedValue(searchQuery);
  const debouncedAction = useDebouncedValue(actionQuery);

  // Jump back to page 1 whenever a filter changes so results aren't stranded
  // on a now out-of-range page.
  useEffect(() => {
    setPage(1);
  }, [entityType, debouncedSearch, debouncedAction, dateFrom, dateTo]);

  const filters: AuditLogParams = {
    search: debouncedSearch.trim() || undefined,
    action: debouncedAction.trim() || undefined,
    entity_type: entityType === 'all' ? undefined : entityType,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };

  const params: AuditLogParams = { ...filters, page, page_size: PAGE_SIZE };

  const auditQuery = useQuery({
    queryKey: queryKeys.controlCenter.auditLogs(params),
    queryFn: () => controlCenterService.auditLogs(params),
  });

  const logs = auditQuery.data?.items ?? [];
  const total = auditQuery.data?.total ?? 0;
  const totalPages = auditQuery.data?.total_pages ?? 1;

  const runExport = async (format: AuditExportFormat) => {
    setExportingFormat(format);
    try {
      const filename = `rooman_billing_audit_${Date.now()}.${format}`;
      await downloadAuthenticated(controlCenterService.auditExportUrl(format, filters), filename);
      showToast(
        'success',
        'Export complete',
        `Exported the audit trail to ${format.toUpperCase()}.`
      );
    } catch (err) {
      showToast('error', 'Export failed', toApiError(err).message);
    } finally {
      setExportingFormat(null);
    }
  };

  // Subsystem filter values come from ENTITY_TYPE_OPTIONS (code); only the tab labels and their
  // order are configurable.
  const subsystemValues = new Set(['all', ...ENTITY_TYPE_OPTIONS.map((o) => o.value)]);
  const subsystemTabs = ui.shown('subsystems').filter((item) => subsystemValues.has(item.key));

  const columns = ui.shown('columns');
  const logCells: Record<string, (entry: AuditLogOut) => ReactNode> = {
    timestamp: (entry) => (
      <td className="px-4 py-3 font-mono text-[11px] text-slate-500 whitespace-nowrap">
        {formatDateTime(entry.created_at)}
      </td>
    ),
    actor: (entry) => (
      <td className="px-4 py-3">
        <div className="font-bold text-slate-900">{entry.actor_label}</div>
        {entry.actor?.email && (
          <div className="text-[10px] text-slate-400">{entry.actor.email}</div>
        )}
      </td>
    ),
    action: (entry) => (
      <td className="px-4 py-3">
        <span className="font-mono font-bold text-slate-800 text-[11px] bg-slate-100 px-1.5 py-0.5 rounded">
          {entry.action}
        </span>
      </td>
    ),
    entity: (entry) => (
      <td className="px-4 py-3">
        <span className="font-semibold text-slate-900">
          {entry.entity_label || entry.entity_id || '—'}
        </span>
        <span className="text-[10px] text-slate-400 block">{entry.entity_type}</span>
      </td>
    ),
    status: (entry) => <td className="px-4 py-3">{getStatusBadge(entry.status)}</td>,
    ip_address: (entry) => (
      <td className="px-4 py-3 font-mono text-[11px] text-slate-500">
        {entry.ip_address || '—'}
      </td>
    ),
    details: (entry) => (
      <td className="px-4 py-3 text-right">
        <Button
          variant="outline"
          size="sm"
          leadingIcon={<Eye className="w-3.5 h-3.5" />}
          onClick={() => setSelectedEntry(entry)}
        >
          Diff
        </Button>
      </td>
    ),
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div {...ui.edit('header')}>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              {ui.text('header', 'eyebrow')}
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              {ui.text('header', 'badge')}
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <History className="w-6 h-6 text-brand-600" />
            {ui.text('header', 'title')}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            {ui.text('header', 'subtitle')}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<Download className="w-3.5 h-3.5" />}
            isLoading={exportingFormat === 'csv'}
            disabled={exportingFormat !== null}
            onClick={() => void runExport('csv')}
          >
            Export CSV
          </Button>
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<Download className="w-3.5 h-3.5" />}
            isLoading={exportingFormat === 'json'}
            disabled={exportingFormat !== null}
            onClick={() => void runExport('json')}
          >
            Export JSON
          </Button>
        </div>
      </div>

      {/* Security & Immutability Notice */}
      <div className="p-3.5 rounded-xl bg-slate-900 text-white flex items-center justify-between gap-4 shadow-sm" {...ui.edit('notice')}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-white/10 text-emerald-400">
            <Lock className="w-4 h-4" />
          </div>
          <div>
            <p className="text-xs font-bold text-slate-100">
              {ui.text('notice', 'title')}
            </p>
            <p className="text-[11px] text-slate-400">
              {ui.text('notice', 'description')}
            </p>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            {/* Entity Type Filter */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 text-xs" {...ui.edit('subsystems')}>
              {subsystemTabs.map((item) => ({ value: item.key, label: item.label })).map((tab) => (
                <button
                  key={tab.value}
                  type="button"
                  {...ui.edit(`subsystems.${tab.value}`)}
                  onClick={() => setEntityType(tab.value)}
                  className={`px-3 py-1.5 rounded-lg font-medium whitespace-nowrap transition-colors cursor-pointer ${
                    entityType === tab.value
                      ? 'bg-brand-600 text-white shadow-xs'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Live Search */}
            <div className="relative w-full sm:w-64 shrink-0" {...ui.edit('filters')}>
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder={ui.text('filters', 'search_placeholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 outline-none focus:bg-white transition-colors"
              />
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 pt-3 border-t border-slate-100">
            <div className="w-full sm:w-56">
              <input
                type="text"
                placeholder={ui.text('filters', 'action_placeholder')}
                value={actionQuery}
                onChange={(e) => setActionQuery(e.target.value)}
                className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 outline-none focus:bg-white transition-colors font-mono"
              />
            </div>
            <div className="flex items-center gap-2 text-xs">
              <label className="text-slate-500 font-medium" htmlFor="audit-date-from">
                From
              </label>
              <input
                id="audit-date-from"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="px-2.5 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-900 outline-none focus:bg-white transition-colors"
              />
              <label className="text-slate-500 font-medium" htmlFor="audit-date-to">
                To
              </label>
              <input
                id="audit-date-to"
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="px-2.5 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-900 outline-none focus:bg-white transition-colors"
              />
              {(dateFrom || dateTo || actionQuery) && (
                <button
                  type="button"
                  onClick={() => {
                    setDateFrom('');
                    setDateTo('');
                    setActionQuery('');
                  }}
                  className="text-brand-600 font-medium hover:underline"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Audit Log Table */}
      {auditQuery.isPending ? (
        <LoadingState message="Loading audit trail..." className="py-16" />
      ) : auditQuery.isError ? (
        <ErrorState message={toApiError(auditQuery.error).message} onRetry={() => void auditQuery.refetch()} />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200/80">
                <tr {...ui.edit('columns')}>
                  {columns.map((col) => (
                    <th
                      key={col.key}
                      className={`px-4 py-3${col.key === 'details' ? ' text-right' : ''}`}
                      {...ui.edit(`columns.${col.key}`)}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {logs.map((entry) => (
                  <tr key={entry.id} className="hover:bg-slate-50/70 transition-colors">
                    {columns.map((col) => <Fragment key={col.key}>{logCells[col.key]?.(entry)}</Fragment>)}
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={columns.length} className="px-4 py-10 text-center text-slate-400" {...ui.edit('empty')}>
                      {ui.text('empty', 'filtered')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {total > 0 && (
            <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500 bg-slate-50/50">
              <div>
                Showing{' '}
                <span className="font-semibold text-slate-700">{(page - 1) * PAGE_SIZE + 1}</span> to{' '}
                <span className="font-semibold text-slate-700">
                  {Math.min(page * PAGE_SIZE, total)}
                </span>{' '}
                of <span className="font-semibold text-slate-700">{total}</span> entries
              </div>
              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  leadingIcon={<ChevronLeft className="w-3.5 h-3.5" />}
                >
                  Previous
                </Button>
                <span className="px-2 font-medium text-slate-600">
                  Page {page} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  trailingIcon={<ChevronRight className="w-3.5 h-3.5" />}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Before / After State Diff Modal */}
      {selectedEntry && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedEntry(null)}
          title={`Audit State Diff: ${selectedEntry.action}`}
          size="lg"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-3 bg-slate-50 rounded-xl border border-slate-200">
              <div>
                <span className="text-slate-400 text-[10px] uppercase font-bold block">Log ID</span>
                <span className="font-mono font-bold text-slate-800">{selectedEntry.id}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] uppercase font-bold block">Actor</span>
                <span className="font-bold text-slate-800">{selectedEntry.actor_label}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] uppercase font-bold block">Entity</span>
                <span className="font-bold text-slate-800">
                  {selectedEntry.entity_label || selectedEntry.entity_id || '—'}
                </span>
                <span className="text-[10px] text-slate-400 block">{selectedEntry.entity_type}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] uppercase font-bold block">IP Origin</span>
                <span className="font-mono text-slate-800">{selectedEntry.ip_address || '—'}</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Before State */}
              <div className="p-3 bg-rose-50/50 border border-rose-200 rounded-xl space-y-1.5">
                <span className="text-[11px] font-bold text-rose-700 uppercase tracking-wider block">
                  Prior State (Before Mutation)
                </span>
                <pre className="p-2.5 bg-white rounded-lg border border-rose-100 text-[11px] font-mono text-slate-800 overflow-x-auto">
                  {selectedEntry.before_state
                    ? JSON.stringify(selectedEntry.before_state, null, 2)
                    : 'N/A — no prior state recorded for this event.'}
                </pre>
              </div>

              {/* After State */}
              <div className="p-3 bg-emerald-50/50 border border-emerald-200 rounded-xl space-y-1.5">
                <span className="text-[11px] font-bold text-emerald-700 uppercase tracking-wider block">
                  New State (Committed State)
                </span>
                <pre className="p-2.5 bg-white rounded-lg border border-emerald-100 text-[11px] font-mono text-slate-800 overflow-x-auto">
                  {selectedEntry.after_state
                    ? JSON.stringify(selectedEntry.after_state, null, 2)
                    : 'N/A — no new state recorded for this event.'}
                </pre>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button variant="primary" size="sm" onClick={() => setSelectedEntry(null)}>
                Close Inspector
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
