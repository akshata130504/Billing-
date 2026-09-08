import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Payment } from '../types';
import { useAuth } from '../../../hooks/useAuth';
import {
  CreditCard,
  MoreVertical,
  Eye,
  RotateCcw,
  Receipt,
  PlusCircle,
  Building,
  FileText,
  Copy,
  CheckCircle2,
} from 'lucide-react';
import { formatMoney } from '../../../utils/format';
import { LoadingState } from '../../../components/common/LoadingState';

interface PaymentTableProps {
  payments: Payment[];
  isLoading?: boolean;
  onRefund: (payment: Payment) => void;
  onViewReceipt: (payment: Payment) => void;
  onRecordNew: () => void;
}

export function PaymentTable({
  payments,
  isLoading = false,
  onRefund,
  onViewReceipt,
  onRecordNew,
}: PaymentTableProps) {
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const isAdminOrOwner = hasRole('admin');
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopyPaymentId = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const getStatusBadge = (status: Payment['status']) => {
    switch (status) {
      case 'completed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/80">
            Completed
          </span>
        );
      case 'pending':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-amber-50 text-amber-700 border border-amber-200/80">
            Pending
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-rose-50 text-rose-700 border border-rose-200/80">
            Failed
          </span>
        );
      case 'partially_refunded':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-purple-50 text-purple-700 border border-purple-200/80">
            Partially Refunded
          </span>
        );
      case 'refunded':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            Refunded
          </span>
        );
      default:
        return null;
    }
  };

  const getMethodBadge = (method: Payment['paymentMethod']) => {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700">
        {method}
      </span>
    );
  };

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  if (payments.length === 0 && isLoading) {
    return (
      <div className="bg-white border border-slate-200/80 rounded-xl p-12 shadow-2xs">
        <LoadingState message="Loading payments..." />
      </div>
    );
  }

  if (payments.length === 0) {
    return (
      <div className="bg-white border border-slate-200/80 rounded-xl p-12 text-center shadow-2xs">
        <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-3">
          <CreditCard className="w-6 h-6" />
        </div>
        <h3 className="text-sm font-semibold text-slate-900">No payments recorded yet</h3>
        <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
          Record your first customer payment to start tracking collections, settlements and receipts.
        </p>
        <div className="mt-4">
          <button
            type="button"
            onClick={onRecordNew}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 shadow-2xs transition-colors"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            <span>Record Payment</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl overflow-hidden shadow-2xs">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-50/80 border-b border-slate-200 text-[11px] font-semibold text-slate-600 uppercase tracking-wider select-none">
              <th className="py-2.5 px-3.5">Payment #</th>
              <th className="py-2.5 px-3">Customer</th>
              <th className="py-2.5 px-3">Invoice(s)</th>
              <th className="py-2.5 px-3">Payment Date</th>
              <th className="py-2.5 px-3">Method</th>
              <th className="py-2.5 px-3 text-right">Amount</th>
              <th className="py-2.5 px-3 text-right">Applied</th>
              <th className="py-2.5 px-3 text-right">Unapplied</th>
              <th className="py-2.5 px-3 text-center">Status</th>
              <th className="py-2.5 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {payments.map((payment) => {
              const isMenuOpen = activeMenuId === payment.id;
              const hasAllocations = payment.allocations && payment.allocations.length > 0;
              const isAdvance = payment.paymentType === 'customer_advance';
              const canRefund =
                isAdminOrOwner &&
                (payment.status === 'completed' || payment.status === 'partially_refunded') &&
                payment.amount > (payment.refundedAmount || 0);

              return (
                <tr
                  key={payment.id}
                  className="hover:bg-slate-50/70 transition-colors group cursor-pointer"
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest('.action-menu-area')) return;
                    navigate(`/payments/${payment.backendId ?? payment.id}`);
                  }}
                >
                  {/* Payment # */}
                  <td className="py-2.5 px-3.5 min-w-[160px]">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center shrink-0">
                        <CreditCard className="w-3.5 h-3.5" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-slate-900 group-hover:text-brand-600 transition-colors truncate">
                            {payment.id}
                          </span>
                          <button
                            type="button"
                            onClick={(e) => handleCopyPaymentId(e, payment.id)}
                            className="text-slate-400 hover:text-slate-600 action-menu-area"
                            title="Copy Payment ID"
                          >
                            {copiedId === payment.id ? (
                              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                          </button>
                        </div>
                        <span className="text-[10px] font-mono text-slate-400 block truncate">
                          Ref: {payment.referenceNumber}
                        </span>
                      </div>
                    </div>
                  </td>

                  {/* Customer */}
                  <td className="py-2.5 px-3 text-slate-800 whitespace-nowrap font-medium min-w-[170px]">
                    <div className="flex items-center gap-1.5">
                      <Building className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="truncate">{payment.customerName}</span>
                    </div>
                  </td>

                  {/* Invoices */}
                  <td className="py-2.5 px-3 whitespace-nowrap min-w-[150px]">
                    {isAdvance ? (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10.5px] font-semibold bg-blue-50 text-blue-700 border border-blue-100">
                        Customer Advance
                      </span>
                    ) : hasAllocations ? (
                      <div className="flex items-center gap-1 text-slate-700">
                        <FileText className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="font-mono text-xs">
                          {payment.allocations.length === 1
                            ? payment.allocations[0].invoiceNumber
                            : `${payment.allocations[0].invoiceNumber} +${payment.allocations.length - 1} more`}
                        </span>
                      </div>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>

                  {/* Payment Date */}
                  <td className="py-2.5 px-3 text-slate-600 whitespace-nowrap">
                    {formatDate(payment.paymentDate)}
                  </td>

                  {/* Method */}
                  <td className="py-2.5 px-3 whitespace-nowrap">
                    {getMethodBadge(payment.paymentMethod)}
                  </td>

                  {/* Amount */}
                  <td className="py-2.5 px-3 text-right whitespace-nowrap font-bold text-slate-900 font-mono">
                    {formatMoney(payment.amount)}
                  </td>

                  {/* Applied Amount */}
                  <td className="py-2.5 px-3 text-right whitespace-nowrap font-mono text-emerald-700 font-medium">
                    {formatMoney(payment.appliedAmount)}
                  </td>

                  {/* Unapplied Amount */}
                  <td className="py-2.5 px-3 text-right whitespace-nowrap font-mono">
                    {payment.unappliedAmount > 0 ? (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10.5px] font-semibold bg-blue-50 text-blue-700 border border-blue-100">
                        {formatMoney(payment.unappliedAmount)} (Credit)
                      </span>
                    ) : (
                      <span className="text-slate-400">₹0</span>
                    )}
                  </td>

                  {/* Status */}
                  <td className="py-2.5 px-3 text-center whitespace-nowrap">
                    {getStatusBadge(payment.status)}
                  </td>

                  {/* Actions */}
                  <td className="py-2.5 px-3 text-right whitespace-nowrap action-menu-area relative">
                    <div className="flex items-center justify-end gap-1">
                      <Link
                        to={`/payments/${payment.backendId ?? payment.id}`}
                        className="p-1.5 text-slate-400 hover:text-brand-600 hover:bg-slate-100 rounded-lg transition-colors"
                        title="View Payment Details"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </Link>

                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onViewReceipt(payment);
                        }}
                        className="p-1.5 text-slate-400 hover:text-brand-600 hover:bg-slate-100 rounded-lg transition-colors"
                        title="View Receipt"
                      >
                        <Receipt className="w-3.5 h-3.5" />
                      </button>

                      {/* Dropdown Menu Toggle */}
                      <div className="relative inline-block text-left">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setActiveMenuId(isMenuOpen ? null : payment.id);
                          }}
                          className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                          title="More Actions"
                        >
                          <MoreVertical className="w-3.5 h-3.5" />
                        </button>

                        {/* Dropdown Menu */}
                        {isMenuOpen && (
                          <>
                            <div
                              className="fixed inset-0 z-20"
                              onClick={(e) => {
                                e.stopPropagation();
                                setActiveMenuId(null);
                              }}
                            />
                            <div className="absolute right-0 top-full mt-1 w-44 bg-white border border-slate-200 rounded-xl shadow-lg z-30 py-1 text-xs">
                              <Link
                                to={`/payments/${payment.backendId ?? payment.id}`}
                                className="w-full px-3 py-1.5 text-left text-slate-700 hover:bg-slate-50 flex items-center gap-2"
                              >
                                <Eye className="w-3.5 h-3.5 text-slate-400" />
                                View Details
                              </Link>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setActiveMenuId(null);
                                  onViewReceipt(payment);
                                }}
                                className="w-full px-3 py-1.5 text-left text-slate-700 hover:bg-slate-50 flex items-center gap-2"
                              >
                                <Receipt className="w-3.5 h-3.5 text-slate-400" />
                                Receipt
                              </button>
                              {canRefund && (
                                <>
                                  <div className="my-1 border-t border-slate-100" />
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setActiveMenuId(null);
                                      onRefund(payment);
                                    }}
                                    className="w-full px-3 py-1.5 text-left text-rose-600 hover:bg-rose-50 flex items-center gap-2 font-medium"
                                  >
                                    <RotateCcw className="w-3.5 h-3.5" />
                                    Issue Refund
                                  </button>
                                </>
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
