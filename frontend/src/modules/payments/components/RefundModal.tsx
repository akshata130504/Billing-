import { useState, useEffect, FormEvent } from 'react';
import { Payment } from '../types';
import { usePayments, RefundPaymentInput } from '../PaymentsContext';
import { useAuth } from '../../../hooks/useAuth';
import { X, RotateCcw, AlertTriangle } from 'lucide-react';
import { formatRecordMoney, recordCurrencySymbol } from '../../../utils/format';
import { validatePositiveMoney, parseStrictNumber } from '../../../utils/validation';

interface RefundModalProps {
  isOpen: boolean;
  onClose: () => void;
  payment: Payment | null;
}

const REFUND_REASONS = [
  'Customer Request',
  'Duplicate Payment',
  'Billing Dispute / SOW Adjustment',
  'Contract Cancellation',
  'Service Outage Credit',
  'Other',
];

export function RefundModal({ isOpen, onClose, payment }: RefundModalProps) {
  const { refundPayment } = usePayments();
  const { hasRole } = useAuth();
  const isAdminOrOwner = hasRole('admin');

  const [refundAmount, setRefundAmount] = useState<string>('');
  const [reason, setReason] = useState<string>(REFUND_REASONS[0]);
  const [refundMode, setRefundMode] = useState<string>('Original Payment Method');
  const [referenceNumber, setReferenceNumber] = useState<string>('');
  const [notes, setNotes] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);

  const alreadyRefunded = payment?.refundedAmount || 0;
  const maxRefundable = payment
    ? Math.round(Math.max(0, payment.amount - alreadyRefunded) * 100) / 100
    : 0;

  useEffect(() => {
    if (payment && isOpen) {
      setRefundAmount(maxRefundable.toFixed(2));
      setReason(REFUND_REASONS[0]);
      setRefundMode(`Original Payment Method (${payment.paymentMethod})`);
      setReferenceNumber('');
      setNotes('');
      setError('');
    }
  }, [payment, isOpen, maxRefundable]);

  if (!isOpen || !payment) return null;

  const handleFullRefundClick = () => {
    setRefundAmount(maxRefundable.toFixed(2));
    setError('');
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!isAdminOrOwner) {
      setError('Refunds require Administrator or Owner permissions.');
      return;
    }

    const amountError = validatePositiveMoney(refundAmount, 'Refund amount', { required: true });
    if (amountError) {
      setError(amountError);
      return;
    }

    const numRefund = parseStrictNumber(refundAmount) ?? 0;

    if (numRefund - maxRefundable > 0.005) {
      setError(`Refund amount cannot exceed the refundable amount (${formatRecordMoney(maxRefundable, payment.currency)})`);
      return;
    }

    const input: RefundPaymentInput = {
      paymentId: payment.id,
      amount: numRefund,
      reason,
      refundMode,
      referenceNumber: referenceNumber.trim() || undefined,
      notes: notes.trim() || undefined,
    };

    setSubmitting(true);
    try {
      await refundPayment(input);
      onClose();
    } catch (err) {
      console.error('Refund processing error:', err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-lg overflow-hidden animate-in fade-in zoom-in-95 duration-150 flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between shrink-0 bg-slate-50/50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
              <RotateCcw className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900">Issue Payment Refund</h3>
              <p className="text-xs text-slate-500">
                Process partial or full refund for Payment #{payment.id}.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Payment Context Card */}
          <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200/70 space-y-2 text-xs">
            <div className="flex justify-between items-center text-slate-600">
              <span>Customer:</span>
              <span className="font-semibold text-slate-900">{payment.customerName}</span>
            </div>
            <div className="flex justify-between items-center text-slate-600">
              <span>Original Payment Amount:</span>
              <span className="font-mono font-bold text-slate-900">{formatRecordMoney(payment.amount, payment.currency)}</span>
            </div>
            {alreadyRefunded > 0 && (
              <div className="flex justify-between items-center text-rose-600">
                <span>Previously Refunded:</span>
                <span className="font-mono font-semibold">{formatRecordMoney(alreadyRefunded, payment.currency)}</span>
              </div>
            )}
            <div className="pt-2 border-t border-slate-200/60 flex justify-between items-center text-emerald-800 font-medium">
              <span>Remaining Refundable:</span>
              <span className="font-mono font-bold text-emerald-700 text-sm">
                {formatRecordMoney(maxRefundable, payment.currency)}
              </span>
            </div>
          </div>

          {/* Refund Amount Input */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-semibold text-slate-700">
                Refund Amount (INR) <span className="text-rose-500">*</span>
              </label>
              <button
                type="button"
                onClick={handleFullRefundClick}
                className="text-[11px] font-semibold text-brand-600 hover:text-brand-700 hover:underline"
              >
                Refund Full Balance ({formatRecordMoney(maxRefundable, payment.currency)})
              </button>
            </div>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400">
                {recordCurrencySymbol(payment.currency)}
              </span>
              <input
                type="number"
                min="1"
                max={maxRefundable}
                step="any"
                value={refundAmount}
                onChange={(e) => {
                  setRefundAmount(e.target.value);
                  setError('');
                }}
                placeholder="0.00"
                className="w-full pl-8 pr-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-rose-500 font-mono"
              />
            </div>
            {error && (
              <div className="flex items-center gap-1.5 text-[11px] text-rose-500 mt-1">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}
          </div>

          {/* Refund Mode & Reason */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Refund Mode
              </label>
              <select
                value={refundMode}
                onChange={(e) => setRefundMode(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                <option value={`Original Payment Method (${payment.paymentMethod})`}>
                  Original ({payment.paymentMethod})
                </option>
                <option value="Bank Transfer (NEFT/RTGS)">Bank Transfer (NEFT/RTGS)</option>
                <option value="Credit Note / Account Balance">Credit Note / Account Credit</option>
                <option value="Cheque">Cheque</option>
                <option value="Cash">Cash</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Reason for Refund <span className="text-rose-500">*</span>
              </label>
              <select
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                {REFUND_REASONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Reference # */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Refund Reference # / Banking Transaction ID
            </label>
            <input
              type="text"
              value={referenceNumber}
              onChange={(e) => setReferenceNumber(e.target.value)}
              placeholder="e.g. REF/REV/8849102"
              className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          {/* Internal Notes */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Internal Audit Notes
            </label>
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Explain reason and authorization for issuing this refund..."
              className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          {/* Actions */}
          <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !isAdminOrOwner}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg shadow-2xs transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5 shrink-0" />
              <span>{submitting ? 'Processing...' : 'Confirm Refund'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
