import React, { useEffect, useState } from 'react';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { fieldErrors } from '../../services/apiClient';
import { catalogService } from '../../services/catalogService';
import {
  validateSensibleName,
  validateSku,
  validateNonNegativeMoney,
  validateNonNegativeInteger,
  parseStrictNumber,
} from '../../utils/validation';
import type { BillingInterval, PlanOut, PricingModel, ProductOut } from '../../types/api';

interface NewPlanModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (plan: PlanOut) => void;
}

const BILLING_INTERVALS: { value: BillingInterval; label: string }[] = [
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'semiannual', label: 'Semiannual' },
  { value: 'yearly', label: 'Yearly' },
  { value: 'one_time', label: 'One-time' },
];

const PRICING_MODELS: { value: PricingModel; label: string }[] = [
  { value: 'flat', label: 'Flat (fixed amount)' },
  { value: 'per_unit', label: 'Per unit (× quantity)' },
];

const NEW_PRODUCT_VALUE = '__new__';

function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64);
}

export function NewPlanModal({ isOpen, onClose, onCreated }: NewPlanModalProps) {
  const { showToast } = useToast();
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(true);

  const [productId, setProductId] = useState<string>('');
  const [newProductName, setNewProductName] = useState('');

  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [codeTouched, setCodeTouched] = useState(false);
  const [billingInterval, setBillingInterval] = useState<BillingInterval>('monthly');
  const [pricingModel, setPricingModel] = useState<PricingModel>('flat');
  const [unitAmount, setUnitAmount] = useState('');
  const [trialDays, setTrialDays] = useState(0);

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setName('');
    setCode('');
    setCodeTouched(false);
    setBillingInterval('monthly');
    setPricingModel('flat');
    setUnitAmount('');
    setTrialDays(0);
    setNewProductName('');
    setErrors({});

    let cancelled = false;
    (async () => {
      try {
        setLoadingProducts(true);
        const res = await catalogService.listProducts({ page_size: 100, is_active: true });
        if (cancelled) return;
        setProducts(res.items || []);
        setProductId(res.items?.length ? res.items[0].id : NEW_PRODUCT_VALUE);
      } catch {
        if (!cancelled) setProductId(NEW_PRODUCT_VALUE);
      } finally {
        if (!cancelled) setLoadingProducts(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const handleNameChange = (value: string) => {
    setName(value);
    if (!codeTouched) setCode(slugify(value));
  };

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    if (productId === NEW_PRODUCT_VALUE) {
      const productNameError = validateSensibleName(newProductName, 'Product name');
      if (productNameError) next.product_id = productNameError;
    }
    const nameError = validateSensibleName(name, 'Plan name');
    if (nameError) next.name = nameError;
    const codeError = validateSku(code, { required: true });
    if (codeError) next.code = codeError;
    const amountError = validateNonNegativeMoney(unitAmount, 'Unit amount', { required: true });
    if (amountError) next.unit_amount = amountError;
    const trialDaysError = validateNonNegativeInteger(trialDays, 'Trial days');
    if (trialDaysError) next.trial_days = trialDaysError;
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    try {
      setSaving(true);
      let resolvedProductId = productId;
      if (productId === NEW_PRODUCT_VALUE) {
        const product = await catalogService.createProduct({ name: newProductName.trim() });
        resolvedProductId = product.id;
      }
      const plan = await catalogService.createPlan({
        product_id: resolvedProductId,
        name: name.trim(),
        code: code.trim(),
        billing_interval: billingInterval,
        pricing_model: pricingModel,
        unit_amount: unitAmount,
        trial_days: trialDays,
      });
      showToast('success', 'Plan created', `${plan.name} is ready to use in subscriptions.`);
      onCreated(plan);
      onClose();
    } catch (err: any) {
      const fe = fieldErrors(err);
      if (Object.keys(fe).length) setErrors(fe);
      showToast('error', err?.message || 'Failed to create plan');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="New Plan"
      description="Define a billable plan under a product. It becomes selectable in Create Subscription immediately."
      size="md"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {loadingProducts ? (
          <p className="text-xs text-slate-500">Loading products...</p>
        ) : (
          <Select
            label="Product"
            required
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            options={[
              ...products.map((p) => ({ value: p.id, label: p.name })),
              { value: NEW_PRODUCT_VALUE, label: '+ Create a new product' },
            ]}
          />
        )}
        {productId === NEW_PRODUCT_VALUE && (
          <Input
            label="New product name"
            required
            placeholder="e.g. Rooman Cloud Platform"
            value={newProductName}
            onChange={(e) => setNewProductName(e.target.value)}
            error={errors.product_id}
          />
        )}

        <Input
          label="Plan name"
          required
          placeholder="e.g. Pro Monthly"
          value={name}
          onChange={(e) => handleNameChange(e.target.value)}
          error={errors.name}
          autoFocus
        />
        <Input
          label="Code"
          required
          placeholder="e.g. pro_monthly"
          value={code}
          onChange={(e) => {
            setCodeTouched(true);
            setCode(e.target.value);
          }}
          error={errors.code}
          helperText="Unique per organisation."
          className="font-mono"
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select
            label="Billing interval"
            value={billingInterval}
            onChange={(e) => setBillingInterval(e.target.value as BillingInterval)}
            options={BILLING_INTERVALS}
          />
          <Select
            label="Pricing model"
            value={pricingModel}
            onChange={(e) => setPricingModel(e.target.value as PricingModel)}
            options={PRICING_MODELS}
          />
          <Input
            label="Unit amount"
            required
            type="number"
            min="0"
            step="0.01"
            placeholder="e.g. 999"
            value={unitAmount}
            onChange={(e) => setUnitAmount(e.target.value)}
            error={errors.unit_amount}
          />
          <Input
            label="Trial days"
            type="number"
            min="0"
            value={trialDays}
            onChange={(e) => {
              const parsed = parseStrictNumber(e.target.value);
              setTrialDays(parsed !== null ? Math.max(0, Math.trunc(parsed)) : 0);
            }}
            error={errors.trial_days}
          />
        </div>

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
          <Button variant="ghost" size="sm" type="button" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" isLoading={saving}>
            Create Plan
          </Button>
        </div>
      </form>
    </Modal>
  );
}
