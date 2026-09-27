import React, { useEffect, useState } from 'react';
import type { ProjectInvoiceInput } from '../../../services/projectService';
import { Modal } from '../../../components/common/Modal';
import { Button } from '../../../components/common/Button';
import { Input } from '../../../components/common/Input';
import { Select } from '../../../components/common/Select';
import { parseStrictNumber } from '../../../utils/validation';
import { toIsoDate } from '../../../utils/format';

interface CreateInvoiceModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Creates a real draft invoice on the server; resolve false to keep the modal open. */
  onCreateInvoice: (invoice: ProjectInvoiceInput) => Promise<boolean> | boolean | void;
  /** Suggested amount (e.g. the unbilled budget); 0 leaves the field empty. */
  defaultAmount: number;
}

function isoToday(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return toIsoDate(d);
}

export function CreateInvoiceModal({
  isOpen,
  onClose,
  onCreateInvoice,
  defaultAmount,
}: CreateInvoiceModalProps) {
  const [description, setDescription] = useState('');
  const [date, setDate] = useState(() => isoToday());
  const [dueDate, setDueDate] = useState(() => isoToday(15));
  const [amount, setAmount] = useState('');
  const [taxRate, setTaxRate] = useState('18');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Reset every time the modal opens so a previous draft never leaks into a new invoice.
  useEffect(() => {
    if (!isOpen) return;
    setDescription('');
    setDate(isoToday());
    setDueDate(isoToday(15));
    setAmount(defaultAmount > 0 ? String(Math.round(defaultAmount * 100) / 100) : '');
    setTaxRate('18');
    setError('');
  }, [isOpen, defaultAmount]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    const numAmount = parseStrictNumber(amount);
    if (numAmount === null || numAmount <= 0) {
      setError('Invoice amount must be greater than 0');
      return;
    }
    if (dueDate && date && dueDate < date) {
      setError('Due date cannot be before the invoice date');
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      const ok = await onCreateInvoice({
        amount: numAmount,
        description: description.trim() || undefined,
        taxRatePct: Number(taxRate),
        issueDate: date,
        dueDate,
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
      title="Create Project Invoice"
      description="Raises a draft invoice for the project's customer. The invoice number is assigned by the invoice series."
      size="md"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" form="invoice-form" isLoading={submitting} disabled={submitting}>
            Create Draft Invoice
          </Button>
        </>
      }
    >
      <form id="invoice-form" onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <Input
              label="Line Description"
              placeholder="e.g. Milestone 1 - Discovery & design"
              maxLength={500}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div>
            <Input
              label="Invoice Date"
              type="date"
              required
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>

          <div>
            <Input
              label="Payment Due Date"
              type="date"
              required
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
            />
          </div>

          <div>
            <Input
              label="Amount before tax (₹)"
              type="number"
              min="0.01"
              step="0.01"
              required
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>

          <div>
            <Select
              label="GST Rate"
              value={taxRate}
              onChange={(e) => setTaxRate(e.target.value)}
              options={[
                { value: '0', label: '0% - Exempt / Nil' },
                { value: '5', label: '5%' },
                { value: '12', label: '12%' },
                { value: '18', label: '18% - Standard' },
                { value: '28', label: '28%' },
              ]}
            />
          </div>
        </div>
      </form>
    </Modal>
  );
}
