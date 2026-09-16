import { useState } from 'react';
import { X, Plus, Trash2, Layers, AlertCircle } from 'lucide-react';
import { Button } from '../../../components/common/Button';
import { validateSensibleName, validateSku, validatePercentage, validateNonNegativeMoney, parseStrictNumber } from '../../../utils/validation';
import type { OfferingIn, OfferingOut, OfferingType, OfferingPricingModel, PricingTier, BundleComponent } from '../../../types/catalog_cpq';

interface OfferingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: OfferingIn) => Promise<void>;
  initialData?: OfferingOut | null;
  availableOfferings?: OfferingOut[];
}

export const OfferingModal: React.FC<OfferingModalProps> = ({
  isOpen,
  onClose,
  onSave,
  initialData,
  availableOfferings = [],
}) => {
  if (!isOpen) return null;

  const [name, setName] = useState(initialData?.name || '');
  const [sku, setSku] = useState(initialData?.sku || '');
  const [type, setType] = useState<OfferingType>(initialData?.type || 'product');
  const [category, setCategory] = useState(initialData?.category || 'General');
  const [unit] = useState(initialData?.unit || 'unit');
  const [pricingModel, setPricingModel] = useState<OfferingPricingModel>(initialData?.pricing_model || 'per_unit');
  const [basePrice, setBasePrice] = useState(initialData?.base_price || '0.00');
  const [taxRatePct, setTaxRatePct] = useState(initialData?.tax_rate_pct || '18.00');
  const [billingFrequency, setBillingFrequency] = useState(initialData?.billing_frequency || 'one_time');
  const [description, setDescription] = useState(initialData?.description || '');

  // Volume / Tiered brackets
  const [pricingTiers, setPricingTiers] = useState<PricingTier[]>(
    initialData?.pricing_tiers || [
      { min_qty: 0, max_qty: 100, unit_price: Number(initialData?.base_price || 0) },
    ]
  );

  // Bundle components
  const [bundleComponents, setBundleComponents] = useState<
    Array<{
      component_offering_id: string;
      is_required: boolean;
      default_quantity: number;
      discount_pct: number;
    }>
  >(
    initialData?.bundle_components?.map((b: BundleComponent) => ({
      component_offering_id: b.component_offering_id,
      is_required: b.is_required,
      default_quantity: Number(b.default_quantity || 1),
      discount_pct: Number(b.discount_pct || 0),
    })) || []
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const nameError = validateSensibleName(name, 'Offering name');
    if (nameError) {
      setError(nameError);
      return;
    }
    const skuError = validateSku(sku, { required: false });
    if (skuError) {
      setError(skuError);
      return;
    }
    const basePriceError = validateNonNegativeMoney(basePrice, 'Catalog base price', { required: true });
    if (basePriceError) {
      setError(basePriceError);
      return;
    }
    const taxRateError = validatePercentage(taxRatePct, 'Tax rate', { required: false });
    if (taxRateError) {
      setError(taxRateError);
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);

      const payload: OfferingIn = {
        name,
        sku: sku.trim() ? sku : undefined,
        type,
        category,
        unit,
        pricing_model: pricingModel,
        base_price: parseStrictNumber(basePrice) ?? 0,
        tax_rate_pct: parseStrictNumber(taxRatePct) ?? 0,
        billing_frequency: billingFrequency,
        description,
        pricing_tiers: (pricingModel === 'volume' || pricingModel === 'tiered' || pricingModel === 'package') ? pricingTiers : undefined,
        bundle_components: type === 'bundle' ? bundleComponents : undefined,
      };

      await onSave(payload);
      onClose();
    } catch (err: any) {
      setError(err?.response?.data?.error?.message || err?.message || 'Failed to save offering.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const addTier = () => {
    const last = pricingTiers[pricingTiers.length - 1];
    const nextMin = last ? (last.max_qty || last.min_qty) + 1 : 0;
    setPricingTiers([...pricingTiers, { min_qty: nextMin, max_qty: null, unit_price: Number(basePrice) }]);
  };

  const removeTier = (idx: number) => {
    setPricingTiers(pricingTiers.filter((_, i) => i !== idx));
  };

  const addBundleComp = () => {
    const candidate = availableOfferings.find((o) => o.id !== initialData?.id);
    if (candidate) {
      setBundleComponents([
        ...bundleComponents,
        {
          component_offering_id: candidate.id,
          is_required: true,
          default_quantity: 1,
          discount_pct: 0,
        },
      ]);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl overflow-hidden my-8">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-brand-50 rounded-lg text-brand-600">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900">
                {initialData ? 'Edit Commercial Offering' : 'Create Commercial Offering'}
              </h3>
              <p className="text-xs text-slate-500">Configure catalog offering, pricing model, and billing properties</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mx-6 mt-4 p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Offering Name *</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Dedicated Cloud Server"
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">SKU (Auto-generated if empty)</label>
              <input
                type="text"
                value={sku}
                onChange={(e) => setSku(e.target.value)}
                placeholder="e.g. CLOUD-SRV-01"
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500 font-mono"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Offering Type</label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value as OfferingType)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
              >
                <option value="product">Product (Goods/Hardware)</option>
                <option value="service">Service (Consulting/Ops)</option>
                <option value="plan">Plan (Recurring SaaS)</option>
                <option value="bundle">Bundle (Curated Stack)</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Category</label>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="e.g. Infrastructure"
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Pricing Model</label>
              <select
                value={pricingModel}
                onChange={(e) => setPricingModel(e.target.value as OfferingPricingModel)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
              >
                <option value="per_unit">Per Unit (Unit × Qty)</option>
                <option value="flat">Flat Rate (Fixed fee)</option>
                <option value="volume">Volume (All units at bracket)</option>
                <option value="tiered">Graduated Tiered</option>
                <option value="package">Package / Block Pricing</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Catalog Base Price (₹) *</label>
              <input
                type="number"
                step="0.01"
                min="0"
                required
                value={basePrice}
                onChange={(e) => setBasePrice(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500 font-semibold"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Tax Rate (GST %)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="100"
                value={taxRatePct}
                onChange={(e) => setTaxRatePct(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Billing Frequency</label>
              <select
                value={billingFrequency}
                onChange={(e) => setBillingFrequency(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
              >
                <option value="one_time">One Time</option>
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
                <option value="yearly">Yearly</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Description / Commercial Specs</label>
            <textarea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Enterprise service level details, compute capacity, or included deliverables..."
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>

          {/* Volume / Tiered / Package Brackets Section */}
          {(pricingModel === 'volume' || pricingModel === 'tiered' || pricingModel === 'package') && (
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-200/80 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-800">
                  {pricingModel === 'volume' ? 'Volume Pricing Brackets' : pricingModel === 'package' ? 'Package / Block Options' : 'Graduated Tier Brackets'}
                </span>
                <button
                  type="button"
                  onClick={addTier}
                  className="text-xs font-semibold text-brand-600 hover:text-brand-700 flex items-center gap-1"
                >
                  <Plus className="w-3.5 h-3.5" /> Add Bracket
                </button>
              </div>
              <div className="space-y-2">
                {pricingTiers.map((t, idx) => (
                  <div key={idx} className="flex items-center gap-2 bg-white p-2 rounded-lg border border-slate-200">
                    <input
                      type="number"
                      placeholder="Min Qty"
                      value={t.min_qty}
                      onChange={(e) => {
                        const updated = [...pricingTiers];
                        updated[idx].min_qty = Number(e.target.value);
                        setPricingTiers(updated);
                      }}
                      className="w-24 px-2 py-1 text-xs border rounded"
                    />
                    <span className="text-xs text-slate-400">to</span>
                    <input
                      type="number"
                      placeholder="Max (blank=∞)"
                      value={t.max_qty ?? ''}
                      onChange={(e) => {
                        const updated = [...pricingTiers];
                        updated[idx].max_qty = e.target.value ? Number(e.target.value) : null;
                        setPricingTiers(updated);
                      }}
                      className="w-28 px-2 py-1 text-xs border rounded"
                    />
                    <span className="text-xs text-slate-400">Rate: ₹</span>
                    <input
                      type="number"
                      step="0.01"
                      placeholder="Rate"
                      value={t.unit_price}
                      onChange={(e) => {
                        const updated = [...pricingTiers];
                        updated[idx].unit_price = Number(e.target.value);
                        setPricingTiers(updated);
                      }}
                      className="w-28 px-2 py-1 text-xs border rounded font-semibold text-slate-800"
                    />
                    <button
                      type="button"
                      onClick={() => removeTier(idx)}
                      className="p-1 text-slate-400 hover:text-red-600 rounded ml-auto"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Bundle Composition Section */}
          {type === 'bundle' && (
            <div className="p-3 bg-blue-50/50 rounded-xl border border-blue-200/60 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-blue-900">Bundle Components</span>
                <button
                  type="button"
                  onClick={addBundleComp}
                  className="text-xs font-semibold text-brand-600 hover:text-brand-700 flex items-center gap-1"
                >
                  <Plus className="w-3.5 h-3.5" /> Add Component
                </button>
              </div>
              <div className="space-y-2">
                {bundleComponents.map((b, idx) => (
                  <div key={idx} className="flex items-center gap-2 bg-white p-2 rounded-lg border border-slate-200">
                    <select
                      value={b.component_offering_id}
                      onChange={(e) => {
                        const updated = [...bundleComponents];
                        updated[idx].component_offering_id = e.target.value;
                        setBundleComponents(updated);
                      }}
                      className="flex-1 px-2 py-1 text-xs border rounded"
                    >
                      {availableOfferings.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.name} ({o.sku}) - ₹{o.base_price}
                        </option>
                      ))}
                    </select>
                    <input
                      type="number"
                      placeholder="Qty"
                      value={b.default_quantity}
                      onChange={(e) => {
                        const updated = [...bundleComponents];
                        updated[idx].default_quantity = Number(e.target.value);
                        setBundleComponents(updated);
                      }}
                      className="w-16 px-2 py-1 text-xs border rounded"
                    />
                    <label className="flex items-center gap-1 text-[11px] text-slate-600">
                      <input
                        type="checkbox"
                        checked={b.is_required}
                        onChange={(e) => {
                          const updated = [...bundleComponents];
                          updated[idx].is_required = e.target.checked;
                          setBundleComponents(updated);
                        }}
                      />
                      Req
                    </label>
                    <button
                      type="button"
                      onClick={() => setBundleComponents(bundleComponents.filter((_, i) => i !== idx))}
                      className="p-1 text-slate-400 hover:text-red-600 rounded ml-auto"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Footer Actions */}
          <div className="pt-4 border-t border-slate-100 flex items-center justify-end gap-2.5">
            <Button variant="outline" size="sm" type="button" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : initialData ? 'Update Offering' : 'Create Offering'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
