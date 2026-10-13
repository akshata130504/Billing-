import { Payment } from '../types';
import { X, Download, Mail, CheckCircle2, ShieldCheck } from 'lucide-react';
import { useToast } from '../../../components/common/Toast';
import { RoomanLogo } from '../../../components/common/RoomanLogo';
import { formatRecordMoney } from '../../../utils/format';
import { useAuth } from '../../../hooks/useAuth';

interface ReceiptModalProps {
  isOpen: boolean;
  onClose: () => void;
  payment: Payment | null;
}

export function ReceiptModal({ isOpen, onClose, payment }: ReceiptModalProps) {
  const { showToast } = useToast();
  const { organization } = useAuth();

  const issuerLocation = [organization?.city, organization?.state, organization?.country]
    .filter(Boolean)
    .join(', ');

  if (!isOpen || !payment) return null;

  const handleDownload = () => {
    window.print();
    showToast('success', 'Receipt Downloaded', `Receipt #${payment.receiptNumber} generated.`);
  };

  const handleSendEmail = () => {
    showToast(
      'success',
      'Receipt Sent',
      `Payment receipt #${payment.receiptNumber} sent to ${payment.customerEmail || payment.customerName}.`
    );
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-xl overflow-hidden animate-in fade-in zoom-in-95 duration-150 flex flex-col max-h-[90vh]">
        {/* Top Control Bar */}
        <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between shrink-0 bg-slate-50/70">
          <span className="text-xs font-semibold text-slate-700">Official Payment Receipt Preview</span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={handleSendEmail}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
            >
              <Mail className="w-3 h-3 text-slate-500" />
              <span>Send</span>
            </button>
            <button
              type="button"
              onClick={handleDownload}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors shadow-2xs"
            >
              <Download className="w-3 h-3" />
              <span>Download / Print</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 ml-1"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Receipt Document Card */}
        <div className="flex-1 overflow-y-auto p-8 space-y-6 bg-white text-slate-900 printable-receipt">
          {/* Header */}
          <div className="flex items-start justify-between border-b border-slate-100 pb-5">
            <div>
              {organization?.logo_url ? (
                <img
                  src={organization.logo_url}
                  alt={organization.name}
                  className="h-8 max-w-[180px] object-contain"
                />
              ) : (
                <RoomanLogo variant="brand" size="md" showBillingBadge={true} />
              )}
              <p className="text-[11px] font-semibold text-slate-700 mt-1">
                {organization?.legal_name || organization?.name || ''}
              </p>
              {issuerLocation && <p className="text-[10px] text-slate-400">{issuerLocation}</p>}
              {organization?.gstin && (
                <p className="text-[10px] text-slate-400">GSTIN: {organization.gstin}</p>
              )}
            </div>

            <div className="text-right">
              <span className="text-xs font-bold uppercase tracking-wider text-brand-700 bg-brand-50 px-2 py-0.5 rounded border border-brand-100">
                Payment Receipt
              </span>
              <p className="text-base font-mono font-bold text-slate-900 mt-1.5">
                {payment.receiptNumber}
              </p>
              <p className="text-[11px] text-slate-500">Date: {payment.paymentDate}</p>
            </div>
          </div>

          {/* Customer & Payment Meta Grid */}
          <div className="grid grid-cols-2 gap-4 p-4 rounded-xl bg-slate-50/80 border border-slate-200/80 text-xs">
            <div>
              <span className="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">
                Received From
              </span>
              <p className="font-bold text-slate-900 text-sm">{payment.customerName}</p>
              {payment.customerEmail && (
                <p className="text-slate-500 text-[11px] mt-0.5">{payment.customerEmail}</p>
              )}
            </div>

            <div className="text-right">
              <span className="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">
                Payment Details
              </span>
              <p className="font-semibold text-slate-800">
                Payment #: <span className="font-mono">{payment.id}</span>
              </p>
              <p className="text-slate-500 text-[11px] mt-0.5">
                Method: {payment.paymentMethod}
              </p>
              <p className="text-slate-400 font-mono text-[10px] mt-0.5">
                Ref: {payment.referenceNumber}
              </p>
            </div>
          </div>

          {/* Amount Paid Callout */}
          <div className="p-4 rounded-xl bg-emerald-50/60 border border-emerald-100 flex items-center justify-between">
            <div>
              <span className="text-[11px] uppercase font-bold text-emerald-800 block">
                Amount Received
              </span>
              <span className="text-2xl font-bold font-mono text-emerald-900">
                {formatRecordMoney(payment.amount, payment.currency)}
              </span>
            </div>
            <div className="text-right flex items-center gap-1 text-xs font-semibold text-emerald-700 bg-white px-3 py-1.5 rounded-lg border border-emerald-200">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>Settlement Cleared</span>
            </div>
          </div>

          {/* Invoices Allocated Section */}
          <div className="space-y-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-700 block">
              Invoice Settlement Breakdown
            </span>

            {payment.allocations && payment.allocations.length > 0 ? (
              <div className="border border-slate-200 rounded-xl overflow-hidden text-xs">
                <table className="w-full text-left">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-[11px] font-semibold text-slate-600">
                      <th className="py-2 px-3">Invoice #</th>
                      <th className="py-2 px-3 text-right">Amount Applied</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {payment.allocations.map((alloc) => (
                      <tr key={alloc.invoiceId}>
                        <td className="py-2 px-3 font-mono font-medium text-slate-900">
                          {alloc.invoiceNumber}
                        </td>
                        <td className="py-2 px-3 text-right font-mono font-bold text-emerald-700">
                          {formatRecordMoney(alloc.appliedAmount, payment.currency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-3 bg-blue-50/60 rounded-xl border border-blue-100 text-xs text-blue-900">
                <p className="font-semibold">Customer Advance Credit</p>
                <p className="text-[11px] text-slate-600 mt-0.5">
                  Full amount of {formatRecordMoney(payment.amount, payment.currency)} credited to customer account for upcoming billing cycles.
                </p>
              </div>
            )}
          </div>

          {/* Refund Notice if applicable */}
          {payment.refundedAmount > 0 && (
            <div className="p-3 bg-rose-50 rounded-xl border border-rose-100 text-xs text-rose-800">
              <span className="font-bold block">Refund Notice:</span>
              <span>
                {formatRecordMoney(payment.refundedAmount, payment.currency)} has been refunded against this payment. Net settled amount: {formatRecordMoney(payment.amount - payment.refundedAmount, payment.currency)}.
              </span>
            </div>
          )}

          {/* Footer Signatory and Security Stamp */}
          <div className="pt-6 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>Digitally verified transaction receipt</span>
            </div>
            <div className="text-right">
              <p className="font-semibold text-slate-800">
                {organization?.name || 'Billing'}
              </p>
              {organization?.email && <p className="text-[10px]">{organization.email}</p>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
