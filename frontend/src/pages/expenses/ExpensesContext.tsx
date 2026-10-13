import { createContext, useContext, useState, useEffect, useMemo, useCallback, ReactNode } from 'react';
import { Expense, RecurringExpense } from './types';
import { expenseService } from '../../services/expenseService';
import { tokenStorage } from '../../services/apiClient';
import { useToast } from '../../components/common/Toast';
import { toApiError } from '../../services/apiClient';
import { todayIso } from '../../utils/format';

/** Server message when there is one (e.g. "Customer not found"), else the fallback. */
function errorMessage(err: unknown, fallback: string): string {
  const message = toApiError(err).message;
  return message || fallback;
}

/** One figure per currency, base currency (INR) first. Amounts in different currencies are
 *  never added together: there is no exchange-rate policy to convert them. */
export type CurrencyAmounts = Array<{ currency: string; amount: number }>;

export interface ExpensesSummary {
  total: CurrencyAmounts;
  billable: CurrencyAmounts;
  nonBillable: CurrencyAmounts;
  pending: CurrencyAmounts;
  /** Expenses (not cancelled) dated in the current local calendar month. */
  thisMonth: CurrencyAmounts;
}

function byCurrency(totals: Map<string, number>): CurrencyAmounts {
  return [...totals.entries()]
    .map(([currency, amount]) => ({ currency, amount: Math.round(amount * 100) / 100 }))
    .sort((a, b) => (a.currency === 'INR' ? -1 : b.currency === 'INR' ? 1 : a.currency.localeCompare(b.currency)));
}

