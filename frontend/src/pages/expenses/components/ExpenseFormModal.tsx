import { useState, useEffect, ChangeEvent, FormEvent } from 'react';
import { Expense, ExpenseCategory, PaymentMethod, InvoiceTreatment, ExpenseReceipt } from '../types';
import { X, UploadCloud, Trash2, FileText, CheckCircle } from 'lucide-react';
import { validateSensibleName, validatePositiveMoney, validateNonNegativeMoney, parseStrictNumber } from '../../../utils/validation';
import { CustomerCombobox } from '../../../components/common/CustomerCombobox';
import { useAuth } from '../../../hooks/useAuth';
import { useCustomerProjects } from '../useCustomerProjects';

const MAX_RECEIPT_BYTES = 10 * 1024 * 1024;
const RECEIPT_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.webp'];

interface ExpenseFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (expenseData: Omit<Expense, 'id' | 'createdAt'>) => void;
  editingExpense?: Expense | null;
}

const CATEGORIES: ExpenseCategory[] = [
  'Travel',
  'Meals',
  'Office Supplies',
  'Software',
  'Cloud Services',
  'Advertising',
  'Utilities',
  'Equipment',
  'Professional Services',
  'Other',
];

const PAYMENT_METHODS: PaymentMethod[] = [
  'Corporate Card',
  'Bank Transfer',
  'Personal Card',
  'UPI / Net Banking',
  'Cash',
  'Other',
];

