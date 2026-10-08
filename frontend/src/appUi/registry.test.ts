import { describe, expect, it } from 'vitest';
import KEYS from './keys.json';
import {
  CUSTOMERS_COLUMN_DEFS,
  CUSTOMERS_STAT_DEFS,
  INVOICES_COLUMN_DEFS,
  INVOICES_KPI_DEFS,
  NAV_LAYOUT,
  NAV_SECTION_DEFS,
  OVERVIEW_KPI_DEFS,
  OVERVIEW_MAIN_WIDGET_DEFS,
  OVERVIEW_SIDE_WIDGET_DEFS,
  CORE_PAGE_KEYS,
  PAGE_KEYS,
  fillTokens,
  labelOf,
  resolveList,
  visible,
  type ListDef,
} from './registry';
import { UI_ICONS, UI_ICON_NAMES, uiIcon } from './icons';
import { sidebarSections } from '../components/layout/Sidebar';
import { Star, Users } from 'lucide-react';

const DEFS: ListDef[] = [
  { key: 'a', label: 'Alpha' },
  { key: 'b', label: 'Beta', required: true },
  { key: 'c', label: 'Gamma' },
  { key: 'd', label: 'Delta' },
];

describe('resolveList', () => {
  it('returns defaults in order when there are no overrides', () => {
    expect(resolveList(DEFS)).toEqual([
      { key: 'a', label: 'Alpha', hidden: false },
      { key: 'b', label: 'Beta', hidden: false },
      { key: 'c', label: 'Gamma', hidden: false },
      { key: 'd', label: 'Delta', hidden: false },
    ]);
    expect(resolveList(DEFS, [])).toEqual(resolveList(DEFS));
  });

  it('puts overridden keys first, ignores unknown and duplicate keys, appends remaining defaults', () => {
    const out = resolveList(DEFS, [
      { key: 'c', label: 'Third' },
      { key: 'zzz', label: 'Unknown' },
      { key: 'a', hidden: true },
      { key: 'c', label: 'Duplicate', hidden: true },
    ]);
    expect(out.map((i) => i.key)).toEqual(['c', 'a', 'b', 'd']);
    expect(out[0]).toEqual({ key: 'c', label: 'Third', hidden: false });
    expect(out[1]).toEqual({ key: 'a', label: 'Alpha', hidden: true });
    expect(out.find((i) => i.label === 'Unknown')).toBeUndefined();
    expect(out.find((i) => i.label === 'Duplicate')).toBeUndefined();
  });

  it('never hides required items', () => {
    const out = resolveList(DEFS, [{ key: 'b', hidden: true }]);
    expect(out.find((i) => i.key === 'b')!.hidden).toBe(false);
    expect(visible(out).map((i) => i.key)).toContain('b');
  });

  it('falls back to the default label for missing or empty labels', () => {
    const out = resolveList(DEFS, [{ key: 'a', label: '' }, { key: 'c' }]);
    expect(labelOf(out, 'a')).toBe('Alpha');
    expect(labelOf(out, 'c')).toBe('Gamma');
    expect(labelOf(out, 'missing', 'fallback')).toBe('fallback');
  });

  it('visible() drops hidden items', () => {
    const out = resolveList(DEFS, [{ key: 'a', hidden: true }, { key: 'd', hidden: true }]);
    expect(visible(out).map((i) => i.key)).toEqual(['b', 'c']);
  });
});

describe('fillTokens', () => {
  it('replaces known tokens and keeps unknown ones verbatim', () => {
    expect(fillTokens('Hi {first_name}, {first_name}!', { first_name: 'Asha' })).toBe('Hi Asha, Asha!');
    expect(fillTokens('MRR ({currency}) {nope}', { currency: 'INR' })).toBe('MRR (INR) {nope}');
  });

  it('does not interpret markup in values', () => {
    expect(fillTokens('{x}', { x: '<b>bold</b>' })).toBe('<b>bold</b>');
    expect(fillTokens('No tokens', {})).toBe('No tokens');
  });
});

describe('keys.json matches the registry and the real UI', () => {
  it('pages are CORE_PAGE_KEYS', () => {
    expect(KEYS.pages).toEqual(CORE_PAGE_KEYS);
    expect(CORE_PAGE_KEYS).toEqual(['theme', 'navigation', 'overview', 'customers', 'invoices']);
    expect(PAGE_KEYS).toEqual(expect.arrayContaining(CORE_PAGE_KEYS));
  });

  it('list allow-lists match the registry defaults', () => {
    const keys = (defs: ListDef[]) => defs.map((d) => d.key);
    expect(KEYS.nav_sections).toEqual(keys(NAV_SECTION_DEFS));
    expect(KEYS.overview_kpis).toEqual(keys(OVERVIEW_KPI_DEFS));
    expect(KEYS.overview_widgets_main).toEqual(keys(OVERVIEW_MAIN_WIDGET_DEFS));
    expect(KEYS.overview_widgets_side).toEqual(keys(OVERVIEW_SIDE_WIDGET_DEFS));
    expect(KEYS.customers_stats).toEqual(keys(CUSTOMERS_STAT_DEFS));
    expect(KEYS.customers_columns).toEqual(keys(CUSTOMERS_COLUMN_DEFS));
    expect(KEYS.invoices_kpis).toEqual(keys(INVOICES_KPI_DEFS));
    expect(KEYS.invoices_columns).toEqual(keys(INVOICES_COLUMN_DEFS));
  });

  it('every sidebar section and item in keys.json exists in the real Sidebar with matching sections', () => {
    expect(sidebarSections.map((s) => s.key)).toEqual(KEYS.nav_sections);
    for (const section of sidebarSections) {
      expect(section.items.map((i) => i.key)).toEqual(NAV_LAYOUT[section.key]);
      expect(NAV_SECTION_DEFS.find((d) => d.key === section.key)!.label).toBe(section.title);
    }
    const allItems = sidebarSections.flatMap((s) => s.items.map((i) => i.key));
    expect(allItems).toEqual(KEYS.nav_items);
    expect(new Set(allItems).size).toBe(allItems.length);
    expect(Object.values(NAV_LAYOUT).flat().sort()).toEqual([...KEYS.nav_items].sort());
  });
});

describe('icons', () => {
  it('allow-list names all map to real icons', () => {
    expect(Object.keys(UI_ICONS).sort()).toEqual([...UI_ICON_NAMES].sort());
  });

  it('uiIcon falls back for unknown names and prototype keys', () => {
    expect(uiIcon('Star', Users)).toBe(Star);
    expect(uiIcon(undefined, Users)).toBe(Users);
    expect(uiIcon('NotAnIcon', Users)).toBe(Users);
    expect(uiIcon('constructor', Users)).toBe(Users);
    expect(uiIcon('__proto__', Users)).toBe(Users);
  });
});
