import { toApiError } from '../../services/apiClient';
import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import {
  Lock,
  Mail,
  Building2,
  AlertCircle,
  ArrowRight,
  ShieldCheck,
  User,
} from 'lucide-react';
import { portalCustomerService } from '../../services/portalCustomerService';
import type { PortalInvitationValidateOut } from '../../types/portal';
import { Button } from '../../components/common/Button';

export const PortalActivationPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token') || '';

  const [loading, setLoading] = useState<boolean>(true);
  const [invitation, setInvitation] = useState<PortalInvitationValidateOut | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const [displayName, setDisplayName] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [confirmPassword, setConfirmPassword] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setValidationError('No activation token provided. Please use the activation link sent by your administrator.');
      setLoading(false);
      return;
    }

    let isMounted = true;
    (async () => {
      try {
        setLoading(true);
        setValidationError(null);
        const data = await portalCustomerService.validateInvitation(token);
        if (isMounted) {
          setInvitation(data);
          setDisplayName(data.customer_name || '');
        }
      } catch (err) {
        if (isMounted) {
          const msg =
            toApiError(err).message ||
            'This activation link is invalid, expired, or has already been used.';
          setValidationError(msg);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    })();

    return () => {
      isMounted = false;
    };
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    if (password.length < 8) {
      setSubmitError('Password must be at least 8 characters long.');
      return;
    }
    if (password.toLowerCase() === password || password.toUpperCase() === password) {
      setSubmitError('Password must contain both uppercase and lowercase letters.');
      return;
    }
    if (!/\d/.test(password)) {
      setSubmitError('Password must contain at least one digit.');
      return;
    }
    if (password !== confirmPassword) {
      setSubmitError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    try {
      if (invitation?.organization_id) {
        try {
          localStorage.setItem('rooman.portal_org_id', invitation.organization_id);
        } catch {
          // ignore storage error
        }
      }
      await portalCustomerService.activate({
        token,
        password,
        display_name: displayName.trim() || undefined,
      });
      navigate('/portal', { replace: true });
    } catch (err) {
      const msg =
        toApiError(err).message ||
        'Failed to activate account. The invitation may have expired or already been used.';
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-indigo-600 text-white shadow-md mb-4">
          <Building2 className="w-6 h-6" />
        </div>
        <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">
          {invitation?.portal_name || 'Customer Portal Activation'}
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          {invitation?.organization_name
            ? `Set up your customer account for ${invitation.organization_name}`
            : 'Set up your password to activate your Customer Portal account'}
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-6 shadow-sm border border-slate-200 rounded-2xl sm:px-10">
          {loading && (
            <div className="py-12 flex flex-col items-center justify-center text-center space-y-3">
              <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-slate-600 font-medium">Validating your activation link...</p>
            </div>
          )}

          {!loading && validationError && (
            <div className="space-y-5 text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-rose-50 text-rose-600 mx-auto">
                <AlertCircle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-slate-900">Activation Link Invalid</h3>
                <p className="mt-1.5 text-xs text-slate-600 leading-relaxed">{validationError}</p>
              </div>
              <div className="pt-2">
                <Link to="/portal/login">
                  <Button variant="outline" className="w-full justify-center text-sm">
                    Go to Portal Login
                  </Button>
                </Link>
              </div>
            </div>
          )}

          {!loading && !validationError && invitation && (
            <div>
              {submitError && (
                <div className="mb-5 p-3 rounded-lg bg-rose-50 border border-rose-200 flex items-start gap-2.5 text-xs text-rose-700">
                  <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  <span>{submitError}</span>
                </div>
              )}

              <div className="mb-5 p-3 rounded-lg bg-indigo-50/60 border border-indigo-100 flex items-start gap-2.5 text-xs text-indigo-900">
                <ShieldCheck className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold">Verified Invitation</div>
                  <div className="text-indigo-700 mt-0.5">
                    Invited for <strong>{invitation.customer_name}</strong>
                  </div>
                </div>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                    Email Address
                  </label>
                  <div className="relative rounded-lg shadow-2xs">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                      <Mail className="w-4 h-4" />
                    </div>
                    <input
                      type="email"
                      readOnly
                      disabled
                      value={invitation.email}
                      className="block w-full pl-9 pr-3 py-2 text-sm border border-slate-200 bg-slate-50 text-slate-600 rounded-lg cursor-not-allowed outline-hidden"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                    Your Name / Display Name
                  </label>
                  <div className="relative rounded-lg shadow-2xs">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                      <User className="w-4 h-4" />
                    </div>
                    <input
                      type="text"
                      required
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      placeholder="e.g. Jane Doe"
                      className="block w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-hidden"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                    Create Password
                  </label>
                  <div className="relative rounded-lg shadow-2xs">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                      <Lock className="w-4 h-4" />
                    </div>
                    <input
                      type="password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="block w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-hidden"
                    />
                  </div>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Min. 8 characters with upper, lower case and a number.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                    Confirm Password
                  </label>
                  <div className="relative rounded-lg shadow-2xs">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                      <Lock className="w-4 h-4" />
                    </div>
                    <input
                      type="password"
                      required
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="••••••••"
                      className="block w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-hidden"
                    />
                  </div>
                </div>

                <div className="pt-2">
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={submitting}
                    className="w-full justify-center py-2.5 text-sm font-semibold"
                  >
                    {submitting ? 'Activating account...' : 'Activate & Enter Portal'}
                    {!submitting && <ArrowRight className="w-4 h-4 ml-2" />}
                  </Button>
                </div>
              </form>

              <div className="mt-6 pt-6 border-t border-slate-100 text-center">
                <p className="text-xs text-slate-500">
                  Already have an active account?{' '}
                  <Link to="/portal/login" className="font-semibold text-indigo-600 hover:text-indigo-500">
                    Sign in here
                  </Link>
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
