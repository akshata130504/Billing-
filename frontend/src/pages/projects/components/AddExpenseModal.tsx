import React, { useState } from 'react';
import { ProjectExpense } from '../types';
import { Modal } from '../../../components/common/Modal';
import { Button } from '../../../components/common/Button';
import { Input } from '../../../components/common/Input';
import { Select } from '../../../components/common/Select';
import { validatePositiveMoney, parseStrictNumber } from '../../../utils/validation';
import { todayIso } from '../../../utils/format';

interface AddExpenseModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Resolve false to keep the modal open (the save failed and was already reported). */
  onAddExpense: (expense: Omit<ProjectExpense, 'id' | 'projectId'>) => Promise<boolean> | boolean | void;
}

export function AddExpenseModal({ isOpen, onClose, onAddExpense }: AddExpenseModalProps) {
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState<ProjectExpense['category']>('Infrastructure');
  const [date, setDate] = useState(() => todayIso());
  const [amount, setAmount] = useState('5000');
  const [billable, setBillable] = useState(true);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    if (!title.trim()) {
      setError('Expense title is required');
      return;
    }
    const amountError = validatePositiveMoney(amount, 'Amount');
    if (amountError) {
      setError(amountError);
      return;
    }
    const numAmount = parseStrictNumber(amount) as number;

    setError('');
    setSubmitting(true);
    try {
      const ok = await onAddExpense({
        title: title.trim(),
        category,
        date,
        amount: numAmount,
        billable,
        status: 'recorded',
      });
      if (ok !== false) onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Add Project Expense"
      description="Record infrastructure, tooling, or logistical outlays associated with this project"
      size="md"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" form="expense-form" isLoading={submitting} disabled={submitting}>
            Save Expense
          </Button>
        </>
      }
    >
      <form id="expense-form" onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <Input
              label="Expense Title / Merchant"
              required
              placeholder="e.g. AWS Cloud Cluster, Stock UI License"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          <div>
            <Select
              label="Category"
              value={category}
              onChange={(e) => setCategory(e.target.value as ProjectExpense['category'])}
              options={[
                { value: 'Infrastructure', label: 'Infrastructure' },
                { value: 'Software Licenses', label: 'Software Licenses' },
                { value: 'Travel & Lodging', label: 'Travel & Lodging' },
                { value: 'Hardware', label: 'Hardware' },
                { value: 'Consulting', label: 'Consulting' },
                { value: 'Miscellaneous', label: 'Miscellaneous' },
              ]}
            />
          </div>

          <div>
            <Input
              label="Date"
              type="date"
              required
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>

          <div className="sm:col-span-2">
            <Input
              label="Amount (₹)"
              type="number"
              min="1"
              required
              placeholder="e.g. 15000"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>

          <div className="sm:col-span-2">
            <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={billable}
                onChange={(e) => setBillable(e.target.checked)}
                className="rounded border-slate-300 text-brand-600 focus:ring-brand-500 w-4 h-4 cursor-pointer"
              />
              <span>Rebill to customer on invoice</span>
            </label>
          </div>
        </div>
      </form>
    </Modal>
  );
}
