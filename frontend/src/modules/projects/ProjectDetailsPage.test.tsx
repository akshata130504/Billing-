import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ProjectDetailsPage } from './ProjectDetailsPage';
import { ProjectsProvider } from './ProjectsContext';
import type { Project } from './types';
import { projectService } from '../../services/projectService';

// Characterisation (modularization P0): the project detail page as it behaves today, rendered
// through the real ProjectsProvider with only the network layer stubbed.

vi.mock('../../services/projectService', () => ({
  projectService: {
    list: vi.fn(),
    summary: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    createInvoice: vi.fn(),
  },
}));
vi.mock('../../services/apiClient', async (orig) => {
  const actual = await orig<typeof import('../../services/apiClient')>();
  return { ...actual, tokenStorage: { ...actual.tokenStorage, hasSession: () => true } };
});
vi.mock('../../services/expenseService', () => ({ expenseService: { create: vi.fn() } }));
vi.mock('../../services/timesheetService', () => ({ timesheetService: { create: vi.fn() } }));
const toast = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock('../../components/common/Toast', () => ({ useToast: () => toast }));
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { full_name: 'Owner', email: 'owner@example.test' } }) }));

const svc = vi.mocked(projectService);

const detail: Project = {
  id: 'p1', name: 'Website Rebuild', customerId: 'c1', customer: 'Acme Ltd', description: 'Rebuild', status: 'active',
  startDate: '2026-01-01', endDate: '2026-03-31', billingMethod: 'time_and_material', budget: 5000, billed: 1200,
  expenses: 70, projectManager: '', notes: '',
  timesheets: [{ id: 't1', projectId: 'p1', employee: 'Owner', date: '2026-01-05', description: 'Build', hours: 2, billable: true, hourlyRate: 150, amount: 300 }],
  expenseList: [{ id: 'e1', projectId: 'p1', date: '2026-01-06', title: 'Hosting', category: 'Infrastructure', amount: 70, billable: true, status: 'recorded' }],
  invoices: [{ id: 'i1', projectId: 'p1', invoiceNumber: 'INV-000007', date: '2026-01-07', dueDate: '2026-02-06', amount: 1180, status: 'draft' }],
  payments: [],
  transactions: [{ id: 'inv-i1', projectId: 'p1', type: 'Invoice', reference: 'INV-000007', date: '2026-01-07', amount: 1180, status: 'draft' }],
};

function renderAt(path = '/projects/p1') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ProjectsProvider>
        <Routes>
          <Route path="/projects" element={<div>projects-list-page</div>} />
          <Route path="/projects/:projectId" element={<ProjectDetailsPage />} />
        </Routes>
      </ProjectsProvider>
    </MemoryRouter>
  );
}

// What the list endpoint returns for the same project: summary fields, no detail collections.
const listed: Project = { ...detail, timesheets: [], expenseList: [], invoices: [], payments: [], transactions: [] };

beforeEach(() => {
  vi.clearAllMocks();
  // Current behaviour: the provider's list load replaces its project state, so a detail page
  // keeps its project only when the list also contains it (as it does in the real app).
  svc.list.mockResolvedValue([listed]);
  svc.get.mockResolvedValue(detail);
});

