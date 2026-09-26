import { useState, useRef, useEffect, type FormEvent, type ClipboardEvent, type KeyboardEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Building2, Lock, Mail, User, CheckCircle2, AlertTriangle } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { LoadingState } from '../../components/common/LoadingState';
import { useAuth } from '../../hooks/useAuth';
import { authService } from '../../services/authService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { AuthShell, FormErrorBanner } from './AuthShell';
import { PasswordRules, passwordMeetsPolicy } from './passwordRules';
import { cn } from '../../utils/cn';

function maskEmail(val: string): string {
  if (!val || !val.includes('@')) return val;
  const [name, domain] = val.split('@');
  if (name.length <= 2) {
    return `${name[0]}***@${domain}`;
  }
  const maskedLocal = name[0] + '*'.repeat(Math.min(Math.max(name.length - 2, 3), 6)) + name[name.length - 1];
  return `${maskedLocal}@${domain}`;
}

export function SignupPage() {
  const { applyTokens, isAuthenticated, isLoading } = useAuth();
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

  // OTP verification state inline beside/below email
  const [otpSent, setOtpSent] = useState(false);
  const [isEmailVerified, setIsEmailVerified] = useState(false);
  const [otp, setOtp] = useState<string[]>(['', '', '', '', '', '']);
  const [verifying, setVerifying] = useState(false);
  const [otpError, setOtpError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const [resending, setResending] = useState(false);
  const otpInputsRef = useRef<(HTMLInputElement | null)[]>([]);

  // Focus first OTP input when OTP section opens
  useEffect(() => {
    if (otpSent && !isEmailVerified) {
      setTimeout(() => {
        otpInputsRef.current[0]?.focus();
      }, 50);
    }
  }, [otpSent, isEmailVerified]);

  // Countdown timer for resend
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => {
      setCooldown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  if (isLoading) return <LoadingState message="Checking your session..." />;
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;

  const validateForm = (): boolean => {
    const clientErrors: Record<string, string> = {};
    if (!organizationName.trim()) {
      clientErrors.organization_name = 'Organization name is required.';
    }
    if (!fullName.trim()) {
      clientErrors.full_name = 'Full name is required.';
    }
    if (!email.trim()) {
      clientErrors.email = 'Work email is required.';
    } else if (!email.includes('@') || !email.includes('.')) {
      clientErrors.email = 'Please enter a valid work email address.';
    }
    if (!passwordMeetsPolicy(password)) {
      clientErrors.password = 'Password does not meet the requirements below.';
    }
    if (confirm !== password) {
      clientErrors.confirm = 'Passwords do not match.';
    }

    setErrors(clientErrors);
    return Object.keys(clientErrors).length === 0;
  };

  const handleRequestVerification = async () => {
    setFormError(null);
    if (!validateForm()) return;

    setSubmitting(true);
    try {
      const res = await authService.requestSignupVerification({
        organization_name: organizationName.trim(),
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      });
      setOtpSent(true);
      setCooldown(res.resend_cooldown_seconds || 60);
      setOtp(['', '', '', '', '', '']);
      setOtpError(null);
      showToast('info', 'Verification code sent', `We've sent a 6-digit code to ${email.trim()}`);
    } catch (err) {
      const apiError = toApiError(err);
      const fields = fieldErrors(err);
      setErrors(fields);
      if (Object.keys(fields).length === 0) setFormError(apiError.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleOtpChange = (index: number, val: string) => {
    const char = val.replace(/\D/g, '').slice(-1);
    const newOtp = [...otp];
    newOtp[index] = char;
    setOtp(newOtp);
    setOtpError(null);

    if (char && index < 5) {
      otpInputsRef.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (index: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      if (!otp[index] && index > 0) {
        const newOtp = [...otp];
        newOtp[index - 1] = '';
        setOtp(newOtp);
        otpInputsRef.current[index - 1]?.focus();
      } else {
        const newOtp = [...otp];
        newOtp[index] = '';
        setOtp(newOtp);
      }
    } else if (e.key === 'ArrowLeft' && index > 0) {
      otpInputsRef.current[index - 1]?.focus();
    } else if (e.key === 'ArrowRight' && index < 5) {
      otpInputsRef.current[index + 1]?.focus();
    }
  };

  const handleOtpPaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasteData = e.clipboardData.getData('text').trim();
    const digits = pasteData.replace(/\D/g, '').slice(0, 6);
    if (!digits) return;

    const newOtp = [...otp];
    for (let i = 0; i < digits.length; i++) {
      newOtp[i] = digits[i];
    }
    setOtp(newOtp);
    setOtpError(null);

    const focusIndex = Math.min(digits.length, 5);
    otpInputsRef.current[focusIndex]?.focus();
  };

  const isOtpComplete = otp.every((d) => d.length === 1);

  const handleVerifyOtp = async () => {
    const otpCode = otp.join('');
    if (otpCode.length !== 6) {
      setOtpError('Please enter all 6 digits.');
      return;
    }

    setVerifying(true);
    setOtpError(null);
    try {
      // The password entered above must accompany the code (it has to match the one the code
      // was requested with), so nobody else's pending signup can be completed with this code.
      const response = await authService.verifySignupOtp({
        email: email.trim(),
        otp: otpCode,
        password,
      });
      setIsEmailVerified(true);
      await applyTokens(response);
      showToast('success', 'Email verified', `${response.me.organization.name} is ready.`);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      const apiError = toApiError(err);
      setOtpError(apiError.message);
    } finally {
      setVerifying(false);
    }
  };

  const handleResendOtp = async () => {
    if (cooldown > 0 || resending) return;
    setResending(true);
    setOtpError(null);
    try {
      const res = await authService.resendSignupOtp(email.trim());
      setCooldown(res.resend_cooldown_seconds || 60);
      setOtp(['', '', '', '', '', '']);
      otpInputsRef.current[0]?.focus();
      showToast('info', 'Code resent', 'A new 6-digit code has been sent to your work email.');
    } catch (err) {
      const apiError = toApiError(err);
      setOtpError(apiError.message);
    } finally {
      setResending(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setErrors({});
    setFormError(null);

    if (!isEmailVerified) {
      if (!otpSent) {
        await handleRequestVerification();
        return;
      }
      if (isOtpComplete) {
        await handleVerifyOtp();
        return;
      }
      setOtpError('Please enter the 6-digit verification code sent to your email.');
      otpInputsRef.current[0]?.focus();
      return;
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

        {/* Work email field with Send OTP and inline verification */}
        <div className="w-full space-y-1.5">
          <div className="flex items-center justify-between">
            <label htmlFor="signup-email" className="block text-xs font-medium text-slate-700 dark:text-slate-300">
              Work email <span className="text-rose-500 ml-0.5">*</span>
            </label>
            {isEmailVerified && (
              <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Verified
              </span>
            )}
          </div>

          <div className="relative rounded-lg shadow-subtle">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              <Mail className="w-4 h-4" />
            </div>
            <input
              id="signup-email"
              type="email"
              required
              autoComplete="email"
              disabled={isEmailVerified || submitting}
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (otpSent) {
                  setOtpSent(false);
                  setOtp(['', '', '', '', '', '']);
                  setOtpError(null);
                }
              }}
              placeholder="user@gmail.com"
              className={cn(
                'block w-full rounded-lg border bg-white dark:bg-slate-900 px-3 py-2 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 transition-colors pl-9',
                'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
                'disabled:bg-slate-50 dark:disabled:bg-slate-800 disabled:text-slate-400 disabled:cursor-not-allowed',
                errors.email
                  ? 'border-rose-300 text-rose-900 dark:text-rose-200 focus:ring-rose-500 focus:border-rose-500'
                  : 'border-slate-300 dark:border-slate-700 hover:border-slate-400'
              )}
            />
          </div>

          {/* Send OTP button right-aligned beneath input */}
          {!isEmailVerified && (
            <div className="flex justify-end pt-0.5">
              <button
                type="button"
                onClick={handleRequestVerification}
                disabled={submitting || cooldown > 0}
                className="px-3.5 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700/60 shadow-sm transition-colors disabled:opacity-50"
              >
                {submitting
                  ? 'Sending OTP...'
                  : otpSent
                  ? cooldown > 0
                    ? `Resend OTP (${cooldown}s)`
                    : 'Resend OTP'
                  : 'Send OTP'}
              </button>
            </div>
          )}

          {errors.email && <p className="text-xs text-rose-600 dark:text-rose-400">{errors.email}</p>}

          {/* Inline Enter OTP section right here */}
          {otpSent && !isEmailVerified && (
            <div className="p-3.5 sm:p-4 rounded-xl border border-brand-200 dark:border-brand-800/60 bg-brand-50/60 dark:bg-brand-950/20 space-y-3">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-brand-950 dark:text-brand-200">
                  Enter 6-digit OTP sent to <strong className="font-semibold text-brand-700 dark:text-brand-300">{maskEmail(email)}</strong>
                </span>
                {cooldown > 0 ? (
                  <span className="text-slate-400 font-medium">Resend in {cooldown}s</span>
                ) : (
                  <button
                    type="button"
                    onClick={handleResendOtp}
                    disabled={resending}
                    className="font-semibold text-brand-600 hover:text-brand-700 dark:text-brand-400 hover:underline"
                  >
                    {resending ? 'Sending...' : 'Resend OTP'}
                  </button>
                )}
              </div>

              <div className="flex items-center gap-2">
                <div className="flex gap-1.5 sm:gap-2">
                  {otp.map((digit, idx) => (
                    <input
                      key={idx}
                      ref={(el) => {
                        otpInputsRef.current[idx] = el;
                      }}
                      type="text"
                      inputMode="numeric"
                      pattern="\d*"
                      maxLength={1}
                      value={digit}
                      onChange={(e) => handleOtpChange(idx, e.target.value)}
                      onKeyDown={(e) => handleOtpKeyDown(idx, e)}
                      onPaste={handleOtpPaste}
                      className="w-9 h-11 sm:w-10 sm:h-12 text-center text-lg sm:text-xl font-bold rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none transition-all"
                      autoComplete="one-time-code"
                      aria-label={`Digit ${idx + 1}`}
                    />
                  ))}
                </div>

                <Button
                  type="button"
                  size="sm"
                  onClick={handleVerifyOtp}
                  isLoading={verifying}
                  disabled={!isOtpComplete || verifying}
                  className="h-11 sm:h-12 px-3 sm:px-4 text-xs font-semibold shrink-0"
                >
                  Verify OTP
                </Button>
              </div>

              {otpError && (
                <p className="text-xs text-rose-600 dark:text-rose-400 font-medium">{otpError}</p>
              )}
            </div>
          )}

          {/* Verification requirement alert banner from user's screenshot */}
          {!isEmailVerified && (
            <div className="rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 p-2.5 text-xs text-amber-800 dark:text-amber-200 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
              <span>Please verify your email address before creating your organization.</span>
            </div>
          )}

          {isEmailVerified && (
            <div className="rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/50 p-2.5 text-xs text-emerald-800 dark:text-emerald-200 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
              <span>Work email verified successfully.</span>
            </div>
          )}
        </div>

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
        <Button type="submit" className="w-full" isLoading={submitting || verifying}>
          Create organization
        </Button>
      </form>
    </AuthShell>
  );
}

export default SignupPage;


