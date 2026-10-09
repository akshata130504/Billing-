import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Clock, Lock } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';

export const PLANS_ROUTE = '/settings/subscription';

/** "12 minutes", "45 seconds", "3 hours", "5 days" - rounded up so it never reads 0 while time is left. */
export function formatTimeLeft(totalSeconds: number): string {
  const seconds = Math.max(0, Math.ceil(totalSeconds));
  if (seconds < 60) return `${seconds} second${seconds === 1 ? '' : 's'}`;
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'}`;
  const hours = Math.ceil(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? '' : 's'}`;
  const days = Math.ceil(hours / 24);
  return `${days} days`;
}

/**
 * Slim, persistent notice about the organization's own free trial: a countdown while it runs, and a
 * calm "trial has ended / data is safe" message afterwards (the app stays readable; it is not a lock
 * screen). The countdown uses the server's clock, not the browser's. Renders nothing for
 * organizations without a trial.
 */
export function TrialBanner() {
  const { trial, serverClockOffsetMs = 0, refreshMe } = useAuth();
  const [now, setNow] = useState(() => Date.now());
  const refreshed = useRef(false);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const endsAtMs = trial ? Date.parse(trial.trial_ends_at) : NaN;
  const remainingSeconds = trial && !Number.isNaN(endsAtMs) ? (endsAtMs - (now + serverClockOffsetMs)) / 1000 : 0;
  const expired = !!trial && (trial.state === 'trial_expired' || remainingSeconds <= 0);

  // The clock hit zero while the page was open: ask the server for the authoritative state once.
  useEffect(() => {
    if (!trial) {
      refreshed.current = false;
      return;
    }
    if (trial.state === 'trialing' && remainingSeconds <= 0 && !refreshed.current) {
      refreshed.current = true;
      void refreshMe();
    }
  }, [trial, remainingSeconds, refreshMe]);

  if (!trial) return null;

  if (expired) {
    return (
      <div role="status" aria-live="off" className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="min-w-0 flex-1">
            <strong>Your free trial has ended.</strong> Your organization&apos;s data is safe and preserved.
            Choose a plan to continue using Rooman Billing.
          </p>
          <Link
            to={PLANS_ROUTE}
            className="shrink-0 rounded-md bg-amber-600 px-3 py-1 text-xs font-semibold text-white hover:bg-amber-700"
          >
            View Plans
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div role="status" aria-live="off" className="border-b border-brand-100 bg-brand-50 px-4 py-1.5 text-sm text-brand-900">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Clock className="h-4 w-4 shrink-0" aria-hidden="true" />
        <p className="min-w-0 flex-1">
          Your free trial ends in <strong>{formatTimeLeft(remainingSeconds)}</strong>
        </p>
        <Link
          to={PLANS_ROUTE}
          className="shrink-0 rounded-md border border-brand-300 bg-white px-3 py-1 text-xs font-semibold text-brand-700 hover:bg-brand-100"
        >
          View Plans
        </Link>
      </div>
    </div>
  );
}
