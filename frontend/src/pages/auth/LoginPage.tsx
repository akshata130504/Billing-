import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Mail, Lock, Eye, EyeOff, ArrowRight } from 'lucide-react';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common/Toast';
import { LoadingState } from '../../components/common/LoadingState';
import { useAuth } from '../../hooks/useAuth';
import { fieldErrors, toApiError } from '../../services/apiClient';
import { FormErrorBanner } from './AuthShell';
import { RoomanLogo } from '../../components/common/RoomanLogo';

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
  const [showPassword, setShowPassword] = useState(false);
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
    <div className="min-h-screen w-full flex flex-col lg:flex-row relative overflow-hidden bg-[#070A1E] select-none">
      {/* =========================================================================
          LEFT SHOWCASE: COSMIC HERO WITH LUMINOUS GLASS ORBS
      ========================================================================== */}
      <div className="w-full lg:w-[54%] relative flex flex-col justify-between p-8 sm:p-12 lg:p-16 overflow-hidden z-10">
        {/* Ambient background glows */}
        <div className="absolute top-1/4 -left-20 w-[480px] h-[480px] bg-gradient-to-tr from-[#1E3A8A]/30 via-[#3B82F6]/20 to-transparent blur-[100px] rounded-full pointer-events-none" />
        <div className="absolute bottom-10 right-10 w-[420px] h-[420px] bg-gradient-to-br from-[#8B5CF6]/25 via-[#EC4899]/20 to-transparent blur-[90px] rounded-full pointer-events-none" />

        {/* Luminous Glass Orbs (Matching mockup curvature & glow) */}
        <div
          className="absolute -bottom-24 -left-20 w-[460px] h-[460px] rounded-full pointer-events-none border border-blue-400/25 shadow-[inset_0_0_80px_rgba(59,130,246,0.22)]"
          style={{
            background: 'radial-gradient(circle at 75% 30%, rgba(96,165,250,0.35) 0%, rgba(30,58,138,0.4) 50%, rgba(7,10,30,0.85) 100%)',
          }}
        />
        <div
          className="absolute bottom-12 left-[28%] w-[420px] h-[420px] rounded-full pointer-events-none border border-fuchsia-400/25 shadow-[inset_0_0_70px_rgba(217,70,239,0.2)]"
          style={{
            background: 'radial-gradient(circle at 65% 25%, rgba(244,114,182,0.3) 0%, rgba(147,51,234,0.35) 45%, rgba(7,10,30,0.85) 100%)',
          }}
        />
        <div
          className="absolute -top-16 left-[42%] w-[320px] h-[320px] rounded-full pointer-events-none border border-indigo-400/20 shadow-[inset_0_0_50px_rgba(99,102,241,0.18)]"
          style={{
            background: 'radial-gradient(circle at 50% 50%, rgba(99,102,241,0.25) 0%, rgba(15,23,42,0.4) 60%, rgba(7,10,30,0.8) 100%)',
          }}
        />

        {/* Top Left: Logo */}
        <div className="relative z-10 mb-12 lg:mb-0">
          <Link to="/" className="inline-block">
            <RoomanLogo variant="brand" size="lg" showBillingBadge />
          </Link>
        </div>

        {/* Middle: Headline & Value Proposition */}
        <div className="relative z-10 max-w-xl my-auto py-8">
          <p className="text-[11px] sm:text-xs font-bold tracking-[0.25em] text-slate-400 uppercase mb-4">
            BUILT FOR WHAT&apos;S NEXT
          </p>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-white tracking-tight leading-[1.1] mb-6">
            Powerful billing.<br />
            <span className="text-white">Smarter </span>
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-[#8EA5FF] via-[#A855F7] to-[#EC4899]">
              business.
            </span>
          </h1>

          <p className="text-slate-300 text-base sm:text-lg leading-relaxed font-normal mb-8 max-w-md">
            One connected platform for products, pricing, quotes, invoices, payments and revenue operations.
          </p>

          <div className="w-16 h-1 bg-gradient-to-r from-[#3F51C9] via-[#8B5CF6] to-[#E83E8C] rounded-full" />
        </div>

        {/* Bottom Left: Copyright & Tagline */}
        <div className="relative z-10 pt-8 text-xs text-slate-400 space-y-1.5">
          <p>&copy; {new Date().getFullYear()} Rooman Billing. All rights reserved.</p>
          <p className="tracking-widest text-[10px] sm:text-[11px] uppercase font-semibold text-slate-500">
            INNOVATE &nbsp;|&nbsp; INTEGRATE &nbsp;|&nbsp; EMPOWER
          </p>
        </div>
      </div>

      {/* =========================================================================
          RIGHT AREA: ORGANIC LIGHT BACKDROP WITH FLOATING SIGN-IN CARD
      ========================================================================== */}
      <div className="w-full lg:w-[46%] min-h-full flex flex-col justify-center items-center p-6 sm:p-10 lg:p-12 relative z-20">
        {/* Soft Organic Light Curve Backdrop on Right */}
        <div className="absolute inset-y-0 right-0 w-full lg:w-[110%] bg-gradient-to-b from-[#F2F4FD] via-[#F7F8FE] to-[#F1F3FB] -z-10 rounded-t-3xl lg:rounded-t-none lg:rounded-l-[3.5rem] shadow-2xl border-l border-white/60" />

        {/* Top Right Header Text (Simple Billing. Stronger Tomorrow.) */}
        <div className="hidden lg:block absolute top-8 right-12 text-right">
          <div className="text-[11px] font-bold tracking-widest text-slate-400 uppercase">
            SIMPLE BILLING.
          </div>
          <div className="text-[11px] font-bold tracking-widest text-slate-400 uppercase">
            STRONGER TOMORROW.
          </div>
          <div className="w-10 h-0.5 bg-gradient-to-r from-[#8EA5FF] to-[#E83E8C] ml-auto mt-1.5 rounded-full" />
        </div>

        {/* Floating Sign-In Card */}
        <div className="w-full max-w-md bg-white rounded-3xl p-8 sm:p-10 shadow-2xl border border-slate-100/90 relative">
          {/* Card Brand Logo */}
          <div className="flex justify-center mb-6">
            <RoomanLogo variant="brand" size="lg" showBillingBadge />
          </div>

          {/* Heading */}
          <div className="text-center mb-6">
            <h2 className="text-2xl sm:text-[26px] font-bold text-[#11194F] tracking-tight flex items-center justify-center gap-2">
              <span>Welcome back</span>
              <span className="text-2xl">👋</span>
            </h2>
            <p className="mt-1.5 text-xs sm:text-sm text-slate-500">
              Sign in to your Rooman Billing workspace.
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <FormErrorBanner message={formError} />

            <div>
              <Input
                label="Email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                error={errors.email}
                leadingIcon={<Mail className="w-4 h-4 text-slate-400" />}
                placeholder="you@company.com"
                className="bg-white border-slate-200 focus:border-[#3F51C9] rounded-xl text-sm"
              />
            </div>

            <div>
              <Input
                label="Password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                error={errors.password}
                leadingIcon={<Lock className="w-4 h-4 text-slate-400" />}
                placeholder="Enter your password"
                className="bg-white border-slate-200 focus:border-[#3F51C9] rounded-xl text-sm"
                trailingIcon={
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="pointer-events-auto text-slate-400 hover:text-slate-600 focus:outline-none cursor-pointer"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                }
              />
              <div className="mt-2 text-right">
                <Link
                  to="/forgot-password"
                  className="text-xs font-semibold text-[#3F51C9] hover:text-[#25247A] transition-colors"
                >
                  Forgot password?
                </Link>
              </div>
            </div>

            {/* Gradient Action Button */}
            <button
              type="submit"
              disabled={submitting}
              className="w-full mt-2 py-3.5 px-4 rounded-xl text-white font-semibold text-sm flex items-center justify-center gap-2 bg-gradient-to-r from-[#11194F] via-[#25247A] to-[#E83E8C] hover:opacity-95 shadow-md hover:shadow-lg active:scale-[0.99] transition-all disabled:opacity-50 cursor-pointer"
            >
              {submitting ? (
                <span>Signing in...</span>
              ) : (
                <>
                  <span>Sign in</span>
                  <ArrowRight className="w-4 h-4 ml-0.5" />
                </>
              )}
            </button>

            {/* Security Assurance */}
            <div className="flex items-center justify-center gap-1.5 text-[11px] sm:text-xs text-slate-500 pt-1">
              <Lock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <span>Secure access to your billing workspace</span>
            </div>
          </form>

          {/* Footer inside card */}
          <div className="mt-7 pt-5 border-t border-slate-100 text-center text-xs text-slate-600">
            New to Rooman Billing?{' '}
            <Link
              to="/signup"
              className="font-bold text-[#3F51C9] hover:text-[#25247A] hover:underline"
            >
              Create your organization
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
