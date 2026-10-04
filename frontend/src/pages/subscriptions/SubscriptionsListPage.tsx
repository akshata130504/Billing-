import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Repeat,
  Plus,
  Search,
  DollarSign,
  TrendingUp,
  Clock,
  PauseCircle,
  XCircle,
  FileText,
  Eye,
  RefreshCw,
  AlertCircle,
  ShieldCheck,
  MoreVertical,
  Layers,
} from 'lucide-react';
import { LegacyPlansManager } from './LegacyPlansManager';
import { subscriptionService } from '../../services/subscriptionService';
import type {
  SubscriptionOut,
  SubscriptionStatus,
  SubscriptionSummaryOut,
} from '../../types/api';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { StatCard } from '../../components/common/StatCard';
import { LoadingState } from '../../components/common/LoadingState';
import { EmptyState } from '../../components/common/EmptyState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatMoney, formatDate, humanize, statusVariant } from '../../utils/format';

export function SubscriptionsListPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canWrite = hasRole('finance');
  const [plansManagerOpen, setPlansManagerOpen] = useState(false);

  const [subscriptions, setSubscriptions] = useState<SubscriptionOut[]>([]);
  const [summary, setSummary] = useState<SubscriptionSummaryOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [activeTab, setActiveTab] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Selected subscription for lifecycle actions
  const [selectedSub, setSelectedSub] = useState<SubscriptionOut | null>(null);
  const [pauseModalOpen, setPauseModalOpen] = useState(false);
  const [resumeModalOpen, setResumeModalOpen] = useState(false);
  const [renewModalOpen, setRenewModalOpen] = useState(false);
  const [cancelModalOpen, setCancelModalOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelAtPeriodEnd, setCancelAtPeriodEnd] = useState(false);
  const [generateInvoiceModalOpen, setGenerateInvoiceModalOpen] = useState(false);
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);

  const fetchSummary = async () => {
    try {
      const data = await subscriptionService.summary();
      setSummary(data);
    } catch {
      // Non-blocking summary error
    }
  };

  const fetchSubscriptions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params: any = {
        page,
        page_size: 20,
      };
      if (activeTab === 'draft') {
        // The list renders pending_activation rows as drafts and the summary's draft_count
        // includes them, so the Draft tab lists both statuses.
        params.status = 'draft,pending_activation';
      } else if (activeTab !== 'all') {
        params.status = activeTab as SubscriptionStatus;
      }
      if (searchQuery.trim()) {
        params.search = searchQuery.trim();
      }
      const data = await subscriptionService.list(params);
      setSubscriptions(data.items);
      setTotalCount(data.total);
    } catch (err: any) {
      setError(err.response?.data?.error?.message || err.message || 'Failed to load subscriptions');
    } finally {
      setLoading(false);
    }
  }, [activeTab, searchQuery, page]);

  useEffect(() => {
    fetchSummary();
  }, []);

  useEffect(() => {
    fetchSubscriptions();
  }, [fetchSubscriptions]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchSubscriptions();
  };

  const handleActivate = async (sub: SubscriptionOut) => {
    try {
      setActionLoading(true);
      await subscriptionService.activate(sub.id);
      showToast('success', 'Subscription activated', `Subscription ${sub.subscription_number} is now active.`);
      fetchSubscriptions();
      fetchSummary();
    } catch (err: any) {
      showToast('error', 'Activation failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
      setActiveMenuId(null);
    }
  };

  const handlePauseConfirm = async () => {
    if (!selectedSub) return;
    try {
      setActionLoading(true);
      await subscriptionService.pause(selectedSub.id);
      showToast('warning', 'Subscription paused', `Subscription ${selectedSub.subscription_number} has been paused.`);
      setPauseModalOpen(false);
      setSelectedSub(null);
      fetchSubscriptions();
      fetchSummary();
    } catch (err: any) {
      showToast('error', 'Pause failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResumeConfirm = async () => {
    if (!selectedSub) return;
    try {
      setActionLoading(true);
      await subscriptionService.resume(selectedSub.id);
      showToast('success', 'Subscription resumed', `Subscription ${selectedSub.subscription_number} is now active.`);
      setResumeModalOpen(false);
      setSelectedSub(null);
      fetchSubscriptions();
      fetchSummary();
    } catch (err: any) {
      showToast('error', 'Resume failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRenewConfirm = async () => {
    if (!selectedSub) return;
    try {
      setActionLoading(true);
      await subscriptionService.renew(selectedSub.id);
      showToast('success', 'Subscription renewed', `Subscription ${selectedSub.subscription_number} renewed and period advanced.`);
      setRenewModalOpen(false);
      setSelectedSub(null);
      fetchSubscriptions();
      fetchSummary();
    } catch (err: any) {
      showToast('error', 'Renewal failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelConfirm = async () => {
    if (!selectedSub) return;
    try {
      setActionLoading(true);
      await subscriptionService.cancel(selectedSub.id, {
        at_period_end: cancelAtPeriodEnd,
        reason: cancelReason.trim() || undefined,
      });
      showToast(
        'info',
        cancelAtPeriodEnd ? 'Cancellation scheduled' : 'Subscription cancelled',
        cancelAtPeriodEnd
          ? `Subscription ${selectedSub.subscription_number} will end on ${formatDate(selectedSub.current_period_end)}.`
          : `Subscription ${selectedSub.subscription_number} was cancelled immediately.`
      );
      setCancelModalOpen(false);
      setSelectedSub(null);
      setCancelReason('');
      fetchSubscriptions();
      fetchSummary();
    } catch (err: any) {
      showToast('error', 'Cancellation failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleGenerateInvoiceConfirm = async () => {
    if (!selectedSub) return;
    try {
      setActionLoading(true);
      const inv = await subscriptionService.generateInvoice(selectedSub.id);
      showToast('success', 'Invoice generated', `Invoice ${inv.invoice_number} created for subscription.`);
      setGenerateInvoiceModalOpen(false);
      setSelectedSub(null);
      fetchSubscriptions();
    } catch (err: any) {
      showToast('error', 'Invoice generation failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const tabs = [
    { id: 'all', label: 'All Subscriptions', count: summary?.total_subscriptions },
    { id: 'active', label: 'Active', count: summary?.active_count },
    { id: 'trialing', label: 'Trialing', count: summary?.trialing_count },
    { id: 'paused', label: 'Paused', count: summary?.paused_count },
    { id: 'past_due', label: 'Past Due', count: summary?.past_due_count },
    { id: 'cancelled', label: 'Cancelled', count: summary?.cancelled_count },
    { id: 'draft', label: 'Draft', count: summary?.draft_count },
  ];

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
            <Repeat className="w-7 h-7 text-brand-600" />
            Subscriptions
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage recurring customer subscriptions, billing intervals, and commercial contracts.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="md"
            onClick={() => navigate('/trials')}
            leadingIcon={<Clock className="w-4 h-4 text-sky-600" />}
          >
            Trial Center
          </Button>
          <Button
            variant="outline"
            size="md"
            onClick={() => setPlansManagerOpen(true)}
            leadingIcon={<Layers className="w-4 h-4 text-brand-600" />}
          >
            Plans &amp; Products
          </Button>
          {canWrite && (
            <Button
              variant="primary"
              size="md"
              onClick={() => navigate('/subscriptions/new')}
              leadingIcon={<Plus className="w-4 h-4" />}
              className="shadow-sm"
            >
              New Subscription
            </Button>
          )}
        </div>
      </div>

      {/* KPI Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Monthly Recurring (MRR)"
          value={formatMoney(summary?.total_mrr ?? 0)}
          icon={<DollarSign className="w-5 h-5 text-brand-600" />}
          comparisonText="Active recurring base"
        />
        <StatCard
          title="Annual Recurring (ARR)"
          value={formatMoney(summary?.total_arr ?? 0)}
          icon={<TrendingUp className="w-5 h-5 text-emerald-600" />}
          comparisonText="Normalized annualized run-rate"
        />
        <StatCard
          title="Active Subscriptions"
          value={summary?.active_count ?? 0}
          icon={<ShieldCheck className="w-5 h-5 text-emerald-600" />}
          comparisonText={`${summary?.auto_renew_enabled_count ?? 0} with auto-renewal`}
        />
        <StatCard
          title="Active Trials"
          value={summary?.trialing_count ?? 0}
          icon={<Clock className="w-5 h-5 text-sky-600" />}
          comparisonText={`${summary?.trial_expiring_soon_count ?? 0} ending this week`}
        />
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-4 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          {/* Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 scrollbar-none">
            {tabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => {
                    setActiveTab(tab.id);
                    setPage(1);
                  }}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 ${
                    isActive
                      ? 'bg-brand-50 text-brand-700 border border-brand-200/60 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50 border border-transparent'
                  }`}
                >
                  <span>{tab.label}</span>
                  {tab.count !== undefined && tab.count > 0 && (
                    <span
                      className={`text-[11px] px-1.5 py-0.2 rounded-full font-bold ${
                        isActive ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {tab.count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Search */}
          <form onSubmit={handleSearchSubmit} className="flex items-center gap-2 shrink-0">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search number, customer, plan..."
                className="pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 w-64 text-slate-900 placeholder:text-slate-400"
              />
            </div>
            <Button type="submit" variant="outline" size="sm">
              Search
            </Button>
          </form>
        </div>

        {/* Data Table */}
        {loading ? (
          <div className="py-12">
            <LoadingState message="Loading subscriptions..." />
          </div>
        ) : error ? (
          <div className="p-8 text-center bg-rose-50/50 rounded-xl border border-rose-100 text-rose-700">
            <AlertCircle className="w-8 h-8 mx-auto mb-2 text-rose-500" />
            <p className="font-semibold text-sm">{error}</p>
            <Button variant="outline" size="sm" onClick={() => fetchSubscriptions()} className="mt-3">
              Retry
            </Button>
          </div>
        ) : subscriptions.length === 0 ? (
          <div className="py-12">
            <EmptyState
              icon={<Repeat className="w-10 h-10 text-slate-400" />}
              title="No subscriptions found"
              description={
                searchQuery || activeTab !== 'all'
                  ? 'No subscriptions match your current filters.'
                  : 'Get started by creating your first recurring customer subscription.'
              }
              action={
                canWrite && !searchQuery && activeTab === 'all' ? (
                  <Button
                    variant="primary"
                    size="md"
                    onClick={() => navigate('/subscriptions/new')}
                    leadingIcon={<Plus className="w-4 h-4" />}
                  >
                    Create Subscription
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-200/80">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50/80 text-slate-600 font-semibold border-b border-slate-200 uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-4">Subscription</th>
                  <th className="py-3 px-4">Customer</th>
                  <th className="py-3 px-4">Plan & Terms</th>
                  <th className="py-3 px-4">Billing Schedule</th>
                  <th className="py-3 px-4 text-right">Amount / Period</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700 font-normal">
                {subscriptions.map((sub) => {
                  const isDraft = sub.status === 'draft' || sub.status === 'pending_activation';
                  const isActive = sub.status === 'active';
                  const isTrialing = sub.status === 'trialing';
                  const isPaused = sub.status === 'paused';
                  const isCancelled = sub.status === 'cancelled' || sub.status === 'expired';

                  return (
                    <tr
                      key={sub.id}
                      className="hover:bg-slate-50/60 transition-colors group cursor-pointer"
                      onClick={() => navigate(`/subscriptions/${sub.id}`)}
                    >
                      {/* Subscription Number */}
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-slate-900 group-hover:text-brand-600 transition-colors flex items-center gap-1.5">
                          {sub.subscription_number}
                          {sub.auto_renewal && (
                            <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-medium">
                              Auto
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          Created {formatDate(sub.created_at)}
                        </div>
                      </td>

                      {/* Customer */}
                      <td className="py-3.5 px-4">
                        <div className="font-medium text-slate-900 truncate max-w-[180px]">
                          {sub.customer?.display_name || '—'}
                        </div>
                        <div className="text-[11px] text-slate-400 truncate max-w-[180px]">
                          {sub.customer?.email || sub.customer?.customer_number || '—'}
                        </div>
                      </td>

                      {/* Plan */}
                      <td className="py-3.5 px-4">
                        <div className="font-medium text-slate-900">
                          {sub.plan?.name || '—'}
                        </div>
                        <div className="text-[11px] text-slate-500 capitalize">
                          {sub.quantity} {sub.quantity === 1 ? 'unit' : 'units'} · {sub.billing_frequency || sub.plan?.billing_interval}
                        </div>
                      </td>

                      {/* Schedule */}
                      <td className="py-3.5 px-4">
                        <div className="text-slate-800">
                          {formatDate(sub.current_period_start)} → {formatDate(sub.current_period_end)}
                        </div>
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          {sub.next_billing_date
                            ? `Next invoice: ${formatDate(sub.next_billing_date)}`
                            : isTrialing && sub.trial_end
                            ? `Trial ends: ${formatDate(sub.trial_end)}`
                            : isPaused
                            ? 'Paused'
                            : 'No future billing'}
                        </div>
                      </td>

                      {/* Amount */}
                      <td className="py-3.5 px-4 text-right">
                        <div className="font-semibold text-slate-900 tabular-nums">
                          {formatMoney(sub.total_amount ?? sub.mrr, sub.currency || 'INR')}
                        </div>
                        <div className="text-[11px] text-slate-400">
                          MRR: {formatMoney(sub.mrr, sub.currency || 'INR')}
                        </div>
                      </td>

                      {/* Status */}
                      <td className="py-3.5 px-4">
                        <Badge variant={statusVariant(sub.status)} dot size="sm">
                          {humanize(sub.status)}
                        </Badge>
                        {sub.cancel_at_period_end && !isCancelled && (
                          <div className="text-[10px] text-rose-600 font-medium mt-1">
                            Cancels at end
                          </div>
                        )}
                      </td>

                      {/* Actions */}
                      <td
                        className="py-3.5 px-4 text-right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => navigate(`/subscriptions/${sub.id}`)}
                            className="p-1 text-slate-400 hover:text-brand-600 hover:bg-slate-100 rounded transition-colors"
                            title="View Subscription"
                          >
                            <Eye className="w-4 h-4" />
                          </button>

                          {/* Quick Action Button */}
                          {isDraft && canWrite && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleActivate(sub)}
                              className="text-[11px] py-1 px-2.5 h-7 text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                            >
                              Activate
                            </Button>
                          )}

                          {isActive && canWrite && (
                            <div className="relative inline-block text-left">
                              <button
                                onClick={() => setActiveMenuId(activeMenuId === sub.id ? null : sub.id)}
                                className="p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors"
                              >
                                <MoreVertical className="w-4 h-4" />
                              </button>

                              {activeMenuId === sub.id && (
                                <div className="origin-top-right absolute right-0 mt-2 w-44 rounded-xl shadow-lg bg-white ring-1 ring-black ring-opacity-5 z-20 py-1 divide-y divide-slate-100">
                                  <div className="py-1">
                                    <button
                                      onClick={() => {
                                        setActiveMenuId(null);
                                        setSelectedSub(sub);
                                        setGenerateInvoiceModalOpen(true);
                                      }}
                                      className="flex items-center gap-2 px-4 py-2 text-xs text-slate-700 hover:bg-slate-50 w-full text-left"
                                    >
                                      <FileText className="w-3.5 h-3.5 text-brand-600" />
                                      Generate Invoice
                                    </button>
                                    <button
                                      onClick={() => {
                                        setActiveMenuId(null);
                                        setSelectedSub(sub);
                                        setRenewModalOpen(true);
                                      }}
                                      className="flex items-center gap-2 px-4 py-2 text-xs text-slate-700 hover:bg-slate-50 w-full text-left"
                                    >
                                      <RefreshCw className="w-3.5 h-3.5 text-emerald-600" />
                                      Renew Period
                                    </button>
                                    <button
                                      onClick={() => {
                                        setActiveMenuId(null);
                                        setSelectedSub(sub);
                                        setPauseModalOpen(true);
                                      }}
                                      className="flex items-center gap-2 px-4 py-2 text-xs text-amber-700 hover:bg-amber-50 w-full text-left"
                                    >
                                      <PauseCircle className="w-3.5 h-3.5 text-amber-600" />
                                      Pause Subscription
                                    </button>
                                  </div>
                                  <div className="py-1">
                                    <button
                                      onClick={() => {
                                        setActiveMenuId(null);
                                        setSelectedSub(sub);
                                        setCancelModalOpen(true);
                                      }}
                                      className="flex items-center gap-2 px-4 py-2 text-xs text-rose-700 hover:bg-rose-50 w-full text-left"
                                    >
                                      <XCircle className="w-3.5 h-3.5 text-rose-600" />
                                      Cancel Subscription
                                    </button>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}

                          {isPaused && canWrite && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setSelectedSub(sub);
                                setResumeModalOpen(true);
                              }}
                              className="text-[11px] py-1 px-2.5 h-7 text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                            >
                              Resume
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination summary */}
        {!loading && subscriptions.length > 0 && (
          <div className="flex items-center justify-between text-xs text-slate-500 pt-2 px-1">
            <div>
              Showing <span className="font-semibold text-slate-800">{subscriptions.length}</span> of{' '}
              <span className="font-semibold text-slate-800">{totalCount}</span> subscriptions
            </div>
            {totalCount > 20 && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <span className="text-xs px-2 font-medium text-slate-700">Page {page}</span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page * 20 >= totalCount}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action Modals */}
      {/* 1. Pause Dialog */}
      <ConfirmDialog
        isOpen={pauseModalOpen}
        onClose={() => {
          setPauseModalOpen(false);
          setSelectedSub(null);
        }}
        onConfirm={handlePauseConfirm}
        title="Pause Subscription"
        description={`Are you sure you want to pause subscription ${selectedSub?.subscription_number}? Billing and renewals will be suspended until resumed.`}
        confirmLabel="Pause Subscription"
        variant="default"
        isLoading={actionLoading}
      />

      {/* 2. Resume Dialog */}
      <ConfirmDialog
        isOpen={resumeModalOpen}
        onClose={() => {
          setResumeModalOpen(false);
          setSelectedSub(null);
        }}
        onConfirm={handleResumeConfirm}
        title="Resume Subscription"
        description={`Resume subscription ${selectedSub?.subscription_number}? Active billing and scheduled renewals will restart immediately.`}
        confirmLabel="Resume Subscription"
        variant="default"
        isLoading={actionLoading}
      />

      {/* 3. Renew Dialog */}
      <ConfirmDialog
        isOpen={renewModalOpen}
        onClose={() => {
          setRenewModalOpen(false);
          setSelectedSub(null);
        }}
        onConfirm={handleRenewConfirm}
        title="Renew Subscription Period"
        description={`Manually advance billing cycle for subscription ${selectedSub?.subscription_number}? This will generate the next period's invoice if billing schedule is active.`}
        confirmLabel="Renew Now"
        variant="default"
        isLoading={actionLoading}
      />

      {/* 4. Cancel Modal */}
      <Modal
        isOpen={cancelModalOpen}
        onClose={() => {
          setCancelModalOpen(false);
          setSelectedSub(null);
        }}
        title="Cancel Subscription"
        size="md"
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setCancelModalOpen(false);
                setSelectedSub(null);
              }}
              disabled={actionLoading}
            >
              Keep Active
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={handleCancelConfirm}
              isLoading={actionLoading}
            >
              Confirm Cancellation
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Cancel subscription <span className="font-semibold text-slate-900">{selectedSub?.subscription_number}</span>.
          </p>

          <div className="bg-slate-50 p-3 rounded-lg border border-slate-200/80 space-y-2">
            <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={cancelAtPeriodEnd}
                onChange={(e) => setCancelAtPeriodEnd(e.target.checked)}
                className="w-4 h-4 rounded text-brand-600 border-slate-300 focus:ring-brand-500"
              />
              <span>Cancel at period end ({formatDate(selectedSub?.current_period_end)})</span>
            </label>
            <p className="text-[11px] text-slate-500 pl-6">
              If checked, customer retains access until the end of the current billing cycle. Otherwise, cancellation is immediate.
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Cancellation Reason (Optional)
            </label>
            <textarea
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              placeholder="e.g. Customer budget reduction, requested churn, etc."
              rows={3}
              className="w-full text-xs p-2.5 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
            />
          </div>
        </div>
      </Modal>

      {/* 5. Generate Invoice Dialog */}
      <ConfirmDialog
        isOpen={generateInvoiceModalOpen}
        onClose={() => {
          setGenerateInvoiceModalOpen(false);
          setSelectedSub(null);
        }}
        onConfirm={handleGenerateInvoiceConfirm}
        title="Generate Subscription Invoice"
        description={`Create an invoice for subscription ${selectedSub?.subscription_number} using agreed pricing snapshot of ${formatMoney(selectedSub?.total_amount ?? selectedSub?.mrr, selectedSub?.currency || 'INR')}?`}
        confirmLabel="Generate Invoice"
        variant="default"
        isLoading={actionLoading}
      />

      <LegacyPlansManager isOpen={plansManagerOpen} onClose={() => setPlansManagerOpen(false)} />
    </div>
  );
}

export default SubscriptionsListPage;
