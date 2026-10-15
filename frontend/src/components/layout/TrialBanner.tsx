import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { AlertTriangle, Clock, Lock } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { hasPurchasablePlan, usePublicPlans } from '../../hooks/usePublicPlans';
import type { PlatformSubscriptionInfo } from '../../types/api';
import { formatDateTime } from '../../utils/format';

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

/** The Subscription settings page, reached as /settings/subscription or /settings?tab=subscription. */
export function isPlansPage(pathname: string, search: string): boolean {
  const path = pathname.replace(/\/+$/, '');
  return path === PLANS_ROUTE || (path === '/settings' && new URLSearchParams(search).get('tab') === 'subscription');
}

const PLANS_SOON = 'Plans will be announced soon.';

/**
 * Slim, persistent notice about the organization's own Rooman plan. Free trial: a countdown while it
 * runs, and a calm "trial has ended / data is safe" message afterwards (the app stays readable; it is
 * not a lock screen). The countdown uses the server's clock, not the browser's. Paid plan: a warning
 * while a payment is overdue, and the same calm message once the plan is no longer active. Renders
 * nothing for organizations without a trial, or with a paid plan in good standing, and nothing on the
 * Subscription page itself, whose status card already says all of this.
 *
 * "View Plans" only appears while at least one plan can actually be bought; until then the banner says
 * plans are coming instead of inviting a choice that does not exist.
 */
export function TrialBanner() {
  const { trial, subscription, serverClockOffsetMs = 0, refreshMe } = useAuth();
  const { pathname, search } = useLocation();
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

  const onPlansPage = isPlansPage(pathname, search);
  const mayOfferPlans = subscription ? subscription.state !== 'active' && subscription.state !== 'past_due' : !!trial;
  const plans = usePublicPlans(mayOfferPlans && !onPlansPage);
  const canChoose = hasPurchasablePlan(plans.data);

  if (onPlansPage) return null;
  if (subscription) return <PaidPlanBanner subscription={subscription} canChoose={canChoose} />;
  if (!trial) return null;

  if (expired) {
    return (
      <div role="status" aria-live="off" className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="min-w-0 flex-1">
            <strong>Your free trial has ended.</strong> Your organization&apos;s data is safe and preserved.{' '}
            {canChoose ? 'Choose a plan to continue using Rooman Billing.' : PLANS_SOON}
          </p>
          {canChoose && (
            <Link
              to={PLANS_ROUTE}
              className="shrink-0 rounded-md bg-amber-600 px-3 py-1 text-xs font-semibold text-white hover:bg-amber-700"
            >
              View Plans
            </Link>
          )}
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
        {canChoose && (
          <Link
            to={PLANS_ROUTE}
            className="shrink-0 rounded-md border border-brand-300 bg-white px-3 py-1 text-xs font-semibold text-brand-700 hover:bg-brand-100"
          >
            View Plans
          </Link>
        )}
      </div>
    </div>
  );
}

function PaidPlanBanner({ subscription, canChoose }: { subscription: PlatformSubscriptionInfo; canChoose: boolean }) {
  if (subscription.state === 'active') return null;

  if (subscription.state === 'past_due') {
    // Links to the plan's status (grace deadline), not to buying one: always available.
    return (
      <div role="status" aria-live="off" className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="min-w-0 flex-1">
            <strong>Your plan payment is overdue.</strong> You can keep working until{' '}
            {formatDateTime(subscription.grace_period_end)} while Razorpay retries the charge.
          </p>
          <Link
            to={PLANS_ROUTE}
            className="shrink-0 rounded-md border border-amber-300 bg-white px-3 py-1 text-xs font-semibold text-amber-800 hover:bg-amber-100"
          >
            View Subscription
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div role="status" aria-live="off" className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
        <p className="min-w-0 flex-1">
          <strong>Your plan is not active.</strong> Your organization&apos;s data is safe and preserved.{' '}
          {canChoose ? 'Choose a plan to continue making changes.' : PLANS_SOON}
        </p>
        {canChoose && (
          <Link
            to={PLANS_ROUTE}
            className="shrink-0 rounded-md bg-amber-600 px-3 py-1 text-xs font-semibold text-white hover:bg-amber-700"
          >
            View Plans
          </Link>
        )}
      </div>
    </div>
  );
}
