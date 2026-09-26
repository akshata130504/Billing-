import { useState } from 'react';
import { Project, TimesheetEntry } from '../types';
import { formatINR } from '../format';
import { formatDate } from './ProjectTable';
import { LogTimeModal } from './LogTimeModal';
import { Button } from '../../../components/common/Button';
import { Badge } from '../../../components/common/Badge';
import { Plus, Clock } from 'lucide-react';

interface ProjectTimesheetsProps {
  project: Project;
  onLogTime: (entry: Omit<TimesheetEntry, 'id' | 'projectId'>) => Promise<boolean> | boolean | void;
}

export function ProjectTimesheets({ project, onLogTime }: ProjectTimesheetsProps) {
  const [isLogModalOpen, setIsLogModalOpen] = useState(false);

  const timesheets = project.timesheets || [];
  const totalHours = timesheets.reduce((acc, t) => acc + t.hours, 0);
  const billableHours = timesheets
    .filter((t) => t.billable)
    .reduce((acc, t) => acc + t.hours, 0);
  const billableAmount = timesheets
    .filter((t) => t.billable)
    .reduce((acc, t) => acc + t.amount, 0);

  return (
    <div className="space-y-4">
      {/* Top action & metrics bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200/90 text-xs text-slate-700">
            Total Hours: <strong className="text-slate-900 ml-1">{totalHours}h</strong>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-100 text-xs text-emerald-800">
            Billable Hours: <strong className="ml-1">{billableHours}h</strong>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-blue-50 border border-blue-100 text-xs text-brand-800">
            Billable Value: <strong className="ml-1">{formatINR(billableAmount)}</strong>
          </div>
        </div>

        <Button
          variant="primary"
          size="sm"
          leadingIcon={<Plus className="w-3.5 h-3.5" />}
          onClick={() => setIsLogModalOpen(true)}
        >
          Log Time
        </Button>
      </div>

      {/* Timesheets Table */}
      <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs overflow-hidden">
        {timesheets.length === 0 ? (
          <div className="p-12 text-center">
            <Clock className="w-8 h-8 text-slate-400 mx-auto mb-2" />
            <h4 className="text-sm font-semibold text-slate-800">No time entries logged</h4>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              Start logging engineering hours to track billable utilization and milestone timelines.
            </p>
            <div className="mt-4">
              <Button
                variant="outline"
                size="sm"
                leadingIcon={<Plus className="w-3.5 h-3.5" />}
                onClick={() => setIsLogModalOpen(true)}
              >
                Log First Entry
              </Button>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 border-b border-slate-200 text-slate-500 uppercase tracking-wider font-semibold text-[10.5px]">
                <tr>
                  <th className="py-3 px-4">Employee</th>
                  <th className="py-3 px-3">Date</th>
                  <th className="py-3 px-3">Description</th>
                  <th className="py-3 px-3 text-right">Hours</th>
                  <th className="py-3 px-3 text-center">Billable</th>
                  <th className="py-3 px-4 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {timesheets.map((entry) => (
                  <tr key={entry.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3 px-4 font-semibold text-slate-900 flex items-center gap-2">
                      <div className="w-6 h-6 rounded-full bg-blue-100 text-brand-700 flex items-center justify-center font-bold text-[10px] shrink-0">
                        {entry.employee.charAt(0)}
                      </div>
                      <span>{entry.employee}</span>
                    </td>
                    <td className="py-3 px-3 text-slate-600 whitespace-nowrap tabular-nums">
                      {formatDate(entry.date)}
                    </td>
                    <td className="py-3 px-3 text-slate-700 min-w-[240px]">
                      {entry.description}
                    </td>
                    <td className="py-3 px-3 text-right font-semibold text-slate-900 tabular-nums">
                      {entry.hours} hrs
                    </td>
                    <td className="py-3 px-3 text-center whitespace-nowrap">
                      {entry.billable ? (
                        <Badge variant="success" size="sm">
                          Billable
                        </Badge>
                      ) : (
                        <Badge variant="neutral" size="sm">
                          Non-Billable
                        </Badge>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right font-medium text-slate-900 tabular-nums whitespace-nowrap">
                      {entry.billable ? formatINR(entry.amount) : '₹0'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <LogTimeModal
        isOpen={isLogModalOpen}
        onClose={() => setIsLogModalOpen(false)}
        onLogTime={onLogTime}
      />
    </div>
  );
}
