import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { KeyRound, ShieldCheck } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { authService } from '../../services/authService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime } from '../../utils/format';
import { PasswordRules, passwordMeetsPolicy } from '../auth/passwordRules';
import { SettingsSection, type FieldErrors } from './settingsShared';

export function SecurityTab() {
  const { showToast } = useToast();
  const { user } = useAuth();

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

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

  const submit = (e: FormEvent) => {
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

  return (
    <div className="space-y-5">
      <SettingsSection
        title="Change password"
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

      <SettingsSection title="Sessions">
        <div className="flex items-start gap-3">
          <div className="p-2.5 rounded-xl bg-emerald-50 text-emerald-600 border border-emerald-100 shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div className="text-sm space-y-1">
            <p className="font-semibold text-slate-900">Sign out everywhere</p>
            <p className="text-xs text-slate-500 leading-relaxed">
              There is no separate session list. To sign out of every other device, change your
              password above — the server revokes all other refresh tokens when it is changed.
            </p>
            {user?.last_login_at && (
              <p className="text-xs text-slate-400">Last sign-in: {formatDateTime(user.last_login_at)}</p>
            )}
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
