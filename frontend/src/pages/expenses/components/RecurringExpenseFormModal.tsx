import { useState, useEffect, FormEvent } from 'react';
import {
  RecurringExpense,
  ExpenseCategory,
  RecurringExpenseFrequency,
  InvoiceTreatment,
  PaymentMethod,
} from '../types';
import { X, CheckCircle, Repeat } from 'lucide-react';
import { CustomerCombobox } from '../../../components/common/CustomerCombobox';
import { useAuth } from '../../../hooks/useAuth';
import { useCustomerProjects } from '../useCustomerProjects';
import { ModalShell } from '../../../components/common/Modal';
import { validateSensibleName, validatePositiveMoney, validateNonNegativeMoney, validateDateNotBefore, parseStrictNumber } from '../../../utils/validation';
import { todayIso, toIsoDate } from '../../../utils/format';

interface RecurringExpenseFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: Omit<RecurringExpense, 'id' | 'createdAt'>) => void;
  editingExpense?: RecurringExpense | null;
}

const CATEGORIES: ExpenseCategory[] = [
  'Software',
  'Cloud Services',
  'Utilities',
  'Office Supplies',
  'Professional Services',
  'Travel',
  'Meals',
  'Equipment',
  'Advertising',
  'Other',
];

const FREQUENCIES: { value: RecurringExpenseFrequency; label: string }[] = [
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'yearly', label: 'Yearly' },
];

