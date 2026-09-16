import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Plus, Save, Star, Trash2, Users } from 'lucide-react';
import { customerService } from '../../services/customerService';
import type { ContactIn, CustomerIn, CustomerOut, CustomerStatus } from '../../types/api';
import { Button } from '../../components/common/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/common/Card';
import { ErrorState } from '../../components/common/ErrorState';
import { Input } from '../../components/common/Input';
import { LoadingState } from '../../components/common/LoadingState';
import { PageHeader } from '../../components/common/PageHeader';
import { Select } from '../../components/common/Select';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { cn } from '../../utils/cn';
import {
  validateSensibleName,
  validateEmail,
  validatePhone,
  validateUrl,
  validateGstin,
  validatePan,
  validateCountryCode,
  validatePostalCode,
} from '../../utils/validation';

// ---------------------------------------------------------------------------
// Form model
// ---------------------------------------------------------------------------

interface ContactDraft {
  key: string;
  name: string;
  email: string;
  phone: string;
  designation: string;
  is_primary: boolean;
}

interface FormValues {
  display_name: string;
  company_name: string;
  email: string;
  phone: string;
  website: string;
  status: CustomerStatus;
  gstin: string;
  pan: string;
  tax_exempt: boolean;
  currency: string;
  payment_terms_days: string;
  billing_address_line1: string;
  billing_address_line2: string;
  billing_city: string;
  billing_state: string;
  billing_postal_code: string;
  billing_country: string;
  notes: string;
  contacts: ContactDraft[];
}

type FieldErrors = Record<string, string>;

const CURRENCIES = ['INR', 'USD', 'EUR', 'GBP', 'AED', 'SGD', 'AUD', 'CAD'];
const PAYMENT_TERM_PRESETS = [0, 7, 15, 30, 45, 60, 90];

let contactSeq = 0;
function nextKey(): string {
  contactSeq += 1;
  return `contact-${contactSeq}`;
}

function emptyContact(isPrimary: boolean): ContactDraft {
  return { key: nextKey(), name: '', email: '', phone: '', designation: '', is_primary: isPrimary };
}

const EMPTY_FORM: FormValues = {
  display_name: '',
  company_name: '',
  email: '',
  phone: '',
  website: '',
  status: 'active',
  gstin: '',
  pan: '',
  tax_exempt: false,
  currency: 'INR',
  payment_terms_days: '30',
  billing_address_line1: '',
  billing_address_line2: '',
  billing_city: '',
  billing_state: '',
  billing_postal_code: '',
  billing_country: 'IN',
  notes: '',
  contacts: [],
};

function fromCustomer(c: CustomerOut): FormValues {
  return {
    display_name: c.display_name,
    company_name: c.company_name ?? '',
    email: c.email ?? '',
    phone: c.phone ?? '',
    website: c.website ?? '',
    status: c.status,
    gstin: c.gstin ?? '',
    pan: c.pan ?? '',
    tax_exempt: c.tax_exempt,
    currency: c.currency,
    payment_terms_days: String(c.payment_terms_days),
    billing_address_line1: c.billing_address_line1 ?? '',
    billing_address_line2: c.billing_address_line2 ?? '',
    billing_city: c.billing_city ?? '',
    billing_state: c.billing_state ?? '',
    billing_postal_code: c.billing_postal_code ?? '',
    billing_country: c.billing_country ?? '',
    notes: c.notes ?? '',
    contacts: c.contacts.map((ct) => ({
      key: nextKey(),
      name: ct.name,
      email: ct.email ?? '',
      phone: ct.phone ?? '',
      designation: ct.designation ?? '',
      is_primary: ct.is_primary,
    })),
  };
}

/** Empty strings become null so the API clears the field instead of storing "". */
function orNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

function toContacts(drafts: ContactDraft[]): ContactIn[] {
  return drafts.map((d) => ({
    name: d.name.trim(),
    email: orNull(d.email),
    phone: orNull(d.phone),
    designation: orNull(d.designation),
    is_primary: d.is_primary,
  }));
}

