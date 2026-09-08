import { useState, useMemo } from 'react';
import { usePayments, INITIAL_PAYMENT_FILTERS, PAYMENTS_PAGE_SIZE } from './PaymentsContext';
import { Payment } from './types';
import { PaymentSummaryCards } from './components/PaymentSummaryCards';
import { PaymentFilters } from './components/PaymentFilters';
import { PaymentTable } from './components/PaymentTable';
import { RecordPaymentModal } from './components/RecordPaymentModal';
import { RefundModal } from './components/RefundModal';
import { ReceiptModal } from './components/ReceiptModal';
import { useAuth } from '../../hooks/useAuth';
import { ErrorState } from '../../components/common/ErrorState';
import { Plus, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react';

export function PaymentsPage() {
  const {
    payments,
    customers,
    isLoading,
    error,
    filters,
    setFilters,
    page,
    setPage,
    total,
    totalPages,
    refreshPayments,
  } = usePayments();
  const { hasRole } = useAuth();
  const canRecord = hasRole('finance');

  const [isRecordOpen, setIsRecordOpen] = useState(false);
  const [refundTarget, setRefundTarget] = useState<Payment | null>(null);
  const [receiptTarget, setReceiptTarget] = useState<Payment | null>(null);

  // The filter bar selects by customer id so the server can filter on it.
  const customerOptions = useMemo(
    () => customers.map((c) => ({ id: c.id, name: c.name })),
    [customers]
  );

  const rangeStart = total === 0 ? 0 : (page - 1) * PAYMENTS_PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * PAYMENTS_PAGE_SIZE, total);

  return (
    <div className="space-y-4">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-1">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Payments</h1>
            {!error && (
              <span className="text-xs font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                {total}
              </span>
            )}
            <button
              type="button"
              onClick={() => void refreshPayments()}
              disabled={isLoading}
              title="Refresh payments"
              className="p-1 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-brand-600' : ''}`} />
            </button>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Track customer payments, invoice settlements and refunds.
          </p>
        </div>

        {/* Primary Action - Gated by Finance/Admin/Owner RBAC */}
        {canRecord && (
          <button
            type="button"
            onClick={() => setIsRecordOpen(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 shadow-2xs transition-colors self-start sm:self-auto"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Record Payment</span>
          </button>
        )}
      </div>

      {error ? (
        /* No figures are shown when the ledger could not be read. */
        <ErrorState
          title="Payments could not be loaded"
          message={error.message}
          onRetry={() => void refreshPayments()}
        />
      ) : (
        <>
          <PaymentSummaryCards />

          <PaymentFilters
            filters={filters}
            onChange={setFilters}
            onReset={() => setFilters(INITIAL_PAYMENT_FILTERS)}
            customers={customerOptions}
          />

          <PaymentTable
            payments={payments}
            isLoading={isLoading}
            onRefund={(payment) => setRefundTarget(payment)}
            onViewReceipt={(payment) => setReceiptTarget(payment)}
            onRecordNew={() => setIsRecordOpen(true)}
          />

          {totalPages > 1 && (
            <div className="flex items-center justify-between bg-white border border-slate-200/80 rounded-xl px-4 py-2.5 shadow-2xs">
              <span className="text-xs text-slate-500">
                Showing {rangeStart}–{rangeEnd} of {total}
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setPage(Math.max(1, page - 1))}
                  disabled={page <= 1 || isLoading}
                  className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Previous page"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-xs font-semibold text-slate-700 px-2">
                  Page {page} of {totalPages}
                </span>
                <button
                  type="button"
                  onClick={() => setPage(Math.min(totalPages, page + 1))}
                  disabled={page >= totalPages || isLoading}
                  className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Next page"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}

      <RecordPaymentModal isOpen={isRecordOpen} onClose={() => setIsRecordOpen(false)} />

      <RefundModal
        isOpen={!!refundTarget}
        onClose={() => setRefundTarget(null)}
        payment={refundTarget}
      />

      <ReceiptModal
        isOpen={!!receiptTarget}
        onClose={() => setReceiptTarget(null)}
        payment={receiptTarget}
      />
    </div>
  );
}
