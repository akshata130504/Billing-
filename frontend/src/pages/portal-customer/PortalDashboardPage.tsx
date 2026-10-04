import { toApiError } from '../../services/apiClient';
import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  DollarSign,
  FileText,
  Repeat,
  CreditCard,
  Download,
  ArrowRight,
  ShieldCheck,
  AlertTriangle,
} from 'lucide-react';
import {
  portalCustomerService,
  type PortalDashboardData,
} from '../../services/portalCustomerService';
import { LoadingState } from '../../components/common/LoadingState';
import { useToast } from '../../components/common/Toast';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';

export const PortalDashboardPage: React.FC = () => {
  const { showToast } = useToast();
  const [data, setData] = useState<PortalDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await portalCustomerService.getDashboard();
      setData(res);
    } catch (err) {
      setError(toApiError(err).message || 'Failed to load dashboard.');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPdf = async (invoiceId: string, invoiceNumber: string) => {
    try {
      setDownloadingId(invoiceId);
      await portalCustomerService.downloadInvoicePdf(invoiceId, invoiceNumber);
    } catch (err) {
      showToast('error', 'Failed to download invoice PDF', toApiError(err).message);
    } finally {
      setDownloadingId(null);
    }
  };

  if (loading) {
    return <LoadingState message="Loading your account summary..." />;
  }

  if (error || !data) {
    return (
      <div className="bg-white rounded-xl border border-rose-200 p-8 text-center max-w-lg mx-auto shadow-xs">
        <p className="text-sm text-rose-600 mb-4">{error || 'Unable to load dashboard'}</p>
        <Button variant="primary" onClick={loadDashboard}>
          Retry
        </Button>
      </div>
    );
  }

  const outstanding = Number(data.total_outstanding_amount || 0);
  const firstUnpaidInvoice = data.recent_invoices.find(
    (inv) => Number(inv.amount_due) > 0 && inv.public_token
  );

  return (
    <div className="space-y-8">
      {data.read_only_reason && (
        <div role="alert" className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <AlertTriangle className="w-5 h-5 shrink-0 text-amber-600" />
          <p>{data.read_only_reason}</p>
        </div>
      )}
      {/* Welcome Banner */}
      <div className="bg-gradient-to-r from-indigo-900 via-indigo-800 to-indigo-900 rounded-2xl p-6 sm:p-8 text-white shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <span className="text-xs font-semibold tracking-wider text-indigo-300 uppercase block mb-1">
            Account Overview
          </span>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Welcome, {data.customer_name}
          </h1>
          <p className="mt-1 text-sm text-indigo-200">
            View your latest billing activity, outstanding invoices, and active services.
          </p>
        </div>

        {outstanding > 0 && firstUnpaidInvoice && (
          <div className="shrink-0">
            <Button
              variant="primary"
              size="lg"
              className="bg-emerald-500 hover:bg-emerald-600 text-white font-semibold shadow-md border-0"
              onClick={() => window.open(`/pay/${firstUnpaidInvoice.public_token}`, '_blank')}
            >
              <CreditCard className="w-5 h-5 mr-2" />
              Pay Outstanding (₹{outstanding.toLocaleString()})
            </Button>
          </div>
        )}
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Outstanding Balance
            </span>
            <div className="p-2 rounded-lg bg-amber-50 text-amber-600">
              <DollarSign className="w-5 h-5" />
            </div>
          </div>
          <p className="mt-3 text-2xl font-bold text-slate-900">
            ₹{outstanding.toLocaleString()}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {data.open_invoices_count} pending {data.open_invoices_count === 1 ? 'invoice' : 'invoices'}
          </p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Open Invoices
            </span>
            <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
              <FileText className="w-5 h-5" />
            </div>
          </div>
          <p className="mt-3 text-2xl font-bold text-slate-900">
            {data.open_invoices_count}
          </p>
          <p className="mt-1 text-xs text-slate-500">Awaiting payment or processing</p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Active Subscriptions
            </span>
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
              <Repeat className="w-5 h-5" />
            </div>
          </div>
          <p className="mt-3 text-2xl font-bold text-slate-900">
            {data.active_subscriptions_count}
          </p>
          <p className="mt-1 text-xs text-slate-500">Active recurring service plans</p>
        </div>
      </div>

      {/* Recent Invoices Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Recent Invoices</h2>
            <p className="text-xs text-slate-500">Your most recent billing statements</p>
          </div>
          <Link
            to="/portal/invoices"
            className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
          >
            View All <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {data.recent_invoices.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-sm">
            No invoices found for your account.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="px-5 py-3">Invoice #</th>
                  <th className="px-5 py-3">Issue Date</th>
                  <th className="px-5 py-3">Due Date</th>
                  <th className="px-5 py-3">Total Amount</th>
                  <th className="px-5 py-3">Balance Due</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.recent_invoices.map((inv) => {
                  const due = Number(inv.amount_due);
                  const isUnpaid = due > 0 && inv.status !== 'void';
                  return (
                    <tr key={inv.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-5 py-3.5 font-semibold text-slate-900">
                        {inv.invoice_number}
                      </td>
                      <td className="px-5 py-3.5 text-slate-600">{inv.issue_date}</td>
                      <td className="px-5 py-3.5 text-slate-600">{inv.due_date}</td>
                      <td className="px-5 py-3.5 font-medium text-slate-900">
                        ₹{Number(inv.total).toLocaleString()}
                      </td>
                      <td className="px-5 py-3.5 font-semibold text-indigo-700">
                        ₹{due.toLocaleString()}
                      </td>
                      <td className="px-5 py-3.5">
                        <Badge
                          variant={
                            inv.status === 'paid'
                              ? 'success'
                              : inv.status === 'partially_paid'
                              ? 'warning'
                              : inv.status === 'overdue'
                              ? 'danger'
                              : 'neutral'
                          }
                        >
                          {inv.status.replace(/_/g, ' ')}
                        </Badge>
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={downloadingId === inv.id}
                            onClick={() => handleDownloadPdf(inv.id, inv.invoice_number)}
                            title="Download PDF"
                          >
                            <Download className="w-3.5 h-3.5" />
                          </Button>
                          {isUnpaid && inv.public_token && (
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => window.open(`/pay/${inv.public_token}`, '_blank')}
                            >
                              <CreditCard className="w-3.5 h-3.5 mr-1" /> Pay Now
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
      </div>

      {/* Active Subscriptions Summary */}
      {data.subscriptions.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
          <div className="p-5 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-slate-900">Active Subscriptions</h2>
              <p className="text-xs text-slate-500">Your recurring plans and services</p>
            </div>
            <Link
              to="/portal/subscriptions"
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
            >
              View Details <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="divide-y divide-slate-100">
            {data.subscriptions.map((sub) => (
              <div key={sub.id} className="p-5 flex items-center justify-between gap-4">
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    {sub.plan_name || 'Standard Plan'}
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Sub #{sub.subscription_number} • Renewal date: {sub.current_period_end}
                  </p>
                  {sub.trial_end && (
                    <p className="text-xs text-amber-600 font-medium mt-0.5">
                      Trial ends on {sub.trial_end}
                    </p>
                  )}
                </div>
                <Badge variant={sub.status === 'active' ? 'success' : 'warning'}>
                  {sub.status}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Security note */}
      <div className="p-4 rounded-xl bg-slate-100/70 border border-slate-200 flex items-center gap-3 text-xs text-slate-600">
        <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0" />
        <span>
          All payments and personal information are transmitted using 256-bit SSL encryption.
          Cards and UPI payments are processed by Razorpay.
        </span>
      </div>
    </div>
  );
};
