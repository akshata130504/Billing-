import { toApiError } from '../../services/apiClient';
import React, { useState, useEffect } from 'react';
import { CreditCard, Trash2, CheckCircle2, ShieldCheck, Star } from 'lucide-react';
import {
  portalCustomerService,
  type PortalPayment,
  type PortalSavedPaymentMethod,
} from '../../services/portalCustomerService';
import { LoadingState } from '../../components/common/LoadingState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { Badge } from '../../components/common/Badge';

export const PortalPaymentsPage: React.FC = () => {
  const [payments, setPayments] = useState<PortalPayment[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<PortalSavedPaymentMethod[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [processingMethodId, setProcessingMethodId] = useState<string | null>(null);
  const [methodToDelete, setMethodToDelete] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [pmts, methods] = await Promise.all([
        portalCustomerService.getPayments(),
        portalCustomerService.getPaymentMethods(),
      ]);
      setPayments(pmts);
      setPaymentMethods(methods);
    } catch (err) {
      setError(toApiError(err).message || 'Failed to load payments.');
    } finally {
      setLoading(false);
    }
  };

  const handleSetDefault = async (methodId: string) => {
    setProcessingMethodId(methodId);
    try {
      await portalCustomerService.setDefaultPaymentMethod(methodId);
      setActionSuccess('Default payment method updated.');
      const updatedMethods = await portalCustomerService.getPaymentMethods();
      setPaymentMethods(updatedMethods);
      setTimeout(() => setActionSuccess(null), 3000);
    } catch (err) {
      setError(toApiError(err).message || 'Failed to update default payment method.');
    } finally {
      setProcessingMethodId(null);
    }
  };

  const handleDeleteMethod = (methodId: string) => {
    setMethodToDelete(methodId);
  };

  const confirmDeleteMethod = async () => {
    const methodId = methodToDelete;
    if (!methodId) return;
    setMethodToDelete(null);
    setProcessingMethodId(methodId);
    try {
      await portalCustomerService.deletePaymentMethod(methodId);
      setActionSuccess('Payment method removed successfully.');
      const updatedMethods = await portalCustomerService.getPaymentMethods();
      setPaymentMethods(updatedMethods);
      setTimeout(() => setActionSuccess(null), 3000);
    } catch (err) {
      setError(toApiError(err).message || 'Failed to remove payment method.');
    } finally {
      setProcessingMethodId(null);
    }
  };

  if (loading) {
    return <LoadingState message="Loading your payment details..." />;
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Payments & Billing Methods</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Manage saved payment cards and view transaction history
        </p>
      </div>

      {actionSuccess && (
        <div className="flex items-center gap-2 p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700">
          {error}
        </div>
      )}

      {/* Saved Payment Methods Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <CreditCard className="w-4 h-4 text-indigo-600" /> Saved Payment Methods
          </h2>
          <span className="flex items-center gap-1 text-[11px] text-slate-500">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> PCI-DSS Tokenized
          </span>
        </div>

        {paymentMethods.length === 0 ? (
          <div className="p-6 bg-white rounded-xl border border-slate-200 text-center text-xs text-slate-500">
            No saved cards or payment methods found on file.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {paymentMethods.map((m) => (
              <div
                key={m.id}
                className="p-4 bg-white rounded-xl border border-slate-200 shadow-2xs space-y-3 flex flex-col justify-between"
              >
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-xs text-slate-800 uppercase">
                      {m.card_brand || m.type}
                    </span>
                    {m.is_default && (
                      <Badge variant="primary" size="sm">
                        Default
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm font-mono text-slate-700 font-medium">
                    •••• •••• •••• {m.last4 || '••••'}
                  </p>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                  {!m.is_default ? (
                    <button
                      type="button"
                      disabled={processingMethodId === m.id}
                      onClick={() => handleSetDefault(m.id)}
                      className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1 disabled:opacity-50"
                    >
                      <Star className="w-3 h-3" /> Set Default
                    </button>
                  ) : (
                    <span className="text-[11px] text-slate-400">Primary Method</span>
                  )}
                  <button
                    type="button"
                    disabled={processingMethodId === m.id}
                    onClick={() => handleDeleteMethod(m.id)}
                    className="text-xs text-rose-600 hover:text-rose-800 font-medium flex items-center gap-1 disabled:opacity-50"
                  >
                    <Trash2 className="w-3.5 h-3.5" /> Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Payment Transactions Table */}
      <div className="space-y-3">
        <h2 className="text-base font-bold text-slate-900">Payment History</h2>
        <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
          {payments.length === 0 ? (
            <div className="p-12 text-center text-slate-400 text-sm">
              <CreditCard className="w-8 h-8 mx-auto text-slate-300 mb-2" />
              No payment records found for your account.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-100">
                  <tr>
                    <th className="px-5 py-3">Payment #</th>
                    <th className="px-5 py-3">Date</th>
                    <th className="px-5 py-3">Amount</th>
                    <th className="px-5 py-3">Method</th>
                    <th className="px-5 py-3">Gateway</th>
                    <th className="px-5 py-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {payments.map((p) => (
                    <tr key={p.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-5 py-3.5 font-semibold text-slate-900">
                        {p.payment_number}
                      </td>
                      <td className="px-5 py-3.5 text-slate-600">
                        {p.created_at ? p.created_at.split('T')[0] : '—'}
                      </td>
                      <td className="px-5 py-3.5 font-bold text-slate-900">
                        ₹{Number(p.amount).toLocaleString()}
                      </td>
                      <td className="px-5 py-3.5 text-slate-600 capitalize">
                        {p.method.replace(/_/g, ' ')}
                      </td>
                      <td className="px-5 py-3.5 text-slate-500 uppercase text-xs font-medium">
                        {p.gateway}
                      </td>
                      <td className="px-5 py-3.5">
                        <Badge
                          variant={
                            p.status === 'succeeded'
                              ? 'success'
                              : p.status === 'pending'
                              ? 'warning'
                              : 'danger'
                          }
                        >
                          {p.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
      <ConfirmDialog
        isOpen={Boolean(methodToDelete)}
        onClose={() => setMethodToDelete(null)}
        onConfirm={() => void confirmDeleteMethod()}
        title="Remove payment method"
        description="Are you sure you want to remove this saved payment method?"
        confirmLabel="Remove"
        variant="danger"
      />
    </div>
  );
};
