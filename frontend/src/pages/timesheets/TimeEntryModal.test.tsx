import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TimeEntryModal } from './TimeEntryModal';
import { customerService } from '../../services/customerService';
import { projectService } from '../../services/projectService';

vi.mock('../../services/customerService', () => ({
  customerService: { list: vi.fn() },
}));
vi.mock('../../services/projectService', () => ({
  projectService: { list: vi.fn() },
}));

function renderModal(props: Partial<React.ComponentProps<typeof TimeEntryModal>> = {}) {
  const onSave = vi.fn().mockResolvedValue(undefined);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <TimeEntryModal isOpen onClose={vi.fn()} onSave={onSave} {...props} />
    </QueryClientProvider>
  );
  return { onSave };
}

describe('<TimeEntryModal />', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(customerService.list).mockResolvedValue({
      items: [
        { id: 'c1', display_name: 'Acme', customer_number: 'CUST-1' },
        { id: 'c2', display_name: 'Globex', customer_number: 'CUST-2' },
      ],
    } as never);
    vi.mocked(projectService.list).mockImplementation(async (params) =>
      (params?.customer_id === 'c1' ? [{ id: 'p1', name: 'Portal Build' }] : [{ id: 'p2', name: 'Audit' }]) as never
    );
  });

  it('labels every field (BUG-22)', () => {
    renderModal();
    for (const label of ['Work Date', 'Customer / Account', 'Project / Engagement Name', 'Start Time', 'End Time', 'Duration (Hours)', 'Work Description', 'Hourly Billing Rate']) {
      expect(screen.getByLabelText(new RegExp(`^${label.replace(/[()/]/g, '\\$&')}`))).toBeInTheDocument();
    }
  });

  it("links the entry to one of the selected customer's projects (BUG-23)", async () => {
    const { onSave } = renderModal();
    await waitFor(() => expect(screen.getByRole('option', { name: /Acme/ })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Customer / Account'), { target: { value: 'c1' } });
    await waitFor(() => expect(screen.getByRole('option', { name: 'Portal Build' })).toBeInTheDocument());
    expect(projectService.list).toHaveBeenCalledWith({ customer_id: 'c1' });
    expect(screen.queryByRole('option', { name: 'Audit' })).toBeNull();

    fireEvent.change(screen.getByLabelText('Project'), { target: { value: 'p1' } });
    fireEvent.change(screen.getByLabelText(/^Work Description/), { target: { value: 'Built the login page' } });
    fireEvent.click(screen.getByRole('button', { name: 'Log Time' }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][0]).toEqual(
      expect.objectContaining({ customer_id: 'c1', project_id: 'p1', project_name: 'Portal Build' })
    );
  });

  it('clears the project when the customer changes', async () => {
    renderModal();
    await waitFor(() => expect(screen.getByRole('option', { name: /Acme/ })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Customer / Account'), { target: { value: 'c1' } });
    await waitFor(() => expect(screen.getByRole('option', { name: 'Portal Build' })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Project'), { target: { value: 'p1' } });
    fireEvent.change(screen.getByLabelText('Customer / Account'), { target: { value: 'c2' } });
    await waitFor(() => expect(screen.getByRole('option', { name: 'Audit' })).toBeInTheDocument());
    expect((screen.getByLabelText('Project') as HTMLSelectElement).value).toBe('');
  });

  it('sends no project id for an entry without a linked project', async () => {
    const { onSave } = renderModal();
    fireEvent.change(screen.getByLabelText(/^Project \/ Engagement Name/), { target: { value: 'Internal training' } });
    fireEvent.change(screen.getByLabelText(/^Work Description/), { target: { value: 'Security workshop' } });
    fireEvent.click(screen.getByRole('button', { name: 'Log Time' }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][0]).toEqual(expect.objectContaining({ project_id: null, project_name: 'Internal training' }));
  });
});
