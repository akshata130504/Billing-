import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { RecurringExpense } from '../types';
import { formatINR } from '../format';
import {
  Repeat,
  MoreVertical,
  Edit2,
  Copy,
  Trash2,
  Play,
  Pause,
  PlusCircle,
} from 'lucide-react';

interface RecurringExpenseTableProps {
  recurringExpenses: RecurringExpense[];
  onEdit: (expense: RecurringExpense) => void;
  onDuplicate: (id: string) => void;
  onDelete: (expense: RecurringExpense) => void;
  onToggleStatus: (id: string) => void;
  onNew: () => void;
}

export function RecurringExpenseTable({
  recurringExpenses,
  onEdit,
  onDuplicate,
  onDelete,
  onToggleStatus,
  onNew,
}: RecurringExpenseTableProps) {
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [menuPos, setMenuPos] = useState<{ top: number; right: number; openUp: boolean } | null>(null);

  useEffect(() => {
    if (!activeMenuId) return;
    const handleDismiss = () => {
      setActiveMenuId(null);
      setMenuPos(null);
    };
    window.addEventListener('scroll', handleDismiss, true);
    window.addEventListener('resize', handleDismiss);
    return () => {
      window.removeEventListener('scroll', handleDismiss, true);
      window.removeEventListener('resize', handleDismiss);
    };
  }, [activeMenuId]);

  const getStatusBadge = (status: RecurringExpense['status']) => {
    switch (status) {
      case 'active':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/80">
            Active
          </span>
        );
      case 'paused':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-amber-50 text-amber-700 border border-amber-200/80">
            Paused
          </span>
        );
      case 'ended':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
            Ended
          </span>
        );
      default:
        return null;
    }
  };

  const getFrequencyBadge = (freq: RecurringExpense['frequency']) => {
    const map: Record<string, string> = {
      weekly: 'Weekly',
      monthly: 'Monthly',
      quarterly: 'Quarterly',
      yearly: 'Yearly',
    };
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-brand-50 text-brand-700 border border-brand-100">
        {map[freq] || freq}
      </span>
    );
  };

  if (recurringExpenses.length === 0) {
    return (
      <div className="bg-white border border-slate-200/80 rounded-xl p-12 text-center shadow-2xs">
        <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-3">
          <Repeat className="w-6 h-6" />
        </div>
        <h3 className="text-sm font-semibold text-slate-900">No recurring expense profiles</h3>
        <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
          Set up automated schedules for recurring subscriptions, utilities, and retainer cloud costs.
        </p>
        <div className="mt-4">
          <button
            type="button"
            onClick={onNew}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-brand-600 hover:bg-brand-700 shadow-2xs transition-colors"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            <span>New Recurring Expense</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl overflow-hidden shadow-2xs min-h-[260px]">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-50/80 border-b border-slate-200 text-[11px] font-semibold text-slate-600 uppercase tracking-wider select-none">
              <th className="py-2.5 px-3.5">Expense</th>
              <th className="py-2.5 px-3">Category</th>
              <th className="py-2.5 px-3">Frequency</th>
              <th className="py-2.5 px-3">Customer</th>
              <th className="py-2.5 px-3">Project</th>
              <th className="py-2.5 px-3 text-right">Amount</th>
              <th className="py-2.5 px-3">Next Run</th>
              <th className="py-2.5 px-3 text-center">Status</th>
              <th className="py-2.5 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {recurringExpenses.map((expense) => {
              const isMenuOpen = activeMenuId === expense.id;

              return (
                <tr
                  key={expense.id}
                  className="hover:bg-slate-50/70 transition-colors group"
                >
                  {/* Expense Name & ID */}
                  <td className="py-2.5 px-3.5 min-w-[170px]">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-lg bg-sky-50 text-sky-600 flex items-center justify-center shrink-0">
                        <Repeat className="w-3.5 h-3.5" />
                      </div>
                      <div className="min-w-0">
                        <span className="font-semibold text-slate-900 block truncate">
                          {expense.name}
                        </span>
                        <span className="text-[10px] font-mono text-slate-400 block truncate">
                          {expense.id}
                        </span>
                      </div>
                    </div>
                  </td>

                  {/* Category */}
                  <td className="py-2.5 px-3 text-slate-600 whitespace-nowrap">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700">
                      {expense.category}
                    </span>
                  </td>

                  {/* Frequency */}
                  <td className="py-2.5 px-3 whitespace-nowrap">
                    {getFrequencyBadge(expense.frequency)}
                  </td>

                  {/* Customer */}
                  <td className="py-2.5 px-3 text-slate-700 whitespace-nowrap font-medium">
                    {expense.customer || 'Internal'}
                  </td>

                  {/* Project */}
                  <td className="py-2.5 px-3 text-slate-500 whitespace-nowrap">
                    {expense.project && expense.project !== '—' ? (
                      <span className="text-slate-700 font-medium">{expense.project}</span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>

                  {/* Amount */}
                  <td className="py-2.5 px-3 text-right whitespace-nowrap font-bold text-slate-900 font-mono">
                    {formatINR(expense.amount, expense.currency)}
                  </td>

                  {/* Next Run */}
                  <td className="py-2.5 px-3 text-slate-600 whitespace-nowrap">
                    {expense.nextRun}
                  </td>

                  {/* Status */}
                  <td className="py-2.5 px-3 text-center whitespace-nowrap">
                    {getStatusBadge(expense.status)}
                  </td>

                  {/* Actions */}
                  <td className="py-2.5 px-3 text-right whitespace-nowrap relative">
                    <div className="flex items-center justify-end gap-1">
                      {/* Quick Pause / Resume button */}
                      <button
                        type="button"
                        onClick={() => onToggleStatus(expense.id)}
                        className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                        title={expense.status === 'active' ? 'Pause schedule' : 'Resume schedule'}
                      >
                        {expense.status === 'active' ? (
                          <Pause className="w-3.5 h-3.5 text-amber-600" />
                        ) : (
                          <Play className="w-3.5 h-3.5 text-emerald-600" />
                        )}
                      </button>

                      <button
                        type="button"
                        onClick={() => onEdit(expense)}
                        className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                        title="Edit profile"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>

                      {/* Dropdown Menu Toggle */}
                      <div className="relative inline-block text-left">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (isMenuOpen) {
                              setActiveMenuId(null);
                              setMenuPos(null);
                            } else {
                              const rect = e.currentTarget.getBoundingClientRect();
                              const spaceBelow = window.innerHeight - rect.bottom;
                              const openUp = spaceBelow < 150 && rect.top > 150;
                              setMenuPos({
                                top: openUp ? rect.top - 4 : rect.bottom + 4,
                                right: Math.max(8, window.innerWidth - rect.right),
                                openUp,
                              });
                              setActiveMenuId(expense.id);
                            }
                          }}
                          className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                          title="More Actions"
                        >
                          <MoreVertical className="w-3.5 h-3.5" />
                        </button>

                        {/* Dropdown Menu Rendered via Portal */}
                        {isMenuOpen && menuPos && createPortal(
                          <>
                            <div
                              className="fixed inset-0 z-50 bg-transparent"
                              onClick={(e) => {
                                e.stopPropagation();
                                setActiveMenuId(null);
                                setMenuPos(null);
                              }}
                            />
                            <div
                              className="fixed w-44 bg-white border border-slate-200 rounded-xl shadow-xl z-50 py-1 text-xs"
                              style={{
                                top: menuPos.openUp ? 'auto' : `${menuPos.top}px`,
                                bottom: menuPos.openUp ? `${window.innerHeight - menuPos.top}px` : 'auto',
                                right: `${menuPos.right}px`,
                              }}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <button
                                type="button"
                                onClick={() => {
                                  setActiveMenuId(null);
                                  setMenuPos(null);
                                  onToggleStatus(expense.id);
                                }}
                                className="w-full px-3 py-1.5 text-left text-slate-700 hover:bg-slate-50 flex items-center gap-2"
                              >
                                {expense.status === 'active' ? (
                                  <>
                                    <Pause className="w-3.5 h-3.5 text-amber-600" />
                                    Pause Schedule
                                  </>
                                ) : (
                                  <>
                                    <Play className="w-3.5 h-3.5 text-emerald-600" />
                                    Resume Schedule
                                  </>
                                )}
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setActiveMenuId(null);
                                  setMenuPos(null);
                                  onDuplicate(expense.id);
                                }}
                                className="w-full px-3 py-1.5 text-left text-slate-700 hover:bg-slate-50 flex items-center gap-2"
                              >
                                <Copy className="w-3.5 h-3.5 text-slate-400" />
                                Duplicate
                              </button>
                              <div className="my-1 border-t border-slate-100" />
                              <button
                                type="button"
                                onClick={() => {
                                  setActiveMenuId(null);
                                  setMenuPos(null);
                                  onDelete(expense);
                                }}
                                className="w-full px-3 py-1.5 text-left text-rose-600 hover:bg-rose-50 flex items-center gap-2 font-medium"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                                Delete Profile
                              </button>
                            </div>
                          </>,
                          document.body
                        )}
                      </div>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
