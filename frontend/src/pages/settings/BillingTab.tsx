import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Save } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { organizationService } from '../../services/organizationService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { useAuth } from '../../hooks/useAuth';
import type { OrganizationOut, OrganizationUpdate } from '../../types/api';
import { ReadOnlyNotice, SettingsSection, nullable, str, type FieldErrors } from './settingsShared';

type SequenceKey = 'invoice' | 'quote' | 'payment' | 'subscription' | 'customer';

const SEQUENCES: { key: SequenceKey; label: string }[] = [
  { key: 'invoice', label: 'Invoices' },
  { key: 'quote', label: 'Quotes' },
  { key: 'payment', label: 'Payments' },
  { key: 'subscription', label: 'Subscriptions' },
  { key: 'customer', label: 'Customers' },
];

interface FormValues {
  default_payment_terms_days: string;
  default_tax_rate_pct: string;
  discount_approval_threshold_pct: string;
  invoice_notes: string;
  invoice_terms: string;
  prefixes: Record<SequenceKey, string>;
  nextNumbers: Record<SequenceKey, string>;
}

function toForm(org: OrganizationOut): FormValues {
  return {
    default_payment_terms_days: String(org.default_payment_terms_days),
    default_tax_rate_pct: org.default_tax_rate_pct,
    discount_approval_threshold_pct: org.discount_approval_threshold_pct,
    invoice_notes: str(org.invoice_notes),
    invoice_terms: str(org.invoice_terms),
    prefixes: {
      invoice: org.invoice_prefix,
      quote: org.quote_prefix,
      payment: org.payment_prefix,
      subscription: org.subscription_prefix,
      customer: org.customer_prefix,
    },
    nextNumbers: {
      invoice: String(org.invoice_next_number),
      quote: String(org.quote_next_number),
      payment: String(org.payment_next_number),
      subscription: String(org.subscription_next_number),
      customer: String(org.customer_next_number),
    },
  };
}

function toPayload(values: FormValues, org: OrganizationOut): OrganizationUpdate {
  const payload: OrganizationUpdate = {
    default_payment_terms_days: Number(values.default_payment_terms_days),
    default_tax_rate_pct: Number(values.default_tax_rate_pct).toFixed(2),
    discount_approval_threshold_pct: Number(values.discount_approval_threshold_pct).toFixed(2),
    invoice_notes: nullable(values.invoice_notes),
    invoice_terms: nullable(values.invoice_terms),
    invoice_prefix: values.prefixes.invoice.trim(),
    quote_prefix: values.prefixes.quote.trim(),
    payment_prefix: values.prefixes.payment.trim(),
    subscription_prefix: values.prefixes.subscription.trim(),
    customer_prefix: values.prefixes.customer.trim(),
  };
  // `*_next_number` may only be increased — only send changed values.
  const next = (key: SequenceKey, current: number): number | undefined => {
    const n = Number(values.nextNumbers[key]);
    return Number.isFinite(n) && n !== current ? n : undefined;
  };
  const inv = next('invoice', org.invoice_next_number);
  const quo = next('quote', org.quote_next_number);
  const pay = next('payment', org.payment_next_number);
  const sub = next('subscription', org.subscription_next_number);
  const cus = next('customer', org.customer_next_number);
  if (inv !== undefined) payload.invoice_next_number = inv;
  if (quo !== undefined) payload.quote_next_number = quo;
  if (pay !== undefined) payload.payment_next_number = pay;
  if (sub !== undefined) payload.subscription_next_number = sub;
  if (cus !== undefined) payload.customer_next_number = cus;
  return payload;
}

function currentNext(org: OrganizationOut, key: SequenceKey): number {
  switch (key) {
    case 'invoice':
      return org.invoice_next_number;
    case 'quote':
      return org.quote_next_number;
    case 'payment':
      return org.payment_next_number;
    case 'subscription':
      return org.subscription_next_number;
    case 'customer':
      return org.customer_next_number;
  }
}

