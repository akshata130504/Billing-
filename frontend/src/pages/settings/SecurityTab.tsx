import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { KeyRound, ShieldCheck, Smartphone, Laptop, LogOut } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { authService, type AuthSession, type TotpSetup } from '../../services/authService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime } from '../../utils/format';
import { PasswordRules, passwordMeetsPolicy } from '../auth/passwordRules';
import { SettingsSection, type FieldErrors } from './settingsShared';

const SESSIONS_QUERY_KEY = ['auth', 'sessions'] as const;

/** A readable label for a stored User-Agent string. */
function describeUserAgent(ua: string | null): string {
  if (!ua) return 'Unknown device';
  const os = /Windows/i.test(ua)
    ? 'Windows'
    : /iPhone|iPad/i.test(ua)
      ? 'iOS'
      : /Android/i.test(ua)
        ? 'Android'
        : /Macintosh|Mac OS/i.test(ua)
          ? 'macOS'
          : /Linux/i.test(ua)
            ? 'Linux'
            : null;
  const browser = /Edg\//i.test(ua)
    ? 'Edge'
    : /Chrome\//i.test(ua)
      ? 'Chrome'
      : /Firefox\//i.test(ua)
        ? 'Firefox'
        : /Safari\//i.test(ua)
          ? 'Safari'
          : null;
  if (os && browser) return `${browser} on ${os}`;
  return os ?? browser ?? ua.slice(0, 60);
}

function onlyDigits(value: string): string {
  return value.replace(/\D/g, '').slice(0, 6);
}

