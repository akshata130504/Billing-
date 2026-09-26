import { useEffect, useState, useRef, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, Upload, X } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { PhoneInput } from '../../components/common/PhoneInput';
import { Select } from '../../components/common/Select';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { organizationService } from '../../services/organizationService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { useAuth } from '../../hooks/useAuth';
import type { OrganizationOut, OrganizationUpdate } from '../../types/api';
import { ReadOnlyNotice, SettingsSection, nullable, str, type FieldErrors } from './settingsShared';
import { ProfilePhotoUpload } from './ProfilePhotoUpload';
import { validateSensibleName, validateEmail, validatePhone, validateUrl, validateGstin, validatePan } from '../../utils/validation';

interface FormValues {
  name: string;
  legal_name: string;
  email: string;
  phone: string;
  website: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  gstin: string;
  pan: string;
  default_currency: string;
  timezone: string;
  logo_url: string;
}

function toForm(org: OrganizationOut): FormValues {
  return {
    name: org.name,
    legal_name: str(org.legal_name),
    email: str(org.email),
    phone: str(org.phone),
    website: str(org.website),
    address_line1: str(org.address_line1),
    address_line2: str(org.address_line2),
    city: str(org.city),
    state: str(org.state),
    postal_code: str(org.postal_code),
    country: str(org.country),
    gstin: str(org.gstin),
    pan: str(org.pan),
    default_currency: org.default_currency,
    timezone: org.timezone,
    logo_url: str(org.logo_url),
  };
}

function toPayload(values: FormValues): OrganizationUpdate {
  return {
    name: values.name.trim(),
    legal_name: nullable(values.legal_name),
    email: nullable(values.email),
    phone: nullable(values.phone),
    website: nullable(values.website),
    address_line1: nullable(values.address_line1),
    address_line2: nullable(values.address_line2),
    city: nullable(values.city),
    state: nullable(values.state),
    postal_code: nullable(values.postal_code),
    country: values.country.trim().toUpperCase() || null,
    gstin: nullable(values.gstin)?.toUpperCase() ?? null,
    pan: nullable(values.pan)?.toUpperCase() ?? null,
    default_currency: values.default_currency.trim().toUpperCase(),
    timezone: values.timezone.trim(),
    logo_url: nullable(values.logo_url),
  };
}

function validate(values: FormValues): FieldErrors {
  const errors: FieldErrors = {};

  const nameError = validateSensibleName(values.name, 'Organization name');
  if (nameError) errors.name = nameError;

  const emailError = validateEmail(values.email);
  if (emailError) errors.email = emailError;

  const phoneError = validatePhone(values.phone);
  if (phoneError) errors.phone = phoneError;

  const websiteError = validateUrl(values.website);
  if (websiteError) errors.website = websiteError;

  const gstinError = validateGstin(values.gstin);
  if (gstinError) errors.gstin = gstinError;

  const panError = validatePan(values.pan);
  if (panError) errors.pan = panError;

  return errors;
}

const CURRENCIES = ['INR', 'USD', 'EUR', 'GBP', 'AED', 'SGD', 'AUD', 'CAD'];

const TIMEZONES = [
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Europe/London',
  'Europe/Berlin',
  'America/New_York',
  'America/Los_Angeles',
  'Australia/Sydney',
  'UTC',
];

