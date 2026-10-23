import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Building2,
  Mail,
  Phone,
  CreditCard,
  Clock,
  FileText,
  Repeat,
  DollarSign,
  Timer,
  CheckCircle2,
  SlidersHorizontal,
  ExternalLink,
} from 'lucide-react';
import { lifecycleService } from '../../services/lifecycleService';
import type {
  CustomerLifecycleDetail,
  CustomerLifecycleStage,
  CustomerLifecycleUpdate,
  HealthStatus,
} from '../../types/api';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { LoadingState } from '../../components/common/LoadingState';
import { EmptyState } from '../../components/common/EmptyState';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatMoney, formatDate, humanize } from '../../utils/format';

const STAGE_ORDER: CustomerLifecycleStage[] = [
  'prospect',
  'onboarding',
  'active',
  'renewal_due',
  'expansion',
];

export function CustomerLifecycleDetailPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canWrite = hasRole('finance') || hasRole('admin');

  const [detail, setDetail] = useState<CustomerLifecycleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('timeline');

  // Stage update modal
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editStage, setEditStage] = useState<CustomerLifecycleStage>('active');
  const [editHealth, setEditHealth] = useState<HealthStatus>('healthy');
  const [editScore, setEditScore] = useState<number>(85);
  const [editNextAction, setEditNextAction] = useState<string>('');
  const [editNotes, setEditNotes] = useState<string>('');

  const loadDetail = useCallback(async () => {
    if (!customerId) return;
    try {
      setLoading(true);
      const data = await lifecycleService.get(customerId);
      setDetail(data);
      setEditStage(data.lifecycle.lifecycle_stage);
      setEditHealth(data.lifecycle.health_status);
      setEditScore(data.lifecycle.health_score);
      setEditNextAction(data.lifecycle.next_action || '');
      setEditNotes(data.lifecycle.notes || '');
    } catch (err: any) {
      showToast('error', 'Error', err.message || 'Failed to load customer lifecycle details');
    } finally {
      setLoading(false);
    }
  }, [customerId, showToast]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const handleSaveStage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerId) return;
    try {
      setActionLoading(true);
      const updatePayload: CustomerLifecycleUpdate = {
        lifecycle_stage: editStage,
        health_status: editHealth,
        health_score: editScore,
        next_action: editNextAction || null,
        notes: editNotes || null,
      };
      await lifecycleService.update(customerId, updatePayload);
      showToast('success', 'Lifecycle Updated', 'Customer lifecycle updated successfully');
      setEditModalOpen(false);
      loadDetail();
    } catch (err: any) {
      showToast('error', 'Update Failed', err.message || 'Failed to update lifecycle');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="py-24">
        <LoadingState message="Loading customer 360° lifecycle..." />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="py-16 text-center">
        <EmptyState
          title="Customer Not Found"
          description="The requested customer lifecycle profile could not be located."
          action={
            <Button variant="primary" onClick={() => navigate('/customer-lifecycle')}>
              Return to Customer Lifecycle
            </Button>
          }
        />
      </div>
    );
  }

  const { customer, lifecycle, timeline, subscriptions, quotes, invoices, payments, timesheet_summary } = detail;
  const currentStageIndex = STAGE_ORDER.indexOf(lifecycle.lifecycle_stage);

  return (
    <div className="space-y-6 pb-16">
      {/* Breadcrumb & Navigation */}
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
        <Link to="/customer-lifecycle" className="hover:text-blue-600 transition-colors">
          Customer Lifecycle
        </Link>
        <span>/</span>
        <span className="text-slate-900 font-semibold">{customer.display_name}</span>
      </div>

      {/* Main Header Banner */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 rounded-2xl bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 font-bold text-xl flex-shrink-0">
            {customer.display_name.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-2xl font-bold text-slate-900">{customer.display_name}</h1>
              <Badge variant="neutral">{customer.customer_number}</Badge>
              <Badge
                variant={
                  lifecycle.lifecycle_stage === 'active'
                    ? 'success'
                    : lifecycle.lifecycle_stage === 'at_risk'
                    ? 'danger'
                    : lifecycle.lifecycle_stage === 'renewal_due'
                    ? 'warning'
                    : 'info'
                }
              >
                {humanize(lifecycle.lifecycle_stage)}
              </Badge>
            </div>
            <div className="flex items-center gap-4 text-xs text-slate-500 mt-2 flex-wrap">
              {customer.company_name && (
                <div className="flex items-center gap-1">
                  <Building2 className="w-3.5 h-3.5 text-slate-400" />
                  <span>{customer.company_name}</span>
                </div>
              )}
              {customer.email && (
                <div className="flex items-center gap-1">
                  <Mail className="w-3.5 h-3.5 text-slate-400" />
                  <span>{customer.email}</span>
                </div>
              )}
              {customer.phone && (
                <div className="flex items-center gap-1">
                  <Phone className="w-3.5 h-3.5 text-slate-400" />
                  <span>{customer.phone}</span>
                </div>
              )}
              <div className="flex items-center gap-1">
                <CreditCard className="w-3.5 h-3.5 text-slate-400" />
                <span>Terms: {customer.payment_terms_days} days ({customer.currency})</span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => navigate(`/customers/${customer.id}`)}>
            <ExternalLink className="w-4 h-4 mr-1.5" />
            Customer Record
          </Button>
          {canWrite && (
            <Button variant="primary" size="sm" onClick={() => setEditModalOpen(true)}>
              <SlidersHorizontal className="w-4 h-4 mr-1.5" />
              Update Stage & Health
            </Button>
          )}
        </div>
      </div>

      {/* Lifecycle Stage Progress Bar */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
            Lifecycle Journey
          </h2>
          <span className="text-xs text-slate-500">
            Stage entered: {formatDate(lifecycle.stage_entered_at)}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 pt-2">
          {STAGE_ORDER.map((stage, idx) => {
            const isCompleted = currentStageIndex > idx;
            const isCurrent = lifecycle.lifecycle_stage === stage;
            return (
              <div
                key={stage}
                className={`p-3 rounded-xl border text-center transition-all ${
                  isCurrent
                    ? 'bg-blue-50 border-blue-300 ring-2 ring-blue-500/20 shadow-sm'
                    : isCompleted
                    ? 'bg-emerald-50/60 border-emerald-200 text-emerald-900'
                    : 'bg-slate-50 border-slate-200 text-slate-400'
                }`}
              >
                <div className="flex items-center justify-center gap-1 text-xs font-semibold">
                  {isCompleted ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  ) : (
                    <span className="w-4 h-4 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center text-[10px]">
                      {idx + 1}
                    </span>
                  )}
                  <span className={isCurrent ? 'text-blue-900' : isCompleted ? 'text-emerald-800' : 'text-slate-500'}>
                    {humanize(stage)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* High-Level Overview Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-1">
          <div className="text-xs font-medium text-slate-500">Account Health</div>
          <div className="flex items-center justify-between pt-1">
            <span className="text-2xl font-bold text-slate-900">{lifecycle.health_score}%</span>
            <Badge
              variant={
                lifecycle.health_status === 'healthy'
                  ? 'success'
                  : lifecycle.health_status === 'critical'
                  ? 'danger'
                  : 'warning'
              }
            >
              {humanize(lifecycle.health_status)}
            </Badge>
          </div>
          <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden mt-2">
            <div
              className={`h-full ${
                lifecycle.health_score >= 80
                  ? 'bg-emerald-500'
                  : lifecycle.health_score >= 50
                  ? 'bg-amber-500'
                  : 'bg-rose-500'
              }`}
              style={{ width: `${lifecycle.health_score}%` }}
            />
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-1">
          <div className="text-xs font-medium text-slate-500">Total Settled Revenue</div>
          <div className="text-2xl font-bold text-slate-900 pt-1">
            {formatMoney(lifecycle.total_spent)}
          </div>
          <div className="text-xs text-slate-400">
            From {lifecycle.total_invoices_count} invoices generated
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-1">
          <div className="text-xs font-medium text-slate-500">Outstanding Balance</div>
          <div className={`text-2xl font-bold pt-1 ${parseFloat(lifecycle.amount_due) > 0 ? 'text-rose-600' : 'text-slate-900'}`}>
            {formatMoney(lifecycle.amount_due)}
          </div>
          <div className="text-xs text-slate-400">
            {parseFloat(lifecycle.amount_due) > 0 ? 'Payment collection required' : 'Account in good standing'}
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-1">
          <div className="text-xs font-medium text-slate-500">Billable Time Logged</div>
          <div className="text-2xl font-bold text-slate-900 pt-1">
            {timesheet_summary.billable_hours} hrs
          </div>
          <div className="text-xs text-slate-400">
            Value: {formatMoney(timesheet_summary.billable_amount)} ({timesheet_summary.total_entries} entries)
          </div>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="border-b border-slate-200 flex items-center gap-6 text-sm font-medium">
        <button
          onClick={() => setActiveTab('timeline')}
          className={`pb-3 border-b-2 flex items-center gap-2 transition-colors ${
            activeTab === 'timeline'
              ? 'border-blue-600 text-blue-600 font-semibold'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          }`}
        >
          <Clock className="w-4 h-4" />
          <span>Activity Timeline ({timeline.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('subscriptions')}
          className={`pb-3 border-b-2 flex items-center gap-2 transition-colors ${
            activeTab === 'subscriptions'
              ? 'border-blue-600 text-blue-600 font-semibold'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          }`}
        >
          <Repeat className="w-4 h-4" />
          <span>Subscriptions ({subscriptions.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('quotes')}
          className={`pb-3 border-b-2 flex items-center gap-2 transition-colors ${
            activeTab === 'quotes'
              ? 'border-blue-600 text-blue-600 font-semibold'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          }`}
        >
          <FileText className="w-4 h-4" />
          <span>Quotes ({quotes.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('invoices')}
          className={`pb-3 border-b-2 flex items-center gap-2 transition-colors ${
            activeTab === 'invoices'
              ? 'border-blue-600 text-blue-600 font-semibold'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          }`}
        >
          <DollarSign className="w-4 h-4" />
          <span>Invoices ({invoices.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('payments')}
          className={`pb-3 border-b-2 flex items-center gap-2 transition-colors ${
            activeTab === 'payments'
              ? 'border-blue-600 text-blue-600 font-semibold'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          }`}
        >
          <CreditCard className="w-4 h-4" />
          <span>Payments ({payments.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('timesheets')}
          className={`pb-3 border-b-2 flex items-center gap-2 transition-colors ${
            activeTab === 'timesheets'
              ? 'border-blue-600 text-blue-600 font-semibold'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          }`}
        >
          <Timer className="w-4 h-4" />
          <span>Timesheets ({timesheet_summary.total_entries})</span>
        </button>
      </div>

      {/* Tab Contents */}
      {activeTab === 'timeline' && (
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-slate-900">Chronological Lifecycle Events</h3>
            <span className="text-xs text-slate-400">All events aggregated from real system activity</span>
          </div>

          {timeline.length === 0 ? (
            <EmptyState
              title="No events recorded"
              description="Events will appear here as quotes, invoices, and payments occur."
              icon={<Clock className="w-8 h-8 text-slate-400" />}
            />
          ) : (
            <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
              {timeline.map((evt) => (
                <div key={evt.id} className="relative group">
                  <div className="absolute -left-6 top-1 w-5 h-5 rounded-full bg-white border-2 border-blue-500 flex items-center justify-center text-blue-500 group-hover:scale-110 transition-transform">
                    <div className="w-1.5 h-1.5 bg-blue-600 rounded-full" />
                  </div>
                  <div className="bg-slate-50/70 hover:bg-slate-50 p-4 rounded-xl border border-slate-200/80 transition-colors">
                    <div className="flex items-center justify-between gap-4 flex-wrap">
                      <div className="font-semibold text-slate-900 text-sm">{evt.title}</div>
                      <div className="flex items-center gap-2">
                        {evt.status && (
                          <Badge variant="neutral" className="text-[10px]">
                            {evt.status.toUpperCase()}
                          </Badge>
                        )}
                        <span className="text-xs text-slate-400">{formatDate(evt.timestamp)}</span>
                      </div>
                    </div>
                    {evt.description && (
                      <p className="text-xs text-slate-600 mt-1">{evt.description}</p>
                    )}
                    <div className="text-[10px] text-slate-400 mt-2 flex items-center gap-2">
                      <span>Actor: {evt.actor_label || 'System'}</span>
                      {evt.related_entity_type && (
                        <>
                          <span>•</span>
                          <span>Entity: {evt.related_entity_type}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'subscriptions' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 bg-slate-50/80 border-b border-slate-200 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900">Active & Historical Subscriptions</h3>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/subscriptions/new?customer_id=${customer.id}`)}
            >
              Add Subscription
            </Button>
          </div>
          {subscriptions.length === 0 ? (
            <div className="py-12">
              <EmptyState
                title="No subscriptions"
                description="No recurring subscriptions exist for this customer yet."
                icon={<Repeat className="w-8 h-8 text-slate-400" />}
              />
            </div>
          ) : (
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-semibold text-slate-500 uppercase">
                <tr>
                  <th className="px-5 py-3">Subscription #</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Frequency</th>
                  <th className="px-5 py-3">Amount</th>
                  <th className="px-5 py-3">Period End</th>
                  <th className="px-5 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {subscriptions.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50">
                    <td className="px-5 py-3 font-semibold text-slate-900">{s.subscription_number}</td>
                    <td className="px-5 py-3"><Badge variant="info">{s.status}</Badge></td>
                    <td className="px-5 py-3 capitalize">{s.billing_frequency}</td>
                    <td className="px-5 py-3 font-medium">{formatMoney(s.total_amount)}</td>
                    <td className="px-5 py-3">{s.current_period_end ? formatDate(s.current_period_end) : '—'}</td>
                    <td className="px-5 py-3 text-right">
                      <Link to={`/subscriptions/${s.id}`} className="text-blue-600 hover:underline text-xs font-medium">
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {activeTab === 'quotes' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 bg-slate-50/80 border-b border-slate-200 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900">Proposals & Quotes</h3>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/quotes/new?customer_id=${customer.id}`)}
            >
              Create Quote
            </Button>
          </div>
          {quotes.length === 0 ? (
            <div className="py-12">
              <EmptyState title="No quotes" description="No quotes recorded for this customer." icon={<FileText className="w-8 h-8 text-slate-400" />} />
            </div>
          ) : (
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-semibold text-slate-500 uppercase">
                <tr>
                  <th className="px-5 py-3">Quote #</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Total</th>
                  <th className="px-5 py-3">Issue Date</th>
                  <th className="px-5 py-3">Expiry Date</th>
                  <th className="px-5 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {quotes.map((q) => (
                  <tr key={q.id} className="hover:bg-slate-50">
                    <td className="px-5 py-3 font-semibold text-slate-900">{q.quote_number}</td>
                    <td className="px-5 py-3"><Badge variant="neutral">{q.status}</Badge></td>
                    <td className="px-5 py-3 font-medium">{formatMoney(q.total)}</td>
                    <td className="px-5 py-3">{q.issue_date ? formatDate(q.issue_date) : '—'}</td>
                    <td className="px-5 py-3">{q.expiry_date ? formatDate(q.expiry_date) : '—'}</td>
                    <td className="px-5 py-3 text-right">
                      <Link to={`/quotes/${q.id}`} className="text-blue-600 hover:underline text-xs font-medium">
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {activeTab === 'invoices' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 bg-slate-50/80 border-b border-slate-200 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900">Issued Invoices</h3>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/invoices/new?customer_id=${customer.id}`)}
            >
              Issue Invoice
            </Button>
          </div>
          {invoices.length === 0 ? (
            <div className="py-12">
              <EmptyState title="No invoices" description="No invoices issued for this customer yet." icon={<DollarSign className="w-8 h-8 text-slate-400" />} />
            </div>
          ) : (
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-semibold text-slate-500 uppercase">
                <tr>
                  <th className="px-5 py-3">Invoice #</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Total</th>
                  <th className="px-5 py-3">Paid</th>
                  <th className="px-5 py-3">Due</th>
                  <th className="px-5 py-3">Due Date</th>
                  <th className="px-5 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {invoices.map((inv) => (
                  <tr key={inv.id} className="hover:bg-slate-50">
                    <td className="px-5 py-3 font-semibold text-slate-900">{inv.invoice_number}</td>
                    <td className="px-5 py-3"><Badge variant="info">{inv.status}</Badge></td>
                    <td className="px-5 py-3 font-medium">{formatMoney(inv.total)}</td>
                    <td className="px-5 py-3 text-emerald-600 font-medium">{formatMoney(inv.amount_paid)}</td>
                    <td className="px-5 py-3 text-rose-600 font-medium">{formatMoney(inv.amount_due)}</td>
                    <td className="px-5 py-3">{inv.due_date ? formatDate(inv.due_date) : '—'}</td>
                    <td className="px-5 py-3 text-right">
                      <Link to={`/invoices/${inv.id}`} className="text-blue-600 hover:underline text-xs font-medium">
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {activeTab === 'payments' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 bg-slate-50/80 border-b border-slate-200 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900">Payment Transactions</h3>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/payments`)}
            >
              All Payments
            </Button>
          </div>
          {payments.length === 0 ? (
            <div className="py-12">
              <EmptyState title="No payments" description="No payment transactions recorded yet." icon={<CreditCard className="w-8 h-8 text-slate-400" />} />
            </div>
          ) : (
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-semibold text-slate-500 uppercase">
                <tr>
                  <th className="px-5 py-3">Payment #</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Amount</th>
                  <th className="px-5 py-3">Method</th>
                  <th className="px-5 py-3">Date</th>
                  <th className="px-5 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {payments.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50">
                    <td className="px-5 py-3 font-semibold text-slate-900">{p.payment_number}</td>
                    <td className="px-5 py-3"><Badge variant="success">{p.status}</Badge></td>
                    <td className="px-5 py-3 font-medium text-slate-900">{formatMoney(p.amount)}</td>
                    <td className="px-5 py-3 capitalize">{p.method}</td>
                    <td className="px-5 py-3">{p.payment_date ? formatDate(p.payment_date) : '—'}</td>
                    <td className="px-5 py-3 text-right">
                      <Link to={`/payments/${p.id}`} className="text-blue-600 hover:underline text-xs font-medium">
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {activeTab === 'timesheets' && (
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-slate-900">Project & Timesheet Logs</h3>
              <p className="text-xs text-slate-500 mt-0.5">Hours tracked against this customer's projects</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/timesheets?customer_id=${customer.id}`)}
            >
              Open Timesheet Module
            </Button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
              <div className="text-xs text-slate-500 font-medium">Total Tracked</div>
              <div className="text-xl font-bold text-slate-900 mt-1">{timesheet_summary.total_hours} hrs</div>
            </div>
            <div className="p-4 bg-emerald-50/60 rounded-xl border border-emerald-200">
              <div className="text-xs text-emerald-700 font-medium">Billable Value</div>
              <div className="text-xl font-bold text-emerald-900 mt-1">{formatMoney(timesheet_summary.billable_amount)}</div>
            </div>
            <div className="p-4 bg-amber-50/60 rounded-xl border border-amber-200">
              <div className="text-xs text-amber-700 font-medium">Unbilled Amount</div>
              <div className="text-xl font-bold text-amber-900 mt-1">{formatMoney(timesheet_summary.unbilled_amount)}</div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-semibold text-slate-500 uppercase">
                <tr>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Project</th>
                  <th className="px-4 py-3">Description</th>
                  <th className="px-4 py-3">Hours</th>
                  <th className="px-4 py-3">Billable</th>
                  <th className="px-4 py-3">Amount</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {timesheet_summary.recent_entries.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">{t.date ? formatDate(t.date) : '—'}</td>
                    <td className="px-4 py-3 font-medium text-slate-900">{t.project_name}</td>
                    <td className="px-4 py-3 max-w-xs truncate text-xs">{t.description}</td>
                    <td className="px-4 py-3 font-semibold text-slate-900">{t.duration_hours}h</td>
                    <td className="px-4 py-3">
                      <Badge variant={t.billable ? 'success' : 'neutral'}>
                        {t.billable ? 'Billable' : 'Non-billable'}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 font-medium">{formatMoney(t.billable_amount)}</td>
                    <td className="px-4 py-3 capitalize"><Badge variant="info">{t.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Stage Update Modal */}
      {editModalOpen && (
        <Modal
          isOpen={editModalOpen}
          onClose={() => setEditModalOpen(false)}
          title={`Update Lifecycle: ${customer.display_name}`}
        >
          <form onSubmit={handleSaveStage} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Lifecycle Stage
              </label>
              <select
                value={editStage}
                onChange={(e) => setEditStage(e.target.value as CustomerLifecycleStage)}
                className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              >
                <option value="prospect">Prospect</option>
                <option value="onboarding">Onboarding</option>
                <option value="active">Active Customer</option>
                <option value="renewal_due">Renewal Due</option>
                <option value="expansion">Expansion / Upsell</option>
                <option value="at_risk">At Risk</option>
                <option value="churned">Churned</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Health Status
                </label>
                <select
                  value={editHealth}
                  onChange={(e) => setEditHealth(e.target.value as HealthStatus)}
                  className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                >
                  <option value="healthy">Healthy</option>
                  <option value="neutral">Neutral</option>
                  <option value="at_risk">At Risk</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Health Score (0 - 100%)
                </label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={editScore}
                  onChange={(e) => setEditScore(parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Next Expected Action
              </label>
              <input
                type="text"
                placeholder="e.g. Follow up on renewal terms"
                value={editNextAction}
                onChange={(e) => setEditNextAction(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Internal Account Notes
              </label>
              <textarea
                rows={3}
                placeholder="Internal notes on account status..."
                value={editNotes}
                onChange={(e) => setEditNotes(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
              <Button variant="ghost" size="sm" type="button" onClick={() => setEditModalOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" type="submit" disabled={actionLoading}>
                {actionLoading ? 'Saving...' : 'Save Lifecycle'}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
