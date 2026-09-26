import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  HeartHandshake,
  RefreshCw,
  Plus,
  Copy,
  ExternalLink,
  Link2,
  CheckCircle2,
  Clock,
  XCircle,
  LayoutTemplate,
  Palette,
  Star,
  Info,
} from 'lucide-react';
import { checkoutService } from '../../services/checkoutService';
import { customerService } from '../../services/customerService';
import { invoiceService } from '../../services/invoiceService';
import { catalogService } from '../../services/catalogService';
import { subscriptionService } from '../../services/subscriptionService';
import type { CustomerOut, PlanOut, SubscriptionOut } from '../../types/api';
import type { Invoice } from '../../types/invoices';
import type {
  CheckoutPurpose,
  CheckoutSession,
  CheckoutSessionCreate,
  CheckoutSessionStatus,
  CheckoutTemplate,
  CheckoutTemplateCreate,
  CheckoutTemplateType,
} from '../../types/checkout';
import { CHECKOUT_PURPOSES, CHECKOUT_STATUSES } from '../../types/checkout';
import { Button } from '../../components/common/Button';
import { Badge, type BadgeProps } from '../../components/common/Badge';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { StatCard } from '../../components/common/StatCard';
import { DataTable, type Column } from '../../components/common/DataTable';
import { Modal } from '../../components/common/Modal';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime, formatMoney, formatRelative, humanize } from '../../utils/format';
import { cn } from '../../utils/cn';

// ---------------------------------------------------------------------------
// Constants & helpers
// ---------------------------------------------------------------------------

const PAGE_SIZE = 20;

const PURPOSE_LABELS: Record<CheckoutPurpose, string> = {
  invoice_payment: 'Invoice payment',
  new_subscription: 'New subscription',
  update_subscription: 'Change subscription plan',
  update_card: 'Update card',
  one_time_addon: 'One-time add-on',
  add_payment_method: 'Add payment method',
};

const STATUS_BADGE: Record<CheckoutSessionStatus, NonNullable<BadgeProps['variant']>> = {
  created: 'neutral',
  pending: 'info',
  processing: 'warning',
  successful: 'success',
  failed: 'danger',
  cancelled: 'neutral',
  expired: 'neutral',
};

/** Backend timestamps are naive UTC (no `Z`); make Date parse them as UTC. */
function utc(ts: string | null | undefined): string | null {
  if (!ts) return null;
  return /(Z|[+-]\d{2}:\d{2})$/.test(ts) ? ts : `${ts}Z`;
}

function purposeLabel(p: string): string {
  return (PURPOSE_LABELS as Record<string, string>)[p] ?? humanize(p);
}

function shortRef(token: string): string {
  return token.length > 14 ? `${token.slice(0, 8)}…${token.slice(-4)}` : token;
}

type Tab = 'sessions' | 'templates';

/**
 * Purposes a hosted link can actually settle. Plan changes go through the subscription's
 * change flow (proration + invoice), and cards are saved while paying an invoice checkout,
 * so the server rejects those purposes at creation.
 */
const CREATABLE_PURPOSES: CheckoutPurpose[] = CHECKOUT_PURPOSES.filter(
  (p) => p !== 'update_subscription' && p !== 'update_card' && p !== 'add_payment_method'
);

const NEW_SESSION_DEFAULTS: CheckoutSessionCreate = {
  purpose: 'invoice_payment',
  template_id: null,
  customer_id: null,
  invoice_id: null,
  subscription_id: null,
  plan_id: null,
  amount: null,
  currency: 'INR',
  expires_in_hours: 24,
  save_payment_method: false,
};

/**
 * Local form state for the template modal. The API type allows `null` for the
 * optional text fields, but controlled inputs need real strings — empty string
 * means "unset" here and is converted back to `null` on submit.
 */
type TemplateFormState = {
  [K in keyof Required<Omit<CheckoutTemplateCreate, 'custom_fields'>>]: NonNullable<
    Required<Omit<CheckoutTemplateCreate, 'custom_fields'>>[K]
  >;
};

