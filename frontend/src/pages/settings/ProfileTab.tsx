import { useState } from 'react';
import { User, Mail, Phone, Building2, Shield, Calendar, Clock, Edit3, CheckCircle2 } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';
import { PhoneInput } from '../../components/common/PhoneInput';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime, initials, ROLE_LABELS } from '../../utils/format';
import { SettingsSection } from './settingsShared';
import { userService } from '../../services/userService';
import { validateSensibleName, validatePhone } from '../../utils/validation';

export function ProfileTab() {
  const { user, organization, membership, refreshMe } = useAuth();
  const { showToast } = useToast();

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [fullName, setFullName] = useState(user?.full_name || '');
  const [phone, setPhone] = useState(user?.phone || '');
  const [isSaving, setIsSaving] = useState(false);

  const roleLabel = membership ? ROLE_LABELS[membership.role] ?? membership.role : 'Member';

  const handleOpenEdit = () => {
    setFullName(user?.full_name || '');
    setPhone(user?.phone || '');
    setIsEditOpen(true);
  };

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = fullName.trim();
    const nameError = validateSensibleName(name, 'Full name');
    if (nameError) {
      showToast('error', 'Invalid name', nameError);
      return;
    }
    const phoneError = validatePhone(phone);
    if (phoneError) {
      showToast('error', 'Invalid phone number', phoneError);
      return;
    }
    setIsSaving(true);
    try {
      // Persisted server-side so the change follows the user across devices.
      await userService.updateMe({ full_name: name, phone: phone.trim() });
      await refreshMe();
      showToast('success', 'Profile updated', 'Your profile details have been successfully saved.');
      setIsEditOpen(false);
    } catch (err: any) {
      showToast('error', 'Update failed', err?.message || 'Could not save profile changes.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Profile Header Card */}
      <div className="bg-white rounded-xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-brand-600 text-white font-bold text-xl flex items-center justify-center shadow-sm shrink-0">
              {initials(user?.full_name, user?.email?.[0]?.toUpperCase() ?? 'U')}
            </div>
            <div className="space-y-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg font-bold text-slate-900 truncate">
                  {user?.full_name || 'User Profile'}
                </h2>
                <Badge variant="success" size="sm" dot>
                  Active
                </Badge>
              </div>
              <p className="text-xs text-slate-500 truncate">{user?.email}</p>
              <div className="flex items-center gap-3 text-xs text-slate-500 pt-0.5">
                <span className="inline-flex items-center gap-1 font-medium text-slate-700">
                  <Shield className="w-3.5 h-3.5 text-brand-600" />
                  {roleLabel}
                </span>
                <span>•</span>
                <span className="inline-flex items-center gap-1 text-slate-600">
                  <Building2 className="w-3.5 h-3.5 text-slate-400" />
                  {organization?.name || 'Rooman Technologies'}
                </span>
              </div>
            </div>
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleOpenEdit}
            leadingIcon={<Edit3 className="w-3.5 h-3.5" />}
          >
            Edit Profile
          </Button>
        </div>

        {user?.last_login_at && (
          <div className="mt-5 pt-4 border-t border-slate-100 flex items-center gap-2 text-xs text-slate-400">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>Last sign in: {formatDateTime(user.last_login_at)}</span>
          </div>
        )}
      </div>

      {/* Profile Details Section */}
      <SettingsSection
        title="Personal Information"
        description="Your personal information and communication details associated with this account."
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-3.5 rounded-lg border border-slate-100 bg-slate-50/50">
            <p className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Full Name</p>
            <p className="text-xs font-semibold text-slate-800 mt-1 flex items-center gap-2">
              <User className="w-3.5 h-3.5 text-slate-400" />
              {user?.full_name || '—'}
            </p>
          </div>

          <div className="p-3.5 rounded-lg border border-slate-100 bg-slate-50/50">
            <p className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Display Name</p>
            <p className="text-xs font-semibold text-slate-800 mt-1 flex items-center gap-2">
              <User className="w-3.5 h-3.5 text-brand-600" />
              {user?.full_name || '—'}
            </p>
          </div>

          <div className="p-3.5 rounded-lg border border-slate-100 bg-slate-50/50">
            <p className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Email Address</p>
            <p className="text-xs font-semibold text-slate-800 mt-1 flex items-center gap-2 truncate">
              <Mail className="w-3.5 h-3.5 text-slate-400" />
              {user?.email || '—'}
            </p>
          </div>

          <div className="p-3.5 rounded-lg border border-slate-100 bg-slate-50/50">
            <p className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Phone Number</p>
            <p className="text-xs font-semibold text-slate-800 mt-1 flex items-center gap-2">
              <Phone className="w-3.5 h-3.5 text-slate-400" />
              {user?.phone ? user.phone : <span className="text-slate-400 font-normal italic">Not specified</span>}
            </p>
          </div>

          <div className="p-3.5 rounded-lg border border-slate-100 bg-slate-50/50">
            <p className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Role & Permissions</p>
            <p className="text-xs font-semibold text-slate-800 mt-1 flex items-center gap-2">
              <Shield className="w-3.5 h-3.5 text-brand-600" />
              {roleLabel}
            </p>
          </div>

          <div className="p-3.5 rounded-lg border border-slate-100 bg-slate-50/50">
            <p className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Current Organization</p>
            <p className="text-xs font-semibold text-slate-800 mt-1 flex items-center gap-2">
              <Building2 className="w-3.5 h-3.5 text-slate-400" />
              {organization?.name || '—'}
            </p>
          </div>
        </div>
      </SettingsSection>

      {/* Account Status Card */}
      <SettingsSection
        title="Account Status & Verification"
        description="Current verification and authentication state of your identity."
      >
        <div className="space-y-3">
          <div className="flex items-center justify-between p-3 rounded-lg border border-emerald-100 bg-emerald-50/50 text-xs">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <div>
                <p className="font-semibold text-emerald-900">Email Authenticated</p>
                <p className="text-emerald-700 text-[11px]">Your work email {user?.email} is registered and verified.</p>
              </div>
            </div>
            <Badge variant="success" size="sm">Verified</Badge>
          </div>

          <div className="flex items-center justify-between p-3 rounded-lg border border-slate-100 bg-slate-50/50 text-xs text-slate-600">
            <div className="flex items-center gap-2.5">
              <Calendar className="w-4 h-4 text-slate-400 shrink-0" />
              <div>
                <p className="font-semibold text-slate-800">Member Since</p>
                <p className="text-slate-500 text-[11px]">Account created on {user?.created_at ? formatDateTime(user.created_at) : 'Active'}</p>
              </div>
            </div>
          </div>
        </div>
      </SettingsSection>

      {/* Edit Profile Modal */}
      <Modal
        isOpen={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        title="Edit Profile"
        description="Update your display name and contact preferences."
        size="md"
      >
        <form onSubmit={handleSaveProfile} className="space-y-4">
          <Input
            label="Full Name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
            leadingIcon={<User className="w-4 h-4" />}
            placeholder="Your full legal name"
          />

          <Input
            label="Work Email"
            type="email"
            value={user?.email || ''}
            disabled
            leadingIcon={<Mail className="w-4 h-4" />}
            helperText="Email cannot be changed directly as it is your unique login credential."
          />

          <PhoneInput
            label="Phone Number"
            value={phone}
            onChange={setPhone}
            helperText="Used for important security and account recovery notifications."
          />

          <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setIsEditOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" isLoading={isSaving}>
              Save Changes
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default ProfileTab;