describe('<ProjectDetailsPage /> characterisation', () => {
  it('fetches the detail for the route id and renders the header, totals and tab counts', async () => {
    renderAt();
    expect(await screen.findByRole('heading', { name: 'Website Rebuild' })).toBeInTheDocument();
    expect(svc.get).toHaveBeenCalledWith('p1');
    expect(screen.getAllByText('Acme Ltd').length).toBeGreaterThan(0);
    // Budget, billed and unbilled balance (budget - billed) in whole rupees.
    expect(screen.getAllByText('₹5,000').length).toBeGreaterThan(0);
    expect(screen.getAllByText('₹1,200').length).toBeGreaterThan(0);
    expect(screen.getAllByText('₹3,800').length).toBeGreaterThan(0);
    for (const [tab, count] of [['Timesheets', '1'], ['Expenses', '1'], ['Transactions', '1']]) {
      expect(screen.getByRole('button', { name: `${tab} ${count}` })).toBeInTheDocument();
    }
  });

  it('shows the transactions tab rows', async () => {
    renderAt();
    await screen.findByRole('heading', { name: 'Website Rebuild' });
    fireEvent.click(screen.getByRole('button', { name: 'Transactions 1' }));
    expect(screen.getByText('INV-000007')).toBeInTheDocument();
  });

  it('shows "Project Not Found" for a 404 without an error toast', async () => {
    svc.get.mockRejectedValue({ code: 'ENTITY_NOT_FOUND', message: 'Project not found', status: 404 });
    renderAt('/projects/missing');
    expect(await screen.findByText('Project Not Found')).toBeInTheDocument();
    expect(toast.showToast).not.toHaveBeenCalled();
  });

  it('toasts other load failures', async () => {
    svc.get.mockRejectedValue({ code: 'INTERNAL_SERVER_ERROR', message: 'Boom', status: 500 });
    renderAt();
    await waitFor(() => expect(toast.showToast).toHaveBeenCalledWith('error', 'Failed to load project', 'Boom'));
  });

  it('creates a draft invoice from the header, defaulting to the unbilled balance, then reloads', async () => {
    svc.createInvoice.mockResolvedValue({
      id: 'i2', projectId: 'p1', invoiceNumber: 'INV-000008', date: '2026-01-08', dueDate: '2026-01-23', amount: 4484, status: 'draft',
    });
    renderAt();
    await screen.findByRole('heading', { name: 'Website Rebuild' });
    fireEvent.click(screen.getByRole('button', { name: /New Invoice/ }));
    expect(screen.getByLabelText(/Amount before tax/)).toHaveValue(3800);
    fireEvent.click(screen.getByRole('button', { name: 'Create Draft Invoice' }));

    await waitFor(() => expect(svc.createInvoice).toHaveBeenCalledTimes(1));
    expect(svc.createInvoice).toHaveBeenCalledWith('p1', {
      amount: 3800,
      description: undefined,
      taxRatePct: 18,
      issueDate: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      dueDate: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    });
    await waitFor(() => expect(svc.get).toHaveBeenCalledTimes(2));
    expect(toast.showToast).toHaveBeenCalledWith('success', 'Invoice Created', 'Draft invoice INV-000008 created.');
  });

  it('refuses a zero invoice amount without calling the API', async () => {
    renderAt();
    await screen.findByRole('heading', { name: 'Website Rebuild' });
    fireEvent.click(screen.getByRole('button', { name: /New Invoice/ }));
    const amount = screen.getByLabelText(/Amount before tax/);
    fireEvent.change(amount, { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Draft Invoice' }));
    // The field's own min="0.01" constraint blocks the submit before the form's handler runs.
    expect(amount).toBeInvalid();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(svc.createInvoice).not.toHaveBeenCalled();
  });

  it('refuses a due date before the invoice date without calling the API', async () => {
    renderAt();
    await screen.findByRole('heading', { name: 'Website Rebuild' });
    fireEvent.click(screen.getByRole('button', { name: /New Invoice/ }));
    fireEvent.change(screen.getByLabelText(/Invoice Date/), { target: { value: '2026-05-10' } });
    fireEvent.change(screen.getByLabelText(/Payment Due Date/), { target: { value: '2026-05-09' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Draft Invoice' }));
    expect(await screen.findByText('Due date cannot be before the invoice date')).toBeInTheDocument();
    expect(svc.createInvoice).not.toHaveBeenCalled();
  });

  it('deletes from the more-actions menu after confirmation and returns to the list', async () => {
    svc.delete.mockResolvedValue(undefined);
    renderAt();
    await screen.findByRole('heading', { name: 'Website Rebuild' });
    fireEvent.click(screen.getByTitle('More project actions'));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(svc.delete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Yes, Delete Project' }));
    await waitFor(() => expect(svc.delete).toHaveBeenCalledWith('p1'));
    expect(await screen.findByText('projects-list-page')).toBeInTheDocument();
  });

  it('marks the project completed through an update', async () => {
    svc.update.mockResolvedValue({ ...detail, status: 'completed' });
    renderAt();
    await screen.findByRole('heading', { name: 'Website Rebuild' });
    fireEvent.click(screen.getByTitle('More project actions'));
    fireEvent.click(screen.getByRole('button', { name: 'Mark Completed' }));
    await waitFor(() => expect(svc.update).toHaveBeenCalledTimes(1));
    expect(svc.update.mock.calls[0][0]).toBe('p1');
    expect(svc.update.mock.calls[0][1]).toMatchObject({ status: 'completed' });
    expect(toast.showToast).toHaveBeenCalledWith('success', 'Status Updated', 'Project marked as Completed.');
  });
});
