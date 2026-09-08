import { useState, useMemo } from 'react';
import { usePayments } from './PaymentsContext';
import { Payment, PaymentFilterState } from './types';
import { PaymentSummaryCards } from './components/PaymentSummaryCards';
import { PaymentFilters } from './components/PaymentFilters';
import { PaymentTable } from './components/PaymentTable';
import { RecordPaymentModal } from './components/RecordPaymentModal';
import { RefundModal } from './components/RefundModal';
import { ReceiptModal } from './components/ReceiptModal';
import { useAuth } from '../../hooks/useAuth';
import { Plus, RefreshCw } from 'lucide-react';

export function PaymentsPage() {
  const { payments, customers, isLoading, refreshPayments } = usePayments();
  const { hasRole } = useAuth();
  const canRecord = hasRole('finance');

  // Filters State
  const [filters, setFilters] = useState<PaymentFilterState>({
    searchQuery: '',
    statusTab: 'all',
    customer: 'all',
    paymentMethod: 'all',
    status: 'all',
    sortBy: 'newest',
  });

  // Modal triggers
  const [isRecordOpen, setIsRecordOpen] = useState(false);
  const [refundTarget, setRefundTarget] = useState<Payment | null>(null);
  const [receiptTarget, setReceiptTarget] = useState<Payment | null>(null);

  const customerNames = useMemo(() => customers.map((c) => c.name), [customers]);

  // Filter and sort payments
  const filteredPayments = useMemo(() => {
    return payments
      .filter((p) => {
        // Search query
        if (filters.searchQuery.trim()) {
          const q = filters.searchQuery.toLowerCase();
          const matchId = p.id.toLowerCase().includes(q);
          const matchCust = p.customerName.toLowerCase().includes(q);
          const matchRef = (p.referenceNumber || '').toLowerCase().includes(q);
          const matchInv = (p.allocations || []).some((a) =>
            a.invoiceNumber.toLowerCase().includes(q)
          );
          if (!matchId && !matchCust && !matchRef && !matchInv) return false;
        }

        // Status Tab
        if (filters.statusTab !== 'all') {
          if (filters.statusTab === 'completed' && p.status !== 'completed' && p.status !== 'partially_refunded') {
            return false;
          }
          if (filters.statusTab === 'pending' && p.status !== 'pending' && p.status !== 'processing') {
            return false;
          }
          if (filters.statusTab === 'failed' && p.status !== 'failed') {
            return false;
          }
          if (filters.statusTab === 'refunded' && p.status !== 'refunded' && p.status !== 'partially_refunded') {
            return false;
          }
        }

        // Customer
        if (filters.customer !== 'all' && p.customerName !== filters.customer) {
          return false;
        }

        // Payment Method
        if (filters.paymentMethod !== 'all' && p.paymentMethod !== filters.paymentMethod) {
          return false;
        }

        // Status Dropdown
        if (filters.status !== 'all' && p.status !== filters.status) {
          return false;
        }

        return true;
      })
      .sort((a, b) => {
        if (filters.sortBy === 'oldest') {
          return new Date(a.paymentDate).getTime() - new Date(b.paymentDate).getTime();
        }
        if (filters.sortBy === 'amount_high') {
          return b.amount - a.amount;
        }
        if (filters.sortBy === 'amount_low') {
          return a.amount - b.amount;
        }
        // Default newest
        return new Date(b.paymentDate).getTime() - new Date(a.paymentDate).getTime();
      });
  }, [payments, filters]);

  const handleResetFilters = () => {
    setFilters({
      searchQuery: '',
      statusTab: 'all',
      customer: 'all',
      paymentMethod: 'all',
      status: 'all',
      sortBy: 'newest',
    });
  };

  return (
    <div className="space-y-4">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-1">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Payments</h1>
            <span className="text-xs font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
              {filteredPayments.length}
            </span>
            <button
              type="button"
              onClick={() => refreshPayments()}
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

      {/* Summary Cards */}
      <PaymentSummaryCards />

      {/* Filters Toolbar */}
      <PaymentFilters
        filters={filters}
        onChange={setFilters}
        onReset={handleResetFilters}
        customers={customerNames}
      />

      {/* Payments Table */}
      <PaymentTable
        payments={filteredPayments}
        onRefund={(payment) => setRefundTarget(payment)}
        onViewReceipt={(payment) => setReceiptTarget(payment)}
        onRecordNew={() => setIsRecordOpen(true)}
      />

      {/* Record Payment Modal */}
      <RecordPaymentModal
        isOpen={isRecordOpen}
        onClose={() => setIsRecordOpen(false)}
      />

      {/* Refund Modal */}
      <RefundModal
        isOpen={!!refundTarget}
        onClose={() => setRefundTarget(null)}
        payment={refundTarget}
      />

      {/* Receipt Modal */}
      <ReceiptModal
        isOpen={!!receiptTarget}
        onClose={() => setReceiptTarget(null)}
        payment={receiptTarget}
      />
    </div>
  );
}
