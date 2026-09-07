import { createContext, useContext, useState, useEffect, useMemo, useCallback, ReactNode } from 'react';
import { Expense, RecurringExpense } from './types';
import { initialExpenses, initialRecurringExpenses } from './mockExpenses';
import { useToast } from '../../components/common/Toast';

const STORAGE_EXPENSES_KEY = 'rooman_expenses_list_v1';
const STORAGE_RECURRING_KEY = 'rooman_expenses_recurring_v1';

export interface ExpensesSummary {
  total: number;
  billable: number;
  nonBillable: number;
  pending: number;
}

export interface RecurringSummary {
  activeProfiles: number;
  monthlyRecurring: number;
  billableRecurring: number;
  nextRun: string;
}

interface ExpensesContextType {
  expenses: Expense[];
  recurringExpenses: RecurringExpense[];
  summary: ExpensesSummary;
  recurringSummary: RecurringSummary;
  addExpense: (data: Omit<Expense, 'id' | 'createdAt'>) => Expense;
  updateExpense: (id: string, updates: Partial<Expense>) => void;
  deleteExpense: (id: string) => void;
  duplicateExpense: (id: string) => Expense;
  addToInvoice: (id: string) => void;
  addRecurringExpense: (data: Omit<RecurringExpense, 'id' | 'createdAt'>) => RecurringExpense;
  updateRecurringExpense: (id: string, updates: Partial<RecurringExpense>) => void;
  deleteRecurringExpense: (id: string) => void;
  toggleRecurringStatus: (id: string) => void;
  duplicateRecurringExpense: (id: string) => RecurringExpense;
  getExpenseById: (id: string) => Expense | undefined;
  getRecurringExpenseById: (id: string) => RecurringExpense | undefined;
}

const ExpensesContext = createContext<ExpensesContextType | undefined>(undefined);