export function RecurringExpenseFormModal({
  isOpen,
  onClose,
  onSave,
  editingExpense,
}: RecurringExpenseFormModalProps) {
  const [name, setName] = useState('');
  const [category, setCategory] = useState<ExpenseCategory>('Software');
  const [description, setDescription] = useState('');
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('INR');

  // Schedule
  const [frequency, setFrequency] = useState<RecurringExpenseFrequency>('monthly');
  const [startDate, setStartDate] = useState(() => todayIso());
  const [neverEnds, setNeverEnds] = useState(true);
  const [endDate, setEndDate] = useState('');

  const { user } = useAuth();
  const defaultPaidBy = user?.full_name || '';

  // Billing
  const [billable, setBillable] = useState(false);
  const [customerId, setCustomerId] = useState('');
  const [customer, setCustomer] = useState('');
  const [projectId, setProjectId] = useState('');
  const [project, setProject] = useState('');
  const [billableAmount, setBillableAmount] = useState('');
  const [invoiceTreatment, setInvoiceTreatment] = useState<InvoiceTreatment>('add_to_next_invoice');
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('Corporate Card');
  const [paidBy, setPaidBy] = useState(defaultPaidBy);

  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (editingExpense) {
      setName(editingExpense.name);
      setCategory(editingExpense.category);
      setDescription(editingExpense.description || '');
      setAmount(String(editingExpense.amount));
      setCurrency(editingExpense.currency || 'INR');
      setFrequency(editingExpense.frequency);
      setStartDate(editingExpense.startDate);
      setNeverEnds(editingExpense.neverEnds);
      setEndDate(editingExpense.endDate || '');
      setBillable(editingExpense.billable);
      setCustomerId(editingExpense.customerId || '');
      setCustomer(editingExpense.customer || '');
      setProjectId(editingExpense.projectId || '');
      setProject(editingExpense.project || '');
      setBillableAmount(editingExpense.billableAmount ? String(editingExpense.billableAmount) : String(editingExpense.amount));
      setInvoiceTreatment(editingExpense.invoiceTreatment || 'add_to_next_invoice');
      setPaymentMethod(editingExpense.paymentMethod);
      setPaidBy(editingExpense.paidBy);
    } else {
      setName('');
      setCategory('Software');
      setDescription('');
      setAmount('');
      setCurrency('INR');
      setFrequency('monthly');
      setStartDate(todayIso());
      setNeverEnds(true);
      setEndDate('');
      setBillable(false);
      setCustomerId('');
      setCustomer('');
      setProjectId('');
      setProject('');
      setBillableAmount('');
      setInvoiceTreatment('add_to_next_invoice');
      setPaymentMethod('Corporate Card');
      setPaidBy(defaultPaidBy);
    }
    setErrors({});
  }, [editingExpense, isOpen, defaultPaidBy]);

  const { projects: availableProjects, loading: projectsLoading } = useCustomerProjects(customerId || undefined);

  const calculateNextRun = (start: string, freq: RecurringExpenseFrequency): string => {
    try {
      // Parse YYYY-MM-DD as a local calendar date (new Date(str) is UTC midnight).
      const [y, m, day] = start.split('-').map(Number);
      const d = new Date(y, m - 1, day);
      if (Number.isNaN(d.getTime())) return start;
      if (freq === 'weekly') d.setDate(d.getDate() + 7);
      else if (freq === 'monthly') d.setMonth(d.getMonth() + 1);
      else if (freq === 'quarterly') d.setMonth(d.getMonth() + 3);
      else if (freq === 'yearly') d.setFullYear(d.getFullYear() + 1);
      return toIsoDate(d);
    } catch {
      return start;
    }
  };

  const validate = () => {
    const errs: Record<string, string> = {};
    const nameError = validateSensibleName(name, 'Profile name');
    if (nameError) errs.name = nameError;
    const amountError = validatePositiveMoney(amount, 'Amount');
    if (amountError) errs.amount = amountError;
    if (!startDate) errs.startDate = 'Start date is required';
    if (!neverEnds && !endDate) {
      errs.endDate = 'Please specify end date or choose Never Ends';
    }
    if (!neverEnds && startDate && endDate) {
      const dateError = validateDateNotBefore(endDate, startDate, 'End date', 'start date');
      if (dateError) errs.endDate = dateError;
    }
    if (billable) {
      if (!customerId) {
        errs.customer = 'Please select a customer for billable expense';
      }
      if (billableAmount.trim() !== '') {
        const billableAmountError = validateNonNegativeMoney(billableAmount, 'Billable amount');
        if (billableAmountError) errs.billableAmount = billableAmountError;
      }
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    const numAmount = parseStrictNumber(amount) as number;
    const numBillable = billable
      ? ((parseStrictNumber(billableAmount) ?? parseStrictNumber(amount)) as number)
      : undefined;
    const nextRun = calculateNextRun(startDate, frequency);

    onSave({
      name: name.trim(),
      category,
      description: description.trim() || undefined,
      amount: numAmount,
      currency,
      frequency,
      startDate,
      endDate: neverEnds ? undefined : endDate,
      neverEnds,
      nextRun,
      billable,
      customerId: billable ? customerId : '',
      customer: billable ? customer : '',
      projectId: billable ? projectId : '',
      project: billable ? project : '',
      billableAmount: numBillable,
      invoiceTreatment: billable ? invoiceTreatment : undefined,
      paymentMethod,
      paidBy: paidBy.trim() || defaultPaidBy || 'Self',
      status: editingExpense ? editingExpense.status : 'active',
      lastRun: editingExpense?.lastRun,
    });

    onClose();
  };

  if (!isOpen) return null;

  return (
    <ModalShell onClose={onClose} labelledBy="recurring-expense-modal-title" className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-xl overflow-hidden animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between shrink-0 bg-slate-50/50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-sky-50 text-sky-600 flex items-center justify-center shrink-0">
              <Repeat className="w-4 h-4" />
            </div>
            <div>
              <h3 id="recurring-expense-modal-title" className="text-base font-bold text-slate-900">
                {editingExpense ? 'Edit Recurring Profile' : 'New Recurring Expense'}
              </h3>
              <p className="text-xs text-slate-500">
                Configure auto-recurring costs, frequency cadence, and billing allocation.
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

        {/* Scrollable Form Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Basic Information */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-600" />
              Basic Information
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <div className="sm:col-span-2">
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Expense Profile Name <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. AWS Cloud Hosting, Leased Fiber Internet"
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                {errors.name && <p className="text-[11px] text-rose-500 mt-1">{errors.name}</p>}
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Category <span className="text-rose-500">*</span>
                </label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value as ExpenseCategory)}
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Amount (INR) <span className="text-rose-500">*</span>
                </label>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={amount}
                  onChange={(e) => {
                    setAmount(e.target.value);
                    if (!editingExpense || !billableAmount) setBillableAmount(e.target.value);
                  }}
                  placeholder="0.00"
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500 font-mono"
                />
                {errors.amount && <p className="text-[11px] text-rose-500 mt-1">{errors.amount}</p>}
              </div>
            </div>
          </div>

          {/* Schedule Cadence */}
          <div className="pt-4 border-t border-slate-100 space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-600" />
              Schedule Cadence
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Frequency <span className="text-rose-500">*</span>
                </label>
                <select
                  value={frequency}
                  onChange={(e) => setFrequency(e.target.value as RecurringExpenseFrequency)}
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  {FREQUENCIES.map((f) => (
                    <option key={f.value} value={f.value}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Start Date <span className="text-rose-500">*</span>
                </label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                {errors.startDate && (
                  <p className="text-[11px] text-rose-500 mt-1">{errors.startDate}</p>
                )}
              </div>

              <div className="sm:col-span-2">
                <div className="flex items-center gap-4 mb-2">
                  <label className="inline-flex items-center gap-2 cursor-pointer text-xs font-semibold text-slate-700">
                    <input
                      type="checkbox"
                      checked={neverEnds}
                      onChange={(e) => setNeverEnds(e.target.checked)}
                      className="w-4 h-4 rounded text-brand-600 border-slate-300 focus:ring-brand-500"
                    />
                    <span>Never Ends (Ongoing Subscription)</span>
                  </label>
                </div>

                {!neverEnds && (
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      End Date <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                    />
                    {errors.endDate && (
                      <p className="text-[11px] text-rose-500 mt-1">{errors.endDate}</p>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Billing & Allocation */}
          <div className="pt-4 border-t border-slate-100 space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                Customer Billing Allocation
              </h4>

              <label className="inline-flex items-center gap-2 cursor-pointer select-none">
                <span className="text-xs font-semibold text-slate-700">Billable:</span>
                <input
                  type="checkbox"
                  checked={billable}
                  onChange={(e) => setBillable(e.target.checked)}
                  className="w-4 h-4 rounded text-brand-600 border-slate-300 focus:ring-brand-500"
                />
                <span className={`text-xs font-bold ${billable ? 'text-emerald-700' : 'text-slate-400'}`}>
                  {billable ? 'Yes' : 'No'}
                </span>
              </label>
            </div>

            {billable && (
              <div className="p-3 bg-emerald-50/50 rounded-xl border border-emerald-100/80 space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <CustomerCombobox
                      label="Customer"
                      required
                      value={customerId}
                      error={errors.customer}
                      onChange={(id, cust) => {
                        setCustomerId(id);
                        setCustomer(cust?.display_name || '');
                        setProjectId('');
                        setProject('');
                      }}
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Project
                    </label>
                    <select
                      value={projectId}
                      disabled={!customerId}
                      onChange={(e) => {
                        const selected = availableProjects.find((p) => p.id === e.target.value);
                        setProjectId(selected?.id || '');
                        setProject(selected?.name || '');
                      }}
                      className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:bg-slate-50"
                    >
                      <option value="">
                        {!customerId ? 'Select a customer first' : projectsLoading ? 'Loading projects…' : 'No project'}
                      </option>
                      {availableProjects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            )}
          </div>
        </form>

        {/* Footer Actions */}
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
            className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-white bg-brand-600 hover:bg-brand-700 rounded-lg shadow-2xs transition-colors font-semibold"
          >
            <CheckCircle className="w-3.5 h-3.5" />
            <span>{editingExpense ? 'Save Changes' : 'Save Recurring Profile'}</span>
          </button>
        </div>
    </ModalShell>
  );
}