export function ExpenseFormModal({
  isOpen,
  onClose,
  onSave,
  editingExpense,
}: ExpenseFormModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [date, setDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [category, setCategory] = useState<ExpenseCategory>('Software');
  const [amount, setAmount] = useState<string>('');
  const [currency, setCurrency] = useState('INR');

  const { user } = useAuth();
  const defaultPaidBy = user?.full_name || '';

  // Billing fields
  const [billable, setBillable] = useState(false);
  const [customerId, setCustomerId] = useState('');
  const [customer, setCustomer] = useState('');
  const [projectId, setProjectId] = useState('');
  const [project, setProject] = useState('');
  const [billableAmount, setBillableAmount] = useState<string>('');
  const [taxRate, setTaxRate] = useState<number>(18);
  const [invoiceTreatment, setInvoiceTreatment] = useState<InvoiceTreatment>('add_to_next_invoice');

  // Payment fields
  const [paidBy, setPaidBy] = useState(defaultPaidBy);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('Corporate Card');
  const [notes, setNotes] = useState('');

  // Receipt: the stored one (from the server) and/or a newly chosen file to upload on save.
  const [receipt, setReceipt] = useState<ExpenseReceipt | undefined>(undefined);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);

  // Errors
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (editingExpense) {
      setName(editingExpense.name);
      setDescription(editingExpense.description || '');
      setDate(editingExpense.date);
      setCategory(editingExpense.category);
      setAmount(String(editingExpense.amount));
      setCurrency(editingExpense.currency || 'INR');
      setBillable(editingExpense.billable);
      setCustomerId(editingExpense.customerId || '');
      setCustomer(editingExpense.customer || '');
      setProjectId(editingExpense.projectId || '');
      setProject(editingExpense.project || '');
      setBillableAmount(editingExpense.billableAmount ? String(editingExpense.billableAmount) : String(editingExpense.amount));
      setTaxRate(editingExpense.taxRate ?? 18);
      setInvoiceTreatment(editingExpense.invoiceTreatment || 'add_to_next_invoice');
      setPaidBy(editingExpense.paidBy);
      setPaymentMethod(editingExpense.paymentMethod);
      setNotes(editingExpense.notes || '');
      setReceipt(editingExpense.receipt);
      setReceiptFile(null);
    } else {
      setName('');
      setDescription('');
      setDate(new Date().toISOString().split('T')[0]);
      setCategory('Software');
      setAmount('');
      setCurrency('INR');
      setBillable(false);
      setCustomerId('');
      setCustomer('');
      setProjectId('');
      setProject('');
      setBillableAmount('');
      setTaxRate(18);
      setInvoiceTreatment('add_to_next_invoice');
      setPaidBy(defaultPaidBy);
      setPaymentMethod('Corporate Card');
      setNotes('');
      setReceipt(undefined);
      setReceiptFile(null);
    }
    setErrors({});
  }, [editingExpense, isOpen, defaultPaidBy]);

  // Update default billableAmount when expense amount changes
  const handleAmountChange = (val: string) => {
    setAmount(val);
    if (!editingExpense || !billableAmount) {
      setBillableAmount(val);
    }
  };

  // Real projects of the selected customer
  const { projects: availableProjects, loading: projectsLoading } = useCustomerProjects(customerId || undefined);

  const handleFileUpload = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (!RECEIPT_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      setErrors((prev) => ({ ...prev, receipt: 'Receipts must be PDF, PNG, JPG or WEBP files.' }));
      return;
    }
    if (file.size > MAX_RECEIPT_BYTES) {
      setErrors((prev) => ({ ...prev, receipt: 'Receipt exceeds the 10 MB limit.' }));
      return;
    }
    setErrors((prev) => {
      const { receipt: _omit, ...rest } = prev;
      return rest;
    });
    setReceiptFile(file);
    setReceipt({
      fileName: file.name,
      fileSize: `${(file.size / 1024).toFixed(0)} KB`,
      uploadDate: new Date().toISOString().split('T')[0],
      fileType: file.type || 'application/octet-stream',
    });
  };

  const validate = () => {
    const newErrors: Record<string, string> = {};
    const nameError = validateSensibleName(name, 'Expense name');
    if (nameError) newErrors.name = nameError;
    if (!date) newErrors.date = 'Expense date is required';
    if (!category) newErrors.category = 'Category is required';
    const amountError = validatePositiveMoney(amount, 'Amount');
    if (amountError) newErrors.amount = amountError;
    if (!currency) newErrors.currency = 'Currency is required';

    if (billable) {
      if (!customerId) {
        newErrors.customer = 'Please select the customer to bill this expense to';
      }
      const billableAmountError = validateNonNegativeMoney(billableAmount, 'Billable amount', { required: true });
      if (billableAmountError) newErrors.billableAmount = billableAmountError;
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    const numAmount = parseStrictNumber(amount) as number;
    const numBillable = billable ? (parseStrictNumber(billableAmount) as number) : undefined;

    onSave({
      name: name.trim(),
      description: description.trim() || undefined,
      date,
      category,
      amount: numAmount,
      currency,
      billable,
      customerId: billable ? customerId : '',
      customer: billable ? customer : '',
      projectId: billable ? projectId : '',
      project: billable ? project : '',
      billableAmount: numBillable,
      taxRate: billable ? taxRate : undefined,
      invoiceTreatment: billable ? invoiceTreatment : undefined,
      paymentMethod,
      paidBy: paidBy.trim() || defaultPaidBy || 'Self',
      status: editingExpense ? editingExpense.status : billable ? 'billable' : 'recorded',
      receipt,
      receiptFile,
      notes: notes.trim() || undefined,
    });

    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between shrink-0 bg-slate-50/50">
          <div>
            <h3 className="text-base font-bold text-slate-900">
              {editingExpense ? 'Edit Expense' : 'Record Expense'}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Enter expense details, customer rebilling allocation, and receipt.
            </p>
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
          {/* Section 1: Basic Information */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-600" />
              Basic Information
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              {/* Expense Name */}
              <div className="sm:col-span-2">
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Expense Name / Description <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. AWS Cloud Hosting, Flight Tickets, Office Internet"
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                {errors.name && <p className="text-[11px] text-rose-500 mt-1">{errors.name}</p>}
              </div>

              {/* Expense Date */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Expense Date <span className="text-rose-500">*</span>
                </label>
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                {errors.date && <p className="text-[11px] text-rose-500 mt-1">{errors.date}</p>}
              </div>

              {/* Category */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Category <span className="text-rose-500">*</span>
                </label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value as ExpenseCategory)}
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </div>

              {/* Amount */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Amount <span className="text-rose-500">*</span>
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-slate-400 font-semibold">
                    {currency === 'INR' ? '₹' : currency}
                  </span>
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={amount}
                    onChange={(e) => handleAmountChange(e.target.value)}
                    placeholder="0.00"
                    className="w-full pl-8 pr-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500 font-mono"
                  />
                </div>
                {errors.amount && <p className="text-[11px] text-rose-500 mt-1">{errors.amount}</p>}
              </div>

              {/* Currency */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Currency <span className="text-rose-500">*</span>
                </label>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  <option value="INR">INR (₹) - Indian Rupee</option>
                  <option value="USD">USD ($) - US Dollar</option>
                  <option value="EUR">EUR (€) - Euro</option>
                </select>
              </div>
            </div>
          </div>

          {/* Section 2: Billing Information */}
          <div className="pt-4 border-t border-slate-100 space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                Billing & Re-billing Allocation
              </h4>

              {/* Billable Toggle */}
              <label className="inline-flex items-center gap-2 cursor-pointer select-none">
                <span className="text-xs font-semibold text-slate-700">Billable to Customer:</span>
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
              <div className="p-3.5 bg-emerald-50/50 rounded-xl border border-emerald-100/80 space-y-3 animate-in fade-in">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {/* Customer */}
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

                  {/* Project */}
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
                    {errors.project && (
                      <p className="text-[11px] text-rose-500 mt-1">{errors.project}</p>
                    )}
                  </div>

                  {/* Billable Amount */}
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Billable Amount (INR) <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={billableAmount}
                      onChange={(e) => setBillableAmount(e.target.value)}
                      placeholder="0.00"
                      className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-emerald-500 font-mono"
                    />
                    {errors.billableAmount && (
                      <p className="text-[11px] text-rose-500 mt-1">{errors.billableAmount}</p>
                    )}
                  </div>

                  {/* Tax Rate */}
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Tax (GST %)
                    </label>
                    <select
                      value={taxRate}
                      onChange={(e) => setTaxRate(Number(e.target.value))}
                      className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    >
                      <option value={0}>0% - Tax Exempt / Nil</option>
                      <option value={5}>5% - Standard Concessional</option>
                      <option value={12}>12% - Standard Services</option>
                      <option value={18}>18% - GST Standard</option>
                      <option value={28}>28% - Highest Rate</option>
                    </select>
                  </div>

                  {/* Invoice Treatment */}
                  <div className="sm:col-span-2">
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Invoice Treatment
                    </label>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      {[
                        { val: 'add_to_next_invoice', label: 'Add to next invoice' },
                        { val: 'add_to_existing_invoice', label: 'Add to existing invoice' },
                        { val: 'keep_billable', label: 'Keep as billable' },
                      ].map((opt) => (
                        <label
                          key={opt.val}
                          className={`flex items-center gap-2 p-2 rounded-lg border text-xs cursor-pointer transition-colors ${
                            invoiceTreatment === opt.val
                              ? 'border-emerald-500 bg-white font-semibold text-emerald-900'
                              : 'border-slate-200 bg-white text-slate-600'
                          }`}
                        >
                          <input
                            type="radio"
                            name="invoiceTreatment"
                            checked={invoiceTreatment === opt.val}
                            onChange={() => setInvoiceTreatment(opt.val as InvoiceTreatment)}
                            className="text-emerald-600 focus:ring-emerald-500"
                          />
                          <span>{opt.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Section 3: Payment Information */}
          <div className="pt-4 border-t border-slate-100 space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
              Payment Information
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              {/* Paid By */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Paid By (Employee / Team)
                </label>
                <input
                  type="text"
                  value={paidBy}
                  onChange={(e) => setPaidBy(e.target.value)}
                  placeholder="e.g. employee name, Operations, Finance"
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </div>

              {/* Payment Method */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Payment Method
                </label>
                <select
                  value={paymentMethod}
                  onChange={(e) => setPaymentMethod(e.target.value as PaymentMethod)}
                  className="w-full px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-1 focus:ring-brand-500"
                >
                  {PAYMENT_METHODS.map((pm) => (
                    <option key={pm} value={pm}>
                      {pm}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Section 4: Receipt Upload (stored privately on the server on save) */}
          <div className="pt-4 border-t border-slate-100 space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-600" />
              Receipt Attachment
            </h4>

            {receipt ? (
              <div className="flex items-center justify-between p-3 bg-slate-50 border border-slate-200 rounded-xl">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-white border border-slate-200 text-brand-600 flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-slate-900 truncate">
                      {receipt.fileName}
                    </p>
                    <p className="text-[11px] text-slate-500">
                      {receipt.fileSize ? `${receipt.fileSize} · ` : ''}
                      {receiptFile ? 'Uploads when you save' : 'Stored receipt'}
                    </p>
                  </div>
                </div>
                {receiptFile ? (
                  <button
                    type="button"
                    onClick={() => {
                      setReceiptFile(null);
                      setReceipt(editingExpense?.receipt);
                    }}
                    className="p-1.5 text-rose-500 hover:text-rose-700 hover:bg-rose-50 rounded-lg transition-colors"
                    title="Discard selected file"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                ) : (
                  <label className="px-2 py-1 text-[11px] font-medium text-brand-700 hover:bg-brand-50 rounded-lg cursor-pointer">
                    Replace
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg,.webp"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                  </label>
                )}
              </div>
            ) : (
              <label className="flex flex-col items-center justify-center p-4 border-2 border-dashed border-slate-200 rounded-xl hover:border-brand-400 hover:bg-slate-50/50 cursor-pointer transition-colors">
                <UploadCloud className="w-6 h-6 text-slate-400 mb-1" />
                <span className="text-xs font-medium text-slate-700">
                  Click to select receipt file (PDF, PNG, JPG, WEBP)
                </span>
                <span className="text-[10px] text-slate-400 mt-0.5">
                  Up to 10 MB. Uploaded privately when you save.
                </span>
                <input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,.webp"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </label>
            )}
            {errors.receipt && <p className="text-[11px] text-rose-500 mt-1">{errors.receipt}</p>}
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
            <span>{editingExpense ? 'Save Changes' : 'Save Expense'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
