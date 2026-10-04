import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Repeat,
  ArrowLeft,
  User,
  Package,
  Calendar,
  DollarSign,
  CheckCircle2,
  AlertCircle,
  Plus,
} from 'lucide-react';
import { subscriptionService } from '../../services/subscriptionService';
import { customerService } from '../../services/customerService';
import { planPricingService } from '../../services/planPricingService';
import type {
  CustomerOut,
  PlanOut,
  SubscribablePlanOption,
  SubscriptionIn,
  SubscriptionStatus,
} from '../../types/api';
import { Button } from '../../components/common/Button';
import { LoadingState } from '../../components/common/LoadingState';
import { useToast } from '../../components/common/Toast';
import { formatMoney, todayIso } from '../../utils/format';
import { validatePositiveInteger } from '../../utils/validation';
import { NewPlanModal } from './NewPlanModal';

/** Stable select key: legacy plans and catalog offerings live in different tables. */
const optionKey = (o: Pick<SubscribablePlanOption, 'source' | 'id'>) => `${o.source}:${o.id}`;

function planToOption(plan: PlanOut): SubscribablePlanOption {
  return {
    id: plan.id,
    source: 'plan',
    plan_id: plan.id,
    offering_id: null,
    name: plan.name,
    code: plan.code,
    product_name: '',
    billing_interval: plan.billing_interval,
    interval_count: plan.interval_count || 1,
    pricing_model: plan.pricing_model,
    unit_amount: plan.unit_amount,
    currency: plan.currency,
    tax_rate_pct: '18.00',
    trial_days: plan.trial_days || 0,
    pricing_tiers: [],
    is_active: true,
  };
}