export interface RecurringSummary {
  activeProfiles: number;
  monthlyRecurring: CurrencyAmounts;
  billableRecurring: CurrencyAmounts;
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
  addToInvoice: (id: string, invoiceId?: string) => void;
  downloadReceipt: (id: string) => Promise<void>;
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
    if (!tokenStorage.hasSession()) {
      setExpenses([]);
      setRecurringExpenses([]);
      setLoading(false);
      return;
    }
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
    if (!tokenStorage.hasSession()) {
      setLoading(false);
      return;
    }
    fetchAll();
  }, [fetchAll]);

  // Compute horizontal summary metrics
  const summary: ExpensesSummary = useMemo(() => {
    const total = new Map<string, number>();
    const billable = new Map<string, number>();
    const nonBillable = new Map<string, number>();
    const pending = new Map<string, number>();
    const thisMonth = new Map<string, number>();
    const add = (m: Map<string, number>, currency: string, amount: number) => m.set(currency, (m.get(currency) ?? 0) + amount);
    // Expense dates are plain YYYY-MM-DD calendar dates: compare against the local month.
    const monthPrefix = todayIso().slice(0, 7);

    for (const exp of expenses) {
      const currency = (exp.currency || 'INR').toUpperCase();
      add(total, currency, exp.amount);
      if (exp.billable) {
        add(billable, currency, exp.amount);
      } else {
        add(nonBillable, currency, exp.amount);
      }

      if (exp.billable && exp.status !== 'invoiced' && exp.status !== 'cancelled') {
        add(pending, currency, exp.amount);
      }

      if (exp.status !== 'cancelled' && (exp.date || '').slice(0, 7) === monthPrefix) {
        add(thisMonth, currency, exp.amount);
      }
    }

    return {
      total: byCurrency(total),
      billable: byCurrency(billable),
      nonBillable: byCurrency(nonBillable),
      pending: byCurrency(pending),
      thisMonth: byCurrency(thisMonth),
    };
  }, [expenses]);

  // Compute recurring summary metrics
  const recurringSummary: RecurringSummary = useMemo(() => {
    const activeProfiles = recurringExpenses.filter((r) => r.status === 'active').length;
    const monthlyRecurring = new Map<string, number>();
    const billableRecurring = new Map<string, number>();

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

        const currency = (r.currency || 'INR').toUpperCase();
        monthlyRecurring.set(currency, (monthlyRecurring.get(currency) ?? 0) + monthlyEq);
        if (r.billable) {
          billableRecurring.set(currency, (billableRecurring.get(currency) ?? 0) + monthlyEq);
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
      monthlyRecurring: byCurrency(monthlyRecurring),
      billableRecurring: byCurrency(billableRecurring),
      nextRun,
    };
  }, [recurringExpenses]);

  // CRUD for Expenses
  const addExpense = useCallback(
    (data: Omit<Expense, 'id' | 'createdAt'>): Expense => {
      const { receiptFile, ...fields } = data;
      const tempId = `EXP-TEMP-${Date.now()}`;
      const newExpense: Expense = {
        ...fields,
        id: tempId,
        createdAt: new Date().toISOString(),
      };
      setExpenses((prev) => [newExpense, ...prev]);

      expenseService
        .create(fields)
        .then(async (created) => {
          setExpenses((prev) =>
            prev.map((e) => (e.id === tempId ? created : e))
          );
          showToast('success', 'Expense Recorded', `${created.name} recorded successfully.`);
          if (receiptFile) {
            try {
              const withReceipt = await expenseService.uploadReceipt(created.id, receiptFile);
              setExpenses((prev) => prev.map((e) => (e.id === created.id ? withReceipt : e)));
            } catch (err) {
              showToast('error', 'Receipt not uploaded', errorMessage(err, 'The expense was saved without its receipt.'));
            }
          }
        })
        .catch((err) => {
          setExpenses((prev) => prev.filter((e) => e.id !== tempId));
          showToast('error', 'Failed to save expense', errorMessage(err, 'Failed to save expense to server.'));
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
      const { receiptFile, ...fields } = updates;
      const backup = expenses.find((item) => item.id === id);
      setExpenses((prev) =>
        prev.map((item) => (item.id === id ? { ...item, ...fields } : item))
      );

      expenseService
        .update(id, fields)
        .then(async (saved) => {
          let latest = saved;
          if (receiptFile) {
            try {
              latest = await expenseService.uploadReceipt(id, receiptFile);
            } catch (err) {
              showToast('error', 'Receipt not uploaded', errorMessage(err, 'Changes were saved without the new receipt.'));
            }
          }
          setExpenses((prev) => prev.map((item) => (item.id === id ? latest : item)));
          showToast('success', 'Expense Updated', 'Changes saved successfully.');
        })
        .catch((err) => {
          if (backup) {
            setExpenses((prev) => prev.map((item) => (item.id === id ? backup : item)));
          }
          showToast('error', 'Failed to update expense', errorMessage(err, 'Failed to update expense on server.'));
        });
    },
    [expenses, showToast]
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
        date: todayIso(),
        status: 'draft',
        invoiceId: undefined,
        receipt: undefined,
        hasReceipt: false,
        receiptFile: null,
      });
    },
    [expenses, addExpense]
  );

  const addToInvoice = useCallback(
    (id: string, invoiceId?: string) => {
      expenseService
        .addToInvoice(id, invoiceId)
        .then((updated) => {
          setExpenses((prev) =>
            prev.map((item) => (item.id === id ? updated : item))
          );
          showToast('success', 'Added to Invoice', 'The expense is now a line on a draft invoice.');
        })
        .catch((err) => {
          showToast('error', 'Failed to add expense to invoice', errorMessage(err, 'Failed to add expense to invoice.'));
        });
    },
    [showToast]
  );

  const downloadReceipt = useCallback(
    async (id: string) => {
      const expense = expenses.find((e) => e.id === id);
      try {
        await expenseService.downloadReceipt(id, expense?.receipt?.fileName || 'receipt');
      } catch (err) {
        showToast('error', 'Download failed', errorMessage(err, 'Could not download the receipt.'));
      }
    },
    [expenses, showToast]
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
        downloadReceipt,
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
