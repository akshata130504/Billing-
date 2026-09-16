import { apiClient, cleanParams } from './apiClient';
import type { Expense, RecurringExpense } from '../pages/expenses/types';

export interface ExpenseListParams {
  search?: string;
  status?: string;
  customer_id?: string;
  project_id?: string;
  category?: string;
  billable?: boolean;
  sort_by?: string;
}

export interface ExpenseSummaryKPIs {
  total: number;
  billable: number;
  nonBillable: number;
  pending: number;
}

export interface RecurringSummaryKPIs {
  activeProfiles: number;
  monthlyRecurring: number;
  billableRecurring: number;
  nextRun: string;
}

export const expenseService = {
  list: async (params?: ExpenseListParams): Promise<Expense[]> => {
    const { data } = await apiClient.get<any[]>('/expenses', {
      params: cleanParams(params),
    });
    return data.map((e) => ({
      id: e.id,
      name: e.name,
      description: e.description || '',
      date: e.date,
      category: e.category,
      amount: Number(e.amount) || 0,
      currency: e.currency || 'INR',
      billable: Boolean(e.billable),
      customer: e.customer_name || e.customer || '',
      project: e.project_name || e.project || '',
      projectId: e.project_id || '',
      billableAmount: e.billable_amount ? Number(e.billable_amount) : undefined,
      taxRate: e.tax_rate ? Number(e.tax_rate) : undefined,
      invoiceTreatment: e.invoice_treatment || undefined,
      invoiceId: e.invoice_id || undefined,
      paymentMethod: e.payment_method || 'Cash',
      paidBy: e.paid_by || 'Self',
      status: e.status,
      receipt: e.receipt_file_name
        ? {
            fileName: e.receipt_file_name,
            fileSize: e.receipt_file_size,
            fileType: e.receipt_file_type,
          }
        : undefined,
      notes: e.notes || '',
      createdAt: e.created_at,
    }));
  },

  summary: async (): Promise<ExpenseSummaryKPIs> => {
    const { data } = await apiClient.get<any>('/expenses/summary');
    return {
      total: Number(data.total) || 0,
      billable: Number(data.billable) || 0,
      nonBillable: Number(data.non_billable) || 0,
      pending: Number(data.pending) || 0,
    };
  },

  get: async (id: string): Promise<Expense> => {
    const { data } = await apiClient.get<any>(`/expenses/${id}`);
    return {
      id: data.id,
      name: data.name,
      description: data.description || '',
      date: data.date,
      category: data.category,
      amount: Number(data.amount) || 0,
      currency: data.currency || 'INR',
      billable: Boolean(data.billable),
      customer: data.customer_name || data.customer || '',
      project: data.project_name || data.project || '',
      projectId: data.project_id || '',
      billableAmount: data.billable_amount ? Number(data.billable_amount) : undefined,
      taxRate: data.tax_rate ? Number(data.tax_rate) : undefined,
      invoiceTreatment: data.invoice_treatment || undefined,
      invoiceId: data.invoice_id || undefined,
      paymentMethod: data.payment_method || 'Cash',
      paidBy: data.paid_by || 'Self',
      status: data.status,
      receipt: data.receipt_file_name
        ? {
            fileName: data.receipt_file_name,
            fileSize: data.receipt_file_size,
            fileType: data.receipt_file_type,
          }
        : undefined,
      notes: data.notes || '',
      createdAt: data.created_at,
    };
  },

  create: async (body: any): Promise<Expense> => {
    const payload = {
      name: body.name,
      description: body.description,
      date: body.date,
      category: body.category,
      amount: body.amount,
      currency: body.currency || 'INR',
      billable: body.billable,
      customer_name: body.customer,
      project_name: body.project,
      project_id: body.projectId,
      billable_amount: body.billableAmount,
      tax_rate: body.taxRate,
      invoice_treatment: body.invoiceTreatment,
      payment_method: body.paymentMethod || 'Cash',
      paid_by: body.paidBy || 'Self',
      status: body.status || 'recorded',
      receipt_file_name: body.receipt?.fileName,
      receipt_file_size: body.receipt?.fileSize,
      receipt_file_type: body.receipt?.fileType,
      notes: body.notes,
    };
    const { data } = await apiClient.post<any>('/expenses', payload);
    return {
      id: data.id,
      name: data.name,
      description: data.description || '',
      date: data.date,
      category: data.category,
      amount: Number(data.amount) || 0,
      currency: data.currency || 'INR',
      billable: Boolean(data.billable),
      customer: data.customer_name || data.customer || '',
      project: data.project_name || data.project || '',
      projectId: data.project_id || '',
      billableAmount: data.billable_amount ? Number(data.billable_amount) : undefined,
      taxRate: data.tax_rate ? Number(data.tax_rate) : undefined,
      invoiceTreatment: data.invoice_treatment || undefined,
      invoiceId: data.invoice_id || undefined,
      paymentMethod: data.payment_method || 'Cash',
      paidBy: data.paid_by || 'Self',
      status: data.status,
      receipt: data.receipt_file_name
        ? {
            fileName: data.receipt_file_name,
            fileSize: data.receipt_file_size,
            fileType: data.receipt_file_type,
          }
        : undefined,
      notes: data.notes || '',
      createdAt: data.created_at,
    };
  },

  update: async (id: string, body: any): Promise<Expense> => {
    const payload: any = {};
    if (body.name !== undefined) payload.name = body.name;
    if (body.description !== undefined) payload.description = body.description;
    if (body.date !== undefined) payload.date = body.date;
    if (body.category !== undefined) payload.category = body.category;
    if (body.amount !== undefined) payload.amount = body.amount;
    if (body.currency !== undefined) payload.currency = body.currency;
    if (body.billable !== undefined) payload.billable = body.billable;
    if (body.customer !== undefined) payload.customer_name = body.customer;
    if (body.project !== undefined) payload.project_name = body.project;
    if (body.projectId !== undefined) payload.project_id = body.projectId;
    if (body.billableAmount !== undefined) payload.billable_amount = body.billableAmount;
    if (body.taxRate !== undefined) payload.tax_rate = body.taxRate;
    if (body.invoiceTreatment !== undefined) payload.invoice_treatment = body.invoiceTreatment;
    if (body.paymentMethod !== undefined) payload.payment_method = body.paymentMethod;
    if (body.paidBy !== undefined) payload.paid_by = body.paidBy;
    if (body.status !== undefined) payload.status = body.status;
    if (body.notes !== undefined) payload.notes = body.notes;

    const { data } = await apiClient.patch<any>(`/expenses/${id}`, payload);
    return {
      id: data.id,
      name: data.name,
      description: data.description || '',
      date: data.date,
      category: data.category,
      amount: Number(data.amount) || 0,
      currency: data.currency || 'INR',
      billable: Boolean(data.billable),
      customer: data.customer_name || data.customer || '',
      project: data.project_name || data.project || '',
      projectId: data.project_id || '',
      billableAmount: data.billable_amount ? Number(data.billable_amount) : undefined,
      taxRate: data.tax_rate ? Number(data.tax_rate) : undefined,
      invoiceTreatment: data.invoice_treatment || undefined,
      invoiceId: data.invoice_id || undefined,
      paymentMethod: data.payment_method || 'Cash',
      paidBy: data.paid_by || 'Self',
      status: data.status,
      receipt: data.receipt_file_name
        ? {
            fileName: data.receipt_file_name,
            fileSize: data.receipt_file_size,
            fileType: data.receipt_file_type,
          }
        : undefined,
      notes: data.notes || '',
      createdAt: data.created_at,
    };
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/expenses/${id}`);
  },

  batchImport: async (items: any[]): Promise<number> => {
    const payload = {
      expenses: items.map((e) => ({
        name: e.name,
        description: e.description,
        date: e.date,
        category: e.category,
        amount: e.amount,
        currency: e.currency || 'INR',
        billable: Boolean(e.billable),
        customer_name: e.customer,
        project_name: e.project,
        project_id: e.projectId,
        billable_amount: e.billableAmount,
        payment_method: e.paymentMethod || 'Cash',
        paid_by: e.paidBy || 'Self',
        status: e.status || 'recorded',
        notes: e.notes,
      })),
    };
    const { data } = await apiClient.post<any>('/expenses/batch', payload);
    return data.imported || 0;
  },

  addToInvoice: async (id: string): Promise<Expense> => {
    const { data } = await apiClient.post<any>(`/expenses/${id}/add-to-invoice`);
    return {
      id: data.id,
      name: data.name,
      description: data.description || '',
      date: data.date,
      category: data.category,
      amount: Number(data.amount) || 0,
      currency: data.currency || 'INR',
      billable: Boolean(data.billable),
      customer: data.customer_name || data.customer || '',
      project: data.project_name || data.project || '',
      projectId: data.project_id || '',
      billableAmount: data.billable_amount ? Number(data.billable_amount) : undefined,
      taxRate: data.tax_rate ? Number(data.tax_rate) : undefined,
      invoiceTreatment: data.invoice_treatment || undefined,
      invoiceId: data.invoice_id || undefined,
      paymentMethod: data.payment_method || 'Cash',
      paidBy: data.paid_by || 'Self',
      status: data.status,
      notes: data.notes || '',
      createdAt: data.created_at,
    };
  },

  // Recurring
  listRecurring: async (): Promise<RecurringExpense[]> => {
    const { data } = await apiClient.get<any[]>('/expenses/recurring');
    return data.map((r) => ({
      id: r.id,
      name: r.name,
      category: r.category,
      description: r.description || '',
      amount: Number(r.amount) || 0,
      currency: r.currency || 'INR',
      frequency: r.frequency,
      startDate: r.start_date,
      endDate: r.end_date || undefined,
      neverEnds: Boolean(r.never_ends),
      nextRun: r.next_run || r.start_date,
      billable: Boolean(r.billable),
      customer: r.customer_name || r.customer || '',
      project: r.project_name || r.project || '',
      projectId: r.project_id || '',
      billableAmount: r.billable_amount ? Number(r.billable_amount) : undefined,
      invoiceTreatment: r.invoice_treatment || undefined,
      paymentMethod: r.payment_method || 'Cash',
      paidBy: r.paid_by || 'Self',
      status: r.status,
      lastRun: r.last_run || undefined,
      createdAt: r.created_at,
    }));
  },

  summaryRecurring: async (): Promise<RecurringSummaryKPIs> => {
    const { data } = await apiClient.get<any>('/expenses/recurring/summary');
    return {
      activeProfiles: Number(data.active_profiles) || 0,
      monthlyRecurring: Number(data.monthly_recurring) || 0,
      billableRecurring: Number(data.billable_recurring) || 0,
      nextRun: data.next_run || '—',
    };
  },

  createRecurring: async (body: any): Promise<RecurringExpense> => {
    const payload = {
      name: body.name,
      category: body.category,
      description: body.description,
      amount: body.amount,
      currency: body.currency || 'INR',
      frequency: body.frequency,
      start_date: body.startDate,
      end_date: body.endDate,
      never_ends: body.neverEnds,
      next_run: body.nextRun || body.startDate,
      billable: body.billable,
      customer_name: body.customer,
      project_name: body.project,
      project_id: body.projectId,
      billable_amount: body.billableAmount,
      invoice_treatment: body.invoiceTreatment,
      payment_method: body.paymentMethod || 'Cash',
      paid_by: body.paidBy || 'Self',
      status: body.status || 'active',
    };
    const { data } = await apiClient.post<any>('/expenses/recurring', payload);
    return {
      id: data.id,
      name: data.name,
      category: data.category,
      description: data.description || '',
      amount: Number(data.amount) || 0,
      currency: data.currency || 'INR',
      frequency: data.frequency,
      startDate: data.start_date,
      endDate: data.end_date || undefined,
      neverEnds: Boolean(data.never_ends),
      nextRun: data.next_run || data.start_date,
      billable: Boolean(data.billable),
      customer: data.customer_name || data.customer || '',
      project: data.project_name || data.project || '',
      projectId: data.project_id || '',
      billableAmount: data.billable_amount ? Number(data.billable_amount) : undefined,
      invoiceTreatment: data.invoice_treatment || undefined,
      paymentMethod: data.payment_method || 'Cash',
      paidBy: data.paid_by || 'Self',
      status: data.status,
      lastRun: data.last_run || undefined,
      createdAt: data.created_at,
    };
  },

  updateRecurring: async (id: string, body: any): Promise<RecurringExpense> => {
    const payload: any = {};
    if (body.name !== undefined) payload.name = body.name;
    if (body.category !== undefined) payload.category = body.category;
    if (body.description !== undefined) payload.description = body.description;
    if (body.amount !== undefined) payload.amount = body.amount;
    if (body.currency !== undefined) payload.currency = body.currency;
    if (body.frequency !== undefined) payload.frequency = body.frequency;
    if (body.startDate !== undefined) payload.start_date = body.startDate;
    if (body.endDate !== undefined) payload.end_date = body.endDate;
    if (body.neverEnds !== undefined) payload.never_ends = body.neverEnds;
    if (body.nextRun !== undefined) payload.next_run = body.nextRun;
    if (body.billable !== undefined) payload.billable = body.billable;
    if (body.customer !== undefined) payload.customer_name = body.customer;
    if (body.project !== undefined) payload.project_name = body.project;
    if (body.projectId !== undefined) payload.project_id = body.projectId;
    if (body.billableAmount !== undefined) payload.billable_amount = body.billableAmount;
    if (body.invoiceTreatment !== undefined) payload.invoice_treatment = body.invoiceTreatment;
    if (body.paymentMethod !== undefined) payload.payment_method = body.paymentMethod;
    if (body.paidBy !== undefined) payload.paid_by = body.paidBy;
    if (body.status !== undefined) payload.status = body.status;

    const { data } = await apiClient.patch<any>(`/expenses/recurring/${id}`, payload);
    return {
      id: data.id,
      name: data.name,
      category: data.category,
      description: data.description || '',
      amount: Number(data.amount) || 0,
      currency: data.currency || 'INR',
      frequency: data.frequency,
      startDate: data.start_date,
      endDate: data.end_date || undefined,
      neverEnds: Boolean(data.never_ends),
      nextRun: data.next_run || data.start_date,
      billable: Boolean(data.billable),
      customer: data.customer_name || data.customer || '',
      project: data.project_name || data.project || '',
      projectId: data.project_id || '',
      billableAmount: data.billable_amount ? Number(data.billable_amount) : undefined,
      invoiceTreatment: data.invoice_treatment || undefined,
      paymentMethod: data.payment_method || 'Cash',
      paidBy: data.paid_by || 'Self',
      status: data.status,
      lastRun: data.last_run || undefined,
      createdAt: data.created_at,
    };
  },

  deleteRecurring: async (id: string): Promise<void> => {
    await apiClient.delete(`/expenses/recurring/${id}`);
  },

  toggleRecurringStatus: async (id: string): Promise<RecurringExpense> => {
    const { data } = await apiClient.post<any>(`/expenses/recurring/${id}/toggle-status`);
    return {
      id: data.id,
      name: data.name,
      category: data.category,
      description: data.description || '',
      amount: Number(data.amount) || 0,
      currency: data.currency || 'INR',
      frequency: data.frequency,
      startDate: data.start_date,
      endDate: data.end_date || undefined,
      neverEnds: Boolean(data.never_ends),
      nextRun: data.next_run || data.start_date,
      billable: Boolean(data.billable),
      customer: data.customer_name || data.customer || '',
      project: data.project_name || data.project || '',
      projectId: data.project_id || '',
      billableAmount: data.billable_amount ? Number(data.billable_amount) : undefined,
      invoiceTreatment: data.invoice_treatment || undefined,
      paymentMethod: data.payment_method || 'Cash',
      paidBy: data.paid_by || 'Self',
      status: data.status,
      lastRun: data.last_run || undefined,
      createdAt: data.created_at,
    };
  },
};
