import React, { useState, useEffect } from 'react';
import { CreditCard } from 'lucide-react';
import {
  portalCustomerService,
  type PortalPayment,
} from '../../services/portalCustomerService';
import { LoadingState } from '../../components/common/LoadingState';
import { Badge } from '../../components/common/Badge';

export const PortalPaymentsPage: React.FC = () => {
  const [payments, setPayments] = useState<PortalPayment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadPayments();
  }, []);

  const loadPayments = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await portalCustomerService.getPayments();
      setPayments(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load payments.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <LoadingState message="Loading your payment history..." />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Payments</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Complete history of all transactions and payments recorded for your account
        </p>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700">
          {error}
        </div>
      )}

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
  );
};
