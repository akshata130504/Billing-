import { Check } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';

/**
 * DISPLAY ONLY. These are the three plans Rooman Billing will offer, shown so a user whose trial has
 * ended can see where plans will live. Names, feature counts and prices below are placeholders:
 * nothing here selects a plan, takes payment or changes what the organization can use.
 */
export const PLACEHOLDER_PLANS = [
  { key: 'plan-1', name: 'Plan 1', features: 'Up to 5 features' },
  { key: 'plan-2', name: 'Plan 2', features: 'Up to 10 features' },
  { key: 'plan-3', name: 'Plan 3', features: 'Up to 15-20 features' },
] as const;

export function SubscriptionTab() {
  const { trial } = useAuth();
  const { showToast } = useToast();
  const expired = trial?.state === 'trial_expired';

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-2xs">
        <h2 className="text-base font-bold text-slate-900">Plans</h2>
        <p className="mt-1 text-sm text-slate-600">
          {expired
            ? "Your free trial has ended. Your organization's data is safe and preserved - choose a plan to continue using Rooman Billing."
            : trial
              ? 'You are on a free trial with every feature included. Plans below show what comes next.'
              : 'Choose the plan that fits your organization.'}
        </p>
        <p className="mt-2 text-xs text-slate-500">
          Plan details and pricing are placeholders and will be announced soon. Choosing a plan is not available yet.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {PLACEHOLDER_PLANS.map((plan) => (
          <section
            key={plan.key}
            aria-label={plan.name}
            data-testid="plan-card"
            className="flex flex-col rounded-xl border border-slate-200/80 bg-white p-5 shadow-2xs"
          >
            <h3 className="text-lg font-bold text-slate-900">{plan.name}</h3>
            <p className="mt-1 flex items-center gap-2 text-sm font-medium text-slate-700">
              <Check className="h-4 w-4 text-brand-600" aria-hidden="true" />
              {plan.features}
            </p>
            <dl className="mt-4 space-y-2 text-sm">
              <div className="flex items-baseline justify-between border-t border-slate-100 pt-2">
                <dt className="text-slate-500">Monthly price</dt>
                <dd className="font-semibold text-slate-900">To be announced</dd>
              </div>
              <div className="flex items-baseline justify-between border-t border-slate-100 pt-2">
                <dt className="text-slate-500">Yearly price</dt>
                <dd className="font-semibold text-slate-900">To be announced</dd>
              </div>
            </dl>
            <Button
              className="mt-5 w-full"
              variant="primary"
              onClick={() =>
                showToast('info', 'Coming soon', 'Choosing a plan is not available yet. Your data stays safe in the meantime.')
              }
            >
              Choose Plan
            </Button>
          </section>
        ))}
      </div>
    </div>
  );
}
