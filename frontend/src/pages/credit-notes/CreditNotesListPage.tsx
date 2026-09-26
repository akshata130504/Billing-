import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Plus, ReceiptText, RefreshCw } from 'lucide-react';
import { PageHeader } from '../../components/common/PageHeader';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { EmptyState } from '../../components/common/EmptyState';
import { CustomerCombobox } from '../../components/common/CustomerCombobox';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';
import { StatCard } from '../../components/common/StatCard';
import {
  creditNoteService,
  type CreditNote,
  type CreditNoteStatus,
  type CreditNoteSummary,
} from '../../services/creditNoteService';
import { formatDate, formatMoney } from '../../utils/format';
import { CreateCreditNoteModal } from './CreateCreditNoteModal';
import { CREDIT_NOTE_STATUS_LABELS, creditNoteStatusLabel, creditNoteStatusVariant } from './creditNoteUi';

const PAGE_SIZE = 25;

export function CreditNotesListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { hasRole } = useAuth();
  const canCreate = hasRole('finance');

  const [notes, setNotes] = useState<CreditNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<CreditNoteStatus | ''>('');
  const [customerFilter, setCustomerFilter] = useState('');
  const [page, setPage] = useState(1);

  // `?new=1&customer_id=..&invoice_id=..` opens the create modal (used by the invoice page).
  const createRequested = searchParams.get('new') === '1';
  const [createOpen, setCreateOpen] = useState(false);
  useEffect(() => {
    if (createRequested && canCreate) setCreateOpen(true);
  }, [createRequested, canCreate]);

  const closeCreate = () => {
    setCreateOpen(false);
    if (createRequested) setSearchParams({}, { replace: true });
  };

  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<CreditNoteSummary | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // `total` is the real number of matching credit notes; the summary tiles come
      // from the server (per currency), not from the rows on this page.
      const [res, sum] = await Promise.all([
        creditNoteService.list({
          status: statusFilter || undefined,
          customer_id: customerFilter || undefined,
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
        }),
        creditNoteService.summary({ customer_id: customerFilter || undefined }).catch(() => null),
      ]);
      setNotes(res.items || []);
      setTotal(res.total ?? 0);
      setSummary(sum);
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, customerFilter, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasNextPage = page < totalPages;
  const visible = notes;
  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(total, (page - 1) * PAGE_SIZE + visible.length);
  const filtered = Boolean(statusFilter || customerFilter);
  const summaryCurrencies = summary?.currencies ?? [];
  const tile = (field: 'issued_total' | 'applied_total' | 'remaining_balance' | 'voided_total') =>
    summaryCurrencies.length === 0
      ? formatMoney(0)
      : summaryCurrencies.map((c) => formatMoney(c[field], c.currency)).join(' · ');

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Revenue"
        title="Credit Notes"
        subtitle="Credits issued to customers, their remaining balance, and where they were applied."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void load()}
              title="Refresh"
              leadingIcon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
            >
              Refresh
            </Button>
            {canCreate && (
              <Button
                variant="primary"
                size="sm"
                leadingIcon={<Plus className="w-4 h-4" />}
                onClick={() => setCreateOpen(true)}
              >
                New Credit Note
              </Button>
            )}
          </div>
        }
      />

      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" aria-label="Credit note totals">
          <StatCard
            title="Issued"
            value={tile('issued_total')}
            comparisonText={`${summary.total_count - (summary.count_by_status.void ?? 0) - (summary.count_by_status.draft ?? 0)} credit notes`}
          />
          <StatCard title="Applied" value={tile('applied_total')} comparisonText="Used against invoices" />
          <StatCard
            title="Remaining balance"
            value={tile('remaining_balance')}
            comparisonText={`${(summary.count_by_status.issued ?? 0) + (summary.count_by_status.partially_applied ?? 0)} with credit left`}
          />
          <StatCard
            title="Voided"
            value={tile('voided_total')}
            comparisonText={`${summary.count_by_status.void ?? 0} voided`}
          />
        </div>
      )}

      <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="sm:col-span-2">
          <CustomerCombobox
            value={customerFilter}
            onChange={(id) => {
              setCustomerFilter(id);
              setPage(1);
            }}
            placeholder="Filter by customer..."
            clearable
          />
        </div>
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as CreditNoteStatus | '');
            setPage(1);
          }}
          className="px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">All statuses</option>
          {(Object.keys(CREDIT_NOTE_STATUS_LABELS) as CreditNoteStatus[]).map((s) => (
            <option key={s} value={s}>
              {CREDIT_NOTE_STATUS_LABELS[s]}
            </option>
          ))}
        </select>
      </div>

      <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
        {error ? (
          <ErrorState
            title="Couldn't load credit notes"
            message={error}
            onRetry={() => void load()}
            className="rounded-none border-0"
          />
        ) : loading ? (
          <LoadingState message="Loading credit notes..." />
        ) : visible.length === 0 ? (
          <EmptyState
            icon={<ReceiptText className="w-6 h-6" />}
            title={filtered ? 'No matching credit notes' : 'No credit notes yet'}
            description={
              filtered
                ? 'Try a different customer or status.'
                : 'Credit notes let you refund or correct an invoice without editing it.'
            }
            action={
              canCreate && !filtered ? (
                <Button size="sm" leadingIcon={<Plus className="w-4 h-4" />} onClick={() => setCreateOpen(true)}>
                  New Credit Note
                </Button>
              ) : undefined
            }
            className="border-0 rounded-none"
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-600 border-collapse">
                <thead className="bg-slate-50 border-b border-slate-200/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                  <tr>
                    <th className="px-4 py-3">Credit Note #</th>
                    <th className="px-4 py-3">Customer</th>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Reason</th>
                    <th className="px-4 py-3 text-right">Total</th>
                    <th className="px-4 py-3 text-right">Balance</th>
                    <th className="px-4 py-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {visible.map((note) => (
                    <tr
                      key={note.id}
                      onClick={() => navigate(`/credit-notes/${note.id}`)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') navigate(`/credit-notes/${note.id}`);
                      }}
                      tabIndex={0}
                      className="hover:bg-slate-50/80 transition-colors cursor-pointer focus:outline-none focus:bg-slate-50"
                    >
                      <td className="px-4 py-3 font-mono font-semibold text-slate-900">{note.credit_note_number}</td>
                      <td className="px-4 py-3">
                        <p className="font-semibold text-slate-900">{note.customer?.display_name ?? '—'}</p>
                        {note.customer?.customer_number && (
                          <p className="text-[10px] text-slate-400">{note.customer.customer_number}</p>
                        )}
                      </td>
                      <td className="px-4 py-3">{formatDate(note.created_at)}</td>
                      <td className="px-4 py-3 max-w-xs truncate">{note.reason || '—'}</td>
                      <td className="px-4 py-3 text-right font-semibold text-slate-900">
                        {formatMoney(note.total, note.currency)}
                      </td>
                      <td className="px-4 py-3 text-right">{formatMoney(note.balance_remaining, note.currency)}</td>
                      <td className="px-4 py-3">
                        <Badge size="sm" variant={creditNoteStatusVariant(note.status)}>
                          {creditNoteStatusLabel(note.status)}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between gap-1.5 text-xs text-slate-500 bg-slate-50/50">
              <span data-testid="credit-notes-range">
                Showing {rangeStart}–{rangeEnd} of {total}
              </span>
              {(page > 1 || hasNextPage) && (
              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
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
                  disabled={!hasNextPage}
                  onClick={() => setPage((p) => p + 1)}
                  trailingIcon={<ChevronRight className="w-3.5 h-3.5" />}
                >
                  Next
                </Button>
              </div>
              )}
            </div>
          </>
        )}
      </div>

      {canCreate && (
        <CreateCreditNoteModal
          isOpen={createOpen}
          onClose={closeCreate}
          initialCustomerId={createRequested ? searchParams.get('customer_id') ?? '' : ''}
          initialInvoiceId={createRequested ? searchParams.get('invoice_id') ?? '' : ''}
          onCreated={(note) => {
            closeCreate();
            navigate(`/credit-notes/${note.id}`);
          }}
        />
      )}
    </div>
  );
}

export default CreditNotesListPage;
