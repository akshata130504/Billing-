import { useEffect, useMemo, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Modal } from '../../../components/common/Modal';
import { Button } from '../../../components/common/Button';
import { CustomerCombobox } from '../../../components/common/CustomerCombobox';
import { useToast } from '../../../components/common/Toast';
import { toApiError, fieldErrors } from '../../../services/apiClient';
import { invoiceService } from '../../../services/invoiceService';
import { creditNoteService, type CreditNote } from '../../../services/creditNoteService';
import { formatMoney } from '../../../utils/format';
import type { Invoice } from '../../../types/invoices';

interface LineDraft {
  description: string;
  amount: string;
  tax_rate_pct: string;
}

const EMPTY_LINE: LineDraft = { description: '', amount: '', tax_rate_pct: '18' };

export interface CreateCreditNoteModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (note: CreditNote) => void;
  /** Prefill when launched from an invoice. */
  initialCustomerId?: string;
  initialInvoiceId?: string;
}

const inputClass =
  'w-full px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500';

export function CreateCreditNoteModal({
  isOpen,
  onClose,
  onCreated,
  initialCustomerId = '',
  initialInvoiceId = '',
}: CreateCreditNoteModalProps) {
  const { showToast } = useToast();
  const [customerId, setCustomerId] = useState(initialCustomerId);
  const [invoiceId, setInvoiceId] = useState(initialInvoiceId);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loadingInvoices, setLoadingInvoices] = useState(false);
  const [reason, setReason] = useState('');
  const [reference, setReference] = useState('');
  const [lines, setLines] = useState<LineDraft[]>([{ ...EMPTY_LINE }]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset whenever the modal is (re)opened.
  useEffect(() => {
    if (!isOpen) return;
    setCustomerId(initialCustomerId);
    setInvoiceId(initialInvoiceId);
    setReason('');
    setReference('');
    setLines([{ ...EMPTY_LINE }]);
    setError(null);
  }, [isOpen, initialCustomerId, initialInvoiceId]);

  // The customer's invoices, for the optional "invoice being corrected" link.
  useEffect(() => {
    if (!isOpen || !customerId) {
      setInvoices([]);
      return;
    }
    let cancelled = false;
    setLoadingInvoices(true);
    invoiceService
      .listInvoices({ customer_id: customerId, page_size: 100, sort: '-issue_date' })
      .then((res) => {
        if (!cancelled) setInvoices((res.items || []).filter((inv) => String(inv.status).toLowerCase() !== 'draft'));
      })
      .catch((err) => {
        if (!cancelled) showToast('error', 'Could not load invoices', toApiError(err).message);
      })
      .finally(() => {
        if (!cancelled) setLoadingInvoices(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, customerId, showToast]);

  const totals = useMemo(() => {
    let subtotal = 0;
    let tax = 0;
    lines.forEach((l) => {
      const amount = Number(l.amount) || 0;
      subtotal += amount;
      tax += (amount * (Number(l.tax_rate_pct) || 0)) / 100;
    });
    return { subtotal, tax, total: subtotal + tax };
  }, [lines]);

  const updateLine = (index: number, patch: Partial<LineDraft>) => {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!customerId) {
      setError('Select a customer.');
      return;
    }
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (!l.description.trim()) {
        setError(`Line ${i + 1}: description is required.`);
        return;
      }
      if (!(Number(l.amount) > 0)) {
        setError(`Line ${i + 1}: amount must be greater than zero.`);
        return;
      }
      const rate = Number(l.tax_rate_pct);
      if (Number.isNaN(rate) || rate < 0 || rate > 100) {
        setError(`Line ${i + 1}: tax rate must be between 0 and 100.`);
        return;
      }
    }

    setSubmitting(true);
    try {
      const created = await creditNoteService.create({
        customer_id: customerId,
        invoice_id: invoiceId || undefined,
        reason: reason.trim() || undefined,
        reference: reference.trim() || undefined,
        lines: lines.map((l) => ({
          description: l.description.trim(),
          amount: Number(l.amount),
          tax_rate_pct: Number(l.tax_rate_pct) || 0,
        })),
      });
      showToast('success', 'Credit note created', created.credit_note_number);
      onCreated(created);
    } catch (err) {
      const fields = fieldErrors(err);
      const firstField = Object.values(fields)[0];
      setError(firstField || toApiError(err).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => !submitting && onClose()}
      title="New Credit Note"
      description="Issue a credit to a customer, optionally against an invoice you are correcting."
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div role="alert" className="px-3 py-2 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
            {error}
          </div>
        )}

        <CustomerCombobox
          label="Customer"
          required
          value={customerId}
          onChange={(id) => {
            setCustomerId(id);
            setInvoiceId('');
          }}
        />

        <div>
          <label htmlFor="cn-invoice" className="block text-xs font-medium text-slate-700 mb-1.5">
            Invoice being corrected <span className="text-slate-400 font-normal">(optional)</span>
          </label>
          <select
            id="cn-invoice"
            value={invoiceId}
            onChange={(e) => setInvoiceId(e.target.value)}
            disabled={!customerId || loadingInvoices}
            className={inputClass}
          >
            <option value="">{loadingInvoices ? 'Loading invoices...' : 'No specific invoice'}</option>
            {invoices.map((inv) => (
              <option key={inv.id} value={inv.id}>
                {inv.invoice_number} · {formatMoney(inv.total, inv.currency)} · {String(inv.status).toLowerCase()}
              </option>
            ))}
            {invoiceId && !invoices.some((inv) => inv.id === invoiceId) && !loadingInvoices && (
              <option value={invoiceId}>Selected invoice</option>
            )}
          </select>
          <p className="mt-1 text-[11px] text-slate-500">
            Linking an invoice applies that invoice's GST treatment to the credit note.
          </p>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-700">Lines</span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              leadingIcon={<Plus className="w-3.5 h-3.5" />}
              onClick={() => setLines((prev) => [...prev, { ...EMPTY_LINE }])}
            >
              Add line
            </Button>
          </div>
          {lines.map((line, index) => (
            <div key={index} className="grid grid-cols-12 gap-2 items-start">
              <input
                aria-label={`Line ${index + 1} description`}
                placeholder="Description"
                value={line.description}
                onChange={(e) => updateLine(index, { description: e.target.value })}
                className={`${inputClass} col-span-12 sm:col-span-6`}
                maxLength={255}
              />
              <input
                aria-label={`Line ${index + 1} amount (pre-tax)`}
                placeholder="Amount (pre-tax)"
                type="number"
                min="0"
                step="0.01"
                value={line.amount}
                onChange={(e) => updateLine(index, { amount: e.target.value })}
                className={`${inputClass} col-span-6 sm:col-span-3`}
              />
              <input
                aria-label={`Line ${index + 1} tax rate %`}
                placeholder="Tax %"
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={line.tax_rate_pct}
                onChange={(e) => updateLine(index, { tax_rate_pct: e.target.value })}
                className={`${inputClass} col-span-4 sm:col-span-2`}
              />
              <button
                type="button"
                aria-label={`Remove line ${index + 1}`}
                disabled={lines.length === 1}
                onClick={() => setLines((prev) => prev.filter((_, i) => i !== index))}
                className="col-span-2 sm:col-span-1 h-9 flex items-center justify-center rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 disabled:opacity-30 disabled:pointer-events-none"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
          <div className="text-right text-xs text-slate-600 space-y-0.5 pt-1">
            <div>Subtotal: {formatMoney(totals.subtotal)}</div>
            <div>Estimated tax: {formatMoney(totals.tax)}</div>
            <div className="font-semibold text-slate-900">Estimated total: {formatMoney(totals.total)}</div>
            <p className="text-[11px] text-slate-400">Final GST split is calculated by the server.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="cn-reason" className="block text-xs font-medium text-slate-700 mb-1.5">
              Reason
            </label>
            <input
              id="cn-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
              placeholder="e.g. Service credit for downtime"
              className={inputClass}
            />
          </div>
          <div>
            <label htmlFor="cn-reference" className="block text-xs font-medium text-slate-700 mb-1.5">
              Reference
            </label>
            <input
              id="cn-reference"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              maxLength={120}
              placeholder="Optional"
              className={inputClass}
            />
          </div>
        </div>

        <div className="pt-3 flex items-center justify-end gap-2 border-t border-slate-100">
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" isLoading={submitting}>
            Create Credit Note
          </Button>
        </div>
      </form>
    </Modal>
  );
}
