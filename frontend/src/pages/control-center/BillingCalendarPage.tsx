import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { Pagination } from '../../components/common/Pagination';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { controlCenterService, toApiError } from '../../services';
import { queryKeys } from '../../hooks/queries';
import { formatDate, formatMoney, humanize, statusVariant } from '../../utils/format';
import type { CalendarEvent, CalendarEventType } from '../../types/api';
import {
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  FileClock,
  Receipt,
  Repeat,
} from 'lucide-react';
import { usePageSpec } from '../../appUi/usePageSpec';

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

/** Format a Date as the `YYYY-MM` string the calendar endpoint expects. */
function toMonthString(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  return `${year}-${month}`;
}

const monthLabelFormatter = new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' });

// Real backend `entity_type` values -> the detail route each one lives at.
const ENTITY_ROUTE_BASE: Record<string, string> = {
  invoice: '/invoices',
  subscription: '/subscriptions',
  quote: '/quotes',
};

function entityHref(entityType: string, entityId: string): string | null {
  const base = ENTITY_ROUTE_BASE[entityType];
  return base ? `${base}/${entityId}` : null;
}

type CalendarCell =
  | { dayNumber: null; isCurrentMonth: false }
  | { dayNumber: number; isCurrentMonth: true; events: CalendarEvent[]; isToday: boolean };

const AGENDA_PAGE_SIZE = 10;

