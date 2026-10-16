import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Plus,
  Trash2,
  ArrowLeft,
  AlertCircle,
  Save,
  Send,
  Sparkles,
  UserPlus,
} from 'lucide-react';
import { invoiceService } from '../../services/invoiceService';
import { planPricingService } from '../../services/planPricingService';
import { catalogCpqService } from '../../services/catalogCpqService';
import { customerService } from '../../services/customerService';
import { quoteService } from '../../services/quoteService';
import type { InvoiceLineItemIn } from '../../types/invoices';
import type { SupplyPreview } from '../../types/quotes';
import type { PlanPricingItem } from '../../types/plans_pricing';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { loadPreferences } from '../settings/PreferencesTab';
import { PhoneInput } from '../../components/common/PhoneInput';
import { CustomerCombobox } from '../../components/common/CustomerCombobox';
import { useToast } from '../../components/common/Toast';
import { PricingExplanation } from '../../components/common/PricingExplanation';
import { toApiError } from '../../services/apiClient';
import { validateDateNotBefore, validateNonNegativeMoney, validatePercentage, validatePositiveQuantity } from '../../utils/validation';
import { currencySymbol, formatMoney, todayIso, toIsoDate } from '../../utils/format';
import { currencyChoices, currencyOptionLabel } from '../../utils/currencies';

/** A form line; `rate_overridden` marks a rate the user typed, which re-pricing must keep. */
type FormLineItem = InvoiceLineItemIn & { rate_overridden?: boolean };

