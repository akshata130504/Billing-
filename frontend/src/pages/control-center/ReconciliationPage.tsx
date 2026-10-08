import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { DataTable, type Column } from '../../components/common/DataTable';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { useToast } from '../../components/common/Toast';
import { paymentService } from '../../services/paymentService';
import { invoiceService } from '../../services/invoiceService';
import { toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { useAuth } from '../../hooks/useAuth';
import { formatDate, formatMoney, parseMoney, toMoneyString } from '../../utils/format';
import type { Invoice } from '../../types/invoices';
import type {
  PaymentGateway,
  PaymentMethod,
  PaymentOut,
  ReconciliationStatus,
} from '../../types/api';
import { ArrowLeftRight, Info, RefreshCw } from 'lucide-react';
import { usePageSpec } from '../../appUi/usePageSpec';

const PAGE_SIZE = 20;

const METHOD_LABELS: Record<PaymentMethod, string> = {
  razorpay: 'Razorpay',
  bank_transfer: 'Bank Transfer',
  upi: 'UPI',
  card: 'Card',
  cash: 'Cash',
  cheque: 'Cheque',
  other: 'Other',
};

const GATEWAY_LABELS: Record<PaymentGateway, string> = {
  manual: 'Manual',
  razorpay: 'Razorpay',
};

function getStatusBadge(status: ReconciliationStatus) {
  switch (status) {
    case 'auto_matched':
      return (
        <Badge variant="success" size="sm">
          Auto-Reconciled
        </Badge>
      );
    case 'matched':
      return (
        <Badge variant="primary" size="sm">
          Matched
        </Badge>
      );
    case 'unmatched':
      return (
        <Badge variant="warning" size="sm">
          Unmatched
        </Badge>
      );
    case 'exception':
      return (
        <Badge variant="danger" size="sm">
          Exception
        </Badge>
      );
    default:
      return (
        <Badge variant="neutral" size="sm">
          {status}
        </Badge>
      );
  }
}

/** Debounces a fast-changing value (e.g. a search input) before it drives a query. */
function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function ReconciliationPage() {
  const ui = usePageSpec('reconciliation');
  const { hasRole } = useAuth();
  const canAllocate = hasRole('finance');

  const [statusFilter, setStatusFilter] = useState<'all' | ReconciliationStatus>('all');
  const [page, setPage] = useState(1);
  const [selectedPayment, setSelectedPayment] = useState<PaymentOut | null>(null);

  const summaryQuery = useQuery({
    queryKey: queryKeys.payments.reconciliationSummary(),
    queryFn: paymentService.reconciliationSummary,
  });

  const listParams = useMemo(
    () => ({
      reconciliation_status: statusFilter === 'all' ? undefined : statusFilter,
      page,
      page_size: PAGE_SIZE,
    }),
    [statusFilter, page]
  );

  const paymentsQuery = useQuery({
    queryKey: queryKeys.payments.list(listParams),
    queryFn: () => paymentService.list(listParams),
  });

  const summary = summaryQuery.data;

  const selectFilter = (key: 'all' | ReconciliationStatus) => {
    setStatusFilter(key);
    setPage(1);
  };

  const handleRefresh = () => {
    void summaryQuery.refetch();
    void paymentsQuery.refetch();
  };

  const allColumnsMap: Record<string, Column<PaymentOut>> = {
    payment_number: {
      key: 'payment_number',
      title: 'Payment Ref',
      render: (item) => (
        <div>
          <div className="font-mono font-bold text-slate-700 text-xs">{item.payment_number}</div>
          <div className="text-[10px] text-slate-400">
            {item.paid_at ? formatDate(item.paid_at) : 'Not yet paid'}
          </div>
        </div>
      ),
    },
    customer: {
      key: 'customer',
      title: 'Customer',
      render: (item) => (
        <span className="font-semibold text-slate-900 text-xs">
          {item.customer?.display_name ?? 'Unlinked deposit'}
        </span>
      ),
    },
    date: {
      key: 'date',
      title: 'Date',
      render: (item) => (
        <span className="text-xs text-slate-600">
          {item.paid_at ? formatDate(item.paid_at) : '—'}
        </span>
      ),
    },
    amount: {
      key: 'amount',
      title: 'Amount',
      align: 'right',
      render: (item) => (
        <div className="text-right">
          <div className="font-bold text-slate-900 tabular-nums text-xs">
            {formatMoney(item.amount, item.currency)}
          </div>
        </div>
      ),
    },
    unallocated: {
      key: 'unallocated',
      title: 'Unallocated',
      align: 'right',
      render: (item) => (
        <div className="text-right text-xs">
          {parseMoney(item.amount_unallocated) > 0 ? (
            <span className="text-amber-600 font-medium">
              {formatMoney(item.amount_unallocated, item.currency)}
            </span>
          ) : (
            <span className="text-slate-400">—</span>
          )}
        </div>
      ),
    },
    status: {
      key: 'status',
      title: 'Recon Status',
      render: (item) => getStatusBadge(item.reconciliation_status),
    },
    actions: {
      key: 'actions',
      title: 'Actions',
      align: 'right',
      render: (item) => (
        <Button variant="outline" size="sm" onClick={() => setSelectedPayment(item)}>
          Inspect
        </Button>
      ),
    },
  };

  const columns: Column<PaymentOut>[] = ui.shown('columns').map((col) => {
    const baseCol = allColumnsMap[col.key];
    if (baseCol) {
      return { ...baseCol, title: col.label };
    }
    return {
      key: col.key,
      title: col.label,
      render: () => null,
    };
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1" {...ui.edit('header')}>
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              {ui.text('header', 'eyebrow')}
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              {ui.text('header', 'badge')}
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2" {...ui.edit('header')}>
            <ArrowLeftRight className="w-6 h-6 text-brand-600" />
            {ui.text('header', 'title')}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl" {...ui.edit('header')}>
            {ui.text('header', 'subtitle')}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button
            variant="outline"
            size="sm"
            isLoading={summaryQuery.isFetching || paymentsQuery.isFetching}
            leadingIcon={<RefreshCw className="w-3.5 h-3.5" />}
            onClick={handleRefresh}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Explanation Banner */}
      <Card className="bg-gradient-to-r from-blue-50/70 via-slate-50 to-indigo-50/70 border-blue-200/70">
        <CardContent className="p-4 sm:p-5">
          <div className="flex items-start gap-3">
            <span className="p-2 rounded-lg bg-white border border-blue-200 text-brand-600 shadow-2xs shrink-0">
              <Info className="w-4 h-4" />
            </span>
            <div className="text-xs text-slate-600 leading-relaxed">
              <p className="font-bold text-slate-900 mb-0.5">How reconciliation works here</p>
              <p>
                Reconciliation matches recorded payments to invoices via allocations — Rooman Billing
                does not currently ingest external bank or gateway settlement feeds. A payment becomes{' '}
                <span className="font-semibold text-emerald-700">Auto-Reconciled</span> or{' '}
                <span className="font-semibold text-brand-700">Matched</span> automatically once it is
                fully allocated to invoices; payments that are{' '}
                <span className="font-semibold text-amber-700">Unmatched</span> or an{' '}
                <span className="font-semibold text-rose-700">Exception</span> below need manual
                allocation.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* KPI Tiles */}
      {summaryQuery.isPending ? (
        <LoadingState message="Loading reconciliation summary..." className="py-8" />
      ) : summaryQuery.isError ? (
        <ErrorState
          message={toApiError(summaryQuery.error).message}
          onRetry={() => void summaryQuery.refetch()}
        />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 sm:gap-4" {...ui.edit('kpis')}>
          {ui.render('kpis', {
            auto_matched: (item, edit) => (
              <div
                key="auto_matched"
                onClick={() => selectFilter('auto_matched')}
                className="p-3.5 bg-white rounded-xl border border-slate-200/90 shadow-2xs cursor-pointer hover:border-emerald-300"
                {...edit}
              >
                <span className="text-xs text-slate-500 font-medium">{item.label}</span>
                <p className="text-xl font-bold text-emerald-600 mt-1">{summary?.auto_matched ?? 0}</p>
                {item.caption && <span className="text-[10px] text-slate-400">{item.caption}</span>}
              </div>
            ),
            matched: (item, edit) => (
              <div
                key="matched"
                onClick={() => selectFilter('matched')}
                className="p-3.5 bg-white rounded-xl border border-slate-200/90 shadow-2xs cursor-pointer hover:border-blue-300"
                {...edit}
              >
                <span className="text-xs text-slate-500 font-medium">{item.label}</span>
                <p className="text-xl font-bold text-brand-600 mt-1">{summary?.matched ?? 0}</p>
                {item.caption && <span className="text-[10px] text-slate-400">{item.caption}</span>}
              </div>
            ),
            unmatched: (item, edit) => (
              <div
                key="unmatched"
                onClick={() => selectFilter('unmatched')}
                className="p-3.5 bg-white rounded-xl border border-slate-200/90 shadow-2xs cursor-pointer hover:border-amber-300"
                {...edit}
              >
                <span className="text-xs text-slate-500 font-medium">{item.label}</span>
                <p className="text-xl font-bold text-amber-600 mt-1">{summary?.unmatched ?? 0}</p>
                {item.caption && <span className="text-[10px] text-slate-400">{item.caption}</span>}
              </div>
            ),
            exception: (item, edit) => (
              <div
                key="exception"
                onClick={() => selectFilter('exception')}
                className="p-3.5 bg-white rounded-xl border border-slate-200/90 shadow-2xs cursor-pointer hover:border-rose-300"
                {...edit}
              >
                <span className="text-xs text-slate-500 font-medium">{item.label}</span>
                <p className="text-xl font-bold text-rose-600 mt-1">{summary?.exception ?? 0}</p>
                {item.caption && <span className="text-[10px] text-slate-400">{item.caption}</span>}
              </div>
            ),
            total: (item, edit) => (
              <div key="total" className="p-3.5 bg-white rounded-xl border border-slate-200/90 shadow-2xs" {...edit}>
                <span className="text-xs text-slate-500 font-medium">{item.label}</span>
                <p className="text-xl font-bold text-slate-700 mt-1">
                  {summary?.total ?? 0}
                </p>
                {item.caption && <span className="text-[10px] text-slate-400">{item.caption}</span>}
              </div>
            ),
          })}
        </div>
      )}

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-slate-200/90">
        {[
          { key: 'all' as const, label: `All Transactions (${summary?.total ?? 0})` },
          { key: 'auto_matched' as const, label: `Auto-Reconciled (${summary?.auto_matched ?? 0})` },
          { key: 'matched' as const, label: `Matched (${summary?.matched ?? 0})` },
          { key: 'unmatched' as const, label: `Unmatched (${summary?.unmatched ?? 0})` },
          { key: 'exception' as const, label: `Exceptions (${summary?.exception ?? 0})` },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => selectFilter(tab.key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer ${
              statusFilter === tab.key
                ? 'bg-slate-900 text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Records Table */}
      {paymentsQuery.isPending ? (
        <LoadingState message="Loading payments..." className="py-12" />
      ) : paymentsQuery.isError ? (
        <ErrorState
          message={toApiError(paymentsQuery.error).message}
          onRetry={() => void paymentsQuery.refetch()}
        />
      ) : (
        <DataTable
          columns={columns}
          data={paymentsQuery.data?.items ?? []}
          keyExtractor={(item) => item.id}
          page={paymentsQuery.data?.page ?? page}
          pageSize={PAGE_SIZE}
          total={paymentsQuery.data?.total}
          onPageChange={setPage}
          emptyMessage={ui.text('empty', 'none')}
          emptySubtext="Try a different reconciliation status filter."
        />
      )}

      {/* Inspect / Allocate Modal */}
      {selectedPayment && (
        <PaymentInspectModal
          payment={selectedPayment}
          canAllocate={canAllocate}
          onClose={() => setSelectedPayment(null)}
        />
      )}
    </div>
  );
}

function PaymentInspectModal({
  payment,
  canAllocate,
  onClose,
}: {
  payment: PaymentOut;
  canAllocate: boolean;
  onClose: () => void;
}) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();

  const needsAllocation = payment.reconciliation_status === 'unmatched' || payment.reconciliation_status === 'exception';

  const [invoiceSearch, setInvoiceSearch] = useState('');
  const [selectedInvoiceId, setSelectedInvoiceId] = useState('');
  const [amount, setAmount] = useState('');
  const debouncedSearch = useDebouncedValue(invoiceSearch, 300);

  const invoiceSearchParams = {
    search: debouncedSearch || undefined,
    customer_id: payment.customer?.id,
    page_size: 20,
  };

  const invoicesQuery = useQuery({
    queryKey: queryKeys.invoices.list(invoiceSearchParams),
    queryFn: () => invoiceService.listInvoices(invoiceSearchParams),
    enabled: needsAllocation && canAllocate,
  });

  const invoiceOptions = (invoicesQuery.data?.items ?? []).map((inv: Invoice) => ({
    value: inv.id,
    label: `${inv.invoice_number} — ${formatMoney(inv.amount_due)} due`,
  }));

  const allocateMutation = useMutation({
    mutationFn: () => paymentService.setAllocations(payment.id, [{ invoice_id: selectedInvoiceId, amount: toMoneyString(amount) }]),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.payments.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.invoices.all });
      showToast('success', 'Payment allocated', 'The payment was linked to the invoice.');
      onClose();
    },
    onError: (err) => showToast('error', 'Could not allocate payment', toApiError(err).message),
  });

  const handleInvoiceSelect = (invoiceId: string) => {
    setSelectedInvoiceId(invoiceId);
    const inv = invoicesQuery.data?.items.find((i) => i.id === invoiceId);
    if (inv) {
      const suggested = Math.min(parseMoney(payment.amount_unallocated), parseMoney(inv.amount_due));
      if (Number.isFinite(suggested) && suggested > 0) setAmount(suggested.toFixed(2));
    }
  };

  const canSubmit = selectedInvoiceId !== '' && parseMoney(amount) > 0;

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={`Payment: ${payment.payment_number}`}
      size="lg"
    >
      <div className="space-y-4 text-xs">
        <div className="grid grid-cols-2 gap-3 p-3.5 bg-slate-50 rounded-xl border border-slate-200">
          <div>
            <span className="text-slate-500 block font-medium">Method / Gateway</span>
            <span className="font-bold text-slate-900">
              {METHOD_LABELS[payment.method] ?? payment.method} ({GATEWAY_LABELS[payment.gateway] ?? payment.gateway})
            </span>
          </div>
          <div>
            <span className="text-slate-500 block font-medium">Reference</span>
            <span className="font-mono text-slate-800">{payment.reference || payment.gateway_payment_id || '—'}</span>
          </div>
          <div>
            <span className="text-slate-500 block font-medium">Customer</span>
            <span className="font-bold text-slate-900">{payment.customer?.display_name ?? 'Unlinked deposit'}</span>
          </div>
          <div>
            <span className="text-slate-500 block font-medium">Allocated Invoice(s)</span>
            <span className="font-bold text-slate-900">
              {payment.allocations.length === 0
                ? 'Unallocated'
                : payment.allocations.map((a) => a.invoice_number).join(', ')}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block font-medium">Payment Amount</span>
            <span className="font-bold text-slate-900 text-sm tabular-nums">
              {formatMoney(payment.amount, payment.currency)}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block font-medium">Reconciliation State</span>
            <div>{getStatusBadge(payment.reconciliation_status)}</div>
          </div>
          <div>
            <span className="text-slate-500 block font-medium">Allocated</span>
            <span className="font-bold text-slate-900 tabular-nums">
              {formatMoney(payment.amount_allocated, payment.currency)}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block font-medium">Unallocated</span>
            <span className="font-bold text-amber-700 tabular-nums">
              {formatMoney(payment.amount_unallocated, payment.currency)}
            </span>
          </div>
        </div>

        {parseMoney(payment.amount_refunded) > 0 && (
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-slate-700">
            <span className="font-bold block mb-0.5">Refunds:</span>
            {formatMoney(payment.amount_refunded, payment.currency)} refunded across{' '}
            {payment.refunds.length} refund{payment.refunds.length === 1 ? '' : 's'}. This reduces the
            amount available to allocate, which can produce an Exception status if allocations now
            exceed what remains available.
          </div>
        )}

        {needsAllocation && (
          <div className="p-3.5 bg-white border border-slate-200 rounded-xl space-y-3">
            <p className="font-bold text-slate-900">Manually allocate to an invoice</p>
            {!canAllocate ? (
              <p className="text-slate-500">
                Manual allocation requires the Finance role. Ask a finance user or admin to complete
                this match.
              </p>
            ) : (
              <>
                <Input
                  label="Search invoices"
                  placeholder="Invoice number..."
                  value={invoiceSearch}
                  onChange={(e) => setInvoiceSearch(e.target.value)}
                />
                <Select
                  label="Invoice"
                  placeholder={invoicesQuery.isFetching ? 'Searching…' : 'Select an invoice'}
                  value={selectedInvoiceId}
                  onChange={(e) => handleInvoiceSelect(e.target.value)}
                  options={invoiceOptions}
                  disabled={invoicesQuery.isFetching}
                />
                {!invoicesQuery.isFetching && invoiceOptions.length === 0 && (
                  <p className="text-slate-400">No matching invoices found.</p>
                )}
                <Input
                  label="Amount to allocate"
                  type="number"
                  min="0"
                  step="0.01"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  helperText={`Up to ${formatMoney(payment.amount_unallocated, payment.currency)} unallocated on this payment.`}
                />
              </>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
          {needsAllocation && canAllocate && (
            <Button
              variant="primary"
              size="sm"
              disabled={!canSubmit}
              isLoading={allocateMutation.isPending}
              onClick={() => allocateMutation.mutate()}
            >
              Save Allocation
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
