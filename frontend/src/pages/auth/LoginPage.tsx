import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Mail, Lock } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { LoadingState } from '../../components/common/LoadingState';
import { useAuth } from '../../hooks/useAuth';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { AuthShell, FormErrorBanner } from './AuthShell';

interface LocationState {
  from?: { pathname?: string; search?: string };
}

export function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { showToast } = useToast();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const from = (location.state as LocationState | null)?.from;
  const redirectTo = from?.pathname ? `${from.pathname}${from.search ?? ''}` : '/dashboard';

  if (isLoading) return <LoadingState message="Checking your session..." />;
  if (isAuthenticated) return <Navigate to={redirectTo} replace />;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrors({});
    setFormError(null);
    try {
      const me = await login({ email: email.trim(), password });
      showToast('success', 'Signed in', `Welcome back, ${me.user.full_name}.`);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      const apiError = toApiError(err);
      const fields = fieldErrors(err);
      setErrors(fields);
      if (Object.keys(fields).length === 0) setFormError(apiError.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Sign in"
      subtitle="Use your work email and password to access your organization."
      footer={
        <>
          New to Rooman Billing?{' '}
          <Link to="/signup" className="font-semibold text-brand-600 hover:text-brand-700">
            Create an organization
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <FormErrorBanner message={formError} />
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          leadingIcon={<Mail className="w-4 h-4" />}
          placeholder="you@company.com"
        />
        <div>
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={errors.password}
            leadingIcon={<Lock className="w-4 h-4" />}
          />
          <div className="mt-1.5 text-right">
            <Link
              to="/forgot-password"
              className="text-xs font-medium text-brand-600 hover:text-brand-700"
            >
              Forgot password?
            </Link>
          </div>
        </div>
        <Button type="submit" className="w-full" isLoading={submitting}>
          Sign in
        </Button>
      </form>
    </AuthShell>
  );
}

export default LoginPage;