export function ExpensesProvider({ children }: { children: ReactNode }) {
  const { showToast } = useToast();

  const [expenses, setExpenses] = useState<Expense[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_EXPENSES_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch (e) {
      console.error('Failed to load expenses from localStorage:', e);
    }
    return initialExpenses;
  });

  const [recurringExpenses, setRecurringExpenses] = useState<RecurringExpense[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_RECURRING_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch (e) {
      console.error('Failed to load recurring expenses from localStorage:', e);
    }
    return initialRecurringExpenses;
  });

  // Sync with localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_EXPENSES_KEY, JSON.stringify(expenses));
    } catch (e) {
      console.error('Failed to save expenses to localStorage:', e);
    }
  }, [expenses]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_RECURRING_KEY, JSON.stringify(recurringExpenses));
    } catch (e) {
      console.error('Failed to save recurring expenses to localStorage:', e);
    }
  }, [recurringExpenses]);

  // Compute horizontal summary metrics
  const summary: ExpensesSummary = useMemo(() => {
    let total = 0;
    let billable = 0;
    let nonBillable = 0;
    let pending = 0;

    for (const exp of expenses) {
      total += exp.amount;
      if (exp.billable) {
        billable += exp.amount;
      } else {
        nonBillable += exp.amount;
      }

      // conceptual pending is billable but not yet invoiced/reimbursed, or status is draft/recorded
      if (exp.billable && exp.status !== 'invoiced' && exp.status !== 'cancelled') {
        pending += exp.amount;
      }
    }

    return { total, billable, nonBillable, pending };
  }, [expenses]);

  // Compute recurring summary metrics
  const recurringSummary: RecurringSummary = useMemo(() => {
    const activeProfiles = recurringExpenses.filter((r) => r.status === 'active').length;
    let monthlyRecurring = 0;
    let billableRecurring = 0;

    for (const r of recurringExpenses) {
      if (r.status === 'active') {
        const monthlyEq =
          r.frequency === 'weekly'
            ? r.amount * 4.33
            : r.frequency === 'quarterly'
            ? r.amount / 3
            : r.frequency === 'yearly'
            ? r.amount / 12
            : r.amount;

        monthlyRecurring += monthlyEq;
        if (r.billable) {
          billableRecurring += monthlyEq;
        }
      }
    }

    // Find earliest upcoming next run
    const upcomingRuns = recurringExpenses
      .filter((r) => r.status === 'active' && r.nextRun)
      .map((r) => r.nextRun)
      .sort();

    const nextRun = upcomingRuns.length > 0 ? upcomingRuns[0] : 'None scheduled';

    return {
      activeProfiles,
      monthlyRecurring: Math.round(monthlyRecurring),
      billableRecurring: Math.round(billableRecurring),
      nextRun,
    };
  }, [recurringExpenses]);

  // CRUD for Expenses
  const addExpense = useCallback(
    (data: Omit<Expense, 'id' | 'createdAt'>): Expense => {
      const id = `EXP-2026-${String(expenses.length + 1).padStart(3, '0')}`;
      const newExpense: Expense = {
        ...data,
        id,
        createdAt: new Date().toISOString(),
      };
      setExpenses((prev) => [newExpense, ...prev]);
      showToast('success', 'Expense Recorded', `${newExpense.name} recorded successfully.`);
      return newExpense;
    },
    [expenses.length, showToast]
  );

  const updateExpense = useCallback(
    (id: string, updates: Partial<Expense>) => {
      setExpenses((prev) =>
        prev.map((item) => (item.id === id ? { ...item, ...updates } : item))
      );
      showToast('success', 'Expense Updated', 'Changes saved successfully.');
    },
    [showToast]
  );

  const deleteExpense = useCallback(
    (id: string) => {
      setExpenses((prev) => prev.filter((item) => item.id !== id));
      showToast('info', 'Expense Removed', 'Expense item has been deleted.');
    },
    [showToast]
  );

  const duplicateExpense = useCallback(
    (id: string): Expense => {
      const original = expenses.find((e) => e.id === id);
      if (!original) {
        throw new Error('Expense not found');
      }
      const newId = `EXP-2026-${String(expenses.length + 1).padStart(3, '0')}`;
      const duplicated: Expense = {
        ...original,
        id: newId,
        name: `${original.name} (Copy)`,
        date: new Date().toISOString().split('T')[0],
        status: 'draft',
        invoiceId: undefined,
        createdAt: new Date().toISOString(),
      };
      setExpenses((prev) => [duplicated, ...prev]);
      showToast('success', 'Expense Duplicated', `Created duplicate as ${newId}.`);
      return duplicated;
    },
    [expenses, showToast]
  );

  const addToInvoice = useCallback(
    (id: string) => {
      setExpenses((prev) =>
        prev.map((item) => {
          if (item.id === id) {
            const mockInvoiceNum = `INV-2026-00${Math.floor(Math.random() * 80) + 10}`;
            return {
              ...item,
              status: 'invoiced',
              invoiceId: mockInvoiceNum,
            };
          }
          return item;
        })
      );
      showToast('success', 'Associated with Invoice', 'Expense converted to invoice billing line.');
    },
    [showToast]
  );

  // CRUD for Recurring Expenses
  const addRecurringExpense = useCallback(
    (data: Omit<RecurringExpense, 'id' | 'createdAt'>): RecurringExpense => {
      const id = `REC-EXP-${String(recurringExpenses.length + 1).padStart(3, '0')}`;
      const newRec: RecurringExpense = {
        ...data,
        id,
        createdAt: new Date().toISOString(),
      };
      setRecurringExpenses((prev) => [newRec, ...prev]);
      showToast('success', 'Recurring Profile Created', `${newRec.name} schedule configured.`);
      return newRec;
    },
    [recurringExpenses.length, showToast]
  );

  const updateRecurringExpense = useCallback(
    (id: string, updates: Partial<RecurringExpense>) => {
      setRecurringExpenses((prev) =>
        prev.map((item) => (item.id === id ? { ...item, ...updates } : item))
      );
      showToast('success', 'Recurring Profile Updated', 'Schedule settings saved.');
    },
    [showToast]
  );

  const deleteRecurringExpense = useCallback(
    (id: string) => {
      setRecurringExpenses((prev) => prev.filter((item) => item.id !== id));
      showToast('info', 'Recurring Profile Removed', 'Recurring profile has been deleted.');
    },
    [showToast]
  );

  const toggleRecurringStatus = useCallback(
    (id: string) => {
      setRecurringExpenses((prev) =>
        prev.map((item) => {
          if (item.id === id) {
            const nextStatus = item.status === 'active' ? 'paused' : 'active';
            return { ...item, status: nextStatus };
          }
          return item;
        })
      );
      showToast('info', 'Status Toggled', 'Recurring profile state updated.');
    },
    [showToast]
  );

  const duplicateRecurringExpense = useCallback(
    (id: string): RecurringExpense => {
      const original = recurringExpenses.find((r) => r.id === id);
      if (!original) {
        throw new Error('Recurring expense not found');
      }
      const newId = `REC-EXP-${String(recurringExpenses.length + 1).padStart(3, '0')}`;
      const duplicated: RecurringExpense = {
        ...original,
        id: newId,
        name: `${original.name} (Copy)`,
        status: 'paused',
        createdAt: new Date().toISOString(),
      };
      setRecurringExpenses((prev) => [duplicated, ...prev]);
      showToast('success', 'Recurring Profile Duplicated', `Created copy as ${newId}.`);
      return duplicated;
    },
    [recurringExpenses, showToast]
  );

  const getExpenseById = useCallback(
    (id: string) => expenses.find((e) => e.id === id),
    [expenses]
  );

  const getRecurringExpenseById = useCallback(
    (id: string) => recurringExpenses.find((r) => r.id === id),
    [recurringExpenses]
  );

  return (
    <ExpensesContext.Provider
      value={{
        expenses,
        recurringExpenses,
        summary,
        recurringSummary,
        addExpense,
        updateExpense,
        deleteExpense,
        duplicateExpense,
        addToInvoice,
        addRecurringExpense,
        updateRecurringExpense,
        deleteRecurringExpense,
        toggleRecurringStatus,
        duplicateRecurringExpense,
        getExpenseById,
        getRecurringExpenseById,
      }}
    >
      {children}
    </ExpensesContext.Provider>
  );
}

export function useExpenses() {
  const context = useContext(ExpensesContext);
  if (!context) {
    throw new Error('useExpenses must be used within an ExpensesProvider');
  }
  return context;
}
