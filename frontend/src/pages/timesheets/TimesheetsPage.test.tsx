import { describe, expect, it, vi, beforeEach, afterEach, type MockInstance } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TimesheetsPage } from './TimesheetsPage';
import { timesheetService } from '../../services/timesheetService';

const showToast = vi.hoisted(() => vi.fn());

vi.mock('../../services/timesheetService', () => ({
  timesheetService: {
    summary: vi.fn(),
    list: vi.fn(),
    delete: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    submit: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
  },
}));

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ hasRole: () => false }),
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast }),
}));

const mocked = vi.mocked(timesheetService);

const entry = {
  id: 'te-1',
  date: '2026-10-01',
  user_name: 'Asha',
  project_name: 'Website',
  customer_id: null,
  customer_name: null,
  description: 'Build landing page',
  duration_hours: '2.00',
  billable: false,
  billing_rate: '0',
  billable_amount: '0',
  status: 'draft',
} as any;

describe('<TimesheetsPage /> delete confirmation', () => {
  let confirmSpy: MockInstance<typeof window.confirm>;

  beforeEach(() => {
    vi.clearAllMocks();
    mocked.summary.mockResolvedValue({} as any);
    mocked.list.mockResolvedValue([entry]);
    mocked.delete.mockResolvedValue(undefined as any);
    confirmSpy = vi.spyOn(window, 'confirm');
  });

  afterEach(() => {
    confirmSpy.mockRestore();
  });

  it('uses the in-app ConfirmDialog (not window.confirm) and deletes on confirm', async () => {
    render(
      <MemoryRouter>
        <TimesheetsPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText('Build landing page')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Delete time entry' }));

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(mocked.delete).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Delete time entry')).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(mocked.delete).toHaveBeenCalledWith('te-1'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('does not delete when the dialog is cancelled', async () => {
    render(
      <MemoryRouter>
        <TimesheetsPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText('Build landing page')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Delete time entry' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(mocked.delete).not.toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();
  });
});
