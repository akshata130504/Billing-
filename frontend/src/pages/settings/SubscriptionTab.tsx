import { useEffect, useState, type ReactNode } from 'react';
import { AlertTriangle, CalendarClock, Check, CheckCircle2, Clock, FlaskConical, Info, Lock, XCircle } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingSpinner } from '../../components/common/LoadingState';
import { formatTimeLeft } from '../../components/layout/TrialBanner';
import { useAuth } from '../../hooks/useAuth';
import { hasPurchasablePlan, usePublicPlans, useSandboxPlans } from '../../hooks/usePublicPlans';
import type { PublicPlan } from '../../services/platformSubscriptionService';
import type { PlatformSubscriptionInfo, TrialInfo } from '../../types/api';
import { cn } from '../../utils/cn';
import { formatDate, formatDateTime, humanize } from '../../utils/format';
import { formatInterval, formatPlanPrice, hasPaidPlan, seatLabel, taxLabel } from './subscriptionDisplay';
import { useSubscriptionCheckout, type CheckoutNotice } from './useSubscriptionCheckout';
import { CancelPlanSection } from './CancelPlanSection';
import { ReceiptsSection } from './ReceiptsSection';

/**
 * The organization's own Rooman plan: where it stands (trial, paid, past due, ended) and the published
 * plans it can buy. Everything shown comes from the server - /auth/me for the current state and the
 * public catalog for plans - and only the Owner can start a checkout, which the server re-checks.
 * The global trial/plan banner hides itself on this page; the status card below is the one place the
 * state is shown here.
 */
export function SubscriptionTab() {
  const { trial, subscription, membership, refreshMe, serverClockOffsetMs = 0 } = useAuth();
  const plansQuery = usePublicPlans();
  const sandboxQuery = useSandboxPlans();
  const checkout = useSubscriptionCheckout({
    refreshMe,
    refreshPlans: () => {
      void plansQuery.refetch();
      void sandboxQuery.refetch();
    },
  });

  const isOwner = membership?.role === 'owner';
  // Payment receipts: Finance, Admin and Owner (the server enforces the same rule).
  const canSeeReceipts = membership?.role === 'owner' || membership?.role === 'admin' || membership?.role === 'finance';
  const paid = hasPaidPlan(subscription);
  // Commercial plans and sandbox TEST plans never mix, whatever a response contains.
  const plans = (plansQuery.data?.plans ?? []).filter((p) => !p.sandbox);
  const sandboxPlans = (sandboxQuery.data?.plans ?? []).filter((p) => p.sandbox);
  const currentPlanName = subscription?.plan_code
    ? [...plans, ...sandboxPlans].find((p) => p.code === subscription.plan_code)?.name ?? humanize(subscription.plan_code)
    : null;
  const cardProps = (plan: PublicPlan) => ({
    plan,
    isOwner,
    isCurrent: paid && subscription?.plan_code === plan.code,
    blockedByPaidPlan: paid,
    busy: checkout.busy,
    loading: checkout.busy && checkout.planCode === plan.code,
    onChoose: () => void checkout.choosePlan(plan),
  });

  return (
    <div className="space-y-6">
      <StatusCard
        trial={trial ?? null}
        subscription={subscription ?? null}
        planName={currentPlanName}
        serverClockOffsetMs={serverClockOffsetMs}
        canChoose={hasPurchasablePlan(plansQuery.data)}
      />

      {checkout.notice && <NoticeBanner notice={checkout.notice} onDismiss={checkout.dismissNotice} />}

      {subscription && (
        <CancelPlanSection subscription={subscription} isOwner={isOwner} refreshMe={refreshMe} onNotice={checkout.showNotice} />
      )}

      {canSeeReceipts && <ReceiptsSection />}

      <section aria-labelledby="plans-heading" className="space-y-4">
        <div>
          <h2 id="plans-heading" className="text-base font-bold text-slate-900">
            Plans
          </h2>
          {!isOwner && plans.length > 0 && (
            <p className="mt-1 text-sm text-slate-600">Ask your organization Owner to choose a plan.</p>
          )}
          {isOwner && paid && plans.length > 0 && (
            <p className="mt-1 text-sm text-slate-600">
              Your organization already has a paid plan. Changing plans is not available here yet.
            </p>
          )}
        </div>

        {plansQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500" role="status">
            <LoadingSpinner size="sm" /> Loading plans...
          </div>
        ) : plansQuery.isError ? (
          <ErrorState
            title="Plans could not be loaded"
            message="Please try again in a moment."
            onRetry={() => void plansQuery.refetch()}
          />
        ) : plans.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center">
            <p className="text-sm font-semibold text-slate-900">Plans will be announced soon.</p>
            <p className="mt-1 text-sm text-slate-600">Your organization&apos;s data stays safe in the meantime.</p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            {plans.map((plan) => (
              <PlanCard key={plan.code} {...cardProps(plan)} />
            ))}
          </div>
        )}
      </section>

      {sandboxPlans.length > 0 && (
        <section
          aria-labelledby="sandbox-plans-heading"
          data-testid="sandbox-plans"
          className="space-y-4 rounded-xl border-2 border-dashed border-amber-400 bg-amber-50/60 p-4"
        >
          <div>
            <SandboxBadge />
            <h2 id="sandbox-plans-heading" className="mt-2 text-base font-bold text-slate-900">
              Sandbox test plan
            </h2>
            <p className="mt-1 text-sm text-slate-700">
              Only for checking the purchase flow with Razorpay Test Mode and a Razorpay test card. It is not a
              Rooman Billing plan you can buy for real, and it is only shown in a local test setup.
            </p>
            {!isOwner && <p className="mt-1 text-sm text-slate-600">Only the organization Owner can run a test purchase.</p>}
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {sandboxPlans.map((plan) => (
              <PlanCard key={plan.code} {...cardProps(plan)} />
            ))}
          </div>
        </section>
      )}

      {checkout.phase === 'verifying' && (
        <p role="status" className="flex items-center gap-2 text-sm text-slate-600">
          <LoadingSpinner size="sm" /> Confirming your payment with Razorpay...
        </p>
      )}
    </div>
  );
}

