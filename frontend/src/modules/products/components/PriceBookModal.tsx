import { toApiError } from '../../../services/apiClient';
import React, { useState } from 'react';
import { X, Plus, Trash2, BookOpen, AlertCircle } from 'lucide-react';
import { Button } from '../../../components/common/Button';
import type { PriceBookIn, PriceBookOut, OfferingOut } from '../../../types/catalog_cpq';
import { formatMoney, currencySymbol } from '../../../utils/format';

interface PriceBookModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: PriceBookIn) => Promise<void>;
  initialData?: PriceBookOut | null;
  offerings: OfferingOut[];
}

export const PriceBookModal: React.FC<PriceBookModalProps> = ({
  isOpen,
  onClose,
  onSave,
  initialData,
  offerings,
}) => {
  if (!isOpen) return null;

  const [name, setName] = useState(initialData?.name || '');
  const [description, setDescription] = useState(initialData?.description || '');
  const [customerSegment, setCustomerSegment] = useState(initialData?.customer_segment || 'Enterprise');
  const [currency, setCurrency] = useState(initialData?.currency || 'INR');
  const [isDefault, setIsDefault] = useState(initialData?.is_default || false);
  const [entries, setEntries] = useState<
    Array<{
      offering_id: string;
      custom_price: number | null;
      discount_pct: number | null;
    }>
  >(
    initialData?.entries?.map((e) => ({
      offering_id: e.offering_id,
      custom_price: e.custom_price ? Number(e.custom_price) : null,
      discount_pct: e.discount_pct ? Number(e.discount_pct) : null,
    })) || []
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addEntry = () => {
    const candidate = offerings.find((o) => !entries.some((e) => e.offering_id === o.id));
    if (candidate) {
      setEntries([
        ...entries,
        { offering_id: candidate.id, custom_price: null, discount_pct: 10 },
      ]);
    }
  };

  const removeEntry = (idx: number) => {
    setEntries(entries.filter((_, i) => i !== idx));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Price book name is required.');
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);

      const payload: PriceBookIn = {
        name,
        description,
        customer_segment: customerSegment,
        currency,
        is_default: isDefault,
        entries: entries.map((e) => ({
          offering_id: e.offering_id,
          custom_price: e.custom_price,
          discount_pct: e.discount_pct,
          is_active: true,
        })),
      };

      await onSave(payload);
      onClose();
    } catch (err) {
      setError(toApiError(err).message || 'Failed to save price book.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl overflow-hidden my-8">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-emerald-50 rounded-lg text-emerald-600">
              <BookOpen className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900">
                {initialData ? 'Edit Price Book' : 'Create Segment Price Book'}
              </h3>
              <p className="text-xs text-slate-500">Tier pricing layers for customer segments or strategic lists</p>
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
              <label className="block text-xs font-semibold text-slate-700 mb-1">Price Book Name *</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Enterprise Tier A"
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Customer Segment</label>
              <input
                type="text"
                value={customerSegment}
                onChange={(e) => setCustomerSegment(e.target.value)}
                placeholder="e.g. Enterprise, Government, Education"
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Currency</label>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
              >
                <option value="INR">INR (₹)</option>
                <option value="USD">USD ($)</option>
                <option value="EUR">EUR (€)</option>
              </select>
            </div>
            <div className="flex items-center pt-5">
              <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isDefault}
                  onChange={(e) => setIsDefault(e.target.checked)}
                  className="rounded text-brand-600 focus:ring-brand-500"
                />
                Set as Default Organization Price Book
              </label>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Description</label>
            <textarea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Applies special 10% volume discount for enterprise contracts..."
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>

          {/* Price Adjustments */}
          <div className="p-3 bg-slate-50 rounded-xl border border-slate-200/80 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-800">Offering Overrides & Discounts</span>
              <button
                type="button"
                onClick={addEntry}
                className="text-xs font-semibold text-brand-600 hover:text-brand-700 flex items-center gap-1"
              >
                <Plus className="w-3.5 h-3.5 shrink-0" /> Add Offering
              </button>
            </div>

            {entries.length === 0 ? (
              <p className="text-xs text-slate-400 italic">No specific offering overrides added yet.</p>
            ) : (
              <div className="space-y-2">
                {entries.map((entry, idx) => (
                  <div key={idx} className="flex items-center gap-2 bg-white p-2 rounded-lg border border-slate-200">
                    <select
                      value={entry.offering_id}
                      onChange={(e) => {
                        const updated = [...entries];
                        updated[idx].offering_id = e.target.value;
                        setEntries(updated);
                      }}
                      className="flex-1 px-2 py-1 text-xs border rounded"
                    >
                      {offerings.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.name} ({o.sku}) - Base: {formatMoney(o.base_price, o.currency || 'INR')}
                        </option>
                      ))}
                    </select>

                    <div className="flex items-center gap-1">
                      <span className="text-xs text-slate-400">Fixed {currencySymbol(currency)}</span>
                      <input
                        type="number"
                        step="0.01"
                        placeholder="Fixed"
                        value={entry.custom_price ?? ''}
                        onChange={(e) => {
                          const updated = [...entries];
                          updated[idx].custom_price = e.target.value ? Number(e.target.value) : null;
                          if (e.target.value) updated[idx].discount_pct = null;
                          setEntries(updated);
                        }}
                        className="w-20 px-2 py-1 text-xs border rounded"
                      />
                    </div>

                    <div className="flex items-center gap-1">
                      <span className="text-xs text-slate-400">or % off</span>
                      <input
                        type="number"
                        placeholder="Disc %"
                        value={entry.discount_pct ?? ''}
                        onChange={(e) => {
                          const updated = [...entries];
                          updated[idx].discount_pct = e.target.value ? Number(e.target.value) : null;
                          if (e.target.value) updated[idx].custom_price = null;
                          setEntries(updated);
                        }}
                        className="w-16 px-2 py-1 text-xs border rounded"
                      />
                    </div>

                    <button
                      type="button"
                      onClick={() => removeEntry(idx)}
                      className="p-1 text-slate-400 hover:text-red-600 rounded ml-auto"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="pt-4 border-t border-slate-100 flex items-center justify-end gap-2.5">
            <Button variant="outline" size="sm" type="button" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : initialData ? 'Update Price Book' : 'Create Price Book'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
