import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Mail } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { authService } from '../../services/authService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import type { ForgotPasswordResponse } from '../../types/api';
import { AuthShell, FormErrorBanner } from './AuthShell';

export function ForgotPasswordPage() {
  const { showToast } = useToast();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<ForgotPasswordResponse | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrors({});
    setFormError(null);
    try {
      const response = await authService.forgotPassword(email.trim());
      setResult(response);
      showToast('success', 'Request received', response.message);
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
      title="Reset your password"
      subtitle="Enter the email you sign in with. If it matches an account, you will receive a reset link."
      footer={
        <Link to="/login" className="font-semibold text-brand-600 hover:text-brand-700">
          Back to sign in
        </Link>
      }
    >
      {result ? (
        <div className="space-y-4">
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-xs text-emerald-800">
            {result.message}
          </div>

          <p className="text-xs text-slate-500 leading-relaxed">
            Check your inbox (and spam folder). The link expires after a short time.
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <FormErrorBanner message={formError} />
          <Input
            label="Email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={errors.email}
            leadingIcon={<Mail className="w-4 h-4" />}
            placeholder="you@company.com"
          />
          <Button type="submit" className="w-full" isLoading={submitting}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthShell>
  );
}

export default ForgotPasswordPage;