export const SANDBOX_LABEL = 'TEST MODE — NOT A COMMERCIAL OFFER';

// --- current state ------------------------------------------------------------------------------

interface StatusCardProps {
  trial: TrialInfo | null;
  subscription: PlatformSubscriptionInfo | null;
  planName: string | null;
  serverClockOffsetMs: number;
  /** At least one plan can be bought now; until then the card does not ask the user to choose one. */
  canChoose: boolean;
}

function StatusCard(props: StatusCardProps) {
  // The banner (which counts down every second elsewhere) is hidden on this page: keep this countdown live.
  const [, setTick] = useState(0);
  const counting = props.trial?.state === 'trialing';
  useEffect(() => {
    if (!counting) return;
    const timer = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [counting]);

  const status = describeStatus(props);
  const Icon = status.icon;
  return (
    <div
      data-testid="subscription-status"
      className={cn('rounded-xl border bg-white p-5 shadow-2xs', TONE_BORDER[status.tone])}
    >
      <div className="flex items-start gap-3">
        <Icon className={cn('mt-0.5 h-5 w-5 shrink-0', TONE_ICON[status.tone])} aria-hidden="true" />
        <div className="min-w-0">
          {props.subscription?.sandbox && <SandboxBadge />}
          <h2 className="text-base font-bold text-slate-900">{status.title}</h2>
          {status.lines.map((line) => (
            <p key={line} className="mt-1 text-sm text-slate-600">
              {line}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}

/** The unmistakable marker on anything belonging to a sandbox TEST plan. */
function SandboxBadge() {
  return (
    <p className="mb-1 inline-flex items-center gap-1.5 rounded-md bg-amber-500 px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-white">
      <FlaskConical className="h-3.5 w-3.5" aria-hidden="true" />
      {SANDBOX_LABEL}
    </p>
  );
}

type Tone = CheckoutNotice['tone'] | 'neutral';

const TONE_BORDER: Record<Tone, string> = {
  success: 'border-emerald-200',
  info: 'border-brand-200',
  warning: 'border-amber-200',
  error: 'border-rose-200',
  neutral: 'border-slate-200/80',
};

const TONE_ICON: Record<Tone, string> = {
  success: 'text-emerald-600',
  info: 'text-brand-600',
  warning: 'text-amber-600',
  error: 'text-rose-600',
  neutral: 'text-slate-500',
};

interface StatusDescription {
  tone: Tone;
  icon: typeof Check;
  title: string;
  lines: string[];
}

const DATA_SAFE = "Your organization's data is safe and preserved.";

export function describeStatus({ trial, subscription, planName, serverClockOffsetMs, canChoose }: StatusCardProps): StatusDescription {
  // With nothing to buy yet, the plans section's "Plans will be announced soon." says what comes next.
  const choose = (sentence: string) => (canChoose ? ` ${sentence}` : '');
  if (subscription) {
    const plan = planName ? (/\bplan\b/i.test(planName) ? planName : `${planName} plan`) : 'Your plan';
    switch (subscription.state) {
      case 'active':
        if (subscription.cancel_at_period_end) {
          return {
            tone: 'warning',
            icon: CalendarClock,
            title: `${plan} - cancellation scheduled`,
            lines: [
              `Your plan stays active until ${formatDate(subscription.current_period_end)} and will not renew.`,
            ],
          };
        }
        return {
          tone: 'success',
          icon: CheckCircle2,
          title: `${plan} is active`,
          lines: [`Current billing period ends on ${formatDate(subscription.current_period_end)}.`],
        };
      case 'past_due':
        return {
          tone: 'warning',
          icon: AlertTriangle,
          title: 'Payment overdue',
          lines: [
            'We could not collect the latest payment for your plan. Razorpay retries the charge automatically.',
            `You can keep working until ${formatDateTime(subscription.grace_period_end)}.`,
          ],
        };
      default:
        return {
          tone: 'neutral',
          icon: Lock,
          title: 'Your plan is not active',
          lines: [`${DATA_SAFE}${choose('Choose a plan to continue making changes.')}`],
        };
    }
  }
  if (trial) {
    const endsAt = Date.parse(trial.trial_ends_at);
    const remaining = Number.isNaN(endsAt) ? 0 : (endsAt - (Date.now() + serverClockOffsetMs)) / 1000;
    if (trial.state === 'trial_expired' || remaining <= 0) {
      return {
        tone: 'warning',
        icon: Lock,
        title: 'Your free trial has ended',
        lines: [`${DATA_SAFE}${choose('Choose a plan to continue using Rooman Billing.')}`],
      };
    }
    return {
      tone: 'info',
      icon: Clock,
      title: 'Free trial',
      lines: [`Your free trial ends in ${formatTimeLeft(remaining)}. Every feature is included until then.`],
    };
  }
  return {
    tone: 'neutral',
    icon: Info,
    title: 'Subscription',
    lines: canChoose ? ['Choose the plan that fits your organization.'] : [],
  };
}

// --- plans --------------------------------------------------------------------------------------

interface PlanCardProps {
  plan: PublicPlan;
  isOwner: boolean;
  isCurrent: boolean;
  blockedByPaidPlan: boolean;
  busy: boolean;
  loading: boolean;
  onChoose: () => void;
}

function PlanCard({ plan, isOwner, isCurrent, blockedByPaidPlan, busy, loading, onChoose }: PlanCardProps) {
  const tax = taxLabel(plan.tax_treatment);
  const optional = plan.modules.filter((m) => !m.base);
  const base = plan.modules.filter((m) => m.base);

  let action: ReactNode;
  if (isCurrent) {
    action = (
      <Button className="mt-5 w-full" variant="outline" disabled>
        Current plan
      </Button>
    );
  } else if (!isOwner) {
    action = null;
  } else if (blockedByPaidPlan) {
    action = (
      <Button className="mt-5 w-full" variant="outline" disabled>
        Choose {plan.name}
      </Button>
    );
  } else if (!plan.purchasable) {
    action = (
      <>
        <Button className="mt-5 w-full" variant="outline" disabled>
          Not available yet
        </Button>
        <p className="mt-2 text-xs text-slate-500">Checkout for this plan is not open yet.</p>
      </>
    );
  } else {
    action = (
      <Button className="mt-5 w-full" variant="primary" onClick={onChoose} disabled={busy} isLoading={loading}>
        Choose {plan.name}
      </Button>
    );
  }

  return (
    <section
      aria-label={plan.name}
      data-testid={plan.sandbox ? 'sandbox-plan-card' : 'plan-card'}
      className={cn(
        'flex flex-col rounded-xl border bg-white p-5 shadow-2xs',
        isCurrent ? 'border-brand-300 ring-1 ring-brand-200' : plan.sandbox ? 'border-amber-300' : 'border-slate-200/80'
      )}
    >
      {plan.sandbox && <SandboxBadge />}
      <h3 className="text-lg font-bold text-slate-900">{plan.name}</h3>
      {plan.description && <p className="mt-1 text-sm text-slate-600">{plan.description}</p>}
      <p className="mt-4">
        <span className="text-2xl font-bold text-slate-900">
          {formatPlanPrice(plan.price.amount_minor, plan.price.currency)}
        </span>{' '}
        <span className="text-sm text-slate-500">{formatInterval(plan.price.interval, plan.price.interval_count)}</span>
      </p>
      {tax && <p className="text-xs text-slate-500">{tax}</p>}
      <p className="mt-3 text-sm font-medium text-slate-700">{seatLabel(plan.seat_limit)}</p>

      {plan.bundles.length > 0 && (
        <ul className="mt-4 space-y-2 border-t border-slate-100 pt-3 text-sm" aria-label={`${plan.name} bundles`}>
          {plan.bundles.map((b) => (
            <li key={b.key}>
              <p className="font-medium text-slate-800">{b.label}</p>
              <p className="text-xs text-slate-500">{b.description}</p>
            </li>
          ))}
        </ul>
      )}

      <ul className="mt-4 flex-1 space-y-1.5 border-t border-slate-100 pt-3 text-sm" aria-label={`${plan.name} features`}>
        {[...base, ...optional].map((m) => (
          <li key={m.key} className="flex items-center gap-2 text-slate-700">
            <Check className="h-4 w-4 shrink-0 text-brand-600" aria-hidden="true" />
            {m.label}
          </li>
        ))}
      </ul>

      {action}
    </section>
  );
}

// --- checkout result ----------------------------------------------------------------------------

const NOTICE_ICON: Record<CheckoutNotice['tone'], typeof Check> = {
  success: CheckCircle2,
  info: Info,
  warning: AlertTriangle,
  error: XCircle,
};

const NOTICE_STYLE: Record<CheckoutNotice['tone'], string> = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  info: 'border-brand-200 bg-brand-50 text-brand-900',
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
  error: 'border-rose-200 bg-rose-50 text-rose-900',
};

function NoticeBanner({ notice, onDismiss }: { notice: CheckoutNotice; onDismiss: () => void }) {
  const Icon = NOTICE_ICON[notice.tone];
  return (
    <div
      role={notice.tone === 'error' ? 'alert' : 'status'}
      data-testid="checkout-notice"
      className={cn('flex items-start gap-3 rounded-xl border p-4 text-sm', NOTICE_STYLE[notice.tone])}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{notice.title}</p>
        <p className="mt-0.5">{notice.message}</p>
      </div>
      <button type="button" onClick={onDismiss} className="shrink-0 text-xs font-medium underline">
        Dismiss
      </button>
    </div>
  );
}
