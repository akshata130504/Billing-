import { useEffect, useState, type FormEvent } from 'react';
import { PenLine, Copy, Check, Wand2, Mail } from 'lucide-react';
import { aiService } from '../../services/aiService';
import { customerService } from '../../services/customerService';
import { invoiceService } from '../../services/invoiceService';
import type { CustomerOut } from '../../types/api';
import type { Invoice } from '../../types/invoices';
import type { AIWritingPurpose, AIWritingResponse, AIWritingTone } from '../../types/ai';
import { AI_WRITING_PURPOSES, AI_WRITING_TONES } from '../../types/ai';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { EmptyState } from '../../components/common/EmptyState';
import { useToast } from '../../components/common/Toast';
import { formatDate, formatMoney } from '../../utils/format';
import { FIELD_LABEL_CLS, PURPOSE_LABELS, TEXTAREA_CLS, TONE_LABELS, errorMessage } from './aiUi';

interface WritingPanelProps {
  onActivity?: () => void;
}

export function WritingPanel({ onActivity }: WritingPanelProps) {
  const { showToast } = useToast();

  const [purpose, setPurpose] = useState<AIWritingPurpose>('payment_reminder');
  const [tone, setTone] = useState<AIWritingTone>('neutral');
  const [customerId, setCustomerId] = useState('');
  const [invoiceId, setInvoiceId] = useState('');
  const [customerName, setCustomerName] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [amountDue, setAmountDue] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [instructions, setInstructions] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});

  const [customers, setCustomers] = useState<CustomerOut[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [invoicesLoading, setInvoicesLoading] = useState(false);

  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<AIWritingResponse | null>(null);
  const [editedBody, setEditedBody] = useState('');
  const [copied, setCopied] = useState<'subject' | 'body' | 'all' | null>(null);

  useEffect(() => {
    customerService
      .list({ page_size: 100, status: 'active' })
      .then((res) => setCustomers(res.items))
      .catch(() => {
        /* picker is a convenience; fields remain editable by hand */
      });
  }, []);

  useEffect(() => {
    setInvoiceId('');
    if (!customerId) {
      setInvoices([]);
      return;
    }
    const c = customers.find((x) => x.id === customerId);
    if (c) setCustomerName(c.display_name);
    let cancelled = false;
    setInvoicesLoading(true);
    invoiceService
      .listInvoices({ customer_id: customerId, page_size: 100, sort: '-due_date' })
      .then((res) => {
        if (!cancelled) setInvoices(res.items.filter((inv) => Number(inv.amount_due) > 0));
      })
      .catch(() => {
        if (!cancelled) setInvoices([]);
      })
      .finally(() => {
        if (!cancelled) setInvoicesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [customerId]);

  const pickInvoice = (id: string) => {
    setInvoiceId(id);
    const inv = invoices.find((x) => x.id === id);
    if (inv) {
      setInvoiceNumber(inv.invoice_number);
      setAmountDue(formatMoney(inv.amount_due, inv.currency));
      setDueDate(formatDate(inv.due_date));
    }
  };

  const handleGenerate = async (e: FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (purpose === 'custom' && !instructions.trim()) errs.instructions = 'Tell the assistant what the note should say.';
    setErrors(errs);
    if (Object.keys(errs).length) return;

    setGenerating(true);
    try {
      const context: Record<string, string> = {};
      if (customerName.trim()) context.customer_name = customerName.trim();
      if (purpose === 'payment_reminder') {
        if (invoiceNumber.trim()) context.invoice_number = invoiceNumber.trim();
        if (amountDue.trim()) context.amount_due = amountDue.trim();
        if (dueDate.trim()) context.due_date = dueDate.trim();
      }
      const res = await aiService.generateWriting({
        purpose,
        tone,
        context,
        instructions: instructions.trim() || null,
      });
      setResult(res);
      setEditedBody(res.body);
      setCopied(null);
      showToast('success', 'Draft generated', 'Review and edit the text before sending it.');
      onActivity?.();
    } catch (err: any) {
      showToast('error', 'Could not generate text', errorMessage(err));
    } finally {
      setGenerating(false);
    }
  };

  const copy = async (what: 'subject' | 'body' | 'all') => {
    if (!result) return;
    const text =
      what === 'subject'
        ? result.subject ?? ''
        : what === 'body'
          ? editedBody
          : `${result.subject ? `Subject: ${result.subject}\n\n` : ''}${editedBody}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      showToast('success', 'Copied to clipboard');
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      showToast('error', 'Copy failed', 'Your browser blocked clipboard access.');
    }
  };

  const isReminder = purpose === 'payment_reminder';

  return (
    <div className="grid lg:grid-cols-5 divide-y lg:divide-y-0 lg:divide-x divide-slate-200 h-full">
      <form onSubmit={handleGenerate} className="lg:col-span-2 p-5 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Select
            label="Purpose"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value as AIWritingPurpose)}
            options={AI_WRITING_PURPOSES.map((p) => ({ value: p, label: PURPOSE_LABELS[p].label }))}
          />
          <Select
            label="Tone"
            value={tone}
            onChange={(e) => setTone(e.target.value as AIWritingTone)}
            options={AI_WRITING_TONES.map((t) => ({ value: t, label: TONE_LABELS[t] }))}
          />
        </div>
        <p className="text-[11px] text-slate-500 -mt-2">{PURPOSE_LABELS[purpose].description}</p>

        <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3 space-y-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Context</div>
          <Select
            label="Prefill from customer"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            placeholder="Optional — pick a customer"
            options={customers.map((c) => ({ value: c.id, label: `${c.display_name} · ${c.customer_number}` }))}
          />
          {isReminder && (
            <Select
              label="Prefill from invoice"
              value={invoiceId}
              onChange={(e) => pickInvoice(e.target.value)}
              disabled={!customerId || invoicesLoading}
              helperText={
                !customerId ? 'Pick a customer to list their unpaid invoices.' : invoicesLoading ? 'Loading…' : invoices.length === 0 ? 'No unpaid invoices for this customer.' : undefined
              }
            >
              <option value="">Optional — pick an invoice</option>
              {invoices.map((inv) => (
                <option key={inv.id} value={inv.id}>
                  {inv.invoice_number} · {formatMoney(inv.amount_due, inv.currency)} · due {formatDate(inv.due_date)}
                </option>
              ))}
            </Select>
          )}
          <Input label="Customer name" value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="Defaults to “there”" />
          {isReminder && (
            <>
              <Input label="Invoice number" value={invoiceNumber} onChange={(e) => setInvoiceNumber(e.target.value)} placeholder="e.g. INV-000123" />
              <div className="grid grid-cols-2 gap-3">
                <Input label="Amount due" value={amountDue} onChange={(e) => setAmountDue(e.target.value)} placeholder="e.g. ₹23,010.00" />
                <Input label="Due date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} placeholder="e.g. 30 Sep 2026" />
              </div>
            </>
          )}
        </div>

        <div>
          <label className={FIELD_LABEL_CLS}>
            {isReminder ? 'Additional note (optional)' : 'Instructions'}
            {!isReminder && <span className="text-rose-500 ml-0.5">*</span>}
          </label>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={3}
            maxLength={1000}
            placeholder={isReminder ? 'Appended to the reminder, e.g. UPI and bank transfer details are on the invoice.' : 'What should the note say?'}
            className={TEXTAREA_CLS}
          />
          {errors.instructions && <p className="mt-1 text-xs text-rose-600 font-medium">{errors.instructions}</p>}
        </div>

        <div className="flex justify-end">
          <Button type="submit" size="sm" isLoading={generating} leadingIcon={<Wand2 className="w-3.5 h-3.5" />}>
            Generate
          </Button>
        </div>
      </form>

      <div className="lg:col-span-3 p-5 bg-slate-50/50 min-h-[320px]">
        {!result ? (
          <EmptyState
            icon={<PenLine className="w-6 h-6 stroke-1" />}
            title="Your draft will appear here"
            description="Generated text is a starting point — edit it in place, then copy it into your email client or the invoice reminder. Nothing is sent automatically."
            className="border-slate-200 bg-white h-full"
          />
        ) : (
          <div className="rounded-xl border border-slate-200 bg-white overflow-hidden flex flex-col h-full">
            <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Mail className="w-4 h-4 text-slate-400" />
                {PURPOSE_LABELS[purpose].label} · {TONE_LABELS[tone]}
              </div>
              <Button variant="outline" size="sm" onClick={() => void copy('all')} leadingIcon={copied === 'all' ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}>
                {copied === 'all' ? 'Copied' : 'Copy all'}
              </Button>
            </div>
            {result.subject && (
              <div className="px-4 py-2.5 border-b border-slate-100 flex items-center gap-3">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 shrink-0">Subject</span>
                <span className="text-sm text-slate-900 font-medium flex-1 truncate">{result.subject}</span>
                <button type="button" onClick={() => void copy('subject')} className="p-1.5 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors" aria-label="Copy subject">
                  {copied === 'subject' ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                </button>
              </div>
            )}
            <div className="p-4 flex-1 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Body (editable)</span>
                <button type="button" onClick={() => void copy('body')} className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 transition-colors">
                  {copied === 'body' ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                  Copy body
                </button>
              </div>
              <textarea
                value={editedBody}
                onChange={(e) => setEditedBody(e.target.value)}
                rows={12}
                className={`${TEXTAREA_CLS} flex-1 font-normal leading-relaxed`}
              />
              <div className="text-[11px] text-slate-400">
                Template-generated from your context — no external model was used. Request {result.request_id.slice(0, 8)}…
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
