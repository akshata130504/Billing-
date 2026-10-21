export type ProjectStatus = 'draft' | 'active' | 'on_hold' | 'completed' | 'cancelled';

export type BillingMethod = 'fixed_price' | 'time_and_material' | 'non_billable';

export type TransactionType = 'Invoice' | 'Payment' | 'Quote' | 'Credit Note';

export interface TimesheetEntry {
  id: string;
  projectId: string;
  employee: string;
  date: string;
  description: string;
  hours: number;
  billable: boolean;
  hourlyRate: number;
  amount: number;
}

export interface ProjectExpense {
  id: string;
  projectId: string;
  date: string;
  title: string;
  category: 'Infrastructure' | 'Software Licenses' | 'Travel & Lodging' | 'Hardware' | 'Consulting' | 'Miscellaneous';
  amount: number;
  billable: boolean;
  status: 'recorded' | 'invoiced' | 'reimbursed';
}

export interface ProjectInvoice {
  id: string;
  projectId: string;
  invoiceNumber: string;
  date: string;
  dueDate: string;
  amount: number;
  status: 'paid' | 'pending' | 'overdue' | 'draft';
}

export interface ProjectPayment {
  id: string;
  projectId: string;
  paymentDate: string;
  reference: string;
  invoiceNumber: string;
  method: 'UPI' | 'NEFT' | 'Credit Card' | 'Net Banking' | 'Wire Transfer';
  amount: number;
  status: 'completed' | 'pending';
}

export interface ProjectTransaction {
  id: string;
  projectId: string;
  type: TransactionType;
  reference: string;
  date: string;
  amount: number;
  status: string;
}

export interface Project {
  id: string;
  name: string;
  /** Linked customer record (who the project bills). */
  customerId?: string;
  customer: string;
  description: string;
  status: ProjectStatus;
  startDate: string;
  endDate: string;
  billingMethod: BillingMethod;
  budget: number;
  billed: number;
  expenses: number;
  projectManager?: string;
  notes?: string;
  timesheets: TimesheetEntry[];
  expenseList: ProjectExpense[];
  invoices: ProjectInvoice[];
  payments: ProjectPayment[];
  transactions: ProjectTransaction[];
}

export interface ProjectFilterState {
  searchQuery: string;
  statusTab: 'all' | 'active' | 'inactive';
  customer: string;
  viewMode: 'list' | 'card';
}
