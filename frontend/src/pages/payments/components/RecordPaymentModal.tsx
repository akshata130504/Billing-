import { useState, useEffect, useRef, useMemo, FormEvent } from 'react';
import { usePayments, RecordPaymentInput } from '../PaymentsContext';
import { PaymentType, PaymentMethod, InvoiceAllocation } from '../types';
import {
  X,
  CheckCircle,
  CreditCard,
  Info,
  Search,
  ChevronDown,
  UserPlus,
  AlertCircle,
} from 'lucide-react';
import { formatMoney } from '../../../utils/format';
import { validateDateNotFuture, validatePositiveMoney } from '../../../utils/validation';

interface RecordPaymentModalProps {
  isOpen: boolean;
  onClose: () => void;
  preselectedCustomerId?: string;
  preselectedInvoiceId?: string;
}

/** Half-up rounding to 2 decimals; money never travels as a raw float sum. */
const round2 = (n: number): number => Math.round((n + Number.EPSILON) * 100) / 100;
/** Half a paise: anything smaller is float noise, not a real overage. */
const CENT_TOLERANCE = 0.005;

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

export function RecordPaymentModal({
  isOpen,
  onClose,
  preselectedCustomerId,
}: RecordPaymentModalProps) {
  const { customers, recordPayment, createCustomer, loadCustomerInvoices, searchCustomers } =
    usePayments();

  const [paymentType, setPaymentType] = useState<PaymentType>('invoice_payment');
  const [customerId, setCustomerId] = useState<string>(preselectedCustomerId || (customers[0]?.id ?? ''));
  const [amountReceived, setAmountReceived] = useState<string>('');
  const [paymentDate, setPaymentDate] = useState<string>(() => new Date().toISOString().split('T')[0]);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('UPI');
  const [referenceNumber, setReferenceNumber] = useState<string>('');
  const [notes, setNotes] = useState<string>('');

  // Customer combobox & create state
  const [customerSearchQuery, setCustomerSearchQuery] = useState('');
  const [isCustomerDropdownOpen, setIsCustomerDropdownOpen] = useState(false);
  const [isCreateCustomerModalOpen, setIsCreateCustomerModalOpen] = useState(false);
  const [newCustomerName, setNewCustomerName] = useState('');
  const [newCustomerEmail, setNewCustomerEmail] = useState('');
  const [newCustomerPhone, setNewCustomerPhone] = useState('');
  const [newCustomerError, setNewCustomerError] = useState('');
  const [creatingCustomer, setCreatingCustomer] = useState(false);
  const customerDropdownRef = useRef<HTMLDivElement>(null);

  // Close customer dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        customerDropdownRef.current &&
        !customerDropdownRef.current.contains(event.target as Node)
      ) {
        setIsCustomerDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  // Per-invoice allocation input: { [invoiceId]: appliedAmount }
  const [selectedInvoices, setSelectedInvoices] = useState<Record<string, boolean>>({});
  const [allocatedAmounts, setAllocatedAmounts] = useState<Record<string, string>>({});

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const selectedCustomer = customers.find((c) => c.id === customerId);
  const outstandingInvoices = selectedCustomer?.outstandingInvoices || [];

  // Typing in the combobox queries the server, so customers beyond the first
  // preloaded page are findable too.
  useEffect(() => {
    if (!isCustomerDropdownOpen) return;
    const q = customerSearchQuery.trim();
    if (q.length < 2) return;
    const timer = setTimeout(() => {
      void searchCustomers(q);
    }, 250);
    return () => clearTimeout(timer);
  }, [customerSearchQuery, isCustomerDropdownOpen, searchCustomers]);

  // Filtered customers for combobox
  const filteredCustomers = useMemo(() => {
    const q = customerSearchQuery.trim().toLowerCase();
    if (!q) return customers;
    return customers.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.email && c.email.toLowerCase().includes(q))
    );
  }, [customers, customerSearchQuery]);

  const handleCreateCustomerSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmedName = newCustomerName.trim();
    if (!trimmedName) {
      setNewCustomerError('Customer name is required.');
      return;
    }
    const isDuplicate = customers.some(
      (c) => c.name.trim().toLowerCase() === trimmedName.toLowerCase()
    );
    if (isDuplicate) {
      setNewCustomerError(`A customer named "${trimmedName}" already exists.`);
      return;
    }

    setNewCustomerError('');
    setCreatingCustomer(true);
    try {
      const created = await createCustomer({
        displayName: trimmedName,
        email: newCustomerEmail.trim() || undefined,
        phone: newCustomerPhone.trim() || undefined,
      });
      handleCustomerChange(created.id);
      setIsCreateCustomerModalOpen(false);
      setNewCustomerName('');
      setNewCustomerEmail('');
      setNewCustomerPhone('');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create customer.';
      setNewCustomerError(msg);
    } finally {
      setCreatingCustomer(false);
    }
  };

  // Reset or initialize state on open
  useEffect(() => {
    if (isOpen) {
      const initialCustId = preselectedCustomerId || customers[0]?.id || '';
      setCustomerId(initialCustId);
      if (initialCustId) void loadCustomerInvoices(initialCustId);
      setPaymentType('invoice_payment');
      setAmountReceived('');
      setPaymentDate(new Date().toISOString().split('T')[0]);
      setPaymentMethod('UPI');
      setReferenceNumber('');
      setNotes('');
      setSelectedInvoices({});
      setAllocatedAmounts({});
      setErrors({});
      setCustomerSearchQuery('');
      setIsCustomerDropdownOpen(false);
      setIsCreateCustomerModalOpen(false);
      setNewCustomerError('');

    }
    // `customers` is deliberately not a dependency: it changes as invoices load,
    // which would otherwise reset the form the user is filling in.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, preselectedCustomerId]);

  // Pre-select the oldest open invoice once the customer's invoices arrive.
  useEffect(() => {
    if (!isOpen || !customerId) return;
    const cust = customers.find((c) => c.id === customerId);
    const first = cust?.outstandingInvoices[0];
    if (!first) return;
    setSelectedInvoices((prev) => (Object.keys(prev).length > 0 ? prev : { [first.id]: true }));
    setAllocatedAmounts((prev) =>
      Object.keys(prev).length > 0 ? prev : { [first.id]: first.balanceDue.toFixed(2) }
    );
    setAmountReceived((prev) => prev || first.balanceDue.toFixed(2));
  }, [isOpen, customerId, customers]);

  // When customer changes, load that customer's open invoices
  const handleCustomerChange = (newCustId: string) => {
    setCustomerId(newCustId);
    setSelectedInvoices({});
    setAllocatedAmounts({});
    setAmountReceived('');
    if (newCustId) void loadCustomerInvoices(newCustId);
  };

  // Toggle invoice checkbox
  const handleToggleInvoice = (invId: string, balanceDue: number) => {
    const isNowSelected = !selectedInvoices[invId];
    setSelectedInvoices((prev) => ({ ...prev, [invId]: isNowSelected }));

    if (isNowSelected) {
      setAllocatedAmounts((prev) => ({
        ...prev,
        [invId]: prev[invId] || balanceDue.toFixed(2),
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
    const totalRec = round2(parseFloat(amountReceived) || 0);
    if (totalRec <= 0) return;

    let remainingToApply = totalRec;
    const newAllocated: Record<string, string> = {};
    const newSelected: Record<string, boolean> = {};

    for (const inv of outstandingInvoices) {
      if (remainingToApply <= 0.004) break;
      const applyThis = round2(Math.min(remainingToApply, inv.balanceDue));
      if (applyThis <= 0) continue;
      newAllocated[inv.id] = applyThis.toFixed(2);
      newSelected[inv.id] = true;
      remainingToApply = round2(remainingToApply - applyThis);
    }

    setSelectedInvoices(newSelected);
    setAllocatedAmounts(newAllocated);
  };

  // Calculate totals (rounded to paise so float drift never reaches a comparison)
  const numReceived = round2(parseFloat(amountReceived) || 0);
  const totalApplied = paymentType === 'invoice_payment'
    ? round2(
        Object.entries(allocatedAmounts).reduce((sum, [invId, amountStr]) => {
          if (selectedInvoices[invId]) {
            return sum + (parseFloat(amountStr) || 0);
          }
          return sum;
        }, 0)
      )
    : 0;

  const unappliedBalance = round2(Math.max(0, numReceived - totalApplied));

  const validate = () => {
    const errs: Record<string, string> = {};
    if (!customerId || !customers.some((c) => c.id === customerId)) {
      errs.customerId = 'Please select a valid customer from the list';
    }
    const amountError = validatePositiveMoney(amountReceived, 'Amount received', { required: true });
    if (amountError) {
      errs.amountReceived = amountError;
    }
    if (!paymentDate) {
      errs.paymentDate = 'Payment date is required';
    } else {
      const dateErr = validateDateNotFuture(paymentDate, 'Payment date');
      if (dateErr) {
        errs.paymentDate = dateErr;
      }
    }
    if (!paymentMethod) errs.paymentMethod = 'Payment method is required';

    if (paymentType === 'invoice_payment') {
      if (totalApplied - numReceived > CENT_TOLERANCE) {
        errs.allocation = `Total applied (₹${totalApplied.toLocaleString('en-IN')}) cannot exceed amount received (₹${numReceived.toLocaleString('en-IN')})`;
      }

      // Check per-invoice limits
      for (const [invId, amtStr] of Object.entries(allocatedAmounts)) {
        if (selectedInvoices[invId]) {
          const val = parseFloat(amtStr) || 0;
          const inv = outstandingInvoices.find((i) => i.id === invId);
          if (inv && val - inv.balanceDue > CENT_TOLERANCE) {
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
              appliedAmount: appliedVal,
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
            {/* Customer Searchable Combobox */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Customer <span className="text-rose-500">*</span>
              </label>
              <div className="relative" ref={customerDropdownRef}>
                <div
                  onClick={() => setIsCustomerDropdownOpen((prev) => !prev)}
                  className={`flex items-center justify-between w-full px-3 py-2 text-xs bg-white border rounded-lg cursor-pointer transition-colors ${
                    errors.customerId
                      ? 'border-rose-400 ring-1 ring-rose-300'
                      : isCustomerDropdownOpen
                      ? 'border-brand-500 ring-1 ring-brand-500'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <div className="flex items-center gap-2 overflow-hidden flex-1 mr-2">
                    <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <input
                      type="text"
                      value={isCustomerDropdownOpen ? customerSearchQuery : (selectedCustomer ? selectedCustomer.name : '')}
                      onChange={(e) => {
                        setCustomerSearchQuery(e.target.value);
                        if (!isCustomerDropdownOpen) setIsCustomerDropdownOpen(true);
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!isCustomerDropdownOpen) setIsCustomerDropdownOpen(true);
                      }}
                      placeholder={selectedCustomer ? selectedCustomer.name : 'Search customer...'}
                      className="w-full bg-transparent text-slate-900 placeholder:text-slate-400 focus:outline-none text-xs truncate"
                    />
                  </div>
                  <div className="flex items-center gap-1 shrink-0 text-slate-400">
                    <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isCustomerDropdownOpen ? 'rotate-180 text-brand-600' : ''}`} />
                  </div>
                </div>

                {/* Dropdown Options */}
                {isCustomerDropdownOpen && (
                  <div className="absolute left-0 right-0 top-full mt-1 bg-white border border-slate-200 rounded-xl shadow-xl z-50 overflow-hidden max-h-56 flex flex-col animate-in fade-in zoom-in-95 duration-100">
                    <div className="overflow-y-auto flex-1 divide-y divide-slate-100">
                      {customers.length === 0 ? (
                        <div className="p-3.5 text-center">
                          <p className="text-xs text-slate-500 mb-2">No customers found. Please create a customer first.</p>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setIsCustomerDropdownOpen(false);
                              setNewCustomerName(customerSearchQuery);
                              setIsCreateCustomerModalOpen(true);
                            }}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-brand-600 bg-brand-50 hover:bg-brand-100 rounded-lg transition-colors"
                          >
                            <UserPlus className="w-3.5 h-3.5" />
                            <span>+ Create New Customer</span>
                          </button>
                        </div>
                      ) : filteredCustomers.length === 0 ? (
                        <div className="p-3.5 text-center">
                          <p className="text-xs text-slate-500 mb-2">No matching customer found</p>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setIsCustomerDropdownOpen(false);
                              setNewCustomerName(customerSearchQuery);
                              setIsCreateCustomerModalOpen(true);
                            }}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-brand-600 bg-brand-50 hover:bg-brand-100 rounded-lg transition-colors"
                          >
                            <UserPlus className="w-3.5 h-3.5" />
                            <span>+ Create New Customer</span>
                          </button>
                        </div>
                      ) : (
                        filteredCustomers.map((c) => {
                          const isSelected = c.id === customerId;
                          return (
                            <button
                              key={c.id}
                              type="button"
                              onClick={() => {
                                handleCustomerChange(c.id);
                                setCustomerSearchQuery('');
                                setIsCustomerDropdownOpen(false);
                              }}
                              className={`w-full text-left px-3.5 py-2.5 flex items-center justify-between text-xs hover:bg-slate-50 transition-colors ${
                                isSelected ? 'bg-brand-50/60 font-medium text-brand-700' : 'text-slate-800'
                              }`}
                            >
                              <div>
                                <div className="font-medium text-slate-900">{c.name}</div>
                                {c.outstandingInvoices.length > 0 ? (
                                  <div className="text-[11px] text-amber-600">
                                    {c.outstandingInvoices.length} outstanding invoice{c.outstandingInvoices.length > 1 ? 's' : ''}
                                  </div>
                                ) : (
                                  <div className="text-[11px] text-slate-400">No open invoices</div>
                                )}
                              </div>
                            </button>
                          );
                        })
                      )}
                    </div>

                    {customers.length > 0 && (
                      <div className="p-2 border-t border-slate-100 bg-slate-50/70 flex justify-between items-center px-3">
                        <span className="text-[11px] text-slate-400">
                          {filteredCustomers.length} of {customers.length} customer{customers.length > 1 ? 's' : ''}
                        </span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setIsCustomerDropdownOpen(false);
                            setNewCustomerName(customerSearchQuery);
                            setIsCreateCustomerModalOpen(true);
                          }}
                          className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand-600 hover:text-brand-700"
                        >
                          <UserPlus className="w-3 h-3" />
                          <span>+ Create New Customer</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
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
                max={new Date().toISOString().split('T')[0]}
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
                              {formatMoney(inv.totalAmount)}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono font-semibold text-slate-900">
                              {formatMoney(inv.balanceDue)}
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
                      {formatMoney(numReceived)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[11px] text-slate-500 block">Amount Applied</span>
                    <span className="font-bold text-emerald-700 font-mono text-sm">
                      {formatMoney(totalApplied)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[11px] text-slate-500 block">Unapplied Balance</span>
                    <span className="font-bold text-blue-700 font-mono text-sm">
                      {formatMoney(unappliedBalance)}
                    </span>
                  </div>
                </div>

                {unappliedBalance > 0 && (
                  <div className="flex items-center gap-1.5 text-[11px] text-blue-700 bg-blue-50/70 p-2 rounded-lg border border-blue-100">
                    <Info className="w-3.5 h-3.5 shrink-0" />
                    <span>
                      The unapplied balance of <strong className="font-mono">{formatMoney(unappliedBalance)}</strong> will be credited to {selectedCustomer?.name} as an available advance credit for future invoices.
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
                The full payment of <strong className="font-mono font-bold text-slate-900">{formatMoney(numReceived)}</strong> will be recorded as unapplied customer credit. It can be applied against subsequent billing cycles or milestone invoices.
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

      {/* Create New Customer Modal */}
      {isCreateCustomerModalOpen && (
        <div className="fixed inset-0 z-60 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl border border-slate-200 w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center shrink-0">
                  <UserPlus className="w-4 h-4" />
                </div>
                <h4 className="text-sm font-bold text-slate-900">Create New Customer</h4>
              </div>
              <button
                type="button"
                onClick={() => setIsCreateCustomerModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateCustomerSubmit} className="p-5 space-y-4">
              {newCustomerError && (
                <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-500" />
                  <span>{newCustomerError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Customer / Company Name <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={newCustomerName}
                  onChange={(e) => {
                    setNewCustomerName(e.target.value);
                    setNewCustomerError('');
                  }}
                  placeholder="e.g. Acme Technologies"
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Billing Email <span className="text-slate-400 font-normal">(Optional)</span>
                </label>
                <input
                  type="email"
                  value={newCustomerEmail}
                  onChange={(e) => setNewCustomerEmail(e.target.value)}
                  placeholder="billing@acme.com"
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Phone Number <span className="text-slate-400 font-normal">(Optional)</span>
                </label>
                <input
                  type="tel"
                  value={newCustomerPhone}
                  onChange={(e) => setNewCustomerPhone(e.target.value)}
                  placeholder="+91 98765 43210"
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsCreateCustomerModalOpen(false)}
                  className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingCustomer || !newCustomerName.trim()}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 rounded-lg shadow-2xs transition-colors"
                >
                  {creatingCustomer ? 'Creating...' : 'Save & Select'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
