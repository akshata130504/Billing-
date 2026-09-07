import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Lock } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { authService } from '../../services/authService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { AuthShell, FormErrorBanner } from './AuthShell';
import { PasswordRules, passwordMeetsPolicy } from './passwordRules';

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setErrors({});
    setFormError(null);

    const clientErrors: Record<string, string> = {};
    if (!passwordMeetsPolicy(password)) {
      clientErrors.new_password = 'Password does not meet the requirements below.';
    }
    if (confirm !== password) clientErrors.confirm = 'Passwords do not match.';
    if (Object.keys(clientErrors).length > 0) {
      setErrors(clientErrors);
      return;
    }

    setSubmitting(true);
    try {
      await authService.resetPassword(token, password);
      showToast('success', 'Password updated', 'You can now sign in with your new password.');
      navigate('/login', { replace: true });
    } catch (err) {
      const apiError = toApiError(err);
      const fields = fieldErrors(err);
      setErrors(fields);
      if (Object.keys(fields).length === 0) setFormError(apiError.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (!token) {
    return (
      <AuthShell
        title="Reset link is incomplete"
        subtitle="This page needs the token from your reset link. Request a new link to continue."
        footer={
          <Link to="/login" className="font-semibold text-brand-600 hover:text-brand-700">
            Back to sign in
          </Link>
        }
      >
        <Link to="/forgot-password">
          <Button className="w-full">Request a new link</Button>
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Choose a new password"
      subtitle="Your other sessions will be signed out after the password changes."
      footer={
        <Link to="/login" className="font-semibold text-brand-600 hover:text-brand-700">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <FormErrorBanner message={formError ?? errors.token ?? null} />
        <Input
          label="New password"
          type="password"
          required
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.new_password}
          leadingIcon={<Lock className="w-4 h-4" />}
        />
        <Input
          label="Confirm new password"
          type="password"
          required
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm}
          leadingIcon={<Lock className="w-4 h-4" />}
        />
        <PasswordRules password={password} />
        <Button type="submit" className="w-full" isLoading={submitting}>
          Update password
        </Button>
      </form>
    </AuthShell>
  );
}

export default ResetPasswordPage;
