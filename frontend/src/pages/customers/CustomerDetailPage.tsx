import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Building2,
  CreditCard,
  ExternalLink,
  FileText,
  Globe,
  Mail,
  MapPin,
  Pencil,
  Phone,
  Plus,
  Receipt,
  Repeat,
  Star,
  Trash2,
  UserCheck,
  UserX,
  Users,
  Wallet,
  Check,
  Copy,
  Key,
  RotateCcw,
  Send,
} from 'lucide-react';
import { customerService } from '../../services/customerService';
import { customerPaymentMethodService } from '../../services/customerPaymentMethodService';
import type { CustomerPortalAccessStatusOut } from '../../types/portal';
import type {
  ContactIn,
  CustomerOut,
  InvoiceOut,
  Paginated,
  PaymentOut,
  SubscriptionOut,
} from '../../types/api';
import type { CustomerDetailTab, CustomerPaymentMethodOut } from '../../types/customers';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/common/Card';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { Modal } from '../../components/common/Modal';
import { DataTable, type Column } from '../../components/common/DataTable';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { Input } from '../../components/common/Input';
import { LoadingState } from '../../components/common/LoadingState';
import { PageHeader } from '../../components/common/PageHeader';
import { StatCard } from '../../components/common/StatCard';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { cn } from '../../utils/cn';
import { formatDate, formatDateTime, formatMoney, humanize, statusVariant } from '../../utils/format';
import { validateSensibleName, validateEmail, validatePhone } from '../../utils/validation';

const TABS: { key: CustomerDetailTab; label: string; icon: ReactNode }[] = [
  { key: 'overview', label: 'Overview', icon: <Building2 className="w-4 h-4" /> },
  { key: 'contacts', label: 'Contacts', icon: <Users className="w-4 h-4" /> },
  { key: 'invoices', label: 'Invoices', icon: <FileText className="w-4 h-4" /> },
  { key: 'payments', label: 'Payments', icon: <Receipt className="w-4 h-4" /> },
  { key: 'subscriptions', label: 'Subscriptions', icon: <Repeat className="w-4 h-4" /> },
  { key: 'payment-methods', label: 'Payment Methods', icon: <CreditCard className="w-4 h-4" /> },
];

const TAB_KEYS = new Set<string>(TABS.map((t) => t.key));
const SUB_PAGE_SIZE = 10;

function isTab(value: string | null): value is CustomerDetailTab {
  return value !== null && TAB_KEYS.has(value);
}

// ---------------------------------------------------------------------------
// Shared bits
// ---------------------------------------------------------------------------

function Field({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  const isEmpty = value === null || value === undefined || value === '';
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</dt>
      <dd className={cn('mt-1 text-sm text-slate-900', mono && 'font-mono text-xs', isEmpty && 'text-slate-400')}>
        {isEmpty ? '—' : value}
      </dd>
    </div>
  );
}

