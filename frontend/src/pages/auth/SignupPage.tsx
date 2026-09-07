import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Building2, Lock, Mail, User } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { LoadingState } from '../../components/common/LoadingState';
import { useAuth } from '../../hooks/useAuth';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { AuthShell, FormErrorBanner } from './AuthShell';
import { PasswordRules, passwordMeetsPolicy } from './passwordRules';

export function SignupPage() {
  const { signup, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [organizationName, setOrganizationName] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  if (isLoading) return <LoadingState message="Checking your session..." />;
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setErrors({});
    setFormError(null);

    const clientErrors: Record<string, string> = {};
    if (!passwordMeetsPolicy(password)) {
      clientErrors.password = 'Password does not meet the requirements below.';
    }
    if (confirm !== password) {
      clientErrors.confirm = 'Passwords do not match.';
    }
    if (Object.keys(clientErrors).length > 0) {
      setErrors(clientErrors);
      return;
    }

    setSubmitting(true);
    try {
      const me = await signup({
        organization_name: organizationName.trim(),
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      });
      showToast('success', 'Organization created', `${me.organization.name} is ready.`);
      navigate('/dashboard', { replace: true });
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
      title="Create your organization"
      subtitle="You will be the owner of the new organization and can invite your team afterwards."
      width="md"
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-brand-600 hover:text-brand-700">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <FormErrorBanner message={formError} />
        <Input
          label="Organization name"
          required
          autoComplete="organization"
          value={organizationName}
          onChange={(e) => setOrganizationName(e.target.value)}
          error={errors.organization_name}
          leadingIcon={<Building2 className="w-4 h-4" />}
        />
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
          label="Work email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          leadingIcon={<Mail className="w-4 h-4" />}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="Password"
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
        </div>
        <PasswordRules password={password} />
        <Button type="submit" className="w-full" isLoading={submitting}>
          Create organization
        </Button>
      </form>
    </AuthShell>
  );
}

export default SignupPage;
