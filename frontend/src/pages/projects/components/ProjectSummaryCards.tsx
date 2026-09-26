import { Project } from '../types';
import { formatINR } from '../format';
import { Briefcase, CheckCircle2, Clock, CreditCard, Receipt } from 'lucide-react';

interface ProjectSummaryCardsProps {
  projects: Project[];
}

export function ProjectSummaryCards({ projects }: ProjectSummaryCardsProps) {
  const totalCount = projects.length;
  const activeCount = projects.filter((p) => p.status === 'active').length;
  const completedCount = projects.filter((p) => p.status === 'completed').length;
  const totalBilled = projects.reduce((acc, p) => acc + p.billed, 0);
  const totalExpenses = projects.reduce((acc, p) => acc + p.expenses, 0);

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs px-4 py-2.5 flex flex-wrap items-center justify-between gap-y-2 gap-x-6 text-xs text-slate-600">
      <div className="flex items-center gap-6 flex-wrap">
        <div className="flex items-center gap-2">
          <Briefcase className="w-3.5 h-3.5 text-slate-400" />
          <span>
            Total Projects: <strong className="text-slate-900 font-semibold">{totalCount}</strong>
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Clock className="w-3.5 h-3.5 text-emerald-600" />
          <span>
            Active: <strong className="text-emerald-700 font-semibold">{activeCount}</strong>
          </span>
        </div>

        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-3.5 h-3.5 text-blue-600" />
          <span>
            Completed: <strong className="text-slate-900 font-semibold">{completedCount}</strong>
          </span>
        </div>
      </div>

      <div className="flex items-center gap-6 flex-wrap">
        <div className="flex items-center gap-2">
          <CreditCard className="w-3.5 h-3.5 text-brand-600" />
          <span>
            Billed to Date: <strong className="text-slate-900 font-semibold">{formatINR(totalBilled)}</strong>
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Receipt className="w-3.5 h-3.5 text-slate-400" />
          <span>
            Project Expenses: <strong className="text-slate-700 font-medium">{formatINR(totalExpenses)}</strong>
          </span>
        </div>
      </div>
    </div>
  );
}
