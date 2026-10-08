import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import keys from '../appUi/keys.json';
import { sidebarSections } from '../components/layout/Sidebar';
import {
  BASE_MODULE_KEYS,
  CORE_NAV_ITEMS,
  MODULES,
  dependents,
  navAllowed,
  navKeyForPath,
  trialDaysLeft,
  withRequirements,
} from './index';
import type { OrganizationAccess } from '../types/api';

const access = (nav_items: string[]): OrganizationAccess => ({
  status: 'active', trial_started_at: null, trial_ends_at: null, module_access: 'entitled',
  modules: [], nav_items, seat_limit: 3, seats_used: 1,
});

describe('module registry', () => {
  it('is byte-identical to the backend copy', () => {
    const here = readFileSync(resolve(__dirname, 'modules.json'));
    const backend = readFileSync(resolve(__dirname, '../../../backend/app/core/modules.json'));
    expect(here.equals(backend)).toBe(true);
  });

  it('maps every sidebar item exactly once (core or one module)', () => {
    const sidebar = sidebarSections.flatMap((s) => s.items.map((i) => i.key)).sort();
    const mapped = [...CORE_NAV_ITEMS, ...MODULES.flatMap((m) => m.nav_items)];
    expect(new Set(mapped).size).toBe(mapped.length);
    expect([...mapped].sort()).toEqual(sidebar);
    // and every key is a known visual-editor navigation key
    const navKeys = JSON.stringify(keys);
    for (const key of mapped) expect(navKeys).toContain(`"${key}"`);
  });

  it('has the four base modules', () => {
    expect(BASE_MODULE_KEYS.sort()).toEqual(['customers', 'invoices', 'payments', 'products']);
  });
});

describe('helpers', () => {
  it('navAllowed: no access info means no restriction; otherwise only listed items', () => {
    expect(navAllowed(null, 'reports')).toBe(true);
    expect(navAllowed(undefined, 'reports')).toBe(true);
    expect(navAllowed(access(['overview', 'quotes']), 'quotes')).toBe(true);
    expect(navAllowed(access(['overview', 'quotes']), 'reports')).toBe(false);
  });

  it('adds required modules and removes dependents', () => {
    expect(withRequirements(['timesheets'])).toEqual(['projects', 'timesheets']);
    expect(withRequirements(['customers', 'quotes'])).toEqual(['quotes']); // base modules are implied
    expect(dependents('projects')).toEqual(['timesheets']);
  });

  it('navKeyForPath matches whole segments, longest first', () => {
    const items = sidebarSections.flatMap((s) => s.items);
    expect(navKeyForPath('/payments', items)).toBe('payments');
    expect(navKeyForPath('/payments/abc', items)).toBe('payments');
    expect(navKeyForPath('/control-center/reconciliation', items)).toBe('reconciliation');
    expect(navKeyForPath('/plans-pricing/simulator', items)).toBe('plans_pricing');
    expect(navKeyForPath('/paymentsx', items)).toBeNull();
    expect(navKeyForPath('/subscription', items)).toBeNull();
  });

  it('trialDaysLeft rounds up and goes to zero or below once ended', () => {
    const now = new Date('2026-10-06T00:00:00Z');
    expect(trialDaysLeft('2026-10-09T00:00:00Z', now)).toBe(3);
    expect(trialDaysLeft('2026-10-06T05:00:00Z', now)).toBe(1);
    expect(trialDaysLeft('2026-10-05T23:00:00Z', now)).toBeLessThanOrEqual(0);
    expect(trialDaysLeft(null, now)).toBeNull();
  });
});
