import { Project } from '../types';
import { formatINR } from '../format';
import { Briefcase, CheckCircle2, Clock, CreditCard, Receipt } from 'lucide-react';
import { usePageSpec } from '../../../appUi/usePageSpec';

interface ProjectSummaryCardsProps {
  projects: Project[];
}

export function ProjectSummaryCards({ projects }: ProjectSummaryCardsProps) {
  const ui = usePageSpec('projects');
  const totalCount = projects.length;
  const activeCount = projects.filter((p) => p.status === 'active').length;
  const completedCount = projects.filter((p) => p.status === 'completed').length;
  const totalBilled = projects.reduce((acc, p) => acc + p.billed, 0);
  const totalExpenses = projects.reduce((acc, p) => acc + p.expenses, 0);

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs px-4 py-2.5 flex flex-wrap items-center justify-between gap-y-2 gap-x-6 text-xs text-slate-600" {...ui.edit('kpis')}>
      <div className="flex items-center gap-6 flex-wrap">
        {ui.render('kpis', {
          total: (item, edit) => (
            <div key="total" className="flex items-center gap-2" {...edit}>
              <Briefcase className="w-3.5 h-3.5 text-slate-400" />
              <span>
                {item.label}: <strong className="text-slate-900 font-semibold">{totalCount}</strong>
              </span>
            </div>
          ),
          active: (item, edit) => (
            <div key="active" className="flex items-center gap-2" {...edit}>
              <Clock className="w-3.5 h-3.5 text-emerald-600" />
              <span>
                {item.label}: <strong className="text-emerald-700 font-semibold">{activeCount}</strong>
              </span>
            </div>
          ),
          completed: (item, edit) => (
            <div key="completed" className="flex items-center gap-2" {...edit}>
              <CheckCircle2 className="w-3.5 h-3.5 text-blue-600" />
              <span>
                {item.label}: <strong className="text-slate-900 font-semibold">{completedCount}</strong>
              </span>
            </div>
          ),
          billed: (item, edit) => (
            <div key="billed" className="flex items-center gap-2" {...edit}>
              <CreditCard className="w-3.5 h-3.5 text-brand-600" />
              <span>
                {item.label}: <strong className="text-slate-900 font-semibold">{formatINR(totalBilled)}</strong>
              </span>
            </div>
          ),
          expenses: (item, edit) => (
            <div key="expenses" className="flex items-center gap-2" {...edit}>
              <Receipt className="w-3.5 h-3.5 text-slate-400" />
              <span>
                {item.label}: <strong className="text-slate-700 font-medium">{formatINR(totalExpenses)}</strong>
              </span>
            </div>
          ),
        })}
      </div>
    </div>
  );
}
