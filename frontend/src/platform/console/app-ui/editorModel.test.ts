import { describe, expect, it } from 'vitest';
import {
  CUSTOMERS_COLUMN_DEFS,
  CUSTOMERS_HEADER_DEFAULTS,
  INVOICES_COLUMN_DEFS,
  NAV_SECTION_DEFS,
  OVERVIEW_KPI_DEFS,
  PAGE_KEYS,
  resolveList,
} from '../../../appUi/registry';
import {
  PAGE_TITLES,
  groupsFor,
  locate,
  materialize,
  moveItem,
  moveNavSection,
  navItemDefs,
  navSections,
  patchItem,
  patchNavSection,
  setList,
  setNavItems,
  setText,
  setTheme,
  summarize,
  type Content,
} from './editorModel';

describe('groupsFor / locate', () => {
  it('has a title and at least one group for every page', () => {
    for (const page of PAGE_KEYS) {
      expect(PAGE_TITLES[page]).toBeTruthy();
      expect(groupsFor(page).length).toBeGreaterThan(0);
    }
  });

  it('describes each page', () => {
    expect(groupsFor('theme').map((g) => g.id)).toEqual(['theme']);
    expect(groupsFor('overview').map((g) => g.id)).toEqual([
      'overview.header', 'overview.kpis', 'overview.main_widgets', 'overview.side_widgets',
    ]);
    expect(groupsFor('customers').map((g) => g.id)).toEqual([
      'customers.header', 'customers.stats', 'customers.columns', 'customers.empty',
    ]);
    expect(groupsFor('invoices').map((g) => g.id)).toEqual([
      'invoices.header', 'invoices.kpis', 'invoices.columns', 'invoices.empty',
    ]);
    const nav = groupsFor('navigation');
    expect(nav[0].id).toBe('nav.sections');
    expect(nav.slice(1).map((g) => g.id)).toEqual(NAV_SECTION_DEFS.map((s) => `nav.section.${s.key}`));
  });

  it('nav item definitions come from the real sidebar; settings is required', () => {
    expect(navItemDefs('workspace')).toEqual([
      { key: 'overview', label: 'Overview', required: false },
      { key: 'customers', label: 'Customers', required: false },
      { key: 'catalog', label: 'Catalog', required: false },
    ]);
    expect(navItemDefs('system').find((d) => d.key === 'settings')!.required).toBe(true);
    expect(navItemDefs('nope')).toEqual([]);
  });

  it('locates groups and items', () => {
    expect(locate('overview', null)).toBeNull();
    expect(locate('overview', 'overview.header')!.group.id).toBe('overview.header');
    expect(locate('overview', 'overview.kpi.mrr')).toMatchObject({ group: { id: 'overview.kpis' }, itemKey: 'mrr' });
    expect(locate('overview', 'overview.widget.quick_actions')).toMatchObject({ group: { id: 'overview.side_widgets' }, itemKey: 'quick_actions' });
    expect(locate('overview', 'overview.widget.customer_health')).toMatchObject({ group: { id: 'overview.main_widgets' }, itemKey: 'customer_health' });
    expect(locate('overview', 'overview.kpi.nope')).toBeNull();
    expect(locate('customers', 'customers.columns')!.group.id).toBe('customers.columns');
    expect(locate('customers', 'customers.column.status')).toMatchObject({ group: { id: 'customers.columns' }, itemKey: 'status' });
    expect(locate('customers', 'customers.stat.active')).toMatchObject({ group: { id: 'customers.stats' }, itemKey: 'active' });
    expect(locate('customers', 'customers.empty')!.group.kind).toBe('empty');
    expect(locate('invoices', 'invoices.kpi.overdue')).toMatchObject({ group: { id: 'invoices.kpis' }, itemKey: 'overdue' });
    expect(locate('invoices', 'invoices.column.balance')).toMatchObject({ group: { id: 'invoices.columns' }, itemKey: 'balance' });
    expect(locate('navigation', 'nav.item.customers')).toMatchObject({ group: { id: 'nav.section.workspace' }, itemKey: 'customers' });
    expect(locate('navigation', 'nav.item.settings')).toMatchObject({ group: { id: 'nav.section.system' }, itemKey: 'settings' });
    expect(locate('navigation', 'nav.item.nope')).toBeNull();
    expect(locate('navigation', 'nav.section.revenue')!.group.sectionKey).toBe('revenue');
    expect(locate('navigation', 'nav.sections')!.group.kind).toBe('nav-sections');
    expect(locate('theme', 'theme')!.group.kind).toBe('theme');
    // An id from another page does not resolve.
    expect(locate('invoices', 'customers.header')).toBeNull();
  });
});

