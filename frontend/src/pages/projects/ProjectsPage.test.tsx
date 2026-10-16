import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectsPage } from './ProjectsPage';
import { ProjectsProvider } from './ProjectsContext';
import type { Project } from './types';
import { projectService } from '../../services/projectService';
import { tokenStorage } from '../../services/apiClient';

// Characterisation (modularization P0): the Projects list page as it behaves today, rendered
// through the real ProjectsProvider with only the network layer and leaf widgets stubbed.

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
  return { ...actual, tokenStorage: { ...actual.tokenStorage, hasSession: vi.fn(() => true) } };
});
vi.mock('../../services/expenseService', () => ({ expenseService: { create: vi.fn() } }));
vi.mock('../../services/timesheetService', () => ({ timesheetService: { create: vi.fn() } }));
const toast = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock('../../components/common/Toast', () => ({ useToast: () => toast }));
vi.mock('../../components/common/CustomerCombobox', () => ({
  CustomerCombobox: ({ onChange, error }: { onChange: (id: string, c?: { display_name: string }) => void; error?: string }) => (
    <div>
      <button type="button" onClick={() => onChange('c1', { display_name: 'Acme Ltd' })}>pick-customer</button>
      {error && <p>{error}</p>}
    </div>
  ),
}));

const svc = vi.mocked(projectService);

function project(over: Partial<Project>): Project {
  return {
    id: 'p1', name: 'Website Rebuild', customerId: 'c1', customer: 'Acme Ltd', description: '', status: 'active',
    startDate: '2026-01-01', endDate: '2026-03-31', billingMethod: 'fixed_price', budget: 5000, billed: 1000,
    expenses: 200, projectManager: '', notes: '', timesheets: [], expenseList: [], invoices: [], payments: [],
    transactions: [], ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/projects']}>
      <ProjectsProvider>
        <ProjectsPage />
      </ProjectsProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(tokenStorage.hasSession).mockReturnValue(true);
  svc.list.mockResolvedValue([
    project({}),
    project({ id: 'p2', name: 'Data Lake', customer: 'Other Co', customerId: 'c2', status: 'completed' }),
  ]);
});

describe('<ProjectsPage /> characterisation', () => {
  it('loads the list once without filters and renders every project; the summary endpoint is not used', async () => {
    renderPage();
    expect(await screen.findByText('Website Rebuild')).toBeInTheDocument();
    expect(screen.getByText('Data Lake')).toBeInTheDocument();
    expect(svc.list).toHaveBeenCalledTimes(1);
    expect(svc.list).toHaveBeenCalledWith();
    expect(svc.summary).not.toHaveBeenCalled();
  });

  it('does not call the API without a session', async () => {
    vi.mocked(tokenStorage.hasSession).mockReturnValue(false);
    renderPage();
    expect(await screen.findByText('Clear Filters')).toBeInTheDocument();
    expect(svc.list).not.toHaveBeenCalled();
  });

  it('searches on the client, by name or customer, without new requests', async () => {
    renderPage();
    await screen.findByText('Website Rebuild');
    const search = screen.getByPlaceholderText('Search project or customer...');
    fireEvent.change(search, { target: { value: 'other co' } });
    expect(screen.queryByText('Website Rebuild')).toBeNull();
    expect(screen.getByText('Data Lake')).toBeInTheDocument();
    fireEvent.change(search, { target: { value: 'no match at all' } });
    expect(screen.queryByText('Data Lake')).toBeNull();
    expect(screen.getByText('Clear Filters')).toBeInTheDocument();
    expect(svc.list).toHaveBeenCalledTimes(1);
  });

  it('toasts when the list fails to load', async () => {
    svc.list.mockRejectedValue({ code: 'INTERNAL_SERVER_ERROR', message: 'Boom', status: 500 });
    renderPage();
    await waitFor(() => expect(toast.showToast).toHaveBeenCalledWith('error', 'Failed to load projects', 'Boom'));
  });

  it('creates a project with the mapped body, then toasts and closes the form', async () => {
    svc.create.mockResolvedValue(project({ id: 'p9', name: 'New Portal' }));
    renderPage();
    await screen.findByText('Website Rebuild');
    fireEvent.click(screen.getByRole('button', { name: /New Project/ }));
    fireEvent.change(screen.getByLabelText(/Project Name/), { target: { value: '  New Portal  ' } });
    fireEvent.click(screen.getByText('pick-customer'));
    fireEvent.click(screen.getByRole('button', { name: 'Create Project' }));

    await waitFor(() => expect(svc.create).toHaveBeenCalledTimes(1));
    expect(svc.create.mock.calls[0][0]).toEqual({
      name: 'New Portal',
      customer_id: 'c1',
      customer_name: undefined,
      description: '',
      status: 'active',
      start_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      end_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      billing_method: 'fixed_price',
      budget: 100000,
      notes: '',
    });
    await waitFor(() => expect(toast.showToast).toHaveBeenCalledWith('success', 'Project Created', '"New Portal" created.'));
    expect(await screen.findByText('New Portal')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create Project' })).toBeNull();
  });

  it('requires a customer before creating', async () => {
    renderPage();
    await screen.findByText('Website Rebuild');
    fireEvent.click(screen.getByRole('button', { name: /New Project/ }));
    fireEvent.change(screen.getByLabelText(/Project Name/), { target: { value: 'No Customer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Project' }));
    expect(await screen.findByText('Customer is required')).toBeInTheDocument();
    expect(svc.create).not.toHaveBeenCalled();
  });

  it('deletes only after confirmation and removes the row', async () => {
    svc.delete.mockResolvedValue(undefined);
    renderPage();
    const row = (await screen.findByText('Website Rebuild')).closest('tr')!;
    fireEvent.click(within(row).getByRole('button', { name: 'Actions' }));
    fireEvent.click(within(row).getByText('Delete'));
    expect(svc.delete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Yes, Delete Project' }));
    await waitFor(() => expect(svc.delete).toHaveBeenCalledWith('p1'));
    await waitFor(() =>
      expect(toast.showToast).toHaveBeenCalledWith('info', 'Project Deleted', '"Website Rebuild" has been removed.')
    );
    expect(screen.queryByText('Website Rebuild')).toBeNull();
  });

  it('restores the row and toasts when the delete fails', async () => {
    svc.delete.mockRejectedValue({ code: 'FORBIDDEN', message: 'Not allowed', status: 403 });
    renderPage();
    const row = (await screen.findByText('Website Rebuild')).closest('tr')!;
    fireEvent.click(within(row).getByRole('button', { name: 'Actions' }));
    fireEvent.click(within(row).getByText('Delete'));
    fireEvent.click(screen.getByRole('button', { name: 'Yes, Delete Project' }));
    await waitFor(() => expect(toast.showToast).toHaveBeenCalledWith('error', 'Failed to delete project', 'Not allowed'));
    expect(await screen.findByText('Website Rebuild')).toBeInTheDocument();
  });
});