export function BillingTab({ organization, canEdit }: { organization: OrganizationOut; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { refreshMe } = useAuth();
  const [values, setValues] = useState<FormValues>(() => toForm(organization));
  const [errors, setErrors] = useState<FieldErrors>({});

  useEffect(() => {
    setValues(toForm(organization));
  }, [organization]);

  const mutation = useMutation({
    mutationFn: (body: OrganizationUpdate) => organizationService.update(body),
    onSuccess: async (updated) => {
      queryClient.setQueryData(queryKeys.organization.detail(), updated);
      await refreshMe();
      setErrors({});
      showToast('success', 'Billing settings saved', 'Defaults and numbering were updated.');
    },
    onError: (err) => {
      const fields = fieldErrors(err);
      setErrors(fields);
      if (Object.keys(fields).length === 0) {
        showToast('error', 'Could not save', toApiError(err).message);
      }
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!canEdit) return;

    const clientErrors: FieldErrors = {};
    for (const seq of SEQUENCES) {
      const n = Number(values.nextNumbers[seq.key]);
      const current = currentNext(organization, seq.key);
      if (!Number.isInteger(n) || n < current) {
        clientErrors[`${seq.key}_next_number`] = `Must be ${current} or higher (numbers cannot be reused).`;
      }
      if (!values.prefixes[seq.key].trim()) {
        clientErrors[`${seq.key}_prefix`] = 'Prefix is required.';
      }
    }
    const terms = Number(values.default_payment_terms_days);
    if (!Number.isInteger(terms) || terms < 0) clientErrors.default_payment_terms_days = 'Enter a whole number of days.';
    const tax = Number(values.default_tax_rate_pct);
    if (!Number.isFinite(tax) || tax < 0 || tax > 100) clientErrors.default_tax_rate_pct = 'Enter a percentage between 0 and 100.';
    const threshold = Number(values.discount_approval_threshold_pct);
    if (!Number.isFinite(threshold) || threshold < 0 || threshold > 100) clientErrors.discount_approval_threshold_pct = 'Enter a percentage between 0 and 100.';

    if (Object.keys(clientErrors).length > 0) {
      setErrors(clientErrors);
      return;
    }
    mutation.mutate(toPayload(values, organization));
  };

  const disabled = !canEdit || mutation.isPending;
  const setField = (key: 'default_payment_terms_days' | 'default_tax_rate_pct' | 'discount_approval_threshold_pct' | 'invoice_notes' | 'invoice_terms') =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setValues((prev) => ({ ...prev, [key]: e.target.value }));

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      {!canEdit && <ReadOnlyNotice what="billing defaults" />}

      <SettingsSection
        title="Defaults"
        description="Applied to new customers, invoices and quotes. Existing records are not changed."
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Input
            label="Payment terms (days)"
            type="number"
            min={0}
            step={1}
            value={values.default_payment_terms_days}
            onChange={setField('default_payment_terms_days')}
            error={errors.default_payment_terms_days}
            disabled={disabled}
            helperText="Due date = issue date + terms."
          />
          <Input
            label="Default tax rate (%)"
            type="number"
            min={0}
            max={100}
            step="0.01"
            value={values.default_tax_rate_pct}
            onChange={setField('default_tax_rate_pct')}
            error={errors.default_tax_rate_pct}
            disabled={disabled}
            helperText="Pre-filled on new products and line items."
          />
          <Input
            label="Discount approval threshold (%)"
            type="number"
            min={0}
            max={100}
            step="0.01"
            value={values.discount_approval_threshold_pct}
            onChange={setField('discount_approval_threshold_pct')}
            error={errors.discount_approval_threshold_pct}
            disabled={disabled}
            helperText="Quotes discounted above this need admin approval before sending."
          />
        </div>
      </SettingsSection>

      <SettingsSection
        title="Document numbering"
        description="Numbers are assigned in sequence from the prefix and next number. The next number can only be increased."
      >
        <div className="overflow-x-auto -mx-5 px-5">
          <table className="w-full text-sm min-w-[520px]">
            <thead>
              <tr className="text-xs font-semibold text-slate-500 uppercase tracking-wider text-left">
                <th className="pb-2 pr-4">Sequence</th>
                <th className="pb-2 pr-4">Prefix</th>
                <th className="pb-2 pr-4">Next number</th>
                <th className="pb-2">Preview</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {SEQUENCES.map((seq) => {
                const prefix = values.prefixes[seq.key];
                const nextNumber = values.nextNumbers[seq.key];
                const preview = `${prefix}${String(Number(nextNumber) || 0).padStart(4, '0')}`;
                return (
                  <tr key={seq.key}>
                    <td className="py-2.5 pr-4 font-medium text-slate-700 whitespace-nowrap">{seq.label}</td>
                    <td className="py-2.5 pr-4 w-44">
                      <Input
                        aria-label={`${seq.label} prefix`}
                        value={prefix}
                        onChange={(e) =>
                          setValues((prev) => ({
                            ...prev,
                            prefixes: { ...prev.prefixes, [seq.key]: e.target.value },
                          }))
                        }
                        error={errors[`${seq.key}_prefix`]}
                        disabled={disabled}
                        className="font-mono"
                      />
                    </td>
                    <td className="py-2.5 pr-4 w-40">
                      <Input
                        aria-label={`${seq.label} next number`}
                        type="number"
                        min={currentNext(organization, seq.key)}
                        step={1}
                        value={nextNumber}
                        onChange={(e) =>
                          setValues((prev) => ({
                            ...prev,
                            nextNumbers: { ...prev.nextNumbers, [seq.key]: e.target.value },
                          }))
                        }
                        error={errors[`${seq.key}_next_number`]}
                        disabled={disabled}
                        className="font-mono tabular-nums"
                      />
                    </td>
                    <td className="py-2.5 font-mono text-xs text-slate-500 whitespace-nowrap">{preview}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </SettingsSection>

      <SettingsSection
        title="Invoice footer"
        description="Default notes and terms printed on every new invoice. Editable per invoice."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <label className="block">
            <span className="block text-xs font-medium text-slate-700 mb-1.5">Notes</span>
            <textarea
              rows={4}
              value={values.invoice_notes}
              onChange={setField('invoice_notes')}
              disabled={disabled}
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-400"
              placeholder="Thank you for your business."
            />
            {errors.invoice_notes && <p className="mt-1 text-xs text-rose-600 font-medium">{errors.invoice_notes}</p>}
          </label>
          <label className="block">
            <span className="block text-xs font-medium text-slate-700 mb-1.5">Terms</span>
            <textarea
              rows={4}
              value={values.invoice_terms}
              onChange={setField('invoice_terms')}
              disabled={disabled}
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-400"
              placeholder="Payment is due within the stated terms."
            />
            {errors.invoice_terms && <p className="mt-1 text-xs text-rose-600 font-medium">{errors.invoice_terms}</p>}
          </label>
        </div>
      </SettingsSection>

      {canEdit && (
        <div className="flex justify-end">
          <Button type="submit" isLoading={mutation.isPending} leadingIcon={<Save className="w-4 h-4" />}>
            Save changes
          </Button>
        </div>
      )}
    </form>
  );
}
