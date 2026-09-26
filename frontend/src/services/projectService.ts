import { apiClient, cleanParams } from './apiClient';
import type { Project, ProjectInvoice } from '../pages/projects/types';

export interface ProjectListParams {
  search?: string;
  status?: string;
  customer_id?: string;
}

export interface ProjectSummaryKPIs {
  total_projects: number;
  active_projects: number;
  total_budget: number;
  total_billed: number;
  total_expenses: number;
}

export interface ProjectCreateInput {
  name: string;
  customer_id?: string;
  customer_name?: string;
  description?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
  billing_method?: string;
  budget?: number;
  project_manager?: string;
  notes?: string;
}

export interface ProjectUpdateInput {
  name?: string;
  /** '' / null unlinks the customer; undefined leaves it unchanged. */
  customer_id?: string | null;
  customer_name?: string;
  description?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
  billing_method?: string;
  budget?: number;
  project_manager?: string;
  notes?: string;
}

/** Milestone / progress invoice raised from a project (billed to its customer). */
export interface ProjectInvoiceInput {
  amount: number;
  description?: string;
  taxRatePct?: number;
  issueDate?: string;
  dueDate?: string;
  notes?: string;
}

/** API row -> UI model. `withDetail` keeps the collections the detail endpoint returns. */
function toProject(p: any, withDetail = false): Project {
  return {
    id: p.id,
    name: p.name,
    customerId: p.customer_id || '',
    customer: p.customer_name || p.customer || '—',
    description: p.description || '',
    status: p.status,
    startDate: p.start_date || '',
    endDate: p.end_date || '',
    billingMethod: p.billing_method,
    budget: Number(p.budget) || 0,
    billed: Number(p.billed) || 0,
    expenses: Number(p.expenses) || 0,
    projectManager: p.project_manager || '',
    notes: p.notes || '',
    timesheets: withDetail ? p.timesheets || [] : [],
    expenseList: withDetail ? p.expense_list || [] : [],
    invoices: withDetail ? p.invoices || [] : [],
    payments: withDetail ? p.payments || [] : [],
    transactions: withDetail ? p.transactions || [] : [],
  };
}

export const projectService = {
  list: async (params?: ProjectListParams): Promise<Project[]> => {
    const { data } = await apiClient.get<any[]>('/projects', {
      params: cleanParams(params),
    });
    return data.map((p) => toProject(p));
  },

  summary: async (): Promise<ProjectSummaryKPIs> => {
    const { data } = await apiClient.get<ProjectSummaryKPIs>('/projects/summary');
    return data;
  },

  get: async (id: string): Promise<Project> => {
    const { data } = await apiClient.get<any>(`/projects/${id}`);
    return toProject(data, true);
  },

  create: async (body: ProjectCreateInput): Promise<Project> => {
    const { data } = await apiClient.post<any>('/projects', body);
    return toProject(data);
  },

  update: async (id: string, body: ProjectUpdateInput): Promise<Project> => {
    const payload: Record<string, unknown> = { ...body };
    if (body.customer_id === '') payload.customer_id = null;
    Object.keys(payload).forEach((k) => payload[k] === undefined && delete payload[k]);
    const { data } = await apiClient.patch<any>(`/projects/${id}`, payload);
    return toProject(data);
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/projects/${id}`);
  },

  /** Creates a real draft invoice for the project's customer and links it to the project. */
  createInvoice: async (id: string, body: ProjectInvoiceInput): Promise<ProjectInvoice> => {
    const { data } = await apiClient.post<any>(`/projects/${id}/invoices`, {
      amount: body.amount,
      description: body.description || undefined,
      tax_rate_pct: body.taxRatePct,
      issue_date: body.issueDate || undefined,
      due_date: body.dueDate || undefined,
      notes: body.notes || undefined,
    });
    return {
      id: data.id,
      projectId: data.projectId,
      invoiceNumber: data.invoiceNumber,
      date: data.date,
      dueDate: data.dueDate,
      amount: Number(data.amount) || 0,
      status: data.status,
    };
  },
};