/** Generic paginated loader for the customer sub-resources (invoices, payments, subscriptions). */
function usePagedResource<T>(
  customerId: string | undefined,
  loader: (id: string, params: { page: number; page_size: number }) => Promise<Paginated<T>>,
  enabled: boolean
) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!customerId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await loader(customerId, { page, page_size: SUB_PAGE_SIZE });
      setItems(data.items);
      setTotal(data.total);
      setLoaded(true);
    } catch (err: any) {
      setError(err?.message || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, [customerId, loader, page]);

  useEffect(() => {
    if (enabled) load();
  }, [enabled, load]);

  return { items, total, page, setPage, loading, loaded, error, reload: load };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canWrite = hasRole('finance');
  const canDelete = hasRole('admin');

  const tabParam = searchParams.get('tab');
  const activeTab: CustomerDetailTab = isTab(tabParam) ? tabParam : 'overview';
  const setTab = (tab: CustomerDetailTab) => {
    const next = new URLSearchParams(searchParams);
    if (tab === 'overview') next.delete('tab');
    else next.set('tab', tab);
    setSearchParams(next, { replace: true });
  };

  const [customer, setCustomer] = useState<CustomerOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusDialogOpen, setStatusDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const loadCustomer = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await customerService.get(id);
      setCustomer(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load customer');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadCustomer();
  }, [loadCustomer]);

  const toggleStatus = async () => {
    if (!customer) return;
    const nextStatus = customer.status === 'active' ? 'inactive' : 'active';
    setActionLoading(true);
    try {
      const updated = await customerService.update(customer.id, { status: nextStatus });
      setCustomer((prev) => (prev ? { ...updated, stats: prev.stats } : updated));
      showToast('success', nextStatus === 'active' ? 'Customer reactivated' : 'Customer deactivated');
      setStatusDialogOpen(false);
    } catch (err: any) {
      showToast('error', err?.message || 'Failed to update customer status');
    } finally {
      setActionLoading(false);
    }
  };

  const deleteCustomer = async () => {
    if (!customer) return;
    setActionLoading(true);
    try {
      await customerService.remove(customer.id);
      showToast('success', 'Customer deleted', `${customer.display_name} has been removed.`);
      navigate('/customers');
    } catch (err: any) {
      showToast('error', err?.message || 'Failed to delete customer');
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 pb-12">
        <PageHeader backTo={{ to: '/customers', label: 'Customers' }} eyebrow="Workspace" title="Customer" />
        <LoadingState message="Loading customer..." />
      </div>
    );
  }

  if (error || !customer) {
    return (
      <div className="space-y-6 pb-12">
        <PageHeader backTo={{ to: '/customers', label: 'Customers' }} eyebrow="Workspace" title="Customer" />
        <ErrorState
          title="Could not load customer"
          message={error || 'This customer could not be found.'}
          onRetry={loadCustomer}
        />
      </div>
    );
  }

  const stats = customer.stats ?? null;
  const isActive = customer.status === 'active';

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        backTo={{ to: '/customers', label: 'Customers' }}
        eyebrow="Workspace"
        title={
          <span className="inline-flex items-center gap-3 flex-wrap">
            <span>{customer.display_name}</span>
            <Badge variant={statusVariant(customer.status)} dot>
              {humanize(customer.status)}
            </Badge>
          </span>
        }
        subtitle={
          <span className="inline-flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs text-slate-600">{customer.customer_number}</span>
            {customer.company_name && (
              <>
                <span className="text-slate-300">•</span>
                <span>{customer.company_name}</span>
              </>
            )}
            <span className="text-slate-300">•</span>
            <span>Customer since {formatDate(customer.created_at)}</span>
          </span>
        }
        actions={
          canWrite ? (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setStatusDialogOpen(true)}
                leadingIcon={isActive ? <UserX className="w-4 h-4" /> : <UserCheck className="w-4 h-4" />}
              >
                {isActive ? 'Deactivate' : 'Reactivate'}
              </Button>
              {canDelete && (
                <Button
                  variant="outline"
                  size="sm"
                  className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 border-rose-200"
                  onClick={() => setDeleteDialogOpen(true)}
                  leadingIcon={<Trash2 className="w-4 h-4" />}
                >
                  Delete
                </Button>
              )}
              <Button
                variant="primary"
                size="sm"
                onClick={() => navigate(`/customers/${customer.id}/edit`)}
                leadingIcon={<Pencil className="w-4 h-4" />}
              >
                Edit
              </Button>
            </>
          ) : undefined
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <StatCard
          title="Outstanding"
          value={stats ? formatMoney(stats.outstanding_amount, customer.currency) : '—'}
          icon={<Wallet className="w-4 h-4" />}
        />
        <StatCard
          title="Total billed"
          value={stats ? formatMoney(stats.total_billed, customer.currency) : '—'}
          icon={<FileText className="w-4 h-4" />}
        />
        <StatCard
          title="Total paid"
          value={stats ? formatMoney(stats.total_paid, customer.currency) : '—'}
          icon={<Receipt className="w-4 h-4" />}
        />
        <StatCard
          title="Open invoices"
          value={stats ? stats.open_invoice_count : '—'}
          icon={<FileText className="w-4 h-4" />}
        />
        <StatCard
          title="Active subscriptions"
          value={stats ? stats.active_subscriptions : '—'}
          icon={<Repeat className="w-4 h-4" />}
        />
      </div>

      <div className="border-b border-slate-200">
        <nav className="-mb-px flex gap-1 overflow-x-auto" aria-label="Customer sections">
          {TABS.map((tab) => {
            const selected = tab.key === activeTab;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setTab(tab.key)}
                aria-current={selected ? 'page' : undefined}
                className={cn(
                  'inline-flex items-center gap-2 whitespace-nowrap px-3.5 py-2.5 text-sm font-medium border-b-2 transition-colors',
                  selected
                    ? 'border-brand-600 text-brand-700'
                    : 'border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300'
                )}
              >
                {tab.icon}
                {tab.label}
                {tab.key === 'contacts' && customer.contacts.length > 0 && (
                  <span className="ml-0.5 rounded-full bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-600">
                    {customer.contacts.length}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {activeTab === 'overview' && <OverviewTab customer={customer} canWrite={canWrite} />}
      {activeTab === 'contacts' && (
        <ContactsTab customer={customer} canWrite={canWrite} onUpdated={(c) => setCustomer({ ...c, stats: customer.stats })} />
      )}
      {activeTab === 'invoices' && <InvoicesTab customerId={customer.id} canWrite={canWrite} />}
      {activeTab === 'payments' && <PaymentsTab customerId={customer.id} />}
      {activeTab === 'subscriptions' && <SubscriptionsTab customerId={customer.id} canWrite={canWrite} />}
      {activeTab === 'payment-methods' && <PaymentMethodsTab customerId={customer.id} canWrite={canWrite} />}

      <ConfirmDialog
        isOpen={statusDialogOpen}
        onClose={() => setStatusDialogOpen(false)}
        onConfirm={toggleStatus}
        isLoading={actionLoading}
        title={isActive ? 'Deactivate customer?' : 'Reactivate customer?'}
        description={
          isActive
            ? `${customer.display_name} will be marked inactive. Existing invoices and subscriptions are kept; you can reactivate at any time.`
            : `${customer.display_name} will be marked active again and available for new quotes, invoices and subscriptions.`
        }
        confirmLabel={isActive ? 'Deactivate' : 'Reactivate'}
        variant={isActive ? 'danger' : 'default'}
      />

      <ConfirmDialog
        isOpen={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        onConfirm={deleteCustomer}
        isLoading={actionLoading}
        title="Delete customer?"
        description={`This permanently deletes ${customer.display_name} (${customer.customer_number}). Customers with invoices or subscriptions cannot be deleted — deactivate them instead.`}
        confirmLabel="Delete customer"
        variant="danger"
      />
    </div>
  );
}

export default CustomerDetailPage;

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

function OverviewTab({ customer, canWrite }: { customer: CustomerOut; canWrite: boolean }) {
  const { showToast } = useToast();
  const addressLines = [
    customer.billing_address_line1,
    customer.billing_address_line2,
    [customer.billing_city, customer.billing_state, customer.billing_postal_code].filter(Boolean).join(', '),
    customer.billing_country,
  ].filter((line) => line && line.trim() !== '');

  const primaryContact = customer.contacts.find((c) => c.is_primary) ?? customer.contacts[0];

  const [portalAccess, setPortalAccess] = useState<CustomerPortalAccessStatusOut | null>(null);
  const [portalLoading, setPortalLoading] = useState<boolean>(true);
  const [lastInviteUrl, setLastInviteUrl] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState<boolean>(false);

  const [inviteDialogOpen, setInviteDialogOpen] = useState<boolean>(false);
  const [inviteEmail, setInviteEmail] = useState<string>(customer.email || primaryContact?.email || '');
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  const [revokeDialogOpen, setRevokeDialogOpen] = useState<boolean>(false);
  const [reactivateDialogOpen, setReactivateDialogOpen] = useState<boolean>(false);

  const loadPortalAccess = useCallback(async () => {
    setPortalLoading(true);
    try {
      const data = await customerService.getPortalAccess(customer.id);
      setPortalAccess(data);
    } catch {
      // ignore
    } finally {
      setPortalLoading(false);
    }
  }, [customer.id]);

  useEffect(() => {
    loadPortalAccess();
  }, [loadPortalAccess]);

  const openInviteDialog = () => {
    setInviteEmail(customer.email || primaryContact?.email || '');
    setInviteDialogOpen(true);
  };

  const handleSendInvite = async () => {
    setActionLoading(true);
    try {
      const inv = await customerService.inviteToPortal(customer.id, inviteEmail.trim() || undefined);
      // The activation link is a customer credential: the API returns it only when the email
      // could not be delivered, and only to admins, so they can share it by hand.
      if (inv.email_delivered === false) {
        showToast(
          'warning',
          'Invitation Created (Action Required)',
          inv.invite_url
            ? `Email could not be delivered to ${inv.email}. Share the activation link shown below with the customer.`
            : `Email could not be delivered to ${inv.email}. Ask an admin to resend the invitation and share the link.`
        );
      } else {
        showToast('success', 'Customer portal invitation sent successfully.');
      }
      setLastInviteUrl(inv.invite_url || null);
      setInviteDialogOpen(false);
      await loadPortalAccess();
    } catch (err: any) {
      showToast('error', err?.response?.data?.detail || err?.message || 'Failed to send invitation');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRevoke = async () => {
    setActionLoading(true);
    try {
      const updated = await customerService.revokePortalAccess(customer.id);
      setPortalAccess(updated);
      setLastInviteUrl(null);
      showToast('success', 'Customer portal access revoked.');
      setRevokeDialogOpen(false);
    } catch (err: any) {
      showToast('error', err?.response?.data?.detail || err?.message || 'Failed to revoke portal access');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReactivate = async () => {
    setActionLoading(true);
    try {
      const updated = await customerService.reactivatePortalAccess(customer.id);
      setPortalAccess(updated);
      showToast('success', 'Customer portal access reactivated.');
      setReactivateDialogOpen(false);
    } catch (err: any) {
      showToast('error', err?.response?.data?.detail || err?.message || 'Failed to reactivate portal access');
    } finally {
      setActionLoading(false);
    }
  };

  const copyActivationLink = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopiedLink(true);
      showToast('success', 'Activation link copied to clipboard.');
      setTimeout(() => setCopiedLink(false), 2500);
    } catch {
      showToast('error', 'Failed to copy link to clipboard');
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
      <div className="lg:col-span-2 space-y-5">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Company details</CardTitle>
              <CardDescription>How this customer appears on quotes and invoices.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5">
              <Field label="Display name" value={customer.display_name} />
              <Field label="Legal / company name" value={customer.company_name} />
              <Field
                label="Email"
                value={
                  customer.email ? (
                    <a href={`mailto:${customer.email}`} className="inline-flex items-center gap-1.5 text-brand-700 hover:underline">
                      <Mail className="w-3.5 h-3.5" />
                      {customer.email}
                    </a>
                  ) : null
                }
              />
              <Field
                label="Phone"
                value={
                  customer.phone ? (
                    <a href={`tel:${customer.phone}`} className="inline-flex items-center gap-1.5 text-brand-700 hover:underline">
                      <Phone className="w-3.5 h-3.5" />
                      {customer.phone}
                    </a>
                  ) : null
                }
              />
              <Field
                label="Website"
                value={
                  customer.website ? (
                    <a
                      href={customer.website.startsWith('http') ? customer.website : `https://${customer.website}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-brand-700 hover:underline"
                    >
                      <Globe className="w-3.5 h-3.5" />
                      {customer.website}
                    </a>
                  ) : null
                }
              />
              <Field
                label="Customer portal"
                value={
                  customer.portal_url ? (
                    <a
                      href={customer.portal_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-brand-700 hover:underline"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      Open portal
                    </a>
                  ) : null
                }
              />
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Tax & billing terms</CardTitle>
              <CardDescription>Used when calculating GST and due dates on new invoices.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5">
              <Field label="GSTIN" value={customer.gstin} mono />
              <Field label="PAN" value={customer.pan} mono />
              <Field
                label="Tax status"
                value={
                  <Badge variant={customer.tax_exempt ? 'warning' : 'success'} size="sm">
                    {customer.tax_exempt ? 'Tax exempt' : 'Taxable'}
                  </Badge>
                }
              />
              <Field label="Currency" value={customer.currency} />
              <Field
                label="Payment terms"
                value={customer.payment_terms_days === 0 ? 'Due on receipt' : `Net ${customer.payment_terms_days} days`}
              />
              <Field label="Last updated" value={formatDateTime(customer.updated_at)} />
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Internal notes</CardTitle>
          </CardHeader>
          <CardContent>
            {customer.notes ? (
              <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{customer.notes}</p>
            ) : (
              <p className="text-sm text-slate-400">No notes recorded for this customer.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-5">
        {/* Customer Portal Access Card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Key className="w-4 h-4 text-indigo-600" />
                Customer Portal Access
              </CardTitle>
              <CardDescription>
                Invitation-only self-service access.
              </CardDescription>
            </div>
            {portalAccess && !portalLoading && (
              <Badge
                variant={
                  portalAccess.status === 'active'
                    ? 'success'
                    : portalAccess.status === 'invitation_pending'
                    ? 'warning'
                    : portalAccess.status === 'revoked'
                    ? 'danger'
                    : 'neutral'
                }
                dot
              >
                {portalAccess.status === 'active'
                  ? 'Active'
                  : portalAccess.status === 'invitation_pending'
                  ? 'Invitation Pending'
                  : portalAccess.status === 'revoked'
                  ? 'Revoked'
                  : 'Not Invited'}
              </Badge>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            {portalLoading ? (
              <div className="py-6 flex justify-center">
                <div className="w-5 h-5 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : (
              <>
                {/* State: Not Invited */}
                {portalAccess?.status === 'not_invited' && (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500 leading-relaxed">
                      This customer does not have access to the Customer Portal. Send a secure, time-limited activation link to invite them.
                    </p>
                    {canWrite && (
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={openInviteDialog}
                        leadingIcon={<Send className="w-3.5 h-3.5" />}
                      >
                        Send Invitation
                      </Button>
                    )}
                  </div>
                )}

                {/* State: Invitation Pending */}
                {portalAccess?.status === 'invitation_pending' && (
                  <div className="space-y-3">
                    <dl className="grid grid-cols-1 gap-2.5 text-xs">
                      <div>
                        <dt className="text-slate-400 uppercase tracking-wider font-semibold text-[10px]">Invited Email</dt>
                        <dd className="mt-0.5 text-slate-800 font-medium">{portalAccess.invitation?.email}</dd>
                      </div>
                      <div>
                        <dt className="text-slate-400 uppercase tracking-wider font-semibold text-[10px]">Expires</dt>
                        <dd className="mt-0.5 text-slate-800 font-medium">
                          {portalAccess.invitation?.expires_at ? formatDateTime(portalAccess.invitation.expires_at) : '—'}
                        </dd>
                      </div>
                      {portalAccess.invitation?.invited_by_name && (
                        <div>
                          <dt className="text-slate-400 uppercase tracking-wider font-semibold text-[10px]">Invited By</dt>
                          <dd className="mt-0.5 text-slate-800 font-medium">{portalAccess.invitation.invited_by_name}</dd>
                        </div>
                      )}
                    </dl>

                    {lastInviteUrl && (
                      <div className="p-2.5 bg-indigo-50/60 border border-indigo-100 rounded-lg space-y-1.5">
                        <div className="flex items-center justify-between text-[11px] font-semibold text-indigo-900">
                          <span>Activation link (email not delivered: share it with the customer)</span>
                          <button
                            type="button"
                            onClick={() => copyActivationLink(lastInviteUrl)}
                            className="inline-flex items-center gap-1 text-indigo-700 hover:text-indigo-900 hover:underline"
                          >
                            {copiedLink ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                            {copiedLink ? 'Copied' : 'Copy'}
                          </button>
                        </div>
                        <div className="text-[11px] font-mono text-indigo-800 truncate select-all">{lastInviteUrl}</div>
                      </div>
                    )}

                    {canWrite && (
                      <div className="flex items-center gap-2 pt-1 flex-wrap">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={openInviteDialog}
                          leadingIcon={<RotateCcw className="w-3.5 h-3.5" />}
                        >
                          Resend Invitation
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 border-rose-200"
                          onClick={() => setRevokeDialogOpen(true)}
                          leadingIcon={<UserX className="w-3.5 h-3.5" />}
                        >
                          Revoke Invitation
                        </Button>
                      </div>
                    )}
                  </div>
                )}

                {/* State: Active */}
                {portalAccess?.status === 'active' && (
                  <div className="space-y-3">
                    <dl className="grid grid-cols-1 gap-2.5 text-xs">
                      <div>
                        <dt className="text-slate-400 uppercase tracking-wider font-semibold text-[10px]">Portal User</dt>
                        <dd className="mt-0.5 text-slate-800 font-medium">{portalAccess.user?.display_name || 'Customer Contact'}</dd>
                      </div>
                      <div>
                        <dt className="text-slate-400 uppercase tracking-wider font-semibold text-[10px]">Login Email</dt>
                        <dd className="mt-0.5 text-slate-800 font-medium">{portalAccess.user?.email}</dd>
                      </div>
                      <div>
                        <dt className="text-slate-400 uppercase tracking-wider font-semibold text-[10px]">Last Login</dt>
                        <dd className="mt-0.5 text-slate-800 font-medium">
                          {portalAccess.user?.last_login_at ? formatDateTime(portalAccess.user.last_login_at) : 'Never logged in'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-slate-400 uppercase tracking-wider font-semibold text-[10px]">Portal Login</dt>
                        <dd className="mt-0.5">
                          <a
                            href="/portal/login"
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-brand-700 hover:underline"
                          >
                            <ExternalLink className="w-3 h-3" />
                            Open Customer Portal
                          </a>
                        </dd>
                      </div>
                    </dl>

                    {lastInviteUrl && (
                      <div className="p-2.5 bg-indigo-50/60 border border-indigo-100 rounded-lg space-y-1.5">
                        <div className="flex items-center justify-between text-[11px] font-semibold text-indigo-900">
                          <span>New activation link (email not delivered: share it with the customer)</span>
                          <button
                            type="button"
                            onClick={() => copyActivationLink(lastInviteUrl)}
                            className="inline-flex items-center gap-1 text-indigo-700 hover:text-indigo-900 hover:underline"
                          >
                            {copiedLink ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                            {copiedLink ? 'Copied' : 'Copy'}
                          </button>
                        </div>
                        <div className="text-[11px] font-mono text-indigo-800 truncate select-all">{lastInviteUrl}</div>
                      </div>
                    )}

                    {canWrite && (
                      <div className="flex items-center gap-2 pt-1 flex-wrap">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={openInviteDialog}
                          leadingIcon={<RotateCcw className="w-3.5 h-3.5" />}
                        >
                          Send New Link
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 border-rose-200"
                          onClick={() => setRevokeDialogOpen(true)}
                          leadingIcon={<UserX className="w-3.5 h-3.5" />}
                        >
                          Revoke Access
                        </Button>
                      </div>
                    )}
                  </div>
                )}

                {/* State: Revoked */}
                {portalAccess?.status === 'revoked' && (
                  <div className="space-y-3">
                    <p className="text-xs text-rose-600 leading-relaxed">
                      Customer Portal access has been revoked. Customer credentials and active sessions are disabled.
                    </p>
                    {canWrite && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setReactivateDialogOpen(true)}
                        leadingIcon={<UserCheck className="w-3.5 h-3.5" />}
                      >
                        Reactivate Portal Access
                      </Button>
                    )}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Billing address</CardTitle>
          </CardHeader>
          <CardContent>
            {addressLines.length > 0 ? (
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-slate-100 text-slate-500 shrink-0">
                  <MapPin className="w-4 h-4" />
                </div>
                <address className="not-italic text-sm text-slate-800 leading-relaxed">
                  {addressLines.map((line, i) => (
                    <div key={i}>{line}</div>
                  ))}
                </address>
              </div>
            ) : (
              <p className="text-sm text-slate-400">No billing address on file.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Primary contact</CardTitle>
          </CardHeader>
          <CardContent>
            {primaryContact ? (
              <div className="space-y-1">
                <div className="text-sm font-semibold text-slate-900">{primaryContact.name}</div>
                {primaryContact.designation && (
                  <div className="text-xs text-slate-500">{primaryContact.designation}</div>
                )}
                {primaryContact.email && (
                  <a href={`mailto:${primaryContact.email}`} className="block text-xs text-brand-700 hover:underline">
                    {primaryContact.email}
                  </a>
                )}
                {primaryContact.phone && <div className="text-xs text-slate-600">{primaryContact.phone}</div>}
              </div>
            ) : (
              <p className="text-sm text-slate-400">No contacts added yet.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Send / Resend Invitation Modal */}
      <Modal
        isOpen={inviteDialogOpen}
        onClose={() => setInviteDialogOpen(false)}
        title={portalAccess?.status === 'active' ? 'Send New Activation Link' : portalAccess?.status === 'invitation_pending' ? 'Resend Portal Invitation' : 'Invite Customer to Portal'}
        description={`Send a time-limited activation link to grant ${customer.display_name} access to the Customer Billing Portal.`}
        footer={
          <div className="flex items-center justify-end gap-3">
            <Button variant="outline" size="sm" onClick={() => setInviteDialogOpen(false)} disabled={actionLoading}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={handleSendInvite} isLoading={actionLoading} leadingIcon={<Send className="w-3.5 h-3.5" />}>
              Send Invitation
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Recipient Email Address
            </label>
            <Input
              type="email"
              required
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="customer@example.com"
            />
            <p className="mt-1.5 text-xs text-slate-500">
              The customer will receive an email with their secure single-use activation link.
            </p>
          </div>
        </div>
      </Modal>

      {/* Revoke Confirmation Dialog */}
      <ConfirmDialog
        isOpen={revokeDialogOpen}
        onClose={() => setRevokeDialogOpen(false)}
        onConfirm={handleRevoke}
        isLoading={actionLoading}
        title="Revoke Customer Portal Access?"
        description={`Are you sure you want to revoke portal access for ${customer.display_name}? Any pending invitations will be invalidated and existing customer sessions will be terminated.`}
        confirmLabel="Revoke Access"
        variant="danger"
      />

      {/* Reactivate Confirmation Dialog */}
      <ConfirmDialog
        isOpen={reactivateDialogOpen}
        onClose={() => setReactivateDialogOpen(false)}
        onConfirm={handleReactivate}
        isLoading={actionLoading}
        title="Reactivate Customer Portal Access?"
        description={`This will restore portal access for ${customer.display_name}.`}
        confirmLabel="Reactivate"
        variant="default"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Contacts
// ---------------------------------------------------------------------------

type ContactDraft = ContactIn & { key: string };

let contactKeySeq = 0;
function newContactKey(): string {
  contactKeySeq += 1;
  return `c${contactKeySeq}`;
}

function ContactsTab({
  customer,
  canWrite,
  onUpdated,
}: {
  customer: CustomerOut;
  canWrite: boolean;
  onUpdated: (customer: CustomerOut) => void;
}) {
  const { showToast } = useToast();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [drafts, setDrafts] = useState<ContactDraft[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const startEditing = () => {
    setDrafts(
      customer.contacts.map((c) => ({
        key: newContactKey(),
        name: c.name,
        email: c.email ?? '',
        phone: c.phone ?? '',
        designation: c.designation ?? '',
        is_primary: c.is_primary,
      }))
    );
    setErrors({});
    setEditing(true);
  };

  const addRow = () => {
    setDrafts((prev) => [
      ...prev,
      { key: newContactKey(), name: '', email: '', phone: '', designation: '', is_primary: prev.length === 0 },
    ]);
  };

  const updateRow = (key: string, patch: Partial<ContactIn>) => {
    setDrafts((prev) => {
      const idx = prev.findIndex((d) => d.key === key);
      if (idx !== -1) {
        const keysToClear = Object.keys(patch).map((k) => `${idx}.${k}`);
        setErrors((prevErr) => {
          let hasMatch = false;
          for (const k of keysToClear) {
            if (prevErr[k]) {
              hasMatch = true;
              break;
            }
          }
          if (!hasMatch) return prevErr;
          const nextErr = { ...prevErr };
          for (const k of keysToClear) {
            delete nextErr[k];
          }
          return nextErr;
        });
      }
      return prev.map((d) => (d.key === key ? { ...d, ...patch } : d));
    });
  };

  const setPrimary = (key: string) => {
    setDrafts((prev) => prev.map((d) => ({ ...d, is_primary: d.key === key })));
  };

  const removeRow = (key: string) => {
    setDrafts((prev) => {
      const next = prev.filter((d) => d.key !== key);
      if (next.length > 0 && !next.some((d) => d.is_primary)) next[0] = { ...next[0], is_primary: true };
      return next;
    });
  };

  const save = async () => {
    const localErrors: Record<string, string> = {};
    drafts.forEach((d, i) => {
      const nameErr = validateSensibleName(d.name, 'Name');
      if (nameErr) localErrors[`${i}.name`] = nameErr;

      const emailErr = validateEmail(d.email);
      if (emailErr) localErrors[`${i}.email`] = emailErr;

      const phoneErr = validatePhone(d.phone);
      if (phoneErr) localErrors[`${i}.phone`] = phoneErr;
    });
    if (Object.keys(localErrors).length > 0) {
      setErrors(localErrors);
      return;
    }
    setSaving(true);
    setErrors({});
    try {
      const payload: ContactIn[] = drafts.map((d) => ({
        name: d.name.trim(),
        email: d.email ? String(d.email).trim() || null : null,
        phone: d.phone ? String(d.phone).trim() || null : null,
        designation: d.designation ? String(d.designation).trim() || null : null,
        is_primary: Boolean(d.is_primary),
      }));
      const updated = await customerService.setContacts(customer.id, payload);
      onUpdated(updated);
      showToast('success', 'Contacts saved', `${payload.length} contact${payload.length === 1 ? '' : 's'} on file.`);
      setEditing(false);
    } catch (err: any) {
      const fields: Record<string, string> = err?.details?.fields ?? {};
      const mapped: Record<string, string> = {};
      Object.entries(fields).forEach(([k, v]) => {
        // Server keys look like "contacts.0.email" (or plain "0.email").
        mapped[k.replace(/^contacts\./, '')] = v;
      });
      setErrors(mapped);
      showToast('error', err?.message || 'Failed to save contacts');
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Edit contacts</CardTitle>
            <CardDescription>Replaces the full contact list for this customer. Exactly one contact should be primary.</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={addRow} leadingIcon={<Plus className="w-4 h-4" />}>
            Add contact
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {drafts.length === 0 && (
            <p className="text-sm text-slate-500">No contacts. Add one above, or save to clear all contacts.</p>
          )}
          {drafts.map((d, i) => (
            <div key={d.key} className="rounded-lg border border-slate-200 p-4 space-y-3 bg-slate-50/40">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Input
                  label="Name"
                  required
                  value={d.name}
                  onChange={(e) => updateRow(d.key, { name: e.target.value })}
                  error={errors[`${i}.name`]}
                  placeholder="Full name"
                />
                <Input
                  label="Designation"
                  value={d.designation ?? ''}
                  onChange={(e) => updateRow(d.key, { designation: e.target.value })}
                  error={errors[`${i}.designation`]}
                  placeholder="e.g. Finance Head"
                />
                <Input
                  label="Email"
                  type="email"
                  value={d.email ?? ''}
                  onChange={(e) => updateRow(d.key, { email: e.target.value })}
                  error={errors[`${i}.email`]}
                  placeholder="name@company.com"
                />
                <Input
                  label="Phone"
                  value={d.phone ?? ''}
                  onChange={(e) => updateRow(d.key, { phone: e.target.value })}
                  error={errors[`${i}.phone`]}
                  placeholder="+91 ..."
                />
              </div>
              <div className="flex items-center justify-between">
                <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                  <input
                    type="radio"
                    name="primary-contact"
                    checked={Boolean(d.is_primary)}
                    onChange={() => setPrimary(d.key)}
                    className="h-4 w-4 text-brand-600 border-slate-300 focus:ring-brand-500"
                  />
                  Primary contact
                </label>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                  onClick={() => removeRow(d.key)}
                  leadingIcon={<Trash2 className="w-3.5 h-3.5" />}
                >
                  Remove
                </Button>
              </div>
            </div>
          ))}
          <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)} disabled={saving}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={save} isLoading={saving}>
              Save contacts
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (customer.contacts.length === 0) {
    return (
      <EmptyState
        icon={<Users className="w-6 h-6 stroke-1" />}
        title="No contacts yet"
        description="Add the people who receive invoices, statements and payment reminders for this customer."
        action={
          canWrite ? (
            <Button variant="primary" size="sm" onClick={startEditing} leadingIcon={<Plus className="w-4 h-4" />}>
              Add contact
            </Button>
          ) : undefined
        }
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Contacts</CardTitle>
          <CardDescription>People at this customer who receive billing communication.</CardDescription>
        </div>
        {canWrite && (
          <Button variant="outline" size="sm" onClick={startEditing} leadingIcon={<Pencil className="w-4 h-4" />}>
            Edit contacts
          </Button>
        )}
      </CardHeader>
      <ul className="divide-y divide-slate-100">
        {customer.contacts.map((c) => (
          <li key={c.id} className="px-5 py-4 flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-slate-900">{c.name}</span>
                {c.is_primary && (
                  <Badge variant="primary" size="sm">
                    <span className="inline-flex items-center gap-1">
                      <Star className="w-3 h-3" /> Primary
                    </span>
                  </Badge>
                )}
              </div>
              {c.designation && <div className="text-xs text-slate-500 mt-0.5">{c.designation}</div>}
            </div>
            <div className="text-right text-xs text-slate-600 space-y-0.5 shrink-0">
              {c.email ? (
                <a href={`mailto:${c.email}`} className="block text-brand-700 hover:underline">
                  {c.email}
                </a>
              ) : (
                <span className="block text-slate-400">No email</span>
              )}
              {c.phone && <span className="block">{c.phone}</span>}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Invoices
// ---------------------------------------------------------------------------

function InvoicesTab({ customerId, canWrite }: { customerId: string; canWrite: boolean }) {
  const navigate = useNavigate();
  const loader = useCallback(
    (id: string, params: { page: number; page_size: number }) => customerService.invoices(id, params),
    []
  );
  const res = usePagedResource<InvoiceOut>(customerId, loader, true);

  const columns = useMemo<Column<InvoiceOut>[]>(
    () => [
      {
        key: 'invoice_number',
        title: 'Invoice',
        render: (inv) => (
          <Link to={`/invoices/${inv.id}`} className="font-mono text-xs font-semibold text-brand-700 hover:underline">
            {inv.invoice_number}
          </Link>
        ),
      },
      {
        key: 'status',
        title: 'Status',
        render: (inv) => (
          <Badge variant={statusVariant(inv.status)} size="sm" dot>
            {humanize(inv.status)}
          </Badge>
        ),
      },
      { key: 'issue_date', title: 'Issued', render: (inv) => formatDate(inv.issue_date) },
      {
        key: 'due_date',
        title: 'Due',
        render: (inv) => (
          <span className={inv.days_overdue > 0 ? 'text-rose-600 font-medium' : undefined}>
            {formatDate(inv.due_date)}
            {inv.days_overdue > 0 && <span className="block text-[11px]">{inv.days_overdue}d overdue</span>}
          </span>
        ),
      },
      { key: 'total', title: 'Total', align: 'right', render: (inv) => <span className="tabular-nums">{formatMoney(inv.total, inv.currency)}</span> },
      {
        key: 'amount_due',
        title: 'Due',
        align: 'right',
        render: (inv) => (
          <span className={cn('tabular-nums', Number(inv.amount_due) > 0 ? 'font-semibold text-slate-900' : 'text-slate-500')}>
            {formatMoney(inv.amount_due, inv.currency)}
          </span>
        ),
      },
    ],
    []
  );

  if (res.error) return <ErrorState title="Could not load invoices" message={res.error} onRetry={res.reload} />;
  if (res.loaded && res.total === 0) {
    return (
      <EmptyState
        icon={<FileText className="w-6 h-6 stroke-1" />}
        title="No invoices yet"
        description="Invoices raised for this customer will appear here with their status and outstanding balance."
        action={
          canWrite ? (
            <Button variant="primary" size="sm" onClick={() => navigate(`/invoices/new?customer_id=${customerId}`)} leadingIcon={<Plus className="w-4 h-4" />}>
              New invoice
            </Button>
          ) : undefined
        }
      />
    );
  }
  return (
    <DataTable<InvoiceOut>
      columns={columns}
      data={res.items}
      keyExtractor={(i) => i.id}
      isLoading={res.loading && !res.loaded}
      page={res.page}
      pageSize={SUB_PAGE_SIZE}
      total={res.total}
      onPageChange={res.setPage}
    />
  );
}

// ---------------------------------------------------------------------------
// Payments
// ---------------------------------------------------------------------------

function PaymentsTab({ customerId }: { customerId: string }) {
  const loader = useCallback(
    (id: string, params: { page: number; page_size: number }) => customerService.payments(id, params),
    []
  );
  const res = usePagedResource<PaymentOut>(customerId, loader, true);

  const columns = useMemo<Column<PaymentOut>[]>(
    () => [
      {
        key: 'payment_number',
        title: 'Payment',
        render: (p) => (
          <Link to={`/payments/${p.id}`} className="font-mono text-xs font-semibold text-brand-700 hover:underline">
            {p.payment_number}
          </Link>
        ),
      },
      {
        key: 'status',
        title: 'Status',
        render: (p) => (
          <Badge variant={statusVariant(p.status)} size="sm" dot>
            {humanize(p.status)}
          </Badge>
        ),
      },
      { key: 'method', title: 'Method', render: (p) => <span>{humanize(p.method)}<span className="block text-[11px] text-slate-400">{humanize(p.gateway)}</span></span> },
      { key: 'reference', title: 'Reference', render: (p) => <span className="font-mono text-xs text-slate-600">{p.reference || '—'}</span> },
      { key: 'paid_at', title: 'Paid on', render: (p) => formatDate(p.paid_at ?? p.created_at) },
      {
        key: 'reconciliation_status',
        title: 'Reconciliation',
        render: (p) => (
          <Badge variant={statusVariant(p.reconciliation_status)} size="sm">
            {humanize(p.reconciliation_status)}
          </Badge>
        ),
      },
      { key: 'amount', title: 'Amount', align: 'right', render: (p) => <span className="tabular-nums font-semibold text-slate-900">{formatMoney(p.amount, p.currency)}</span> },
    ],
    []
  );

  if (res.error) return <ErrorState title="Could not load payments" message={res.error} onRetry={res.reload} />;
  if (res.loaded && res.total === 0) {
    return (
      <EmptyState
        icon={<Receipt className="w-6 h-6 stroke-1" />}
        title="No payments recorded"
        description="Payments received against this customer's invoices — manual or via the gateway — will be listed here."
      />
    );
  }
  return (
    <DataTable<PaymentOut>
      columns={columns}
      data={res.items}
      keyExtractor={(p) => p.id}
      isLoading={res.loading && !res.loaded}
      page={res.page}
      pageSize={SUB_PAGE_SIZE}
      total={res.total}
      onPageChange={res.setPage}
    />
  );
}

// ---------------------------------------------------------------------------
// Subscriptions
// ---------------------------------------------------------------------------

function SubscriptionsTab({ customerId, canWrite }: { customerId: string; canWrite: boolean }) {
  const navigate = useNavigate();
  const loader = useCallback(
    (id: string, params: { page: number; page_size: number }) => customerService.subscriptions(id, params),
    []
  );
  const res = usePagedResource<SubscriptionOut>(customerId, loader, true);

  const columns = useMemo<Column<SubscriptionOut>[]>(
    () => [
      {
        key: 'subscription_number',
        title: 'Subscription',
        render: (s) => (
          <Link to={`/subscriptions/${s.id}`} className="font-mono text-xs font-semibold text-brand-700 hover:underline">
            {s.subscription_number}
          </Link>
        ),
      },
      {
        key: 'plan',
        title: 'Plan',
        render: (s) => (
          <div className="min-w-0">
            <div className="text-slate-900 font-medium truncate">{s.plan?.name ?? '—'}</div>
            <div className="text-xs text-slate-500 truncate">
              {s.plan?.product_name}
              {s.plan ? ` · ${humanize(s.plan.billing_interval)}` : ''}
            </div>
          </div>
        ),
      },
      {
        key: 'status',
        title: 'Status',
        render: (s) => (
          <Badge variant={statusVariant(s.status)} size="sm" dot>
            {humanize(s.status)}
          </Badge>
        ),
      },
      { key: 'quantity', title: 'Qty', align: 'right', render: (s) => s.quantity },
      {
        key: 'unit_amount',
        title: 'Unit amount',
        align: 'right',
        render: (s) => <span className="tabular-nums">{s.plan ? formatMoney(s.plan.unit_amount, s.plan.currency) : '—'}</span>,
      },
      {
        key: 'current_period',
        title: 'Current period',
        render: (s) => (
          <span className="text-xs text-slate-600 whitespace-nowrap">
            {formatDate(s.current_period_start)} → {formatDate(s.current_period_end)}
          </span>
        ),
      },
      {
        key: 'next_billing_date',
        title: 'Next billing',
        render: (s) => (
          <span>
            {formatDate(s.next_billing_date)}
            {s.cancel_at_period_end && <span className="block text-[11px] text-amber-600">Cancels at period end</span>}
          </span>
        ),
      },
    ],
    []
  );

  if (res.error) return <ErrorState title="Could not load subscriptions" message={res.error} onRetry={res.reload} />;
  if (res.loaded && res.total === 0) {
    return (
      <EmptyState
        icon={<Repeat className="w-6 h-6 stroke-1" />}
        title="No subscriptions"
        description="Recurring plans this customer is subscribed to will show here with their billing cycle and renewal date."
        action={
          canWrite ? (
            <Button variant="primary" size="sm" onClick={() => navigate(`/subscriptions/new?customer_id=${customerId}`)} leadingIcon={<Plus className="w-4 h-4" />}>
              New subscription
            </Button>
          ) : undefined
        }
      />
    );
  }
  return (
    <DataTable<SubscriptionOut>
      columns={columns}
      data={res.items}
      keyExtractor={(s) => s.id}
      isLoading={res.loading && !res.loaded}
      page={res.page}
      pageSize={SUB_PAGE_SIZE}
      total={res.total}
      onPageChange={res.setPage}
    />
  );
}

// ---------------------------------------------------------------------------
// Payment methods
// ---------------------------------------------------------------------------

function describeMethod(pm: CustomerPaymentMethodOut): string {
  const brand = pm.card_brand ? humanize(pm.card_brand) : humanize(pm.type);
  return pm.last4 ? `${brand} •••• ${pm.last4}` : brand;
}

function PaymentMethodsTab({ customerId, canWrite }: { customerId: string; canWrite: boolean }) {
  const { showToast } = useToast();
  const [methods, setMethods] = useState<CustomerPaymentMethodOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<CustomerPaymentMethodOut | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await customerPaymentMethodService.list(customerId);
      setMethods(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load payment methods');
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    load();
  }, [load]);

  const setDefault = async (pm: CustomerPaymentMethodOut) => {
    setBusyId(pm.id);
    try {
      await customerPaymentMethodService.setDefault(customerId, pm.id);
      showToast('success', 'Default payment method updated', describeMethod(pm));
      await load();
    } catch (err: any) {
      showToast('error', err?.message || 'Failed to set default payment method');
    } finally {
      setBusyId(null);
    }
  };

  const revoke = async () => {
    if (!revokeTarget) return;
    setBusyId(revokeTarget.id);
    try {
      await customerPaymentMethodService.revoke(customerId, revokeTarget.id);
      showToast('success', 'Payment method removed', describeMethod(revokeTarget));
      setRevokeTarget(null);
      await load();
    } catch (err: any) {
      showToast('error', err?.message || 'Failed to remove payment method');
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <LoadingState message="Loading payment methods..." />;
  if (error) return <ErrorState title="Could not load payment methods" message={error} onRetry={load} />;

  const visible = methods.filter((m) => m.status !== 'revoked');

  if (visible.length === 0) {
    return (
      <EmptyState
        icon={<CreditCard className="w-6 h-6 stroke-1" />}
        title="No saved payment methods"
        description="Cards and payment methods saved during checkout or in the customer portal are stored securely at the gateway for customer-initiated payments."
      />
    );
  }

  return (
    <>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Saved payment methods</CardTitle>
            <CardDescription>Tokenised instruments stored at the payment gateway. Card numbers are never stored here.</CardDescription>
          </div>
        </CardHeader>
        <ul className="divide-y divide-slate-100">
          {visible.map((pm) => {
            const expiry = pm.exp_month && pm.exp_year ? `${String(pm.exp_month).padStart(2, '0')}/${pm.exp_year}` : null;
            const busy = busyId === pm.id;
            return (
              <li key={pm.id} className="px-5 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0">
                  <div className="p-2 rounded-lg bg-slate-100 text-slate-600 shrink-0">
                    <CreditCard className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-slate-900">{describeMethod(pm)}</span>
                      {pm.is_default && (
                        <Badge variant="primary" size="sm">
                          Default
                        </Badge>
                      )}
                      <Badge variant={statusVariant(pm.status)} size="sm">
                        {humanize(pm.status)}
                      </Badge>
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {humanize(pm.gateway)}
                      {expiry ? ` · Expires ${expiry}` : ''}
                      {` · Added ${formatDate(pm.created_at)}`}
                      {pm.is_autocharge_eligible ? ' · Saved for customer checkout' : ' · Manual record'}
                    </div>
                  </div>
                </div>
                {canWrite && (
                  <div className="flex items-center gap-2 shrink-0">
                    {!pm.is_default && pm.status === 'active' && (
                      <Button variant="outline" size="sm" onClick={() => setDefault(pm)} isLoading={busy} leadingIcon={<Star className="w-3.5 h-3.5" />}>
                        Set default
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                      onClick={() => setRevokeTarget(pm)}
                      disabled={busy}
                      leadingIcon={<Trash2 className="w-3.5 h-3.5" />}
                    >
                      Remove
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      <ConfirmDialog
        isOpen={revokeTarget !== null}
        onClose={() => setRevokeTarget(null)}
        onConfirm={revoke}
        isLoading={busyId !== null && revokeTarget !== null && busyId === revokeTarget.id}
        title="Remove payment method?"
        description={
          revokeTarget
            ? `${describeMethod(revokeTarget)} will be revoked and can no longer be used for checkout. The customer can save a new method at checkout.`
            : undefined
        }
        confirmLabel="Remove"
        variant="danger"
      />
    </>
  );
}
