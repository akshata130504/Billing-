import React, { useState } from 'react';
import { ProjectInvoice } from '../types';
import { Modal } from '../../../components/common/Modal';
import { Button } from '../../../components/common/Button';
import { Input } from '../../../components/common/Input';
import { Select } from '../../../components/common/Select';

interface CreateInvoiceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreateInvoice: (invoice: Omit<ProjectInvoice, 'id' | 'projectId'>) => void;
  defaultAmount: number;
}

export function CreateInvoiceModal({
  isOpen,
  onClose,
  onCreateInvoice,
  defaultAmount,
}: CreateInvoiceModalProps) {
  const [invoiceNumber, setInvoiceNumber] = useState(
    () => `INV-2026-${Math.floor(1000 + Math.random() * 9000)}`
  );
  const [date, setDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [dueDate, setDueDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 15);
    return d.toISOString().split('T')[0];
  });
  const [amount, setAmount] = useState(defaultAmount > 0 ? String(defaultAmount) : '40000');
  const [status, setStatus] = useState<ProjectInvoice['status']>('draft');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!invoiceNumber.trim()) {
      setError('Invoice number is required');
      return;
    }
    const numAmount = parseFloat(amount);
    if (isNaN(numAmount) || numAmount <= 0) {
      setError('Invoice amount must be greater than 0');
      return;
    }

    onCreateInvoice({
      invoiceNumber: invoiceNumber.trim(),
      date,
      dueDate,
      amount: numAmount,
      status,
    });
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create Project Invoice"
      description="Issue milestone or progress billing against this engagement"
      size="md"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" form="invoice-form">
            Generate Invoice
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
              label="Invoice Number"
              required
              value={invoiceNumber}
              onChange={(e) => setInvoiceNumber(e.target.value)}
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
              label="Invoice Amount (₹)"
              type="number"
              min="100"
              required
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>

          <div>
            <Select
              label="Initial Status"
              value={status}
              onChange={(e) => setStatus(e.target.value as ProjectInvoice['status'])}
              options={[
                { value: 'draft', label: 'Draft' },
                { value: 'pending', label: 'Sent / Pending' },
                { value: 'paid', label: 'Paid & Settled' },
              ]}
            />
          </div>
        </div>
      </form>
    </Modal>
  );
}
