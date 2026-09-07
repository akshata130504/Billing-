import { Project } from '../types';
import { formatINR } from '../mockProjects';
import { formatDate, getBillingMethodLabel } from './ProjectTable';
import { Card, CardContent } from '../../../components/common/Card';
import {
  Building2,
  Calendar,
  User,
  Clock,
} from 'lucide-react';

interface ProjectOverviewProps {
  project: Project;
}

export function ProjectOverview({ project }: ProjectOverviewProps) {
  const profit = project.billed - project.expenses;
  const unbilledAmount = Math.max(0, project.budget - project.billed);
  const totalHours = (project.timesheets || []).reduce((acc, t) => acc + t.hours, 0);
  const billableHours = (project.timesheets || [])
    .filter((t) => t.billable)
    .reduce((acc, t) => acc + t.hours, 0);

  return (
    <div className="space-y-6">
      {/* Top Split: Project Details & Compact Billing Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Project Details */}
        <Card>
          <CardContent className="p-5 space-y-3.5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Project Details
            </h3>

            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between py-1 border-b border-slate-100">
                <span className="text-slate-500">Customer</span>
                <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                  <Building2 className="w-3.5 h-3.5 text-slate-400" />
                  {project.customer}
                </span>
              </div>

              <div className="flex items-center justify-between py-1 border-b border-slate-100">
                <span className="text-slate-500">Billing Method</span>
                <span className="font-semibold text-slate-800">
                  {getBillingMethodLabel(project.billingMethod)}
                </span>
              </div>

              <div className="flex items-center justify-between py-1 border-b border-slate-100">
                <span className="text-slate-500">Contract Duration</span>
                <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                  {formatDate(project.startDate)} – {formatDate(project.endDate)}
                </span>
              </div>

              <div className="flex items-center justify-between py-1 border-b border-slate-100">
                <span className="text-slate-500">Project Budget</span>
                <span className="font-bold text-slate-900 tabular-nums">
                  {formatINR(project.budget)}
                </span>
              </div>

              {project.projectManager && (
                <div className="flex items-center justify-between py-1">
                  <span className="text-slate-500">Lead / Manager</span>
                  <span className="font-medium text-slate-800 flex items-center gap-1.5">
                    <User className="w-3.5 h-3.5 text-slate-400" />
                    {project.projectManager}
                  </span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Billing Summary */}
        <Card>
          <CardContent className="p-5 space-y-3.5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Billing Summary
            </h3>

            <div className="grid grid-cols-3 gap-3">
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
                <span className="text-[10.5px] font-semibold text-slate-400 uppercase block">
                  Billed
                </span>
                <div className="text-base font-bold text-slate-900 mt-1 tabular-nums">
                  {formatINR(project.billed)}
                </div>
                <span className="text-[10px] text-slate-500 mt-0.5 block">Invoiced</span>
              </div>

              <div className="p-3 rounded-xl bg-blue-50/70 border border-blue-100">
                <span className="text-[10.5px] font-semibold text-brand-600 uppercase block">
                  Unbilled
                </span>
                <div className="text-base font-bold text-brand-900 mt-1 tabular-nums">
                  {formatINR(unbilledAmount)}
                </div>
                <span className="text-[10px] text-brand-700 mt-0.5 block">Remaining</span>
              </div>

              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
                <span className="text-[10.5px] font-semibold text-slate-400 uppercase block">
                  Expenses
                </span>
                <div className="text-base font-bold text-slate-700 mt-1 tabular-nums">
                  {formatINR(project.expenses)}
                </div>
                <span className="text-[10px] text-slate-500 mt-0.5 block">Costs</span>
              </div>
            </div>

            <div className="pt-2 text-xs text-slate-600 flex items-center justify-between border-t border-slate-100">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                Logged Hours: <strong className="text-slate-900">{totalHours}h</strong> ({billableHours}h billable)
              </span>
              <span>
                Invoices Issued: <strong className="text-slate-900">{(project.invoices || []).length}</strong>
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Secondary Section: Description & Profitability */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Description & Scope */}
        <div className="md:col-span-2">
          <Card>
            <CardContent className="p-5 space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Scope & Deliverables
              </h4>
              <p className="text-xs sm:text-sm text-slate-700 leading-relaxed">
                {project.description || 'No description entered for this project.'}
              </p>

              {project.notes && (
                <div className="mt-3 pt-3 border-t border-slate-100">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase block mb-1">
                    Engagement Notes
                  </span>
                  <p className="text-xs text-slate-600 italic bg-slate-50 p-2.5 rounded-lg border border-slate-200/60">
                    {project.notes}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Secondary Financial Calculation */}
        <div>
          <Card className="border-slate-200/90">
            <CardContent className="p-5 space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Financial Health
              </h4>

              <div className="space-y-2 text-xs">
                <div className="flex justify-between text-slate-600">
                  <span>Gross Billed:</span>
                  <span className="font-semibold text-slate-900 tabular-nums">{formatINR(project.billed)}</span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Total Expenses:</span>
                  <span className="font-semibold text-slate-700 tabular-nums">– {formatINR(project.expenses)}</span>
                </div>
                <div className="pt-2 border-t border-slate-100 flex justify-between font-bold">
                  <span className="text-slate-900">Net Profit:</span>
                  <span className={profit >= 0 ? 'text-emerald-700 tabular-nums' : 'text-rose-600 tabular-nums'}>
                    {formatINR(profit)}
                  </span>
                </div>
              </div>

              <p className="text-[11px] text-slate-400 mt-2">
                Calculated as total billed revenue less direct recorded expenses.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