describe('list edits', () => {
  it('materialize returns a complete cleaned list', () => {
    expect(materialize(CUSTOMERS_COLUMN_DEFS, undefined)).toEqual(CUSTOMERS_COLUMN_DEFS.map((d) => ({ key: d.key })));
  });

  it('patchItem returns the complete list with only real differences', () => {
    const renamed = patchItem(OVERVIEW_KPI_DEFS, undefined, 'mrr', { label: 'Monthly recurring' });
    expect(renamed).toHaveLength(OVERVIEW_KPI_DEFS.length);
    expect(renamed.map((i) => i.key)).toEqual(OVERVIEW_KPI_DEFS.map((d) => d.key));
    expect(renamed.find((i) => i.key === 'mrr')).toEqual({ key: 'mrr', label: 'Monthly recurring' });
    expect(renamed.filter((i) => i.key !== 'mrr').every((i) => Object.keys(i).length === 1)).toBe(true);

    const hidden = patchItem(OVERVIEW_KPI_DEFS, renamed, 'churn_rate', { hidden: true });
    expect(hidden.find((i) => i.key === 'churn_rate')).toEqual({ key: 'churn_rate', hidden: true });
    expect(hidden.find((i) => i.key === 'mrr')).toEqual({ key: 'mrr', label: 'Monthly recurring' });

    // Back to the default label and shown again: no stray fields.
    const reset = patchItem(OVERVIEW_KPI_DEFS, hidden, 'mrr', { label: 'MRR ({currency})' });
    const shown = patchItem(OVERVIEW_KPI_DEFS, reset, 'churn_rate', { hidden: false });
    expect(shown).toEqual(OVERVIEW_KPI_DEFS.map((d) => ({ key: d.key })));
  });

  it('patchItem never stores hidden for required items and drops blank labels', () => {
    const list = patchItem(CUSTOMERS_COLUMN_DEFS, undefined, 'customer', { hidden: true });
    expect(list.find((i) => i.key === 'customer')).toEqual({ key: 'customer' });
    const blank = patchItem(CUSTOMERS_COLUMN_DEFS, undefined, 'status', { label: '' });
    expect(blank.find((i) => i.key === 'status')).toEqual({ key: 'status' });
  });

  it('moveItem swaps neighbours and keeps edits; out-of-range is a no-op', () => {
    const base = patchItem(INVOICES_COLUMN_DEFS, undefined, 'status', { label: 'State' });
    const up = moveItem(INVOICES_COLUMN_DEFS, base, 'status', -1);
    const keys = INVOICES_COLUMN_DEFS.map((d) => d.key);
    const expected = [...keys];
    expected.splice(keys.indexOf('status') - 1, 2, 'status', 'balance');
    expect(up.map((i) => i.key)).toEqual(expected);
    expect(up.find((i) => i.key === 'status')).toEqual({ key: 'status', label: 'State' });
    expect(up).toHaveLength(keys.length);

    expect(moveItem(INVOICES_COLUMN_DEFS, base, 'invoice_number', -1).map((i) => i.key)).toEqual(keys);
    expect(moveItem(INVOICES_COLUMN_DEFS, base, 'actions', 1).map((i) => i.key)).toEqual(keys);
    expect(moveItem(INVOICES_COLUMN_DEFS, base, 'missing', 1).map((i) => i.key)).toEqual(keys);
  });

  it('setList drops the field when the list is back to the defaults', () => {
    const moved = moveItem(OVERVIEW_KPI_DEFS, undefined, 'mrr', -1);
    const withList = setList({ header: { title: 'x' } }, 'kpis', moved, OVERVIEW_KPI_DEFS);
    expect(withList.kpis).toEqual(moved);
    const back = moveItem(OVERVIEW_KPI_DEFS, moved, 'mrr', 1);
    const cleared = setList(withList, 'kpis', back, OVERVIEW_KPI_DEFS);
    expect(cleared).toEqual({ header: { title: 'x' } });
    expect('kpis' in cleared).toBe(false);
  });
});

describe('text and theme edits', () => {
  it('setText stores non-default values and removes default or blank ones', () => {
    const d = CUSTOMERS_HEADER_DEFAULTS.title;
    let c: Content = setText({}, 'header', 'title', 'Clients', d);
    expect(c).toEqual({ header: { title: 'Clients' } });
    c = setText(c, 'header', 'subtitle', 'Sub', CUSTOMERS_HEADER_DEFAULTS.subtitle);
    expect(c).toEqual({ header: { title: 'Clients', subtitle: 'Sub' } });
    c = setText(c, 'header', 'title', d, d);
    expect(c).toEqual({ header: { subtitle: 'Sub' } });
    c = setText(c, 'header', 'subtitle', '   ', CUSTOMERS_HEADER_DEFAULTS.subtitle);
    expect(c).toEqual({});
  });

  it('setText does not mutate its input', () => {
    const before: Content = { header: { title: 'A' } };
    setText(before, 'header', 'title', 'B', 'Default');
    expect(before).toEqual({ header: { title: 'A' } });
  });

  it('setTheme drops default colours (case-insensitively) and nulls', () => {
    let c: Content = setTheme({}, 'brand_600', '#112233');
    expect(c).toEqual({ brand_600: '#112233' });
    c = setTheme(c, 'sidebar_background', '#171b63'); // default is #171B63
    expect(c).toEqual({ brand_600: '#112233' });
    c = setTheme(c, 'brand_600', null);
    expect(c).toEqual({});
  });
});

