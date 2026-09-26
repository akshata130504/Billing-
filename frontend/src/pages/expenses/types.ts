/** The canonical category list. Derive the union from it so a value can be
 *  validated at runtime (CSV import) against exactly what the UI offers. */
export const EXPENSE_CATEGORIES = [
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
] as const;

export type ExpenseCategory = (typeof EXPENSE_CATEGORIES)[number];

export type ExpenseStatus =
  | 'draft'
  | 'recorded'
  | 'billable'
  | 'invoiced'
  | 'reimbursed'
  | 'cancelled';

export type InvoiceTreatment =
  | 'add_to_next_invoice'
  | 'add_to_existing_invoice'
  | 'keep_billable';

export const EXPENSE_PAYMENT_METHODS = [
  'Cash',
  'Bank Transfer',
  'Corporate Card',
  'Personal Card',
  'UPI / Net Banking',
  'Other',
] as const;

export type PaymentMethod = (typeof EXPENSE_PAYMENT_METHODS)[number];

export type RecurringExpenseFrequency =
  | 'weekly'
  | 'monthly'
  | 'quarterly'
  | 'yearly';

export type RecurringExpenseStatus =
  | 'active'
  | 'paused'
  | 'ended';

export interface ExpenseReceipt {
  fileName: string;
  fileSize?: string;
  uploadDate?: string;
  fileType?: string;
}

export interface Expense {
  id: string;
  name: string;
  description?: string;
  date: string;
  category: ExpenseCategory;
  amount: number;
  currency: string;
  billable: boolean;
  customerId?: string;
  customer?: string;
  project?: string;
  projectId?: string;
  billableAmount?: number;
  taxRate?: number;
  invoiceTreatment?: InvoiceTreatment;
  invoiceId?: string;
  paymentMethod: PaymentMethod;
  paidBy: string;
  status: ExpenseStatus;
  receipt?: ExpenseReceipt;
  /** True when a receipt file is stored on the server (downloadable). */
  hasReceipt?: boolean;
  /** Transient: a newly chosen receipt to upload after the expense is saved. */
  receiptFile?: File | null;
  notes?: string;
  createdAt: string;
}

export interface RecurringExpense {
  id: string;
  name: string;
  category: ExpenseCategory;
  description?: string;
  amount: number;
  currency: string;
  frequency: RecurringExpenseFrequency;
  startDate: string;
  endDate?: string;
  neverEnds: boolean;
  nextRun: string;
  billable: boolean;
  customerId?: string;
  customer?: string;
  project?: string;
  projectId?: string;
  billableAmount?: number;
  invoiceTreatment?: InvoiceTreatment;
  paymentMethod: PaymentMethod;
  paidBy: string;
  status: RecurringExpenseStatus;
  lastRun?: string;
  createdAt: string;
}

export interface ExpenseFilterState {
  searchQuery: string;
  status: string;
  customer: string;
  project: string;
  category: string;
  billable: string;
  sortBy: 'newest' | 'oldest' | 'amount_high' | 'amount_low';
  viewMode: 'list' | 'card';
}
