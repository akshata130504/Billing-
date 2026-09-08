import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  FilePlus2,
  Plus,
  Trash2,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ExternalLink,
  Lock,
} from 'lucide-react';
import { aiService } from '../../services/aiService';
import { customerService } from '../../services/customerService';
import { invoiceService } from '../../services/invoiceService';
import type { CustomerOut } from '../../types/api';
import type { Invoice } from '../../types/invoices';
import type {
  AIActionDraft,
  AIActionDraftLineIn,
  AIActionType,
  AIDraftConfirmResponse,
  AIDraftRequest,
} from '../../types/ai';
import { AI_ACTION_TYPES } from '../../types/ai';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { EmptyState } from '../../components/common/EmptyState';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime, formatMoney, humanize } from '../../utils/format';
import {
  ACTION_TYPE_LABELS,
  DRAFT_STATUS_BADGE,
  FIELD_LABEL_CLS,
  TEXTAREA_CLS,
  asUtc,
  errorMessage,
  extractValidationMessages,
} from './aiUi';

interface LineForm {
  key: string;
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate_pct: string;
}

function newLine(): LineForm {
  return { key: Math.random().toString(36).slice(2, 10), description: '', quantity: '1', unit_price: '', tax_rate_pct: '0' };
}

interface DraftPanelProps {
  onActivity?: () => void;
}

