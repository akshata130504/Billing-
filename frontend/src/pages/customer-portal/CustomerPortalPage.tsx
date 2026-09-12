import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Globe,
  RefreshCw,
  Save,
  Copy,
  KeyRound,
  ShieldCheck,
  CreditCard,
  Clock,
  FileText,
  Repeat,
  LayoutDashboard,
  Wallet,
  Sparkles,
  Info,
  Undo2,
  HeartHandshake,
  Check,
} from 'lucide-react';
import { portalService } from '../../services/portalService';
import { API_ORIGIN } from '../../services/apiClient';
import type {
  CustomerPortalSettings,
  CustomerPortalSettingsUpdate,
  CustomerPortalToggleKey,
} from '../../types/portal';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Input } from '../../components/common/Input';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime } from '../../utils/format';
import { cn } from '../../utils/cn';

// ---------------------------------------------------------------------------
// Form model
// ---------------------------------------------------------------------------

type FormState = Pick<
  CustomerPortalSettings,
  | 'portal_name'
  | 'portal_url_slug'
  | 'banner_message'
  | 'auto_invite_enabled'
  | 'mfa_enabled'
  | 'prevent_duplicate_payments'
  | 'allow_self_signup'
  | 'allow_document_upload'
  | 'allow_document_forwarding'
  | 'allow_save_payment_methods'
  | 'save_payment_method_default'
  | 'prevent_deselecting_save_payment'
  | 'enable_identity_verification_public_links'
  | 'trials_allow_customer_extension'
  | 'trials_max_extensions'
  | 'trials_activate_immediately'
>;

const FORM_KEYS: (keyof FormState)[] = [
  'portal_name',
  'portal_url_slug',
  'banner_message',
  'auto_invite_enabled',
  'mfa_enabled',
  'prevent_duplicate_payments',
  'allow_self_signup',
  'allow_document_upload',
  'allow_document_forwarding',
  'allow_save_payment_methods',
  'save_payment_method_default',
  'prevent_deselecting_save_payment',
  'enable_identity_verification_public_links',
  'trials_allow_customer_extension',
  'trials_max_extensions',
  'trials_activate_immediately',
];

function toForm(s: CustomerPortalSettings): FormState {
  const out = {} as FormState;
  FORM_KEYS.forEach((k) => {
    (out as Record<string, unknown>)[k] = s[k];
  });
  return out;
}

/** Only the fields that differ from the saved record are sent (backend uses exclude_unset). */
function diff(saved: FormState, current: FormState): CustomerPortalSettingsUpdate {
  const patch: Record<string, unknown> = {};
  FORM_KEYS.forEach((k) => {
    const a = saved[k];
    const b = current[k];
    const normA = typeof a === 'string' && a.trim() === '' ? null : a;
    const normB = typeof b === 'string' && b.trim() === '' ? null : b;
    if (normA !== normB) patch[k] = normB;
  });
  return patch as CustomerPortalSettingsUpdate;
}

interface ToggleDef {
  key: CustomerPortalToggleKey;
  label: string;
  description: string;
}

const ACCESS_TOGGLES: ToggleDef[] = [
  {
    key: 'allow_self_signup',
    label: 'Allow self sign-up',
    description:
      'Customers can create their own portal login. Their email must match the customer record or one of its contacts.',
  },
  {
    key: 'auto_invite_enabled',
    label: 'Auto-invite new customers',
    description: 'Flag new customer records for a portal invitation as soon as they are created.',
  },
  {
    key: 'mfa_enabled',
    label: 'Require multi-factor authentication',
    description: 'Portal users must supply an MFA code when signing in.',
  },
  {
    key: 'enable_identity_verification_public_links',
    label: 'Identity verification on public links',
    description: 'Ask customers to verify who they are before opening shared invoice or quote links.',
  },
  {
    key: 'allow_document_upload',
    label: 'Allow document upload',
    description: 'Customers can attach supporting documents (POs, remittance advice) from the portal.',
  },
  {
    key: 'allow_document_forwarding',
    label: 'Allow document forwarding',
    description: 'Customers can forward invoices and statements to other email addresses.',
  },
];

