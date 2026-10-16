import { beforeEach, describe, expect, it, vi } from 'vitest';
import { projectService } from './projectService';

// Characterisation (modularization P0): pins the requests projectService sends and how it
// maps API rows to the UI model, so moving the Projects code can be shown to change nothing.

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('./apiClient', async (orig) => ({
  ...(await orig<typeof import('./apiClient')>()),
  apiClient: api,
}));

const row = {
  id: 'p1',
  organization_id: 'o1',
  name: 'Website',
  customer_id: 'c1',
  customer_name: 'Acme',
  customer: 'Acme',
  description: 'Rebuild',
  status: 'active',
  start_date: '2026-01-01',
  end_date: '2026-03-31',
  billing_method: 'time_and_material',
  budget: '1234.50',
  billed: '100.00',
  expenses: '20.00',
  project_manager: 'PM',
  notes: 'N',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const detail = {
  ...row,
  timesheets: [{ id: 't1' }],
  expense_list: [{ id: 'e1' }],
  invoices: [{ id: 'i1' }],
  payments: [{ id: 'pay1' }],
  transactions: [{ id: 'inv-i1' }],
};

const mapped = {
  id: 'p1',
  name: 'Website',
  customerId: 'c1',
  customer: 'Acme',
  description: 'Rebuild',
  status: 'active',
  startDate: '2026-01-01',
  endDate: '2026-03-31',
  billingMethod: 'time_and_material',
  budget: 1234.5,
  billed: 100,
  expenses: 20,
  projectManager: 'PM',
  notes: 'N',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('projectService.list', () => {
  it('GETs /projects with empty params dropped and maps rows without detail collections', async () => {
    api.get.mockResolvedValue({ data: [detail] });
    const result = await projectService.list({ search: '', status: 'active', customer_id: undefined });
    expect(api.get).toHaveBeenCalledWith('/projects', { params: { status: 'active' } });
    expect(result).toEqual([
      { ...mapped, timesheets: [], expenseList: [], invoices: [], payments: [], transactions: [] },
    ]);
  });

  it('sends no params when called without filters', async () => {
    api.get.mockResolvedValue({ data: [] });
    await projectService.list();
    expect(api.get).toHaveBeenCalledWith('/projects', { params: {} });
  });

  it('falls back for missing fields', async () => {
    api.get.mockResolvedValue({
      data: [{ id: 'p2', name: 'Bare', status: 'draft', billing_method: 'fixed_price', budget: 'not-a-number' }],
    });
    const [project] = await projectService.list();
    expect(project).toMatchObject({
      customerId: '',
      customer: '—',
      description: '',
      startDate: '',
      endDate: '',
      budget: 0,
      billed: 0,
      expenses: 0,
      projectManager: '',
      notes: '',
    });
  });

  it('uses the customer alias when customer_name is empty', async () => {
    api.get.mockResolvedValue({ data: [{ ...row, customer_name: null, customer: 'Alias Co' }] });
    const [project] = await projectService.list();
    expect(project.customer).toBe('Alias Co');
  });
});

describe('projectService.summary', () => {
  it('GETs /projects/summary and returns the body unchanged (money stays as the API sent it)', async () => {
    const body = { total_projects: 2, active_projects: 1, total_budget: '10.00', total_billed: '0', total_expenses: '5' };
    api.get.mockResolvedValue({ data: body });
    await expect(projectService.summary()).resolves.toBe(body);
    expect(api.get).toHaveBeenCalledWith('/projects/summary');
  });
});

describe('projectService.get', () => {
  it('GETs /projects/:id and keeps the detail collections', async () => {
    api.get.mockResolvedValue({ data: detail });
    const result = await projectService.get('p1');
    expect(api.get).toHaveBeenCalledWith('/projects/p1');
    expect(result).toEqual({
      ...mapped,
      timesheets: detail.timesheets,
      expenseList: detail.expense_list,
      invoices: detail.invoices,
      payments: detail.payments,
      transactions: detail.transactions,
    });
  });
});

describe('projectService.create', () => {
  it('POSTs the body unchanged to /projects', async () => {
    api.post.mockResolvedValue({ data: row });
    const body = { name: 'Website', customer_id: 'c1', budget: 10, status: 'active' };
    const result = await projectService.create(body);
    expect(api.post).toHaveBeenCalledWith('/projects', body);
    expect(result.id).toBe('p1');
  });
});

describe('projectService.update', () => {
  it('PATCHes only defined fields and turns an empty customer_id into null (unlink)', async () => {
    api.patch.mockResolvedValue({ data: row });
    await projectService.update('p1', { name: 'New', customer_id: '', notes: undefined, budget: 0 });
    expect(api.patch).toHaveBeenCalledWith('/projects/p1', { name: 'New', customer_id: null, budget: 0 });
  });

  it('leaves customer_id out when it is undefined', async () => {
    api.patch.mockResolvedValue({ data: row });
    await projectService.update('p1', { status: 'completed' });
    expect(api.patch).toHaveBeenCalledWith('/projects/p1', { status: 'completed' });
  });
});

describe('projectService.delete', () => {
  it('DELETEs /projects/:id', async () => {
    api.delete.mockResolvedValue({ data: undefined });
    await projectService.delete('p1');
    expect(api.delete).toHaveBeenCalledWith('/projects/p1');
  });
});

describe('projectService.createInvoice', () => {
  it('POSTs snake_case fields, sending empty strings as undefined, and maps the reply', async () => {
    api.post.mockResolvedValue({
      data: {
        id: 'i1', projectId: 'p1', invoiceNumber: 'INV-000001', date: '2026-01-02', dueDate: '2026-02-01',
        amount: 1180, amountDue: 1180, currency: 'INR', status: 'draft', rawStatus: 'draft',
      },
    });
    const result = await projectService.createInvoice('p1', {
      amount: 1000, description: '', taxRatePct: 18, issueDate: '', dueDate: '2026-02-01', notes: '',
    });
    expect(api.post).toHaveBeenCalledWith('/projects/p1/invoices', {
      amount: 1000,
      description: undefined,
      tax_rate_pct: 18,
      issue_date: undefined,
      due_date: '2026-02-01',
      notes: undefined,
    });
    expect(result).toEqual({
      id: 'i1', projectId: 'p1', invoiceNumber: 'INV-000001', date: '2026-01-02', dueDate: '2026-02-01',
      amount: 1180, status: 'draft',
    });
  });
});
