import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useParams, useLocation, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Plus,
  Trash2,
  Copy,
  Save,
  Send,
  AlertCircle,
  HelpCircle,
  UserPlus,
} from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { LoadingState } from '../../components/common/LoadingState';
import { validateDateNotBefore, validateNonNegativeMoney, validatePercentage, validatePositiveQuantity } from '../../utils/validation';
import { quoteService } from '../../services/quoteService';
import { customerService } from '../../services/customerService';
import { catalogCpqService } from '../../services/catalogCpqService';
import { planPricingService } from '../../services/planPricingService';
import type { CustomerOut } from '../../types/api';
import type { OfferingOut } from '../../types/catalog_cpq';
import type { QuoteItemIn } from '../../types/quotes';

interface FormLineItem extends QuoteItemIn {
  id?: string;
  name?: string;
  sku?: string;
  pricing_model?: string;
  tax_amount?: number;
  total_amount?: number;
  is_custom?: boolean;
}

export function QuoteFormPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { id } = useParams<{ id: string }>();
  const isEditing = Boolean(id);

  const [customers, setCustomers] = useState<CustomerOut[]>([]);
  const [offerings, setOfferings] = useState<OfferingOut[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Quick Customer Creation Modal State
  const [showCustomerModal, setShowCustomerModal] = useState(false);
  const [newCustName, setNewCustName] = useState('');
  const [newCustEmail, setNewCustEmail] = useState('');
  const [newCustPhone, setNewCustPhone] = useState('');
  const [newCustCompany, setNewCustCompany] = useState('');
  const [creatingCustomer, setCreatingCustomer] = useState(false);

  // Form State
  const [customerId, setCustomerId] = useState('');
  const [title, setTitle] = useState('');
  const [issueDate, setIssueDate] = useState(new Date().toISOString().split('T')[0]);
  const [expiryDate, setExpiryDate] = useState(
    new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
  );
  const [currency, setCurrency] = useState('INR');
  const [discountPct, setDiscountPct] = useState<number>(0);
  const [notes, setNotes] = useState('');
  const [terms, setTerms] = useState(
    '1. Quote valid for 30 days.\n2. Payment terms: 30 days from invoice date.\n3. Taxes as applicable per Indian GST.'
  );

  const [items, setItems] = useState<FormLineItem[]>([]);

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
      setCustomers([created, ...customers]);
      setCustomerId(created.id);
      setShowCustomerModal(false);
      setNewCustName('');
      setNewCustEmail('');
      setNewCustPhone('');
      setNewCustCompany('');
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to create customer');
    } finally {
      setCreatingCustomer(false);
    }
  };

  // Load initial data and customers / catalog offerings
  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      try {
        const [custRes, offRes] = await Promise.all([
          customerService.list({ page_size: 100 }),
          catalogCpqService.listOfferings({ page_size: 100 }),
        ]);
        setCustomers(custRes.items);
        setOfferings(offRes.items);

        if (isEditing && id) {
          const q = await quoteService.getQuote(id);
          setCustomerId(q.customer?.id || '');
          setTitle(q.title || '');
          setIssueDate(q.issue_date);
          setExpiryDate(q.expiry_date || '');
          setCurrency(q.currency || 'INR');
          setDiscountPct(Number(q.discount_pct || 0));
          setNotes(q.notes || '');
          setTerms(q.terms || '');
          setItems(
            q.items.map((it) => ({
              offering_id: it.offering_id,
              product_id: it.product_id,
              plan_id: it.plan_id,
              description: it.description,
              quantity: Number(it.quantity || 1),
              unit_price: Number(it.unit_price || 0),
              tax_rate_pct: Number(it.tax_rate_pct || 18),
              pricing_explanation: it.pricing_explanation,
            }))
          );
        } else if (location.state?.prefilledItem) {
          // Pre-filled from Pricing Simulator
          const pref = location.state.prefilledItem;
          if (location.state.prefilledCustomer) {
            setCustomerId(location.state.prefilledCustomer);
          }
          setItems([
            {
              offering_id: pref.offering_id,
              name: pref.name,
              sku: pref.sku,
              description: `${pref.name} (${pref.sku || 'Plan'})`,
              quantity: pref.quantity || 1,
              unit_price: pref.unit_price || 0,
              tax_rate_pct: pref.tax_rate_pct || 18,
              pricing_explanation: pref.pricing_explanation,
            },
          ]);
        } else if (offRes.items.length > 0) {
          // Default first item
          const firstOff = offRes.items[0];
          setItems([
            {
              offering_id: firstOff.id,
              name: firstOff.name,
              sku: firstOff.sku,
              description: `${firstOff.name} (${firstOff.sku})`,
              quantity: 1,
              unit_price: Number(firstOff.base_price || 0),
              tax_rate_pct: Number(firstOff.tax_rate_pct || 18),
              pricing_model: firstOff.pricing_model,
            },
          ]);
        }
      } catch (err) {
        console.error('Failed to load quote form data', err);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, [id, isEditing, location.state]);

  // Recalculate line pricing when offering or quantity changes
  const handleSelectOffering = async (index: number, offeringId: string) => {
    const off = offerings.find((o) => o.id === offeringId);
    if (!off) return;

    try {
      const sim = await planPricingService.simulatePricing({
        offering_id: off.id,
        customer_id: customerId || undefined,
        quantity: items[index]?.quantity || 1,
        discount_pct: 0,
      });

      const updated = [...items];
      updated[index] = {
        ...updated[index],
        offering_id: off.id,
        name: off.name,
        sku: off.sku,
        description: `${off.name} (${off.sku})`,
        unit_price: Number(sim.effective_unit_price),
        tax_rate_pct: Number(off.tax_rate_pct || 18),
        pricing_model: off.pricing_model,
        pricing_explanation: JSON.stringify(sim.explanation),
      };
      setItems(updated);
    } catch {
      const updated = [...items];
      updated[index] = {
        ...updated[index],
        offering_id: off.id,
        name: off.name,
        sku: off.sku,
        description: `${off.name} (${off.sku})`,
        unit_price: Number(off.base_price || 0),
        tax_rate_pct: Number(off.tax_rate_pct || 18),
        pricing_model: off.pricing_model,
      };
      setItems(updated);
    }
  };

  const handleQuantityChange = async (index: number, qty: number) => {
    const item = items[index];
    const newQty = Math.max(1, qty);

    if (item.offering_id) {
      try {
        const sim = await planPricingService.simulatePricing({
          offering_id: item.offering_id,
          customer_id: customerId || undefined,
          quantity: newQty,
          discount_pct: 0,
        });
        const updated = [...items];
        updated[index] = {
          ...item,
          quantity: newQty,
          unit_price: Number(sim.effective_unit_price),
          pricing_explanation: JSON.stringify(sim.explanation),
        };
        setItems(updated);
        return;
      } catch (err) {
        console.error('Pricing simulation error', err);
      }
    }

    const updated = [...items];
    updated[index] = { ...item, quantity: newQty };
    setItems(updated);
  };

  const handleAddItem = () => {
    if (offerings.length > 0) {
      const firstOff = offerings[0];
      setItems([
        ...items,
        {
          offering_id: firstOff.id,
          name: firstOff.name,
          sku: firstOff.sku,
          description: `${firstOff.name} (${firstOff.sku})`,
          quantity: 1,
          unit_price: Number(firstOff.base_price || 0),
          tax_rate_pct: Number(firstOff.tax_rate_pct || 18),
          pricing_model: firstOff.pricing_model,
        },
      ]);
    } else {
      setItems([
        ...items,
        {
          description: 'Consulting & Engineering Services',
          quantity: 1,
          unit_price: 5000,
          tax_rate_pct: 18,
          is_custom: true,
        },
      ]);
    }
  };

  const handleDuplicateItem = (index: number) => {
    const item = items[index];
    setItems([...items, { ...item }]);
  };

  const handleRemoveItem = (index: number) => {
    if (items.length === 1) return;
    setItems(items.filter((_, i) => i !== index));
  };

  // Financial Totals Computation
  const totals = useMemo(() => {
    let subtotal = 0;
    let taxTotal = 0;

    const disc = Math.max(0, Math.min(100, Number(discountPct) || 0));

    for (const item of items) {
      const qty = Number(item.quantity || 1);
      const price = Number(item.unit_price || 0);
      const taxRate = Number(item.tax_rate_pct || 0);

      const amount = qty * price;
      const taxable = amount - (amount * disc) / 100;
      const lineTax = (taxable * taxRate) / 100;

      subtotal += amount;
      taxTotal += lineTax;
    }

    const discountAmount = (subtotal * disc) / 100;
    const total = subtotal - discountAmount + taxTotal;

    return {
      subtotal,
      discountAmount,
      taxTotal,
      total,
      cgst: taxTotal / 2,
      sgst: taxTotal / 2,
    };
  }, [items, discountPct]);

  const handleSubmit = async (shouldSend = false) => {
    if (!customerId) {
      setError('Please select a customer.');
      return;
    }
    if (items.length === 0) {
      setError('At least one line item is required.');
      return;
    }

    const dateError = validateDateNotBefore(expiryDate, issueDate, 'Expiry date', 'issue date');
    if (dateError) {
      setError(dateError);
      return;
    }

    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      const label = `Line ${i + 1} (${it.description?.trim() || 'item'})`;
      if (!it.description || !it.description.trim()) {
        setError(`Line ${i + 1} must have a description.`);
        return;
      }
      const qtyError = validatePositiveQuantity(it.quantity, `${label} quantity`);
      if (qtyError) {
        setError(qtyError);
        return;
      }
      const priceError = validateNonNegativeMoney(it.unit_price, `${label} unit price`);
      if (priceError) {
        setError(priceError);
        return;
      }
      const taxError = validatePercentage(it.tax_rate_pct, `${label} tax rate`);
      if (taxError) {
        setError(taxError);
        return;
      }
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const payload = {
        customer_id: customerId,
        title: title.trim() || undefined,
        issue_date: issueDate,
        expiry_date: expiryDate || undefined,
        currency,
        discount_pct: Number(discountPct) || 0,
        notes: notes.trim() || undefined,
        terms: terms.trim() || undefined,
        items: items.map((it) => ({
          offering_id: it.offering_id || undefined,
          product_id: it.product_id || undefined,
          plan_id: it.plan_id || undefined,
          description: it.description.trim(),
          quantity: Number(it.quantity),
          unit_price: Number(it.unit_price),
          tax_rate_pct: Number(it.tax_rate_pct || 0),
          pricing_explanation: it.pricing_explanation,
        })),
      };

      let quote;
      if (isEditing && id) {
        quote = await quoteService.updateQuote(id, payload);
      } else {
        quote = await quoteService.createQuote(payload);
      }

      if (shouldSend && quote?.id) {
        await quoteService.sendQuote(quote.id);
      }

      navigate(quote?.id ? `/quotes/${quote.id}` : '/quotes');
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to save quote');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="py-24">
        <LoadingState message="Loading quote builder..." />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6 animate-in fade-in duration-150">
      {/* Top Bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/quotes">
            <Button variant="outline" size="sm" leadingIcon={<ArrowLeft className="w-3.5 h-3.5" />}>
              Back to Quotes
            </Button>
          </Link>
          <div>
            <h1 className="text-xl font-bold text-slate-900">
              {isEditing ? 'Edit Quote' : 'Create Commercial Quote'}
            </h1>
            <p className="text-xs text-slate-500">
              Configure offerings, volume pricing brackets, discounts, and terms for customer approval.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleSubmit(false)}
            isLoading={isSubmitting}
            leadingIcon={<Save className="w-4 h-4" />}
          >
            Save Draft
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => handleSubmit(true)}
            isLoading={isSubmitting}
            leadingIcon={<Send className="w-4 h-4" />}
          >
            Save & Send
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Primary Card */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-2xs space-y-6">
        {/* Section 1: Customer & Primary Terms */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-semibold text-slate-700">
                Select Customer <span className="text-red-500">*</span>
              </label>
              <button
                type="button"
                onClick={() => setShowCustomerModal(true)}
                className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1"
              >
                <UserPlus className="w-3.5 h-3.5" /> + Create Customer
              </button>
            </div>
            <select
              required
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              className="w-full px-3 py-2 text-xs font-medium rounded-lg border border-slate-200 bg-white text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10"
            >
              <option value="">Select a customer...</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.display_name} ({c.customer_number}) {c.company_name ? `- ${c.company_name}` : ''}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Currency</label>
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 bg-white font-medium text-slate-900"
            >
              <option value="INR">INR (₹)</option>
              <option value="USD">USD ($)</option>
              <option value="EUR">EUR (€)</option>
              <option value="GBP">GBP (£)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Quote Title / Subject</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Turnkey Industrial Automation Upgrade"
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Issue Date</label>
            <input
              type="date"
              required
              value={issueDate}
              onChange={(e) => setIssueDate(e.target.value)}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 font-medium text-slate-800"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Expiry Date (Valid Until)</label>
            <input
              type="date"
              value={expiryDate}
              onChange={(e) => setExpiryDate(e.target.value)}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 font-medium text-slate-800"
            />
          </div>
        </div>

        <hr className="border-slate-100" />

        {/* Section 2: Items Table */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Line Items & Offerings</h3>
              <p className="text-[11px] text-slate-500">
                Centralized pricing engine dynamically resolves volume brackets and package rates.
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddItem}
              leadingIcon={<Plus className="w-3.5 h-3.5" />}
            >
              Add Item
            </Button>
          </div>

          <div className="border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
            <table className="w-full text-left text-xs text-slate-600 border-collapse">
              <thead className="bg-slate-50 border-b border-slate-200 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-2.5 w-72">Offering / Product</th>
                  <th className="px-4 py-2.5">Description</th>
                  <th className="px-3 py-2.5 w-24">Qty</th>
                  <th className="px-3 py-2.5 w-28">Rate (₹)</th>
                  <th className="px-3 py-2.5 w-20">GST %</th>
                  <th className="px-4 py-2.5 w-28 text-right">Amount (₹)</th>
                  <th className="px-3 py-2.5 w-16 text-center"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/50">
                    <td className="px-4 py-2.5">
                      <select
                        value={item.offering_id || ''}
                        onChange={(e) => handleSelectOffering(idx, e.target.value)}
                        className="w-full px-2 py-1.5 text-xs rounded border border-slate-200 bg-white font-medium text-slate-900"
                      >
                        <option value="">Custom Item</option>
                        {offerings.map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.name} ({o.sku}) - {o.pricing_model.toUpperCase()}
                          </option>
                        ))}
                      </select>
                      {item.pricing_model && (
                        <span className="text-[10px] font-semibold text-purple-600 block mt-1 capitalize">
                          ⚡ {item.pricing_model.replace('_', ' ')} pricing active
                        </span>
                      )}
                    </td>

                    <td className="px-4 py-2.5">
                      <input
                        type="text"
                        value={item.description}
                        onChange={(e) => {
                          const updated = [...items];
                          updated[idx] = { ...item, description: e.target.value };
                          setItems(updated);
                        }}
                        placeholder="Item description..."
                        className="w-full px-2 py-1.5 text-xs rounded border border-slate-200"
                      />
                    </td>

                    <td className="px-3 py-2.5">
                      <input
                        type="number"
                        min="1"
                        value={item.quantity}
                        onChange={(e) => handleQuantityChange(idx, Number(e.target.value))}
                        className="w-full px-2 py-1.5 text-xs font-bold rounded border border-slate-200 text-center"
                      />
                    </td>

                    <td className="px-3 py-2.5">
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={item.unit_price}
                        onChange={(e) => {
                          const updated = [...items];
                          updated[idx] = { ...item, unit_price: Number(e.target.value) };
                          setItems(updated);
                        }}
                        className="w-full px-2 py-1.5 text-xs font-semibold rounded border border-slate-200 text-right font-mono"
                      />
                    </td>

                    <td className="px-3 py-2.5">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        value={item.tax_rate_pct}
                        onChange={(e) => {
                          const updated = [...items];
                          updated[idx] = { ...item, tax_rate_pct: Number(e.target.value) };
                          setItems(updated);
                        }}
                        className="w-full px-2 py-1.5 text-xs rounded border border-slate-200 text-center"
                      />
                    </td>

                    <td className="px-4 py-2.5 font-semibold text-slate-900 text-right font-mono">
                      ₹{Math.round(Number(item.quantity || 1) * Number(item.unit_price || 0)).toLocaleString('en-IN')}
                    </td>

                    <td className="px-3 py-2.5 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleDuplicateItem(idx)}
                          className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                          title="Duplicate item"
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRemoveItem(idx)}
                          disabled={items.length <= 1}
                          className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 disabled:opacity-30"
                          title="Remove item"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Section 3: Notes & Totals Breakdown */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-6 pt-4">
          <div className="md:col-span-7 space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Customer Notes</label>
              <textarea
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Notes visible to customer on quote..."
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Terms & Conditions</label>
              <textarea
                rows={3}
                value={terms}
                onChange={(e) => setTerms(e.target.value)}
                placeholder="Standard payment terms, warranty and SLA..."
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 font-mono text-[11px]"
              />
            </div>
          </div>

          <div className="md:col-span-5 bg-slate-50/80 p-4 rounded-xl border border-slate-200/80 space-y-3">
            <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Financial Summary</h4>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between text-slate-600">
                <span>Subtotal (Pre-tax)</span>
                <span className="font-mono font-medium">₹{Math.round(totals.subtotal).toLocaleString('en-IN')}</span>
              </div>

              <div className="flex items-center justify-between text-slate-600">
                <div className="flex items-center gap-1">
                  <span>Overall Discount</span>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={discountPct}
                    onChange={(e) => setDiscountPct(Math.max(0, Math.min(100, Number(e.target.value))))}
                    className="w-14 px-1.5 py-0.5 text-xs rounded border border-slate-300 font-bold text-center"
                  />
                  <span>%</span>
                </div>
                <span className="font-mono font-medium text-amber-600">
                  -₹{Math.round(totals.discountAmount).toLocaleString('en-IN')}
                </span>
              </div>

              <div className="flex justify-between text-slate-600 text-[11px] pt-1">
                <span className="text-slate-500">CGST (9%)</span>
                <span className="font-mono">₹{Math.round(totals.cgst).toLocaleString('en-IN')}</span>
              </div>

              <div className="flex justify-between text-slate-600 text-[11px]">
                <span className="text-slate-500">SGST (9%)</span>
                <span className="font-mono">₹{Math.round(totals.sgst).toLocaleString('en-IN')}</span>
              </div>

              <hr className="border-slate-200" />

              <div className="flex justify-between items-center text-sm font-bold text-slate-900 pt-1">
                <span>Total Amount ({currency})</span>
                <span className="text-base font-mono text-emerald-600">
                  ₹{Math.round(totals.total).toLocaleString('en-IN')}
                </span>
              </div>
            </div>

            {Number(discountPct) > 20 && (
              <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-lg text-[11px] text-amber-800 flex items-center gap-2">
                <HelpCircle className="w-4 h-4 shrink-0 text-amber-600" />
                <span>Discount &gt; 20% requires Manager / Admin approval prior to customer send.</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Quick Customer Creation Modal */}
      <Modal
        isOpen={showCustomerModal}
        onClose={() => setShowCustomerModal(false)}
        title="Create New Customer"
        description="Quickly add a new customer to select on this quote"
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
              <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
              <input
                type="tel"
                placeholder="+91 98765 43210"
                value={newCustPhone}
                onChange={(e) => setNewCustPhone(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
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
    </div>
  );
}

export default QuoteFormPage;
