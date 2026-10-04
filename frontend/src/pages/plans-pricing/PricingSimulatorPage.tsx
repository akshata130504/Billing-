import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  Calculator,
  ArrowLeft,
  Sparkles,
  FileText,
} from 'lucide-react';
import { Button } from '../../components/common/Button';
import { planPricingService } from '../../services/planPricingService';
import { customerService } from '../../services/customerService';
import { catalogCpqService } from '../../services/catalogCpqService';
import type { PlanPricingItem, PricingSimulationResponse } from '../../types/plans_pricing';
import type { CustomerOut } from '../../types/api';
import type { PriceBookOut } from '../../types/catalog_cpq';

import { LoadingState } from '../../components/common/LoadingState';
import { currencySymbol } from '../../utils/format';

/** Largest quantity the simulator prices (the API rejects anything above it with a 422). */
export const MAX_SIMULATOR_QUANTITY = 1_000_000;
export const QUANTITY_LIMIT_MESSAGE = `Quantity cannot exceed ${MAX_SIMULATOR_QUANTITY.toLocaleString('en-IN')}.`;

/** Clamp a typed quantity into 1..MAX_SIMULATOR_QUANTITY (whole units). */
export function clampSimulatorQuantity(raw: string | number): { value: number; error: string | null } {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return { value: 1, error: null };
  if (n > MAX_SIMULATOR_QUANTITY) return { value: MAX_SIMULATOR_QUANTITY, error: QUANTITY_LIMIT_MESSAGE };
  return { value: Math.floor(n), error: null };
}

