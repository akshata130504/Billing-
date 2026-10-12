import type { WidgetVisibilityState } from '../../types';

export const DEFAULT_WIDGET_VISIBILITY: WidgetVisibilityState = {
  revenueIntelligence: true,
  actionCenter: true,
  billingPipeline: true,
  customerHealth: true,
  paymentRecovery: true,
  recentTransactions: true,
  activityTimeline: true,
};

/**
 * "Customize Dashboard" choices are a per-user convenience, kept in this browser for each
 * user and organization (like the account preferences). Storage may be unavailable (private
 * mode, blocked site data): every access is guarded and the defaults apply.
 */
export function widgetVisibilityKey(userId?: string | null, organizationId?: string | null): string | null {
  return userId ? `rooman.dashboard.widgets.${userId}.${organizationId || 'none'}` : null;
}

export function loadWidgetVisibility(key: string | null): WidgetVisibilityState {
  if (!key) return DEFAULT_WIDGET_VISIBILITY;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return DEFAULT_WIDGET_VISIBILITY;
    const stored = JSON.parse(raw) as Record<string, unknown>;
    const next = { ...DEFAULT_WIDGET_VISIBILITY };
    for (const k of Object.keys(next) as (keyof WidgetVisibilityState)[]) {
      if (typeof stored?.[k] === 'boolean') next[k] = stored[k] as boolean;
    }
    return next;
  } catch {
    return DEFAULT_WIDGET_VISIBILITY;
  }
}

export function saveWidgetVisibility(key: string | null, value: WidgetVisibilityState): void {
  if (!key) return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage unavailable: the choice lasts for this visit only.
  }
}

export function clearWidgetVisibility(key: string | null): void {
  if (!key) return;
  try {
    localStorage.removeItem(key);
  } catch {
    // Storage unavailable.
  }
}
