import { useState } from 'react';
import { Project, ProjectExpense } from '../types';
import { formatINR } from '../format';
import { formatDate } from './ProjectTable';
import { AddExpenseModal } from './AddExpenseModal';
import { Button } from '../../../components/common/Button';
import { Badge } from '../../../components/common/Badge';
import { Plus, Receipt } from 'lucide-react';

interface ProjectExpensesProps {
  project: Project;
  onAddExpense: (expense: Omit<ProjectExpense, 'id' | 'projectId'>) => Promise<boolean> | boolean | void;
}

export function ProjectExpenses({ project, onAddExpense }: ProjectExpensesProps) {
  const [isExpenseModalOpen, setIsExpenseModalOpen] = useState(false);

  const expenses = project.expenseList || [];
  const totalExpense = expenses.reduce((acc, exp) => acc + exp.amount, 0);
  const billableExpense = expenses
    .filter((exp) => exp.billable)
    .reduce((acc, exp) => acc + exp.amount, 0);

  return (
    <div className="space-y-4">
      {/* Top action & metrics bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200/90 text-xs text-slate-700">
            Total Incurred: <strong className="text-slate-900 ml-1">{formatINR(totalExpense)}</strong>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-blue-50 border border-blue-100 text-xs text-brand-800">
            Billable Outlays: <strong className="ml-1">{formatINR(billableExpense)}</strong>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-amber-50 border border-amber-100 text-xs text-amber-800">
            Non-Billable: <strong className="ml-1">{formatINR(Math.max(0, totalExpense - billableExpense))}</strong>
          </div>
        </div>

        <Button
          variant="primary"
          size="sm"
          leadingIcon={<Plus className="w-3.5 h-3.5" />}
          onClick={() => setIsExpenseModalOpen(true)}
        >
          Add Expense
        </Button>
      </div>

      {/* Expenses Table */}
      <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs overflow-hidden">
        {expenses.length === 0 ? (
          <div className="p-12 text-center">
            <Receipt className="w-8 h-8 text-slate-400 mx-auto mb-2" />
            <h4 className="text-sm font-semibold text-slate-800">No project expenses recorded</h4>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              Track vendor software licenses, travel, hosting, or third-party costs tied directly to this engagement.
            </p>
            <div className="mt-4">
              <Button
                variant="outline"
                size="sm"
                leadingIcon={<Plus className="w-3.5 h-3.5" />}
                onClick={() => setIsExpenseModalOpen(true)}
              >
                Add First Expense
              </Button>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 border-b border-slate-200 text-slate-500 uppercase tracking-wider font-semibold text-[10.5px]">
                <tr>
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-3">Expense Title</th>
                  <th className="py-3 px-3">Category</th>
                  <th className="py-3 px-3 text-right">Amount</th>
                  <th className="py-3 px-3 text-center">Billable</th>
                  <th className="py-3 px-4 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {expenses.map((exp) => (
                  <tr key={exp.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3 px-4 text-slate-600 whitespace-nowrap tabular-nums">
                      {formatDate(exp.date)}
                    </td>
                    <td className="py-3 px-3 font-semibold text-slate-900">
                      {exp.title}
                    </td>
                    <td className="py-3 px-3 text-slate-600 whitespace-nowrap">
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 text-[11px] font-medium text-slate-700">
                        {exp.category}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-right font-semibold text-slate-900 tabular-nums whitespace-nowrap">
                      {formatINR(exp.amount)}
                    </td>
                    <td className="py-3 px-3 text-center whitespace-nowrap">
                      {exp.billable ? (
                        <Badge variant="success" size="sm">
                          Yes
                        </Badge>
                      ) : (
                        <Badge variant="neutral" size="sm">
                          No
                        </Badge>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center whitespace-nowrap">
                      <Badge
                        variant={
                          exp.status === 'invoiced'
                            ? 'primary'
                            : exp.status === 'reimbursed'
                            ? 'success'
                            : 'neutral'
                        }
                        size="sm"
                      >
                        {exp.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <AddExpenseModal
        isOpen={isExpenseModalOpen}
        onClose={() => setIsExpenseModalOpen(false)}
        onAddExpense={onAddExpense}
      />
    </div>
  );
}