export function BillingCalendarPage() {
  const navigate = useNavigate();
  const ui = usePageSpec('billing_calendar');
  const [viewMonth, setViewMonth] = useState<Date>(() => startOfMonth(new Date()));
  const [selectedType, setSelectedType] = useState<'all' | CalendarEventType>('all');
  const [activeEvent, setActiveEvent] = useState<CalendarEvent | null>(null);
  const [agendaPage, setAgendaPage] = useState(1);

  const selectedMonthLabel = monthLabelFormatter.format(viewMonth);
  const monthString = useMemo(() => toMonthString(viewMonth), [viewMonth]);

  const calendarQuery = useQuery({
    queryKey: queryKeys.controlCenter.calendar(monthString),
    queryFn: () => controlCenterService.calendar(monthString),
  });

  // Events for the visible month, honouring the type filter, in chronological order
  const filteredEvents = useMemo(() => {
    const events = calendarQuery.data?.events ?? [];
    return events
      .filter((e) => selectedType === 'all' || e.type === selectedType)
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [calendarQuery.data, selectedType]);

  // Agenda-only paging (the month grid keeps every event). Clamp if the list shrinks.
  const agendaTotalPages = Math.max(1, Math.ceil(filteredEvents.length / AGENDA_PAGE_SIZE));
  const currentAgendaPage = Math.min(agendaPage, agendaTotalPages);
  const agendaEvents = useMemo(
    () =>
      filteredEvents.slice(
        (currentAgendaPage - 1) * AGENDA_PAGE_SIZE,
        currentAgendaPage * AGENDA_PAGE_SIZE
      ),
    [filteredEvents, currentAgendaPage]
  );

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
    {
      setViewMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
      setAgendaPage(1);
    };
  const goToNextMonth = () =>
    {
      setViewMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
      setAgendaPage(1);
    };

  const goToEntity = (event: CalendarEvent) => {
    const href = entityHref(event.entity_type, event.entity_id);
    if (href) {
      setActiveEvent(null);
      navigate(href);
    }
  };

  const getEventBadge = (type: CalendarEventType) => {
    switch (type) {
      case 'invoice_due':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
            <Receipt className="w-2.5 h-2.5" />
            Invoice Due
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
      case 'quote_expiry':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">
            <FileClock className="w-2.5 h-2.5" />
            Quote Expiring
          </span>
        );
    }
  };

  const isLoading = calendarQuery.isPending;
  const isError = calendarQuery.isError;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div {...ui.edit('header')}>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              {ui.text('header', 'eyebrow')}
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              {ui.text('header', 'badge')}
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <CalendarIcon className="w-6 h-6 text-brand-600" />
            {ui.text('header', 'title')}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            {ui.text('header', 'subtitle')}
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
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-slate-200/90" {...ui.edit('tabs')}>
        {ui.shown('tabs').map((item) => ({ key: item.key, label: item.label })).map((tab) => (
          <button
            key={tab.key}
            {...ui.edit(`tabs.${tab.key}`)}
            type="button"
            onClick={() => {
              setSelectedType(tab.key as typeof selectedType);
              setAgendaPage(1);
            }}
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

      {isLoading ? (
        <LoadingState message="Loading billing calendar..." className="py-16" />
      ) : isError ? (
        <ErrorState
          message={toApiError(calendarQuery.error).message}
          onRetry={() => void calendarQuery.refetch()}
        />
      ) : (
        <>
          {/* Main Layout: Calendar Grid + Agenda Sidebar */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Calendar Grid (2 Cols) */}
            <div className="lg:col-span-2 space-y-3">
              <Card>
                <CardContent className="p-4 sm:p-5">
                  {/* Day Headers */}
                  {/* Fixed Sunday-first order (matches the grid offset); labels come from the page spec. */}
                  <div className="grid grid-cols-7 text-center text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2" {...ui.edit('weekdays')}>
                    {ui.shown('weekdays').map((day) => (
                      <div key={day.key} {...ui.edit(`weekdays.${day.key}`)}>{day.label}</div>
                    ))}
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
                              <span className="text-[9px] font-bold text-brand-600 hidden sm:inline" {...ui.edit('calendar')}>
                                {ui.text('calendar', 'today')}
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
                                title={`${ev.title} (${ev.customer?.display_name ?? humanize(ev.entity_type)})`}
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
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3" {...ui.edit('agenda')}>
                    <h3 className="text-sm font-bold text-slate-900 tracking-tight">
                      {ui.text('agenda', 'title')} ({filteredEvents.length})
                    </h3>
                    <span className="text-[10px] font-medium text-slate-400">
                      {ui.text('agenda', 'caption')}
                    </span>
                  </div>

                  <div className="space-y-3 max-h-[640px] overflow-y-auto pr-1">
                    {filteredEvents.length === 0 && (
                      <p className="text-xs text-slate-500 text-center py-6" {...ui.edit('agenda')}>
                        {ui.text('agenda', 'empty', { month: selectedMonthLabel })}
                      </p>
                    )}
                    {agendaEvents.map((ev) => (
                      <div
                        key={ev.id}
                        onClick={() => setActiveEvent(ev)}
                        className="min-w-0 p-3 rounded-xl bg-slate-50 hover:bg-slate-100/80 border border-slate-200/80 transition-colors cursor-pointer space-y-1.5"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[11px] font-bold text-slate-500">
                            {formatDate(ev.date)}
                          </span>
                          {getEventBadge(ev.type)}
                        </div>

                        <h4 className="text-xs font-bold text-slate-900 leading-tight break-words">
                          {ev.title}
                        </h4>

                        <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500 pt-0.5">
                          <span className="min-w-0 flex-1 truncate">
                            {ev.customer?.display_name ?? '—'}
                          </span>
                          {ev.amount !== null && (
                            <span className="shrink-0 font-bold text-slate-900 tabular-nums">
                              {formatMoney(ev.amount)}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  {filteredEvents.length > AGENDA_PAGE_SIZE && (
                    <Pagination
                      page={currentAgendaPage}
                      pageSize={AGENDA_PAGE_SIZE}
                      total={filteredEvents.length}
                      onPageChange={setAgendaPage}
                      itemLabel="events"
                    />
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      )}

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
                <span className="font-bold text-slate-900">{formatDate(activeEvent.date)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500 font-medium">Customer</span>
                <span className="font-bold text-slate-900">
                  {activeEvent.customer?.display_name ?? '—'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500 font-medium">Category</span>
                <div>{getEventBadge(activeEvent.type)}</div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500 font-medium">Status</span>
                <Badge variant={statusVariant(activeEvent.status)} size="sm">
                  {humanize(activeEvent.status)}
                </Badge>
              </div>
              {activeEvent.amount !== null && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500 font-medium">Scheduled Value</span>
                  <span className="font-bold text-slate-900 text-sm tabular-nums">
                    {formatMoney(activeEvent.amount)}
                  </span>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setActiveEvent(null)}>
                Close
              </Button>
              {entityHref(activeEvent.entity_type, activeEvent.entity_id) && (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => goToEntity(activeEvent)}
                  trailingIcon={<ExternalLink className="w-3.5 h-3.5" />}
                >
                  View {humanize(activeEvent.entity_type)}
                </Button>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
