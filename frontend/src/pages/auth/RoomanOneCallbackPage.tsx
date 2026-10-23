import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { LoadingState } from '../../components/common/LoadingState';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';
import { authService } from '../../services/authService';
import { isSafeAppPath } from '../../utils/redirect';

/**
 * Landing page of "Sign in with Rooman One". The backend callback redirects here with a
 * one-time, 60-second hand-over in the URL fragment (#handoff=...), which browsers never send
 * to servers. It is removed from the address bar at once, then redeemed for the same result as
 * a password sign-in: tokens, or the two-factor step on the login page.
 */
export function RoomanOneCallbackPage() {
  const { applyTokens } = useAuth();
  const navigate = useNavigate();
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // StrictMode runs effects twice; a hand-over works only once
    started.current = true;

    const handoff = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('handoff');
    window.history.replaceState(null, '', window.location.pathname);

    const fail = (message: string) =>
      navigate(`/login?${new URLSearchParams({ sso_error: message }).toString()}`, { replace: true });

    if (!handoff) {
      fail('Your Rooman One sign-in expired or was interrupted. Please try again.');
      return;
    }

    authService
      .roomanOneExchange(handoff)
      .then(async (result) => {
        const next = isSafeAppPath(result.next) ? result.next : '/dashboard';
        if (result.mfa_required) {
          navigate('/login', { replace: true, state: { mfaToken: result.mfa_token, from: { pathname: next } } });
          return;
        }
        await applyTokens(result);
        navigate(next, { replace: true });
      })
      .catch((err) => fail(toApiError(err).message));
  }, [applyTokens, navigate]);

  return <LoadingState message="Signing you in with Rooman One..." />;
}

export default RoomanOneCallbackPage;