export function SecurityTab() {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const { user, logout, refreshMe } = useAuth();
  const twoFactorEnabled = Boolean(user?.two_factor_enabled);

  // Password state
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  // 2FA state
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [isEnableOpen, setIsEnableOpen] = useState(false);
  const [isDisableOpen, setIsDisableOpen] = useState(false);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [disablePassword, setDisablePassword] = useState('');
  const [twoFactorErrors, setTwoFactorErrors] = useState<FieldErrors>({});
  const [twoFactorFormError, setTwoFactorFormError] = useState<string | null>(null);

  const sessions = useQuery({
    queryKey: SESSIONS_QUERY_KEY,
    queryFn: authService.listSessions,
  });

  const mutation = useMutation({
    mutationFn: () => authService.changePassword(current, next),
    onSuccess: () => {
      setCurrent('');
      setNext('');
      setConfirm('');
      setErrors({});
      setFormError(null);
      void queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY });
      showToast('success', 'Password changed', 'Your other sessions have been signed out.');
    },
    onError: (err) => {
      const fields = fieldErrors(err);
      setErrors(fields);
      setFormError(Object.keys(fields).length === 0 ? toApiError(err).message : null);
    },
  });

  const reset2FAForm = () => {
    setTwoFactorCode('');
    setDisablePassword('');
    setTwoFactorErrors({});
    setTwoFactorFormError(null);
  };

  const show2FAError = (err: unknown) => {
    const fields = fieldErrors(err);
    setTwoFactorErrors(fields);
    setTwoFactorFormError(Object.keys(fields).length === 0 ? toApiError(err).message : null);
  };

  const setupMutation = useMutation({
    mutationFn: authService.setupTwoFactor,
    onSuccess: (data) => {
      reset2FAForm();
      setSetup(data);
      setIsEnableOpen(true);
    },
    onError: (err) => showToast('error', 'Could not start 2FA setup', toApiError(err).message),
  });

  const enableMutation = useMutation({
    mutationFn: (code: string) => authService.enableTwoFactor(code),
    onSuccess: async () => {
      setIsEnableOpen(false);
      setSetup(null);
      reset2FAForm();
      await refreshMe();
      showToast('success', '2FA enabled', 'You will be asked for an authenticator code when you sign in.');
    },
    onError: show2FAError,
  });

  const disableMutation = useMutation({
    mutationFn: ({ password, code }: { password: string; code: string }) =>
      authService.disableTwoFactor(password, code),
    onSuccess: async () => {
      setIsDisableOpen(false);
      reset2FAForm();
      await refreshMe();
      showToast('info', '2FA disabled', 'Two-factor authentication has been turned off for your account.');
    },
    onError: show2FAError,
  });

  const revokeMutation = useMutation({
    mutationFn: (sessionId: string) => authService.revokeSession(sessionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY });
      showToast('success', 'Session signed out', 'That device will need to sign in again.');
    },
    onError: (err) => showToast('error', 'Could not sign out session', toApiError(err).message),
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
    reset2FAForm();
    if (twoFactorEnabled) setIsDisableOpen(true);
    else setupMutation.mutate();
  };

  const handleConfirmEnable = (e: React.FormEvent) => {
    e.preventDefault();
    if (twoFactorCode.length !== 6) {
      setTwoFactorErrors({ code: 'Enter the 6-digit code shown in your authenticator app.' });
      return;
    }
    enableMutation.mutate(twoFactorCode);
  };

  const handleConfirmDisable = (e: React.FormEvent) => {
    e.preventDefault();
    const clientErrors: FieldErrors = {};
    if (!disablePassword) clientErrors.password = 'Enter your password.';
    if (twoFactorCode.length !== 6) clientErrors.code = 'Enter the 6-digit code shown in your authenticator app.';
    if (Object.keys(clientErrors).length > 0) {
      setTwoFactorErrors(clientErrors);
      return;
    }
    disableMutation.mutate({ password: disablePassword, code: twoFactorCode });
  };

  const handleRevoke = (session: AuthSession) => {
    if (session.current) {
      void logout();
      return;
    }
    revokeMutation.mutate(session.id);
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
            <div className={`p-2.5 rounded-xl border ${twoFactorEnabled ? 'bg-emerald-50 text-emerald-600 border-emerald-200' : 'bg-slate-100 text-slate-500 border-slate-200'}`}>
              <Smartphone className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <p className="text-xs font-semibold text-slate-900">Authenticator App</p>
                <Badge variant={twoFactorEnabled ? 'success' : 'neutral'} size="sm">
                  {twoFactorEnabled ? 'Enabled' : 'Disabled'}
                </Badge>
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {twoFactorEnabled
                  ? 'Signing in requires a code from your authenticator app.'
                  : 'Protect your account using an authenticator app (Google Authenticator, Authy, 1Password).'}
              </p>
            </div>
          </div>

          <Button
            type="button"
            variant={twoFactorEnabled ? 'outline' : 'primary'}
            size="sm"
            onClick={handleToggle2FA}
            isLoading={setupMutation.isPending}
          >
            {twoFactorEnabled ? 'Disable 2FA' : 'Enable 2FA'}
          </Button>
        </div>
      </SettingsSection>

      {/* Active Sessions */}
      <SettingsSection
        title="Active Sessions & Devices"
        description="Browsers and devices currently signed into your account. Signing one out revokes it immediately."
      >
        <div className="space-y-3">
          {sessions.isPending && <p className="text-xs text-slate-500">Loading sessions...</p>}
          {sessions.isError && (
            <p className="text-xs text-rose-600">{toApiError(sessions.error).message}</p>
          )}
          {sessions.data?.map((session) => (
            <div key={session.id} className="flex items-center justify-between p-3.5 rounded-xl border border-slate-200 bg-white">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-blue-50 text-brand-600 border border-blue-100">
                  <Laptop className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-xs font-semibold text-slate-800">{describeUserAgent(session.user_agent)}</p>
                    {session.current && <Badge variant="primary" size="sm">This Device</Badge>}
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Last active {formatDateTime(session.last_active_at)}
                    {session.ip_address ? ` • ${session.ip_address}` : ''}
                  </p>
                </div>
              </div>

              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => handleRevoke(session)}
                disabled={revokeMutation.isPending}
                className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                leadingIcon={<LogOut className="w-3.5 h-3.5" />}
              >
                Sign Out
              </Button>
            </div>
          ))}
          {sessions.data && sessions.data.length === 0 && (
            <p className="text-xs text-slate-500">No other active sessions.</p>
          )}

          <div className="flex items-start gap-3 p-3.5 rounded-xl border border-emerald-100 bg-emerald-50/40 text-xs">
            <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
            <div className="text-slate-600 text-[11px] leading-relaxed">
              <span className="font-semibold text-slate-800 block text-xs mb-0.5">Automatic Session Revocation</span>
              Changing your password keeps this session and signs out every other device.
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
              <p className="font-semibold text-slate-800">Brute-force Protection</p>
              <p className="text-[11px] text-slate-400">
                Repeated failed sign-ins from one network are paused for 15 minutes without locking you out elsewhere.
              </p>
            </div>
            <Badge variant="primary" size="sm">Active</Badge>
          </div>
        </div>
      </SettingsSection>

      {/* 2FA Setup Modal */}
      <Modal
        isOpen={isEnableOpen}
        onClose={() => setIsEnableOpen(false)}
        title="Enable Two-Factor Authentication"
        description="Add this account to your authenticator app, then enter the code it shows."
        size="md"
      >
        <form onSubmit={handleConfirmEnable} className="space-y-4" noValidate>
          {twoFactorFormError && (
            <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-700 font-medium">
              {twoFactorFormError}
            </div>
          )}
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
            <p className="text-xs font-semibold text-slate-700 text-center">Setup key</p>
            <p className="font-mono text-xs bg-white px-3 py-1.5 rounded border border-slate-200 text-slate-800 select-all break-all text-center">
              {setup?.secret.replace(/(.{4})/g, '$1 ').trim()}
            </p>
            <p className="text-[11px] text-slate-400 text-center">
              Enter this key (time-based, 6 digits) in Google Authenticator, Microsoft Authenticator or 1Password.
            </p>
            {setup?.otpauth_uri && (
              <details className="text-[11px] text-slate-500">
                <summary className="cursor-pointer">Setup link (otpauth://)</summary>
                <p className="mt-1 font-mono break-all select-all">{setup.otpauth_uri}</p>
              </details>
            )}
          </div>

          <Input
            label="6-Digit Verification Code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={twoFactorCode}
            onChange={(e) => setTwoFactorCode(onlyDigits(e.target.value))}
            placeholder="123456"
            error={twoFactorErrors.code}
            required
            helperText="Enter the 6-digit code currently shown in your authenticator app."
          />

          <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100">
            <Button type="button" variant="outline" onClick={() => setIsEnableOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" isLoading={enableMutation.isPending}>
              Verify & Enable
            </Button>
          </div>
        </form>
      </Modal>

      {/* 2FA Disable Modal */}
      <Modal
        isOpen={isDisableOpen}
        onClose={() => setIsDisableOpen(false)}
        title="Disable Two-Factor Authentication"
        description="Confirm with your password and a current authenticator code."
        size="md"
      >
        <form onSubmit={handleConfirmDisable} className="space-y-4" noValidate>
          {twoFactorFormError && (
            <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-700 font-medium">
              {twoFactorFormError}
            </div>
          )}
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            value={disablePassword}
            onChange={(e) => setDisablePassword(e.target.value)}
            error={twoFactorErrors.password}
            required
          />
          <Input
            label="6-Digit Verification Code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={twoFactorCode}
            onChange={(e) => setTwoFactorCode(onlyDigits(e.target.value))}
            placeholder="123456"
            error={twoFactorErrors.code}
            required
          />
          <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100">
            <Button type="button" variant="outline" onClick={() => setIsDisableOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" isLoading={disableMutation.isPending}>
              Disable 2FA
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default SecurityTab;