export const InvoiceFormPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSendConfirm, setShowSendConfirm] = useState(false);

  // Reference data
  // Active offerings only: the pickers for new lines.
  const [plans, setPlans] = useState<PlanPricingItem[]>([]);
  const [catalogItems, setCatalogItems] = useState<any[]>([]);
  // Offerings of an existing invoice's lines that have been archived since: shown (disabled) so the
  // line stays readable, never selectable for new lines.
  const [archivedLineOfferings, setArchivedLineOfferings] = useState<any[]>([]);
  const archivedIds = useMemo(() => new Set(archivedLineOfferings.map((o) => o.id)), [archivedLineOfferings]);

  // Quick Create Customer Modal State
  const [showCustomerModal, setShowCustomerModal] = useState(false);
  const [newCustName, setNewCustName] = useState('');
  const [newCustEmail, setNewCustEmail] = useState('');
  const [newCustPhone, setNewCustPhone] = useState('');
  const [newCustCompany, setNewCustCompany] = useState('');
  const [creatingCustomer, setCreatingCustomer] = useState(false);

  // Form State
  const [customerId, setCustomerId] = useState('');
  // Read-only: the backend assigns the number from the organization's number
  // series when the invoice is created/issued.
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(todayIso());
  const [dueDate, setDueDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 30);
    return toIsoDate(d);
  });
  const [paymentTerms, setPaymentTerms] = useState('Net 30');
  const [currency, setCurrency] = useState('INR');
  const [reference, setReference] = useState('');
  const [salesperson, setSalesperson] = useState('');
  const [customerNotes, setCustomerNotes] = useState('');
  const [termsAndConditions, setTermsAndConditions] = useState(
    'Payment is due within 30 days of invoice date. Thank you for your business!'
  );
  const [adjustment, setAdjustment] = useState<number>(0);

  // GST treatment as the server will save it; null until known. No GSTIN (or an
  // export) means the server charges no GST, so the preview must not either.
  const [supply, setSupply] = useState<SupplyPreview | null>(null);
  useEffect(() => {
    let cancelled = false;
    setSupply(null);
    if (!customerId) return;
    (async () => {
      try {
        const res = await quoteService.getSupplyPreview(customerId);
        if (!cancelled) setSupply(res ?? null);
      } catch {
        if (!cancelled) setSupply(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [customerId]);
  const noGst = supply !== null && !supply.charges_gst;

  // Per-row selection counter: a pricing response is applied only if the row's
  // selection has not changed since the request was made.
  const selectionTokens = useRef<number[]>([]);
  // Text being typed in a Qty box. The line's quantity (and its repricing) only changes once the
  // text is a valid positive number, so clearing the box to retype never zeroes the line.
  const [qtyDrafts, setQtyDrafts] = useState<Record<number, string>>({});

  const [items, setItems] = useState<FormLineItem[]>([
    {
      name: '',
      description: '',
      quantity: 1,
      rate: 0,
      discount_percentage: 0,
      tax_rate: 18,
      pricing_model: 'FLAT',
      pricing_explanation: '',
    },
  ]);

  const itemsRef = useRef<FormLineItem[]>([]);
  itemsRef.current = items;

  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    try {
      setLoading(true);
      const [planRes, catRes] = await Promise.all([
        planPricingService.getPlans({ is_active: true, page_size: 100 }),
        catalogCpqService.listOfferings({ is_active: true, page_size: 100 }),
      ]);
      setPlans(planRes.items || []);
      setCatalogItems(catRes.items || []);

      if (isEdit && id) {
        const inv = await invoiceService.getInvoice(id);
        setCustomerId(inv.customer_id || (inv.customer && inv.customer.id) || '');
        setInvoiceNumber(inv.invoice_number);
        setInvoiceDate(inv.issue_date || inv.invoice_date || todayIso());
        setDueDate(inv.due_date);
        setPaymentTerms(inv.payment_terms || 'Net 30');
        setCurrency(inv.currency || 'INR');
        setReference(inv.reference || '');
        setSalesperson(inv.salesperson || '');
        setCustomerNotes(inv.notes || inv.customer_notes || '');
        setTermsAndConditions(inv.terms || inv.terms_and_conditions || '');
        setAdjustment(Number(inv.adjustment || 0));

        if (inv.items && inv.items.length > 0) {
          setItems(
            inv.items.map((it: any) => ({
              id: it.id,
              plan_id: it.plan_id,
              offering_id: it.offering_id,
              name: it.description?.split(' - ')[0] || it.name || 'Line Item',
              description: it.description || '',
              quantity: Number(it.quantity || 1),
              rate: Number(it.unit_price || it.rate || 0),
              discount_percentage: Number(it.discount_percentage || 0),
              tax_rate: Number(it.tax_rate_pct || it.tax_rate || 18),
              pricing_model: it.pricing_model || 'FLAT',
              pricing_explanation: it.pricing_explanation || '',
            }))
          );

          // A line may reference an offering that has been archived since the invoice was made. It
          // is not in the active lists, so look it up and keep it (read-only) for display.
          const activeIds = new Set([...(planRes.items || []), ...(catRes.items || [])].map((o: any) => o.id));
          const lineOfferingIds: string[] = Array.from(
            new Set<string>(
              inv.items
                .map((it: any) => it.offering_id as string | undefined)
                .filter((oid: string | undefined): oid is string => Boolean(oid) && !activeIds.has(oid as string))
            )
          );
          if (lineOfferingIds.length > 0) {
            const found = await Promise.all(
              lineOfferingIds.map((oid) =>
                Promise.resolve()
                  .then(() => catalogCpqService.getOffering(oid))
                  .catch(() => null)
              )
            );
            setArchivedLineOfferings(found.filter((o: any) => o && o.is_active === false));
          }
        }
      }
    } catch (err) {
      setError(toApiError(err).message || 'Failed to load form data');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Ask the pricing engine for the unit rate of one line at a given quantity.
   *
   * The response is merged into the *latest* state via a functional update
   * (never a stale copy of ``items``), and only when the row still refers to
   * the same plan/offering and still carries the quantity that was priced.
   * A late response for an older quantity is therefore ignored instead of
   * overwriting what the user has typed since. Only rate/pricing fields are
   * merged; a failed or zero-rate pricing call never blanks the existing rate.
   */
  const calculateLineItemPrice = async (
    index: number,
    planId: string | undefined,
    qty: number,
    token: number = selectionTokens.current[index] ?? 0
  ) => {
    const pid = planId;
    if (!pid) return;
    const pricedQuantity = Number(qty) || 1;

    try {
      const calc = await planPricingService.calculatePrice({
        plan_id: pid,
        quantity: pricedQuantity,
      });

      setItems((prev) => {
        const row = prev[index];
        if (!row) return prev;
        const rowPid = row.offering_id || row.plan_id;
        // Stale response: the row now points at another item/selection or quantity, or the
        // user has typed their own rate since.
        if (
          row.rate_overridden ||
          (selectionTokens.current[index] ?? 0) !== token ||
          rowPid !== pid ||
          (Number(row.quantity) || 1) !== pricedQuantity
        ) {
          return prev;
        }
        const returnedRate = Number(calc.unit_rate);
        // Preserve existing rate unless pricing engine returned a positive rate
        const effectiveRate = Number.isFinite(returnedRate) && returnedRate > 0 ? returnedRate : (row.rate ?? 0);
        const next = [...prev];
        next[index] = {
          ...row,
          rate: effectiveRate,
          pricing_model: calc.pricing_model || row.pricing_model,
          pricing_explanation: calc.pricing_explanation || row.pricing_explanation,
        };
        return next;
      });
    } catch (err) {
      const apiError = toApiError(err);
      if (apiError.status === 422) {
        // The offering cannot be priced (e.g. it was archived since the list loaded): say so, and
        // do not leave a NEW selection looking like a normal priced offering. A line that is
        // already on the invoice (it has an id) is never replaced.
        showToast('error', 'This offering cannot be used', apiError.message);
        setItems((prev) => {
          const row = prev[index];
          if (!row || row.id) return prev;
          if ((selectionTokens.current[index] ?? 0) !== token || (row.offering_id || row.plan_id) !== pid) return prev;
          const next = [...prev];
          next[index] = { ...row, offering_id: undefined, plan_id: undefined };
          return next;
        });
        return;
      }
      showToast('warning', 'Could not calculate price', apiError.message);
    }
  };

  const handleItemChange = (index: number, field: keyof InvoiceLineItemIn, value: any) => {
    const current = items[index];
    if (!current) return;
    setItems((prev) => {
      if (!prev[index]) return prev;
      const next = [...prev];
      const prevRate = next[index].rate;
      next[index] = { ...next[index], [field]: value };
      if (field === 'rate') {
        // A typed rate is the user's, not the engine's: keep it and drop the engine's explanation.
        next[index].rate_overridden = true;
        next[index].pricing_explanation = '';
      }
      // Never allow editing quantity or other non-rate fields to wipe out existing rate
      if (field === 'quantity' && (next[index].rate === undefined || Number.isNaN(next[index].rate))) {
        next[index].rate = prevRate ?? 0;
      }
      return next;
    });

    const pid = current.offering_id || current.plan_id;
    // A retained archived line keeps its stored rate: archived offerings cannot be priced, and
    // only its quantity (and other plain fields) are editable.
    if (field === 'quantity' && pid && !archivedIds.has(pid) && !current.rate_overridden) {
      // Only recalculate for dynamic pricing models where rate varies by volume/tier.
      // Backend models are lowercase ('flat', 'per_unit', 'tiered', ...), older
      // rows may carry 'FLAT' — compare case-insensitively.
      const itemModel = String(current.pricing_model || '').toLowerCase();
      if (itemModel && itemModel !== 'flat' && itemModel !== 'per_unit') {
        void calculateLineItemPrice(index, pid, Number(value));
      }
    }
  };

  /**
   * Single place that builds a whole line from a selection (blank/custom, a
   * plan, or a catalog offering). Everything item-specific is replaced so no
   * data of the previously selected item can leak into the new one; only the
   * quantity is kept. Plans and offerings are both catalog offerings, so the
   * id is stored in `offering_id` only (never duplicated into `plan_id`).
   */
  const applySelection = (index: number, value: string) => {
    const token = (selectionTokens.current[index] ?? 0) + 1;
    selectionTokens.current[index] = token;

    const [type, itemId] = value ? value.split(':') : ['', ''];
    const plan = type === 'plan' ? plans.find((p) => p.id === itemId) : undefined;
    const cat = type === 'offering' ? catalogItems.find((c) => c.id === itemId) : undefined;

    let build: (qty: number) => FormLineItem;
    let priceId: string | undefined;
    if (plan) {
      priceId = plan.id;
      build = (quantity) => ({
        offering_id: plan.id,
        plan_id: undefined,
        name: plan.name,
        description: plan.description || `${plan.name} (${plan.pricing_model})`,
        quantity,
        rate: Number(plan.base_price || 0),
        discount_percentage: 0,
        tax_rate: Number(plan.tax_rate_pct || 18),
        pricing_model: plan.pricing_model,
        pricing_explanation: '',
      });
    } else if (cat) {
      priceId = cat.pricing_tiers && cat.pricing_tiers.length > 0 ? cat.id : undefined;
      build = (quantity) => ({
        offering_id: cat.id,
        plan_id: undefined,
        name: cat.name,
        description: cat.description || cat.sku || cat.name,
        quantity,
        rate: Number(cat.base_price || 0),
        discount_percentage: 0,
        tax_rate: Number(cat.tax_rate_pct || 18),
        pricing_model: cat.pricing_model || 'FLAT',
        pricing_explanation: 'Base Catalog Price',
      });
    } else {
      // Blank / custom (or an unknown id): a clean line.
      build = (quantity) => ({
        offering_id: undefined,
        plan_id: undefined,
        name: '',
        description: '',
        quantity,
        rate: 0,
        discount_percentage: 0,
        tax_rate: 18,
        pricing_model: 'FLAT',
        pricing_explanation: '',
      });
    }

    const quantity = itemsRef.current[index]?.quantity ?? 1;
    setItems((prev) => {
      const row = prev[index];
      if (!row) return prev;
      const next = [...prev];
      next[index] = build(row.quantity);
      return next;
    });

    if (priceId) {
      void calculateLineItemPrice(index, priceId, quantity, token);
    }
  };

  const handleUnifiedItemSelect = (index: number, value: string) => applySelection(index, value);

  const lineSelectValue = (item: InvoiceLineItemIn): string => {
    const id = item.offering_id || item.plan_id;
    if (!id) return '';
    if (plans.some((p) => p.id === id)) return `plan:${id}`;
    if (catalogItems.some((c) => c.id === id)) return `offering:${id}`;
    if (archivedIds.has(id)) return `offering:${id}`;
    return '';
  };

  const addItemRow = () => {
    setItems((prev) => [
      ...prev,
      {
        name: '',
        description: '',
        quantity: 1,
        rate: 0,
        discount_percentage: 0,
        tax_rate: 18,
        pricing_model: 'FLAT',
        pricing_explanation: '',
      },
    ]);
  };

  const removeItemRow = (index: number) => {
    if (items.length === 1) return;
    selectionTokens.current.splice(index, 1);
    setQtyDrafts({}); // drafts are keyed by row index, which shifts
    setItems((prev) => prev.filter((_, i) => i !== index));
  };

  // Calculation summaries
  const subtotal = items.reduce((acc, it) => acc + (Number(it.quantity) || 0) * (Number(it.rate) || 0), 0);
  const discountAmount = items.reduce((acc, it) => {
    const lineSub = (Number(it.quantity) || 0) * (Number(it.rate) || 0);
    return acc + lineSub * ((Number(it.discount_percentage) || 0) / 100);
  }, 0);
  const taxableAmount = subtotal - discountAmount;
  const taxAmount = items.reduce((acc, it) => {
    const lineSub = (Number(it.quantity) || 0) * (Number(it.rate) || 0);
    const lineDisc = lineSub * ((Number(it.discount_percentage) || 0) / 100);
    const lineTaxable = lineSub - lineDisc;
    return acc + lineTaxable * ((noGst ? 0 : Number(it.tax_rate) || 0) / 100);
  }, 0);
  const grandTotal = taxableAmount + taxAmount + (Number(adjustment) || 0);

  const handleQuickCreateCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCustName.trim()) return;

    try {
      setCreatingCustomer(true);
      const created = await customerService.create({
        display_name: newCustName.trim(),
        company_name: newCustCompany.trim() || undefined,
        email: newCustEmail.trim() || undefined,
        phone: newCustPhone.trim() || undefined,
        currency: 'INR',
      });
      setCustomerId(created.id);
      showToast('success', 'Customer created', created.display_name);
      setShowCustomerModal(false);
      setNewCustName('');
      setNewCustEmail('');
      setNewCustPhone('');
      setNewCustCompany('');
    } catch (err) {
      showToast('error', 'Failed to create customer', toApiError(err).message);
    } finally {
      setCreatingCustomer(false);
    }
  };

  const handleSaveAndSendClick = (e: React.MouseEvent) => {
    e.preventDefault();
    const prefs = loadPreferences();
    if (prefs.confirmBeforeSendInvoice) {
      setShowSendConfirm(true);
    } else {
      void handleSubmit(e, true);
    }
  };

  const handleSubmit = async (e?: React.FormEvent, sendAfter: boolean = false) => {
    if (e) e.preventDefault();
    if (!customerId) {
      setError('Please select a customer');
      return;
    }
    if (items.some((it) => !it.name.trim())) {
      setError('All line items must have a name');
      return;
    }

    const dateError = validateDateNotBefore(dueDate, invoiceDate, 'Due date', 'invoice date');
    if (dateError) {
      setError(dateError);
      return;
    }

    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      const label = `Line ${i + 1} (${it.name.trim() || 'item'})`;
      const qtyError = validatePositiveQuantity(it.quantity, `${label} quantity`);
      if (qtyError) {
        setError(qtyError);
        return;
      }
      const rateError = validateNonNegativeMoney(it.rate, `${label} rate`);
      if (rateError) {
        setError(rateError);
        return;
      }
      const taxError = validatePercentage(it.tax_rate, `${label} tax rate`);
      if (taxError) {
        setError(taxError);
        return;
      }
    }

    try {
      setLoading(true);
      setError(null);

      const payload = {
        customer_id: customerId,
        issue_date: invoiceDate || todayIso(),
        due_date: dueDate || todayIso(),
        currency,
        discount_pct: 0,
        notes: customerNotes.trim() || undefined,
        terms: termsAndConditions.trim() || undefined,
        items: items.map((it, idx) => {
          const lineDesc = it.description && it.description.trim()
            ? (it.description.trim().startsWith(it.name.trim()) ? it.description.trim() : `${it.name.trim()} - ${it.description.trim()}`)
            : (it.name.trim() || `Item ${idx + 1}`);
          return {
            // Only lines kept from the stored invoice carry an id; new lines never do.
            id: isEdit ? it.id || undefined : undefined,
            offering_id: it.offering_id || undefined,
            plan_id: it.plan_id || undefined,
            description: lineDesc,
            quantity: Number(it.quantity) || 1,
            unit_price: Number(it.rate) || 0,
            tax_rate_pct: Number(it.tax_rate) || 0,
            pricing_explanation: it.pricing_explanation || undefined,
          };
        }),
      };

      let result;
      if (isEdit && id) {
        result = await invoiceService.updateInvoice(id, payload);
      } else {
        result = await invoiceService.createInvoice(payload);
      }

      if (sendAfter && result?.id) {
        const sent = await invoiceService.sendInvoice(result.id);
        if (sent.email_delivery_failed) {
          showToast(
            'warning',
            'Email not delivered',
            'Invoice marked as sent, but the email could not be delivered. Check your SMTP settings under Settings > Integrations.',
            8000
          );
        } else {
          showToast('success', 'Invoice sent');
        }
      } else {
        showToast('success', isEdit ? 'Invoice updated' : 'Invoice saved as draft');
      }

      navigate(`/invoices/${result.id}`);
    } catch (err) {
      setError(toApiError(err).message || 'Failed to save invoice');
    } finally {
      setLoading(false);
    }
  };


  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/invoices')}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {isEdit ? `Edit Invoice${invoiceNumber ? ` (${invoiceNumber})` : ''}` : 'New Invoice'}
            </h1>
            <p className="text-sm text-gray-500">Generate an invoice with centralized pricing & tax computation</p>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={(e) => handleSubmit(e, false)} className="space-y-6">
        {/* Customer & Invoice Meta Details */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Customer Selector */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-sm font-medium text-gray-700">
                  Customer <span className="text-red-500">*</span>
                </label>
                <button
                  type="button"
                  onClick={() => setShowCustomerModal(true)}
                  className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1"
                >
                  <UserPlus className="w-3.5 h-3.5" /> + Create Customer
                </button>
              </div>
              <CustomerCombobox
                required
                value={customerId}
                onChange={(nextId) => setCustomerId(nextId)}
                placeholder="Search customers by name or email..."
              />
            </div>

            {/* Invoice Number & Reference */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Invoice Number</label>
                <input
                  type="text"
                  value={invoiceNumber || 'Assigned automatically when issued'}
                  readOnly
                  aria-readonly="true"
                  tabIndex={-1}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-gray-50 text-gray-500 cursor-not-allowed focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Order/Ref #</label>
                <input
                  type="text"
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                  placeholder="PO-2026-X"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>
            </div>
          </div>

          {/* Dates, Terms & Salesperson */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 pt-4 border-t border-gray-100">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Invoice Date</label>
              <input
                type="date"
                value={invoiceDate}
                onChange={(e) => setInvoiceDate(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Due Date</label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Payment Terms</label>
              <select
                value={paymentTerms}
                onChange={(e) => setPaymentTerms(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              >
                <option value="Due on Receipt">Due on Receipt</option>
                <option value="Net 15">Net 15</option>
                <option value="Net 30">Net 30</option>
                <option value="Net 60">Net 60</option>
              </select>
            </div>
            <div>
              <label htmlFor="invoice-currency" className="block text-sm font-medium text-gray-700 mb-1">Currency</label>
              <select
                id="invoice-currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              >
                {currencyChoices(currency).map((c) => (
                  <option key={c} value={c}>
                    {currencyOptionLabel(c)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Salesperson</label>
              <input
                type="text"
                placeholder="e.g. Sales Rep"
                value={salesperson}
                onChange={(e) => setSalesperson(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
          </div>
        </div>

        {/* Line Items Table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-base font-semibold text-gray-900">Line Items</h3>
            <span className="text-xs text-indigo-600 bg-indigo-50 px-2.5 py-1 rounded-md font-medium flex items-center gap-1">
              <Sparkles className="w-3.5 h-3.5" /> Pricing Engine Active
            </span>
          </div>

          <div className="space-y-4">
            {items.map((item, index) => (
              <div
                key={index}
                className="p-4 border border-gray-200 rounded-lg bg-gray-50/50 space-y-3 relative group"
              >
                <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-start">
                  {/* Select Plan / Offering or Item Name */}
                  <div className="md:col-span-5 space-y-2">
                    <label className="block text-xs font-semibold text-gray-600 uppercase">
                      Select Item / Plan / Custom
                    </label>
                    <select
                      value={lineSelectValue(item)}
                      onChange={(e) => handleUnifiedItemSelect(index, e.target.value)}
                      className="w-full px-3 py-1.5 bg-white border border-gray-300 rounded-md text-xs font-medium focus:ring-1 focus:ring-indigo-500"
                    >
                      <option value="">-- Choose from Catalog / Plans (or enter custom) --</option>
                      {plans.length > 0 && (
                        <optgroup label="Plans & Pricing">
                          {plans.map((p) => (
                            <option key={`p-${p.id}`} value={`plan:${p.id}`}>
                              Plan: {p.name} ({p.pricing_model || 'per_unit'} • {formatMoney(p.base_price || 0, p.currency || 'INR')})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {catalogItems.length > 0 && (
                        <optgroup label="Catalog Offerings (Products / Services / Bundles)">
                          {catalogItems.map((c) => (
                            <option key={`c-${c.id}`} value={`offering:${c.id}`}>
                              {c.type ? c.type.toUpperCase() : 'PRODUCT'}: {c.name} ({formatMoney(c.base_price || 0, c.currency || 'INR')})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {archivedLineOfferings
                        .filter((o) => o.id === item.offering_id)
                        .map((o) => (
                          <option key={`a-${o.id}`} value={`offering:${o.id}`} disabled>
                            {o.type ? o.type.toUpperCase() : 'PRODUCT'}: {o.name} ({formatMoney(o.base_price || 0, o.currency || 'INR')}) (Archived)
                          </option>
                        ))}
                    </select>

                    <input
                      type="text"
                      placeholder="Item Name (e.g. Cloud Hosting)"
                      value={item.name}
                      onChange={(e) => handleItemChange(index, 'name', e.target.value)}
                      required
                      className="w-full px-3 py-1.5 bg-white border border-gray-300 rounded-md text-sm font-medium focus:ring-1 focus:ring-indigo-500"
                    />
                    <input
                      type="text"
                      placeholder="Description / notes (optional)"
                      value={item.description || ''}
                      onChange={(e) => handleItemChange(index, 'description', e.target.value)}
                      className="w-full px-3 py-1 bg-white border border-gray-200 rounded text-xs text-gray-600 focus:ring-1 focus:ring-indigo-500"
                    />

                    {item.pricing_explanation && <PricingExplanation value={item.pricing_explanation} />}
                  </div>

                  {/* Quantity */}
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                      Qty
                    </label>
                    <input
                      type="number"
                      min="1"
                      aria-label={`Line ${index + 1} quantity`}
                      value={qtyDrafts[index] ?? item.quantity}
                      onChange={(e) => {
                        const text = e.target.value;
                        setQtyDrafts((d) => ({ ...d, [index]: text }));
                        const qty = Number(text);
                        if (text.trim() !== '' && Number.isFinite(qty) && qty > 0) {
                          handleItemChange(index, 'quantity', qty);
                        }
                      }}
                      onBlur={() =>
                        setQtyDrafts((d) => {
                          const next = { ...d };
                          delete next[index];
                          return next;
                        })
                      }
                      className="w-full px-3 py-1.5 bg-white border border-gray-300 rounded-md text-sm text-right focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>

                  {/* Rate */}
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                      Rate ({currencySymbol(currency)})
                    </label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={item.rate}
                      onChange={(e) => handleItemChange(index, 'rate', Number(e.target.value))}
                      className="w-full px-3 py-1.5 bg-white border border-gray-300 rounded-md text-sm text-right focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>

                  {/* Tax % */}
                  <div className="md:col-span-1">
                    <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                      Tax %
                    </label>
                    <select
                      value={item.tax_rate}
                      onChange={(e) => handleItemChange(index, 'tax_rate', Number(e.target.value))}
                      className="w-full px-2 py-1.5 bg-white border border-gray-300 rounded-md text-sm focus:ring-1 focus:ring-indigo-500"
                    >
                      <option value="0">0%</option>
                      <option value="5">5%</option>
                      <option value="12">12%</option>
                      <option value="18">18%</option>
                      <option value="28">28%</option>
                    </select>
                  </div>

                  {/* Line Total */}
                  <div className="md:col-span-2 flex items-center justify-between pt-5">
                    <div className="text-right w-full pr-3">
                      <span className="text-xs text-gray-400 block">Amount</span>
                      <span className="text-sm font-bold text-gray-900">
                        {formatMoney(
                          (Number(item.quantity) || 0) *
                            (Number(item.rate) || 0) *
                            (1 + (noGst ? 0 : Number(item.tax_rate) || 0) / 100),
                          currency
                        )}
                      </span>
                    </div>
                    {items.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeItemRow(index)}
                        className="text-gray-400 hover:text-red-500 transition-colors p-1"
                        title="Remove Row"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}

            <Button type="button" variant="secondary" onClick={addItemRow}>
              <Plus className="w-4 h-4 mr-1.5" /> Add Line Item
            </Button>
          </div>

          {/* Totals Section */}
          <div className="mt-8 border-t border-gray-100 pt-6 flex justify-end">
            <div className="w-full sm:w-80 space-y-2.5 text-sm">
              <div className="flex justify-between text-gray-600">
                <span>Subtotal</span>
                <span>{formatMoney(subtotal, currency)}</span>
              </div>
              <div className="flex justify-between text-gray-600">
                <span>Tax</span>
                <span>+{formatMoney(taxAmount, currency)}</span>
              </div>
              {noGst && (
                <p className="text-xs text-amber-700" data-testid="no-gst-notice">
                  {supply?.supply_type === 'export' ? (
                    'GST is not charged on an export supply.'
                  ) : (
                    <>
                      GST is not charged because your organization has no GSTIN — add it in{' '}
                      <Link to="/settings/organization" className="underline font-medium">
                        Settings → Organization
                      </Link>
                      .
                    </>
                  )}
                </p>
              )}
              <div className="flex items-center justify-between text-gray-600 gap-2">
                <span>Adjustment</span>
                <input
                  type="number"
                  step="0.01"
                  value={adjustment}
                  onChange={(e) => setAdjustment(Number(e.target.value))}
                  className="w-24 px-2 py-1 text-right border border-gray-300 rounded text-xs focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="flex justify-between text-lg font-bold text-gray-900 border-t border-gray-200 pt-3">
                <span>Total Amount</span>
                <span className="text-indigo-600">
                  {formatMoney(grandTotal, currency)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Notes & Terms */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Customer Notes</label>
            <textarea
              value={customerNotes}
              onChange={(e) => setCustomerNotes(e.target.value)}
              rows={3}
              placeholder="Notes for client..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Terms & Conditions</label>
            <textarea
              value={termsAndConditions}
              onChange={(e) => setTermsAndConditions(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
          </div>
        </div>

        {/* Actions bar */}
        <div className="flex flex-wrap justify-end items-center gap-3 pt-4">
          <Button type="button" variant="secondary" onClick={() => navigate('/invoices')}>
            Cancel
          </Button>
          <Button type="submit" variant="secondary" disabled={loading}>
            <Save className="w-4 h-4 mr-1.5" /> Save as Draft
          </Button>
          <Button
            type="button"
            variant="primary"
            onClick={handleSaveAndSendClick}
            disabled={loading}
          >
            <Send className="w-4 h-4 mr-1.5" /> Save & Send
          </Button>
        </div>
      </form>

      {/* Quick Customer Creation Modal */}
      <Modal
        isOpen={showCustomerModal}
        onClose={() => setShowCustomerModal(false)}
        title="Create New Customer"
        description="Quickly add a new customer to select on this invoice"
      >
        <form onSubmit={handleQuickCreateCustomer} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Customer / Contact Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              required
              placeholder="e.g. John Doe or Acme Corp"
              value={newCustName}
              onChange={(e) => setNewCustName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Company Name</label>
            <input
              type="text"
              placeholder="e.g. Acme Innovations Pvt Ltd"
              value={newCustCompany}
              onChange={(e) => setNewCustCompany(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                placeholder="billing@example.com"
                value={newCustEmail}
                onChange={(e) => setNewCustEmail(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <PhoneInput label="Phone" value={newCustPhone} onChange={setNewCustPhone} />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-gray-100">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setShowCustomerModal(false)}
              disabled={creatingCustomer}
            >
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={creatingCustomer || !newCustName.trim()}>
              {creatingCustomer ? 'Creating...' : 'Create & Select Customer'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Send Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showSendConfirm}
        onClose={() => setShowSendConfirm(false)}
        onConfirm={async () => {
          setShowSendConfirm(false);
          await handleSubmit(undefined, true);
        }}
        title="Save & Send Invoice"
        description="Are you sure you want to save and immediately dispatch this invoice to the customer?"
        confirmLabel="Send Invoice"
        isLoading={loading}
      />
    </div>
  );
};
