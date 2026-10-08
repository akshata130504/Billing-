/**
 * Visual-editor model: the component tree per page, which group a selected preview element belongs
 * to, and pure edit operations on a page's override document.
 *
 * Lists are always stored complete and in display order ({key, label?, hidden?} for every entry),
 * with labels equal to the default and hidden=false omitted, so the server's allow-list validation
 * stays simple and the document stays small.
 */
import {
  CUSTOMERS_COLUMN_DEFS,
  CUSTOMERS_EMPTY_DEFAULTS,
  CUSTOMERS_HEADER_DEFAULTS,
  CUSTOMERS_STAT_DEFS,
  INVOICES_COLUMN_DEFS,
  INVOICES_EMPTY_DEFAULTS,
  INVOICES_HEADER_DEFAULTS,
  INVOICES_KPI_DEFS,
  NAV_LAYOUT,
  NAV_SECTION_DEFS,
  OVERVIEW_HEADER_DEFAULTS,
  OVERVIEW_KPI_DEFS,
  OVERVIEW_MAIN_WIDGET_DEFS,
  OVERVIEW_SIDE_WIDGET_DEFS,
  PAGE_SPECS,
  TEXT_LIMITS,
  THEME_DEFAULTS,
  resolveList,
  type ItemOverride,
  type ListDef,
  type NavItemOverride,
  type NavSectionOverride,
  type NavigationConfig,
  type PageKey,
  type ThemeConfig,
} from '../../../appUi/registry';
import { sidebarSections } from '../../../components/layout/Sidebar';

export type Content = Record<string, unknown> & { schema_version?: 1 };

export type GroupKind = 'header' | 'list' | 'empty' | 'theme' | 'nav-sections' | 'nav-section';

export interface Group {
  id: string;
  label: string;
  kind: GroupKind;
  /** Document field the group edits (header / empty / list name). */
  field?: string;
  defs?: ListDef[];
  /** Header / empty-state fields and their defaults. */
  textFields?: { name: string; label: string; default: string; multiline?: boolean; hint?: string; maxLength?: number }[];
  /** List capabilities (module pages); both default to true. */
  reorder?: boolean;
  hide?: boolean;
  /** List items have an editable caption. */
  captions?: boolean;
  /** Prefix of the preview element ids for items of this list (e.g. "overview.kpi."). */
  itemPrefix?: string;
  sectionKey?: string;
}

export const PAGE_TITLES: Record<PageKey, string> = {
  theme: 'Theme & colours',
  navigation: 'Navigation (sidebar)',
  overview: 'Overview (dashboard)',
  customers: 'Customers',
  invoices: 'Invoices',
  ...Object.fromEntries(Object.values(PAGE_SPECS).map((spec) => [spec.key, spec.title])),
};

/** Editor groups generated from a module page's spec (same ids the page passes to ui.edit()). */
function specGroups(page: string): Group[] {
  const spec = PAGE_SPECS[page];
  if (!spec) return [];
  return [
    ...(spec.texts ?? []).map((g) => ({
      id: `${page}.${g.id}`, label: g.label, kind: 'header' as const, field: g.id,
      textFields: g.fields.map((f) => ({
        name: f.name, label: f.label, default: f.default, hint: f.hint,
        multiline: f.kind === 'body', maxLength: TEXT_LIMITS[f.kind],
      })),
    })),
    ...(spec.lists ?? []).map((l) => ({
      id: `${page}.${l.id}`, label: l.label, kind: 'list' as const, field: l.id, itemPrefix: `${page}.${l.id}.`,
      reorder: l.reorder !== false, hide: l.hide !== false, captions: Boolean(l.captions),
      defs: l.items.map((i) => ({ key: i.key, label: i.label, required: i.required || l.hide === false, caption: i.caption })),
    })),
  ];
}

/** Navigation item definitions from the real sidebar (labels = what users see today). */
export function navItemDefs(sectionKey: string): ListDef[] {
  const section = sidebarSections.find((s) => s.key === sectionKey);
  return (NAV_LAYOUT[sectionKey] ?? []).map((key) => ({
    key,
    label: section?.items.find((i) => i.key === key)?.title ?? key,
    required: key === 'settings',
  }));
}