describe('navigation edits', () => {
  it('setNavItems creates a complete section list and keeps other sections', () => {
    const items = patchItem(navItemDefs('workspace'), undefined, 'customers', { label: 'Clients' });
    const c = setNavItems({}, 'workspace', items);
    const sections = navSections(c);
    expect(sections.map((s) => s.key)).toEqual(NAV_SECTION_DEFS.map((s) => s.key));
    expect(sections.find((s) => s.key === 'workspace')!.items).toEqual(items);
    expect(sections.filter((s) => s.key !== 'workspace').every((s) => !s.items)).toBe(true);
  });

  it('patchNavSection and moveNavSection keep the items of every section', () => {
    const items = patchItem(navItemDefs('revenue'), undefined, 'invoices', { icon: 'Star' } as never);
    let c = setNavItems({}, 'revenue', items);
    c = patchNavSection(c, 'revenue', { label: 'MONEY' });
    expect(navSections(c).find((s) => s.key === 'revenue')).toEqual({ key: 'revenue', label: 'MONEY', items });
    c = patchNavSection(c, 'platforms', { hidden: true });
    expect(navSections(c).find((s) => s.key === 'platforms')).toEqual({ key: 'platforms', hidden: true });
    c = moveNavSection(c, 'revenue', -1);
    const order = navSections(c).map((s) => s.key);
    expect(order.slice(0, 2)).toEqual(['revenue', 'workspace']);
    expect(navSections(c).find((s) => s.key === 'revenue')).toEqual({ key: 'revenue', label: 'MONEY', items });
    expect(navSections(c).find((s) => s.key === 'platforms')!.hidden).toBe(true);
    // Editing items afterwards keeps the reordered sections.
    c = setNavItems(c, 'workspace', patchItem(navItemDefs('workspace'), undefined, 'catalog', { hidden: true }));
    expect(navSections(c).map((s) => s.key)).toEqual(order);
    expect(navSections(c).find((s) => s.key === 'revenue')!.items).toEqual(items);
    // The required System section cannot be hidden.
    c = patchNavSection(c, 'system', { hidden: true });
    expect(resolveList(NAV_SECTION_DEFS, navSections(c)).find((s) => s.key === 'system')!.hidden).toBe(false);
  });
});

describe('summarize', () => {
  it('describes header, rename, hide and reorder changes', () => {
    let after: Content = setText({}, 'header', 'title', 'Clients', CUSTOMERS_HEADER_DEFAULTS.title);
    after = setList(after, 'columns', patchItem(CUSTOMERS_COLUMN_DEFS, undefined, 'status', { label: 'State' }), CUSTOMERS_COLUMN_DEFS);
    after = setList(after, 'columns', patchItem(CUSTOMERS_COLUMN_DEFS, after.columns as never, 'created', { hidden: true }), CUSTOMERS_COLUMN_DEFS);
    after = setList(after, 'columns', moveItem(CUSTOMERS_COLUMN_DEFS, after.columns as never, 'company', -1), CUSTOMERS_COLUMN_DEFS);
    const lines = summarize('customers', {}, after);
    expect(lines).toContain('Page header – Heading: “Customers” → “Clients”');
    expect(lines).toContain('Table columns: “Status” renamed to “State”');
    expect(lines).toContain('Table columns: “Created” hidden');
    expect(lines.some((l) => l.startsWith('Table columns: order changed (Customer # → Company / GSTIN → Customer → State'))).toBe(true);
    expect(summarize('customers', after, after)).toEqual([]);
    expect(summarize('customers', after, {})).toContain('Table columns: “Created” shown');
  });

  it('describes theme changes', () => {
    expect(summarize('theme', {}, { brand_600: '#112233' })).toEqual(['brand 600: #25247a → #112233']);
    expect(summarize('theme', {}, { brand_600: '#25247A' })).toEqual([]);
  });

  it('describes navigation section, item and icon changes', () => {
    let c = setNavItems({}, 'workspace', patchItem(navItemDefs('workspace'), undefined, 'customers', { label: 'Clients', icon: 'Star' } as never));
    c = patchNavSection(c, 'platforms', { hidden: true });
    c = moveNavSection(c, 'revenue', -1);
    const lines = summarize('navigation', {}, c);
    expect(lines).toContain('WORKSPACE items: “Customers” renamed to “Clients”');
    expect(lines).toContain('Customers: icon default → Star');
    expect(lines).toContain('Sidebar sections: “PLATFORMS” hidden');
    expect(lines.some((l) => l.startsWith('Sidebar sections: order changed (REVENUE → WORKSPACE'))).toBe(true);
  });
});
