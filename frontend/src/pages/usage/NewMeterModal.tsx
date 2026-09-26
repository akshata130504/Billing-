import React, { useEffect, useState } from 'react';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { fieldErrors } from '../../services/apiClient';
import { meterService } from '../../services/meterService';
import { AGGREGATION_TYPES, type AggregationType, type UsageMeterOut } from '../../types/meters';
import { AGGREGATION_LABELS } from './usageUtils';

interface NewMeterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (meter: UsageMeterOut) => void;
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64);
}

export function NewMeterModal({ isOpen, onClose, onCreated }: NewMeterModalProps) {
  const { showToast } = useToast();
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [codeTouched, setCodeTouched] = useState(false);
  const [unitName, setUnitName] = useState('unit');
  const [aggregation, setAggregation] = useState<AggregationType>('sum');
  const [description, setDescription] = useState('');
  const [unitPrice, setUnitPrice] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setName('');
    setCode('');
    setCodeTouched(false);
    setUnitName('unit');
    setAggregation('sum');
    setDescription('');
    setUnitPrice('');
    setErrors({});
  }, [isOpen]);

  const handleNameChange = (value: string) => {
    setName(value);
    if (!codeTouched) setCode(slugify(value));
  };

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    const trimmedCode = code.trim();
    if (!name.trim()) next.name = 'Name is required.';
    else if (name.trim().length > 120) next.name = 'Name must be 120 characters or fewer.';
    if (!trimmedCode) next.code = 'Code is required.';
    else if (trimmedCode.length > 64) next.code = 'Code must be 64 characters or fewer.';
    else if (!/^[a-z0-9][a-z0-9_.-]*$/i.test(trimmedCode)) {
      next.code = 'Use letters, digits, underscores, dots or hyphens only.';
    }
    if (!unitName.trim()) next.unit_name = 'Unit is required.';
    else if (unitName.trim().length > 40) next.unit_name = 'Unit must be 40 characters or fewer.';
    if (description.trim().length > 300) next.description = 'Description must be 300 characters or fewer.';
    if (unitPrice.trim() && !/^\d{1,14}(\.\d{1,4})?$/.test(unitPrice.trim())) {
      next.unit_price = 'Enter a non-negative amount with up to 4 decimals.';
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    try {
      setSaving(true);
      const meter = await meterService.create({
        code: code.trim().toLowerCase(),
        name: name.trim(),
        unit_name: unitName.trim(),
        aggregation_type: aggregation,
        description: description.trim() || null,
        unit_price: unitPrice.trim() || null,
      });
      showToast('success', 'Meter created', `${meter.name} (${meter.code}) is ready to receive usage.`);
      onCreated(meter);
      onClose();
    } catch (err: any) {
      const fe = fieldErrors(err);
      if (Object.keys(fe).length) setErrors(fe);
      showToast('error', err?.message || 'Failed to create meter');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="New Meter"
      description="Define a measurable quantity you bill on. Usage events reference the meter by its code."
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <Input
          label="Name"
          required
          placeholder="e.g. API Requests"
          value={name}
          maxLength={120}
          onChange={(e) => handleNameChange(e.target.value)}
          error={errors.name}
          autoFocus
        />
        <Input
          label="Code"
          required
          placeholder="e.g. api_requests"
          value={code}
          maxLength={64}
          onChange={(e) => {
            setCodeTouched(true);
            setCode(e.target.value);
          }}
          error={errors.code}
          helperText="Unique per organisation. Stored lower-case; this is the value integrations send as meter_code."
          className="font-mono"
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="Unit"
            required
            placeholder="e.g. request, GB, seat"
            value={unitName}
            maxLength={40}
            onChange={(e) => setUnitName(e.target.value)}
            error={errors.unit_name}
          />
          <Select
            label="Aggregation"
            required
            value={aggregation}
            onChange={(e) => setAggregation(e.target.value as AggregationType)}
            options={AGGREGATION_TYPES.map((t) => ({ value: t, label: AGGREGATION_LABELS[t].label }))}
            helperText={AGGREGATION_LABELS[aggregation].hint}
          />
        </div>
        <Input
          label="Price per unit"
          placeholder="e.g. 0.50"
          inputMode="decimal"
          value={unitPrice}
          onChange={(e) => setUnitPrice(e.target.value)}
          error={errors.unit_price}
          helperText="Usage on this meter is billed at this flat rate. Leave empty for an unpriced (tracked-only) meter: its usage rates at 0."
        />
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1.5">Description</label>
          <textarea
            rows={2}
            maxLength={300}
            placeholder="What this meter measures and how it maps to pricing."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:outline-none"
          />
          {errors.description && <p className="mt-1.5 text-xs text-rose-600">{errors.description}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
          <Button variant="ghost" size="sm" type="button" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" isLoading={saving}>
            Create Meter
          </Button>
        </div>
      </form>
    </Modal>
  );
}