export function groupsFor(page: PageKey): Group[] {
  switch (page) {
    case 'theme':
      return [{ id: 'theme', label: 'Colours', kind: 'theme' }];
    case 'navigation':
      return [
        { id: 'nav.sections', label: 'Sections (order & visibility)', kind: 'nav-sections', defs: NAV_SECTION_DEFS },
        ...NAV_SECTION_DEFS.map((s) => ({
          id: `nav.section.${s.key}`, label: s.label, kind: 'nav-section' as const, sectionKey: s.key,
          defs: navItemDefs(s.key), itemPrefix: 'nav.item.',
        })),
      ];
    case 'overview':
      return [
        { id: 'overview.header', label: 'Page header', kind: 'header', field: 'header', textFields: [
          { name: 'title', label: 'Heading', default: OVERVIEW_HEADER_DEFAULTS.title, hint: '{first_name} is replaced by the user’s first name' },
          { name: 'subtitle', label: 'Subtitle', default: OVERVIEW_HEADER_DEFAULTS.subtitle, multiline: true },
        ] },
        { id: 'overview.kpis', label: 'KPI cards', kind: 'list', field: 'kpis', defs: OVERVIEW_KPI_DEFS, itemPrefix: 'overview.kpi.' },
        { id: 'overview.main_widgets', label: 'Main column widgets', kind: 'list', field: 'main_widgets', defs: OVERVIEW_MAIN_WIDGET_DEFS, itemPrefix: 'overview.widget.' },
        { id: 'overview.side_widgets', label: 'Side column widgets', kind: 'list', field: 'side_widgets', defs: OVERVIEW_SIDE_WIDGET_DEFS, itemPrefix: 'overview.widget.' },
      ];
    case 'customers':
      return [
        { id: 'customers.header', label: 'Page header', kind: 'header', field: 'header', textFields: [
          { name: 'eyebrow', label: 'Eyebrow', default: CUSTOMERS_HEADER_DEFAULTS.eyebrow },
          { name: 'title', label: 'Heading', default: CUSTOMERS_HEADER_DEFAULTS.title },
          { name: 'subtitle', label: 'Subtitle', default: CUSTOMERS_HEADER_DEFAULTS.subtitle, multiline: true },
        ] },
        { id: 'customers.stats', label: 'Summary cards', kind: 'list', field: 'stats', defs: CUSTOMERS_STAT_DEFS, itemPrefix: 'customers.stat.' },
        { id: 'customers.columns', label: 'Table columns', kind: 'list', field: 'columns', defs: CUSTOMERS_COLUMN_DEFS, itemPrefix: 'customers.column.' },
        { id: 'customers.empty', label: 'Empty state', kind: 'empty', field: 'empty', textFields: [
          { name: 'title', label: 'Title', default: CUSTOMERS_EMPTY_DEFAULTS.title },
          { name: 'description', label: 'Description', default: CUSTOMERS_EMPTY_DEFAULTS.description, multiline: true },
        ] },
      ];
    case 'invoices':
      return [
        { id: 'invoices.header', label: 'Page header', kind: 'header', field: 'header', textFields: [
          { name: 'title', label: 'Heading', default: INVOICES_HEADER_DEFAULTS.title },
          { name: 'subtitle', label: 'Subtitle', default: INVOICES_HEADER_DEFAULTS.subtitle, multiline: true },
        ] },
        { id: 'invoices.kpis', label: 'KPI cards', kind: 'list', field: 'kpis', defs: INVOICES_KPI_DEFS, itemPrefix: 'invoices.kpi.' },
        { id: 'invoices.columns', label: 'Table columns', kind: 'list', field: 'columns', defs: INVOICES_COLUMN_DEFS, itemPrefix: 'invoices.column.' },
        { id: 'invoices.empty', label: 'Empty state', kind: 'empty', field: 'empty', textFields: [
          { name: 'title', label: 'Title', default: INVOICES_EMPTY_DEFAULTS.title },
          { name: 'description', label: 'Description', default: INVOICES_EMPTY_DEFAULTS.description, multiline: true },
        ] },
      ];
    default:
      return specGroups(page);
  }
}