export function PricingSimulatorPage() {
  const navigate = useNavigate();
  const [plans, setPlans] = useState<PlanPricingItem[]>([]);
  const [customers, setCustomers] = useState<CustomerOut[]>([]);
  const [priceBooks, setPriceBooks] = useState<PriceBookOut[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Simulation parameters
  const [selectedPlanId, setSelectedPlanId] = useState<string>('');
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('');
  const [selectedPriceBookId, setSelectedPriceBookId] = useState<string>('');
  const [quantity, setQuantity] = useState<number>(10);
  const [quantityError, setQuantityError] = useState<string | null>(null);
  const [discountPct, setDiscountPct] = useState<number>(0);

  const [isCalculating, setIsCalculating] = useState(false);
  const [result, setResult] = useState<PricingSimulationResponse | null>(null);
  // Currency of the plan the current result was calculated for (the response carries no currency).
  const [resultCurrency, setResultCurrency] = useState<string>('INR');
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      setLoadError(null);
      try {
        const [plansRes, custRes, pbRes] = await Promise.all([
          planPricingService.listPlans(),
          customerService.list({ page_size: 100 }),
          catalogCpqService.listPriceBooks(),
        ]);
        setPlans(plansRes.items);
        setCustomers(custRes.items);
        setPriceBooks(pbRes.items);
        if (plansRes.items.length > 0) {
          setSelectedPlanId(plansRes.items[0].id);
        }
      } catch (err: any) {
        console.error('Failed to load simulator data', err);
        setLoadError(err?.response?.data?.detail || err?.message || 'Failed to load plans, customers or price books.');
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, []);

  const handleCalculate = async () => {
    if (!selectedPlanId) return;
    setIsCalculating(true);
    setError(null);
    try {
      const res = await planPricingService.simulatePricing({
        offering_id: selectedPlanId,
        customer_id: selectedCustomerId || undefined,
        price_book_id: selectedPriceBookId || undefined,
        quantity: clampSimulatorQuantity(quantity).value,
        discount_pct: Number(discountPct) || 0,
      });
      setResultCurrency(plans.find((p) => p.id === selectedPlanId)?.currency || 'INR');
      setResult(res);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(
        err?.response?.data?.error?.message ||
          (typeof detail === 'string' ? detail : null) ||
          err?.message ||
          'Calculation failed'
      );
    } finally {
      setIsCalculating(false);
    }
  };

  useEffect(() => {
    if (selectedPlanId) {
      handleCalculate();
    }
  }, [selectedPlanId, selectedCustomerId, selectedPriceBookId, quantity, discountPct]);

  const handleReset = () => {
    if (plans.length > 0) setSelectedPlanId(plans[0].id);
    setSelectedCustomerId('');
    setSelectedPriceBookId('');
    setQuantity(10);
    setQuantityError(null);
    setDiscountPct(0);
    setError(null);
  };

  const handleUseInQuote = () => {
    const selectedPlan = plans.find((p) => p.id === selectedPlanId);
    navigate('/quotes/new', {
      state: {
        prefilledCustomer: selectedCustomerId,
        prefilledPriceBook: selectedPriceBookId,
        prefilledItem: selectedPlan
          ? {
              offering_id: selectedPlan.id,
              name: selectedPlan.name,
              sku: selectedPlan.code || selectedPlan.sku,
              quantity: quantity,
              unit_price: result ? Number(result.effective_unit_price) : Number(selectedPlan.base_price),
              tax_rate_pct: Number(selectedPlan.tax_rate_pct || 18),
              discount_pct: discountPct,
              pricing_explanation: result?.explanation ? JSON.stringify(result.explanation) : undefined,
            }
          : undefined,
      },
    });
  };

  const selectedPlanObj = plans.find((p) => p.id === selectedPlanId);
  const planSym = currencySymbol(selectedPlanObj?.currency || 'INR');
  const sym = currencySymbol(resultCurrency);

  if (isLoading) {
    return (
      <div className="py-24">
        <LoadingState message="Loading pricing simulator models and customers..." />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 animate-in fade-in duration-150">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link to="/plans-pricing">
            <Button variant="outline" size="sm" leadingIcon={<ArrowLeft className="w-3.5 h-3.5" />}>
              Back
            </Button>
          </Link>
          <div>
            <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
              Pricing Simulator & Calculator
              <Sparkles className="w-4 h-4 text-amber-500" />
            </h1>
            <p className="text-xs text-slate-500">
              Simulate tiered volume brackets, price book overrides, and transparent &quot;Why This Price?&quot; breakdowns.
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleReset}>
            Reset
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleUseInQuote}
            disabled={!result}
            leadingIcon={<FileText className="w-4 h-4" />}
          >
            Use in Quote
          </Button>
        </div>
      </div>

      {loadError && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600">
          {loadError}
        </div>
      )}

      {!loadError && plans.length === 0 && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800">
          No plans or offerings found yet. Create one on the{' '}
          <Link to="/plans-pricing" className="font-semibold underline">
            Plans & Pricing
          </Link>{' '}
          page, then come back here to simulate its price.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Form: Inputs */}
        <div className="lg:col-span-5 space-y-5 bg-white p-5 rounded-xl border border-slate-200/80 shadow-2xs">
          <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Simulation Parameters</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Select Plan / Offering <span className="text-red-500">*</span>
              </label>
              <select
                value={selectedPlanId}
                onChange={(e) => setSelectedPlanId(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 bg-white font-medium text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10"
              >
                {plans.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.pricing_model.toUpperCase()}) - {currencySymbol(p.currency || 'INR')}{Number(p.base_price).toLocaleString('en-IN')}/{p.unit}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Customer (Optional Segment Matching)
              </label>
              <select
                value={selectedCustomerId}
                onChange={(e) => setSelectedCustomerId(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 bg-white font-medium text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10"
              >
                <option value="">No Customer Selected (Standard Account)</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.display_name} ({c.customer_number})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Price Book (Segment Negotiated Rates)
              </label>
              <select
                value={selectedPriceBookId}
                onChange={(e) => setSelectedPriceBookId(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 bg-white font-medium text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10"
              >
                <option value="">Standard Catalog Rate (No Price Book)</option>
                {priceBooks.map((pb) => (
                  <option key={pb.id} value={pb.id}>
                    {pb.name} ({pb.customer_segment || 'General'})
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="simulator-quantity" className="block text-xs font-semibold text-slate-700 mb-1">
                  Quantity
                </label>
                <input
                  id="simulator-quantity"
                  type="number"
                  min="1"
                  max={MAX_SIMULATOR_QUANTITY}
                  step="1"
                  value={quantity}
                  aria-invalid={quantityError ? true : undefined}
                  onChange={(e) => {
                    const { value, error: limitError } = clampSimulatorQuantity(e.target.value);
                    setQuantity(value);
                    setQuantityError(limitError);
                  }}
                  className={`w-full px-3 py-2 text-xs font-bold rounded-lg border text-slate-900 ${
                    quantityError ? 'border-red-300' : 'border-slate-200'
                  }`}
                />
                {quantityError && (
                  <p role="alert" className="mt-1 text-[11px] text-red-600">
                    {quantityError}
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Deal Discount (%)</label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={discountPct}
                  onChange={(e) => setDiscountPct(Math.max(0, Math.min(100, Number(e.target.value))))}
                  className="w-full px-3 py-2 text-xs font-bold rounded-lg border border-slate-200 text-slate-900"
                />
              </div>
            </div>

            {selectedPlanObj?.pricing_tiers && selectedPlanObj.pricing_tiers.length > 0 && (
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200/80 space-y-1.5 text-xs">
                <p className="font-semibold text-slate-700">Configured Tiers / Packages:</p>
                <div className="space-y-1 text-[11px] text-slate-600">
                  {selectedPlanObj.pricing_tiers.map((t, i) => (
                    <div key={i} className="flex justify-between gap-2 font-mono tabular-nums">
                      {selectedPlanObj.pricing_model === 'package' ? (
                        <>
                          <span className="min-w-0 break-all">Block of {t.package_qty} units:</span>
                          <span className="min-w-0 break-all text-right font-semibold text-slate-900">{planSym}{Number(t.package_price).toLocaleString('en-IN')}</span>
                        </>
                      ) : (
                        <>
                          <span className="min-w-0 break-all">Tier [{t.min_qty} - {t.max_qty || '∞'}]:</span>
                          <span className="min-w-0 break-all text-right font-semibold text-slate-900">{planSym}{Number(t.unit_price).toLocaleString('en-IN')}/unit</span>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <Button
              variant="primary"
              size="sm"
              onClick={handleCalculate}
              isLoading={isCalculating}
              className="w-full"
              leadingIcon={<Calculator className="w-4 h-4" />}
            >
              Recalculate Price
            </Button>
          </div>
        </div>

        {/* Right Output: Breakdown & "Why This Price?" */}
        <div className="lg:col-span-7 space-y-5">
          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600">
              {error}
            </div>
          )}

          {result && (
            <div className="space-y-5">
              {/* Summary Card */}
              <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-2xs space-y-4">
                <div className="flex items-center justify-between gap-3 border-b border-slate-100 pb-3">
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold text-slate-900 break-words">{result.offering_name}</h3>
                    <p className="text-xs text-slate-500 font-mono break-all">{result.offering_sku}</p>
                  </div>
                  <span className="shrink-0 px-2.5 py-1 rounded-full text-xs font-semibold capitalize bg-purple-50 text-purple-700 border border-purple-200">
                    {result.pricing_model.replace('_', ' ')} Model
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div className="min-w-0">
                    <p className="text-slate-400 text-[11px]">Effective Rate</p>
                    <p className="text-base font-bold text-slate-900 break-all">{sym}{Number(result.effective_unit_price).toLocaleString('en-IN')}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-slate-400 text-[11px]">Subtotal</p>
                    <p className="text-base font-bold text-slate-900 break-all">{sym}{Number(result.subtotal).toLocaleString('en-IN')}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-slate-400 text-[11px]">Discount ({result.discount_pct}%)</p>
                    <p className="text-base font-bold text-amber-600 break-all">-{sym}{Number(result.discount_amount).toLocaleString('en-IN')}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-slate-400 text-[11px]">Final Total (incl. Tax)</p>
                    <p data-testid="simulator-final-total" className="text-lg font-bold text-emerald-600 break-all">{sym}{Number(result.total_amount).toLocaleString('en-IN')}</p>
                  </div>
                </div>
              </div>

              {/* "Why This Price?" Mathematical Breakdown Tree */}
              <div className="bg-slate-900 text-slate-100 p-5 rounded-xl shadow-md space-y-4">
                <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
                  <Sparkles className="w-4 h-4 text-amber-400" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-amber-400">
                    Why This Price? — Detailed Calculation Audit
                  </h3>
                </div>

                <div className="space-y-3 font-mono text-xs">
                  <div className="flex items-start justify-between gap-3 py-1 border-b border-slate-800/80">
                    <span className="text-slate-400">1. Catalog Base Rate</span>
                    <span className="min-w-0 break-all text-right text-slate-200">{sym}{result.explanation.catalog_base_price}</span>
                  </div>

                  {result.explanation.price_book_adjustment && (
                    <div className="flex items-start justify-between gap-3 py-1 border-b border-slate-800/80 text-indigo-300">
                      <span>2. Price Book Adjustment</span>
                      <span className="min-w-0 break-all text-right">{result.explanation.price_book_adjustment}</span>
                    </div>
                  )}

                  {result.explanation.tier_explanation && (
                    <div className="flex items-start justify-between gap-3 py-1 border-b border-slate-800/80 text-purple-300">
                      <span>3. Applied Tier / Bracket</span>
                      <span className="min-w-0 break-all text-right">{result.explanation.tier_explanation}</span>
                    </div>
                  )}

                  <div className="flex items-start justify-between gap-3 py-1 border-b border-slate-800/80">
                    <span className="text-slate-400">4. Pre-discount Subtotal ({result.quantity} units)</span>
                    <span className="min-w-0 break-all text-right text-slate-200">{sym}{result.explanation.subtotal_pre_discount}</span>
                  </div>

                  {Number(result.discount_amount) > 0 && (
                    <div className="flex items-start justify-between gap-3 py-1 border-b border-slate-800/80 text-amber-400">
                      <span>5. Applied Discount ({result.discount_pct}%)</span>
                      <span className="min-w-0 break-all text-right">-{sym}{result.discount_amount}</span>
                    </div>
                  )}

                  <div className="flex items-start justify-between gap-3 py-1 border-b border-slate-800/80">
                    <span className="text-slate-400">6. Applicable GST ({result.tax_rate_pct}%)</span>
                    <span className="min-w-0 break-all text-right text-slate-200">+{sym}{result.tax_amount}</span>
                  </div>

                  <div className="flex items-start justify-between gap-3 pt-2 text-sm font-bold text-emerald-400">
                    <span>FINAL TOTAL AMOUNT</span>
                    <span className="min-w-0 break-all text-right">{sym}{result.total_amount}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default PricingSimulatorPage;
