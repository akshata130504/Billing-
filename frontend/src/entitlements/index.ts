/**
 * Product modules (modules.json, byte-identical to backend/app/core/modules.json).
 *
 * The API decides access (FEATURE_NOT_ENTITLED / ORGANIZATION_TRIAL_EXPIRED); these helpers only
 * keep the sidebar and direct URLs in step with /auth/me `access`. Nothing here, and nothing the
 * visual editor configures, can grant a module.
 */
import registry from './modules.json';
import type { OrganizationAccess } from '../types/api';

export interface ModuleDef {
  key: string;
  label: string;
  description: string;
  base?: boolean;
  requires?: string[];
  nav_items: string[];
  api_prefixes: string[];
}

export const MODULES: ModuleDef[] = registry.modules as ModuleDef[];
export const CORE_NAV_ITEMS: string[] = registry.core_nav_items;
export const BASE_MODULE_KEYS = MODULES.filter((m) => m.base).map((m) => m.key);
export const OPTIONAL_MODULES = MODULES.filter((m) => !m.base);

/** Whether a sidebar item (appUi/keys.json key) is open to this organization. No access info
 * (previews, legacy test doubles) means no restriction - the API still enforces. */
export function navAllowed(access: OrganizationAccess | null | undefined, navKey: string): boolean {
  if (!access) return true;
  return access.nav_items.includes(navKey);
}

/** `keys` plus every module they require (timesheets -> projects), in registry order. */
export function withRequirements(keys: Iterable<string>): string[] {
  const out = new Set(keys);
  let changed = true;
  while (changed) {
    changed = false;
    for (const key of [...out]) {
      for (const dep of MODULES.find((m) => m.key === key)?.requires ?? []) {
        if (!out.has(dep)) {
          out.add(dep);
          changed = true;
        }
      }
    }
  }
  return OPTIONAL_MODULES.map((m) => m.key).filter((k) => out.has(k));
}

/** Modules that require `key` (unchecking projects must uncheck timesheets). */
export function dependents(key: string): string[] {
  return OPTIONAL_MODULES.filter((m) => m.requires?.includes(key)).map((m) => m.key);
}

export function moduleLabel(key: string): string {
  return MODULES.find((m) => m.key === key)?.label ?? key;
}

/** Days left in a trial, rounded up (1 on the last day; 0 or less once it has ended). */
export function trialDaysLeft(trialEndsAt: string | null | undefined, now: Date = new Date()): number | null {
  if (!trialEndsAt) return null;
  return Math.ceil((new Date(trialEndsAt).getTime() - now.getTime()) / 86_400_000);
}

/** The sidebar key that owns `pathname`: the longest item path matching whole segments. */
export function navKeyForPath(pathname: string, items: Array<{ key: string; path: string }>): string | null {
  let best: { key: string; path: string } | null = null;
  for (const item of items) {
    if (pathname === item.path || pathname.startsWith(`${item.path}/`)) {
      if (!best || item.path.length > best.path.length) best = item;
    }
  }
  return best?.key ?? null;
}
