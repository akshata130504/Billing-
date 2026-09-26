import React, { useState } from 'react';
import { TimesheetEntry } from '../types';
import { Modal } from '../../../components/common/Modal';
import { Button } from '../../../components/common/Button';
import { Input } from '../../../components/common/Input';
import { validateDescription, validateNonNegativeMoney, parseStrictNumber } from '../../../utils/validation';
import { useAuth } from '../../../hooks/useAuth';

interface LogTimeModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Resolve false to keep the modal open (the save failed and was already reported). */
  onLogTime: (entry: Omit<TimesheetEntry, 'id' | 'projectId'>) => Promise<boolean> | boolean | void;
}

export function LogTimeModal({ isOpen, onClose, onLogTime }: LogTimeModalProps) {
  // Time is always logged as the signed-in user (the API records the caller).
  const { user } = useAuth();
  const employee = user?.full_name || user?.email || 'You';
  const [submitting, setSubmitting] = useState(false);
  const [date, setDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [description, setDescription] = useState('');
  const [hours, setHours] = useState('4.0');
  const [billable, setBillable] = useState(true);
  const [hourlyRate, setHourlyRate] = useState('500');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    const descriptionError = validateDescription(description, 500, 'Work description');
    if (descriptionError) {
      setError(descriptionError);
      return;
    }
    const numHours = parseStrictNumber(hours);
    if (numHours === null || numHours <= 0) {
      setError('Hours must be greater than 0');
      return;
    }
    if (numHours > 24) {
      setError('Hours cannot exceed 24 in a single entry');
      return;
    }
    const rateError = validateNonNegativeMoney(hourlyRate, 'Hourly rate');
    if (rateError) {
      setError(rateError);
      return;
    }
    const numRate = parseStrictNumber(hourlyRate) ?? 0;

    if (date) {
      const entryDate = new Date(date);
      const maxAllowed = new Date();
      maxAllowed.setDate(maxAllowed.getDate() + 1);
      if (!Number.isNaN(entryDate.getTime()) && entryDate.getTime() > maxAllowed.getTime()) {
        setError('Date cannot be more than 1 day in the future');
        return;
      }
    }

    const calculatedAmount = billable ? Math.round(numHours * numRate) : 0;

    setError('');
    setSubmitting(true);
    try {
      const ok = await onLogTime({
        employee,
        date,
        description: description.trim(),
        hours: numHours,
        billable,
        hourlyRate: numRate || 0,
        amount: calculatedAmount,
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
      title="Log Project Time"
      description="Record engineering hours and billable time allocations"
      size="md"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" form="timesheet-form" isLoading={submitting} disabled={submitting}>
            Log Time Entry
          </Button>
        </>
      }
    >
      <form id="timesheet-form" onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <Input label="Logged By" value={employee} readOnly disabled />
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

          <div>
            <Input
              label="Hours Worked"
              type="number"
              step="0.5"
              min="0.5"
              max="24"
              required
              value={hours}
              onChange={(e) => setHours(e.target.value)}
            />
          </div>

          <div>
            <Input
              label="Hourly Rate (₹)"
              type="number"
              min="0"
              step="50"
              value={hourlyRate}
              onChange={(e) => setHourlyRate(e.target.value)}
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
              <span>Mark as Billable Hours</span>
            </label>
          </div>

          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-slate-700 mb-1.5">
              Task Description <span className="text-rose-500">*</span>
            </label>
            <textarea
              rows={2}
              required
              placeholder="Detail the work performed..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </div>
      </form>
    </Modal>
  );
}