/** The group (and item key) a preview element id belongs to. */
export function locate(page: PageKey, id: string | null): { group: Group; itemKey?: string } | null {
  if (!id) return null;
  const groups = groupsFor(page);
  const direct = groups.find((g) => g.id === id);
  if (direct) return { group: direct };
  if (page === 'navigation' && id.startsWith('nav.item.')) {
    const key = id.slice('nav.item.'.length);
    const group = groups.find((g) => g.kind === 'nav-section' && g.defs?.some((d) => d.key === key));
    return group ? { group, itemKey: key } : null;
  }
  for (const g of groups) {
    if (g.itemPrefix && id.startsWith(g.itemPrefix)) {
      const key = id.slice(g.itemPrefix.length);
      if (g.defs?.some((d) => d.key === key)) return { group: g, itemKey: key };
    }
  }
  if (page === 'customers' && id === 'customers.columns') return { group: groups.find((g) => g.id === 'customers.columns')! };
  return null;
}

// --- list helpers ----------------------------------------------------------------------------------

/** Complete, ordered, cleaned override list. */
export function materialize(defs: ListDef[], overrides: ItemOverride[] | undefined): ItemOverride[] {
  return resolveList(defs, overrides).map((item) => clean(defs, item));
}

function clean<T extends ItemOverride>(defs: ListDef[], item: T): T {
  const def = defs.find((d) => d.key === item.key);
  const out = { ...item };
  if (!out.label || out.label === def?.label) delete out.label;
  if (!out.hidden || def?.required) delete out.hidden;
  if (!out.caption || out.caption === def?.caption) delete out.caption;
  return out;
}

export function patchItem<T extends ItemOverride>(defs: ListDef[], list: T[] | undefined, key: string, patch: Partial<T>): T[] {
  const extras = new Map((list ?? []).map((item) => [item.key, item]));
  return resolveList(defs, list).map((resolved) => {
    const merged = {
      ...(extras.get(resolved.key) ?? {}),
      key: resolved.key,
      label: resolved.label,
      hidden: resolved.hidden,
      ...(resolved.caption !== undefined ? { caption: resolved.caption } : {}),
      ...(resolved.key === key ? patch : {}),
    } as T;
    return clean(defs, merged);
  });
}

export function moveItem<T extends ItemOverride>(defs: ListDef[], list: T[] | undefined, key: string, delta: -1 | 1): T[] {
  const order = resolveList(defs, list).map((r) => r.key);
  const index = order.indexOf(key);
  const target = index + delta;
  if (index < 0 || target < 0 || target >= order.length) return patchItem(defs, list, key, {});
  [order[index], order[target]] = [order[target], order[index]];
  const current = patchItem(defs, list, key, {});
  return order.map((k) => current.find((c) => c.key === k)!);
}

// --- page-level edits ------------------------------------------------------------------------------

export function setText(content: Content, field: string, name: string, value: string, defaultValue: string): Content {
  const current = { ...((content[field] as Record<string, string>) ?? {}) };
  if (value.trim() === '' || value === defaultValue) delete current[name];
  else current[name] = value;
  const next = { ...content };
  if (Object.keys(current).length) next[field] = current;
  else delete next[field];
  return next;
}

/** Store a complete list, or drop the field when it is exactly the default (order, labels, visibility). */
export function setList(content: Content, field: string, list: ItemOverride[], defs: ListDef[]): Content {
  const next = { ...content };
  const isDefault =
    list.length === defs.length && list.every((item, i) => item.key === defs[i].key && Object.keys(item).length === 1);
  if (isDefault) delete next[field];
  else next[field] = list;
  return next;
}

export function setTheme(content: Content, field: keyof typeof THEME_DEFAULTS, value: string | null): Content {
  const next: ThemeConfig & Content = { ...content };
  if (!value || value.toLowerCase() === THEME_DEFAULTS[field].toLowerCase()) delete next[field];
  else next[field] = value;
  return next;
}

export function navSections(content: Content): NavSectionOverride[] {
  return ((content as NavigationConfig).sections ?? []) as NavSectionOverride[];
}

export function setNavSections(content: Content, sections: NavSectionOverride[]): Content {
  const next = { ...content };
  next.sections = sections;
  return next;
}

/** Patch one section (label / hidden) keeping its items. */
export function patchNavSection(content: Content, key: string, patch: Partial<NavSectionOverride>): Content {
  const sections = navSections(content);
  const list = patchItem(NAV_SECTION_DEFS, sections, key, patch).map((s) => ({
    ...s, ...(sections.find((x) => x.key === s.key)?.items ? { items: sections.find((x) => x.key === s.key)!.items } : {}),
  }));
  return setNavSections(content, list);
}