const PAYMENT_TOGGLES: ToggleDef[] = [
  {
    key: 'prevent_duplicate_payments',
    label: 'Prevent duplicate payments',
    description:
      'Block a new hosted checkout for an invoice while another payment attempt on it is still processing.',
  },
  {
    key: 'allow_save_payment_methods',
    label: 'Allow saving payment methods',
    description: 'Show the "save this card" option during checkout so customers can pay faster next time.',
  },
  {
    key: 'save_payment_method_default',
    label: 'Save payment method by default',
    description: 'Pre-tick the "save this card" option on hosted checkout pages.',
  },
  {
    key: 'prevent_deselecting_save_payment',
    label: 'Lock the save option',
    description: 'Customers cannot untick "save this card" — useful for subscriptions that need a card on file.',
  },
];

const TRIAL_TOGGLES: ToggleDef[] = [
  {
    key: 'trials_allow_customer_extension',
    label: 'Customers can extend their own trial',
    description: 'Exposes the self-service "extend trial" action (1–30 days per extension) in the portal.',
  },
  {
    key: 'trials_activate_immediately',
    label: 'Activate immediately on early conversion',
    description: 'When a customer converts a trial early, the subscription goes live straight away.',
  },
];

// ---------------------------------------------------------------------------
// Small UI helpers
// ---------------------------------------------------------------------------

function ToggleRow({
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3.5">
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-900">{label}</p>
        <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2',
          checked ? 'bg-brand-600' : 'bg-slate-200',
          disabled && 'opacity-50 cursor-not-allowed'
        )}
      >
        <span
          className={cn(
            'inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform',
            checked ? 'translate-x-5' : 'translate-x-0.5'
          )}
        />
      </button>
    </div>
  );
}

function SectionCard({
  icon,
  title,
  description,
  children,
  className,
}: {
  icon: React.ReactNode;
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('bg-white rounded-xl border border-slate-200 shadow-sm', className)}>
      <div className="px-5 py-4 border-b border-slate-100 flex items-start gap-3">
        <div className="p-2 rounded-lg bg-brand-50 text-brand-600 shrink-0">{icon}</div>
        <div>
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          {description && <p className="text-xs text-slate-500 mt-0.5">{description}</p>}
        </div>
      </div>
      <div className="px-5">{children}</div>
    </div>
  );
}

function CodeLine({ label, value, onCopy }: { label: string; value: string; onCopy: () => void }) {
  return (
    <div>
      <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{label}</p>
      <div className="flex items-center gap-2">
        <code className="flex-1 min-w-0 truncate text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-700">
          {value}
        </code>
        <Button variant="ghost" size="sm" onClick={onCopy} aria-label={`Copy ${label}`} className="shrink-0">
          <Copy className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  );
}

