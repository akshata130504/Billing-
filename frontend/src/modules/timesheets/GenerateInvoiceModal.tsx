import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckSquare, Square } from 'lucide-react';
import type { TimeEntryRead, TimesheetInvoiceCreate } from '../../types/api';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { timesheetService } from '../../services/timesheetService';
import { customerService } from '../../services/customerService';
import { formatMoney, formatDate, todayIso, toIsoDate } from '../../utils/format';

interface GenerateInvoiceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  initialCustomerId?: string;
}

export function GenerateInvoiceModal({
  isOpen,
  onClose,
  onSuccess,
  initialCustomerId,
}: GenerateInvoiceModalProps) {
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [customers, setCustomers] = useState<Array<{ id: string; display_name: string; customer_number: string }>>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>(initialCustomerId || '');
  const [unbilledEntries, setUnbilledEntries] = useState<TimeEntryRead[]>([]);
  const [selectedEntryIds, setSelectedEntryIds] = useState<string[]>([]);
  const [loadingEntries, setLoadingEntries] = useState(false);
  const [generating, setGenerating] = useState(false);

  const [issueDate, setIssueDate] = useState(todayIso());
  const [dueDate, setDueDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 30);
    return toIsoDate(d);
  });
  const [notes, setNotes] = useState('Consulting & technical services for tracked timesheet entries.');

  useEffect(() => {
    customerService.list({ page_size: 100 }).then((res) => {
      setCustomers(res.items || []);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (initialCustomerId) {
      setSelectedCustomerId(initialCustomerId);
    }
  }, [initialCustomerId]);

  useEffect(() => {
    if (!selectedCustomerId) {
      setUnbilledEntries([]);
      setSelectedEntryIds([]);
      return;
    }

    setLoadingEntries(true);
    timesheetService.list({
      customer_id: selectedCustomerId,
      billable: true,
    }).then((entries) => {
      // Only approved, billable entries that have not already been billed can be invoiced
      const unbilled = entries.filter((e) => e.status === 'approved');
      setUnbilledEntries(unbilled);
      setSelectedEntryIds(unbilled.map((e) => e.id));
    }).catch((err) => {
      showToast('error', 'Error', err.message || 'Failed to load unbilled entries');
    }).finally(() => {
      setLoadingEntries(false);
    });
  }, [selectedCustomerId, showToast]);

  const handleToggleEntry = (id: string) => {
    setSelectedEntryIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleToggleAll = () => {
    if (selectedEntryIds.length === unbilledEntries.length) {
      setSelectedEntryIds([]);
    } else {
      setSelectedEntryIds(unbilledEntries.map((e) => e.id));
    }
  };

  const selectedEntries = unbilledEntries.filter((e) => selectedEntryIds.includes(e.id));
  const totalHours = selectedEntries.reduce((sum, e) => sum + parseFloat(e.duration_hours || '0'), 0);
  const totalAmount = selectedEntries.reduce((sum, e) => sum + parseFloat(e.billable_amount || '0'), 0);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCustomerId || selectedEntryIds.length === 0) {
      showToast('warning', 'Selection Required', 'Please select at least one time entry to invoice');
      return;
    }

    try {
      setGenerating(true);
      const payload: TimesheetInvoiceCreate = {
        customer_id: selectedCustomerId,
        time_entry_ids: selectedEntryIds,
        issue_date: issueDate,
        due_date: dueDate,
        notes: notes.trim() || undefined,
      };

      const invoice = await timesheetService.generateInvoice(payload);
      showToast('success', 'Invoice Created', `Invoice #${invoice.invoice_number} created successfully!`);
      onSuccess();
      onClose();
      if (invoice.id) {
        navigate(`/invoices/${invoice.id}`);
      }
    } catch (err: any) {
      showToast('error', 'Generation Failed', err.message || 'Failed to generate invoice');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Convert Timesheets to Invoice"
    >
      <form onSubmit={handleGenerate} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
            Select Customer <span className="text-rose-500">*</span>
          </label>
          <select
            required
            value={selectedCustomerId}
            onChange={(e) => setSelectedCustomerId(e.target.value)}
            className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
          >
            <option value="">Select a customer...</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.display_name} ({c.customer_number})
              </option>
            ))}
          </select>
        </div>

        {selectedCustomerId && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
                Unbilled Billable Entries ({unbilledEntries.length})
              </label>
              {unbilledEntries.length > 0 && (
                <button
                  type="button"
                  onClick={handleToggleAll}
                  className="text-xs text-blue-600 hover:underline font-medium flex items-center gap-1"
                >
                  {selectedEntryIds.length === unbilledEntries.length ? 'Deselect All' : 'Select All'}
                </button>
              )}
            </div>

            {loadingEntries ? (
              <div className="py-6 text-center text-xs text-slate-500">Loading entries...</div>
            ) : unbilledEntries.length === 0 ? (
              <div className="p-4 bg-slate-50 rounded-lg text-center text-xs text-slate-500">
                No unbilled billable entries found for this customer.
              </div>
            ) : (
              <div className="max-h-48 overflow-y-auto space-y-2 border border-slate-200 rounded-lg p-2 bg-slate-50/50">
                {unbilledEntries.map((entry) => {
                  const isChecked = selectedEntryIds.includes(entry.id);
                  return (
                    <div
                      key={entry.id}
                      onClick={() => handleToggleEntry(entry.id)}
                      className={`p-2.5 rounded-lg border text-xs cursor-pointer flex items-center justify-between transition-colors ${
                        isChecked
                          ? 'bg-blue-50/80 border-blue-200 text-blue-900'
                          : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        {isChecked ? (
                          <CheckSquare className="w-4 h-4 text-blue-600 flex-shrink-0" />
                        ) : (
                          <Square className="w-4 h-4 text-slate-300 flex-shrink-0" />
                        )}
                        <div className="min-w-0">
                          <div className="font-semibold text-slate-900 truncate">
                            {entry.project_name || 'General Work'}: {entry.description}
                          </div>
                          <div className="text-[10px] text-slate-400">
                            {formatDate(entry.date)} • {entry.duration_hours}h @ INR {entry.billing_rate}/hr
                          </div>
                        </div>
                      </div>
                      <span className="font-bold text-slate-900 ml-2 flex-shrink-0">
                        {formatMoney(entry.billable_amount)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              Invoice Issue Date
            </label>
            <input
              type="date"
              value={issueDate}
              onChange={(e) => setIssueDate(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
              Payment Due Date
            </label>
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
            Invoice Notes / Memo
          </label>
          <textarea
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
          />
        </div>

        {selectedEntryIds.length > 0 && (
          <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-200 flex items-center justify-between">
            <div>
              <div className="text-xs text-emerald-800 font-semibold">
                {selectedEntryIds.length} entries selected ({totalHours.toFixed(2)} hours)
              </div>
              <div className="text-[11px] text-emerald-600">Line items will be created automatically</div>
            </div>
            <div className="text-right font-bold text-lg text-emerald-900">
              {formatMoney(totalAmount.toFixed(2))}
            </div>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
          <Button variant="ghost" size="sm" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            type="submit"
            disabled={generating || selectedEntryIds.length === 0}
          >
            {generating ? 'Generating Invoice...' : 'Generate Invoice'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
