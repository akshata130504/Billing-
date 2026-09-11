import React, { useState, useEffect } from 'react';
import { Building2, MapPin, User } from 'lucide-react';
import {
  portalCustomerService,
  type PortalProfileData,
} from '../../services/portalCustomerService';
import { LoadingState } from '../../components/common/LoadingState';
import { Badge } from '../../components/common/Badge';

export const PortalProfilePage: React.FC = () => {
  const [profile, setProfile] = useState<PortalProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await portalCustomerService.getProfile();
      setProfile(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load profile.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <LoadingState message="Loading your profile details..." />;
  }

  if (error || !profile) {
    return (
      <div className="p-8 text-center text-rose-600 bg-white rounded-xl border border-rose-200">
        {error || 'Unable to load profile.'}
      </div>
    );
  }

  const { customer, user, contacts } = profile;

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Profile & Billing Details</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Your registered business information and portal user credentials
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Company & Billing Info */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-2xs space-y-4">
          <div className="flex items-center gap-3 pb-3 border-b border-slate-100">
            <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">{customer.display_name}</h2>
              <span className="text-xs text-slate-500">Customer #{customer.customer_number}</span>
            </div>
          </div>

          <div className="space-y-2.5 text-xs text-slate-700">
            {customer.company_name && (
              <div className="flex justify-between py-1 border-b border-slate-50">
                <span className="text-slate-500">Legal Entity</span>
                <span className="font-semibold">{customer.company_name}</span>
              </div>
            )}
            {customer.email && (
              <div className="flex justify-between py-1 border-b border-slate-50">
                <span className="text-slate-500">Billing Email</span>
                <span className="font-medium">{customer.email}</span>
              </div>
            )}
            {customer.phone && (
              <div className="flex justify-between py-1 border-b border-slate-50">
                <span className="text-slate-500">Phone</span>
                <span className="font-medium">{customer.phone}</span>
              </div>
            )}
            {customer.gstin && (
              <div className="flex justify-between py-1 border-b border-slate-50">
                <span className="text-slate-500">GSTIN</span>
                <span className="font-mono font-semibold">{customer.gstin}</span>
              </div>
            )}
            {customer.pan && (
              <div className="flex justify-between py-1 border-b border-slate-50">
                <span className="text-slate-500">PAN</span>
                <span className="font-mono font-semibold">{customer.pan}</span>
              </div>
            )}
            <div className="flex justify-between py-1">
              <span className="text-slate-500">Billing Currency</span>
              <span className="font-semibold">{customer.currency || 'INR'}</span>
            </div>
          </div>
        </div>

        {/* Billing Address Card */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-2xs space-y-4">
          <div className="flex items-center gap-3 pb-3 border-b border-slate-100">
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
              <MapPin className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">Billing Address</h2>
              <span className="text-xs text-slate-500">Address used on tax invoices</span>
            </div>
          </div>

          <div className="text-xs text-slate-700 leading-relaxed">
            {customer.billing_address_line1 ? (
              <address className="not-italic space-y-1">
                <p>{customer.billing_address_line1}</p>
                {customer.billing_address_line2 && <p>{customer.billing_address_line2}</p>}
                <p>
                  {[customer.billing_city, customer.billing_state, customer.billing_postal_code]
                    .filter(Boolean)
                    .join(', ')}
                </p>
                <p className="font-semibold text-slate-900">{customer.billing_country || 'India'}</p>
              </address>
            ) : (
              <p className="text-slate-400 italic">No billing address specified on record.</p>
            )}
          </div>
        </div>
      </div>

      {/* Portal User Account */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-2xs space-y-4">
        <div className="flex items-center gap-3 pb-3 border-b border-slate-100">
          <div className="p-2 rounded-lg bg-violet-50 text-violet-600">
            <User className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900">Portal Account User</h2>
            <span className="text-xs text-slate-500">Your portal sign-in credentials</span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs text-slate-700">
          <div className="p-3 bg-slate-50 rounded-lg">
            <span className="text-slate-500 block mb-0.5">Display Name</span>
            <span className="font-semibold text-slate-900">{user.display_name}</span>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg">
            <span className="text-slate-500 block mb-0.5">Login Email</span>
            <span className="font-semibold text-slate-900">{user.email}</span>
          </div>
        </div>
      </div>

      {/* Customer Contacts */}
      {contacts.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-2xs space-y-4">
          <h2 className="text-base font-bold text-slate-900">Registered Contacts</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {contacts.map((c) => (
              <div
                key={c.id}
                className="p-3.5 border border-slate-100 rounded-lg bg-slate-50/50 space-y-1 text-xs"
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-900">{c.name}</span>
                  {c.is_primary && (
                    <Badge variant="primary" size="sm">
                      Primary
                    </Badge>
                  )}
                </div>
                {c.designation && <p className="text-slate-500">{c.designation}</p>}
                {c.email && <p className="text-slate-600 font-medium">{c.email}</p>}
                {c.phone && <p className="text-slate-600">{c.phone}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