function StatusChip({ on, onLabel = 'Enabled', offLabel = 'Off' }: { on: boolean; onLabel?: string; offLabel?: string }) {
  return <Badge variant={on ? 'success' : 'neutral'} size="sm">{on ? onLabel : offLabel}</Badge>;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function CustomerPortalPage() {
  const { showToast } = useToast();
  const { hasRole, organization } = useAuth();
  const canEdit = hasRole('admin');

  const [settings, setSettings] = useState<CustomerPortalSettings | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const data = await portalService.getSettings();
      setSettings(data);
      setForm(toForm(data));
    } catch (err: any) {
      setLoadError(err.message || 'Failed to load customer portal settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const patch = useMemo(() => (settings && form ? diff(toForm(settings), form) : {}), [settings, form]);
  const dirty = Object.keys(patch).length > 0;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const validate = (): boolean => {
    if (!form) return false;
    const errs: Record<string, string> = {};
    if (!form.portal_name.trim()) errs.portal_name = 'Portal name is required.';
    else if (form.portal_name.length > 100) errs.portal_name = 'Maximum 100 characters.';
    if (form.portal_url_slug && form.portal_url_slug.length > 64) errs.portal_url_slug = 'Maximum 64 characters.';
    if (form.portal_url_slug && !/^[a-z0-9-]+$/i.test(form.portal_url_slug))
      errs.portal_url_slug = 'Use letters, numbers and hyphens only.';
    if (!Number.isInteger(form.trials_max_extensions) || form.trials_max_extensions < 0 || form.trials_max_extensions > 10)
      errs.trials_max_extensions = 'Must be a whole number between 0 and 10.';
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSave = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!form || !settings || !dirty) return;
    if (!validate()) {
      showToast('error', 'Please fix the highlighted fields.');
      return;
    }
    try {
      setSaving(true);
      const updated = await portalService.updateSettings(patch);
      setSettings(updated);
      setForm(toForm(updated));
      showToast('success', 'Portal settings saved', `${Object.keys(patch).length} setting(s) updated.`);
    } catch (err: any) {
      const fields = err?.details?.fields;
      if (fields && typeof fields === 'object') setFieldErrors(fields);
      showToast('error', err.message || 'Failed to save portal settings');
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    if (settings) setForm(toForm(settings));
    setFieldErrors({});
  };

  const copy = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      showToast('success', `${label} copied`);
    } catch {
      showToast('error', 'Clipboard unavailable', 'Select the text and copy it manually.');
    }
  };

  const apiOrigin = API_ORIGIN || window.location.origin;
  const orgId = organization?.id ?? settings?.organization_id ?? '';
  const signupUrl = `${apiOrigin}/api/v1/portal/auth/signup`;
  const loginUrl = `${apiOrigin}/api/v1/portal/auth/login`;

  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-1">
            <HeartHandshake className="w-4 h-4" />
            Customer Experience
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Customer Portal</h1>
          <p className="text-sm text-slate-500 mt-1">
            Control what your customers can see and do when they sign in to view invoices, subscriptions and
            saved payment methods.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => load()}
            disabled={loading}
            leadingIcon={<RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />}
          >
            Refresh
          </Button>
          {canEdit && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => handleSave()}
              disabled={!dirty || saving || loading}
              isLoading={saving}
              leadingIcon={<Save className="w-4 h-4" />}
            >
              Save changes
            </Button>
          )}
        </div>
      </div>

      {loading && !settings ? (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm py-16">
          <LoadingState message="Loading portal settings..." />
        </div>
      ) : loadError && !settings ? (
        <ErrorState title="Couldn't load portal settings" message={loadError} onRetry={load} />
      ) : settings && form ? (
        <form onSubmit={handleSave} className="grid grid-cols-1 lg:grid-cols-3 gap-6" noValidate>
          {/* ---------------- Left: settings ---------------- */}
          <div className="lg:col-span-2 space-y-6">
            {!canEdit && (
              <div className="flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
                <Info className="w-4 h-4 mt-0.5 shrink-0" />
                <p>
                  You have read-only access to portal settings. Changing them requires the <strong>Admin</strong>{' '}
                  or <strong>Owner</strong> role.
                </p>
              </div>
            )}

            <SectionCard
              icon={<Globe className="w-4 h-4" />}
              title="Portal identity"
              description="How the portal introduces itself to your customers."
            >
              <div className="py-5 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Input
                    label="Portal name"
                    required
                    maxLength={100}
                    value={form.portal_name}
                    disabled={!canEdit}
                    error={fieldErrors.portal_name}
                    onChange={(e) => set('portal_name', e.target.value)}
                    helperText="Shown in the portal header and dashboard."
                  />
                  <Input
                    label="URL slug"
                    maxLength={64}
                    value={form.portal_url_slug ?? ''}
                    disabled={!canEdit}
                    error={fieldErrors.portal_url_slug}
                    onChange={(e) => set('portal_url_slug', e.target.value || null)}
                    helperText="Reserved for the hosted portal address. Letters, numbers and hyphens."
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1.5">Banner message</label>
                  <textarea
                    rows={3}
                    value={form.banner_message ?? ''}
                    disabled={!canEdit}
                    onChange={(e) => set('banner_message', e.target.value || null)}
                    placeholder="e.g. Our finance team is closed on 2 October. Payments will be reconciled the next working day."
                    className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-400"
                  />
                  <p className="mt-1.5 text-xs text-slate-500">
                    Displayed at the top of the customer dashboard. Leave empty to hide the banner.
                  </p>
                </div>
              </div>
            </SectionCard>

            <SectionCard
              icon={<ShieldCheck className="w-4 h-4" />}
              title="Access & security"
              description="Who can sign in and what they can share."
            >
              <div className="divide-y divide-slate-100">
                {ACCESS_TOGGLES.map((tg) => (
                  <ToggleRow
                    key={tg.key}
                    label={tg.label}
                    description={tg.description}
                    checked={form[tg.key]}
                    disabled={!canEdit}
                    onChange={(v) => set(tg.key, v)}
                  />
                ))}
              </div>
            </SectionCard>

            <SectionCard
              icon={<CreditCard className="w-4 h-4" />}
              title="Payments & saved cards"
              description="These also govern the hosted checkout pages your customers pay through."
            >
              <div className="divide-y divide-slate-100">
                {PAYMENT_TOGGLES.map((tg) => (
                  <ToggleRow
                    key={tg.key}
                    label={tg.label}
                    description={tg.description}
                    checked={form[tg.key]}
                    disabled={!canEdit || (tg.key !== 'allow_save_payment_methods' && tg.key !== 'prevent_duplicate_payments' && !form.allow_save_payment_methods)}
                    onChange={(v) => set(tg.key, v)}
                  />
                ))}
              </div>
            </SectionCard>

            <SectionCard
              icon={<Clock className="w-4 h-4" />}
              title="Trials"
              description="Self-service trial controls available to customers on trialing subscriptions."
            >
              <div className="divide-y divide-slate-100">
                {TRIAL_TOGGLES.map((tg) => (
                  <ToggleRow
                    key={tg.key}
                    label={tg.label}
                    description={tg.description}
                    checked={form[tg.key]}
                    disabled={!canEdit}
                    onChange={(v) => set(tg.key, v)}
                  />
                ))}
                <div className="py-4 grid grid-cols-1 sm:grid-cols-2 gap-4 items-start">
                  <Input
                    type="number"
                    label="Maximum extensions per trial"
                    min={0}
                    max={10}
                    step={1}
                    value={form.trials_max_extensions}
                    disabled={!canEdit || !form.trials_allow_customer_extension}
                    error={fieldErrors.trials_max_extensions}
                    onChange={(e) => set('trials_max_extensions', Number(e.target.value))}
                    helperText="0–10. Each extension can add up to 30 days."
                  />
                </div>
              </div>
            </SectionCard>

            {/* Sticky save bar */}
            {canEdit && dirty && (
              <div className="sticky bottom-4 z-10 flex items-center justify-between gap-3 rounded-xl border border-brand-200 bg-brand-50/95 backdrop-blur px-4 py-3 shadow-lg">
                <p className="text-xs font-medium text-brand-800">
                  {Object.keys(patch).length} unsaved change{Object.keys(patch).length === 1 ? '' : 's'}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={handleDiscard}
                    disabled={saving}
                    leadingIcon={<Undo2 className="w-3.5 h-3.5" />}
                  >
                    Discard
                  </Button>
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    disabled={saving}
                    isLoading={saving}
                    leadingIcon={<Save className="w-3.5 h-3.5" />}
                  >
                    Save changes
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* ---------------- Right: access + preview ---------------- */}
          <div className="space-y-6">
            <SectionCard
              icon={<KeyRound className="w-4 h-4" />}
              title="Portal access"
              description="How customers get in today."
            >
              <div className="py-5 space-y-4">
                <div className="flex items-start gap-2.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
                  <Badge variant="info" size="sm" className="shrink-0 mt-0.5">API-enabled</Badge>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    The portal is available through the public API. A hosted sign-in screen is not part of this
                    app yet, so customers (or your own customer-facing site) call these endpoints directly.
                  </p>
                </div>

                <CodeLine
                  label="Organization ID (required in every portal call)"
                  value={orgId || '—'}
                  onCopy={() => copy('Organization ID', orgId)}
                />
                <CodeLine label="Sign-up endpoint" value={`POST ${signupUrl}`} onCopy={() => copy('Sign-up endpoint', signupUrl)} />
                <CodeLine label="Sign-in endpoint" value={`POST ${loginUrl}`} onCopy={() => copy('Sign-in endpoint', loginUrl)} />

                <ol className="space-y-2.5 text-xs text-slate-600 leading-relaxed list-none">
                  <li className="flex gap-2">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-brand-50 text-brand-700 text-[11px] font-semibold flex items-center justify-center">1</span>
                    <span>
                      <strong className="text-slate-800">Sign up</strong> with <code className="font-mono">organization_id</code>,{' '}
                      <code className="font-mono">email</code>, <code className="font-mono">password</code> (8+ chars) and{' '}
                      <code className="font-mono">display_name</code>. The email must match the customer&apos;s billing
                      email or one of its contacts — that is how the login is linked to the right account.
                      {!form.allow_self_signup && (
                        <span className="block mt-1 text-amber-700 font-medium">
                          Self sign-up is currently off, so this call will be rejected.
                        </span>
                      )}
                    </span>
                  </li>
                  <li className="flex gap-2">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-brand-50 text-brand-700 text-[11px] font-semibold flex items-center justify-center">2</span>
                    <span>
                      <strong className="text-slate-800">Sign in</strong> to receive a session token valid for 7 days.
                      {form.mfa_enabled && ' An MFA code is also required.'}
                    </span>
                  </li>
                  <li className="flex gap-2">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-brand-50 text-brand-700 text-[11px] font-semibold flex items-center justify-center">3</span>
                    <span>
                      Send the token on every request as the <code className="font-mono">X-Portal-Token</code> header
                      (or a Bearer token) to <code className="font-mono">/api/v1/portal/*</code>.
                    </span>
                  </li>
                </ol>

                {form.portal_url_slug && (
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    Slug <code className="font-mono text-slate-500">{form.portal_url_slug}</code> is saved with these
                    settings and reserved for the hosted portal address when it ships.
                  </p>
                )}
              </div>
            </SectionCard>

            <SectionCard
              icon={<Sparkles className="w-4 h-4" />}
              title="What customers see"
              description={dirty ? 'Preview reflects your unsaved changes.' : 'Read-only preview of portal capabilities.'}
            >
              <div className="py-5 space-y-4">
                {/* Mini dashboard frame */}
                <div className="rounded-lg border border-slate-200 overflow-hidden">
                  <div className="px-3 py-2 bg-slate-900 text-white flex items-center gap-2">
                    <LayoutDashboard className="w-3.5 h-3.5 text-slate-300" />
                    <span className="text-xs font-semibold truncate">{form.portal_name || 'Customer Billing Portal'}</span>
                  </div>
                  {form.banner_message ? (
                    <div className="px-3 py-2 bg-amber-50 border-b border-amber-100 text-[11px] text-amber-800 leading-relaxed">
                      {form.banner_message}
                    </div>
                  ) : (
                    <div className="px-3 py-2 bg-slate-50 border-b border-slate-100 text-[11px] text-slate-400 italic">
                      No banner message
                    </div>
                  )}
                  <div className="px-3 py-3 grid grid-cols-3 gap-2 text-center">
                    {['Open invoices', 'Outstanding', 'Active plans'].map((lbl) => (
                      <div key={lbl} className="rounded-md bg-slate-50 border border-slate-100 px-2 py-2">
                        <p className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">{lbl}</p>
                        <div className="mt-1 h-3 w-10 mx-auto rounded bg-slate-200" />
                      </div>
                    ))}
                  </div>
                </div>

                <ul className="space-y-2.5">
                  <PreviewItem icon={<FileText className="w-3.5 h-3.5" />} title="Invoices & PDF downloads" chip={<StatusChip on onLabel="Always on" />}>
                    Full invoice history with status and balance, direct PDF download, and signed download links
                    that expire after 5 minutes.
                  </PreviewItem>
                  <PreviewItem icon={<Repeat className="w-3.5 h-3.5" />} title="Subscriptions" chip={<StatusChip on onLabel="Always on" />}>
                    Plan, quantity, status, current billing period and trial end date for every subscription.
                  </PreviewItem>
                  <PreviewItem
                    icon={<Wallet className="w-3.5 h-3.5" />}
                    title="Saved payment methods"
                    chip={<StatusChip on={form.allow_save_payment_methods} />}
                  >
                    Cards vaulted during hosted checkout, with brand, last four digits and default marker.
                  </PreviewItem>
                  <PreviewItem
                    icon={<Clock className="w-3.5 h-3.5" />}
                    title="Extend trial"
                    chip={<StatusChip on={form.trials_allow_customer_extension} />}
                  >
                    Self-service extension of a trialing subscription
                    {form.trials_allow_customer_extension
                      ? `, up to ${form.trials_max_extensions} time${form.trials_max_extensions === 1 ? '' : 's'}.`
                      : '.'}
                  </PreviewItem>
                  <PreviewItem
                    icon={<Check className="w-3.5 h-3.5" />}
                    title="Convert trial early"
                    chip={<StatusChip on={form.trials_activate_immediately} onLabel="Immediate" offLabel="At period end" />}
                  >
                    Customers can end a trial and start paying now; the first invoice is raised and charged.
                  </PreviewItem>
                </ul>

                <p className="text-[11px] text-slate-400">
                  Last updated {formatDateTime(settings.updated_at)}
                </p>
              </div>
            </SectionCard>
          </div>
        </form>
      ) : null}
    </div>
  );
}

function PreviewItem({
  icon,
  title,
  chip,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  chip: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <li className="flex items-start gap-3">
      <div className="mt-0.5 p-1.5 rounded-md bg-slate-100 text-slate-500 shrink-0">{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold text-slate-800">{title}</p>
          {chip}
        </div>
        <p className="text-[11px] text-slate-500 leading-relaxed mt-0.5">{children}</p>
      </div>
    </li>
  );
}
