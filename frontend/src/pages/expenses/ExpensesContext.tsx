import { createContext, useContext, useState, useEffect, useMemo, useCallback, ReactNode } from 'react';
import { Expense, RecurringExpense } from './types';
import { expenseService } from '../../services/expenseService';
import { useToast } from '../../components/common/Toast';

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
  loading: boolean;
  refreshExpenses: () => Promise<void>;
  addExpense: (data: Omit<Expense, 'id' | 'createdAt'>) => Expense;
  importExpenses: (items: Omit<Expense, 'id' | 'createdAt'>[]) => number;
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

  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [recurringExpenses, setRecurringExpenses] = useState<RecurringExpense[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchAll = useCallback(async () => {
    try {
      setLoading(true);
      const [expList, recList] = await Promise.all([
        expenseService.list(),
        expenseService.listRecurring(),
      ]);
      setExpenses(expList);
      setRecurringExpenses(recList);
    } catch (e) {
      console.error('Failed to load expenses from server:', e);
      showToast('error', 'Failed to load expenses from server.');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

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
      const tempId = `EXP-TEMP-${Date.now()}`;
      const newExpense: Expense = {
        ...data,
        id: tempId,
        createdAt: new Date().toISOString(),
      };
      setExpenses((prev) => [newExpense, ...prev]);

      expenseService
        .create(data)
        .then((created) => {
          setExpenses((prev) =>
            prev.map((e) => (e.id === tempId ? created : e))
          );
          showToast('success', 'Expense Recorded', `${created.name} recorded successfully.`);
        })
        .catch((err) => {
          console.error('Failed to create expense on backend:', err);
          setExpenses((prev) => prev.filter((e) => e.id !== tempId));
          showToast('error', 'Failed to save expense to server.');
        });

      return newExpense;
    },
    [showToast]
  );

  const importExpenses = useCallback(
    (items: Omit<Expense, 'id' | 'createdAt'>[]): number => {
      if (!items.length) return 0;
      expenseService
        .batchImport(items)
        .then((count) => {
          showToast('success', 'Import Successful', `Successfully imported ${count} expense(s).`);
          fetchAll();
        })
        .catch((err) => {
          console.error('Failed to import expenses on backend:', err);
          showToast('error', 'Failed to import expenses to server.');
        });

      return items.length;
    },
    [fetchAll, showToast]
  );

  const updateExpense = useCallback(
    (id: string, updates: Partial<Expense>) => {
      setExpenses((prev) =>
        prev.map((item) => (item.id === id ? { ...item, ...updates } : item))
      );

      expenseService
        .update(id, updates)
        .then(() => {
          showToast('success', 'Expense Updated', 'Changes saved successfully.');
        })
        .catch((err) => {
          console.error('Failed to update expense on backend:', err);
          showToast('error', 'Failed to update expense on server.');
        });
    },
    [showToast]
  );

  const deleteExpense = useCallback(
    (id: string) => {
      const backup = expenses;
      setExpenses((prev) => prev.filter((item) => item.id !== id));

      expenseService
        .delete(id)
        .then(() => {
          showToast('info', 'Expense Removed', 'Expense item has been deleted.');
        })
        .catch((err) => {
          console.error('Failed to delete expense on backend:', err);
          setExpenses(backup);
          showToast('error', 'Failed to delete expense on server.');
        });
    },
    [expenses, showToast]
  );

  const duplicateExpense = useCallback(
    (id: string): Expense => {
      const original = expenses.find((e) => e.id === id);
      if (!original) {
        throw new Error('Expense not found');
      }
      return addExpense({
        ...original,
        name: `${original.name} (Copy)`,
        date: new Date().toISOString().split('T')[0],
        status: 'draft',
        invoiceId: undefined,
      });
    },
    [expenses, addExpense]
  );

  const addToInvoice = useCallback(
    (id: string) => {
      expenseService
        .addToInvoice(id)
        .then((updated) => {
          setExpenses((prev) =>
            prev.map((item) => (item.id === id ? updated : item))
          );
          showToast('success', 'Associated with Invoice', 'Expense converted to invoice billing line.');
        })
        .catch((err) => {
          console.error('Failed to associate expense with invoice on backend:', err);
          showToast('error', 'Failed to add expense to invoice.');
        });
    },
    [showToast]
  );

  // CRUD for Recurring Expenses
  const addRecurringExpense = useCallback(
    (data: Omit<RecurringExpense, 'id' | 'createdAt'>): RecurringExpense => {
      const tempId = `REC-TEMP-${Date.now()}`;
      const newRec: RecurringExpense = {
        ...data,
        id: tempId,
        createdAt: new Date().toISOString(),
      };
      setRecurringExpenses((prev) => [newRec, ...prev]);

      expenseService
        .createRecurring(data)
        .then((created) => {
          setRecurringExpenses((prev) =>
            prev.map((r) => (r.id === tempId ? created : r))
          );
          showToast('success', 'Recurring Profile Created', `${created.name} schedule configured.`);
        })
        .catch((err) => {
          console.error('Failed to create recurring expense on backend:', err);
          setRecurringExpenses((prev) => prev.filter((r) => r.id !== tempId));
          showToast('error', 'Failed to save recurring profile to server.');
        });

      return newRec;
    },
    [showToast]
  );

  const updateRecurringExpense = useCallback(
    (id: string, updates: Partial<RecurringExpense>) => {
      setRecurringExpenses((prev) =>
        prev.map((item) => (item.id === id ? { ...item, ...updates } : item))
      );

      expenseService
        .updateRecurring(id, updates)
        .then(() => {
          showToast('success', 'Recurring Profile Updated', 'Schedule settings saved.');
        })
        .catch((err) => {
          console.error('Failed to update recurring profile on backend:', err);
          showToast('error', 'Failed to update recurring profile on server.');
        });
    },
    [showToast]
  );

  const deleteRecurringExpense = useCallback(
    (id: string) => {
      const backup = recurringExpenses;
      setRecurringExpenses((prev) => prev.filter((item) => item.id !== id));

      expenseService
        .deleteRecurring(id)
        .then(() => {
          showToast('info', 'Recurring Profile Removed', 'Recurring profile has been deleted.');
        })
        .catch((err) => {
          console.error('Failed to delete recurring profile on backend:', err);
          setRecurringExpenses(backup);
          showToast('error', 'Failed to delete recurring profile from server.');
        });
    },
    [recurringExpenses, showToast]
  );

  const toggleRecurringStatus = useCallback(
    (id: string) => {
      expenseService
        .toggleRecurringStatus(id)
        .then((updated) => {
          setRecurringExpenses((prev) =>
            prev.map((item) => (item.id === id ? updated : item))
          );
          showToast('info', 'Status Toggled', 'Recurring profile state updated.');
        })
        .catch((err) => {
          console.error('Failed to toggle recurring status on backend:', err);
          showToast('error', 'Failed to update recurring status.');
        });
    },
    [showToast]
  );

  const duplicateRecurringExpense = useCallback(
    (id: string): RecurringExpense => {
      const original = recurringExpenses.find((r) => r.id === id);
      if (!original) {
        throw new Error('Recurring expense not found');
      }
      return addRecurringExpense({
        ...original,
        name: `${original.name} (Copy)`,
        status: 'paused',
      });
    },
    [recurringExpenses, addRecurringExpense]
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
        loading,
        refreshExpenses: fetchAll,
        addExpense,
        importExpenses,
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
