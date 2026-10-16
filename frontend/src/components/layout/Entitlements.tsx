/**
 * The tenant shell's view of the organization's access (/auth/me `access`): a trial countdown
 * banner, and a guard so a direct URL to a module outside the plan shows an explanation instead of
 * a page whose API calls would all be refused. The API is the enforcement (FEATURE_NOT_ENTITLED);
 * this keeps the UI honest about it.
 */
import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Clock, Lock } from 'lucide-react';
import { Button } from '../common/Button';
import { useAuth } from '../../hooks/useAuth';
import { MODULES, navAllowed, navKeyForPath, trialDaysLeft } from '../../entitlements';
import { sidebarSections } from './Sidebar';

const NAV_ITEMS = sidebarSections.flatMap((s) => s.items.map((i) => ({ key: i.key, path: i.path, title: i.title })));

export function TrialBanner() {
  const { access } = useAuth();
  if (access?.status !== 'trial') return null;
  const days = trialDaysLeft(access.trial_ends_at);
  const left = days === null ? 'You are on a free trial.' : days <= 1 ? 'Your free trial ends today.' : `Your free trial ends in ${days} days.`;
  return (
    <div role="status" className="no-print border-b border-indigo-200 bg-indigo-50 px-4 py-2 text-sm text-indigo-900">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <p className="flex min-w-0 items-center gap-2">
          <Clock className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            <span className="font-semibold">{left}</span> Every module is open during the trial.
          </span>
        </p>
        <Link to="/subscription" className="font-semibold text-indigo-700 underline underline-offset-2 hover:text-indigo-900">
          Choose your plan
        </Link>
      </div>
    </div>
  );
}

export function EntitlementGuard({ children }: { children: ReactNode }) {
  const { access } = useAuth();
  const { pathname } = useLocation();
  const navKey = navKeyForPath(pathname, NAV_ITEMS);
  if (!navKey || navAllowed(access, navKey)) return <>{children}</>;
  const title = NAV_ITEMS.find((i) => i.key === navKey)?.title ?? 'This module';
  const module = MODULES.find((m) => m.nav_items.includes(navKey));
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-3 rounded-full border border-slate-200 bg-slate-100 p-3 text-slate-500">
        <Lock className="h-8 w-8" aria-hidden="true" />
      </div>
      <h2 className="text-xl font-bold text-slate-900">{title} is not in your plan</h2>
      <p className="mt-1 max-w-sm text-sm text-slate-500">
        {module ? `${module.label} is not part of your organization's subscription.` : ''} Ask Rooman to add it.
      </p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        <Link to="/subscription">
          <Button variant="primary" size="sm">View subscription</Button>
        </Link>
        <Link to="/dashboard">
          <Button variant="outline" size="sm">Return to Overview</Button>
        </Link>
      </div>
    </div>
  );
}
