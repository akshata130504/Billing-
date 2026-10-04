import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BillingCalendarPage } from './BillingCalendarPage';
import { controlCenterService } from '../../services';
import type { CalendarEvent } from '../../types/api';

vi.mock('../../services', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services')>();
  return {
    ...actual,
    controlCenterService: { ...actual.controlCenterService, calendar: vi.fn() },
  };
});

const calendarMock = vi.mocked(controlCenterService.calendar);

function monthPrefix() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function makeEvents(count: number): CalendarEvent[] {
  return Array.from({ length: count }, (_, i) => {
    const day = Math.floor((i * 28) / count) + 1; // non-decreasing => order == index
    const n = String(i + 1).padStart(2, '0');
    return {
      id: `ev-${n}`,
      date: `${monthPrefix()}-${String(day).padStart(2, '0')}`,
      type: i % 2 === 0 ? 'invoice_due' : 'subscription_renewal',
      title: `Event ${n}`,
      customer: { id: `c-${n}`, display_name: `Customer ${n}` },
      amount: '100.00',
      entity_type: 'invoice',
      entity_id: `inv-${n}`,
      status: 'sent',
    } as unknown as CalendarEvent;
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BillingCalendarPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function agenda() {
  // The first render of a full month (40 events) can exceed findBy's 1 s default under a loaded runner.
  const heading = await screen.findByRole('heading', { name: /upcoming agenda/i }, { timeout: 5000 });
  return within(heading.closest('div.p-5') as HTMLElement);
}

describe('BillingCalendarPage agenda pagination', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders only the first page of 40 events with pagination controls', async () => {
    calendarMock.mockResolvedValue({ events: makeEvents(40) });
    renderPage();
    const a = await agenda();
    expect(a.getByText('Upcoming Agenda (40)')).toBeInTheDocument();
    expect(a.getByText('Event 01')).toBeInTheDocument();
    expect(a.getByText('Event 10')).toBeInTheDocument();
    expect(a.queryByText('Event 11')).not.toBeInTheDocument();
    expect(a.getByText(/page 1 of 4/i)).toBeInTheDocument();
  });

  it('shows the next page when Next is clicked', async () => {
    calendarMock.mockResolvedValue({ events: makeEvents(40) });
    renderPage();
    const a = await agenda();
    fireEvent.click(a.getByRole('button', { name: /next/i }));
    expect(a.getByText('Event 11')).toBeInTheDocument();
    expect(a.queryByText('Event 01')).not.toBeInTheDocument();
    expect(a.getByText(/page 2 of 4/i)).toBeInTheDocument();
  });

  it('resets to page 1 and filters when the type filter changes', async () => {
    calendarMock.mockResolvedValue({ events: makeEvents(40) });
    renderPage();
    const a = await agenda();
    fireEvent.click(a.getByRole('button', { name: /next/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Renewals' }));
    expect(a.getByText('Upcoming Agenda (20)')).toBeInTheDocument();
    expect(a.getByText(/page 1 of 2/i)).toBeInTheDocument();
    expect(a.getByText('Event 02')).toBeInTheDocument();
    expect(a.queryByText('Event 01')).not.toBeInTheDocument();
  });

  it('opens details for an event selected on page 2', async () => {
    calendarMock.mockResolvedValue({ events: makeEvents(40) });
    renderPage();
    const a = await agenda();
    fireEvent.click(a.getByRole('button', { name: /next/i }));
    fireEvent.click(a.getByText('Event 12'));
    expect(await screen.findByText('Event Date')).toBeInTheDocument();
    expect(screen.getAllByText('Customer 12').length).toBeGreaterThan(1);
  });

  it('shows no pagination when events fit on one page', async () => {
    calendarMock.mockResolvedValue({ events: makeEvents(10) });
    renderPage();
    const a = await agenda();
    expect(a.getByText('Event 10')).toBeInTheDocument();
    expect(a.queryByRole('button', { name: /next/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/page 1 of/i)).not.toBeInTheDocument();
  });

  it('shows the empty state for a month without events', async () => {
    calendarMock.mockResolvedValue({ events: [] });
    renderPage();
    expect(await screen.findByText(/no scheduled events in/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument();
  });

  it('shows the error state when loading fails', async () => {
    calendarMock.mockRejectedValue(new Error('boom'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeInTheDocument();
  });
});
