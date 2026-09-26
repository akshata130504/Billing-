import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Ban, CheckCircle2 } from 'lucide-react';
import { PageHeader } from '../../components/common/PageHeader';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Modal } from '../../components/common/Modal';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';
import { creditNoteService, type CreditNote } from '../../services/creditNoteService';
import { invoiceService } from '../../services/invoiceService';
import type { Invoice } from '../../types/invoices';
import { formatDate, formatDateTime, formatMoney } from '../../utils/format';
import { creditNoteStatusLabel, creditNoteStatusVariant } from './creditNoteUi';

const CLOSED_INVOICE_STATUSES = new Set(['draft', 'paid', 'void', 'voided', 'cancelled', 'written_off']);

function invoiceDue(inv: Invoice): number {
  return Number(inv.amount_due ?? inv.balance_due ?? 0) || 0;
}

const inputClass =
  'w-full px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500';

export function CreditNoteDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canApply = hasRole('finance');
  const canVoid = hasRole('admin');

  const [note, setNote] = useState<CreditNote | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // invoice id -> invoice number, for the linked invoice and the applications list
  const [invoiceNumbers, setInvoiceNumbers] = useState<Record<string, string>>({});

  // Apply modal
  const [applyOpen, setApplyOpen] = useState(false);
  const [openInvoices, setOpenInvoices] = useState<Invoice[]>([]);
  const [loadingInvoices, setLoadingInvoices] = useState(false);
  const [applyInvoiceId, setApplyInvoiceId] = useState('');
  const [applyAmount, setApplyAmount] = useState('');
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);

  // Void modal
  const [voidOpen, setVoidOpen] = useState(false);
  const [voidReason, setVoidReason] = useState('');
  const [voiding, setVoiding] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      setNote(await creditNoteService.get(id));
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  // Resolve invoice numbers (best effort; falls back to a short id).
  useEffect(() => {
    if (!note) return;
    const ids = new Set<string>();
    if (note.invoice_id) ids.add(note.invoice_id);
    (note.applications ?? []).forEach((a) => ids.add(a.invoice_id));
    const missing = [...ids].filter((invId) => !invoiceNumbers[invId]);
    if (missing.length === 0) return;
    let cancelled = false;
    void Promise.allSettled(missing.map((invId) => invoiceService.getInvoice(invId))).then((results) => {
      if (cancelled) return;
      const found: Record<string, string> = {};
      results.forEach((r) => {
        if (r.status === 'fulfilled') found[r.value.id] = r.value.invoice_number;
      });
      if (Object.keys(found).length) setInvoiceNumbers((prev) => ({ ...prev, ...found }));
    });
    return () => {
      cancelled = true;
    };
    // invoiceNumbers intentionally omitted: it only grows from this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [note]);

  const balance = Number(note?.balance_remaining ?? 0) || 0;
  const status = note?.status ?? 'draft';
  const canBeApplied = balance > 0 && (status === 'issued' || status === 'partially_applied');
  const canBeVoided = status !== 'void' && (note?.applications?.length ?? 0) === 0;

  const openApply = async () => {
    if (!note) return;
    setApplyOpen(true);
    setApplyError(null);
    setApplyInvoiceId('');
    setApplyAmount('');
    setLoadingInvoices(true);
    try {
      const res = await invoiceService.listInvoices({ customer_id: note.customer_id, page_size: 100 });
      const open = (res.items || []).filter(
        (inv) => !CLOSED_INVOICE_STATUSES.has(String(inv.status).toLowerCase()) && invoiceDue(inv) > 0
      );
      setOpenInvoices(open);
      const preferred = open.find((inv) => inv.id === note.invoice_id) ?? open[0];
      if (preferred) {
        setApplyInvoiceId(preferred.id);
        setApplyAmount(Math.min(balance, invoiceDue(preferred)).toFixed(2));
      }
    } catch (err) {
      setApplyError(toApiError(err).message);
    } finally {
      setLoadingInvoices(false);
    }
  };

  const selectedInvoice = useMemo(
    () => openInvoices.find((inv) => inv.id === applyInvoiceId) ?? null,
    [openInvoices, applyInvoiceId]
  );

  const handleApply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!note || !selectedInvoice) {
      setApplyError('Select an invoice.');
      return;
    }
    const amount = Number(applyAmount);
    const max = Math.min(balance, invoiceDue(selectedInvoice));
    if (!(amount > 0)) {
      setApplyError('Amount must be greater than zero.');
      return;
    }
    if (amount > max + 0.001) {
      setApplyError(`Amount cannot exceed ${formatMoney(max, note.currency)}.`);
      return;
    }
    setApplying(true);
    setApplyError(null);
    try {
      const updated = await creditNoteService.apply(note.id, { invoice_id: selectedInvoice.id, amount });
      setNote(updated);
      setInvoiceNumbers((prev) => ({ ...prev, [selectedInvoice.id]: selectedInvoice.invoice_number }));
      setApplyOpen(false);
      showToast('success', 'Credit applied', `${formatMoney(amount, note.currency)} applied to ${selectedInvoice.invoice_number}.`);
    } catch (err) {
      setApplyError(toApiError(err).message);
    } finally {
      setApplying(false);
    }
  };

  const handleVoid = async () => {
    if (!note) return;
    setVoiding(true);
    try {
      const updated = await creditNoteService.void(note.id, voidReason.trim() || undefined);
      setNote(updated);
      setVoidOpen(false);
      setVoidReason('');
      showToast('success', 'Credit note voided');
    } catch (err) {
      showToast('error', 'Could not void credit note', toApiError(err).message);
    } finally {
      setVoiding(false);
    }
  };

  if (loading) return <LoadingState message="Loading credit note..." />;
  if (error || !note) {
    return (
      <div className="space-y-4">
        <PageHeader title="Credit Note" backTo={{ to: '/credit-notes', label: 'Back to credit notes' }} />
        <ErrorState
          title="Couldn't load this credit note"
          message={error ?? 'Credit note not found.'}
          onRetry={() => void load()}
        />
      </div>
    );
  }

  const invoiceLabel = (invId: string) => invoiceNumbers[invId] ?? `${invId.slice(0, 8)}…`;
  const gstRows = [
    { label: 'CGST', value: note.cgst_amount },
    { label: 'SGST', value: note.sgst_amount },
    { label: 'IGST', value: note.igst_amount },
  ].filter((r) => Number(r.value ?? 0) > 0);

  return (
    <div className="space-y-6">
      <PageHeader
        backTo={{ to: '/credit-notes', label: 'Back to credit notes' }}
        eyebrow="Credit Note"
        title={
          <span className="flex items-center gap-2">
            <span className="font-mono">{note.credit_note_number}</span>
            <Badge variant={creditNoteStatusVariant(note.status)}>{creditNoteStatusLabel(note.status)}</Badge>
          </span>
        }
        subtitle={`Issued ${formatDate(note.created_at)}${note.reason ? ` · ${note.reason}` : ''}`}
        actions={
          <div className="flex items-center gap-2">
            {canApply && canBeApplied && (
              <Button
                variant="primary"
                size="sm"
                leadingIcon={<CheckCircle2 className="w-4 h-4" />}
                onClick={() => void openApply()}
              >
                Apply to Invoice
              </Button>
            )}
            {canVoid && canBeVoided && (
              <Button variant="danger" size="sm" leadingIcon={<Ban className="w-4 h-4" />} onClick={() => setVoidOpen(true)}>
                Void
              </Button>
            )}
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 text-sm font-semibold text-slate-900">Lines</div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-600 border-collapse">
                <thead className="bg-slate-50 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                  <tr>
                    <th className="px-4 py-2.5">Description</th>
                    <th className="px-4 py-2.5 text-right">Tax %</th>
                    <th className="px-4 py-2.5 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(note.lines ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={3} className="px-4 py-6 text-center text-slate-400">
                        No line details.
                      </td>
                    </tr>
                  ) : (
                    (note.lines ?? []).map((line) => (
                      <tr key={line.id}>
                        <td className="px-4 py-2.5 text-slate-900">{line.description}</td>
                        <td className="px-4 py-2.5 text-right">{line.tax_rate_pct != null ? `${Number(line.tax_rate_pct)}%` : '—'}</td>
                        <td className="px-4 py-2.5 text-right font-medium text-slate-900">
                          {formatMoney(line.amount, note.currency)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="px-4 py-3 border-t border-slate-100 text-xs space-y-1 text-right">
              <div>Subtotal: <span className="font-medium text-slate-900">{formatMoney(note.subtotal, note.currency)}</span></div>
              {gstRows.length > 0
                ? gstRows.map((r) => (
                    <div key={r.label}>
                      {r.label}: <span className="font-medium text-slate-900">{formatMoney(r.value, note.currency)}</span>
                    </div>
                  ))
                : Number(note.tax_amount ?? 0) > 0 && (
                    <div>Tax: <span className="font-medium text-slate-900">{formatMoney(note.tax_amount, note.currency)}</span></div>
                  )}
              <div className="text-sm font-semibold text-slate-900">Total: {formatMoney(note.total, note.currency)}</div>
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 text-sm font-semibold text-slate-900">Applications</div>
            {(note.applications ?? []).length === 0 ? (
              <p className="px-4 py-6 text-xs text-slate-400 text-center">This credit has not been applied to any invoice yet.</p>
            ) : (
              <ul className="divide-y divide-slate-100 text-xs">
                {(note.applications ?? []).map((a) => (
                  <li key={a.id} className="px-4 py-2.5 flex items-center justify-between gap-3">
                    <Link to={`/invoices/${a.invoice_id}`} className="font-mono font-semibold text-brand-600 hover:underline">
                      {invoiceLabel(a.invoice_id)}
                    </Link>
                    <span className="text-slate-500">{formatDateTime(a.applied_at)}</span>
                    <span className="font-semibold text-slate-900">{formatMoney(a.amount, note.currency)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs p-4 space-y-3 text-xs">
            <div>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Remaining balance</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">{formatMoney(note.balance_remaining, note.currency)}</p>
            </div>
            <div className="border-t border-slate-100 pt-3 space-y-2">
              <div>
                <p className="text-slate-400">Customer</p>
                {note.customer ? (
                  <Link to={`/customers/${note.customer.id}`} className="font-semibold text-brand-600 hover:underline">
                    {note.customer.display_name}
                  </Link>
                ) : (
                  <Link to={`/customers/${note.customer_id}`} className="font-semibold text-brand-600 hover:underline">
                    View customer
                  </Link>
                )}
              </div>
              {note.invoice_id && (
                <div>
                  <p className="text-slate-400">Corrects invoice</p>
                  <Link to={`/invoices/${note.invoice_id}`} className="font-mono font-semibold text-brand-600 hover:underline">
                    {invoiceLabel(note.invoice_id)}
                  </Link>
                </div>
              )}
              {note.place_of_supply_name && (
                <div>
                  <p className="text-slate-400">Place of supply</p>
                  <p className="font-medium text-slate-800">{note.place_of_supply_name}</p>
                </div>
              )}
              {note.reference && (
                <div>
                  <p className="text-slate-400">Reference</p>
                  <p className="font-medium text-slate-800">{note.reference}</p>
                </div>
              )}
              {note.notes && (
                <div>
                  <p className="text-slate-400">Notes</p>
                  <p className="text-slate-700 whitespace-pre-wrap">{note.notes}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Apply to invoice */}
      <Modal
        isOpen={applyOpen}
        onClose={() => !applying && setApplyOpen(false)}
        title="Apply credit to invoice"
        description={`Available credit: ${formatMoney(balance, note.currency)}`}
        size="md"
      >
        <form onSubmit={handleApply} className="space-y-4">
          {applyError && (
            <div role="alert" className="px-3 py-2 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
              {applyError}
            </div>
          )}
          {loadingInvoices ? (
            <LoadingState message="Loading open invoices..." className="py-6" />
          ) : openInvoices.length === 0 ? (
            <p className="text-xs text-slate-500">This customer has no open invoices with a balance due.</p>
          ) : (
            <>
              <div>
                <label htmlFor="apply-invoice" className="block text-xs font-medium text-slate-700 mb-1.5">
                  Invoice
                </label>
                <select
                  id="apply-invoice"
                  value={applyInvoiceId}
                  onChange={(e) => {
                    setApplyInvoiceId(e.target.value);
                    const inv = openInvoices.find((i) => i.id === e.target.value);
                    if (inv) setApplyAmount(Math.min(balance, invoiceDue(inv)).toFixed(2));
                  }}
                  className={inputClass}
                >
                  {openInvoices.map((inv) => (
                    <option key={inv.id} value={inv.id}>
                      {inv.invoice_number} · due {formatMoney(invoiceDue(inv), inv.currency)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="apply-amount" className="block text-xs font-medium text-slate-700 mb-1.5">
                  Amount
                </label>
                <input
                  id="apply-amount"
                  type="number"
                  min="0"
                  step="0.01"
                  value={applyAmount}
                  onChange={(e) => setApplyAmount(e.target.value)}
                  className={inputClass}
                />
              </div>
            </>
          )}
          <div className="pt-3 flex items-center justify-end gap-2 border-t border-slate-100">
            <Button type="button" variant="outline" onClick={() => setApplyOpen(false)} disabled={applying}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" isLoading={applying} disabled={!selectedInvoice}>
              Apply Credit
            </Button>
          </div>
        </form>
      </Modal>

      {/* Void */}
      <Modal
        isOpen={voidOpen}
        onClose={() => !voiding && setVoidOpen(false)}
        title="Void credit note"
        description="A voided credit note can no longer be applied. This cannot be undone."
        size="sm"
      >
        <div className="space-y-4">
          <div>
            <label htmlFor="void-reason" className="block text-xs font-medium text-slate-700 mb-1.5">
              Reason <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <input
              id="void-reason"
              value={voidReason}
              onChange={(e) => setVoidReason(e.target.value)}
              maxLength={500}
              className={inputClass}
            />
          </div>
          <div className="pt-3 flex items-center justify-end gap-2 border-t border-slate-100">
            <Button type="button" variant="outline" onClick={() => setVoidOpen(false)} disabled={voiding}>
              Cancel
            </Button>
            <Button type="button" variant="danger" isLoading={voiding} onClick={() => void handleVoid()}>
              Void Credit Note
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default CreditNoteDetailPage;
