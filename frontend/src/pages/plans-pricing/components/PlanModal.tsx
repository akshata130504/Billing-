import React, { useState, useEffect } from 'react';
import { X, Plus, Trash2, Calculator, CheckCircle2, AlertCircle } from 'lucide-react';
import { Button } from '../../../components/common/Button';
import { validateSensibleName, validateSku, validatePercentage, validateNonNegativeMoney } from '../../../utils/validation';
import { calculatePricePreview } from './planPricePreview';
import { errorSummary } from '../../../services/apiClient';
import type {
  PlanPricingItem,
  CreatePlanPricingInput,
  PlanPricingModel,
  PlanBillingFrequency,
  PlanPricingTier,
} from '../../../types/plans_pricing';

interface PlanModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: CreatePlanPricingInput) => Promise<void>;
  initialData?: PlanPricingItem | null;
}

export function PlanModal({ isOpen, onClose, onSave, initialData }: PlanModalProps) {
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('Subscriptions');
  const [unit, setUnit] = useState('subscription');
  const [currency, setCurrency] = useState('INR');
  const [billingFrequency, setBillingFrequency] = useState<PlanBillingFrequency>('monthly');
  const [pricingModel, setPricingModel] = useState<PlanPricingModel>('per_unit');
  const [basePrice, setBasePrice] = useState<number>(0);
  const [taxRatePct, setTaxRatePct] = useState<number>(18);
  const [status, setStatus] = useState<'active' | 'draft' | 'archived'>('active');
  const [tiers, setTiers] = useState<PlanPricingTier[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Live preview test quantity
  const [previewQty, setPreviewQty] = useState<number>(5);

  useEffect(() => {
    if (initialData) {
      setName(initialData.name || '');
      setCode(initialData.code || initialData.sku || '');
      setDescription(initialData.description || '');
      setCategory(initialData.category || 'Subscriptions');
      setUnit(initialData.unit || 'subscription');
      setCurrency(initialData.currency || 'INR');
      setBillingFrequency(initialData.billing_frequency || 'monthly');
      setPricingModel(initialData.pricing_model || 'per_unit');
      setBasePrice(Number(initialData.base_price || 0));
      setTaxRatePct(Number(initialData.tax_rate_pct || 18));
      setStatus(initialData.is_active ? 'active' : 'archived');
      setTiers(initialData.pricing_tiers ? JSON.parse(JSON.stringify(initialData.pricing_tiers)) : []);
    } else {
      setName('');
      setCode('');
      setDescription('');
      setCategory('Subscriptions');
      setUnit('subscription');
      setCurrency('INR');
      setBillingFrequency('monthly');
      setPricingModel('per_unit');
      setBasePrice(1000);
      setTaxRatePct(18);
      setStatus('active');
      setTiers([]);
    }
    setError(null);
  }, [initialData, isOpen]);

  if (!isOpen) return null;

  const handleAddTier = () => {
    if (pricingModel === 'package') {
      const lastTier = tiers[tiers.length - 1];
      const nextQty = lastTier?.package_qty ? lastTier.package_qty + 10 : 10;
      const nextPrice = lastTier?.package_price ? lastTier.package_price + 5000 : 5000;
      setTiers([...tiers, { package_qty: nextQty, package_price: nextPrice }]);
    } else {
      const lastTier = tiers[tiers.length - 1];
      const nextMin = lastTier?.max_qty ? lastTier.max_qty + 1 : (tiers.length ? 11 : 1);
      const nextPrice = lastTier?.unit_price ? Math.max(0, lastTier.unit_price - 100) : basePrice;
      setTiers([...tiers, { min_qty: nextMin, max_qty: nextMin + 10, unit_price: nextPrice }]);
    }
  };

  const handleRemoveTier = (index: number) => {
    setTiers(tiers.filter((_, i) => i !== index));
  };

  const handleUpdateTier = (index: number, field: keyof PlanPricingTier, value: any) => {
    const updated = [...tiers];
    updated[index] = { ...updated[index], [field]: value === '' ? undefined : Number(value) };
    setTiers(updated);
  };

  // Live price preview (same bracket semantics as backend pricing_engine).
  const preview = calculatePricePreview({ pricingModel, basePrice, taxRatePct, tiers, quantity: previewQty });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const nameError = validateSensibleName(name, 'Plan name');
    if (nameError) {
      setError(nameError);
      return;
    }
    const codeError = validateSku(code, { required: false });
    if (codeError) {
      setError(codeError);
      return;
    }
    const basePriceError = validateNonNegativeMoney(basePrice, 'Base price', { required: true });
    if (basePriceError) {
      setError(basePriceError);
      return;
    }
    const taxRateError = validatePercentage(taxRatePct, 'Tax rate', { required: false });
    if (taxRateError) {
      setError(taxRateError);
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      await onSave({
        name: name.trim(),
        code: code.trim() || undefined,
        description: description.trim() || undefined,
        category,
        unit,
        currency,
        pricing_model: pricingModel,
        base_price: Number(basePrice),
        tax_rate_pct: Number(taxRatePct),
        billing_frequency: billingFrequency,
        status,
        is_active: status === 'active',
        pricing_tiers: (pricingModel === 'volume' || pricingModel === 'tiered' || pricingModel === 'package') && tiers.length > 0 ? tiers : undefined,
      });
      onClose();
    } catch (err) {
      setError(errorSummary(err) || 'Failed to save plan');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              {initialData ? 'Edit Plan & Pricing' : 'Create New Pricing Plan'}
            </h2>
            <p className="text-xs text-slate-500">
              Configure commercial terms, billing cadence, and multi-tier pricing models.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-6">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Section 1: Basic Information */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              1. Basic Information
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Plan Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Enterprise Cloud Annual Plan"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Plan Code / SKU
                </label>
                <input
                  type="text"
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  placeholder="e.g. PLAN-ENT-ANNUAL"
                  className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800 uppercase"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Description
                </label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Detailed plan description, features included, SLA commitments..."
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Category</label>
                <input
                  type="text"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="Subscriptions, Cloud, Professional"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Status</label>
                <select
                  value={status}
                  onChange={(e: any) => setStatus(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 bg-white focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800"
                >
                  <option value="active">Active</option>
                  <option value="draft">Draft</option>
                  <option value="archived">Archived</option>
                </select>
              </div>
            </div>
          </div>

          <hr className="border-slate-100" />

          {/* Section 2: Billing & Cadence */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              2. Billing Cadence & Currency
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Billing Frequency
                </label>
                <select
                  value={billingFrequency}
                  onChange={(e: any) => setBillingFrequency(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 bg-white focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800"
                >
                  <option value="monthly">Monthly</option>
                  <option value="quarterly">Quarterly</option>
                  <option value="semiannual">Half-Yearly (Semiannual)</option>
                  <option value="yearly">Yearly (Annual)</option>
                  <option value="one_time">One-Time</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Unit of Measure</label>
                <input
                  type="text"
                  value={unit}
                  onChange={(e) => setUnit(e.target.value)}
                  placeholder="subscription, user, license"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Currency</label>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 bg-white focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800"
                >
                  <option value="INR">INR (₹)</option>
                  <option value="USD">USD ($)</option>
                  <option value="EUR">EUR (€)</option>
                  <option value="GBP">GBP (£)</option>
                </select>
              </div>
            </div>
          </div>

          <hr className="border-slate-100" />

          {/* Section 3: Pricing Model & Rates */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                3. Pricing Model & Structure
              </h3>
              <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl text-xs font-semibold text-slate-600">
                {(['flat', 'per_unit', 'volume', 'tiered', 'package'] as PlanPricingModel[]).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setPricingModel(m)}
                    className={`px-2.5 py-1 rounded-lg capitalize transition-all ${
                      pricingModel === m
                        ? 'bg-white text-slate-900 shadow-2xs font-bold'
                        : 'text-slate-500 hover:text-slate-900'
                    }`}
                  >
                    {m.replace('_', ' ')}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {pricingModel === 'flat' ? 'Fixed Flat Rate (₹)' : 'Catalog Base Rate (₹)'}
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  required
                  value={basePrice}
                  onChange={(e) => setBasePrice(Number(e.target.value))}
                  className="w-full px-3 py-2 text-xs font-semibold rounded-lg border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800"
                />
                <p className="text-[11px] text-slate-400 mt-1">
                  {pricingModel === 'flat'
                    ? 'Charged once per period regardless of seat count or quantity.'
                    : 'Base fallback unit price if no tier or volume bracket applies.'}
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Applicable GST / Tax Rate (%)
                </label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={taxRatePct}
                  onChange={(e) => setTaxRatePct(Number(e.target.value))}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800"
                />
                <p className="text-[11px] text-slate-400 mt-1">Standard 18% GST (9% CGST + 9% SGST / IGST).</p>
              </div>
            </div>

            {/* Dynamic Tiers / Package Editor */}
            {(pricingModel === 'volume' || pricingModel === 'tiered' || pricingModel === 'package') && (
              <div className="mt-4 p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-xs font-bold text-slate-800 capitalize">
                      {pricingModel === 'package' ? 'Discrete Package Blocks' : `${pricingModel} Brackets & Tiers`}
                    </h4>
                    <p className="text-[11px] text-slate-500">
                      {pricingModel === 'volume' && 'All units evaluated at the single applicable quantity bracket rate.'}
                      {pricingModel === 'tiered' && 'Incremental units evaluated progressively across each cumulative tier.'}
                      {pricingModel === 'package' && 'Defined discrete package blocks with fixed package rates.'}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleAddTier}
                    leadingIcon={<Plus className="w-3.5 h-3.5" />}
                  >
                    Add {pricingModel === 'package' ? 'Package' : 'Tier'}
                  </Button>
                </div>

                {tiers.length === 0 ? (
                  <p className="text-xs text-slate-400 italic py-2 text-center">
                    No custom tiers added yet. Default base price of ₹{basePrice} will apply.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {tiers.map((t, idx) => (
                      <div key={idx} className="flex items-center gap-2 bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs text-xs">
                        {pricingModel === 'package' ? (
                          <>
                            <span className="font-semibold text-slate-500 text-[11px] w-6">#{idx + 1}</span>
                            <div className="flex-1 flex items-center gap-2">
                              <span className="text-slate-500 text-[11px]">Package Qty:</span>
                              <input
                                type="number"
                                min="1"
                                value={t.package_qty ?? ''}
                                onChange={(e) => handleUpdateTier(idx, 'package_qty', e.target.value)}
                                className="w-24 px-2 py-1 rounded border border-slate-200 font-semibold"
                                placeholder="e.g. 10"
                              />
                            </div>
                            <div className="flex-1 flex items-center gap-2">
                              <span className="text-slate-500 text-[11px]">Package Price (₹):</span>
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                value={t.package_price ?? ''}
                                onChange={(e) => handleUpdateTier(idx, 'package_price', e.target.value)}
                                className="w-28 px-2 py-1 rounded border border-slate-200 font-semibold text-slate-900"
                                placeholder="5000"
                              />
                            </div>
                          </>
                        ) : (
                          <>
                            <span className="font-semibold text-slate-500 text-[11px] w-6">#{idx + 1}</span>
                            <div className="flex items-center gap-1">
                              <span className="text-slate-500 text-[11px]">Min:</span>
                              <input
                                type="number"
                                min="0"
                                value={t.min_qty ?? ''}
                                onChange={(e) => handleUpdateTier(idx, 'min_qty', e.target.value)}
                                className="w-20 px-2 py-1 rounded border border-slate-200 font-semibold"
                                placeholder="1"
                              />
                            </div>
                            <div className="flex items-center gap-1">
                              <span className="text-slate-500 text-[11px]">Max:</span>
                              <input
                                type="number"
                                min="0"
                                value={t.max_qty ?? ''}
                                onChange={(e) => handleUpdateTier(idx, 'max_qty', e.target.value)}
                                className="w-20 px-2 py-1 rounded border border-slate-200 font-semibold"
                                placeholder="∞"
                              />
                            </div>
                            <div className="flex-1 flex items-center gap-1 justify-end">
                              <span className="text-slate-500 text-[11px]">Rate (₹/unit):</span>
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                value={t.unit_price ?? ''}
                                onChange={(e) => handleUpdateTier(idx, 'unit_price', e.target.value)}
                                className="w-24 px-2 py-1 rounded border border-slate-200 font-semibold text-slate-900 text-right"
                                placeholder="1000"
                              />
                            </div>
                          </>
                        )}
                        <button
                          type="button"
                          onClick={() => handleRemoveTier(idx)}
                          className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <hr className="border-slate-100" />

          {/* Section 4: Live Pricing Preview */}
          <div className="p-4 rounded-xl bg-emerald-50/50 border border-emerald-200/80 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Calculator className="w-4 h-4 text-emerald-600" />
                <h4 className="text-xs font-bold text-emerald-900 uppercase tracking-wider">
                  Live Pricing Preview
                </h4>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-emerald-700 font-semibold">Simulate Quantity:</span>
                <input
                  type="number"
                  min="1"
                  value={previewQty}
                  onChange={(e) => setPreviewQty(Math.max(1, Number(e.target.value)))}
                  className="w-20 px-2 py-1 rounded-md border border-emerald-300 bg-white font-bold text-emerald-900 text-center"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs bg-white p-3 rounded-lg border border-emerald-100">
              <div>
                <p className="text-slate-400 text-[11px]">Calculated Subtotal</p>
                <p className="font-bold text-slate-900 text-sm">₹{preview.subtotal.toLocaleString('en-IN')}</p>
              </div>
              <div>
                <p className="text-slate-400 text-[11px]">Taxes ({taxRatePct}% GST)</p>
                <p className="font-bold text-slate-900 text-sm">₹{preview.tax.toLocaleString('en-IN')}</p>
              </div>
              <div>
                <p className="text-slate-400 text-[11px]">Final Total Amount</p>
                <p className="font-bold text-emerald-600 text-base">₹{preview.total.toLocaleString('en-IN')}</p>
              </div>
            </div>
            <p className="text-[11px] text-emerald-700 font-medium italic">
              💡 {preview.note}
            </p>
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
            <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              isLoading={isSubmitting}
              leadingIcon={<CheckCircle2 className="w-4 h-4" />}
            >
              {initialData ? 'Update Plan' : 'Create Plan'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
