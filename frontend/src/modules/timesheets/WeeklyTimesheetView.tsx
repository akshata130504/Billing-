import { useState, useEffect, useCallback } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Calendar,
  Clock,
  Briefcase,
  Building2,
  Plus,
} from 'lucide-react';
import { timesheetService } from '../../services/timesheetService';
import type { WeeklyTimesheetResponse } from '../../types/api';
import { Button } from '../../components/common/Button';
import { LoadingState } from '../../components/common/LoadingState';
import { EmptyState } from '../../components/common/EmptyState';
import { formatMoney, toIsoDate } from '../../utils/format';

interface WeeklyTimesheetViewProps {
  onAddEntry: () => void;
}

export function WeeklyTimesheetView({ onAddEntry }: WeeklyTimesheetViewProps) {
  const [currentWeekStart, setCurrentWeekStart] = useState<Date>(() => {
    const d = new Date();
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1); // Monday
    const mon = new Date(d.setDate(diff));
    mon.setHours(0, 0, 0, 0);
    return mon;
  });

  const [weeklyData, setWeeklyData] = useState<WeeklyTimesheetResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const loadWeekly = useCallback(async () => {
    try {
      setLoading(true);
      const startStr = toIsoDate(currentWeekStart);
      const data = await timesheetService.weekly(startStr);
      setWeeklyData(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [currentWeekStart]);

  useEffect(() => {
    loadWeekly();
  }, [loadWeekly]);

  const handlePrevWeek = () => {
    const d = new Date(currentWeekStart);
    d.setDate(d.getDate() - 7);
    setCurrentWeekStart(d);
  };

  const handleNextWeek = () => {
    const d = new Date(currentWeekStart);
    d.setDate(d.getDate() + 7);
    setCurrentWeekStart(d);
  };

  const handleThisWeek = () => {
    const d = new Date();
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1);
    const mon = new Date(d.setDate(diff));
    mon.setHours(0, 0, 0, 0);
    setCurrentWeekStart(mon);
  };

  const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  const daysList = Array.from({ length: 7 }).map((_, i) => {
    const d = new Date(currentWeekStart);
    d.setDate(d.getDate() + i);
    const iso = toIsoDate(d);
    const dayNum = d.getDate();
    return { iso, label: `${dayNames[i]} ${dayNum}` };
  });

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden space-y-4 p-6">
      {/* Week Navigator */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <div className="flex items-center bg-slate-100 p-1 rounded-lg border border-slate-200">
            <button
              onClick={handlePrevWeek}
              className="p-1.5 hover:bg-white rounded text-slate-600 transition-colors"
              title="Previous Week"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={handleThisWeek}
              className="px-3 py-1 text-xs font-semibold hover:bg-white rounded text-slate-700 transition-colors"
            >
              Current Week
            </button>
            <button
              onClick={handleNextWeek}
              className="p-1.5 hover:bg-white rounded text-slate-600 transition-colors"
              title="Next Week"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
          <div className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
            <Calendar className="w-4 h-4 text-blue-600" />
            <span>
              {weeklyData ? `${weeklyData.week_start} — ${weeklyData.week_end}` : 'Loading week...'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500">Week Total:</span>
            <span className="font-bold text-slate-900 text-sm">
              {weeklyData?.total_hours || '0.00'}h
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-emerald-600 font-medium">Billable:</span>
            <span className="font-bold text-emerald-700 text-sm">
              {weeklyData?.billable_hours || '0.00'}h
            </span>
          </div>
          <Button variant="primary" size="sm" onClick={onAddEntry}>
            <Plus className="w-3.5 h-3.5 mr-1" />
            Log Entry
          </Button>
        </div>
      </div>

      {/* Weekly Matrix Table */}
      {loading ? (
        <div className="py-16">
          <LoadingState message="Loading weekly timesheet matrix..." />
        </div>
      ) : !weeklyData || weeklyData.rows.length === 0 ? (
        <div className="py-12">
          <EmptyState
            title="No time entries for this week"
            description="Log your project hours or navigate to another week."
            icon={<Clock className="w-8 h-8 text-slate-400" />}
            action={
              <Button variant="primary" size="sm" onClick={onAddEntry}>
                Log Time Entry
              </Button>
            }
          />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-600">
            <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
              <tr>
                <th className="px-4 py-3 min-w-[200px]">Project / Customer</th>
                <th className="px-3 py-3 min-w-[120px]">Member</th>
                {daysList.map((d) => (
                  <th key={d.iso} className="px-3 py-3 text-center min-w-[70px]">
                    {d.label}
                  </th>
                ))}
                <th className="px-4 py-3 text-right min-w-[90px]">Total</th>
                <th className="px-4 py-3 text-right min-w-[110px]">Billable Amt</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {weeklyData.rows.map((r) => (
                <tr key={r.key} className="hover:bg-slate-50/70 transition-colors">
                  <td className="px-4 py-3.5">
                    <div className="font-semibold text-slate-900 flex items-center gap-1.5">
                      <Briefcase className="w-3.5 h-3.5 text-blue-500 flex-shrink-0" />
                      <span>{r.project_name || 'General / Non-project'}</span>
                    </div>
                    {r.customer_name && (
                      <div className="text-xs text-slate-400 flex items-center gap-1 mt-0.5 pl-5">
                        <Building2 className="w-3 h-3 text-slate-300" />
                        <span>{r.customer_name}</span>
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3.5 text-xs text-slate-600 font-medium">
                    {r.user_name}
                  </td>
                  {daysList.map((d) => {
                    const hrs = r.daily_hours[d.iso];
                    const numHrs = parseFloat(hrs || '0');
                    return (
                      <td key={d.iso} className="px-3 py-3.5 text-center">
                        {numHrs > 0 ? (
                          <span className="inline-block px-2 py-1 rounded bg-blue-50 text-blue-700 font-bold text-xs border border-blue-100">
                            {hrs}h
                          </span>
                        ) : (
                          <span className="text-slate-300 text-xs">—</span>
                        )}
                      </td>
                    );
                  })}
                  <td className="px-4 py-3.5 text-right font-bold text-slate-900">
                    {r.total_hours}h
                  </td>
                  <td className="px-4 py-3.5 text-right font-semibold text-emerald-700">
                    {formatMoney(r.billable_amount)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-slate-50/90 font-bold text-slate-900 border-t-2 border-slate-200">
              <tr>
                <td className="px-4 py-3" colSpan={2}>
                  Daily Totals
                </td>
                {daysList.map((d) => {
                  const dayTotal = weeklyData.day_totals[d.iso] || '0.00';
                  return (
                    <td key={d.iso} className="px-3 py-3 text-center text-xs font-bold text-blue-700">
                      {parseFloat(dayTotal) > 0 ? `${dayTotal}h` : '—'}
                    </td>
                  );
                })}
                <td className="px-4 py-3 text-right text-sm text-slate-900">
                  {weeklyData.total_hours}h
                </td>
                <td className="px-4 py-3 text-right text-sm text-emerald-700">
                  {/* Aggregated sum */}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