export function OrganizationTab({ organization, canEdit }: { organization: OrganizationOut; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { refreshMe } = useAuth();
  const [values, setValues] = useState<FormValues>(() => toForm(organization));
  const [errors, setErrors] = useState<FieldErrors>({});
  const [isUploadingLogo, setIsUploadingLogo] = useState(false);
  const logoInputRef = useRef<HTMLInputElement | null>(null);

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setIsUploadingLogo(true);
      const res = await organizationService.uploadLogo(file);
      setValues((prev) => ({ ...prev, logo_url: res.logo_url }));
      showToast('success', 'Logo uploaded', 'Organization logo was uploaded successfully.');
    } catch (err: any) {
      showToast('error', 'Upload failed', err?.response?.data?.detail || err.message || 'Could not upload logo.');
    } finally {
      setIsUploadingLogo(false);
      if (logoInputRef.current) logoInputRef.current.value = '';
    }
  };

  const handleLogoRemove = async () => {
    try {
      await organizationService.deleteLogo();
      setValues((prev) => ({ ...prev, logo_url: '' }));
      showToast('success', 'Logo removed', 'Organization logo was removed.');
    } catch (err: any) {
      setValues((prev) => ({ ...prev, logo_url: '' }));
    }
  };

  useEffect(() => {
    setValues(toForm(organization));
  }, [organization]);

  const mutation = useMutation({
    mutationFn: (body: OrganizationUpdate) => organizationService.update(body),
    onSuccess: async (updated) => {
      queryClient.setQueryData(queryKeys.organization.detail(), updated);
      await refreshMe();
      setErrors({});
      showToast('success', 'Organization updated', 'Your organization details were saved.');
    },
    onError: (err) => {
      const fields = fieldErrors(err);
      setErrors(fields);
      if (Object.keys(fields).length === 0) {
        showToast('error', 'Could not save', toApiError(err).message);
      }
    },
  });

  const set = (key: keyof FormValues) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setValues((prev) => ({ ...prev, [key]: e.target.value }));

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!canEdit) return;
    const clientErrors = validate(values);
    if (Object.keys(clientErrors).length > 0) {
      setErrors(clientErrors);
      showToast('error', 'Please fix the highlighted fields');
      return;
    }
    setErrors({});
    mutation.mutate(toPayload(values));
  };

  const disabled = !canEdit || mutation.isPending;
  const timezoneOptions = TIMEZONES.includes(values.timezone)
    ? TIMEZONES
    : [values.timezone, ...TIMEZONES];
  const currencyOptions = CURRENCIES.includes(values.default_currency)
    ? CURRENCIES
    : [values.default_currency, ...CURRENCIES];

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      {!canEdit && <ReadOnlyNotice what="organization details" />}

      <SettingsSection
        title="Profile"
        description="Shown on invoices, quotes and the public payment page."
      >
        <ProfilePhotoUpload />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input label="Organization name" required value={values.name} onChange={set('name')} error={errors.name} disabled={disabled} />
          <Input label="Legal name" value={values.legal_name} onChange={set('legal_name')} error={errors.legal_name} disabled={disabled} helperText="Registered entity name, if different." />
          <Input label="Billing email" type="email" value={values.email} onChange={set('email')} error={errors.email} disabled={disabled} />
          <PhoneInput label="Phone" value={values.phone} onChange={(v) => setValues((prev) => ({ ...prev, phone: v }))} error={errors.phone} disabled={disabled} />
          <Input label="Website" type="url" placeholder="https://" value={values.website} onChange={set('website')} error={errors.website} disabled={disabled} />
          <div className="space-y-2 sm:col-span-2">
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <Input label="Logo URL" type="url" placeholder="https://" value={values.logo_url} onChange={set('logo_url')} error={errors.logo_url} disabled={disabled} helperText="Public image URL or upload an image file." />
              </div>
              <input
                ref={logoInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={handleLogoUpload}
                disabled={disabled || isUploadingLogo}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mb-1"
                onClick={() => logoInputRef.current?.click()}
                disabled={disabled || isUploadingLogo}
                isLoading={isUploadingLogo}
                leadingIcon={<Upload className="w-3.5 h-3.5" />}
              >
                Upload File
              </Button>
            </div>
            {values.logo_url && (
              <div className="flex items-center gap-3 p-2 border border-slate-200 rounded-lg bg-slate-50 w-fit">
                <img
                  src={values.logo_url}
                  alt="Logo preview"
                  className="max-h-8 max-w-[120px] object-contain"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-xs text-red-600 hover:text-red-700 h-7 px-2"
                  onClick={handleLogoRemove}
                  disabled={disabled}
                >
                  <X className="w-3.5 h-3.5 mr-1" /> Remove
                </Button>
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="font-medium text-slate-600">Slug</span>
          <code className="font-mono bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5">{organization.slug}</code>
        </div>
      </SettingsSection>

      <SettingsSection title="Address">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input label="Address line 1" value={values.address_line1} onChange={set('address_line1')} error={errors.address_line1} disabled={disabled} />
          <Input label="Address line 2" value={values.address_line2} onChange={set('address_line2')} error={errors.address_line2} disabled={disabled} />
          <Input label="City" value={values.city} onChange={set('city')} error={errors.city} disabled={disabled} />
          <Input label="State" value={values.state} onChange={set('state')} error={errors.state} disabled={disabled} />
          <Input label="Postal code" value={values.postal_code} onChange={set('postal_code')} error={errors.postal_code} disabled={disabled} />
          <Input label="Country (ISO-2)" maxLength={2} placeholder="IN" value={values.country} onChange={set('country')} error={errors.country} disabled={disabled} className="uppercase" />
        </div>
      </SettingsSection>

      <SettingsSection title="Tax & locale">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input label="GSTIN" value={values.gstin} onChange={set('gstin')} error={errors.gstin} disabled={disabled} className="uppercase font-mono" />
          <Input label="PAN" value={values.pan} onChange={set('pan')} error={errors.pan} disabled={disabled} className="uppercase font-mono" />
          <Select
            label="Default currency"
            value={values.default_currency}
            onChange={set('default_currency')}
            error={errors.default_currency}
            disabled={disabled}
            options={currencyOptions.map((c) => ({ value: c, label: c }))}
          />
          <Select
            label="Timezone"
            value={values.timezone}
            onChange={set('timezone')}
            error={errors.timezone}
            disabled={disabled}
            options={timezoneOptions.map((tz) => ({ value: tz, label: tz }))}
          />
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
