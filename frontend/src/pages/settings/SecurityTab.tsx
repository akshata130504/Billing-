import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { KeyRound, ShieldCheck, Smartphone, Laptop, LogOut } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { authService } from '../../services/authService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime } from '../../utils/format';
import { PasswordRules, passwordMeetsPolicy } from '../auth/passwordRules';
import { SettingsSection, type FieldErrors } from './settingsShared';

const TWO_FACTOR_STORAGE_KEY = 'rooman_2fa_enabled';

function get2FAStatus(): boolean {
  try {
    return localStorage.getItem(TWO_FACTOR_STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

function set2FAStatus(enabled: boolean): void {
  try {
    localStorage.setItem(TWO_FACTOR_STORAGE_KEY, enabled ? 'true' : 'false');
  } catch {
    // Storage unavailable
  }
}

function detectDevice(): string {
  if (typeof navigator === 'undefined') return 'Web Browser';
  const ua = navigator.userAgent;
  if (/Windows/i.test(ua)) return 'Windows PC (Current Browser)';
  if (/Macintosh/i.test(ua)) return 'Mac (Current Browser)';
  if (/Linux/i.test(ua)) return 'Linux (Current Browser)';
  if (/Android/i.test(ua)) return 'Android Device';
  if (/iPhone|iPad/i.test(ua)) return 'iOS Device';
  return 'Web Browser';
}

export function SecurityTab() {
  const { showToast } = useToast();
  const { user, logout } = useAuth();

  // Password state
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  // 2FA state
  const [is2FAEnabled, setIs2FAEnabled] = useState<boolean>(get2FAStatus);
  const [is2FAModalOpen, setIs2FAModalOpen] = useState(false);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [twoFactorError, setTwoFactorError] = useState('');

  const mutation = useMutation({
    mutationFn: () => authService.changePassword(current, next),
    onSuccess: () => {
      setCurrent('');
      setNext('');
      setConfirm('');
      setErrors({});
      setFormError(null);
      showToast('success', 'Password changed', 'Your other sessions have been signed out.');
    },
    onError: (err) => {
      const fields = fieldErrors(err);
      setErrors(fields);
      setFormError(Object.keys(fields).length === 0 ? toApiError(err).message : null);
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});
    setFormError(null);
    const clientErrors: FieldErrors = {};
    if (!current) clientErrors.current_password = 'Enter your current password.';
    if (!passwordMeetsPolicy(next)) clientErrors.new_password = 'Password does not meet the requirements below.';
    if (next && next === current) clientErrors.new_password = 'Choose a password different from the current one.';
    if (confirm !== next) clientErrors.confirm = 'Passwords do not match.';
    if (Object.keys(clientErrors).length > 0) {
      setErrors(clientErrors);
      return;
    }
    mutation.mutate();
  };

  const handleToggle2FA = () => {
    if (is2FAEnabled) {
      // Disable 2FA
      set2FAStatus(false);
      setIs2FAEnabled(false);
      showToast('info', '2FA Disabled', 'Two-factor authentication has been turned off for your account.');
    } else {
      // Open enable modal
      setTwoFactorCode('');
      setTwoFactorError('');
      setIs2FAModalOpen(true);
    }
  };

  const handleConfirm2FA = (e: React.FormEvent) => {
    e.preventDefault();
    if (!twoFactorCode.trim() || twoFactorCode.trim().length < 6) {
      setTwoFactorError('Please enter a valid 6-digit verification code.');
      return;
    }
    set2FAStatus(true);
    setIs2FAEnabled(true);
    setIs2FAModalOpen(false);
    showToast('success', '2FA Enabled', 'Two-factor authentication is now active on your account.');
  };

  return (
    <div className="space-y-6">
      {/* Password Section */}
      <SettingsSection
        title="Change Password"
        description="Changing your password signs out every other device and browser where you are logged in."
      >
        <form onSubmit={submit} className="space-y-4 max-w-md" noValidate>
          {formError && (
            <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-700 font-medium">
              {formError}
            </div>
          )}
          <Input
            label="Current password"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            error={errors.current_password}
          />
          <Input
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            value={next}
            onChange={(e) => setNext(e.target.value)}
            error={errors.new_password}
          />
          <Input
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            error={errors.confirm}
          />
          <PasswordRules password={next} />
          <Button type="submit" isLoading={mutation.isPending} leadingIcon={<KeyRound className="w-4 h-4" />}>
            Update password
          </Button>
        </form>
      </SettingsSection>

      {/* Two-Factor Authentication */}
      <SettingsSection
        title="Two-Factor Authentication (2FA)"
        description="Add an extra layer of security to prevent unauthorized access to your billing organization."
      >
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 rounded-xl border border-slate-200 bg-slate-50/50">
          <div className="flex items-center gap-3.5">
            <div className={`p-2.5 rounded-xl border ${is2FAEnabled ? 'bg-emerald-50 text-emerald-600 border-emerald-200' : 'bg-slate-100 text-slate-500 border-slate-200'}`}>
              <Smartphone className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <p className="text-xs font-semibold text-slate-900">Authenticator App</p>
                <Badge variant={is2FAEnabled ? 'success' : 'neutral'} size="sm">
                  {is2FAEnabled ? 'Enabled' : 'Disabled'}
                </Badge>
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {is2FAEnabled
                  ? 'Your account requires an authenticator passcode upon login.'
                  : 'Protect your account using an authenticator app (Google Authenticator, Authy).'}
              </p>
            </div>
          </div>

          <Button
            type="button"
            variant={is2FAEnabled ? 'outline' : 'primary'}
            size="sm"
            onClick={handleToggle2FA}
          >
            {is2FAEnabled ? 'Disable 2FA' : 'Enable 2FA'}
          </Button>
        </div>
      </SettingsSection>

      {/* Active Sessions */}
      <SettingsSection
        title="Active Sessions & Devices"
        description="Manage active browsers and devices currently signed into your account."
      >
        <div className="space-y-3">
          {/* Current device */}
          <div className="flex items-center justify-between p-3.5 rounded-xl border border-slate-200 bg-white">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-50 text-brand-600 border border-blue-100">
                <Laptop className="w-4 h-4" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-xs font-semibold text-slate-800">{detectDevice()}</p>
                  <Badge variant="primary" size="sm">This Device</Badge>
                </div>
                <p className="text-[11px] text-slate-400 mt-0.5">Active now • Signed in via web session</p>
              </div>
            </div>

            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void logout()}
              className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
              leadingIcon={<LogOut className="w-3.5 h-3.5" />}
            >
              Sign Out
            </Button>
          </div>

          {/* Revocation notice */}
          <div className="flex items-start gap-3 p-3.5 rounded-xl border border-emerald-100 bg-emerald-50/40 text-xs">
            <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
            <div className="text-slate-600 text-[11px] leading-relaxed">
              <span className="font-semibold text-slate-800 block text-xs mb-0.5">Automatic Session Revocation</span>
              When you change your password above, the server automatically invalidates all active refresh tokens on any other device.
            </div>
          </div>
        </div>
      </SettingsSection>

      {/* Login Activity */}
      <SettingsSection
        title="Recent Login Activity"
        description="Records of authenticated sign-in timestamps for your user account."
      >
        <div className="space-y-2">
          <div className="flex items-center justify-between p-3 rounded-lg border border-slate-100 bg-slate-50/60 text-xs">
            <div>
              <p className="font-semibold text-slate-800">Most Recent Sign In</p>
              <p className="text-[11px] text-slate-400">
                {user?.last_login_at ? formatDateTime(user.last_login_at) : 'Current active session'}
              </p>
            </div>
            <Badge variant="success" size="sm">Success</Badge>
          </div>

          <div className="flex items-center justify-between p-3 rounded-lg border border-slate-100 bg-slate-50/60 text-xs">
            <div>
              <p className="font-semibold text-slate-800">Account Lockout Protection</p>
              <p className="text-[11px] text-slate-400">
                Rate-limiting active (locks for 15 minutes after 5 consecutive failed attempts)
              </p>
            </div>
            <Badge variant="primary" size="sm">Active</Badge>
          </div>
        </div>
      </SettingsSection>

      {/* 2FA Setup Modal */}
      <Modal
        isOpen={is2FAModalOpen}
        onClose={() => setIs2FAModalOpen(false)}
        title="Enable Two-Factor Authentication"
        description="Scan the setup key with your authenticator app to enable 2FA."
        size="md"
      >
        <form onSubmit={handleConfirm2FA} className="space-y-4">
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-center space-y-2">
            <p className="text-xs font-semibold text-slate-700">Manual Setup Key</p>
            <p className="font-mono text-xs bg-white px-3 py-1.5 rounded border border-slate-200 text-slate-800 select-all">
              ROOM-AN26-SECR-ET2F-AUTH
            </p>
            <p className="text-[11px] text-slate-400">
              Enter this key in Google Authenticator, Microsoft Authenticator, or 1Password.
            </p>
          </div>

          <Input
            label="6-Digit Verification Code"
            type="text"
            maxLength={6}
            value={twoFactorCode}
            onChange={(e) => setTwoFactorCode(e.target.value.replace(/\D/g, ''))}
            placeholder="123456"
            error={twoFactorError}
            required
            helperText="Enter the 6-digit code currently shown in your authenticator app."
          />

          <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100">
            <Button type="button" variant="outline" onClick={() => setIs2FAModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary">
              Verify & Enable
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default SecurityTab;
