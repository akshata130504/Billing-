import React, { useState, useEffect } from 'react';
import type { TimeEntryCreate, TimeEntryRead, TimeEntryUpdate } from '../../types/api';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { customerService } from '../../services/customerService';
import { validateDescription, validateNonNegativeMoney, parseStrictNumber } from '../../utils/validation';
import { todayIso } from '../../utils/format';
import { useCustomerProjects } from '../expenses/useCustomerProjects';

interface TimeEntryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: TimeEntryCreate | TimeEntryUpdate) => Promise<void>;
  initialEntry?: TimeEntryRead | null;
  loading?: boolean;
}

export function TimeEntryModal({
  isOpen,
  onClose,
  onSave,
  initialEntry,
  loading = false,
}: TimeEntryModalProps) {
  const [customers, setCustomers] = useState<Array<{ id: string; display_name: string; customer_number: string }>>([]);
  const [customerId, setCustomerId] = useState('');
  const [projectTitle, setProjectTitle] = useState('');
  // A real project of the selected customer; projectTitle is only a free label when none is linked.
  const [projectId, setProjectId] = useState('');
  const { projects, loading: projectsLoading } = useCustomerProjects(customerId || undefined);
  const [dateStr, setDateStr] = useState(todayIso());
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [durationHours, setDurationHours] = useState<number | string>(1);
  const [description, setDescription] = useState('');
  const [billable, setBillable] = useState(true);
  const [billingRate, setBillingRate] = useState<number | string>(100);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    customerService.list({ page_size: 100 }).then((res) => {
      setCustomers(res.items || []);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (initialEntry) {
      setCustomerId(initialEntry.customer_id || '');
      setProjectTitle(initialEntry.project_name || '');
      setProjectId(initialEntry.project_id || '');
      setDateStr(initialEntry.date);
      setStartTime(initialEntry.start_time || '');
      setEndTime(initialEntry.end_time || '');
      setDurationHours(parseFloat(initialEntry.duration_hours) || 1);
      setDescription(initialEntry.description);
      setBillable(initialEntry.billable);
      setBillingRate(parseFloat(initialEntry.billing_rate) || 0);
    } else {
      setCustomerId('');
      setProjectTitle('');
      setProjectId('');
      setDateStr(todayIso());
      setStartTime('');
      setEndTime('');
      setDurationHours(1);
      setDescription('');
      setBillable(true);
      setBillingRate(100);
    }
    setError(null);
  }, [initialEntry, isOpen]);

  // Auto calculate duration from start and end time if entered
  useEffect(() => {
    if (startTime && endTime) {
      const [sh, sm] = startTime.split(':').map(Number);
      const [eh, em] = endTime.split(':').map(Number);
      if (!isNaN(sh) && !isNaN(sm) && !isNaN(eh) && !isNaN(em)) {
        const startMin = sh * 60 + sm;
        const endMin = eh * 60 + em;
        if (endMin > startMin) {
          const diffHours = (endMin - startMin) / 60;
          setDurationHours(parseFloat(diffHours.toFixed(2)));
          setError((prev) => (prev === 'End time must be later than start time.' ? null : prev));
        } else {
          setError('End time must be later than start time.');
        }
      }
    }
  }, [startTime, endTime]);

  const numDuration = typeof durationHours === 'number' ? durationHours : (parseStrictNumber(durationHours) ?? 0);
  const numRate = typeof billingRate === 'number' ? billingRate : (parseStrictNumber(billingRate) ?? 0);
  const estimatedAmount = billable ? (numDuration * numRate).toFixed(2) : '0.00';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (startTime && endTime) {
      const [sh, sm] = startTime.split(':').map(Number);
      const [eh, em] = endTime.split(':').map(Number);
      if (!isNaN(sh) && !isNaN(sm) && !isNaN(eh) && !isNaN(em)) {
        if (eh * 60 + em <= sh * 60 + sm) {
          setError('End time must be later than start time.');
          return;
        }
      }
    }

    if (numDuration <= 0 || numDuration > 24) {
      setError('Duration must be greater than 0 and at most 24 hours.');
      return;
    }
    const descriptionError = validateDescription(description, 500, 'Work description');
    if (descriptionError) {
      setError(descriptionError);
      return;
    }
    if (billable) {
      const rateError = validateNonNegativeMoney(billingRate, 'Hourly billing rate');
      if (rateError) {
        setError(rateError);
        return;
      }
    }
    if (dateStr) {
      const entryDate = new Date(dateStr);
      const maxAllowed = new Date();
      maxAllowed.setDate(maxAllowed.getDate() + 1);
      if (!Number.isNaN(entryDate.getTime()) && entryDate.getTime() > maxAllowed.getTime()) {
        setError('Work date cannot be more than 1 day in the future.');
        return;
      }
    }
    setError(null);

    const linkedProject = projectId ? projects.find((p) => p.id === projectId) : undefined;
    const payload: TimeEntryCreate = {
      customer_id: customerId || null,
      // '' unlinks a project on edit; a new entry simply has none.
      project_id: projectId || (initialEntry?.project_id ? '' : null),
      project_name: linkedProject?.name || projectTitle.trim() || null,
      date: dateStr,
      start_time: startTime || null,
      end_time: endTime || null,
      duration_hours: numDuration,
      description: description.trim(),
      billable,
      billing_rate: billable ? numRate : 0,
    };
    await onSave(payload);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={initialEntry ? 'Edit Time Entry' : 'Log Time Entry'}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="time-entry-date" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              Work Date <span className="text-rose-500">*</span>
            </label>
            <div className="relative">
              <input
                id="time-entry-date"
                type="date"
                required
                value={dateStr}
                onChange={(e) => setDateStr(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label htmlFor="time-entry-customer" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              Customer / Account
            </label>
            <select
              id="time-entry-customer"
              value={customerId}
              onChange={(e) => {
                setCustomerId(e.target.value);
                // Projects belong to one customer: a new customer means picking its project again.
                setProjectId('');
              }}
              className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
            >
              <option value="">No Customer / Internal</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.display_name} ({c.customer_number})
                </option>
              ))}
            </select>
          </div>
        </div>

        {customerId && (
          <div>
            <label htmlFor="time-entry-project" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              Project
            </label>
            <select
              id="time-entry-project"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              disabled={projectsLoading}
              className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
            >
              <option value="">{projectsLoading ? 'Loading projects...' : 'No linked project'}</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
              {/* A linked project missing from the customer's list (e.g. since moved) stays visible. */}
              {projectId && !projectsLoading && !projects.some((p) => p.id === projectId) && (
                <option value={projectId}>{projectTitle || 'Linked project'}</option>
              )}
            </select>
          </div>
        )}

        {!projectId && (
        <div>
          <label htmlFor="time-entry-project-name" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
            Project / Engagement Name
          </label>
          <input
            id="time-entry-project-name"
            type="text"
            placeholder="e.g. Cloud Migration, Q3 Security Audit, Frontend Sprint"
            value={projectTitle}
            onChange={(e) => setProjectTitle(e.target.value)}
            className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
          />
        </div>
        )}

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label htmlFor="time-entry-start" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              Start Time
            </label>
            <input
              id="time-entry-start"
              type="time"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor="time-entry-end" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              End Time
            </label>
            <input
              id="time-entry-end"
              type="time"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor="time-entry-hours" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              Duration (Hours) <span className="text-rose-500">*</span>
            </label>
            <input
              id="time-entry-hours"
              type="number"
              // Any 2-decimal value: start/end times auto-fill e.g. 2.5 or 0.33 h. A 0.25 step
              // offset from a 0.1 minimum only allowed 0.1, 0.35, 0.6 ... so the browser blocked
              // whole hours and every auto-calculated duration.
              step="0.01"
              min="0.01"
              max="24"
              required
              value={durationHours}
              onChange={(e) => setDurationHours(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none font-semibold text-slate-900"
            />
          </div>
        </div>

        <div>
          <label htmlFor="time-entry-description" className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
            Work Description <span className="text-rose-500">*</span>
          </label>
          <textarea
            id="time-entry-description"
            rows={3}
            required
            placeholder="Detailed description of tasks completed, client deliverables, or deliverables achieved..."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
          />
        </div>

        <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="billableCheck"
                checked={billable}
                onChange={(e) => setBillable(e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded border-slate-300 focus:ring-blue-500"
              />
              <label htmlFor="billableCheck" className="text-sm font-semibold text-slate-900 cursor-pointer">
                Billable to Client
              </label>
            </div>
            {billable && (
              <span className="text-xs font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                Billable Entry
              </span>
            )}
          </div>

          {billable && (
            <div className="grid grid-cols-2 gap-4 pt-2 border-t border-slate-200/80">
              <div>
                <label htmlFor="time-entry-rate" className="block text-xs font-medium text-slate-600 mb-1">
                  Hourly Billing Rate
                </label>
                <input
                  id="time-entry-rate"
                  type="number"
                  step="1"
                  min="0"
                  value={billingRate}
                  onChange={(e) => setBillingRate(e.target.value)}
                  className="w-full px-3 py-1.5 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none font-medium"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Estimated Total Amount
                </label>
                <div className="px-3 py-1.5 text-sm bg-emerald-50/70 border border-emerald-200 rounded-lg font-bold text-emerald-800 flex items-center justify-between">
                  <span>INR</span>
                  <span>{estimatedAmount}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
          <Button variant="ghost" size="sm" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" disabled={loading}>
            {loading ? 'Saving...' : initialEntry ? 'Update Entry' : 'Log Time'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
