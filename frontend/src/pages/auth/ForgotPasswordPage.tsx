import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Mail, Copy, ExternalLink } from 'lucide-react';
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

  const copyResetUrl = async () => {
    if (!result?.reset_url) return;
    try {
      await navigator.clipboard.writeText(result.reset_url);
      showToast('success', 'Copied', 'Reset link copied to clipboard.');
    } catch {
      showToast('warning', 'Copy failed', 'Select the link and copy it manually.');
    }
  };

  const resetPath = result?.reset_url ? toRelativePath(result.reset_url) : null;

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

          {result.reset_url && (
            <div className="space-y-2.5">
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-xs text-amber-800 leading-relaxed">
                Email delivery is not configured on this server, so the reset link is shown here
                instead of being emailed. Anyone with this link can set a new password for this
                account — keep it private.
              </div>
              <div className="flex items-stretch gap-2">
                <input
                  readOnly
                  value={result.reset_url}
                  onFocus={(e) => e.currentTarget.select()}
                  className="flex-1 min-w-0 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-xs font-mono text-slate-700"
                  aria-label="Password reset link"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="md"
                  onClick={copyResetUrl}
                  leadingIcon={<Copy className="w-3.5 h-3.5" />}
                >
                  Copy
                </Button>
              </div>
              {resetPath && (
                <Link to={resetPath}>
                  <Button
                    type="button"
                    className="w-full"
                    trailingIcon={<ExternalLink className="w-3.5 h-3.5" />}
                  >
                    Open reset page
                  </Button>
                </Link>
              )}
            </div>
          )}

          {!result.reset_url && (
            <p className="text-xs text-slate-500 leading-relaxed">
              Check your inbox (and spam folder). The link expires after a short time.
            </p>
          )}
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

/** Turns an absolute reset URL into an in-app path when it points at this frontend. */
function toRelativePath(url: string): string | null {
  try {
    const parsed = new URL(url, window.location.origin);
    if (!parsed.pathname.startsWith('/reset-password')) return null;
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return null;
  }
}

export default ForgotPasswordPage;