export function DraftPanel({ onActivity }: DraftPanelProps) {
  const { showToast } = useToast();
  const { hasRole, organization } = useAuth();
  const canDraft = hasRole('finance');
  const currency = organization?.default_currency ?? 'INR';

  // Reference data
  const [customers, setCustomers] = useState<CustomerOut[]>([]);
  const [customersLoading, setCustomersLoading] = useState(true);
  const [customersError, setCustomersError] = useState<string | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [invoicesLoading, setInvoicesLoading] = useState(false);

  // Form
  const [actionType, setActionType] = useState<AIActionType>('credit_note');
  const [prompt, setPrompt] = useState('');
  const [customerId, setCustomerId] = useState('');
  const [invoiceId, setInvoiceId] = useState('');
  const [reason, setReason] = useState('');
  const [lines, setLines] = useState<LineForm[]>([newLine()]);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Result
  const [submitting, setSubmitting] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [draft, setDraft] = useState<AIActionDraft | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [executed, setExecuted] = useState<AIDraftConfirmResponse | null>(null);

  const loadCustomers = async () => {
    setCustomersLoading(true);
    setCustomersError(null);
    try {
      const res = await customerService.list({ page_size: 100, status: 'active' });
      setCustomers(res.items);
    } catch (err: any) {
      setCustomersError(errorMessage(err, 'Could not load customers.'));
    } finally {
      setCustomersLoading(false);
    }
  };

  useEffect(() => {
    if (canDraft) void loadCustomers();
  }, [canDraft]);

  useEffect(() => {
    setInvoiceId('');
    if (!customerId) {
      setInvoices([]);
      return;
    }
    let cancelled = false;
    setInvoicesLoading(true);
    invoiceService
      .listInvoices({ customer_id: customerId, page_size: 100, sort: '-issue_date' })
      .then((res) => {
        if (!cancelled) setInvoices(res.items.filter((inv) => inv.status !== 'draft' && inv.status !== 'void'));
      })
      .catch((err: any) => {
        if (!cancelled) showToast('error', 'Could not load invoices', errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setInvoicesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [customerId]);

  const selectedCustomer = useMemo(() => customers.find((c) => c.id === customerId) ?? null, [customers, customerId]);
  const selectedInvoice = useMemo(() => invoices.find((i) => i.id === invoiceId) ?? null, [invoices, invoiceId]);

  const lineTotals = useMemo(() => {
    let subtotal = 0;
    let tax = 0;
    lines.forEach((l) => {
      const q = Number(l.quantity) || 0;
      const p = Number(l.unit_price) || 0;
      const t = Number(l.tax_rate_pct) || 0;
      const amt = q * p;
      subtotal += amt;
      tax += (amt * t) / 100;
    });
    return { subtotal, tax, total: subtotal + tax };
  }, [lines]);

  const updateLine = (key: string, patch: Partial<LineForm>) =>
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const validateForm = (): AIDraftRequest | null => {
    const errs: Record<string, string> = {};
    if (!prompt.trim()) errs.prompt = 'Describe what you want to do.';
    if (!customerId) errs.customer_id = 'Pick a customer.';
    const parsed: AIActionDraftLineIn[] = [];
    lines.forEach((l, idx) => {
      const q = Number(l.quantity);
      const p = Number(l.unit_price);
      const t = Number(l.tax_rate_pct || 0);
      if (!l.description.trim()) errs[`line.${idx}.description`] = 'Required';
      if (!(q > 0)) errs[`line.${idx}.quantity`] = 'Must be > 0';
      if (!(p >= 0) || l.unit_price === '') errs[`line.${idx}.unit_price`] = 'Must be ≥ 0';
      if (!(t >= 0 && t <= 100)) errs[`line.${idx}.tax_rate_pct`] = '0–100';
      parsed.push({ description: l.description.trim(), quantity: q, unit_price: p, tax_rate_pct: t });
    });
    setFormErrors(errs);
    if (Object.keys(errs).length) return null;
    return {
      prompt: prompt.trim(),
      action_type: actionType,
      customer_id: customerId,
      invoice_id: invoiceId || null,
      reason: reason.trim() || null,
      lines: parsed,
    };
  };

  const handlePropose = async (e: FormEvent) => {
    e.preventDefault();
    const body = validateForm();
    if (!body) return;
    setSubmitting(true);
    setValidationErrors([]);
    setDraft(null);
    setExecuted(null);
    try {
      const res = await aiService.proposeDraft(body);
      setDraft(res.draft);
      showToast('success', 'Draft validated', 'Review the proposal below, then confirm to execute it.');
      onActivity?.();
    } catch (err: any) {
      const messages = extractValidationMessages(err);
      setValidationErrors(messages.length ? messages : [errorMessage(err, 'The draft could not be proposed.')]);
      showToast('error', 'Draft rejected', errorMessage(err));
      onActivity?.();
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirm = async () => {
    if (!draft) return;
    setConfirming(true);
    try {
      const res = await aiService.confirmDraft(draft.id);
      setExecuted(res);
      setDraft(res.draft);
      setConfirmOpen(false);
      showToast(
        'success',
        'Credit note created',
        res.executed_result.credit_note_number
          ? `${res.executed_result.credit_note_number} for ${formatMoney(res.executed_result.total ?? null, currency)}`
          : undefined
      );
      onActivity?.();
    } catch (err: any) {
      const messages = extractValidationMessages(err);
      setConfirmOpen(false);
      setValidationErrors(messages.length ? messages : [errorMessage(err)]);
      // Backend flips the draft to rejected/expired on these paths; reflect that locally.
      setDraft((d) => (d ? { ...d, status: /expired/i.test(errorMessage(err)) ? 'expired' : 'rejected' } : d));
      showToast('error', 'Could not confirm draft', errorMessage(err));
    } finally {
      setConfirming(false);
    }
  };

  const resetAll = () => {
    setPrompt('');
    setCustomerId('');
    setInvoiceId('');
    setReason('');
    setLines([newLine()]);
    setFormErrors({});
    setValidationErrors([]);
    setDraft(null);
    setExecuted(null);
  };

  if (!canDraft) {
    return (
      <div className="p-5">
        <EmptyState
          icon={<Lock className="w-6 h-6 stroke-1" />}
          title="Finance role required"
          description="Drafting and confirming billing actions is limited to Finance, Admin and Owner roles. You can still ask questions and use the writing assistant."
          className="border-slate-200"
        />
      </div>
    );
  }

  const isExecuted = executed !== null || draft?.status === 'executed';
  const canConfirm = draft && draft.status === 'validated' && !isExecuted;

  return (
    <div className="grid lg:grid-cols-5 divide-y lg:divide-y-0 lg:divide-x divide-slate-200 h-full">
      {/* Form */}
      <form onSubmit={handlePropose} className="lg:col-span-3 p-5 space-y-5">
        <div className="grid sm:grid-cols-2 gap-4">
          <Select
            label="Action type"
            value={actionType}
            onChange={(e) => setActionType(e.target.value as AIActionType)}
            options={AI_ACTION_TYPES.map((t) => ({ value: t, label: ACTION_TYPE_LABELS[t].label }))}
            helperText={ACTION_TYPE_LABELS[actionType].description}
          />
          <div>
            <label className={FIELD_LABEL_CLS}>
              What do you want to do? <span className="text-rose-500">*</span>
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="e.g. Credit the double-billed support hours on the September invoice"
              className={TEXTAREA_CLS}
            />
            {formErrors.prompt && <p className="mt-1 text-xs text-rose-600 font-medium">{formErrors.prompt}</p>}
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <Select
            label="Customer"
            required
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            placeholder={customersLoading ? 'Loading customers…' : 'Select a customer'}
            disabled={customersLoading || !!customersError}
            error={formErrors.customer_id || customersError || undefined}
            options={customers.map((c) => ({ value: c.id, label: `${c.display_name} · ${c.customer_number}` }))}
          />
          <Select
            label="Against invoice (optional)"
            value={invoiceId}
            onChange={(e) => setInvoiceId(e.target.value)}
            disabled={!customerId || invoicesLoading}
            helperText={
              !customerId
                ? 'Pick a customer first.'
                : invoicesLoading
                  ? 'Loading invoices…'
                  : invoices.length === 0
                    ? 'This customer has no issued invoices.'
                    : undefined
            }
          >
            <option value="">No specific invoice</option>
            {invoices.map((inv) => (
              <option key={inv.id} value={inv.id}>
                {inv.invoice_number} · {humanize(inv.status)} · due {formatMoney(inv.amount_due, inv.currency)}
              </option>
            ))}
          </Select>
        </div>

        <Input
          label="Reason (optional)"
          value={reason}
          maxLength={255}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Shown on the credit note, e.g. Duplicate charge"
        />

        {/* Lines */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className={FIELD_LABEL_CLS + ' mb-0'}>
              Credit note lines <span className="text-rose-500">*</span>
            </label>
            <Button type="button" variant="ghost" size="sm" onClick={() => setLines((p) => [...p, newLine()])} leadingIcon={<Plus className="w-3.5 h-3.5" />}>
              Add line
            </Button>
          </div>
          <div className="rounded-xl border border-slate-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-3 py-2 text-left">Description</th>
                  <th className="px-3 py-2 text-right w-20">Qty</th>
                  <th className="px-3 py-2 text-right w-32">Unit price</th>
                  <th className="px-3 py-2 text-right w-20">Tax %</th>
                  <th className="px-2 py-2 w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {lines.map((l, idx) => (
                  <tr key={l.key} className="align-top">
                    <td className="px-2 py-2">
                      <Input
                        value={l.description}
                        maxLength={255}
                        onChange={(e) => updateLine(l.key, { description: e.target.value })}
                        placeholder="Line description"
                        error={formErrors[`line.${idx}.description`]}
                      />
                    </td>
                    <td className="px-2 py-2">
                      <Input
                        type="number"
                        min={0}
                        step="any"
                        className="text-right"
                        value={l.quantity}
                        onChange={(e) => updateLine(l.key, { quantity: e.target.value })}
                        error={formErrors[`line.${idx}.quantity`]}
                      />
                    </td>
                    <td className="px-2 py-2">
                      <Input
                        type="number"
                        min={0}
                        step="0.01"
                        className="text-right"
                        value={l.unit_price}
                        onChange={(e) => updateLine(l.key, { unit_price: e.target.value })}
                        placeholder="0.00"
                        error={formErrors[`line.${idx}.unit_price`]}
                      />
                    </td>
                    <td className="px-2 py-2">
                      <Input
                        type="number"
                        min={0}
                        max={100}
                        step="0.01"
                        className="text-right"
                        value={l.tax_rate_pct}
                        onChange={(e) => updateLine(l.key, { tax_rate_pct: e.target.value })}
                        error={formErrors[`line.${idx}.tax_rate_pct`]}
                      />
                    </td>
                    <td className="px-1 py-2">
                      <button
                        type="button"
                        onClick={() => setLines((p) => (p.length > 1 ? p.filter((x) => x.key !== l.key) : p))}
                        disabled={lines.length === 1}
                        className="mt-2 p-1.5 rounded-md text-slate-400 hover:text-rose-600 hover:bg-rose-50 disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
                        aria-label="Remove line"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-slate-50/60 border-t border-slate-200 text-xs">
                <tr>
                  <td colSpan={5} className="px-3 py-2">
                    <div className="flex items-center justify-end gap-5 text-slate-600 tabular-nums">
                      <span>Subtotal <strong className="text-slate-900 ml-1">{formatMoney(lineTotals.subtotal, currency)}</strong></span>
                      <span>Tax <strong className="text-slate-900 ml-1">{formatMoney(lineTotals.tax, currency)}</strong></span>
                      <span>Total <strong className="text-slate-900 ml-1">{formatMoney(lineTotals.total, currency)}</strong></span>
                    </div>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 pt-1">
          <p className="text-[11px] text-slate-400 max-w-sm">
            Proposing only validates the draft against current data. Nothing is posted to the ledger until you confirm.
          </p>
          <div className="flex items-center gap-2 shrink-0">
            {(draft || validationErrors.length > 0) && (
              <Button type="button" variant="ghost" size="sm" onClick={resetAll}>
                Start over
              </Button>
            )}
            <Button type="submit" size="sm" isLoading={submitting} leadingIcon={<FilePlus2 className="w-3.5 h-3.5" />}>
              Propose draft
            </Button>
          </div>
        </div>
      </form>

      {/* Review pane */}
      <div className="lg:col-span-2 p-5 bg-slate-50/50 space-y-4 min-h-[320px]">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">
          <ShieldCheck className="w-4 h-4" />
          Review &amp; confirm
        </div>

        {validationErrors.length > 0 && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-rose-800">
              <AlertTriangle className="w-4 h-4" />
              Validation failed
            </div>
            <ul className="mt-2 space-y-1 text-sm text-rose-700 list-disc list-inside">
              {validationErrors.map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
          </div>
        )}

        {!draft && validationErrors.length === 0 && (
          <EmptyState
            icon={<FilePlus2 className="w-6 h-6 stroke-1" />}
            title="No draft yet"
            description="Fill in the form and propose a draft. It will appear here with its validation result and a confirm button."
            className="border-slate-200 bg-white py-10"
          />
        )}

        {draft && (
          <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-slate-900">{ACTION_TYPE_LABELS[draft.action_type].label} draft</div>
                <div className="text-[11px] text-slate-400 font-mono truncate">{draft.id}</div>
              </div>
              <Badge variant={DRAFT_STATUS_BADGE[draft.status]} dot>
                {humanize(draft.status)}
              </Badge>
            </div>
            <dl className="px-4 py-3 text-sm space-y-2">
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Customer</dt>
                <dd className="font-medium text-slate-900 text-right">
                  {selectedCustomer ? (
                    <Link to={`/customers/${selectedCustomer.id}`} className="hover:text-brand-600 inline-flex items-center gap-1">
                      {selectedCustomer.display_name}
                      <ExternalLink className="w-3 h-3" />
                    </Link>
                  ) : (
                    <span className="font-mono text-xs">{draft.proposed_payload.customer_id}</span>
                  )}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Invoice</dt>
                <dd className="font-medium text-slate-900 text-right">
                  {draft.proposed_payload.invoice_id ? (
                    <Link to={`/invoices/${draft.proposed_payload.invoice_id}`} className="hover:text-brand-600 inline-flex items-center gap-1">
                      {selectedInvoice?.invoice_number ?? 'View invoice'}
                      <ExternalLink className="w-3 h-3" />
                    </Link>
                  ) : (
                    <span className="text-slate-400">None</span>
                  )}
                </dd>
              </div>
              {draft.proposed_payload.reason && (
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">Reason</dt>
                  <dd className="text-slate-900 text-right">{draft.proposed_payload.reason}</dd>
                </div>
              )}
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Lines</dt>
                <dd className="text-slate-900">{draft.proposed_payload.lines.length}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Proposed total</dt>
                <dd className="font-semibold text-slate-900 tabular-nums">{formatMoney(lineTotals.total, currency)}</dd>
              </div>
              <div className="flex justify-between gap-3 items-center">
                <dt className="text-slate-500 inline-flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" /> Expires
                </dt>
                <dd className="text-slate-700 text-xs">{formatDateTime(asUtc(draft.expires_at))}</dd>
              </div>
            </dl>
            <ul className="px-4 pb-3 space-y-1">
              {draft.proposed_payload.lines.map((l, i) => (
                <li key={i} className="flex justify-between gap-3 text-xs text-slate-600 border-t border-slate-100 pt-1.5">
                  <span className="truncate">
                    {l.description} <span className="text-slate-400">× {l.quantity}</span>
                  </span>
                  <span className="tabular-nums shrink-0">
                    {formatMoney(l.quantity * l.unit_price, currency)}
                    {l.tax_rate_pct > 0 && <span className="text-slate-400"> +{l.tax_rate_pct}%</span>}
                  </span>
                </li>
              ))}
            </ul>

            {executed ? (
              <div className="px-4 py-3 bg-emerald-50 border-t border-emerald-100">
                <div className="flex items-center gap-2 text-sm font-semibold text-emerald-800">
                  <CheckCircle2 className="w-4 h-4" />
                  Executed
                </div>
                <p className="text-xs text-emerald-800 mt-1">
                  Credit note <strong>{executed.executed_result.credit_note_number ?? executed.draft.executed_entity_id}</strong>
                  {executed.executed_result.total && <> for <strong>{formatMoney(executed.executed_result.total, currency)}</strong></>} was
                  created through the credit service.
                </p>
                <div className="flex flex-wrap gap-2 mt-2">
                  {selectedCustomer && (
                    <Link to={`/customers/${selectedCustomer.id}`} className="text-xs font-medium text-emerald-800 underline underline-offset-2 hover:text-emerald-900">
                      Open customer
                    </Link>
                  )}
                  {draft.proposed_payload.invoice_id && (
                    <Link to={`/invoices/${draft.proposed_payload.invoice_id}`} className="text-xs font-medium text-emerald-800 underline underline-offset-2 hover:text-emerald-900">
                      Open invoice
                    </Link>
                  )}
                </div>
              </div>
            ) : (
              <div className="px-4 py-3 bg-slate-50 border-t border-slate-100 flex items-center justify-between gap-3">
                <p className="text-[11px] text-slate-500">
                  {canConfirm
                    ? 'Confirming re-validates against current data and posts the credit note.'
                    : 'This draft can no longer be confirmed. Propose a new one.'}
                </p>
                <Button size="sm" disabled={!canConfirm} onClick={() => setConfirmOpen(true)} leadingIcon={<CheckCircle2 className="w-3.5 h-3.5" />}>
                  Confirm
                </Button>
              </div>
            )}
          </div>
        )}
      </div>

      <ConfirmDialog
        isOpen={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={handleConfirm}
        isLoading={confirming}
        title="Execute this credit note?"
        description={`A credit note for ${formatMoney(lineTotals.total, currency)} will be created for ${selectedCustomer?.display_name ?? 'the selected customer'}${selectedInvoice ? ` against ${selectedInvoice.invoice_number}` : ''}. This posts to the ledger and cannot be undone from here.`}
        confirmLabel="Create credit note"
      />
    </div>
  );
}
