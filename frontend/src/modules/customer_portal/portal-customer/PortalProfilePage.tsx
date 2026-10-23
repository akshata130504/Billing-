import { toApiError } from '../../../services/apiClient';
import React, { useState, useEffect } from 'react';
import { Building2, MapPin, User, Edit3, ShieldAlert, CheckCircle2, Lock } from 'lucide-react';
import {
  portalCustomerService,
  type PortalProfileData,
  type PortalProfileUpdate,
} from '../../../services/portalCustomerService';
import { LoadingState } from '../../../components/common/LoadingState';
import { Badge } from '../../../components/common/Badge';
import { Button } from '../../../components/common/Button';
import { Input } from '../../../components/common/Input';
import { Modal } from '../../../components/common/Modal';

export const PortalProfilePage: React.FC = () => {
  const [profile, setProfile] = useState<PortalProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Edit modal state
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState<PortalProfileUpdate>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await portalCustomerService.getProfile();
      setProfile(data);
    } catch (err) {
      setError(toApiError(err).message || 'Failed to load profile.');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenEdit = () => {
    if (!profile) return;
    setEditForm({
      display_name: profile.customer.display_name || '',
      email: profile.customer.email || '',
      phone: profile.customer.phone || '',
      website: profile.customer.website || '',
      billing_address_line1: profile.customer.billing_address_line1 || '',
      billing_address_line2: profile.customer.billing_address_line2 || '',
      billing_city: profile.customer.billing_city || '',
      billing_state: profile.customer.billing_state || '',
      billing_postal_code: profile.customer.billing_postal_code || '',
      billing_country: profile.customer.billing_country || 'India',
      user_display_name: profile.user.display_name || '',
    });
    setIsEditing(true);
  };

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const updated = await portalCustomerService.updateProfile(editForm);
      setProfile(updated);
      setIsEditing(false);
      setSuccessMessage('Profile and contact information updated successfully.');
      setTimeout(() => setSuccessMessage(null), 4000);
    } catch (err) {
      setError(toApiError(err).message || 'Failed to update profile.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <LoadingState message="Loading your profile details..." />;
  }

  if (error && !profile) {
    return (
      <div className="p-8 text-center text-rose-600 bg-white rounded-xl border border-rose-200">
        {error || 'Unable to load profile.'}
      </div>
    );
  }

  if (!profile) return null;

  const { customer, user, contacts } = profile;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Profile & Billing Details</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Your registered business information and portal user credentials
          </p>
        </div>
        <Button
          type="button"
          variant="primary"
          size="sm"
          onClick={handleOpenEdit}
          leadingIcon={<Edit3 className="w-3.5 h-3.5" />}
        >
          Edit Contact Info
        </Button>
      </div>

      {successMessage && (
        <div className="flex items-center gap-2 p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 p-3.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-800">
          <ShieldAlert className="w-4 h-4 text-rose-600 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

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
                <span className="text-slate-500 flex items-center gap-1">
                  Legal Entity <Lock className="w-3 h-3 text-slate-400" />
                </span>
                <span className="font-semibold">{customer.company_name}</span>
              </div>
            )}
            <div className="flex justify-between py-1 border-b border-slate-50">
              <span className="text-slate-500">Billing Email</span>
              <span className="font-medium text-slate-800">{customer.email || '—'}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-50">
              <span className="text-slate-500">Phone</span>
              <span className="font-medium text-slate-800">{customer.phone || '—'}</span>
            </div>
            {customer.gstin && (
              <div className="flex justify-between py-1 border-b border-slate-50">
                <span className="text-slate-500 flex items-center gap-1">
                  GSTIN <Lock className="w-3 h-3 text-slate-400" />
                </span>
                <span className="font-mono font-semibold text-slate-900">{customer.gstin}</span>
              </div>
            )}
            {customer.pan && (
              <div className="flex justify-between py-1 border-b border-slate-50">
                <span className="text-slate-500 flex items-center gap-1">
                  PAN <Lock className="w-3 h-3 text-slate-400" />
                </span>
                <span className="font-mono font-semibold text-slate-900">{customer.pan}</span>
              </div>
            )}
            <div className="flex justify-between py-1">
              <span className="text-slate-500">Billing Currency</span>
              <span className="font-semibold text-slate-900">{customer.currency || 'INR'}</span>
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

      {/* Edit Profile Modal */}
      <Modal
        isOpen={isEditing}
        onClose={() => setIsEditing(false)}
        title="Edit Contact & Address Details"
        size="lg"
      >
        <form onSubmit={handleSaveProfile} className="space-y-4">
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-[11px] text-slate-600 space-y-1">
            <div className="flex items-center gap-1.5 font-semibold text-slate-800">
              <Lock className="w-3.5 h-3.5 text-slate-500" />
              Tax & Legal Information Protected
            </div>
            <p>
              Fields such as Legal Entity ({customer.company_name || 'N/A'}), GSTIN ({customer.gstin || 'None'}), and PAN are locked for compliance.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input
              label="Primary Contact / Display Name"
              value={editForm.display_name || ''}
              onChange={(e) => setEditForm((prev) => ({ ...prev, display_name: e.target.value }))}
              required
            />
            <Input
              label="Billing Email"
              type="email"
              value={editForm.email || ''}
              onChange={(e) => setEditForm((prev) => ({ ...prev, email: e.target.value }))}
              required
            />
            <Input
              label="Phone Number"
              value={editForm.phone || ''}
              onChange={(e) => setEditForm((prev) => ({ ...prev, phone: e.target.value }))}
            />
            <Input
              label="Website"
              value={editForm.website || ''}
              onChange={(e) => setEditForm((prev) => ({ ...prev, website: e.target.value }))}
            />
          </div>

          <div className="pt-2 border-t border-slate-100">
            <h3 className="text-xs font-semibold text-slate-800 mb-2">Billing Address</h3>
            <div className="space-y-3">
              <Input
                label="Address Line 1"
                value={editForm.billing_address_line1 || ''}
                onChange={(e) =>
                  setEditForm((prev) => ({ ...prev, billing_address_line1: e.target.value }))
                }
              />
              <Input
                label="Address Line 2"
                value={editForm.billing_address_line2 || ''}
                onChange={(e) =>
                  setEditForm((prev) => ({ ...prev, billing_address_line2: e.target.value }))
                }
              />
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <Input
                  label="City"
                  value={editForm.billing_city || ''}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, billing_city: e.target.value }))}
                />
                <Input
                  label="State"
                  value={editForm.billing_state || ''}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, billing_state: e.target.value }))}
                />
                <Input
                  label="Postal Code"
                  value={editForm.billing_postal_code || ''}
                  onChange={(e) =>
                    setEditForm((prev) => ({ ...prev, billing_postal_code: e.target.value }))
                  }
                />
                <Input
                  label="Country"
                  value={editForm.billing_country || ''}
                  onChange={(e) =>
                    setEditForm((prev) => ({ ...prev, billing_country: e.target.value }))
                  }
                />
              </div>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
            <Button type="button" variant="outline" onClick={() => setIsEditing(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" isLoading={saving}>
              Save Changes
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
