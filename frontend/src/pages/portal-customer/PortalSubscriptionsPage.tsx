import { toApiError } from '../../services/apiClient';
import React, { useState, useEffect } from 'react';
import { Repeat } from 'lucide-react';
import {
  portalCustomerService,
  type PortalSubscription,
} from '../../services/portalCustomerService';
import { LoadingState } from '../../components/common/LoadingState';
import { Badge } from '../../components/common/Badge';

export const PortalSubscriptionsPage: React.FC = () => {
  const [subscriptions, setSubscriptions] = useState<PortalSubscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSubscriptions();
  }, []);

  const loadSubscriptions = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await portalCustomerService.getSubscriptions();
      setSubscriptions(data);
    } catch (err) {
      setError(toApiError(err).message || 'Failed to load subscriptions.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <LoadingState message="Loading your subscriptions..." />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Subscriptions</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Overview of your active subscription plans, service periods, and renewals
        </p>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700">
          {error}
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
        {subscriptions.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            <Repeat className="w-8 h-8 mx-auto text-slate-300 mb-2" />
            No active subscriptions found for your account.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="px-5 py-3">Subscription #</th>
                  <th className="px-5 py-3">Plan Name</th>
                  <th className="px-5 py-3">Seats / Qty</th>
                  <th className="px-5 py-3">Current Period</th>
                  <th className="px-5 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {subscriptions.map((sub) => (
                  <tr key={sub.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-5 py-3.5 font-semibold text-slate-900">
                      {sub.subscription_number}
                    </td>
                    <td className="px-5 py-3.5 font-medium text-slate-900">
                      {sub.plan_name || 'Standard Plan'}
                      {sub.trial_end && (
                        <span className="block text-xs text-amber-600 font-normal">
                          Trial ends {sub.trial_end}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-slate-600">{sub.quantity}</td>
                    <td className="px-5 py-3.5 text-slate-600 text-xs">
                      {sub.current_period_start} to {sub.current_period_end}
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge
                        variant={
                          sub.status === 'active'
                            ? 'success'
                            : sub.status === 'trialing'
                            ? 'warning'
                            : sub.status === 'cancelled'
                            ? 'danger'
                            : 'neutral'
                        }
                      >
                        {sub.status}
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
