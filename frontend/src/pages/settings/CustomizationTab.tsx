import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Save } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { organizationService } from '../../services/organizationService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { useAuth } from '../../hooks/useAuth';
import type { OrganizationOut, OrganizationUpdate } from '../../types/api';
import { ReadOnlyNotice, SettingsSection, nullable, str, type FieldErrors } from './settingsShared';

const HEX_COLOR_RE = /^#[0-9A-Fa-f]{6}$/;

const DATE_FORMATS: { value: string; label: string; example: string }[] = [
  { value: 'DD/MM/YYYY', label: 'DD/MM/YYYY', example: '31/12/2026' },
  { value: 'MM/DD/YYYY', label: 'MM/DD/YYYY', example: '12/31/2026' },
  { value: 'YYYY-MM-DD', label: 'YYYY-MM-DD', example: '2026-12-31' },
];

const DASHBOARD_RANGES: { value: string; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: '7_days', label: 'Last 7 days' },
  { value: '30_days', label: 'Last 30 days' },
  { value: '3_months', label: 'Last 3 months' },
  { value: '12_months', label: 'Last 12 months' },
];

const TABLE_DENSITIES: { value: string; label: string }[] = [
  { value: 'comfortable', label: 'Comfortable' },
  { value: 'compact', label: 'Compact' },
];

interface FormValues {
  brand_color: string;
  quote_notes: string;
  quote_terms: string;
  date_format: string;
  decimal_display_precision: string;
  default_dashboard_range: string;
  table_density: string;
}

function toForm(org: OrganizationOut): FormValues {
  return {
    brand_color: str(org.brand_color),
    quote_notes: str(org.quote_notes),
    quote_terms: str(org.quote_terms),
    date_format: org.date_format,
    decimal_display_precision: String(org.decimal_display_precision),
    default_dashboard_range: org.default_dashboard_range,
    table_density: org.table_density,
  };
}

export function CustomizationTab({ organization, canEdit }: { organization: OrganizationOut; canEdit: boolean }) {
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
      showToast('success', 'Customization saved', 'Branding and display preferences were updated.');
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
    if (values.brand_color.trim() !== '' && !HEX_COLOR_RE.test(values.brand_color.trim())) {
      clientErrors.brand_color = 'Enter a hex color like #2563EB.';
    }
    const precision = Number(values.decimal_display_precision);
    if (!Number.isInteger(precision) || precision < 0 || precision > 6) {
      clientErrors.decimal_display_precision = 'Enter a whole number between 0 and 6.';
    }

    if (Object.keys(clientErrors).length > 0) {
      setErrors(clientErrors);
      return;
    }

    mutation.mutate({
      brand_color: nullable(values.brand_color),
      quote_notes: nullable(values.quote_notes),
      quote_terms: nullable(values.quote_terms),
      date_format: values.date_format,
      decimal_display_precision: precision,
      default_dashboard_range: values.default_dashboard_range,
      table_density: values.table_density,
    });
  };

  const disabled = !canEdit || mutation.isPending;
  const setField = (key: 'quote_notes' | 'quote_terms') =>
    (e: React.ChangeEvent<HTMLTextAreaElement>) => setValues((prev) => ({ ...prev, [key]: e.target.value }));

  const setHexColor = (value: string) => setValues((prev) => ({ ...prev, brand_color: value }));

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      {!canEdit && <ReadOnlyNotice what="customization settings" />}

      <SettingsSection
        title="Branding"
        description="Used on quote and invoice documents alongside your logo."
      >
        <div className="flex items-end gap-3">
          <label className="block">
            <span className="block text-xs font-medium text-slate-700 mb-1.5">Brand color</span>
            <input
              type="color"
              value={HEX_COLOR_RE.test(values.brand_color) ? values.brand_color : '#2563eb'}
              onChange={(e) => setHexColor(e.target.value.toUpperCase())}
              disabled={disabled}
              className="h-9 w-14 rounded-lg border border-slate-300 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
              aria-label="Brand color picker"
            />
          </label>
          <div className="w-40">
            <Input
              aria-label="Brand color hex"
              value={values.brand_color}
              onChange={(e) => setHexColor(e.target.value)}
              placeholder="#2563EB"
              error={errors.brand_color}
              disabled={disabled}
              className="font-mono uppercase"
            />
          </div>
          {organization.logo_url && (
            <img
              src={organization.logo_url}
              alt="Organization logo preview"
              className="h-9 w-9 rounded-lg border border-slate-200 object-contain bg-white"
            />
          )}
        </div>
      </SettingsSection>

      <SettingsSection
        title="Document preferences"
        description="Applied when generating new quotes and invoices, and formatting dates and amounts across the app."
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select
            label="Date format"
            value={values.date_format}
            onChange={(e) => setValues((prev) => ({ ...prev, date_format: e.target.value }))}
            options={DATE_FORMATS.map((f) => ({ value: f.value, label: `${f.label} (${f.example})` }))}
            error={errors.date_format}
            disabled={disabled}
          />
          <Input
            label="Decimal display precision"
            type="number"
            min={0}
            max={6}
            step={1}
            value={values.decimal_display_precision}
            onChange={(e) => setValues((prev) => ({ ...prev, decimal_display_precision: e.target.value }))}
            error={errors.decimal_display_precision}
            disabled={disabled}
            helperText="Display only — changes how many decimals are shown on screen. Stored amounts always keep exact 2-decimal precision."
          />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <label className="block">
            <span className="block text-xs font-medium text-slate-700 mb-1.5">Quote notes</span>
            <textarea
              rows={4}
              value={values.quote_notes}
              onChange={setField('quote_notes')}
              disabled={disabled}
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-400"
              placeholder="Thank you for considering us."
            />
            {errors.quote_notes && <p className="mt-1 text-xs text-rose-600 font-medium">{errors.quote_notes}</p>}
          </label>
          <label className="block">
            <span className="block text-xs font-medium text-slate-700 mb-1.5">Quote terms</span>
            <textarea
              rows={4}
              value={values.quote_terms}
              onChange={setField('quote_terms')}
              disabled={disabled}
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-400"
              placeholder="Prices valid for 30 days from the issue date."
            />
            {errors.quote_terms && <p className="mt-1 text-xs text-rose-600 font-medium">{errors.quote_terms}</p>}
          </label>
        </div>
      </SettingsSection>

      <SettingsSection
        title="UI preferences"
        description="Personalize how dashboards and tables load for everyone in this organization."
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select
            label="Default dashboard range"
            value={values.default_dashboard_range}
            onChange={(e) => setValues((prev) => ({ ...prev, default_dashboard_range: e.target.value }))}
            options={DASHBOARD_RANGES}
            error={errors.default_dashboard_range}
            disabled={disabled}
          />
          <Select
            label="Table density"
            value={values.table_density}
            onChange={(e) => setValues((prev) => ({ ...prev, table_density: e.target.value }))}
            options={TABLE_DENSITIES}
            error={errors.table_density}
            disabled={disabled}
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

export default CustomizationTab;
