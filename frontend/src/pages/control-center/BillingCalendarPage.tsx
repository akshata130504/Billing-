import { useState } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import {
  Calendar as CalendarIcon,
} from 'lucide-react';

interface CalendarEvent {
  id: string;
  type: 'invoice' | 'renewal' | 'trial' | 'payment' | 'retry';
  title: string;
  client: string;
  amount: string;
  date: string;
  day: number;
  time: string;
  status: 'scheduled' | 'imminent' | 'action_required';
}

const mockEvents: CalendarEvent[] = [
  {
    id: 'EVT-01',
    type: 'invoice',
    day: 8,
    date: 'Sep 08, 2026',
    time: '09:00 AM',
    title: 'Net 30 Invoice Due (#INV-2026-081)',
    client: 'Starlight Media Group',
    amount: '$18,400.00',
    status: 'imminent',
  },
  {
    id: 'EVT-02',
    type: 'renewal',
    day: 10,
    date: 'Sep 10, 2026',
    time: '12:00 PM',
    title: 'Annual Subscription Renewal (12 Seats)',
    client: 'Apex Global Logistics',
    amount: '$48,000.00 / yr',
    status: 'scheduled',
  },
  {
    id: 'EVT-03',
    type: 'trial',
    day: 11,
    date: 'Sep 11, 2026',
    time: '05:00 PM',
    title: '14-Day Free Trial Expiration',
    client: 'CloudScale Systems',
    amount: 'Pipeline $6,000',
    status: 'action_required',
  },
  {
    id: 'EVT-04',
    type: 'payment',
    day: 15,
    date: 'Sep 15, 2026',
    time: '02:00 AM',
    title: 'Mid-Month Batch Direct Debit Run',
    client: '42 Active Accounts',
    amount: '$126,800.00',
    status: 'scheduled',
  },
  {
    id: 'EVT-05',
    type: 'retry',
    day: 16,
    date: 'Sep 16, 2026',
    time: '10:30 AM',
    title: 'Smart Dunning Payment Retry #3',
    client: 'Zenith Retail India',
    amount: '$3,150.00',
    status: 'imminent',
  },
  {
    id: 'EVT-06',
    type: 'renewal',
    day: 22,
    date: 'Sep 22, 2026',
    time: '11:00 AM',
    title: 'Quarterly Multi-Tenant Renewal',
    client: 'HyperLink Networks',
    amount: '$15,200.00',
    status: 'scheduled',
  },
];

export function BillingCalendarPage() {
  const [filterType, setFilterType] = useState<string>('all');
  const [selectedDay, setSelectedDay] = useState<number | null>(null);

  const filteredEvents = mockEvents.filter((ev) => {
    if (selectedDay !== null && ev.day !== selectedDay) return false;
    if (filterType === 'all') return true;
    return ev.type === filterType;
  });

  const daysInMonth = Array.from({ length: 30 }, (_, i) => i + 1);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              Control Center
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              Time-Based Planning
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Billing Calendar
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Chronological horizon for scheduled recurring runs, invoice due dates, subscription renewals, trial expiries, and automated payment retries.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<CalendarIcon className="w-3.5 h-3.5" />}
          >
            September 2026
          </Button>
        </div>
      </div>

      {/* Filter Chips */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {[
          { id: 'all', label: 'All Events' },
          { id: 'invoice', label: 'Invoices Due' },
          { id: 'renewal', label: 'Renewals' },
          { id: 'trial', label: 'Trials Expiring' },
          { id: 'payment', label: 'Batch Payments' },
          { id: 'retry', label: 'Payment Retries' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setFilterType(tab.id)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-colors whitespace-nowrap cursor-pointer ${
              filterType === tab.id
                ? 'bg-brand-600 text-white shadow-xs'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Calendar Grid */}
        <Card className="lg:col-span-2">
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <CalendarIcon className="w-4 h-4 text-brand-600" />
                <span>September 2026 Schedule</span>
              </h3>
              {selectedDay !== null && (
                <button
                  onClick={() => setSelectedDay(null)}
                  className="text-xs text-brand-600 hover:underline font-medium"
                >
                  Clear day filter ({selectedDay}th)
                </button>
              )}
            </div>

            {/* Days of week */}
            <div className="grid grid-cols-7 gap-1.5 text-center text-[11px] font-bold text-slate-400 uppercase mb-2">
              <span>Mon</span>
              <span>Tue</span>
              <span>Wed</span>
              <span>Thu</span>
              <span>Fri</span>
              <span>Sat</span>
              <span>Sun</span>
            </div>

            {/* Day Cells */}
            <div className="grid grid-cols-7 gap-1.5 text-xs">
              {daysInMonth.map((day) => {
                const dayEvents = mockEvents.filter((e) => e.day === day);
                const isSelected = selectedDay === day;
                return (
                  <div
                    key={day}
                    onClick={() => setSelectedDay(isSelected ? null : day)}
                    className={`min-h-[64px] p-1.5 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${
                      isSelected
                        ? 'border-brand-600 bg-brand-50/40 ring-1 ring-brand-600'
                        : dayEvents.length > 0
                        ? 'border-slate-300 bg-white hover:border-brand-400'
                        : 'border-slate-100 bg-slate-50/50 hover:bg-slate-100/50 text-slate-400'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`text-xs font-semibold ${isSelected ? 'text-brand-700 font-bold' : 'text-slate-700'}`}>
                        {day}
                      </span>
                      {dayEvents.length > 0 && (
                        <span className="w-2 h-2 rounded-full bg-brand-600" />
                      )}
                    </div>

                    <div className="space-y-1 mt-1">
                      {dayEvents.slice(0, 1).map((ev) => (
                        <div
                          key={ev.id}
                          className={`text-[9px] font-medium px-1 py-0.5 rounded truncate ${
                            ev.type === 'invoice'
                              ? 'bg-rose-100 text-rose-700'
                              : ev.type === 'renewal'
                              ? 'bg-teal-100 text-teal-700'
                              : ev.type === 'trial'
                              ? 'bg-amber-100 text-amber-700'
                              : 'bg-blue-100 text-brand-700'
                          }`}
                        >
                          {ev.client}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Upcoming Agenda */}
        <Card className="lg:col-span-1">
          <CardContent className="p-5">
            <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center justify-between">
              <span>Timeline Agenda</span>
              <span className="text-xs font-normal text-slate-400">
                {filteredEvents.length} events
              </span>
            </h3>

            <div className="space-y-3 max-h-[460px] overflow-y-auto pr-1 divide-y divide-slate-100">
              {filteredEvents.map((ev) => (
                <div key={ev.id} className="pt-3 first:pt-0 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-brand-600">
                      {ev.date} • {ev.time}
                    </span>
                    <Badge
                      variant={
                        ev.status === 'action_required'
                          ? 'danger'
                          : ev.status === 'imminent'
                          ? 'warning'
                          : 'neutral'
                      }
                      size="sm"
                    >
                      {ev.type}
                    </Badge>
                  </div>
                  <h4 className="text-xs font-bold text-slate-900 leading-snug">
                    {ev.title}
                  </h4>
                  <p className="text-[11px] text-slate-500">
                    Client: <span className="font-medium text-slate-700">{ev.client}</span>
                  </p>
                  <p className="text-[11px] font-bold text-slate-900">
                    {ev.amount}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
