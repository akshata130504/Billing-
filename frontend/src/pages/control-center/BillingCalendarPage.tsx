import { useState, useMemo } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import {
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  Clock,
  Receipt,
  Repeat,
  CreditCard,
} from 'lucide-react';

export type CalendarEventType = 'invoice_generation' | 'subscription_renewal' | 'trial_ending' | 'payment_collection';

export interface CalendarEvent {
  id: string;
  date: string; // YYYY-MM-DD
  type: CalendarEventType;
  title: string;
  account: string;
  amount?: string;
  details: string;
  time?: string;
}

const mockEvents: CalendarEvent[] = [
  {
    id: 'EVT-01',
    date: '2026-09-08',
    type: 'trial_ending',
    title: 'Trial Expiration: Vanguard Biometrics',
    account: 'Vanguard Biometrics',
    amount: '₹65,000.00 / yr',
    details: '14-day enterprise trial completes. Conversion checkout link scheduled.',
    time: '11:00 AM IST',
  },
  {
    id: 'EVT-02',
    date: '2026-09-09',
    type: 'invoice_generation',
    title: 'Monthly Recurring Batch Run #09',
    account: '42 Active Subscriptions',
    amount: '₹4,85,000.00',
    details: 'Automated invoice generation for mid-month subscription cycle accounts.',
    time: '02:00 AM IST',
  },
  {
    id: 'EVT-03',
    date: '2026-09-11',
    type: 'subscription_renewal',
    title: 'Annual Plan Renewal: Acme Cloud Dynamics',
    account: 'Acme Cloud Dynamics',
    amount: '₹1,20,000.00',
    details: 'Tier-3 Pro Annual plan auto-renewal via saved credit mandate.',
    time: '09:30 AM IST',
  },
  {
    id: 'EVT-04',
    date: '2026-09-14',
    type: 'payment_collection',
    title: 'Dunning Automated Retry #3',
    account: 'Hyperion FinTech Ltd',
    amount: '₹42,000.00',
    details: 'Third scheduled attempt for overdue invoice collection.',
    time: '10:00 AM IST',
  },
  {
    id: 'EVT-05',
    date: '2026-09-18',
    type: 'subscription_renewal',
    title: 'Quarterly Renewal: Solaria Robotics',
    account: 'Solaria Robotics Corp',
    amount: '₹37,500.00',
    details: 'Quarterly platform license and 20 compute seats renewal.',
    time: '12:00 PM IST',
  },
  {
    id: 'EVT-06',
    date: '2026-09-22',
    type: 'trial_ending',
    title: 'Trial Expiration: Matrix Logistics',
    account: 'Matrix Logistics Ltd',
    amount: '₹24,000.00 / yr',
    details: 'Trial day 14 completion. Automated conversion campaign triggers.',
    time: '05:00 PM IST',
  },
  {
    id: 'EVT-07',
    date: '2026-09-25',
    type: 'invoice_generation',
    title: 'Usage Metering Invoice Run',
    account: '18 Metered Accounts',
    amount: '₹2,14,000.00',
    details: 'Telemetry data ingestion aggregation cut-off and cycle billing run.',
    time: '11:59 PM IST',
  },
  {
    id: 'EVT-08',
    date: '2026-09-28',
    type: 'payment_collection',
    title: 'ACH / Wire Transfer Settlement Audit',
    account: 'Rooman Treasury',
    amount: '₹6,40,000.00',
    details: 'Quarter-end bank reconciliation cut-off and unallocated payment review.',
    time: '04:00 PM IST',
  },
];

/** Parse a YYYY-MM-DD string as a local date (avoids UTC shifting the day). */
function parseIsoDate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day);
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

const monthLabelFormatter = new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' });
const agendaDateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
});

// Open the calendar on the month that holds the mock schedule so the demo has content.
const DEFAULT_VIEW_MONTH = startOfMonth(parseIsoDate(mockEvents[0].date));

type CalendarCell =
  | { dayNumber: null; isCurrentMonth: false }
  | { dayNumber: number; isCurrentMonth: true; events: CalendarEvent[]; isToday: boolean };

