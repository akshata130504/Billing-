import { useState, useMemo } from 'react';
import { NavLink } from 'react-router-dom';
import { useExpenses } from './ExpensesContext';
import { RecurringExpense } from './types';
import { RecurringSummary } from './components/RecurringSummary';
import { RecurringExpenseTable } from './components/RecurringExpenseTable';
import { RecurringExpenseFormModal } from './components/RecurringExpenseFormModal';
import { DeleteExpenseModal } from './components/DeleteExpenseModal';
import { Plus, Search, Repeat } from 'lucide-react';

export function RecurringExpensesPage() {
  const {
    recurringExpenses,
    addRecurringExpense,
    updateRecurringExpense,
    deleteRecurringExpense,
    toggleRecurringStatus,
    duplicateRecurringExpense,
  } = useExpenses();

  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'paused' | 'ended'>('all');
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingExpense, setEditingExpense] = useState<RecurringExpense | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RecurringExpense | null>(null);

  const filteredRecurring = useMemo(() => {
    return recurringExpenses.filter((item) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchName = item.name.toLowerCase().includes(q);
        const matchId = item.id.toLowerCase().includes(q);
        const matchCust = (item.customer || '').toLowerCase().includes(q);
        const matchCat = item.category.toLowerCase().includes(q);
        if (!matchName && !matchId && !matchCust && !matchCat) return false;
      }

      if (statusFilter !== 'all' && item.status !== statusFilter) {
        return false;
      }

      return true;
    });
  }, [recurringExpenses, searchQuery, statusFilter]);

  const handleSave = (data: Omit<RecurringExpense, 'id' | 'createdAt'>) => {
    if (editingExpense) {
      updateRecurringExpense(editingExpense.id, data);
    } else {
      addRecurringExpense(data);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-1">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Recurring Expenses</h1>
            <span className="text-xs font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
              {filteredRecurring.length}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Automatically track recurring business expenses and recurring billable costs.
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            setEditingExpense(null);
            setIsFormOpen(true);
          }}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 shadow-2xs transition-colors self-start sm:self-auto"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>New Recurring Expense</span>
        </button>
      </div>

      {/* Sub-navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200/80">
        <NavLink
          to="/expenses"
          end
          className={({ isActive }) =>
            `inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold border-b-2 transition-colors -mb-px ${
              isActive
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`
          }
        >
          <span>All Expenses</span>
        </NavLink>
        <NavLink
          to="/expenses/recurring"
          className={({ isActive }) =>
            `inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold border-b-2 transition-colors -mb-px ${
              isActive
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`
          }
        >
          <Repeat className="w-3.5 h-3.5" />
          <span>Recurring Expenses</span>
        </NavLink>
      </div>

      {/* Recurring Summary Cards */}
      <RecurringSummary />

      {/* Filter Toolbar */}
      <div className="bg-white border border-slate-200/80 rounded-xl p-3 shadow-2xs flex flex-col sm:flex-row items-center justify-between gap-3">
        {/* Search */}
        <div className="relative w-full sm:max-w-xs">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search recurring profiles..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50/70 border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        {/* Status Filter Tabs */}
        <div className="inline-flex items-center p-0.5 bg-slate-100/90 rounded-lg border border-slate-200/80 self-end sm:self-auto">
          {(['all', 'active', 'paused', 'ended'] as const).map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => setStatusFilter(status)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md capitalize transition-colors ${
                statusFilter === status
                  ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              {status}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <RecurringExpenseTable
        recurringExpenses={filteredRecurring}
        onEdit={(item) => {
          setEditingExpense(item);
          setIsFormOpen(true);
        }}
        onDuplicate={(id) => duplicateRecurringExpense(id)}
        onDelete={(item) => setDeleteTarget(item)}
        onToggleStatus={(id) => toggleRecurringStatus(id)}
        onNew={() => {
          setEditingExpense(null);
          setIsFormOpen(true);
        }}
      />

      {/* Form Modal */}
      <RecurringExpenseFormModal
        isOpen={isFormOpen}
        onClose={() => {
          setIsFormOpen(false);
          setEditingExpense(null);
        }}
        onSave={handleSave}
        editingExpense={editingExpense}
      />

      {/* Delete Confirmation Modal */}
      <DeleteExpenseModal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteRecurringExpense(deleteTarget.id);
        }}
        title="Delete Recurring Profile"
        itemName={deleteTarget?.name || ''}
        description="This will permanently delete this recurring expense profile. No further scheduled expenses will be tracked."
      />
    </div>
  );
}