function toPayload(values: FormValues): CustomerIn {
  return {
    display_name: values.display_name.trim(),
    company_name: orNull(values.company_name),
    email: orNull(values.email),
    phone: orNull(values.phone),
    website: orNull(values.website),
    status: values.status,
    gstin: orNull(values.gstin.toUpperCase()),
    pan: orNull(values.pan.toUpperCase()),
    tax_exempt: values.tax_exempt,
    currency: values.currency.trim().toUpperCase(),
    payment_terms_days: Number(values.payment_terms_days),
    billing_address_line1: orNull(values.billing_address_line1),
    billing_address_line2: orNull(values.billing_address_line2),
    billing_city: orNull(values.billing_city),
    billing_state: orNull(values.billing_state),
    billing_postal_code: orNull(values.billing_postal_code),
    billing_country: orNull(values.billing_country.toUpperCase()),
    notes: orNull(values.notes),
  };
}

function validate(values: FormValues): FieldErrors {
  const errors: FieldErrors = {};

  const displayNameError = validateSensibleName(values.display_name, 'Display name');
  if (displayNameError) errors.display_name = displayNameError;

  if (values.company_name.trim() !== '') {
    const companyNameError = validateSensibleName(values.company_name, 'Legal / company name');
    if (companyNameError) errors.company_name = companyNameError;
  }

  const emailError = validateEmail(values.email, { required: true });
  if (emailError) errors.email = emailError;

  const phoneError = validatePhone(values.phone);
  if (phoneError) errors.phone = phoneError;

  const websiteError = validateUrl(values.website);
  if (websiteError) errors.website = websiteError;

  const gstinError = validateGstin(values.gstin);
  if (gstinError) errors.gstin = gstinError;

  const panError = validatePan(values.pan);
  if (panError) errors.pan = panError;

  if (!/^[A-Za-z]{3}$/.test(values.currency.trim())) errors.currency = 'Use a 3-letter currency code';
  const terms = Number(values.payment_terms_days);
  if (values.payment_terms_days.trim() === '' || !Number.isInteger(terms) || terms < 0 || terms > 365) {
    errors.payment_terms_days = 'Enter a whole number of days between 0 and 365';
  }

  if (values.billing_country.trim() !== '') {
    const countryError = validateCountryCode(values.billing_country);
    if (countryError) errors.billing_country = countryError;
  }

  if (values.billing_postal_code.trim() !== '') {
    const postalCodeError = validatePostalCode(values.billing_postal_code);
    if (postalCodeError) errors.billing_postal_code = postalCodeError;
  }

  values.contacts.forEach((c, i) => {
    const contactNameError = validateSensibleName(c.name, 'Contact name');
    if (contactNameError) errors[`contacts.${i}.name`] = contactNameError;

    const contactEmailError = validateEmail(c.email);
    if (contactEmailError) errors[`contacts.${i}.email`] = contactEmailError;

    const contactPhoneError = validatePhone(c.phone);
    if (contactPhoneError) errors[`contacts.${i}.phone`] = contactPhoneError;
  });

  return errors;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function CustomerFormPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canWrite = hasRole('finance');

  const [values, setValues] = useState<FormValues>(EMPTY_FORM);
  const [original, setOriginal] = useState<CustomerOut | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [loading, setLoading] = useState(isEdit);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadCustomer = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setLoadError(null);
    try {
      const data = await customerService.get(id);
      setOriginal(data);
      setValues(fromCustomer(data));
    } catch (err: any) {
      setLoadError(err?.message || 'Failed to load customer');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (isEdit) loadCustomer();
    else {
      setValues(EMPTY_FORM);
      setOriginal(null);
      setLoading(false);
    }
  }, [isEdit, loadCustomer]);

  const setField = <K extends keyof FormValues>(key: K, value: FormValues[K]) => {
    setValues((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const updateContact = (key: string, patch: Partial<ContactDraft>) => {
    setValues((prev) => ({
      ...prev,
      contacts: prev.contacts.map((c) => (c.key === key ? { ...c, ...patch } : c)),
    }));
  };

  const addContact = () => {
    setValues((prev) => ({ ...prev, contacts: [...prev.contacts, emptyContact(prev.contacts.length === 0)] }));
  };

  const removeContact = (key: string) => {
    setValues((prev) => {
      const next = prev.contacts.filter((c) => c.key !== key);
      if (next.length > 0 && !next.some((c) => c.is_primary)) next[0] = { ...next[0], is_primary: true };
      return { ...prev, contacts: next };
    });
  };

  const setPrimaryContact = (key: string) => {
    setValues((prev) => ({
      ...prev,
      contacts: prev.contacts.map((c) => ({ ...c, is_primary: c.key === key })),
    }));
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const clientErrors = validate(values);
    if (Object.keys(clientErrors).length > 0) {
      setErrors(clientErrors);
      showToast('error', 'Please fix the highlighted fields');
      return;
    }
    setErrors({});
    setSaving(true);
    try {
      const payload = toPayload(values);
      const contacts = toContacts(values.contacts);
      let saved: CustomerOut;
      if (isEdit && id) {
        saved = await customerService.update(id, payload);
        // PATCH /customers/{id} ignores contacts; they have their own endpoint.
        saved = await customerService.setContacts(id, contacts);
        showToast('success', 'Customer updated', `${saved.display_name} has been saved.`);
      } else {
        saved = await customerService.create({ ...payload, contacts });
        showToast('success', 'Customer created', `${saved.display_name} is ready for quotes and invoices.`);
      }
      navigate(`/customers/${saved.id}`);
    } catch (err: any) {
      const fields: Record<string, string> | undefined = err?.details?.fields;
      if (fields && Object.keys(fields).length > 0) {
        setErrors(fields);
        showToast('error', err?.message || 'Some fields are invalid');
      } else {
        showToast('error', err?.message || (isEdit ? 'Failed to update customer' : 'Failed to create customer'));
      }
    } finally {
      setSaving(false);
    }
  };

  const backTo = isEdit && id ? { to: `/customers/${id}`, label: original?.display_name ?? 'Customer' } : { to: '/customers', label: 'Customers' };

  if (loading) {
    return (
      <div className="space-y-6 pb-12">
        <PageHeader backTo={backTo} eyebrow="Workspace" title={isEdit ? 'Edit customer' : 'New customer'} />
        <LoadingState message="Loading customer..." />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="space-y-6 pb-12">
        <PageHeader backTo={backTo} eyebrow="Workspace" title="Edit customer" />
        <ErrorState title="Could not load customer" message={loadError} onRetry={loadCustomer} />
      </div>
    );
  }

  if (!canWrite) {
    return (
      <div className="space-y-6 pb-12">
        <PageHeader backTo={backTo} eyebrow="Workspace" title={isEdit ? 'Edit customer' : 'New customer'} />
        <ErrorState
          title="You don't have permission to edit customers"
          message="Only finance, admin and owner roles can create or edit customers. Ask an administrator to update your role."
        />
      </div>
    );
  }

  const termsIsPreset = PAYMENT_TERM_PRESETS.includes(Number(values.payment_terms_days));

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        backTo={backTo}
        eyebrow="Workspace"
        title={isEdit ? `Edit ${original?.display_name ?? 'customer'}` : 'New customer'}
        subtitle={
          isEdit
            ? `Update details for ${original?.customer_number ?? 'this customer'}. Changes apply to new invoices only.`
            : 'Add an organisation or individual you bill. Only the display name and email are required — everything else can be filled in later.'
        }
      />

      <form onSubmit={handleSubmit} noValidate className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-5">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Basic details</CardTitle>
                <CardDescription>The name shown on documents and how to reach the customer.</CardDescription>
              </div>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Input
                label="Display name"
                required
                value={values.display_name}
                onChange={(e) => setField('display_name', e.target.value)}
                error={errors.display_name}
                placeholder="Acme Pvt Ltd"
                autoFocus={!isEdit}
              />
              <Input
                label="Legal / company name"
                value={values.company_name}
                onChange={(e) => setField('company_name', e.target.value)}
                error={errors.company_name}
                placeholder="Acme Private Limited"
              />
              <Input
                label="Billing email"
                type="email"
                required
                value={values.email}
                onChange={(e) => setField('email', e.target.value)}
                error={errors.email}
                placeholder="accounts@acme.com"
                helperText="Invoices and reminders are sent here."
              />
              <Input
                label="Phone"
                value={values.phone}
                onChange={(e) => setField('phone', e.target.value)}
                error={errors.phone}
                placeholder="+91 98765 43210"
              />
              <Input
                label="Website"
                value={values.website}
                onChange={(e) => setField('website', e.target.value)}
                error={errors.website}
                placeholder="https://acme.com"
              />
              <Select
                label="Status"
                value={values.status}
                onChange={(e) => setField('status', e.target.value as CustomerStatus)}
                error={errors.status}
                options={[
                  { value: 'active', label: 'Active' },
                  { value: 'inactive', label: 'Inactive' },
                ]}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div>
                <CardTitle>Tax & billing</CardTitle>
                <CardDescription>Tax identifiers and the default terms applied to new invoices.</CardDescription>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input
                  label="GSTIN"
                  value={values.gstin}
                  onChange={(e) => setField('gstin', e.target.value.toUpperCase())}
                  error={errors.gstin}
                  placeholder="29ABCDE1234F1Z5"
                  maxLength={15}
                  className="font-mono uppercase"
                />
                <Input
                  label="PAN"
                  value={values.pan}
                  onChange={(e) => setField('pan', e.target.value.toUpperCase())}
                  error={errors.pan}
                  placeholder="ABCDE1234F"
                  maxLength={10}
                  className="font-mono uppercase"
                />
                <Select
                  label="Currency"
                  value={CURRENCIES.includes(values.currency) ? values.currency : 'other'}
                  onChange={(e) => setField('currency', e.target.value === 'other' ? '' : e.target.value)}
                  error={CURRENCIES.includes(values.currency) ? errors.currency : undefined}
                  options={[...CURRENCIES.map((c) => ({ value: c, label: c })), { value: 'other', label: 'Other…' }]}
                />
                {!CURRENCIES.includes(values.currency) && (
                  <Input
                    label="Currency code"
                    required
                    value={values.currency}
                    onChange={(e) => setField('currency', e.target.value.toUpperCase())}
                    error={errors.currency}
                    placeholder="e.g. JPY"
                    maxLength={3}
                    className="font-mono uppercase"
                  />
                )}
                <div>
                  <Select
                    label="Payment terms"
                    value={termsIsPreset ? values.payment_terms_days : 'custom'}
                    onChange={(e) => setField('payment_terms_days', e.target.value === 'custom' ? '' : e.target.value)}
                    error={termsIsPreset ? errors.payment_terms_days : undefined}
                    options={[
                      ...PAYMENT_TERM_PRESETS.map((d) => ({
                        value: String(d),
                        label: d === 0 ? 'Due on receipt' : `Net ${d} days`,
                      })),
                      { value: 'custom', label: 'Custom…' },
                    ]}
                  />
                </div>
                {!termsIsPreset && (
                  <Input
                    label="Payment terms (days)"
                    type="number"
                    min={0}
                    max={365}
                    required
                    value={values.payment_terms_days}
                    onChange={(e) => setField('payment_terms_days', e.target.value)}
                    error={errors.payment_terms_days}
                    placeholder="e.g. 21"
                  />
                )}
              </div>
              <label className="flex items-start gap-3 rounded-lg border border-slate-200 p-3.5 cursor-pointer hover:bg-slate-50 transition-colors">
                <input
                  type="checkbox"
                  checked={values.tax_exempt}
                  onChange={(e) => setField('tax_exempt', e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                />
                <span>
                  <span className="block text-sm font-medium text-slate-900">Tax exempt</span>
                  <span className="block text-xs text-slate-500 mt-0.5">
                    No GST is applied to this customer's invoices (e.g. SEZ units or export of services with LUT).
                  </span>
                </span>
              </label>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div>
                <CardTitle>Billing address</CardTitle>
                <CardDescription>Printed on invoices and used to determine place of supply.</CardDescription>
              </div>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="md:col-span-2">
                <Input
                  label="Address line 1"
                  value={values.billing_address_line1}
                  onChange={(e) => setField('billing_address_line1', e.target.value)}
                  error={errors.billing_address_line1}
                  placeholder="Street address, building"
                />
              </div>
              <div className="md:col-span-2">
                <Input
                  label="Address line 2"
                  value={values.billing_address_line2}
                  onChange={(e) => setField('billing_address_line2', e.target.value)}
                  error={errors.billing_address_line2}
                  placeholder="Floor, suite, landmark (optional)"
                />
              </div>
              <Input
                label="City"
                value={values.billing_city}
                onChange={(e) => setField('billing_city', e.target.value)}
                error={errors.billing_city}
                placeholder="Bengaluru"
              />
              <Input
                label="State"
                value={values.billing_state}
                onChange={(e) => setField('billing_state', e.target.value)}
                error={errors.billing_state}
                placeholder="Karnataka"
              />
              <Input
                label="Postal code"
                value={values.billing_postal_code}
                onChange={(e) => setField('billing_postal_code', e.target.value)}
                error={errors.billing_postal_code}
                placeholder="560001"
              />
              <Input
                label="Country"
                value={values.billing_country}
                onChange={(e) => setField('billing_country', e.target.value.toUpperCase())}
                error={errors.billing_country}
                placeholder="IN"
                maxLength={2}
                helperText="ISO 3166-1 alpha-2 code"
                className="font-mono uppercase"
              />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Contacts</CardTitle>
                <CardDescription>People who receive billing communication.</CardDescription>
              </div>
              <Button type="button" variant="outline" size="sm" onClick={addContact} leadingIcon={<Plus className="w-4 h-4" />}>
                Add
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {values.contacts.length === 0 && (
                <div className="flex flex-col items-center text-center py-4">
                  <div className="p-2.5 rounded-full bg-slate-100 text-slate-500 mb-2">
                    <Users className="w-5 h-5 stroke-1" />
                  </div>
                  <p className="text-xs text-slate-500 max-w-[16rem] leading-relaxed">
                    No contacts yet. Add the finance or procurement person who should receive invoices.
                  </p>
                </div>
              )}
              {values.contacts.map((c, i) => (
                <div
                  key={c.key}
                  className={cn(
                    'rounded-lg border p-3.5 space-y-3',
                    c.is_primary ? 'border-brand-200 bg-brand-50/40' : 'border-slate-200 bg-slate-50/40'
                  )}
                >
                  <div className="flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setPrimaryContact(c.key)}
                      className={cn(
                        'inline-flex items-center gap-1.5 text-xs font-medium rounded-md px-2 py-1 transition-colors',
                        c.is_primary ? 'text-brand-700 bg-brand-100/70' : 'text-slate-500 hover:text-slate-800 hover:bg-slate-100'
                      )}
                      aria-pressed={c.is_primary}
                    >
                      <Star className={cn('w-3.5 h-3.5', c.is_primary && 'fill-current')} />
                      {c.is_primary ? 'Primary contact' : 'Make primary'}
                    </button>
                    <button
                      type="button"
                      onClick={() => removeContact(c.key)}
                      className="p-1.5 rounded-md text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                      aria-label="Remove contact"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                  <Input
                    label="Name"
                    required
                    value={c.name}
                    onChange={(e) => updateContact(c.key, { name: e.target.value })}
                    error={errors[`contacts.${i}.name`]}
                    placeholder="Full name"
                  />
                  <Input
                    label="Designation"
                    value={c.designation}
                    onChange={(e) => updateContact(c.key, { designation: e.target.value })}
                    error={errors[`contacts.${i}.designation`]}
                    placeholder="e.g. Accounts Payable"
                  />
                  <Input
                    label="Email"
                    type="email"
                    value={c.email}
                    onChange={(e) => updateContact(c.key, { email: e.target.value })}
                    error={errors[`contacts.${i}.email`]}
                    placeholder="name@company.com"
                  />
                  <Input
                    label="Phone"
                    value={c.phone}
                    onChange={(e) => updateContact(c.key, { phone: e.target.value })}
                    error={errors[`contacts.${i}.phone`]}
                    placeholder="+91 ..."
                  />
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div>
                <CardTitle>Internal notes</CardTitle>
                <CardDescription>Visible to your team only — never printed on documents.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <textarea
                rows={5}
                value={values.notes}
                onChange={(e) => setField('notes', e.target.value)}
                placeholder="Billing preferences, PO requirements, escalation contacts..."
                className={cn(
                  'block w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 transition-colors',
                  'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
                  errors.notes ? 'border-rose-300' : 'border-slate-300 hover:border-slate-400'
                )}
              />
              {errors.notes && <p className="mt-1 text-xs text-rose-600 font-medium">{errors.notes}</p>}
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-3 flex flex-col-reverse sm:flex-row sm:items-center sm:justify-end gap-2 pt-2 border-t border-slate-200">
          <Button type="button" variant="ghost" onClick={() => navigate(backTo.to)} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" isLoading={saving} leadingIcon={<Save className="w-4 h-4" />}>
            {isEdit ? 'Save changes' : 'Create customer'}
          </Button>
        </div>
      </form>
    </div>
  );
}

export default CustomerFormPage;
