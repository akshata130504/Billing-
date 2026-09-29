import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Repeat,
  ArrowLeft,
  Calendar,
  DollarSign,
  User,
  Package,
  FileText,
  PauseCircle,
  PlayCircle,
  XCircle,
  RefreshCw,
  Edit2,
  AlertCircle,
  CheckCircle2,
  Receipt,
  Mail,
} from 'lucide-react';
import { subscriptionService } from '../../services/subscriptionService';
import type {
  SubscriptionOut,
  InvoiceOut,
  SubscriptionUpdate,
} from '../../types/api';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { LoadingState } from '../../components/common/LoadingState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatMoney, formatDate, formatDateTime, humanize, statusVariant } from '../../utils/format';

export function SubscriptionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canWrite = hasRole('finance');

  const [subscription, setSubscription] = useState<SubscriptionOut | null>(null);
  const [invoices, setInvoices] = useState<InvoiceOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [invoicesLoading, setInvoicesLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modals
  const [pauseModalOpen, setPauseModalOpen] = useState(false);
  const [resumeModalOpen, setResumeModalOpen] = useState(false);
  const [renewModalOpen, setRenewModalOpen] = useState(false);
  const [cancelModalOpen, setCancelModalOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelAtPeriodEnd, setCancelAtPeriodEnd] = useState(false);
  const [prorateCredit, setProrateCredit] = useState(false);
  const [generateInvoiceModalOpen, setGenerateInvoiceModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);

  // Edit form state
  const [editQuantity, setEditQuantity] = useState(1);
  const [editNotes, setEditNotes] = useState('');
  const [editAutoRenewal, setEditAutoRenewal] = useState(true);

  const fetchSubscription = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const data = await subscriptionService.get(id);
      setSubscription(data);
      setEditQuantity(data.quantity);
      setEditNotes(data.notes || '');
      setEditAutoRenewal(data.auto_renewal ?? true);
    } catch (err: any) {
      setError(err.response?.data?.error?.message || err.message || 'Failed to load subscription details');
    } finally {
      setLoading(false);
    }
  }, [id]);

  const fetchInvoices = useCallback(async () => {
    if (!id) return;
    try {
      setInvoicesLoading(true);
      const data = await subscriptionService.invoices(id);
      setInvoices(data.items);
    } catch {
      // Invoices non-blocking
    } finally {
      setInvoicesLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchSubscription();
    fetchInvoices();
  }, [fetchSubscription, fetchInvoices]);

  const handleActivate = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      await subscriptionService.activate(id);
      showToast('success', 'Subscription activated', 'The subscription is now active.');
      fetchSubscription();
      fetchInvoices();
    } catch (err: any) {
      showToast('error', 'Activation failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handlePauseConfirm = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      await subscriptionService.pause(id);
      showToast('warning', 'Subscription paused', 'Billing and renewals have been suspended.');
      setPauseModalOpen(false);
      fetchSubscription();
    } catch (err: any) {
      showToast('error', 'Pause failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResumeConfirm = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      await subscriptionService.resume(id);
      showToast('success', 'Subscription resumed', 'Subscription billing has been reactivated.');
      setResumeModalOpen(false);
      fetchSubscription();
    } catch (err: any) {
      showToast('error', 'Resume failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRenewConfirm = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      await subscriptionService.renew(id);
      showToast('success', 'Subscription renewed', 'Billing cycle advanced to next period.');
      setRenewModalOpen(false);
      fetchSubscription();
      fetchInvoices();
    } catch (err: any) {
      showToast('error', 'Renewal failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelConfirm = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      await subscriptionService.cancel(id, {
        at_period_end: cancelAtPeriodEnd,
        reason: cancelReason.trim() || undefined,
        prorate_credit: !cancelAtPeriodEnd && prorateCredit,
      });
      showToast(
        'info',
        cancelAtPeriodEnd ? 'Cancellation scheduled' : 'Subscription cancelled',
        cancelAtPeriodEnd
          ? `Subscription will terminate on ${formatDate(subscription?.current_period_end)}.`
          : 'Subscription has been cancelled immediately.'
      );
      setCancelModalOpen(false);
      setCancelReason('');
      fetchSubscription();
    } catch (err: any) {
      showToast('error', 'Cancellation failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleGenerateInvoiceConfirm = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      const inv = await subscriptionService.generateInvoice(id);
      showToast('success', 'Invoice generated', `Invoice ${inv.invoice_number} created successfully.`);
      setGenerateInvoiceModalOpen(false);
      fetchInvoices();
    } catch (err: any) {
      showToast('error', 'Invoice generation failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleEditSave = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      const body: SubscriptionUpdate = {
        quantity: editQuantity,
        notes: editNotes,
        auto_renewal: editAutoRenewal,
      };
      await subscriptionService.update(id, body);
      showToast('success', 'Subscription updated', 'Subscription details saved.');
      setEditModalOpen(false);
      fetchSubscription();
    } catch (err: any) {
      showToast('error', 'Update failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="py-24">
        <LoadingState message="Loading subscription details..." />
      </div>
    );
  }

  if (error || !subscription) {
    return (
      <div className="max-w-2xl mx-auto py-16 text-center space-y-4">
        <div className="p-4 bg-rose-50 text-rose-700 rounded-xl border border-rose-100">
          <AlertCircle className="w-8 h-8 mx-auto mb-2 text-rose-500" />
          <p className="font-semibold">{error || 'Subscription not found'}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => navigate('/subscriptions')}>
          <ArrowLeft className="w-4 h-4 mr-1.5" />
          Back to Subscriptions
        </Button>
      </div>
    );
  }

  const isDraft = subscription.status === 'draft' || subscription.status === 'pending_activation';
  const isActive = subscription.status === 'active';
  const isTrialing = subscription.status === 'trialing';
  const isPaused = subscription.status === 'paused';
  const isCancelled = subscription.status === 'cancelled' || subscription.status === 'expired';

  return (
    <div className="space-y-6 pb-16">
      {/* Top Navigation & Action Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <button
            onClick={() => navigate('/subscriptions')}
            className="inline-flex items-center text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors mb-2"
          >
            <ArrowLeft className="w-3.5 h-3.5 mr-1" />
            Back to Subscriptions
          </button>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
              <Repeat className="w-6 h-6 text-brand-600" />
              {subscription.subscription_number}
            </h1>
            <Badge variant={statusVariant(subscription.status)} dot size="md">
              {humanize(subscription.status)}
            </Badge>
            {subscription.auto_renewal && (
              <Badge variant="primary" size="sm">
                Auto-Renew
              </Badge>
            )}
            {subscription.cancel_at_period_end && !isCancelled && (
              <Badge variant="warning" size="sm">
                Cancels at Period End
              </Badge>
            )}
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Created on {formatDateTime(subscription.created_at)}
          </p>
        </div>

        {/* Action Buttons */}
        {canWrite && (
          <div className="flex flex-wrap items-center gap-2">
            {!isCancelled && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setEditModalOpen(true)}
                className="flex items-center gap-1.5"
              >
                <Edit2 className="w-3.5 h-3.5" />
                Edit
              </Button>
            )}

            {isDraft && (
              <Button
                variant="primary"
                size="sm"
                onClick={handleActivate}
                isLoading={actionLoading}
                className="flex items-center gap-1.5"
              >
                <PlayCircle className="w-3.5 h-3.5" />
                Activate Subscription
              </Button>
            )}

            {isActive && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setGenerateInvoiceModalOpen(true)}
                  className="flex items-center gap-1.5"
                >
                  <FileText className="w-3.5 h-3.5 text-brand-600" />
                  Generate Invoice
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setRenewModalOpen(true)}
                  className="flex items-center gap-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5 text-emerald-600" />
                  Renew
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPauseModalOpen(true)}
                  className="flex items-center gap-1.5 text-amber-700 hover:bg-amber-50"
                >
                  <PauseCircle className="w-3.5 h-3.5" />
                  Pause
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCancelModalOpen(true)}
                  className="flex items-center gap-1.5 text-rose-700 hover:bg-rose-50"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  Cancel
                </Button>
              </>
            )}

            {isTrialing && (
              <>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleActivate}
                  isLoading={actionLoading}
                  className="flex items-center gap-1.5"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Convert to Active
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCancelModalOpen(true)}
                  className="flex items-center gap-1.5 text-rose-700 hover:bg-rose-50"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  Cancel Trial
                </Button>
              </>
            )}

            {isPaused && (
              <>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setResumeModalOpen(true)}
                  className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700"
                >
                  <PlayCircle className="w-3.5 h-3.5" />
                  Resume Subscription
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCancelModalOpen(true)}
                  className="flex items-center gap-1.5 text-rose-700 hover:bg-rose-50"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  Cancel
                </Button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Columns: Commercial Details */}
        <div className="lg:col-span-2 space-y-6">
          {/* Commercial Pricing Snapshot Card */}
          <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-brand-600" />
                Commercial Terms & Pricing Snapshot
              </h2>
              <span className="text-xs bg-slate-100 text-slate-600 font-semibold px-2 py-0.5 rounded uppercase">
                {subscription.billing_frequency || subscription.plan?.billing_interval} billing
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-slate-50/70 rounded-lg border border-slate-100">
              <div>
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                  Plan Unit Price
                </span>
                <span className="text-base font-bold text-slate-900 mt-0.5 block tabular-nums">
                  {formatMoney(subscription.unit_price || subscription.plan?.unit_amount, subscription.currency || 'INR')}
                </span>
              </div>
              <div>
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                  Quantity / Seats
                </span>
                <span className="text-base font-bold text-slate-900 mt-0.5 block tabular-nums">
                  {subscription.quantity} {subscription.quantity === 1 ? 'unit' : 'units'}
                </span>
              </div>
              <div>
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                  Subtotal
                </span>
                <span className="text-base font-bold text-slate-900 mt-0.5 block tabular-nums">
                  {formatMoney(subscription.subtotal ?? (Number(subscription.unit_price || subscription.plan?.unit_amount || 0) * subscription.quantity), subscription.currency || 'INR')}
                </span>
              </div>
              <div>
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                  Total per Period
                </span>
                <span className="text-base font-bold text-brand-700 mt-0.5 block tabular-nums">
                  {formatMoney(subscription.total_amount ?? subscription.mrr, subscription.currency || 'INR')}
                </span>
              </div>
            </div>

            {/* Financial Detail Breakdown */}
            <div className="space-y-2 pt-2 border-t border-slate-100 text-xs">
              <div className="flex justify-between text-slate-600">
                <span>Monthly Recurring Revenue (MRR)</span>
                <span className="font-semibold text-slate-900 tabular-nums">
                  {formatMoney(subscription.mrr, subscription.currency || 'INR')}
                </span>
              </div>
              <div className="flex justify-between text-slate-600">
                <span>Tax Amount (Included / Applied)</span>
                <span className="font-semibold text-slate-900 tabular-nums">
                  {formatMoney(subscription.tax_amount || 0, subscription.currency || 'INR')}
                </span>
              </div>
              {Number(subscription.discount_amount || 0) > 0 && (
                <div className="flex justify-between text-emerald-600">
                  <span>Agreed Discount</span>
                  <span className="font-semibold tabular-nums">
                    - {formatMoney(subscription.discount_amount, subscription.currency || 'INR')}
                  </span>
                </div>
              )}
            </div>

            {subscription.notes && (
              <div className="pt-3 border-t border-slate-100">
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block mb-1">
                  Contract Notes
                </span>
                <p className="text-xs text-slate-700 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                  {subscription.notes}
                </p>
              </div>
            )}
          </div>

          {/* Linked Invoices Section */}
          <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
                  <Receipt className="w-4 h-4 text-brand-600" />
                  Subscription Billing Invoices
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  All billing invoices generated from this subscription contract.
                </p>
              </div>
              {canWrite && isActive && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setGenerateInvoiceModalOpen(true)}
                  className="text-xs"
                >
                  <FileText className="w-3.5 h-3.5 mr-1" />
                  Generate Invoice
                </Button>
              )}
            </div>

            {invoicesLoading ? (
              <div className="py-8">
                <LoadingState message="Loading invoices..." />
              </div>
            ) : invoices.length === 0 ? (
              <div className="p-8 text-center bg-slate-50/50 rounded-lg border border-dashed border-slate-200 text-slate-500 text-xs">
                No invoices have been generated for this subscription yet.
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200/80">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200 uppercase tracking-wider text-[11px]">
                      <th className="py-2.5 px-3.5">Invoice #</th>
                      <th className="py-2.5 px-3.5">Issue Date</th>
                      <th className="py-2.5 px-3.5">Due Date</th>
                      <th className="py-2.5 px-3.5 text-right">Total Amount</th>
                      <th className="py-2.5 px-3.5 text-right">Balance Due</th>
                      <th className="py-2.5 px-3.5">Status</th>
                      <th className="py-2.5 px-3.5 text-right">View</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {invoices.map((inv) => (
                      <tr key={inv.id} className="hover:bg-slate-50/60 transition-colors">
                        <td className="py-2.5 px-3.5 font-semibold text-brand-600">
                          <Link to={`/invoices/${inv.id}`} className="hover:underline">
                            {inv.invoice_number}
                          </Link>
                        </td>
                        <td className="py-2.5 px-3.5">{formatDate(inv.issue_date)}</td>
                        <td className="py-2.5 px-3.5">{formatDate(inv.due_date)}</td>
                        <td className="py-2.5 px-3.5 text-right font-medium tabular-nums">
                          {formatMoney(inv.total, inv.currency)}
                        </td>
                        <td className="py-2.5 px-3.5 text-right font-medium tabular-nums text-slate-900">
                          {formatMoney(inv.amount_due, inv.currency)}
                        </td>
                        <td className="py-2.5 px-3.5">
                          <Badge variant={statusVariant(inv.status)} dot size="sm">
                            {humanize(inv.status)}
                          </Badge>
                        </td>
                        <td className="py-2.5 px-3.5 text-right">
                          <Link
                            to={`/invoices/${inv.id}`}
                            className="text-slate-400 hover:text-brand-600 p-1 inline-block"
                          >
                            <ArrowLeft className="w-3.5 h-3.5 rotate-180" />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Customer & Plan info & Schedule */}
        <div className="space-y-6">
          {/* Customer Card */}
          <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
                <User className="w-4 h-4 text-brand-600" />
                Customer
              </h2>
              {subscription.customer?.id && (
                <Link
                  to={`/customers/${subscription.customer.id}`}
                  className="text-xs text-brand-600 hover:underline font-medium"
                >
                  View Profile →
                </Link>
              )}
            </div>

            <div className="space-y-2 text-xs">
              <div className="font-semibold text-slate-900 text-sm">
                {subscription.customer?.display_name || '—'}
              </div>
              <div className="text-slate-500 font-mono text-[11px]">
                {subscription.customer?.customer_number}
              </div>
              {subscription.customer?.email && (
                <div className="flex items-center gap-1.5 text-slate-600">
                  <Mail className="w-3.5 h-3.5 text-slate-400" />
                  {subscription.customer.email}
                </div>
              )}
            </div>
          </div>

          {/* Plan & Product Card */}
          <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
                <Package className="w-4 h-4 text-brand-600" />
                Plan & Product
              </h2>
              <Link to="/catalog" className="text-xs text-brand-600 hover:underline font-medium">
                Catalog →
              </Link>
            </div>

            <div className="space-y-2 text-xs">
              <div>
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                  Product
                </span>
                <span className="font-medium text-slate-900">
                  {subscription.plan?.product_name || 'Subscription Product'}
                </span>
              </div>
              <div>
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                  Plan Name & Code
                </span>
                <span className="font-semibold text-slate-900">
                  {subscription.plan?.name} <span className="text-slate-400 font-mono text-[11px]">({subscription.plan?.code})</span>
                  {subscription.plan?.source === 'offering' && (
                    <span className="ml-1.5 text-[10px] font-semibold text-indigo-700 bg-indigo-50 border border-indigo-100 rounded px-1.5 py-0.5">
                      Plans &amp; Pricing{subscription.plan?.offering_pricing_model ? ` · ${subscription.plan.offering_pricing_model}` : ''}
                    </span>
                  )}
                </span>
              </div>
              <div>
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                  Billing Interval
                </span>
                <span className="font-medium text-slate-800 capitalize">
                  {subscription.plan?.billing_interval} (x{subscription.plan?.interval_count})
                </span>
              </div>
            </div>
          </div>

          {/* Billing Timeline & Schedule */}
          <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 space-y-3">
            <h2 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
              <Calendar className="w-4 h-4 text-brand-600" />
              Lifecycle & Schedule
            </h2>

            <div className="space-y-3 text-xs divide-y divide-slate-100">
              <div className="pt-1 flex justify-between">
                <span className="text-slate-500">Contract Start</span>
                <span className="font-medium text-slate-900">{formatDate(subscription.start_date)}</span>
              </div>

              {isTrialing && subscription.trial_end && (
                <div className="pt-2 flex justify-between text-sky-700 bg-sky-50/50 p-1.5 rounded">
                  <span className="font-medium">Trial Period Ends</span>
                  <span className="font-bold">{formatDate(subscription.trial_end)}</span>
                </div>
              )}

              <div className="pt-2 flex justify-between">
                <span className="text-slate-500">Current Period Start</span>
                <span className="font-medium text-slate-900">{formatDate(subscription.current_period_start)}</span>
              </div>

              <div className="pt-2 flex justify-between">
                <span className="text-slate-500">Current Period End</span>
                <span className="font-medium text-slate-900">{formatDate(subscription.current_period_end)}</span>
              </div>

              <div className="pt-2 flex justify-between">
                <span className="text-slate-500">Next Scheduled Billing</span>
                <span className="font-semibold text-slate-900">
                  {subscription.next_billing_date ? formatDate(subscription.next_billing_date) : '—'}
                </span>
              </div>

              {subscription.paused_at && (
                <div className="pt-2 flex justify-between text-amber-700">
                  <span>Paused Date</span>
                  <span className="font-medium">{formatDate(subscription.paused_at)}</span>
                </div>
              )}

              {subscription.cancelled_at && (
                <div className="pt-2 flex justify-between text-rose-700">
                  <span>Cancelled Date</span>
                  <span className="font-medium">{formatDate(subscription.cancelled_at)}</span>
                </div>
              )}

              {subscription.cancellation_reason && (
                <div className="pt-2">
                  <span className="text-[11px] text-slate-500 uppercase tracking-wider block">Reason</span>
                  <p className="text-xs text-rose-700 mt-0.5">{subscription.cancellation_reason}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Action Modals */}
      {/* 1. Edit Subscription Modal */}
      <Modal
        isOpen={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        title="Edit Subscription"
        size="md"
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setEditModalOpen(false)} disabled={actionLoading}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={handleEditSave} isLoading={actionLoading}>
              Save Changes
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Quantity / Units
            </label>
            <input
              type="number"
              min={1}
              value={editQuantity}
              onChange={(e) => setEditQuantity(Math.max(1, parseInt(e.target.value) || 1))}
              className="w-full text-xs p-2.5 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="editAutoRenew"
              checked={editAutoRenewal}
              onChange={(e) => setEditAutoRenewal(e.target.checked)}
              className="w-4 h-4 rounded text-brand-600 border-slate-300 focus:ring-brand-500"
            />
            <label htmlFor="editAutoRenew" className="text-xs font-medium text-slate-700 cursor-pointer">
              Enable Automatic Renewal
            </label>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Contract Notes
            </label>
            <textarea
              value={editNotes}
              onChange={(e) => setEditNotes(e.target.value)}
              rows={3}
              className="w-full text-xs p-2.5 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
            />
          </div>
        </div>
      </Modal>

      {/* 2. Pause Dialog */}
      <ConfirmDialog
        isOpen={pauseModalOpen}
        onClose={() => setPauseModalOpen(false)}
        onConfirm={handlePauseConfirm}
        title="Pause Subscription"
        description="Are you sure you want to pause this subscription? Scheduled renewals and invoicing will be paused until resumed."
        confirmLabel="Pause"
        variant="default"
        isLoading={actionLoading}
      />

      {/* 3. Resume Dialog */}
      <ConfirmDialog
        isOpen={resumeModalOpen}
        onClose={() => setResumeModalOpen(false)}
        onConfirm={handleResumeConfirm}
        title="Resume Subscription"
        description="Reactivate billing cycle and resume automatic renewals for this subscription?"
        confirmLabel="Resume Subscription"
        variant="default"
        isLoading={actionLoading}
      />

      {/* 4. Renew Dialog */}
      <ConfirmDialog
        isOpen={renewModalOpen}
        onClose={() => setRenewModalOpen(false)}
        onConfirm={handleRenewConfirm}
        title="Advance Billing Period"
        description="Manually renew this subscription for the next billing cycle? This advances the active period and generates the renewal invoice."
        confirmLabel="Renew Now"
        variant="default"
        isLoading={actionLoading}
      />

      {/* 5. Cancel Modal */}
      <Modal
        isOpen={cancelModalOpen}
        onClose={() => setCancelModalOpen(false)}
        title="Cancel Subscription"
        size="md"
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setCancelModalOpen(false)} disabled={actionLoading}>
              Keep Active
            </Button>
            <Button variant="danger" size="sm" onClick={handleCancelConfirm} isLoading={actionLoading}>
              Confirm Cancellation
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Cancel subscription <span className="font-semibold text-slate-900">{subscription.subscription_number}</span>.
          </p>

          <div className="bg-slate-50 p-3 rounded-lg border border-slate-200/80 space-y-2">
            <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={cancelAtPeriodEnd}
                onChange={(e) => setCancelAtPeriodEnd(e.target.checked)}
                className="w-4 h-4 rounded text-brand-600 border-slate-300 focus:ring-brand-500"
              />
              <span>Cancel at period end ({formatDate(subscription.current_period_end)})</span>
            </label>
            <p className="text-[11px] text-slate-500 pl-6">
              If checked, customer retains access until the current cycle expires. If unchecked, subscription cancels immediately.
            </p>
            {!cancelAtPeriodEnd && (
              <>
                <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer pt-1">
                  <input
                    type="checkbox"
                    checked={prorateCredit}
                    onChange={(e) => setProrateCredit(e.target.checked)}
                    className="w-4 h-4 rounded text-brand-600 border-slate-300 focus:ring-brand-500"
                  />
                  <span>Issue a prorated credit note for the unused period</span>
                </label>
                <p className="text-[11px] text-slate-500 pl-6">
                  Credits the unused, already-invoiced remainder of the current period (with tax) to the customer.
                </p>
              </>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Cancellation Reason (Optional)
            </label>
            <textarea
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              placeholder="e.g. Churn reason, customer switched to custom solution"
              rows={3}
              className="w-full text-xs p-2.5 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
            />
          </div>
        </div>
      </Modal>

      {/* 6. Generate Invoice Dialog */}
      <ConfirmDialog
        isOpen={generateInvoiceModalOpen}
        onClose={() => setGenerateInvoiceModalOpen(false)}
        onConfirm={handleGenerateInvoiceConfirm}
        title="Generate Invoice"
        description={`Create an invoice for ${formatMoney(subscription.total_amount ?? subscription.mrr, subscription.currency || 'INR')} for the current subscription cycle?`}
        confirmLabel="Generate Invoice"
        variant="default"
        isLoading={actionLoading}
      />
    </div>
  );
}

export default SubscriptionDetailPage;
