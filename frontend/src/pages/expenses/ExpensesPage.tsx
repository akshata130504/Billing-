import { useState, useMemo } from 'react';
import { NavLink } from 'react-router-dom';
import { useExpenses } from './ExpensesContext';
import { Expense, ExpenseFilterState } from './types';
import { ExpenseSummary } from './components/ExpenseSummary';
import { ExpenseFilters } from './components/ExpenseFilters';
import { ExpenseTable } from './components/ExpenseTable';
import { ExpenseFormModal } from './components/ExpenseFormModal';
import { DeleteExpenseModal } from './components/DeleteExpenseModal';
import { Plus, UploadCloud, Receipt } from 'lucide-react';
import { useToast } from '../../components/common/Toast';

export function ExpensesPage() {
  const {
    expenses,
    addExpense,
    updateExpense,
    deleteExpense,
    duplicateExpense,
    addToInvoice,
  } = useExpenses();
  const { showToast } = useToast();

  // Filters State
  const [filters, setFilters] = useState<ExpenseFilterState>({
    searchQuery: '',
    status: 'all',
    customer: 'all',
    project: 'all',
    category: 'all',
    billable: 'all',
    sortBy: 'newest',
    viewMode: 'list',
  });

  // Modals state
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingExpense, setEditingExpense] = useState<Expense | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Expense | null>(null);

  // Available projects for dropdown
  const availableProjects = useMemo(() => {
    const set = new Set<string>();
    expenses.forEach((e) => {
      if (e.project && e.project !== '—') set.add(e.project);
    });
    return Array.from(set);
  }, [expenses]);

  // Filter and sort expenses
  const filteredExpenses = useMemo(() => {
    return expenses
      .filter((exp) => {
        // Search query
        if (filters.searchQuery.trim()) {
          const q = filters.searchQuery.toLowerCase();
          const matchName = exp.name.toLowerCase().includes(q);
          const matchId = exp.id.toLowerCase().includes(q);
          const matchCust = (exp.customer || '').toLowerCase().includes(q);
          const matchProj = (exp.project || '').toLowerCase().includes(q);
          const matchCat = exp.category.toLowerCase().includes(q);
          if (!matchName && !matchId && !matchCust && !matchProj && !matchCat) {
            return false;
          }
        }

        // Status
        if (filters.status !== 'all' && exp.status !== filters.status) {
          return false;
        }

        // Customer
        if (filters.customer !== 'all') {
          if (filters.customer === 'Internal' && exp.customer !== 'Internal') return false;
          if (filters.customer !== 'Internal' && exp.customer !== filters.customer) return false;
        }

        // Project
        if (filters.project !== 'all' && exp.project !== filters.project) {
          return false;
        }

        // Category
        if (filters.category !== 'all' && exp.category !== filters.category) {
          return false;
        }

        // Billable
        if (filters.billable === 'billable' && !exp.billable) return false;
        if (filters.billable === 'non_billable' && exp.billable) return false;

        return true;
      })
      .sort((a, b) => {
        if (filters.sortBy === 'oldest') {
          return new Date(a.date).getTime() - new Date(b.date).getTime();
        }
        if (filters.sortBy === 'amount_high') {
          return b.amount - a.amount;
        }
        if (filters.sortBy === 'amount_low') {
          return a.amount - b.amount;
        }
        // default newest
        return new Date(b.date).getTime() - new Date(a.date).getTime();
      });
  }, [expenses, filters]);

  const handleResetFilters = () => {
    setFilters({
      searchQuery: '',
      status: 'all',
      customer: 'all',
      project: 'all',
      category: 'all',
      billable: 'all',
      sortBy: 'newest',
      viewMode: filters.viewMode,
    });
  };

  const handleSaveExpense = (data: Omit<Expense, 'id' | 'createdAt'>) => {
    if (editingExpense) {
      updateExpense(editingExpense.id, data);
    } else {
      addExpense(data);
    }
  };

  const handleImportExpenses = () => {
    showToast('info', 'Import CSV / Excel', 'Upload CSV template to batch import corporate and vendor expenses.');
  };

  return (
    <div className="space-y-4">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-1">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Expenses</h1>
            <span className="text-xs font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
              {filteredExpenses.length}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Track operating costs, billable expenses and reimbursable expenses.
          </p>
        </div>

        {/* Primary & Secondary Actions */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleImportExpenses}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-700 bg-white border border-slate-200/80 hover:bg-slate-50 shadow-2xs transition-colors"
          >
            <UploadCloud className="w-3.5 h-3.5 text-slate-500" />
            <span>Import Expenses</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setEditingExpense(null);
              setIsFormOpen(true);
            }}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 shadow-2xs transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Record Expense</span>
          </button>
        </div>
      </div>

      {/* Module Sub-navigation Tabs */}
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
          <Receipt className="w-3.5 h-3.5" />
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
          <span>Recurring Expenses</span>
        </NavLink>
      </div>

      {/* Summary Area */}
      <ExpenseSummary />

      {/* Filters Toolbar */}
      <ExpenseFilters
        filters={filters}
        onChange={setFilters}
        onReset={handleResetFilters}
        availableProjects={availableProjects}
      />

      {/* Expense Table / Cards */}
      <ExpenseTable
        expenses={filteredExpenses}
        viewMode={filters.viewMode}
        onEdit={(exp) => {
          setEditingExpense(exp);
          setIsFormOpen(true);
        }}
        onDuplicate={(id) => duplicateExpense(id)}
        onDelete={(exp) => setDeleteTarget(exp)}
        onAddToInvoice={(id) => addToInvoice(id)}
        onRecordNew={() => {
          setEditingExpense(null);
          setIsFormOpen(true);
        }}
      />

      {/* Record / Edit Expense Modal */}
      <ExpenseFormModal
        isOpen={isFormOpen}
        onClose={() => {
          setIsFormOpen(false);
          setEditingExpense(null);
        }}
        onSave={handleSaveExpense}
        editingExpense={editingExpense}
      />

      {/* Delete Confirmation Modal */}
      <DeleteExpenseModal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteExpense(deleteTarget.id);
        }}
        title="Delete Expense"
        itemName={deleteTarget?.name || ''}
      />
    </div>
  );
}
