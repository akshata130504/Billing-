import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Plus,
  Trash2,
  ArrowLeft,
  HelpCircle,
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
import type { InvoiceLineItemIn } from '../../types/invoices';
import type { PlanPricingItem } from '../../types/plans_pricing';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { PhoneInput } from '../../components/common/PhoneInput';
import { validateDateNotBefore, validateNonNegativeMoney, validatePercentage, validatePositiveQuantity } from '../../utils/validation';

export const InvoiceFormPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reference data
  const [customers, setCustomers] = useState<any[]>([]);
  const [customerSearch, setCustomerSearch] = useState('');
  const [plans, setPlans] = useState<PlanPricingItem[]>([]);
  const [catalogItems, setCatalogItems] = useState<any[]>([]);

  // Quick Create Customer Modal State
  const [showCustomerModal, setShowCustomerModal] = useState(false);
  const [newCustName, setNewCustName] = useState('');
  const [newCustEmail, setNewCustEmail] = useState('');
  const [newCustPhone, setNewCustPhone] = useState('');
  const [newCustCompany, setNewCustCompany] = useState('');
  const [creatingCustomer, setCreatingCustomer] = useState(false);

  // Form State
  const [customerId, setCustomerId] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(new Date().toISOString().split('T')[0]);
  const [dueDate, setDueDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 30);
    return d.toISOString().split('T')[0];
  });
  const [paymentTerms, setPaymentTerms] = useState('Net 30');
  const [reference, setReference] = useState('');
  const [salesperson, setSalesperson] = useState('');
  const [customerNotes, setCustomerNotes] = useState('');
  const [termsAndConditions, setTermsAndConditions] = useState(
    'Payment is due within 30 days of invoice date. Thank you for your business!'
  );
  const [adjustment, setAdjustment] = useState<number>(0);

  const [items, setItems] = useState<InvoiceLineItemIn[]>([
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

  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    try {
      setLoading(true);
      const [custRes, planRes, catRes] = await Promise.all([
        customerService.list({ page_size: 100 }),
        planPricingService.getPlans({ page_size: 100 }),
        catalogCpqService.listOfferings({ page_size: 100 }),
      ]);
      setCustomers(custRes.items || []);
      setPlans(planRes.items || []);
      setCatalogItems(catRes.items || []);

      if (isEdit && id) {
        const inv = await invoiceService.getInvoice(id);
        setCustomerId(inv.customer_id || (inv.customer && inv.customer.id) || '');
        setInvoiceNumber(inv.invoice_number);
        setInvoiceDate(inv.issue_date || inv.invoice_date || new Date().toISOString().split('T')[0]);
        setDueDate(inv.due_date);
        setPaymentTerms(inv.payment_terms || 'Net 30');
        setReference(inv.reference || '');
        setSalesperson(inv.salesperson || '');
        setCustomerNotes(inv.notes || inv.customer_notes || '');
        setTermsAndConditions(inv.terms || inv.terms_and_conditions || '');
        setAdjustment(Number(inv.adjustment || 0));

        if (inv.items && inv.items.length > 0) {
          setItems(
            inv.items.map((it: any) => ({
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
        }
      } else {
        const genNum = `INV-${new Date().getFullYear()}-${Math.floor(1000 + Math.random() * 9000)}`;
        setInvoiceNumber(genNum);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load form data');
    } finally {
      setLoading(false);
    }
  };

  const calculateLineItemPrice = async (index: number, planId?: string, qty?: number) => {
    const targetItem = items[index];
    if (!targetItem) return;
    const pid = planId || targetItem.plan_id || targetItem.offering_id;
    const quantity = qty !== undefined ? qty : targetItem.quantity;

    if (!pid) return;

    try {
      const calc = await planPricingService.calculatePrice({
        plan_id: pid,
        quantity: Number(quantity) || 1,
      });

      const updated = [...items];
      if (!updated[index]) return;
      const returnedRate = Number(calc.unit_rate);
      // Preserve existing rate unless pricing engine returned a positive rate
      const effectiveRate = returnedRate > 0 ? returnedRate : (updated[index].rate ?? 0);
      updated[index] = {
        ...updated[index],
        rate: effectiveRate,
        pricing_model: calc.pricing_model || updated[index].pricing_model,
        pricing_explanation: calc.pricing_explanation || updated[index].pricing_explanation,
      };
      setItems(updated);
    } catch (err) {
      console.error('Pricing calculation failed:', err);
    }
  };

  const handleItemChange = (index: number, field: keyof InvoiceLineItemIn, value: any) => {
    const updated = [...items];
    const prevRate = updated[index]?.rate;
    updated[index] = { ...updated[index], [field]: value };
    // Never allow editing quantity or other non-rate fields to wipe out existing rate
    if (field === 'quantity' && (updated[index].rate === undefined || Number.isNaN(updated[index].rate))) {
      updated[index].rate = prevRate ?? 0;
    }
    setItems(updated);

    if (field === 'quantity' && (updated[index].plan_id || updated[index].offering_id)) {
      const itemModel = updated[index].pricing_model;
      // Only recalculate for dynamic pricing models where rate varies by volume/tier
      if (itemModel && itemModel !== 'FLAT' && itemModel !== 'per_unit') {
        calculateLineItemPrice(index, updated[index].plan_id || updated[index].offering_id, value);
      }
    }
  };

  const handleUnifiedItemSelect = async (index: number, value: string) => {
    if (!value) {
      const updated = [...items];
      updated[index] = {
        ...updated[index],
        plan_id: undefined,
        offering_id: undefined,
        pricing_explanation: '',
      };
      setItems(updated);
      return;
    }

    const [type, itemId] = value.split(':');
    if (type === 'plan') {
      const plan = plans.find((p) => p.id === itemId);
      if (!plan) return;

      const updated = [...items];
      updated[index] = {
        ...updated[index],
        plan_id: plan.id,
        offering_id: plan.id,
        name: plan.name,
        description: plan.description || `${plan.name} (${plan.pricing_model})`,
        rate: Number(plan.base_price || 0),
        tax_rate: Number(plan.tax_rate_pct || 18),
        pricing_model: plan.pricing_model,
      };
      setItems(updated);

      await calculateLineItemPrice(index, plan.id, updated[index].quantity);
    } else if (type === 'offering') {
      const cat = catalogItems.find((c) => c.id === itemId);
      if (!cat) return;

      const updated = [...items];
      updated[index] = {
        ...updated[index],
        offering_id: cat.id,
        plan_id: cat.type === 'plan' ? cat.id : undefined,
        name: cat.name,
        description: cat.description || cat.sku || cat.name,
        rate: Number(cat.base_price || 0),
        tax_rate: Number(cat.tax_rate_pct || 18),
        pricing_model: cat.pricing_model || 'FLAT',
        pricing_explanation: 'Base Catalog Price',
      };
      setItems(updated);

      if (cat.pricing_tiers && cat.pricing_tiers.length > 0) {
        await calculateLineItemPrice(index, cat.id, updated[index].quantity);
      }
    }
  };

  const addItemRow = () => {
    setItems([
      ...items,
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
    setItems(items.filter((_, i) => i !== index));
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
    return acc + lineTaxable * ((Number(it.tax_rate) || 0) / 100);
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

  const handleSubmit = async (e: React.FormEvent, sendAfter: boolean = false) => {
    e.preventDefault();
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
        issue_date: invoiceDate || new Date().toISOString().split('T')[0],
        due_date: dueDate || new Date().toISOString().split('T')[0],
        currency: 'INR',
        discount_pct: 0,
        notes: customerNotes.trim() || undefined,
        terms: termsAndConditions.trim() || undefined,
        items: items.map((it, idx) => {
          const lineDesc = it.description && it.description.trim()
            ? (it.description.trim().startsWith(it.name.trim()) ? it.description.trim() : `${it.name.trim()} - ${it.description.trim()}`)
            : (it.name.trim() || `Item ${idx + 1}`);
          return {
            offering_id: it.offering_id || it.plan_id || undefined,
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
        await invoiceService.sendInvoice(result.id);
      }

      navigate(`/invoices/${result.id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to save invoice');
    } finally {
      setLoading(false);
    }
  };

  const filteredCustomers = customers.filter(
    (c) =>
      c.displayName?.toLowerCase().includes(customerSearch.toLowerCase()) ||
      c.display_name?.toLowerCase().includes(customerSearch.toLowerCase()) ||
      c.name?.toLowerCase().includes(customerSearch.toLowerCase()) ||
      c.email?.toLowerCase().includes(customerSearch.toLowerCase())
  );

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
              {isEdit ? `Edit Invoice (${invoiceNumber})` : 'New Invoice'}
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
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder="Type to filter customers..."
                  value={customerSearch}
                  onChange={(e) => setCustomerSearch(e.target.value)}
                  className="w-full px-3 py-1.5 border border-gray-200 rounded-md text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <select
                  value={customerId}
                  onChange={(e) => setCustomerId(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                >
                  <option value="">-- Select Customer --</option>
                  {filteredCustomers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.display_name || c.displayName || c.name} {c.email ? `(${c.email})` : ''}
                    </option>
                  ))}
                </select>
                {filteredCustomers.length === 0 && (
                  <p className="text-xs text-amber-600">
                    No customer matches "{customerSearch}". Click <strong>+ Create Customer</strong> above to add one.
                  </p>
                )}
              </div>
            </div>

            {/* Invoice Number & Reference */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Invoice Number <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={invoiceNumber}
                  onChange={(e) => setInvoiceNumber(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
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
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 pt-4 border-t border-gray-100">
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
                      value={
                        item.plan_id
                          ? `plan:${item.plan_id}`
                          : item.offering_id
                          ? `offering:${item.offering_id}`
                          : ''
                      }
                      onChange={(e) => handleUnifiedItemSelect(index, e.target.value)}
                      className="w-full px-3 py-1.5 bg-white border border-gray-300 rounded-md text-xs font-medium focus:ring-1 focus:ring-indigo-500"
                    >
                      <option value="">-- Choose from Catalog / Plans (or enter custom) --</option>
                      {plans.length > 0 && (
                        <optgroup label="Plans & Pricing">
                          {plans.map((p) => (
                            <option key={`p-${p.id}`} value={`plan:${p.id}`}>
                              Plan: {p.name} ({p.pricing_model || 'per_unit'} • ₹{Number(p.base_price || 0).toLocaleString()})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {catalogItems.length > 0 && (
                        <optgroup label="Catalog Offerings (Products / Services / Bundles)">
                          {catalogItems.map((c) => (
                            <option key={`c-${c.id}`} value={`offering:${c.id}`}>
                              {c.type ? c.type.toUpperCase() : 'PRODUCT'}: {c.name} (₹{Number(c.base_price || 0).toLocaleString()})
                            </option>
                          ))}
                        </optgroup>
                      )}
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

                    {item.pricing_explanation && (
                      <div className="flex items-center gap-1 text-xs text-indigo-700 bg-indigo-50 px-2 py-1 rounded">
                        <HelpCircle className="w-3.5 h-3.5 flex-shrink-0" />
                        <span className="truncate">{item.pricing_explanation}</span>
                      </div>
                    )}
                  </div>

                  {/* Quantity */}
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                      Qty
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={item.quantity}
                      onChange={(e) => handleItemChange(index, 'quantity', Number(e.target.value))}
                      className="w-full px-3 py-1.5 bg-white border border-gray-300 rounded-md text-sm text-right focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>

                  {/* Rate */}
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                      Rate (₹)
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
                        ₹
                        {(
                          (Number(item.quantity) || 0) *
                          (Number(item.rate) || 0) *
                          (1 + (Number(item.tax_rate) || 0) / 100)
                        ).toLocaleString(undefined, { maximumFractionDigits: 2 })}
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
                <span>₹{subtotal.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
              </div>
              <div className="flex justify-between text-gray-600">
                <span>Tax</span>
                <span>+₹{taxAmount.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
              </div>
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
                  ₹{grandTotal.toLocaleString(undefined, { maximumFractionDigits: 2 })}
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
        <div className="flex justify-end items-center gap-3 pt-4">
          <Button type="button" variant="secondary" onClick={() => navigate('/invoices')}>
            Cancel
          </Button>
          <Button type="submit" variant="secondary" disabled={loading}>
            <Save className="w-4 h-4 mr-1.5" /> Save as Draft
          </Button>
          <Button
            type="button"
            variant="primary"
            onClick={(e: React.MouseEvent) => handleSubmit(e, true)}
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
    </div>
  );
};