export function moveNavSection(content: Content, key: string, delta: -1 | 1): Content {
  const sections = navSections(content);
  const list = moveItem(NAV_SECTION_DEFS, sections, key, delta).map((s) => ({
    ...s, ...(sections.find((x) => x.key === s.key)?.items ? { items: sections.find((x) => x.key === s.key)!.items } : {}),
  }));
  return setNavSections(content, list);
}

export function setNavItems(content: Content, sectionKey: string, items: NavItemOverride[]): Content {
  const sections = navSections(content);
  const base = sections.find((s) => s.key === sectionKey)
    ? sections
    : materialize(NAV_SECTION_DEFS, sections).map((s) => ({ ...s, ...(sections.find((x) => x.key === s.key) ?? {}) }));
  return setNavSections(content, base.map((s) => (s.key === sectionKey ? { ...s, items } : s)));
}

// --- change summary -----------------------------------------------------------------------------------

/** Human-readable list of differences between two documents of one page. */
export function summarize(page: PageKey, before: Content, after: Content): string[] {
  const out: string[] = [];
  const groups = groupsFor(page);
  if (page === 'theme') {
    for (const key of Object.keys(THEME_DEFAULTS) as (keyof typeof THEME_DEFAULTS)[]) {
      const a = (before as ThemeConfig)[key] ?? THEME_DEFAULTS[key];
      const b = (after as ThemeConfig)[key] ?? THEME_DEFAULTS[key];
      if (a.toLowerCase() !== b.toLowerCase()) out.push(`${key.replace(/_/g, ' ')}: ${a} → ${b}`);
    }
    return out;
  }
  if (page === 'navigation') {
    const sb = resolveList(NAV_SECTION_DEFS, navSections(before));
    const sa = resolveList(NAV_SECTION_DEFS, navSections(after));
    diffList('Sidebar sections', sb, sa, out);
    for (const s of NAV_SECTION_DEFS) {
      const defs = navItemDefs(s.key);
      const ib = navSections(before).find((x) => x.key === s.key)?.items;
      const ia = navSections(after).find((x) => x.key === s.key)?.items;
      diffList(`${s.label} items`, resolveList(defs, ib), resolveList(defs, ia), out);
      for (const d of defs) {
        const a = ib?.find((i) => i.key === d.key)?.icon;
        const b = ia?.find((i) => i.key === d.key)?.icon;
        if (a !== b) out.push(`${d.label}: icon ${a ?? 'default'} → ${b ?? 'default'}`);
      }
    }
    return out;
  }
  for (const g of groups) {
    if ((g.kind === 'header' || g.kind === 'empty') && g.field && g.textFields) {
      for (const f of g.textFields) {
        const a = ((before[g.field] as Record<string, string>) ?? {})[f.name] ?? f.default;
        const b = ((after[g.field] as Record<string, string>) ?? {})[f.name] ?? f.default;
        if (a !== b) out.push(`${g.label} – ${f.label}: “${a}” → “${b}”`);
      }
    } else if (g.kind === 'list' && g.field && g.defs) {
      diffList(g.label, resolveList(g.defs, before[g.field] as ItemOverride[]), resolveList(g.defs, after[g.field] as ItemOverride[]), out);
    }
  }
  return out;
}

function diffList(label: string, before: ReturnType<typeof resolveList>, after: ReturnType<typeof resolveList>, out: string[]) {
  const orderB = before.map((i) => i.key).join(',');
  const orderA = after.map((i) => i.key).join(',');
  if (orderB !== orderA) out.push(`${label}: order changed (${after.map((i) => i.label).join(' → ')})`);
  for (const a of after) {
    const b = before.find((x) => x.key === a.key);
    if (!b) continue;
    if (b.label !== a.label) out.push(`${label}: “${b.label}” renamed to “${a.label}”`);
    if (b.hidden !== a.hidden) out.push(`${label}: “${a.label}” ${a.hidden ? 'hidden' : 'shown'}`);
    if (b.caption !== a.caption) out.push(`${label}: “${a.label}” caption “${b.caption ?? ''}” → “${a.caption ?? ''}”`);
  }
}
