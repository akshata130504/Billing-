import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Clock,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  Search,
  DollarSign,
  Repeat,
  XCircle,
  Eye,
  CalendarPlus,
  LifeBuoy,
} from 'lucide-react';
import { subscriptionService } from '../../services/subscriptionService';
import { catalogService } from '../../services/catalogService';
import type {
  PlanOut,
  SubscriptionOut,
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
import { formatMoney, formatDate } from '../../utils/format';

export function TrialsPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canWrite = hasRole('finance');

  const [trials, setTrials] = useState<SubscriptionOut[]>([]);
  const [summary, setSummary] = useState<SubscriptionSummaryOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Selected for action
  const [selectedTrial, setSelectedTrial] = useState<SubscriptionOut | null>(null);
  const [convertModalOpen, setConvertModalOpen] = useState(false);
  const [cancelModalOpen, setCancelModalOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [extendModalOpen, setExtendModalOpen] = useState(false);
  const [extendDays, setExtendDays] = useState('7');
  const [extendReason, setExtendReason] = useState('');
  const [fallbackModalOpen, setFallbackModalOpen] = useState(false);
  const [fallbackPlans, setFallbackPlans] = useState<PlanOut[]>([]);
  const [fallbackPlanId, setFallbackPlanId] = useState('');

  const errorMessage = (err: any) => err?.response?.data?.error?.message || err?.message || 'Request failed';

  const fetchSummary = async () => {
    try {
      const data = await subscriptionService.summary();
      setSummary(data);
    } catch {
      // Non-blocking
    }
  };

  const fetchTrials = useCallback(async () => {
    try {
      setLoading(true);
      const params: any = {
        status: 'trialing',
        page_size: 50,
      };
      if (searchQuery.trim()) {
        params.search = searchQuery.trim();
      }
      const data = await subscriptionService.list(params);
      setTrials(data.items);
    } catch (err: any) {
      showToast('error', 'Error', 'Failed to load trials');
    } finally {
      setLoading(false);
    }
  }, [searchQuery, showToast]);

  useEffect(() => {
    fetchSummary();
  }, []);

  useEffect(() => {
    fetchTrials();
  }, [fetchTrials]);

  const handleConvertConfirm = async () => {
    if (!selectedTrial) return;
    try {
      setActionLoading(true);
      // Trials convert through the trial service (/trials/{id}/convert): it records the
      // conversion, issues the first invoice and charges the default card when one is on
      // file. /subscriptions/{id}/activate only handles drafts and rejected trials.
      const result = await subscriptionService.convertTrial(selectedTrial.id);
      showToast(
        result.payment_succeeded || result.status === 'active' ? 'success' : 'warning',
        'Trial Converted',
        result.message || `Subscription ${selectedTrial.subscription_number} is now active and billed.`
      );
      setConvertModalOpen(false);
      setSelectedTrial(null);
      fetchTrials();
      fetchSummary();
    } catch (err: any) {
      showToast('error', 'Conversion Failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelConfirm = async () => {
    if (!selectedTrial) return;
    try {
      setActionLoading(true);
      await subscriptionService.cancel(selectedTrial.id, {
        at_period_end: false,
        reason: cancelReason.trim() || 'Trial expired / churned',
      });
      showToast('info', 'Trial Cancelled', `Trial ${selectedTrial.subscription_number} has been ended.`);
      setCancelModalOpen(false);
      setSelectedTrial(null);
      setCancelReason('');
      fetchTrials();
      fetchSummary();
    } catch (err: any) {
      showToast('error', 'Cancellation Failed', err.response?.data?.error?.message || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleExtendConfirm = async () => {
    if (!selectedTrial) return;
    const days = Number(extendDays);
    if (!Number.isInteger(days) || days < 1 || days > 365) {
      showToast('error', 'Invalid extension', 'Enter a whole number of days between 1 and 365.');
      return;
    }
    try {
      setActionLoading(true);
      const tp = await subscriptionService.extendTrial(selectedTrial.id, {
        days,
        reason: extendReason.trim() || undefined,
      });
      showToast('success', 'Trial Extended', `Trial now ends on ${formatDate(tp.trial_end_date)}.`);
      setExtendModalOpen(false);
      setSelectedTrial(null);
      setExtendReason('');
      fetchTrials();
      fetchSummary();
    } catch (err: any) {
      showToast('error', 'Extension Failed', errorMessage(err));
    } finally {
      setActionLoading(false);
    }
  };

  const openFallback = async (sub: SubscriptionOut) => {
    setSelectedTrial(sub);
    setFallbackPlanId('');
    setFallbackModalOpen(true);
    try {
      const data = await catalogService.listPlans({ is_active: true, page_size: 100 });
      // Only plans the subscription can legally move to: same currency, recurring.
      setFallbackPlans(
        data.items.filter(
          (p) =>
            p.id !== sub.plan?.id &&
            p.billing_interval !== 'one_time' &&
            p.currency === (sub.currency || sub.plan?.currency)
        )
      );
    } catch (err: any) {
      showToast('error', 'Error', 'Failed to load plans');
    }
  };

  const handleFallbackConfirm = async () => {
    if (!selectedTrial) return;
    try {
      setActionLoading(true);
      await subscriptionService.moveTrialToFallback(selectedTrial.id, fallbackPlanId || null);
      showToast('success', 'Moved to Fallback Plan', `Subscription ${selectedTrial.subscription_number} moved.`);
      setFallbackModalOpen(false);
      setSelectedTrial(null);
      fetchTrials();
      fetchSummary();
    } catch (err: any) {
      showToast('error', 'Fallback Failed', errorMessage(err));
    } finally {
      setActionLoading(false);
    }
  };

  // Helper to calculate days left
  const getDaysRemaining = (trialEnd: string | null | undefined) => {
    if (!trialEnd) return 0;
    const end = new Date(trialEnd);
    const now = new Date();
    const diff = Math.ceil((end.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
    return diff;
  };

  return (
    <div className="space-y-6 pb-16">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <button
            onClick={() => navigate('/subscriptions')}
            className="inline-flex items-center text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors mb-2"
          >
            <ArrowLeft className="w-3.5 h-3.5 mr-1" />
            Back to Subscriptions
          </button>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
            <Clock className="w-6 h-6 text-sky-600" />
            Trial Center & Pipeline
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Monitor active trial periods, track expiration timelines, and convert prospects into recurring revenue.
          </p>
        </div>

        <Button
          variant="primary"
          size="md"
          onClick={() => navigate('/subscriptions/new?trial=1')}
          leadingIcon={<Repeat className="w-4 h-4" />}
        >
          New Trial
        </Button>
      </div>

      {/* KPI Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Active Trials"
          value={summary?.trialing_count ?? 0}
          icon={<Clock className="w-5 h-5 text-sky-600" />}
          comparisonText="Potential customer pipeline"
        />
        <StatCard
          title="Expiring Within 7 Days"
          value={summary?.trial_expiring_soon_count ?? 0}
          icon={<AlertTriangle className="w-5 h-5 text-amber-600" />}
          comparisonText="High-priority conversion window"
        />
        <StatCard
          title="Total Subscriptions Base"
          value={summary?.total_subscriptions ?? 0}
          icon={<DollarSign className="w-5 h-5 text-brand-600" />}
          comparisonText={`${summary?.active_count ?? 0} currently paid & active`}
        />
      </div>

      {/* Trials Table Container */}
      <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h2 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Clock className="w-4 h-4 text-sky-600" />
            Active Trial Accounts
          </h2>

          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search customer, plan, or trial..."
              className="pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500/20 focus:border-sky-500 w-64 text-slate-900 placeholder:text-slate-400"
            />
          </div>
        </div>

        {loading ? (
          <div className="py-12">
            <LoadingState message="Loading active trials..." />
          </div>
        ) : trials.length === 0 ? (
          <div className="py-12">
            <EmptyState
              icon={<Clock className="w-10 h-10 text-slate-400" />}
              title="No active trials"
              description="There are currently no customers in an active trial evaluation period."
            />
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-200/80">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200 uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-4">Trial / Subscription</th>
                  <th className="py-3 px-4">Customer</th>
                  <th className="py-3 px-4">Plan & Terms</th>
                  <th className="py-3 px-4">Trial Window</th>
                  <th className="py-3 px-4">Timeline</th>
                  <th className="py-3 px-4 text-right">Potential MRR</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {trials.map((sub) => {
                  const daysLeft = getDaysRemaining(sub.trial_end);
                  const isExpiringSoon = daysLeft <= 3;

                  return (
                    <tr
                      key={sub.id}
                      className="hover:bg-slate-50/60 transition-colors cursor-pointer group"
                      onClick={() => navigate(`/subscriptions/${sub.id}`)}
                    >
                      <td className="py-3.5 px-4 font-semibold text-slate-900 group-hover:text-brand-600">
                        {sub.subscription_number}
                        <div className="text-[11px] text-slate-400 font-normal mt-0.5">
                          Started {formatDate(sub.trial_start || sub.start_date)}
                        </div>
                      </td>

                      <td className="py-3.5 px-4">
                        <div className="font-medium text-slate-900">{sub.customer?.display_name || '—'}</div>
                        <div className="text-[11px] text-slate-400">{sub.customer?.email || sub.customer?.customer_number || '—'}</div>
                      </td>

                      <td className="py-3.5 px-4">
                        <div className="font-medium text-slate-900">{sub.plan?.name}</div>
                        <div className="text-[11px] text-slate-500 capitalize">
                          {sub.quantity} units · {sub.plan?.billing_interval}
                        </div>
                      </td>

                      <td className="py-3.5 px-4">
                        <div className="text-slate-800">
                          {formatDate(sub.trial_start || sub.start_date)} → {formatDate(sub.trial_end)}
                        </div>
                      </td>

                      <td className="py-3.5 px-4">
                        {daysLeft > 0 ? (
                          <Badge variant={isExpiringSoon ? 'warning' : 'info'} dot size="sm">
                            {daysLeft} {daysLeft === 1 ? 'day' : 'days'} left
                          </Badge>
                        ) : (
                          <Badge variant="danger" dot size="sm">
                            Expired
                          </Badge>
                        )}
                      </td>

                      <td className="py-3.5 px-4 text-right font-semibold text-slate-900 tabular-nums">
                        {formatMoney(sub.mrr, sub.currency || 'INR')}
                      </td>

                      <td className="py-3.5 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1.5">
                          {canWrite && (
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => {
                                setSelectedTrial(sub);
                                setConvertModalOpen(true);
                              }}
                              leadingIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
                              className="text-[11px] py-1 px-2.5 h-7 bg-emerald-600 hover:bg-emerald-700"
                            >
                              Convert
                            </Button>
                          )}
                          {canWrite && (
                            <button
                              onClick={() => {
                                setSelectedTrial(sub);
                                setExtendDays('7');
                                setExtendModalOpen(true);
                              }}
                              className="p-1 text-slate-400 hover:text-sky-600 rounded transition-colors"
                              title="Extend Trial"
                            >
                              <CalendarPlus className="w-4 h-4" />
                            </button>
                          )}
                          {canWrite && (
                            <button
                              onClick={() => openFallback(sub)}
                              className="p-1 text-slate-400 hover:text-amber-600 rounded transition-colors"
                              title="Move to Fallback Plan"
                            >
                              <LifeBuoy className="w-4 h-4" />
                            </button>
                          )}
                          <button
                            onClick={() => navigate(`/subscriptions/${sub.id}`)}
                            className="p-1 text-slate-400 hover:text-brand-600 rounded transition-colors"
                            title="View Subscription"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          {canWrite && (
                            <button
                              onClick={() => {
                                setSelectedTrial(sub);
                                setCancelModalOpen(true);
                              }}
                              className="p-1 text-slate-400 hover:text-rose-600 rounded transition-colors"
                              title="Cancel Trial"
                            >
                              <XCircle className="w-4 h-4" />
                            </button>
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
      </div>

      {/* Convert to Paid Modal */}
      <ConfirmDialog
        isOpen={convertModalOpen}
        onClose={() => {
          setConvertModalOpen(false);
          setSelectedTrial(null);
        }}
        onConfirm={handleConvertConfirm}
        title="Convert Trial to Active Subscription"
        description={`Convert trial ${selectedTrial?.subscription_number} for customer ${selectedTrial?.customer?.display_name} to a paid active subscription? The first invoice is issued now and charged to the default card on file, if any.`}
        confirmLabel="Convert to Active"
        variant="default"
        isLoading={actionLoading}
      />

      {/* Extend Trial Modal */}
      <Modal
        isOpen={extendModalOpen}
        onClose={() => {
          setExtendModalOpen(false);
          setSelectedTrial(null);
        }}
        title="Extend Trial"
        size="md"
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setExtendModalOpen(false);
                setSelectedTrial(null);
              }}
              disabled={actionLoading}
            >
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={handleExtendConfirm} isLoading={actionLoading}>
              Extend Trial
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Current trial end for{' '}
            <span className="font-semibold text-slate-900">{selectedTrial?.subscription_number}</span>:{' '}
            {formatDate(selectedTrial?.trial_end)}
          </p>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Additional days</label>
            <input
              type="number"
              min={1}
              max={365}
              step={1}
              value={extendDays}
              onChange={(e) => setExtendDays(e.target.value)}
              className="w-32 text-xs p-2 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Reason (optional)</label>
            <input
              type="text"
              maxLength={255}
              value={extendReason}
              onChange={(e) => setExtendReason(e.target.value)}
              placeholder="e.g. Customer needs more time to evaluate"
              className="w-full text-xs p-2 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
            />
          </div>
        </div>
      </Modal>

      {/* Fallback Plan Modal */}
      <Modal
        isOpen={fallbackModalOpen}
        onClose={() => {
          setFallbackModalOpen(false);
          setSelectedTrial(null);
        }}
        title="Move Trial to Fallback Plan"
        size="md"
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setFallbackModalOpen(false);
                setSelectedTrial(null);
              }}
              disabled={actionLoading}
            >
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={handleFallbackConfirm} isLoading={actionLoading}>
              Move to Plan
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Ends the trial of <span className="font-semibold text-slate-900">{selectedTrial?.subscription_number}</span>{' '}
            and starts a new period on the selected plan. A paid plan invoices its first period immediately.
          </p>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Fallback plan</label>
            <select
              value={fallbackPlanId}
              onChange={(e) => setFallbackPlanId(e.target.value)}
              className="w-full text-xs p-2 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
            >
              <option value="">Configured fallback / free plan of this product</option>
              {fallbackPlans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.code}) - {formatMoney(p.unit_amount, p.currency)} / {p.billing_interval}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Modal>

      {/* Cancel Trial Modal */}
      <Modal
        isOpen={cancelModalOpen}
        onClose={() => {
          setCancelModalOpen(false);
          setSelectedTrial(null);
        }}
        title="End Trial"
        size="md"
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setCancelModalOpen(false);
                setSelectedTrial(null);
              }}
              disabled={actionLoading}
            >
              Keep Trial
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={handleCancelConfirm}
              isLoading={actionLoading}
            >
              End Trial
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Terminate trial for subscription <span className="font-semibold text-slate-900">{selectedTrial?.subscription_number}</span>.
          </p>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Feedback / Churn Reason
            </label>
            <textarea
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              placeholder="e.g. Prospect chose not to proceed after evaluation period"
              rows={3}
              className="w-full text-xs p-2.5 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900"
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default TrialsPage;
