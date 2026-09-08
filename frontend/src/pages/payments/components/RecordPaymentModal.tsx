import { useState, useEffect, FormEvent } from 'react';
import { usePayments, RecordPaymentInput } from '../PaymentsContext';
import { PaymentType, PaymentMethod, InvoiceAllocation } from '../types';
import { formatINR } from '../mockPayments';
import { X, CheckCircle, CreditCard, Info } from 'lucide-react';

interface RecordPaymentModalProps {
  isOpen: boolean;
  onClose: () => void;
  preselectedCustomerId?: string;
  preselectedInvoiceId?: string;
}

const PAYMENT_METHODS: PaymentMethod[] = [
  'UPI',
  'Credit Card',
  'Debit Card',
  'Bank Transfer',
  'Net Banking',
  'Cash',
  'Cheque',
  'Other',
];

const BANK_ACCOUNTS = [
  'HDFC Bank - A/C **4920 (Operating Collections)',
  'ICICI Bank - A/C **8301 (Corporate Settlement)',
  'Kotak Mahindra Bank - A/C **1190 (Enterprise Escrow)',
  'Axis Bank - A/C **6621 (Merchant Gateway)',
  'State Bank of India - A/C **3320 (General Ledger)',
];

export function RecordPaymentModal({
  isOpen,
  onClose,
  preselectedCustomerId,
}: RecordPaymentModalProps) {
  const { customers, recordPayment } = usePayments();

  const [paymentType, setPaymentType] = useState<PaymentType>('invoice_payment');
  const [customerId, setCustomerId] = useState<string>(preselectedCustomerId || (customers[0]?.id ?? ''));
  const [amountReceived, setAmountReceived] = useState<string>('');
  const [paymentDate, setPaymentDate] = useState<string>(() => new Date().toISOString().split('T')[0]);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('UPI');
  const [referenceNumber, setReferenceNumber] = useState<string>('');
  const [bankAccount, setBankAccount] = useState<string>(BANK_ACCOUNTS[0]);
  const [notes, setNotes] = useState<string>('');

  // Per-invoice allocation input: { [invoiceId]: appliedAmount }
  const [selectedInvoices, setSelectedInvoices] = useState<Record<string, boolean>>({});
  const [allocatedAmounts, setAllocatedAmounts] = useState<Record<string, string>>({});

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const selectedCustomer = customers.find((c) => c.id === customerId);
  const outstandingInvoices = selectedCustomer?.outstandingInvoices || [];

  // Reset or initialize state on open
  useEffect(() => {
    if (isOpen) {
      const initialCustId = preselectedCustomerId || customers[0]?.id || '';
      setCustomerId(initialCustId);
      setPaymentType('invoice_payment');
      setAmountReceived('');
      setPaymentDate(new Date().toISOString().split('T')[0]);
      setPaymentMethod('UPI');
      setReferenceNumber('');
      setBankAccount(BANK_ACCOUNTS[0]);
      setNotes('');
      setSelectedInvoices({});
      setAllocatedAmounts({});
      setErrors({});

      // If customer has invoices, pre-select first invoice
      const cust = customers.find((c) => c.id === initialCustId);
      if (cust && cust.outstandingInvoices.length > 0) {
        const firstInv = cust.outstandingInvoices[0];
        setSelectedInvoices({ [firstInv.id]: true });
        setAllocatedAmounts({ [firstInv.id]: String(firstInv.balanceDue) });
        setAmountReceived(String(firstInv.balanceDue));
      }
    }
  }, [isOpen, preselectedCustomerId, customers]);

  // When customer changes, update available invoices
  const handleCustomerChange = (newCustId: string) => {
    setCustomerId(newCustId);
    setSelectedInvoices({});
    setAllocatedAmounts({});
    const cust = customers.find((c) => c.id === newCustId);
    if (cust && cust.outstandingInvoices.length > 0) {
      const firstInv = cust.outstandingInvoices[0];
      setSelectedInvoices({ [firstInv.id]: true });
      setAllocatedAmounts({ [firstInv.id]: String(firstInv.balanceDue) });
      setAmountReceived(String(firstInv.balanceDue));
    } else {
      setAmountReceived('');
    }
  };

  // Toggle invoice checkbox
  const handleToggleInvoice = (invId: string, balanceDue: number) => {
    const isNowSelected = !selectedInvoices[invId];
    setSelectedInvoices((prev) => ({ ...prev, [invId]: isNowSelected }));

    if (isNowSelected) {
      setAllocatedAmounts((prev) => ({
        ...prev,
        [invId]: prev[invId] || String(balanceDue),
      }));
    } else {
      setAllocatedAmounts((prev) => {
        const copy = { ...prev };
        delete copy[invId];
        return copy;
      });
    }
  };

  // Change individual applied amount
  const handleAppliedAmountChange = (invId: string, val: string) => {
    setAllocatedAmounts((prev) => ({
      ...prev,
      [invId]: val,
    }));
  };

  // Auto-distribute received amount across selected invoices
  const handleAutoDistribute = () => {
    const totalRec = parseFloat(amountReceived) || 0;
    if (totalRec <= 0) return;

    let remainingToApply = totalRec;
    const newAllocated: Record<string, string> = {};
    const newSelected: Record<string, boolean> = {};

    for (const inv of outstandingInvoices) {
      if (remainingToApply <= 0) break;
      const applyThis = Math.min(remainingToApply, inv.balanceDue);
      newAllocated[inv.id] = String(applyThis);
      newSelected[inv.id] = true;
      remainingToApply -= applyThis;
    }

    setSelectedInvoices(newSelected);
    setAllocatedAmounts(newAllocated);
  };

  // Calculate totals
  const numReceived = parseFloat(amountReceived) || 0;
  const totalApplied = paymentType === 'invoice_payment'
    ? Object.entries(allocatedAmounts).reduce((sum, [invId, amountStr]) => {
        if (selectedInvoices[invId]) {
          return sum + (parseFloat(amountStr) || 0);
        }
        return sum;
      }, 0)
    : 0;

  const unappliedBalance = Math.max(0, numReceived - totalApplied);

  const validate = () => {
    const errs: Record<string, string> = {};
    if (!customerId) errs.customerId = 'Please select a customer';
    if (isNaN(numReceived) || numReceived <= 0) {
      errs.amountReceived = 'Amount received must be greater than 0';
    }
    if (!paymentDate) errs.paymentDate = 'Payment date is required';
    if (!paymentMethod) errs.paymentMethod = 'Payment method is required';

    if (paymentType === 'invoice_payment') {
      if (totalApplied > numReceived) {
        errs.allocation = `Total applied (₹${totalApplied.toLocaleString('en-IN')}) cannot exceed amount received (₹${numReceived.toLocaleString('en-IN')})`;
      }

      // Check per-invoice limits
      for (const [invId, amtStr] of Object.entries(allocatedAmounts)) {
        if (selectedInvoices[invId]) {
          const val = parseFloat(amtStr) || 0;
          const inv = outstandingInvoices.find((i) => i.id === invId);
          if (inv && val > inv.balanceDue) {
            errs[`inv_${invId}`] = `Cannot exceed balance due of ₹${inv.balanceDue.toLocaleString('en-IN')}`;
          }
        }
      }
    }

    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    // Build allocations
    const allocations: InvoiceAllocation[] = [];
    if (paymentType === 'invoice_payment') {
      for (const [invId, amtStr] of Object.entries(allocatedAmounts)) {
        if (selectedInvoices[invId]) {
          const appliedVal = parseFloat(amtStr) || 0;
          const inv = outstandingInvoices.find((i) => i.id === invId);
          if (inv && appliedVal > 0) {
            allocations.push({
              invoiceId: inv.id,
              invoiceNumber: inv.invoiceNumber,
              invoiceDate: inv.date,
              invoiceTotal: inv.totalAmount,
              appliedAmount: appliedVal,
              remainingAmount: Math.max(0, inv.balanceDue - appliedVal),
            });
          }
        }
      }
    }

    const input: RecordPaymentInput = {
      paymentType,
      customerId,
      customerName: selectedCustomer?.name || 'Customer',
      amount: numReceived,
      paymentDate,
      paymentMethod,
      referenceNumber: referenceNumber.trim(),
      notes: notes.trim() || undefined,
      bankAccount,
      allocations,
    };

    setSubmitting(true);
    try {
      await recordPayment(input);
      onClose();
    } catch (err) {
      console.error('Failed to record payment:', err);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] flex flex-col">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between shrink-0 bg-slate-50/50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
              <CreditCard className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900">Record Payment</h3>
              <p className="text-xs text-slate-500">
                Log a received customer payment, settle outstanding invoices or record advance credit.
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

        {/* Modal Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Payment Type Tabs */}
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-700">Payment Type</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setPaymentType('invoice_payment')}
                className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg border text-xs font-semibold transition-all ${
                  paymentType === 'invoice_payment'
                    ? 'border-brand-500 bg-brand-50 text-brand-700 shadow-2xs'
                    : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                <span>Invoice Payment</span>
              </button>
              <button
                type="button"
                onClick={() => setPaymentType('customer_advance')}
                className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg border text-xs font-semibold transition-all ${
                  paymentType === 'customer_advance'
                    ? 'border-blue-500 bg-blue-50 text-blue-700 shadow-2xs'
                    : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                <span>Customer Advance Credit</span>
              </button>
            </div>
          </div>

          {/* Customer & Amount Row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            {/* Customer */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Customer <span className="text-rose-500">*</span>
              </label>
              <select
                value={customerId}
                onChange={(e) => handleCustomerChange(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} {c.creditBalance > 0 ? `(Credit: ₹${c.creditBalance.toLocaleString('en-IN')})` : ''}
                  </option>
                ))}
              </select>
              {errors.customerId && (
                <p className="text-[11px] text-rose-500 mt-1">{errors.customerId}</p>
              )}
            </div>

            {/* Amount Received */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Amount Received (INR) <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400">
                  ₹
                </span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={amountReceived}
                  onChange={(e) => setAmountReceived(e.target.value)}
                  placeholder="0.00"
                  className="w-full pl-8 pr-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500 font-mono"
                />
              </div>
              {errors.amountReceived && (
                <p className="text-[11px] text-rose-500 mt-1">{errors.amountReceived}</p>
              )}
            </div>
          </div>

          {/* Payment Date & Payment Method */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            {/* Payment Date */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Payment Date <span className="text-rose-500">*</span>
              </label>
              <input
                type="date"
                value={paymentDate}
                onChange={(e) => setPaymentDate(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              {errors.paymentDate && (
                <p className="text-[11px] text-rose-500 mt-1">{errors.paymentDate}</p>
              )}
            </div>

            {/* Payment Method */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Payment Method <span className="text-rose-500">*</span>
              </label>
              <select
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value as PaymentMethod)}
                className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                {PAYMENT_METHODS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Reference Number & Deposit Account */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Reference / Transaction #
              </label>
              <input
                type="text"
                value={referenceNumber}
                onChange={(e) => setReferenceNumber(e.target.value)}
                placeholder="e.g. UPI/20260907/112938, NEFT/HDFC/9981"
                className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Deposit To (Account)
              </label>
              <select
                value={bankAccount}
                onChange={(e) => setBankAccount(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500 truncate"
              >
                {BANK_ACCOUNTS.map((acc) => (
                  <option key={acc} value={acc}>
                    {acc}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* INVOICE SETTLEMENT SECTION */}
          {paymentType === 'invoice_payment' ? (
            <div className="pt-3 border-t border-slate-100 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Apply Payment to Outstanding Invoices
                  </h4>
                  <p className="text-[11px] text-slate-500">
                    Select invoices to settle. Supports full and partial payment application.
                  </p>
                </div>
                {outstandingInvoices.length > 0 && (
                  <button
                    type="button"
                    onClick={handleAutoDistribute}
                    className="text-xs font-semibold text-brand-600 hover:text-brand-700 bg-brand-50 hover:bg-brand-100 px-2.5 py-1 rounded-md transition-colors"
                  >
                    Auto-Allocate
                  </button>
                )}
              </div>

              {errors.allocation && (
                <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
                  {errors.allocation}
                </div>
              )}

              {outstandingInvoices.length === 0 ? (
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 text-center text-xs text-slate-500">
                  <p className="font-medium text-slate-700">No unpaid invoices for this customer</p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Any payment recorded will be stored as an unapplied customer advance credit.
                  </p>
                </div>
              ) : (
                <div className="border border-slate-200/80 rounded-xl overflow-hidden">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-[11px] font-semibold text-slate-600">
                        <th className="py-2 px-3 w-8"></th>
                        <th className="py-2 px-3">Invoice #</th>
                        <th className="py-2 px-3">Due Date</th>
                        <th className="py-2 px-3 text-right">Invoice Total</th>
                        <th className="py-2 px-3 text-right">Balance Due</th>
                        <th className="py-2 px-3 text-right w-36">Apply Amount</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {outstandingInvoices.map((inv) => {
                        const isSelected = !!selectedInvoices[inv.id];
                        const appliedVal = allocatedAmounts[inv.id] || '';
                        const invErr = errors[`inv_${inv.id}`];

                        return (
                          <tr
                            key={inv.id}
                            className={`transition-colors ${isSelected ? 'bg-brand-50/30' : 'hover:bg-slate-50/60'}`}
                          >
                            <td className="py-2.5 px-3">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => handleToggleInvoice(inv.id, inv.balanceDue)}
                                className="w-3.5 h-3.5 rounded text-brand-600 border-slate-300 focus:ring-brand-500"
                              />
                            </td>
                            <td className="py-2.5 px-3 font-mono font-medium text-slate-900">
                              {inv.invoiceNumber}
                            </td>
                            <td className="py-2.5 px-3 text-slate-500">{inv.dueDate}</td>
                            <td className="py-2.5 px-3 text-right font-mono text-slate-600">
                              {formatINR(inv.totalAmount)}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono font-semibold text-slate-900">
                              {formatINR(inv.balanceDue)}
                            </td>
                            <td className="py-2.5 px-3 text-right">
                              <div className="relative inline-block w-32">
                                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-slate-400 font-semibold">
                                  ₹
                                </span>
                                <input
                                  type="number"
                                  min="0"
                                  max={inv.balanceDue}
                                  step="any"
                                  disabled={!isSelected}
                                  value={appliedVal}
                                  onChange={(e) => handleAppliedAmountChange(inv.id, e.target.value)}
                                  placeholder="0.00"
                                  className={`w-full pl-6 pr-2 py-1 text-xs border rounded-lg font-mono text-right focus:outline-none ${
                                    isSelected
                                      ? 'bg-white border-brand-300 text-slate-900 focus:ring-1 focus:ring-brand-500'
                                      : 'bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed'
                                  }`}
                                />
                              </div>
                              {invErr && (
                                <p className="text-[10px] text-rose-500 mt-0.5 text-right">{invErr}</p>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Settlement Live Summary Strip */}
              <div className="bg-slate-50/90 rounded-xl p-3 border border-slate-200/80 space-y-2">
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <span className="text-[11px] text-slate-500 block">Amount Received</span>
                    <span className="font-bold text-slate-900 font-mono text-sm">
                      {formatINR(numReceived)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[11px] text-slate-500 block">Amount Applied</span>
                    <span className="font-bold text-emerald-700 font-mono text-sm">
                      {formatINR(totalApplied)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[11px] text-slate-500 block">Unapplied Balance</span>
                    <span className="font-bold text-blue-700 font-mono text-sm">
                      {formatINR(unappliedBalance)}
                    </span>
                  </div>
                </div>

                {unappliedBalance > 0 && (
                  <div className="flex items-center gap-1.5 text-[11px] text-blue-700 bg-blue-50/70 p-2 rounded-lg border border-blue-100">
                    <Info className="w-3.5 h-3.5 shrink-0" />
                    <span>
                      The unapplied balance of <strong className="font-mono">{formatINR(unappliedBalance)}</strong> will be credited to {selectedCustomer?.name} as an available advance credit for future invoices.
                    </span>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="p-4 rounded-xl bg-blue-50/60 border border-blue-100 space-y-1.5 text-xs text-blue-900">
              <div className="flex items-center gap-2 font-bold">
                <Info className="w-4 h-4 text-blue-600" />
                <span>Customer Advance Deposit</span>
              </div>
              <p className="text-slate-600 leading-relaxed text-[11px]">
                The full payment of <strong className="font-mono font-bold text-slate-900">{formatINR(numReceived)}</strong> will be recorded as unapplied customer credit. It can be applied against subsequent billing cycles or milestone invoices.
              </p>
            </div>
          )}

          {/* Notes */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Internal Notes / Remittance Details
            </label>
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Bank remittance advice verified; settled per contract terms."
              className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>
        </form>

        {/* Modal Footer Actions */}
        <div className="px-6 py-3.5 border-t border-slate-100 bg-slate-50/70 flex items-center justify-end gap-2 shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-200/70 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg shadow-2xs transition-colors"
          >
            <CheckCircle className="w-3.5 h-3.5" />
            <span>{submitting ? 'Recording...' : 'Record Payment'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
