import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { usePayments } from './PaymentsContext';
import { Payment } from './types';
import { useAuth } from '../../hooks/useAuth';
import { RefundModal } from './components/RefundModal';
import { ReceiptModal } from './components/ReceiptModal';
import {
  ArrowLeft,
  RotateCcw,
  Receipt,
  Mail,
  Building,
  FileText,
  AlertCircle,
  Clock,
  Landmark,
} from 'lucide-react';
import { useToast } from '../../components/common/Toast';
import { formatMoney } from '../../utils/format';

export function PaymentDetailsPage() {
  const { paymentId, id: paramId } = useParams<{ paymentId?: string; id?: string }>();
  const effectiveId = paymentId || paramId;
  const { getPaymentById, fetchPaymentById } = usePayments();
  const { hasRole } = useAuth();
  const isAdminOrOwner = hasRole('admin');
  const { showToast } = useToast();

  const [isRefundOpen, setIsRefundOpen] = useState(false);
  const [isReceiptOpen, setIsReceiptOpen] = useState(false);
  const [livePayment, setLivePayment] = useState<Payment | null>(null);
  const [loadingLive, setLoadingLive] = useState(false);

  const localPayment = effectiveId ? getPaymentById(effectiveId) : undefined;
  const payment = livePayment || localPayment;

  useEffect(() => {
    if (!localPayment && effectiveId) {
      setLoadingLive(true);
      fetchPaymentById(effectiveId)
        .then((p) => {
          if (p) setLivePayment(p);
        })
        .finally(() => setLoadingLive(false));
    }
  }, [localPayment, effectiveId, fetchPaymentById]);

  if (loadingLive) {
    return (
      <div className="bg-white border border-slate-200/80 rounded-2xl p-12 text-center shadow-2xs">
        <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-xs text-slate-500 font-medium">Loading payment details...</p>
      </div>
    );
  }

  if (!payment) {
    return (
      <div className="bg-white border border-slate-200/80 rounded-2xl p-12 text-center shadow-2xs">
        <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-500 flex items-center justify-center mx-auto mb-3">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-base font-bold text-slate-900">Payment Not Found</h2>
        <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
          The requested payment record <span className="font-mono font-semibold">{effectiveId}</span> could not be found in this organization.
        </p>
        <div className="mt-4">
          <Link
            to="/payments"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 shadow-2xs transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Return to Payments</span>
          </Link>
        </div>
      </div>
    );
  }

  const getStatusBadge = () => {
    switch (payment.status) {
      case 'completed':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            Completed
          </span>
        );
      case 'pending':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            Pending
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            Failed
          </span>
        );
      case 'partially_refunded':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            Partially Refunded
          </span>
        );
      case 'refunded':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            Refunded
          </span>
        );
      default:
        return null;
    }
  };

  const handleSendReceipt = () => {
    showToast(
      'success',
      'Receipt Sent',
      `Payment receipt #${payment.receiptNumber} sent to ${payment.customerEmail || payment.customerName}.`
    );
  };

  const netAmount = payment.amount - (payment.refundedAmount || 0);
  const canRefund =
    isAdminOrOwner &&
    (payment.status === 'completed' || payment.status === 'partially_refunded') &&
    payment.amount > (payment.refundedAmount || 0);

  return (
    <div className="space-y-4">
      {/* Back button */}
      <div>
        <Link
          to="/payments"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Payments</span>
        </Link>
      </div>

      {/* Top Banner Header */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              <span className="text-xs font-mono font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
                {payment.id}
              </span>
              {getStatusBadge()}
              {payment.paymentType === 'customer_advance' ? (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-100">
                  Customer Advance
                </span>
              ) : (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
                  Invoice Settlement
                </span>
              )}
            </div>

            <h1 className="text-xl font-bold text-slate-900 tracking-tight">
              Payment #{payment.id}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Received from <strong className="text-slate-800 font-semibold">{payment.customerName}</strong> on {payment.paymentDate} via {payment.paymentMethod}.
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 flex-wrap shrink-0">
            <button
              type="button"
              onClick={() => setIsReceiptOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-700 bg-white border border-slate-200/80 hover:bg-slate-50 shadow-2xs transition-colors"
            >
              <Receipt className="w-3.5 h-3.5 text-slate-500" />
              <span>View Receipt</span>
            </button>

            <button
              type="button"
              onClick={handleSendReceipt}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-700 bg-white border border-slate-200/80 hover:bg-slate-50 shadow-2xs transition-colors"
            >
              <Mail className="w-3.5 h-3.5 text-slate-500" />
              <span>Send Receipt</span>
            </button>

            {canRefund && (
              <button
                type="button"
                onClick={() => setIsRefundOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-rose-600 bg-white border border-rose-200/80 hover:bg-rose-50 shadow-2xs transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5 text-rose-500" />
                <span>Issue Refund</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Main Grid: Details & Settlement Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left 2 Columns */}
        <div className="lg:col-span-2 space-y-4">
          {/* Amount & Key Metrics */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-800 mb-3 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-600" />
              Transaction Breakdown
            </h2>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-1">
              <div>
                <span className="text-[11px] font-medium text-slate-400 block uppercase">
                  Amount Received
                </span>
                <span className="text-xl font-bold text-slate-900 font-mono tracking-tight">
                  {formatMoney(payment.amount)}
                </span>
              </div>

              <div>
                <span className="text-[11px] font-medium text-emerald-600 block uppercase">
                  Applied to Invoices
                </span>
                <span className="text-xl font-bold text-emerald-700 font-mono tracking-tight">
                  {formatMoney(payment.appliedAmount)}
                </span>
              </div>

              <div>
                <span className="text-[11px] font-medium text-blue-600 block uppercase">
                  Unapplied / Advance
                </span>
                <span className="text-xl font-bold text-blue-700 font-mono tracking-tight">
                  {formatMoney(payment.unappliedAmount)}
                </span>
              </div>

              <div>
                <span className="text-[11px] font-medium text-slate-400 block uppercase">
                  Net Settlement
                </span>
                <span className="text-xl font-bold text-slate-900 font-mono tracking-tight">
                  {formatMoney(netAmount)}
                </span>
              </div>
            </div>
          </div>

          {/* Payment Allocation Table */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
              Invoice Allocations
            </h2>

            {payment.allocations && payment.allocations.length > 0 ? (
              <div className="border border-slate-200 rounded-xl overflow-hidden text-xs">
                <table className="w-full text-left">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-[11px] font-semibold text-slate-600 uppercase">
                      <th className="py-2.5 px-3.5">Invoice #</th>
                      <th className="py-2.5 px-3 text-right">Applied This Payment</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {payment.allocations.map((alloc) => (
                      <tr key={alloc.invoiceId} className="hover:bg-slate-50/50">
                        <td className="py-2.5 px-3.5 font-mono font-medium text-brand-600">
                          <Link to={`/invoices/${alloc.invoiceId}`} className="hover:underline">
                            {alloc.invoiceNumber}
                          </Link>
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold text-emerald-700">
                          {formatMoney(alloc.appliedAmount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-4 rounded-xl bg-blue-50/60 border border-blue-100 text-xs text-blue-900 space-y-1">
                <p className="font-semibold">Customer Advance Credit (Unallocated)</p>
                <p className="text-slate-600 leading-relaxed text-[11px]">
                  This payment was recorded as an advance customer credit. The full received amount of {formatMoney(payment.amount)} is preserved as available credit on the customer's account.
                </p>
              </div>
            )}
          </div>

          {/* Refund History Ledger (if any) */}
          {payment.refunds && payment.refunds.length > 0 && (
            <div className="bg-white border border-rose-200/80 rounded-2xl p-5 shadow-2xs space-y-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-rose-700 flex items-center gap-2">
                <RotateCcw className="w-3.5 h-3.5 text-rose-600" />
                Refund History Ledger
              </h2>

              <div className="border border-rose-100 rounded-xl overflow-hidden text-xs">
                <table className="w-full text-left">
                  <thead>
                    <tr className="bg-rose-50/60 border-b border-rose-100 text-[11px] font-semibold text-rose-800 uppercase">
                      <th className="py-2 px-3">Refund ID</th>
                      <th className="py-2 px-3">Date</th>
                      <th className="py-2 px-3">Reason</th>
                      <th className="py-2 px-3">Mode</th>
                      <th className="py-2 px-3 text-right">Amount Refunded</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-rose-50">
                    {payment.refunds.map((ref) => (
                      <tr key={ref.id}>
                        <td className="py-2 px-3 font-mono font-semibold text-slate-900">{ref.id}</td>
                        <td className="py-2 px-3 text-slate-600">{ref.date}</td>
                        <td className="py-2 px-3 text-slate-700">{ref.reason}</td>
                        <td className="py-2 px-3 text-slate-600">{ref.refundMode}</td>
                        <td className="py-2 px-3 text-right font-mono font-bold text-rose-700">
                          {formatMoney(ref.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Banking & Remittance Metadata */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <Landmark className="w-3.5 h-3.5 text-slate-500" />
              Settlement Details
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-0.5">
                  Channel
                </span>
                <span className="font-semibold text-slate-800">
                  {payment.gateway === 'razorpay' ? 'Razorpay gateway' : 'Recorded manually'}
                </span>
              </div>

              <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-0.5">
                  {payment.gateway === 'razorpay' ? 'Gateway reference' : 'Transaction reference'}
                </span>
                <span className="font-mono font-semibold text-slate-800">
                  {payment.gatewayReference || payment.referenceNumber || '—'}
                </span>
              </div>
            </div>

            {payment.notes && (
              <div className="pt-2 text-xs">
                <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-1">
                  Remittance Notes
                </span>
                <p className="p-3 rounded-xl bg-slate-50 border border-slate-100 text-slate-600 leading-relaxed">
                  {payment.notes}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Right 1 Column: Customer Summary & Receipt Card */}
        <div className="space-y-4">
          {/* Customer Overview Card */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <Building className="w-3.5 h-3.5 text-brand-600" />
              Customer Information
            </h2>

            <div className="space-y-2 text-xs">
              <div>
                <span className="text-[10px] uppercase text-slate-400 block">Customer Name</span>
                <p className="font-bold text-slate-900 text-sm">{payment.customerName}</p>
                <span className="text-[11px] font-mono text-slate-400">{payment.customerId}</span>
              </div>

              {payment.customerEmail && (
                <div>
                  <span className="text-[10px] uppercase text-slate-400 block">Billing Email</span>
                  <p className="text-slate-700">{payment.customerEmail}</p>
                </div>
              )}

              <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
                <span className="text-slate-500">Payment Method</span>
                <span className="font-semibold text-slate-800">{payment.paymentMethod}</span>
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">Receipt #</span>
                <span className="font-mono font-medium text-slate-700">{payment.receiptNumber}</span>
              </div>
            </div>
          </div>

          {/* Quick Receipt Download Card */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-800">
              <Receipt className="w-3.5 h-3.5 text-brand-600" />
              Payment Receipt
            </div>

            <p className="text-xs text-slate-500 leading-relaxed">
              Official company receipt generated under Rooman Billing digital settlement records.
            </p>

            <button
              type="button"
              onClick={() => setIsReceiptOpen(true)}
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200/70 rounded-lg transition-colors"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Preview Full Receipt</span>
            </button>
          </div>

          {/* Audit Timestamp Card */}
          <div className="bg-slate-50 border border-slate-200/70 rounded-2xl p-4 text-xs text-slate-500 space-y-1.5">
            <div className="flex items-center gap-1.5 font-semibold text-slate-700">
              <Clock className="w-3.5 h-3.5" />
              <span>Audit Trail</span>
            </div>
            <p className="text-[11px]">
              Recorded on {new Date(payment.createdAt).toLocaleString()}
            </p>
            {payment.updatedAt !== payment.createdAt && (
              <p className="text-[11px]">
                Last updated on {new Date(payment.updatedAt).toLocaleString()}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Modals */}
      <RefundModal
        isOpen={isRefundOpen}
        onClose={() => setIsRefundOpen(false)}
        payment={payment}
      />

      <ReceiptModal
        isOpen={isReceiptOpen}
        onClose={() => setIsReceiptOpen(false)}
        payment={payment}
      />
    </div>
  );
}
