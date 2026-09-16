import { apiClient, cleanParams } from './apiClient';
import type { Project } from '../pages/projects/types';

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

export const projectService = {
  list: async (params?: ProjectListParams): Promise<Project[]> => {
    const { data } = await apiClient.get<any[]>('/projects', {
      params: cleanParams(params),
    });
    return data.map((p) => ({
      id: p.id,
      name: p.name,
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
      timesheets: [],
      expenseList: [],
      invoices: [],
      payments: [],
      transactions: [],
    }));
  },

  summary: async (): Promise<ProjectSummaryKPIs> => {
    const { data } = await apiClient.get<ProjectSummaryKPIs>('/projects/summary');
    return data;
  },

  get: async (id: string): Promise<Project> => {
    const { data } = await apiClient.get<any>(`/projects/${id}`);
    return {
      id: data.id,
      name: data.name,
      customer: data.customer_name || data.customer || '—',
      description: data.description || '',
      status: data.status,
      startDate: data.start_date || '',
      endDate: data.end_date || '',
      billingMethod: data.billing_method,
      budget: Number(data.budget) || 0,
      billed: Number(data.billed) || 0,
      expenses: Number(data.expenses) || 0,
      projectManager: data.project_manager || '',
      notes: data.notes || '',
      timesheets: data.timesheets || [],
      expenseList: data.expense_list || [],
      invoices: data.invoices || [],
      payments: data.payments || [],
      transactions: data.transactions || [],
    };
  },

  create: async (body: ProjectCreateInput): Promise<Project> => {
    const { data } = await apiClient.post<any>('/projects', body);
    return {
      id: data.id,
      name: data.name,
      customer: data.customer_name || data.customer || '—',
      description: data.description || '',
      status: data.status,
      startDate: data.start_date || '',
      endDate: data.end_date || '',
      billingMethod: data.billing_method,
      budget: Number(data.budget) || 0,
      billed: Number(data.billed) || 0,
      expenses: Number(data.expenses) || 0,
      projectManager: data.project_manager || '',
      notes: data.notes || '',
      timesheets: [],
      expenseList: [],
      invoices: [],
      payments: [],
      transactions: [],
    };
  },

  update: async (id: string, body: ProjectUpdateInput): Promise<Project> => {
    const { data } = await apiClient.patch<any>(`/projects/${id}`, body);
    return {
      id: data.id,
      name: data.name,
      customer: data.customer_name || data.customer || '—',
      description: data.description || '',
      status: data.status,
      startDate: data.start_date || '',
      endDate: data.end_date || '',
      billingMethod: data.billing_method,
      budget: Number(data.budget) || 0,
      billed: Number(data.billed) || 0,
      expenses: Number(data.expenses) || 0,
      projectManager: data.project_manager || '',
      notes: data.notes || '',
      timesheets: [],
      expenseList: [],
      invoices: [],
      payments: [],
      transactions: [],
    };
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/projects/${id}`);
  },
};