const NEW_TEMPLATE_DEFAULTS: TemplateFormState = {
  name: '',
  template_type: 'single_page',
  primary_color: '#2563eb',
  accent_color: '#1e40af',
  logo_url: '',
  button_text: 'Pay Now',
  allow_quantity_edit: false,
  show_order_summary: true,
  redirect_url: '',
  thank_you_message: '',
  error_message_template: '',
  is_default: false,
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function HostedPaymentPagesPage() {
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canWrite = hasRole('finance');

  const [tab, setTab] = useState<Tab>('sessions');

  // Sessions
  const [sessions, setSessions] = useState<CheckoutSession[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionsError, setSessionsError] = useState<string | null>(null);

  // Stats (from status-filtered totals — the list endpoint is paginated)
  const [counts, setCounts] = useState<Record<CheckoutSessionStatus, number> | null>(null);

  // Templates
  const [templates, setTemplates] = useState<CheckoutTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

  // Customer name lookup (sessions only carry customer_id)
  const [customers, setCustomers] = useState<CustomerOut[]>([]);
  const customerName = useMemo(() => {
    const m = new Map<string, string>();
    customers.forEach((c) => m.set(c.id, c.display_name));
    return m;
  }, [customers]);

  // Modals
  const [sessionModalOpen, setSessionModalOpen] = useState(false);
  const [templateModalOpen, setTemplateModalOpen] = useState(false);

  const copy = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      showToast('success', `${label} copied to clipboard`);
    } catch {
      showToast('error', 'Clipboard unavailable', 'Select the text and copy it manually.');
    }
  };

  // --- Loaders --------------------------------------------------------------

  const loadSessions = useCallback(async () => {
    try {
      setSessionsLoading(true);
      setSessionsError(null);
      const data = await checkoutService.listSessions({
        status: statusFilter !== 'all' ? statusFilter : undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setSessions(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setSessionsError(err.message || 'Failed to load checkout sessions');
    } finally {
      setSessionsLoading(false);
    }
  }, [statusFilter, page]);

  const loadCounts = useCallback(async () => {
    try {
      const results = await Promise.all(
        CHECKOUT_STATUSES.map((s) => checkoutService.listSessions({ status: s, page: 1, page_size: 1 }))
      );
      const next = {} as Record<CheckoutSessionStatus, number>;
      CHECKOUT_STATUSES.forEach((s, i) => {
        next[s] = results[i].total;
      });
      setCounts(next);
    } catch {
      // Stats are secondary; the table surfaces the real error.
      setCounts(null);
    }
  }, []);

  const loadTemplates = useCallback(async () => {
    try {
      setTemplatesLoading(true);
      setTemplatesError(null);
      setTemplates(await checkoutService.listTemplates());
    } catch (err: any) {
      setTemplatesError(err.message || 'Failed to load checkout templates');
    } finally {
      setTemplatesLoading(false);
    }
  }, []);

  const loadCustomers = useCallback(async () => {
    try {
      const data = await customerService.list({ page: 1, page_size: 100 });
      setCustomers(data.items);
    } catch {
      // Names are a nicety; fall back to ids.
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    loadCounts();
    loadTemplates();
    loadCustomers();
  }, [loadCounts, loadTemplates, loadCustomers]);

  const refreshAll = () => {
    loadSessions();
    loadCounts();
    loadTemplates();
  };

  const totalSessions = counts ? CHECKOUT_STATUSES.reduce((sum, s) => sum + counts[s], 0) : total;
  const awaiting = counts ? counts.created + counts.pending + counts.processing : 0;
  const successful = counts ? counts.successful : 0;
  const closed = counts ? counts.failed + counts.cancelled + counts.expired : 0;

  // --- Table -----------------------------------------------------------------

  const columns: Column<CheckoutSession>[] = [
    {
      key: 'ref',
      title: 'Reference',
      render: (s) => (
        <div>
          <div className="font-mono text-xs font-semibold text-slate-900">{shortRef(s.token)}</div>
          <div className="text-xs text-slate-500 mt-0.5">{purposeLabel(s.purpose)}</div>
        </div>
      ),
    },
    {
      key: 'customer',
      title: 'Customer',
      render: (s) =>
        s.customer_id ? (
          <span className="text-slate-800">{customerName.get(s.customer_id) ?? shortRef(s.customer_id)}</span>
        ) : (
          <span className="text-slate-400 italic">Not linked</span>
        ),
    },
    {
      key: 'amount',
      title: 'Amount',
      align: 'right',
      render: (s) =>
        Number(s.amount) > 0 ? (
          <span className="font-medium text-slate-900">{formatMoney(s.amount, s.currency)}</span>
        ) : (
          <span className="text-slate-400">No charge</span>
        ),
    },
    {
      key: 'status',
      title: 'Status',
      render: (s) => (
        <Badge variant={STATUS_BADGE[s.status as CheckoutSessionStatus] ?? 'neutral'} dot>
          {humanize(s.status)}
        </Badge>
      ),
    },
    {
      key: 'expires',
      title: 'Expires',
      render: (s) => {
        const iso = utc(s.expires_at);
        const past = iso ? new Date(iso).getTime() < Date.now() : false;
        return (
          <div>
            <div className={cn('text-xs font-medium', past ? 'text-slate-400' : 'text-slate-800')}>
              {formatRelative(iso)}
            </div>
            <div className="text-[11px] text-slate-400">{formatDateTime(iso)}</div>
          </div>
        );
      },
    },
    {
      key: 'created',
      title: 'Created',
      render: (s) => <span className="text-xs text-slate-600">{formatDateTime(utc(s.created_at))}</span>,
    },
    {
      key: 'actions',
      title: 'Actions',
      align: 'right',
      render: (s) => {
        // The raw token only exists in the create response; listings carry a
        // display reference, so there is no link to copy after the fact.
        if (!s.checkout_url) {
          return <span className="text-[11px] text-slate-400">Link shown once at creation</span>;
        }
        const url = checkoutService.publicUrl(s.token);
        return (
          <div className="flex items-center justify-end gap-1.5">
            <Button
              variant="ghost"
              size="sm"
              className="text-xs"
              onClick={() => copy('Checkout link', url)}
              leadingIcon={<Copy className="w-3.5 h-3.5" />}
            >
              Copy link
            </Button>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Open
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        );
      },
    },
  ];

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
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Hosted Payment Pages</h1>
          <p className="text-sm text-slate-500 mt-1">
            Generate secure, expiring checkout links for invoices, subscriptions and card capture — branded with
            your own templates.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={refreshAll}
            leadingIcon={<RefreshCw className="w-4 h-4" />}
          >
            Refresh
          </Button>
          {canWrite && tab === 'sessions' && (
            <Button variant="primary" size="sm" onClick={() => setSessionModalOpen(true)} leadingIcon={<Plus className="w-4 h-4" />}>
              New checkout session
            </Button>
          )}
          {canWrite && tab === 'templates' && (
            <Button variant="primary" size="sm" onClick={() => setTemplateModalOpen(true)} leadingIcon={<Plus className="w-4 h-4" />}>
              New template
            </Button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total sessions" value={totalSessions} icon={<Link2 className="w-4 h-4" />} />
        <StatCard title="Awaiting payment" value={awaiting} icon={<Clock className="w-4 h-4" />} />
        <StatCard title="Successful" value={successful} icon={<CheckCircle2 className="w-4 h-4" />} />
        <StatCard title="Failed / expired" value={closed} icon={<XCircle className="w-4 h-4" />} />
      </div>

      {/* Tabs + filters */}
      <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <nav className="flex items-center gap-1" aria-label="Sections">
          {(
            [
              { key: 'sessions', label: 'Sessions', icon: Link2, count: totalSessions },
              { key: 'templates', label: 'Templates', icon: LayoutTemplate, count: templates.length },
            ] as { key: Tab; label: string; icon: typeof Link2; count: number }[]
          ).map((t) => {
            const Icon = t.icon;
            const active = tab === t.key;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                  active ? 'bg-brand-50 text-brand-700 font-semibold' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                )}
              >
                <Icon className={cn('w-4 h-4', active ? 'text-brand-600' : 'text-slate-400')} />
                {t.label}
                <span className={cn('ml-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-semibold', active ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-500')}>
                  {t.count}
                </span>
              </button>
            );
          })}
        </nav>
        {tab === 'sessions' && (
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All statuses</option>
            {CHECKOUT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Sessions tab */}
      {tab === 'sessions' &&
        (sessionsError ? (
          <ErrorState title="Couldn't load checkout sessions" message={sessionsError} onRetry={loadSessions} />
        ) : !sessionsLoading && sessions.length === 0 && statusFilter === 'all' ? (
          <EmptyState
            icon={<Link2 className="w-6 h-6 stroke-1" />}
            title="No checkout sessions yet"
            description="Create a hosted checkout link to let a customer pay an invoice, start a subscription or save a card without signing in."
            action={
              canWrite ? (
                <Button variant="primary" size="sm" onClick={() => setSessionModalOpen(true)} leadingIcon={<Plus className="w-4 h-4" />}>
                  New checkout session
                </Button>
              ) : undefined
            }
          />
        ) : (
          <DataTable<CheckoutSession>
            columns={columns}
            data={sessions}
            keyExtractor={(s) => s.id}
            isLoading={sessionsLoading}
            emptyMessage={`No ${statusFilter === 'all' ? '' : humanize(statusFilter).toLowerCase() + ' '}sessions`}
            emptySubtext="Try a different status filter."
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onPageChange={setPage}
          />
        ))}

      {/* Templates tab */}
      {tab === 'templates' &&
        (templatesLoading ? (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm py-16">
            <LoadingState message="Loading templates..." />
          </div>
        ) : templatesError ? (
          <ErrorState title="Couldn't load templates" message={templatesError} onRetry={loadTemplates} />
        ) : templates.length === 0 ? (
          <EmptyState
            icon={<LayoutTemplate className="w-6 h-6 stroke-1" />}
            title="No checkout templates"
            description="Templates control the colours, logo, button text and redirect of your hosted pages. A “Standard Checkout” default is created automatically the first time a session is generated without one."
            action={
              canWrite ? (
                <Button variant="primary" size="sm" onClick={() => setTemplateModalOpen(true)} leadingIcon={<Plus className="w-4 h-4" />}>
                  New template
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {templates.map((t) => (
              <TemplateCard key={t.id} template={t} />
            ))}
          </div>
        ))}

      {/* Modals */}
      {sessionModalOpen && (
        <NewSessionModal
          templates={templates}
          customers={customers}
          onClose={() => setSessionModalOpen(false)}
          onCreated={() => {
            loadSessions();
            loadCounts();
          }}
        />
      )}
      {templateModalOpen && (
        <NewTemplateModal
          onClose={() => setTemplateModalOpen(false)}
          onCreated={(t) => {
            setTemplates((prev) => [t, ...prev.map((p) => (t.is_default ? { ...p, is_default: false } : p))]);
            setTemplateModalOpen(false);
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Template card
// ---------------------------------------------------------------------------

function TemplateCard({ template: t }: { template: CheckoutTemplate }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
      <div className="h-2" style={{ background: `linear-gradient(90deg, ${t.primary_color}, ${t.accent_color})` }} />
      <div className="p-4 flex-1 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-slate-900 truncate">{t.name}</h3>
              {t.is_default && (
                <Badge variant="primary" size="sm">
                  <Star className="w-3 h-3 mr-1" />
                  Default
                </Badge>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">{humanize(t.template_type)}</p>
          </div>
          <Badge variant={t.is_active ? 'success' : 'neutral'} size="sm">
            {t.is_active ? 'Active' : 'Inactive'}
          </Badge>
        </div>

        <div className="flex items-center gap-3 text-xs text-slate-600">
          <span className="inline-flex items-center gap-1.5">
            <span className="w-4 h-4 rounded-full border border-slate-200" style={{ backgroundColor: t.primary_color }} />
            <code className="font-mono">{t.primary_color}</code>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-4 h-4 rounded-full border border-slate-200" style={{ backgroundColor: t.accent_color }} />
            <code className="font-mono">{t.accent_color}</code>
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <div>
            <dt className="text-slate-400">Button</dt>
            <dd className="text-slate-800 font-medium truncate">{t.button_text}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Order summary</dt>
            <dd className="text-slate-800 font-medium">{t.show_order_summary ? 'Shown' : 'Hidden'}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Quantity edit</dt>
            <dd className="text-slate-800 font-medium">{t.allow_quantity_edit ? 'Allowed' : 'Locked'}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Logo</dt>
            <dd className="text-slate-800 font-medium truncate">{t.logo_url ? 'Custom' : 'None'}</dd>
          </div>
        </dl>

        {t.redirect_url && (
          <p className="text-[11px] text-slate-500 truncate">
            <span className="text-slate-400">After payment → </span>
            <span className="font-mono">{t.redirect_url}</span>
          </p>
        )}
        {t.thank_you_message && (
          <p className="text-[11px] text-slate-500 italic line-clamp-2">“{t.thank_you_message}”</p>
        )}
      </div>
      <div className="px-4 py-2.5 border-t border-slate-100 text-[11px] text-slate-400">
        Created {formatDateTime(utc(t.created_at))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// New session modal
// ---------------------------------------------------------------------------

function needsCustomerPicker(p: CheckoutPurpose): boolean {
  return p === 'new_subscription' || p === 'update_card' || p === 'add_payment_method' || p === 'one_time_addon';
}

function NewSessionModal({
  templates,
  customers,
  onClose,
  onCreated,
}: {
  templates: CheckoutTemplate[];
  customers: CustomerOut[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const { showToast } = useToast();
  const [form, setForm] = useState<CheckoutSessionCreate>(NEW_SESSION_DEFAULTS);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<CheckoutSession | null>(null);

  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [plans, setPlans] = useState<PlanOut[] | null>(null);
  const [subs, setSubs] = useState<SubscriptionOut[] | null>(null);
  const [pickerError, setPickerError] = useState<string | null>(null);

  const purpose = form.purpose;

  // Lazy-load reference data for the selected purpose.
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        setPickerError(null);
        if (purpose === 'invoice_payment' && invoices === null) {
          const res = await invoiceService.list({ page: 1, page_size: 100, sort: '-issue_date' });
          if (!cancelled)
            setInvoices(res.items.filter((i) => i.status !== 'paid' && i.status !== 'void' && Number(i.amount_due) > 0));
        }
        if ((purpose === 'new_subscription' || purpose === 'update_subscription') && plans === null) {
          const res = await catalogService.listPlans({ page: 1, page_size: 100, is_active: true });
          if (!cancelled) setPlans(res.items);
        }
        if (purpose === 'update_subscription' && subs === null) {
          const res = await subscriptionService.list({ page: 1, page_size: 100 });
          if (!cancelled) setSubs(res.items);
        }
      } catch (err: any) {
        if (!cancelled) setPickerError(err.message || 'Failed to load options');
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [purpose, invoices, plans, subs]);

  const set = <K extends keyof CheckoutSessionCreate>(key: K, value: CheckoutSessionCreate[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const changePurpose = (p: CheckoutPurpose) => {
    setForm((prev) => ({
      ...NEW_SESSION_DEFAULTS,
      purpose: p,
      template_id: prev.template_id,
      expires_in_hours: prev.expires_in_hours,
      currency: prev.currency,
    }));
    setErrors({});
  };

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (purpose === 'invoice_payment' && !form.invoice_id) errs.invoice_id = 'Choose an invoice with an outstanding balance.';
    if (purpose === 'new_subscription' && !form.plan_id) errs.plan_id = 'Choose a plan.';
    if (purpose === 'update_subscription' && !form.subscription_id) errs.subscription_id = 'Choose a subscription.';
    if (needsCustomerPicker(purpose) && !form.customer_id) errs.customer_id = 'Choose a customer.';
    if (purpose === 'one_time_addon' && !(Number(form.amount) > 0)) errs.amount = 'Enter an amount greater than 0.';
    const hrs = Number(form.expires_in_hours);
    if (!Number.isInteger(hrs) || hrs < 1 || hrs > 168) errs.expires_in_hours = 'Between 1 and 168 hours.';
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    try {
      setSubmitting(true);
      const body: CheckoutSessionCreate = {
        purpose,
        template_id: form.template_id || null,
        expires_in_hours: Number(form.expires_in_hours),
        save_payment_method: !!form.save_payment_method,
        currency: form.currency || 'INR',
      };
      if (purpose === 'invoice_payment') body.invoice_id = form.invoice_id;
      if (purpose === 'new_subscription') {
        body.plan_id = form.plan_id;
        body.customer_id = form.customer_id;
      }
      if (purpose === 'update_subscription') {
        body.subscription_id = form.subscription_id;
        if (form.plan_id) body.plan_id = form.plan_id;
      }
      if (purpose === 'update_card' || purpose === 'add_payment_method') body.customer_id = form.customer_id;
      if (purpose === 'one_time_addon') {
        body.customer_id = form.customer_id;
        body.amount = Number(form.amount).toFixed(2);
      }
      const session = await checkoutService.createSession(body);
      setCreated(session);
      showToast('success', 'Checkout session created', 'Share the link before it expires.');
      onCreated();
    } catch (err: any) {
      const fields = err?.details?.fields;
      if (fields && typeof fields === 'object') setErrors(fields);
      showToast('error', err.message || 'Failed to create checkout session');
    } finally {
      setSubmitting(false);
    }
  };

  const copyLink = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      showToast('success', 'Checkout link copied to clipboard');
    } catch {
      showToast('error', 'Clipboard unavailable', 'Select the link and copy it manually.');
    }
  };

  const customerOptions = customers.map((c) => ({
    value: c.id,
    label: `${c.display_name} · ${c.customer_number}`,
  }));

  // --- Success view ------------------------------------------------------------
  if (created) {
    const url = checkoutService.publicUrl(created.token);
    return (
      <Modal isOpen onClose={onClose} title="Checkout link ready" size="md">
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            <div className="text-xs text-emerald-900 leading-relaxed">
              <p className="font-semibold">{purposeLabel(created.purpose)} session created.</p>
              <p className="mt-0.5">
                Expires {formatRelative(utc(created.expires_at))} ({formatDateTime(utc(created.expires_at))}).
                {Number(created.amount) > 0 && <> Amount due: <strong>{formatMoney(created.amount, created.currency)}</strong>.</>}
              </p>
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">Shareable link</p>
            <div className="flex items-center gap-2">
              <input
                readOnly
                value={url}
                onFocus={(e) => e.currentTarget.select()}
                className="flex-1 min-w-0 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-xs font-mono text-slate-800"
              />
              <Button variant="outline" size="sm" onClick={() => copyLink(url)} leadingIcon={<Copy className="w-3.5 h-3.5" />}>
                Copy
              </Button>
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-lg bg-brand-600 px-3 py-2 text-xs font-semibold text-white hover:bg-brand-700 transition-colors"
              >
                Open
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
            <p className="mt-2 text-[11px] text-slate-500 leading-relaxed flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 shrink-0 mt-px" />
              Copy this link now; it is shown only once. The sessions table shows a reference, not the link.
              If it is lost, create a new session.
            </p>
          </div>

          <div className="flex justify-end pt-2 border-t border-slate-200">
            <Button variant="primary" size="sm" onClick={onClose}>
              Done
            </Button>
          </div>
        </div>
      </Modal>
    );
  }

  // --- Form view ---------------------------------------------------------------
  return (
    <Modal
      isOpen
      onClose={onClose}
      title="New checkout session"
      description="Generates a one-off, expiring link the customer can open without signing in."
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <Select
          label="Purpose"
          required
          value={purpose}
          onChange={(e) => changePurpose(e.target.value as CheckoutPurpose)}
          options={CREATABLE_PURPOSES.map((p) => ({ value: p, label: PURPOSE_LABELS[p] }))}
        />

        {pickerError && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{pickerError}</div>
        )}

        {purpose === 'invoice_payment' && (
          <Select
            label="Invoice"
            required
            value={form.invoice_id ?? ''}
            onChange={(e) => set('invoice_id', e.target.value || null)}
            error={errors.invoice_id}
            placeholder={invoices === null ? 'Loading invoices…' : invoices.length === 0 ? 'No invoices with a balance due' : 'Select an invoice'}
            disabled={invoices === null || invoices.length === 0}
            options={(invoices ?? []).map((i) => ({
              value: i.id,
              label: `${i.invoice_number} · ${i.customer?.display_name ?? ''} · ${formatMoney(i.amount_due, i.currency)} due`,
            }))}
            helperText="Amount, currency and customer are taken from the invoice."
          />
        )}

        {needsCustomerPicker(purpose) && (
          <Select
            label="Customer"
            required
            value={form.customer_id ?? ''}
            onChange={(e) => set('customer_id', e.target.value || null)}
            error={errors.customer_id}
            placeholder={customers.length === 0 ? 'No customers found' : 'Select a customer'}
            disabled={customers.length === 0}
            options={customerOptions}
          />
        )}

        {(purpose === 'new_subscription' || purpose === 'update_subscription') && (
          <Select
            label={purpose === 'new_subscription' ? 'Plan' : 'New plan (optional)'}
            required={purpose === 'new_subscription'}
            value={form.plan_id ?? ''}
            onChange={(e) => set('plan_id', e.target.value || null)}
            error={errors.plan_id}
            placeholder={plans === null ? 'Loading plans…' : plans.length === 0 ? 'No active plans' : purpose === 'new_subscription' ? 'Select a plan' : 'Keep current plan'}
            disabled={plans === null || plans.length === 0}
            options={(plans ?? []).map((p) => ({
              value: p.id,
              label: `${p.name} · ${formatMoney(p.unit_amount, p.currency)} / ${humanize(p.billing_interval).toLowerCase()}${p.trial_days ? ` · ${p.trial_days}-day trial` : ''}`,
            }))}
            helperText={purpose === 'new_subscription' ? 'The plan price sets the amount charged.' : undefined}
          />
        )}

        {purpose === 'update_subscription' && (
          <Select
            label="Subscription"
            required
            value={form.subscription_id ?? ''}
            onChange={(e) => set('subscription_id', e.target.value || null)}
            error={errors.subscription_id}
            placeholder={subs === null ? 'Loading subscriptions…' : subs.length === 0 ? 'No subscriptions found' : 'Select a subscription'}
            disabled={subs === null || subs.length === 0}
            options={(subs ?? []).map((s) => ({
              value: s.id,
              label: `${s.subscription_number} · ${s.customer.display_name} · ${s.plan.name} (${humanize(s.status)})`,
            }))}
          />
        )}

        {purpose === 'one_time_addon' && (
          <div className="grid grid-cols-3 gap-4">
            <div className="col-span-2">
              <Input
                label="Amount"
                required
                type="number"
                min={0.01}
                step={0.01}
                inputMode="decimal"
                value={form.amount ?? ''}
                onChange={(e) => set('amount', e.target.value || null)}
                error={errors.amount}
                placeholder="0.00"
              />
            </div>
            <Input
              label="Currency"
              maxLength={3}
              value={form.currency ?? 'INR'}
              onChange={(e) => set('currency', e.target.value.toUpperCase())}
            />
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select
            label="Template"
            value={form.template_id ?? ''}
            onChange={(e) => set('template_id', e.target.value || null)}
            options={[
              { value: '', label: templates.length ? 'Organization default' : 'Standard Checkout (auto-created)' },
              ...templates.map((t) => ({ value: t.id, label: `${t.name}${t.is_default ? ' (default)' : ''}` })),
            ]}
            helperText="Controls colours, logo, button text and redirect."
          />
          <Input
            label="Link valid for (hours)"
            required
            type="number"
            min={1}
            max={168}
            step={1}
            value={form.expires_in_hours ?? 24}
            onChange={(e) => set('expires_in_hours', Number(e.target.value))}
            error={errors.expires_in_hours}
            helperText="1–168 hours (7 days max)."
          />
        </div>

        <label className="flex items-start gap-2.5 rounded-lg border border-slate-200 px-3 py-2.5 cursor-pointer hover:bg-slate-50">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            checked={!!form.save_payment_method}
            onChange={(e) => set('save_payment_method', e.target.checked)}
          />
          <span className="text-xs text-slate-700 leading-relaxed">
            <span className="font-medium text-slate-900">Save the payment method</span> to the customer&apos;s
            account after a successful payment. Required for card-update and add-payment-method purposes to have
            any effect.
          </span>
        </label>

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
          <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" size="sm" disabled={submitting} isLoading={submitting}>
            Create link
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// New template modal
// ---------------------------------------------------------------------------

function NewTemplateModal({ onClose, onCreated }: { onClose: () => void; onCreated: (t: CheckoutTemplate) => void }) {
  const { showToast } = useToast();
  const [form, setForm] = useState(NEW_TEMPLATE_DEFAULTS);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const set = <K extends keyof typeof NEW_TEMPLATE_DEFAULTS>(key: K, value: (typeof NEW_TEMPLATE_DEFAULTS)[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const isHex = (v: string) => /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(v);
  const isHttpUrl = (v: string) => /^https?:\/\//i.test(v);

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!form.name.trim()) errs.name = 'Name is required.';
    else if (form.name.length > 100) errs.name = 'Maximum 100 characters.';
    if (!isHex(form.primary_color)) errs.primary_color = 'Use a hex colour like #2563eb.';
    if (!isHex(form.accent_color)) errs.accent_color = 'Use a hex colour like #1e40af.';
    if (!form.button_text.trim()) errs.button_text = 'Button text is required.';
    else if (form.button_text.length > 50) errs.button_text = 'Maximum 50 characters.';
    if (form.logo_url && !isHttpUrl(form.logo_url)) errs.logo_url = 'Must start with http:// or https://';
    if (form.redirect_url && !isHttpUrl(form.redirect_url)) errs.redirect_url = 'Must start with http:// or https://';
    if (form.error_message_template.length > 255) errs.error_message_template = 'Maximum 255 characters.';
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    try {
      setSubmitting(true);
      const body: CheckoutTemplateCreate = {
        name: form.name.trim(),
        template_type: form.template_type,
        primary_color: form.primary_color,
        accent_color: form.accent_color,
        logo_url: form.logo_url.trim() || null,
        button_text: form.button_text.trim(),
        allow_quantity_edit: form.allow_quantity_edit,
        show_order_summary: form.show_order_summary,
        redirect_url: form.redirect_url.trim() || null,
        thank_you_message: form.thank_you_message.trim() || null,
        error_message_template: form.error_message_template.trim() || null,
        is_default: form.is_default,
      };
      const created = await checkoutService.createTemplate(body);
      showToast('success', 'Template created', `“${created.name}” is ready to use on new sessions.`);
      onCreated(created);
    } catch (err: any) {
      const fields = err?.details?.fields;
      if (fields && typeof fields === 'object') setErrors(fields);
      showToast('error', err.message || 'Failed to create template');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen
      onClose={onClose}
      title="New checkout template"
      description="Branding and behaviour applied to hosted payment pages that use this template."
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="Template name"
            required
            maxLength={100}
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            error={errors.name}
            placeholder="e.g. Invoice payments"
          />
          <Select
            label="Layout"
            value={form.template_type}
            onChange={(e) => set('template_type', e.target.value as CheckoutTemplateType)}
            options={[
              { value: 'single_page', label: 'Single page' },
              { value: 'multi_page', label: 'Multi-step' },
            ]}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <ColorField label="Primary colour" value={form.primary_color} error={errors.primary_color} onChange={(v) => set('primary_color', v)} />
          <ColorField label="Accent colour" value={form.accent_color} error={errors.accent_color} onChange={(v) => set('accent_color', v)} />
        </div>

        {/* Live preview strip */}
        <div className="rounded-lg border border-slate-200 overflow-hidden">
          <div className="h-1.5" style={{ background: `linear-gradient(90deg, ${form.primary_color}, ${form.accent_color})` }} />
          <div className="px-3 py-2.5 flex items-center justify-between gap-3 bg-slate-50">
            <div className="flex items-center gap-2 min-w-0">
              <Palette className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <span className="text-xs text-slate-500 truncate">Button preview</span>
            </div>
            <span
              className="inline-flex items-center rounded-lg px-3 py-1.5 text-xs font-semibold text-white shadow-sm"
              style={{ backgroundColor: isHex(form.primary_color) ? form.primary_color : '#2563eb' }}
            >
              {form.button_text || 'Pay Now'}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="Button text"
            required
            maxLength={50}
            value={form.button_text}
            onChange={(e) => set('button_text', e.target.value)}
            error={errors.button_text}
          />
          <Input
            label="Logo URL"
            type="url"
            maxLength={500}
            value={form.logo_url}
            onChange={(e) => set('logo_url', e.target.value)}
            error={errors.logo_url}
            placeholder="https://…/logo.png"
          />
        </div>

        <Input
          label="Redirect URL after success"
          type="url"
          maxLength={500}
          value={form.redirect_url}
          onChange={(e) => set('redirect_url', e.target.value)}
          error={errors.redirect_url}
          placeholder="https://yourcompany.com/thank-you"
          helperText="Optional. Only http(s) destinations are accepted by the server."
        />

        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1.5">Thank-you message</label>
          <textarea
            rows={2}
            value={form.thank_you_message}
            onChange={(e) => set('thank_you_message', e.target.value)}
            placeholder="Shown on the confirmation screen after a successful payment."
            className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
          />
        </div>

        <Input
          label="Error message"
          maxLength={255}
          value={form.error_message_template}
          onChange={(e) => set('error_message_template', e.target.value)}
          error={errors.error_message_template}
          placeholder="Shown if a payment fails. Leave blank for the default."
        />

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <CheckboxField label="Show order summary" checked={form.show_order_summary} onChange={(v) => set('show_order_summary', v)} />
          <CheckboxField label="Allow quantity edit" checked={form.allow_quantity_edit} onChange={(v) => set('allow_quantity_edit', v)} />
          <CheckboxField label="Make default template" checked={form.is_default} onChange={(v) => set('is_default', v)} />
        </div>

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
          <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" size="sm" disabled={submitting} isLoading={submitting}>
            Create template
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function ColorField({
  label,
  value,
  error,
  onChange,
}: {
  label: string;
  value: string;
  error?: string;
  onChange: (v: string) => void;
}) {
  const valid = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(value);
  return (
    <div className="w-full">
      <label className="block text-xs font-medium text-slate-700 mb-1.5">{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          aria-label={`${label} picker`}
          value={valid ? value : '#000000'}
          onChange={(e) => onChange(e.target.value)}
          className="h-9 w-10 rounded-lg border border-slate-300 bg-white p-0.5 cursor-pointer"
        />
        <input
          type="text"
          value={value}
          maxLength={20}
          onChange={(e) => onChange(e.target.value)}
          className={cn(
            'block w-full rounded-lg border bg-white px-3 py-2 text-sm font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
            error ? 'border-rose-300' : 'border-slate-300'
          )}
        />
      </div>
      {error && <p className="mt-1.5 text-xs text-rose-600">{error}</p>}
    </div>
  );
}

function CheckboxField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2.5 rounded-lg border border-slate-200 px-3 py-2.5 cursor-pointer hover:bg-slate-50">
      <input
        type="checkbox"
        className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="text-xs font-medium text-slate-800">{label}</span>
    </label>
  );
}