export function BillingCalendarPage() {
  const [viewMonth, setViewMonth] = useState<Date>(DEFAULT_VIEW_MONTH);
  const [selectedType, setSelectedType] = useState<'all' | CalendarEventType>('all');
  const [activeEvent, setActiveEvent] = useState<CalendarEvent | null>(null);

  const selectedMonthLabel = monthLabelFormatter.format(viewMonth);

  // Events for the visible month, honouring the type filter, in chronological order
  const filteredEvents = useMemo(() => {
    return mockEvents
      .filter((e) => selectedType === 'all' || e.type === selectedType)
      .filter((e) => {
        const d = parseIsoDate(e.date);
        return d.getFullYear() === viewMonth.getFullYear() && d.getMonth() === viewMonth.getMonth();
      })
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [selectedType, viewMonth]);

  const calendarDays = useMemo<CalendarCell[]>(() => {
    const year = viewMonth.getFullYear();
    const month = viewMonth.getMonth();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const startDayOffset = new Date(year, month, 1).getDay(); // 0 = Sunday, matches header row
    const today = new Date();

    const days: CalendarCell[] = [];
    for (let i = 0; i < startDayOffset; i++) {
      days.push({ dayNumber: null, isCurrentMonth: false });
    }
    for (let i = 1; i <= daysInMonth; i++) {
      const cellDate = new Date(year, month, i);
      days.push({
        dayNumber: i,
        isCurrentMonth: true,
        events: filteredEvents.filter((e) => parseIsoDate(e.date).getDate() === i),
        isToday: isSameDay(cellDate, today),
      });
    }
    return days;
  }, [filteredEvents, viewMonth]);

  const goToPreviousMonth = () =>
    setViewMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
  const goToNextMonth = () =>
    setViewMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));

  const getEventBadge = (type: CalendarEventType) => {
    switch (type) {
      case 'invoice_generation':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
            <Receipt className="w-2.5 h-2.5" />
            Invoice Run
          </span>
        );
      case 'subscription_renewal':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
            <Repeat className="w-2.5 h-2.5" />
            Renewal
          </span>
        );
      case 'trial_ending':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
            <Clock className="w-2.5 h-2.5" />
            Trial End
          </span>
        );
      case 'payment_collection':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">
            <CreditCard className="w-2.5 h-2.5" />
            Payment Run
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              Control Center
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              Schedule & Planning
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <CalendarIcon className="w-6 h-6 text-brand-600" />
            Billing Calendar
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Visualize recurring billing schedules, scheduled batch invoice generation, subscription renewal cut-offs, and trial expiration dates.
          </p>
        </div>

        {/* Month Picker Controls */}
        <div className="flex items-center gap-2 bg-white border border-slate-200/90 rounded-xl p-1 shadow-2xs">
          <button
            type="button"
            onClick={goToPreviousMonth}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
            aria-label="Previous month"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs font-bold text-slate-900 px-2 min-w-[110px] text-center">
            {selectedMonthLabel}
          </span>
          <button
            type="button"
            onClick={goToNextMonth}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
            aria-label="Next month"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-slate-200/90">
        {[
          { key: 'all', label: 'All Events' },
          { key: 'invoice_generation', label: 'Invoice Generation' },
          { key: 'subscription_renewal', label: 'Renewals' },
          { key: 'trial_ending', label: 'Expiring Trials' },
          { key: 'payment_collection', label: 'Collections' },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setSelectedType(tab.key as typeof selectedType)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer ${
              selectedType === tab.key
                ? 'bg-slate-900 text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Main Layout: Calendar Grid + Agenda Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Calendar Grid (2 Cols) */}
        <div className="lg:col-span-2 space-y-3">
          <Card>
            <CardContent className="p-4 sm:p-5">
              {/* Day Headers */}
              <div className="grid grid-cols-7 text-center text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                <div>Sun</div>
                <div>Mon</div>
                <div>Tue</div>
                <div>Wed</div>
                <div>Thu</div>
                <div>Fri</div>
                <div>Sat</div>
              </div>

              {/* Month Grid Cells */}
              <div className="grid grid-cols-7 gap-1.5 sm:gap-2">
                {calendarDays.map((cell, idx) => {
                  if (!cell.isCurrentMonth) {
                    return (
                      <div
                        key={idx}
                        className="h-20 sm:h-24 bg-slate-50/50 rounded-xl border border-slate-100/80 p-1.5 opacity-40 pointer-events-none"
                      />
                    );
                  }

                  const hasEvents = cell.events && cell.events.length > 0;

                  return (
                    <div
                      key={idx}
                      className={`h-20 sm:h-24 rounded-xl border p-1.5 flex flex-col justify-between transition-all ${
                        cell.isToday
                          ? 'bg-blue-50/40 border-brand-300 ring-1 ring-brand-400'
                          : hasEvents
                          ? 'bg-white border-slate-200/90 hover:border-brand-300 shadow-2xs cursor-pointer'
                          : 'bg-white border-slate-200/60'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span
                          className={`text-xs font-bold ${
                            cell.isToday
                              ? 'w-5 h-5 rounded-full bg-brand-600 text-white flex items-center justify-center text-[10px]'
                              : 'text-slate-700'
                          }`}
                        >
                          {cell.dayNumber}
                        </span>
                        {cell.isToday && (
                          <span className="text-[9px] font-bold text-brand-600 hidden sm:inline">
                            Today
                          </span>
                        )}
                      </div>

                      {/* Event Chips inside cell */}
                      <div className="space-y-1 overflow-hidden">
                        {cell.events?.map((ev) => (
                          <div
                            key={ev.id}
                            onClick={() => setActiveEvent(ev)}
                            className="text-[10px] p-1 rounded font-medium truncate bg-slate-100/90 text-slate-800 hover:bg-brand-50 hover:text-brand-700 transition-colors cursor-pointer border border-slate-200/70"
                            title={`${ev.title} (${ev.account})`}
                          >
                            {ev.title}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Agenda / Upcoming Events Panel (1 Col) */}
        <div className="space-y-4">
          <Card>
            <CardContent className="p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <h3 className="text-sm font-bold text-slate-900 tracking-tight">
                  Upcoming Agenda ({filteredEvents.length})
                </h3>
                <span className="text-[10px] font-medium text-slate-400">
                  Chronological
                </span>
              </div>

              <div className="space-y-3">
                {filteredEvents.length === 0 && (
                  <p className="text-xs text-slate-500 text-center py-6">
                    No scheduled events in {selectedMonthLabel}.
                  </p>
                )}
                {filteredEvents.map((ev) => (
                  <div
                    key={ev.id}
                    onClick={() => setActiveEvent(ev)}
                    className="p-3 rounded-xl bg-slate-50 hover:bg-slate-100/80 border border-slate-200/80 transition-colors cursor-pointer space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-slate-500">
                        {agendaDateFormatter.format(parseIsoDate(ev.date))}
                      </span>
                      {getEventBadge(ev.type)}
                    </div>

                    <h4 className="text-xs font-bold text-slate-900 leading-tight">
                      {ev.title}
                    </h4>

                    <div className="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
                      <span className="truncate max-w-[150px]">{ev.account}</span>
                      {ev.amount && (
                        <span className="font-bold text-slate-900 tabular-nums">
                          {ev.amount}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Event Details Modal */}
      {activeEvent && (
        <Modal
          isOpen={true}
          onClose={() => setActiveEvent(null)}
          title={activeEvent.title}
        >
          <div className="space-y-4">
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-500 font-medium">Event Date</span>
                <span className="font-bold text-slate-900">
                  {agendaDateFormatter.format(parseIsoDate(activeEvent.date))}
                  {activeEvent.time ? ` (${activeEvent.time})` : ''}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500 font-medium">Account / Group</span>
                <span className="font-bold text-slate-900">{activeEvent.account}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500 font-medium">Category</span>
                <div>{getEventBadge(activeEvent.type)}</div>
              </div>
              {activeEvent.amount && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500 font-medium">Scheduled Value</span>
                  <span className="font-bold text-slate-900 text-sm tabular-nums">
                    {activeEvent.amount}
                  </span>
                </div>
              )}
            </div>

            <div>
              <h5 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-1">
                Execution Description
              </h5>
              <p className="text-xs text-slate-700 bg-white p-3 rounded-lg border border-slate-200 leading-relaxed">
                {activeEvent.details}
              </p>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="primary" size="sm" onClick={() => setActiveEvent(null)}>
                Close
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
