import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Lock, ShieldCheck, User } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { useToast } from '../../components/common/Toast';
import { LoadingSpinner } from '../../components/common/LoadingState';
import { useAuth } from '../../hooks/useAuth';
import { queryKeys } from '../../hooks/queries';
import { authService } from '../../services/authService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { formatDateTime, ROLE_LABELS } from '../../utils/format';
import { AuthShell, FormErrorBanner } from './AuthShell';
import { PasswordRules, passwordMeetsPolicy } from './passwordRules';

export function AcceptInvitationPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { applyTokens, logout, isAuthenticated } = useAuth();

  const invitation = useQuery({
    queryKey: queryKeys.auth.invitation(token),
    queryFn: () => authService.getInvitation(token),
    enabled: token.length > 0,
    retry: false,
  });

  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  // Existing accounts with two-factor authentication on are asked for a code too.
  const [totpCode, setTotpCode] = useState('');
  const [needsTotp, setNeedsTotp] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const accept = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!invitation.data) return;
    setErrors({});
    setFormError(null);

    const needsAccount = !invitation.data.user_exists;
    if (needsAccount) {
      const clientErrors: Record<string, string> = {};
      if (!fullName.trim()) clientErrors.full_name = 'Please enter your name.';
      if (!passwordMeetsPolicy(password)) {
        clientErrors.password = 'Password does not meet the requirements below.';
      }
      if (confirm !== password) clientErrors.confirm = 'Passwords do not match.';
      if (Object.keys(clientErrors).length > 0) {
        setErrors(clientErrors);
        return;
      }
    } else if (!password) {
      // The invitation link alone never signs anyone into an existing account.
      setErrors({ password: 'Enter the password of your existing account.' });
      return;
    }

    setSubmitting(true);
    try {
      // If another session is active in this browser, drop it so the new tokens win.
      if (isAuthenticated) await logout();
      const tokens = await authService.acceptInvitation(
        needsAccount
          ? { token, full_name: fullName.trim(), password }
          : { token, password, ...(totpCode.trim() ? { totp_code: totpCode.trim() } : {}) }
      );
      const me = await applyTokens(tokens);
      showToast('success', 'Invitation accepted', `You have joined ${me.organization.name}.`);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      const apiError = toApiError(err);
      const fields = fieldErrors(err);
      if (fields.totp_code) setNeedsTotp(true);
      setErrors(fields);
      if (Object.keys(fields).length === 0) setFormError(apiError.message);
    } finally {
      setSubmitting(false);
    }
  };

  const footer = (
    <Link to="/login" className="font-semibold text-brand-600 hover:text-brand-700">
      Back to sign in
    </Link>
  );

  if (!token) {
    return (
      <AuthShell
        title="Invitation link is incomplete"
        subtitle="This page needs the token from your invitation email. Ask the person who invited you to send it again."
        footer={footer}
      >
        <Link to="/login">
          <Button className="w-full" variant="outline">
            Go to sign in
          </Button>
        </Link>
      </AuthShell>
    );
  }

  if (invitation.isPending) {
    return (
      <AuthShell title="Checking your invitation">
        <div className="py-8 flex justify-center">
          <LoadingSpinner size="lg" />
        </div>
      </AuthShell>
    );
  }

  if (invitation.isError || !invitation.data) {
    const apiError = toApiError(invitation.error);
    return (
      <AuthShell
        title="This invitation is not valid"
        subtitle={apiError.message || 'The invitation may have expired or already been used.'}
        footer={footer}
      >
        <Link to="/login">
          <Button className="w-full" variant="outline">
            Go to sign in
          </Button>
        </Link>
      </AuthShell>
    );
  }

  const inv = invitation.data;

  return (
    <AuthShell
      title={`Join ${inv.organization_name}`}
      subtitle={
        <>
          {inv.invited_by} invited <span className="font-medium text-slate-700">{inv.email}</span> to
          join as{' '}
          <Badge variant="primary" size="sm" className="align-middle">
            {ROLE_LABELS[inv.role] ?? inv.role}
          </Badge>
          . This invitation expires {formatDateTime(inv.expires_at)}.
        </>
      }
      footer={footer}
    >
      <form onSubmit={accept} className="space-y-4" noValidate>
        <FormErrorBanner message={formError} />

        {inv.user_exists ? (
          <>
            <p className="text-sm text-slate-600 leading-relaxed">
              An account already exists for {inv.email}. Sign in with its password to add{' '}
              {inv.organization_name} to your organizations.
            </p>
            <Input
              label="Your password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={errors.password}
              leadingIcon={<Lock className="w-4 h-4" />}
            />
            {needsTotp && (
              <Input
                label="Authentication code"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                maxLength={8}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                error={errors.totp_code}
                leadingIcon={<ShieldCheck className="w-4 h-4" />}
              />
            )}
            <p className="text-xs text-slate-500">
              <Link to="/forgot-password" className="font-semibold text-brand-600 hover:text-brand-700">
                Forgot your password?
              </Link>
            </p>
          </>
        ) : (
          <>
            <Input
              label="Your full name"
              required
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              error={errors.full_name}
              leadingIcon={<User className="w-4 h-4" />}
            />
            <Input
              label="Create a password"
              type="password"
              required
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={errors.password}
              leadingIcon={<Lock className="w-4 h-4" />}
            />
            <Input
              label="Confirm password"
              type="password"
              required
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              error={errors.confirm}
              leadingIcon={<Lock className="w-4 h-4" />}
            />
            <PasswordRules password={password} />
          </>
        )}

        <Button type="submit" className="w-full" isLoading={submitting}>
          {inv.user_exists ? 'Sign in and accept' : 'Create account and join'}
        </Button>
      </form>
    </AuthShell>
  );
}

export default AcceptInvitationPage;
