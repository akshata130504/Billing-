import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useNavigate } from 'react-router-dom';
import { Expense } from '../types';
import { formatINR } from '../format';
import {
  FileText,
  Paperclip,
  MoreVertical,
  Eye,
  Edit2,
  Copy,
  Trash2,
  Receipt,
  PlusCircle,
  Building,
  Briefcase,
  Calendar,
} from 'lucide-react';
import { usePageSpec } from '../../../appUi/usePageSpec';

interface ExpenseTableProps {
  expenses: Expense[];
  viewMode: 'list' | 'card';
  onEdit: (expense: Expense) => void;
  onDuplicate: (id: string) => void;
  onDelete: (expense: Expense) => void;
  onAddToInvoice: (id: string) => void;
  onRecordNew: () => void;
}

export function ExpenseTable({
  expenses,
  viewMode,
  onEdit,
  onDuplicate,
  onDelete,
  onAddToInvoice,
  onRecordNew,
}: ExpenseTableProps) {
  const ui = usePageSpec('expenses');
  const navigate = useNavigate();
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [menuPos, setMenuPos] = useState<{ top: number; right: number; openUp: boolean } | null>(null);

  const closeMenu = () => {
    setActiveMenuId(null);
    setMenuPos(null);
  };

  // A fixed-position menu would drift away from its button on scroll/resize; dismiss it instead.
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

  const getStatusBadge = (status: Expense['status']) => {
    switch (status) {
      case 'invoiced':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/80">
            Invoiced
          </span>
        );
      case 'billable':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-sky-50 text-sky-700 border border-sky-200/80">
            Billable
          </span>
        );
      case 'recorded':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            Recorded
          </span>
        );
      case 'reimbursed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-purple-50 text-purple-700 border border-purple-200/80">
            Reimbursed
          </span>
        );
      case 'draft':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-amber-50 text-amber-700 border border-amber-200/80">
            Draft
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-rose-50 text-rose-700 border border-rose-200/80">
            Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-medium bg-slate-100 text-slate-600">
            {status}
          </span>
        );
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  if (expenses.length === 0) {
    return (
      <div className="bg-white border border-slate-200/80 rounded-xl p-12 text-center shadow-2xs" {...ui.edit('empty')}>
        <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-3">
          <Receipt className="w-6 h-6" />
        </div>
        <h3 className="text-sm font-semibold text-slate-900">{ui.text('empty', 'none')}</h3>
        <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
          Try changing your search keywords, filter conditions or record a new business expense.
        </p>
        <div className="mt-4">
          <button
            type="button"
            onClick={onRecordNew}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-brand-600 hover:bg-brand-700 shadow-2xs transition-colors"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            <span>Record Expense</span>
          </button>
        </div>
      </div>
    );
  }

  // Card View
  if (viewMode === 'card') {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
        {expenses.map((expense) => (
          <div
            key={expense.id}
            className="bg-white border border-slate-200/80 rounded-xl p-4 shadow-2xs hover:shadow-sm hover:border-slate-300 transition-all flex flex-col justify-between group"
          >
            <div>
              {/* Header */}
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[10px] font-mono font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">
                      {expense.id}
                    </span>
                    {getStatusBadge(expense.status)}
                    {expense.billable ? (
                      <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-100">
                        Billable
                      </span>
                    ) : (
                      <span className="text-[10px] font-medium text-slate-500 bg-slate-50 px-1.5 py-0.5 rounded">
                        Non-Billable
                      </span>
                    )}
                  </div>
                  <Link
                    to={`/expenses/${expense.id}`}
                    className="mt-1.5 block text-sm font-semibold text-slate-900 hover:text-brand-600 truncate transition-colors"
                  >
                    {expense.name}
                  </Link>
                  <p className="text-xs text-slate-500 truncate mt-0.5">
                    {expense.category}
                  </p>
                </div>

                <span className="text-base font-bold text-slate-900 shrink-0">
                  {formatINR(expense.amount, expense.currency)}
                </span>
              </div>

              {/* Customer & Project metadata */}
              <div className="mt-3.5 pt-3 border-t border-slate-100 space-y-1.5 text-xs text-slate-600">
                <div className="flex items-center gap-2 truncate">
                  <Building className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span className="truncate">{expense.customer || 'Internal'}</span>
                </div>
                {expense.project && expense.project !== '—' && (
                  <div className="flex items-center gap-2 truncate">
                    <Briefcase className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span className="truncate text-slate-500">{expense.project}</span>
                  </div>
                )}
                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                  <span className="flex items-center gap-1.5">
                    <Calendar className="w-3 h-3" />
                    {formatDate(expense.date)}
                  </span>
                  {expense.receipt && (
                    <span className="inline-flex items-center gap-1 text-slate-500 font-medium">
                      <Paperclip className="w-3 h-3" />
                      Receipt
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Actions footer */}
            <div className="mt-3.5 pt-2.5 border-t border-slate-100 flex items-center justify-between gap-2">
              <Link
                to={`/expenses/${expense.id}`}
                className="text-xs font-medium text-brand-600 hover:text-brand-700"
              >
                View details →
              </Link>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onEdit(expense)}
                  className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                  title="Edit expense"
                >
                  <Edit2 className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onDuplicate(expense.id)}
                  className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                  title="Duplicate expense"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(expense)}
                  className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                  title="Delete expense"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Default List View (Table)
  return (
    <div className="bg-white border border-slate-200/80 rounded-xl overflow-hidden shadow-2xs">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-50/80 border-b border-slate-200 text-[11px] font-semibold text-slate-600 uppercase tracking-wider select-none" {...ui.edit('columns')}>
              {ui.shown('columns').map((col) => {
                const align = col.key === 'amount' || col.key === 'actions' ? 'text-right' : col.key === 'status' ? 'text-center' : '';
                const pad = col.key === 'expense' ? 'py-2.5 px-3.5' : 'py-2.5 px-3';
                return (
                  <th key={col.key} className={`${pad} ${align}`} {...ui.edit(`columns.${col.key}`)}>
                    {col.label}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {expenses.map((expense) => {
              const isMenuOpen = activeMenuId === expense.id;

              return (
                <tr
                  key={expense.id}
                  className="hover:bg-slate-50/70 transition-colors group cursor-pointer"
                  onClick={(e) => {
                    // avoid triggering if clicked action button/menu
                    if ((e.target as HTMLElement).closest('.action-menu-area')) return;
                    navigate(`/expenses/${expense.id}`);
                  }}
                >
                  {ui.shown('columns').map((col) => {
                    if (col.key === 'expense') {
                      return (
                        <td key="expense" className="py-2.5 px-3.5 min-w-[180px]">
                          <div className="flex items-center gap-2">
                            <div className="w-7 h-7 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center shrink-0">
                              <FileText className="w-3.5 h-3.5" />
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5">
                                <span className="font-semibold text-slate-900 group-hover:text-brand-600 transition-colors truncate">
                                  {expense.name}
                                </span>
                                {expense.receipt && (
                                  <span title="Has receipt attachment">
                                    <Paperclip className="w-3 h-3 text-slate-400 shrink-0" />
                                  </span>
                                )}
                              </div>
                              <span className="text-[10px] font-mono text-slate-400 block truncate">
                                {expense.id}
                              </span>
                            </div>
                          </div>
                        </td>
                      );
                    }
                    if (col.key === 'category') {
                      return (
                        <td key="category" className="py-2.5 px-3 text-slate-600 whitespace-nowrap">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700">
                            {expense.category}
                          </span>
                        </td>
                      );
                    }
                    if (col.key === 'customer') {
                      return (
                        <td key="customer" className="py-2.5 px-3 text-slate-700 whitespace-nowrap font-medium">
                          {expense.customer || 'Internal'}
                        </td>
                      );
                    }
                    if (col.key === 'project') {
                      return (
                        <td key="project" className="py-2.5 px-3 text-slate-500 whitespace-nowrap">
                          {expense.project && expense.project !== '—' ? (
                            <span className="text-slate-700 font-medium">
                              {expense.project}
                            </span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                      );
                    }
                    if (col.key === 'date') {
                      return (
                        <td key="date" className="py-2.5 px-3 text-slate-600 whitespace-nowrap">
                          {formatDate(expense.date)}
                        </td>
                      );
                    }
                    if (col.key === 'billable') {
                      return (
                        <td key="billable" className="py-2.5 px-3 whitespace-nowrap">
                          {expense.billable ? (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10.5px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/60">
                              Billable
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10.5px] font-medium bg-slate-100 text-slate-600">
                              Non-Billable
                            </span>
                          )}
                        </td>
                      );
                    }
                    if (col.key === 'amount') {
                      return (
                        <td key="amount" className="py-2.5 px-3 text-right whitespace-nowrap font-bold text-slate-900 font-mono">
                          {formatINR(expense.amount, expense.currency)}
                        </td>
                      );
                    }
                    if (col.key === 'status') {
                      return (
                        <td key="status" className="py-2.5 px-3 text-center whitespace-nowrap">
                          {getStatusBadge(expense.status)}
                        </td>
                      );
                    }
                    if (col.key === 'actions') {
                      return (
                        <td key="actions" className="py-2.5 px-3 text-right whitespace-nowrap action-menu-area relative">
                          <div className="flex items-center justify-end gap-1">
                            <Link
                              to={`/expenses/${expense.id}`}
                              className="p-1.5 text-slate-400 hover:text-brand-600 hover:bg-slate-100 rounded-lg transition-colors"
                              title="View Details"
                            >
                              <Eye className="w-3.5 h-3.5" />
                            </Link>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onEdit(expense);
                              }}
                              className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                              title="Edit Expense"
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
                                    closeMenu();
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
                                      closeMenu();
                                    }}
                                  />
                                  <div
                                    role="menu"
                                    className="fixed w-44 bg-white border border-slate-200 rounded-xl shadow-xl z-50 py-1 text-xs"
                                    style={{
                                      top: menuPos.openUp ? 'auto' : `${menuPos.top}px`,
                                      bottom: menuPos.openUp ? `${window.innerHeight - menuPos.top}px` : 'auto',
                                      right: `${menuPos.right}px`,
                                    }}
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    {expense.billable && expense.status !== 'invoiced' && (
                                      <button
                                        type="button"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          closeMenu();
                                          onAddToInvoice(expense.id);
                                        }}
                                        className="w-full px-3 py-1.5 text-left text-emerald-700 hover:bg-emerald-50 flex items-center gap-2 font-medium"
                                      >
                                        <Receipt className="w-3.5 h-3.5 text-emerald-600" />
                                        Add to Invoice
                                      </button>
                                    )}
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        closeMenu();
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
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        closeMenu();
                                        onDelete(expense);
                                      }}
                                      className="w-full px-3 py-1.5 text-left text-rose-600 hover:bg-rose-50 flex items-center gap-2 font-medium"
                                    >
                                      <Trash2 className="w-3.5 h-3.5" />
                                      Delete Expense
                                    </button>
                                  </div>
                                </>,
                                document.body
                              )}
                            </div>
                          </div>
                        </td>
                      );
                    }
                    return null;
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