export function SubscriptionFormPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [searchParams] = useSearchParams();

  const [customers, setCustomers] = useState<CustomerOut[]>([]);
  const [plans, setPlans] = useState<SubscribablePlanOption[]>([]);
  // Engine-priced preview for volume / tiered / package offerings (per period, pre-tax).
  const [enginePreview, setEnginePreview] = useState<{ unitRate: number; subtotal: number } | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form Fields
  const [customerId, setCustomerId] = useState('');
  const [planId, setPlanId] = useState('');
  const [quantity, setQuantity] = useState(1);
  const [status, setStatus] = useState<SubscriptionStatus>('active');
  const [startDate, setStartDate] = useState(todayIso());
  const [trialDays, setTrialDays] = useState<number>(0);
  const [hasTrialOverride, setHasTrialOverride] = useState(false);
  const [autoRenewal, setAutoRenewal] = useState(true);
  const [generateFirstInvoice, setGenerateFirstInvoice] = useState(true);
  const [notes, setNotes] = useState('');
  const [newPlanOpen, setNewPlanOpen] = useState(false);

  useEffect(() => {
    async function loadData() {
      try {
        setLoadingData(true);
        const [custRes, options] = await Promise.all([
          customerService.list({ page_size: 100 }),
          subscriptionService.planOptions(),
        ]);
        setCustomers(custRes.items || []);
        setPlans(options);
        if (custRes.items?.length > 0) {
          setCustomerId(custRes.items[0].id);
        }
        // Deep links from Plans & Pricing (?offering_id=) or the legacy plan list (?plan_id=).
        const wantedOffering = searchParams.get('offering_id');
        const wantedPlan = searchParams.get('plan_id');
        const initial =
          options.find((o) => wantedOffering && o.source === 'offering' && o.id === wantedOffering) ||
          options.find((o) => wantedPlan && o.source === 'plan' && o.id === wantedPlan) ||
          options[0];
        if (initial) {
          setPlanId(optionKey(initial));
          const initialTrial = initial.trial_days || 0;
          setTrialDays(initialTrial);
          if (initialTrial > 0) {
            setGenerateFirstInvoice(false);
          }
        }
      } catch {
        setError('Failed to load customers and plans. Please refresh.');
      } finally {
        setLoadingData(false);
      }
    }
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Selected customer & plan objects
  const selectedCustomer = useMemo(
    () => customers.find((c) => c.id === customerId),
    [customers, customerId]
  );

  const selectedPlan = useMemo(
    () => plans.find((p) => optionKey(p) === planId),
    [plans, planId]
  );

  const needsEngine =
    selectedPlan?.source === 'offering' && !['flat', 'per_unit'].includes(selectedPlan.pricing_model);

  useEffect(() => {
    if (!selectedPlan || !needsEngine) {
      setEnginePreview(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      planPricingService
        .calculatePrice({ offering_id: selectedPlan.id, quantity: Math.max(1, quantity || 1) })
        .then((r) => {
          if (!cancelled) setEnginePreview({ unitRate: r.unit_rate, subtotal: r.subtotal });
        })
        .catch(() => {
          if (!cancelled) setEnginePreview(null);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [selectedPlan, needsEngine, quantity]);

  const handlePlanChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const pId = e.target.value;
    setPlanId(pId);
    const p = plans.find((plan) => optionKey(plan) === pId);
    if (p && !hasTrialOverride) {
      const pTrial = p.trial_days || 0;
      setTrialDays(pTrial);
      if (pTrial > 0) {
        setGenerateFirstInvoice(false);
      } else {
        setGenerateFirstInvoice(true);
      }
    }
  };

  const handlePlanCreated = (plan: PlanOut) => {
    const option = planToOption(plan);
    setPlans((prev) => [...prev, option]);
    setPlanId(optionKey(option));
    setHasTrialOverride(false);
    const pTrial = plan.trial_days || 0;
    setTrialDays(pTrial);
    setGenerateFirstInvoice(pTrial === 0);
  };

  // Real-time Commercial Calculations
  const calculations = useMemo(() => {
    if (!selectedPlan) {
      return {
        unitPrice: 0,
        subtotal: 0,
        taxRate: 0,
        taxAmount: 0,
        totalAmount: 0,
        mrr: 0,
      };
    }

    const qty = Math.max(1, quantity || 1);
    let unitPrice = parseFloat(selectedPlan.unit_amount || '0') || 0;
    let subtotal = selectedPlan.pricing_model === 'flat' ? unitPrice : unitPrice * qty;
    if (needsEngine && enginePreview) {
      unitPrice = enginePreview.unitRate;
      subtotal = enginePreview.subtotal;
    }

    const isTaxExempt = selectedCustomer?.tax_exempt || false;
    const taxRate = isTaxExempt ? 0 : parseFloat(selectedPlan.tax_rate_pct || '0') || 0;
    const taxAmount = (subtotal * taxRate) / 100;
    const totalAmount = subtotal + taxAmount;

    // Normalize MRR
    let mrr = subtotal;
    if (selectedPlan.billing_interval === 'yearly') {
      mrr = subtotal / (12 * (selectedPlan.interval_count || 1));
    } else if (selectedPlan.billing_interval === 'quarterly') {
      mrr = subtotal / (3 * (selectedPlan.interval_count || 1));
    } else if (selectedPlan.billing_interval === 'semiannual') {
      mrr = subtotal / (6 * (selectedPlan.interval_count || 1));
    }

    return {
      unitPrice,
      subtotal,
      taxRate,
      taxAmount,
      totalAmount,
      mrr,
    };
  }, [selectedPlan, selectedCustomer, quantity, needsEngine, enginePreview]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerId) {
      showToast('error', 'Validation Error', 'Please select a customer.');
      return;
    }
    if (!selectedPlan) {
      showToast('error', 'Validation Error', 'Please select a plan.');
      return;
    }
    const quantityError = validatePositiveInteger(quantity, 'Quantity', { required: true });
    if (quantityError) {
      setError(quantityError);
      showToast('error', 'Validation Error', quantityError);
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      const payload: SubscriptionIn = {
        customer_id: customerId,
        ...(selectedPlan.source === 'offering'
          ? { offering_id: selectedPlan.id }
          : { plan_id: selectedPlan.id }),
        quantity: Math.max(1, quantity || 1),
        status: status,
        start_date: startDate || todayIso(),
        trial_days: trialDays > 0 ? trialDays : 0,
        auto_renewal: autoRenewal,
        generate_first_invoice: trialDays > 0 ? false : generateFirstInvoice,
        notes: notes.trim() || undefined,
      };

      const result = await subscriptionService.create(payload);
      showToast(
        'success',
        'Subscription Created',
        `Subscription ${result.subscription_number} created successfully.`
      );
      navigate(`/subscriptions/${result.id}`);
    } catch (err: any) {
      const msg = err.response?.data?.error?.message || err.message || 'Failed to create subscription.';
      setError(msg);
      showToast('error', 'Creation Failed', msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (loadingData) {
    return (
      <div className="py-24">
        <LoadingState message="Loading customer and catalog options..." />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-16">
      {/* Top Header */}
      <div className="border-b border-slate-200 pb-4">
        <button
          onClick={() => navigate('/subscriptions')}
          className="inline-flex items-center text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors mb-2"
        >
          <ArrowLeft className="w-3.5 h-3.5 mr-1" />
          Back to Subscriptions
        </button>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
          <Repeat className="w-6 h-6 text-brand-600" />
          Create New Subscription
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Set up a recurring subscription contract for an existing customer with agreed plan pricing.
        </p>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-700 flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
          <span className="font-medium">{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Customer & Plan Selection */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* 1. Customer Card */}
          <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 space-y-4">
            <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
              <User className="w-4 h-4 text-brand-600" />
              1. Select Customer
            </h2>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1.5">
                Customer Account <span className="text-rose-500">*</span>
              </label>
              <select
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value)}
                required
                className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
              >
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.display_name} {c.company_name ? `(${c.company_name})` : ''} - {c.email || c.customer_number}
                  </option>
                ))}
              </select>
            </div>

            {selectedCustomer && (
              <div className="p-3 bg-slate-50/80 rounded-lg border border-slate-100 text-xs space-y-1">
                <div className="flex justify-between text-slate-600">
                  <span>Currency:</span>
                  <span className="font-semibold text-slate-800">{selectedCustomer.currency || 'INR'}</span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Tax Status:</span>
                  <span className="font-semibold text-slate-800">
                    {selectedCustomer.tax_exempt ? 'Tax Exempt' : 'Taxable (18% GST)'}
                  </span>
                </div>
                {selectedCustomer.email && (
                  <div className="flex justify-between text-slate-600 truncate">
                    <span>Email:</span>
                    <span className="text-slate-800">{selectedCustomer.email}</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 2. Plan Selection */}
          <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <Package className="w-4 h-4 text-brand-600" />
                2. Select Plan
              </h2>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setNewPlanOpen(true)}
                leadingIcon={<Plus className="w-3.5 h-3.5" />}
              >
                New Plan
              </Button>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1.5">
                Subscription Plan <span className="text-rose-500">*</span>
              </label>
              {plans.length === 0 ? (
                <p className="text-xs text-slate-500 italic">
                  No plans yet — click "New Plan" above to create one.
                </p>
              ) : (
                <select
                  value={planId}
                  onChange={handlePlanChange}
                  required
                  className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
                >
                  {(['offering', 'plan'] as const).map((source) => {
                    const group = plans.filter((p) => p.source === source);
                    if (group.length === 0) return null;
                    return (
                      <optgroup
                        key={source}
                        label={source === 'offering' ? 'Plans & Pricing plans' : 'Legacy plans'}
                      >
                        {group.map((p) => (
                          <option key={optionKey(p)} value={optionKey(p)}>
                            {source === 'offering' ? '[Plans & Pricing] ' : '[Legacy] '}
                            {p.name} ({p.code}) - {formatMoney(p.unit_amount, p.currency)} / {p.billing_interval}
                            {source === 'offering' && !['flat', 'per_unit'].includes(p.pricing_model)
                              ? ` (${p.pricing_model} pricing)`
                              : ''}
                          </option>
                        ))}
                      </optgroup>
                    );
                  })}
                </select>
              )}
            </div>

            {selectedPlan && (
              <div className="p-3 bg-slate-50/80 rounded-lg border border-slate-100 text-xs space-y-1">
                <div className="flex justify-between text-slate-600">
                  <span>Source:</span>
                  <span className="font-semibold text-slate-800">
                    {selectedPlan.source === 'offering' ? 'Plans & Pricing (catalog)' : 'Legacy plan'}
                  </span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Interval:</span>
                  <span className="font-semibold text-slate-800 capitalize">
                    {selectedPlan.billing_interval} (x{selectedPlan.interval_count})
                  </span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Pricing Model:</span>
                  <span className="font-semibold text-slate-800 capitalize">
                    {selectedPlan.pricing_model?.replace('_', ' ')}
                  </span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Default Trial:</span>
                  <span className="font-semibold text-slate-800">
                    {selectedPlan.trial_days ? `${selectedPlan.trial_days} days` : 'None'}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 3. Subscription Terms & Schedule */}
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 space-y-4">
          <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
            <Calendar className="w-4 h-4 text-brand-600" />
            3. Subscription Terms & Schedule
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Quantity / Seats <span className="text-rose-500">*</span>
              </label>
              <input
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                required
                className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Initial Status
              </label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as SubscriptionStatus)}
                className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
              >
                <option value="active">Active (Immediate)</option>
                <option value="draft">Draft (Review first)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Start Date
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                required
                className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Trial Period (Days)
              </label>
              <input
                type="number"
                min={0}
                value={trialDays}
                onChange={(e) => {
                  setHasTrialOverride(true);
                  const days = Math.max(0, parseInt(e.target.value) || 0);
                  setTrialDays(days);
                  if (days > 0) {
                    setGenerateFirstInvoice(false);
                  }
                }}
                className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
              />
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                0 = no trial (immediate billing cycle)
              </span>
            </div>

            <div className="flex flex-col justify-center space-y-2.5 pt-2">
              <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoRenewal}
                  onChange={(e) => setAutoRenewal(e.target.checked)}
                  className="w-4 h-4 rounded text-brand-600 border-slate-300 focus:ring-brand-500"
                />
                <span>Enable Automatic Renewal</span>
              </label>

              <label className={`flex items-center gap-2 text-xs font-medium cursor-pointer ${trialDays > 0 ? 'text-slate-400' : 'text-slate-700'}`}>
                <input
                  type="checkbox"
                  checked={generateFirstInvoice && trialDays === 0}
                  disabled={trialDays > 0}
                  onChange={(e) => setGenerateFirstInvoice(e.target.checked)}
                  className="w-4 h-4 rounded text-brand-600 border-slate-300 focus:ring-brand-500"
                />
                <span>Generate First Period Invoice Immediately</span>
              </label>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Internal / Contract Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Approved under Enterprise Q3 discount terms..."
              rows={2}
              className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
            />
          </div>
        </div>

        {/* 4. Live Pricing Snapshot Calculator */}
        <div className="bg-brand-50/50 rounded-xl border border-brand-100 p-5 space-y-4">
          <h2 className="text-xs font-bold text-brand-900 uppercase tracking-wider flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-brand-600" />
            4. Live Commercial Pricing Snapshot
          </h2>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-white rounded-lg border border-brand-100 shadow-xs">
            <div>
              <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                Unit Price
              </span>
              <span className="text-base font-bold text-slate-900 mt-0.5 block tabular-nums">
                {formatMoney(calculations.unitPrice, selectedPlan?.currency || 'INR')}
              </span>
            </div>
            <div>
              <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                Seats / Units
              </span>
              <span className="text-base font-bold text-slate-900 mt-0.5 block tabular-nums">
                {quantity}
              </span>
            </div>
            <div>
              <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                Subtotal
              </span>
              <span className="text-base font-bold text-slate-900 mt-0.5 block tabular-nums">
                {formatMoney(calculations.subtotal, selectedPlan?.currency || 'INR')}
              </span>
            </div>
            <div>
              <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                Total per Cycle
              </span>
              <span className="text-base font-bold text-brand-700 mt-0.5 block tabular-nums">
                {formatMoney(calculations.totalAmount, selectedPlan?.currency || 'INR')}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between text-xs text-brand-800 gap-2 px-1">
            <span>
              Monthly Recurring Revenue (MRR):{' '}
              <strong className="font-semibold text-brand-950">
                {formatMoney(calculations.mrr, selectedPlan?.currency || 'INR')}
              </strong>
            </span>
            <span>
              Tax Applied:{' '}
              <strong className="font-semibold text-brand-950">
                {formatMoney(calculations.taxAmount, selectedPlan?.currency || 'INR')} ({calculations.taxRate}%)
              </strong>
            </span>
          </div>
        </div>

        {/* Submit Actions */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-200">
          <Button
            type="button"
            variant="outline"
            size="md"
            onClick={() => navigate('/subscriptions')}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            size="md"
            isLoading={submitting}
            className="flex items-center gap-2"
          >
            <CheckCircle2 className="w-4 h-4" />
            Create Subscription Contract
          </Button>
        </div>
      </form>

      <NewPlanModal
        isOpen={newPlanOpen}
        onClose={() => setNewPlanOpen(false)}
        onCreated={handlePlanCreated}
      />
    </div>
  );
}

export default SubscriptionFormPage;
