/**
 * Application UI configuration registry (Super Admin visual editor).
 *
 * Code defines WHAT each page can do; this registry defines which presentational properties of
 * which components may be configured, and their built-in defaults. Published configuration is a
 * document of OVERRIDES only (validated server-side by backend/app/schemas/app_ui.py against the
 * same allow-lists in ./keys.json); `resolve*` merges it over these defaults, so a missing page,
 * component or property always renders exactly as the hard-coded UI did before.
 *
 * Nothing here can carry code: labels are plain text rendered as React text nodes, colours are
 * validated #RRGGBB values applied as CSS custom properties, icons come from an allow-list.
 */
import KEYS from './keys.json';

/** The hand-written Milestone 1 pages. */
export type CorePageKey = 'theme' | 'navigation' | 'overview' | 'customers' | 'invoices';
/** Core pages plus every module page described by a spec (./specs/<key>.json). */
export type PageKey = CorePageKey | (string & {});
export const CORE_PAGE_KEYS = KEYS.pages as CorePageKey[];

// --- module page specs ---------------------------------------------------------------------------
//
// Every module page beyond the core five is described by ./specs/<key>.json (an identical copy of
// backend/app/app_ui/specs/<key>.json, which generates the server-side schema). A spec lists the
// page's text groups and ordered lists with their built-in defaults; usePageSpec() merges the
// published overrides over them and the editor builds its controls from the same file.

export type TextKind = 'label' | 'heading' | 'body';
export const TEXT_LIMITS: Record<TextKind, number> = { label: 60, heading: 120, body: 300 };
export const CAPTION_LIMIT = 120;

export interface SpecTextField {
  name: string;
  label: string;
  kind: TextKind;
  default: string;
  hint?: string;
}
export interface SpecTextGroup {
  id: string;
  label: string;
  fields: SpecTextField[];
}
export interface SpecListItem {
  key: string;
  label: string;
  required?: boolean;
  caption?: string;
}
export interface SpecList {
  id: string;
  label: string;
  /** Defaults to true. A fixed-order list can be relabelled (and hidden) but not reordered. */
  reorder?: boolean;
  /** Defaults to true. */
  hide?: boolean;
  /** Items have an editable secondary line (e.g. a KPI card's caption). */
  captions?: boolean;
  items: SpecListItem[];
}
export interface PageSpec {
  key: string;
  title: string;
  /** Tenant route the preview renders. */
  route: string;
  /** Sidebar entry (orders the page list in the editor). */
  nav_item?: string;
  texts?: SpecTextGroup[];
  lists?: SpecList[];
}

const specModules = import.meta.glob<PageSpec>('./specs/*.json', { eager: true, import: 'default' });
const navOrder = (spec: PageSpec) => {
  const index = spec.nav_item ? KEYS.nav_items.indexOf(spec.nav_item) : -1;
  return index < 0 ? KEYS.nav_items.length : index;
};
/** Module page specs, in sidebar order. */
export const PAGE_SPECS: Record<string, PageSpec> = Object.fromEntries(
  Object.values(specModules)
    .sort((a, b) => navOrder(a) - navOrder(b) || a.key.localeCompare(b.key))
    .map((spec) => [spec.key, spec])
);
export const PAGE_KEYS: PageKey[] = [...CORE_PAGE_KEYS, ...Object.keys(PAGE_SPECS)];

export function isSpecPage(key: string): boolean {
  return Object.prototype.hasOwnProperty.call(PAGE_SPECS, key);
}

/** Override document of a spec page: text groups and lists keyed by their spec id. */
export type SpecConfig = { schema_version?: 1 } & Record<string, Record<string, string> | ItemOverride[] | number | undefined>;

export interface ItemOverride {
  key: string;
  label?: string;
  hidden?: boolean;
  caption?: string;
}
export interface HeaderOverride {
  title?: string;
  subtitle?: string;
  eyebrow?: string;
}
export interface EmptyOverride {
  title?: string;
  description?: string;
}

export interface ThemeConfig {
  schema_version?: 1;
  brand_500?: string;
  brand_600?: string;
  brand_700?: string;
  sidebar_background?: string;
  sidebar_active?: string;
}
export interface NavItemOverride extends ItemOverride {
  icon?: string;
}
export interface NavSectionOverride extends ItemOverride {
  items?: NavItemOverride[];
}
export interface NavigationConfig {
  schema_version?: 1;
  sections?: NavSectionOverride[];
}
export interface OverviewConfig {
  schema_version?: 1;
  header?: HeaderOverride;
  kpis?: ItemOverride[];
  main_widgets?: ItemOverride[];
  side_widgets?: ItemOverride[];
}
export interface CustomersConfig {
  schema_version?: 1;
  header?: HeaderOverride;
  stats?: ItemOverride[];
  columns?: ItemOverride[];
  empty?: EmptyOverride;
}
export interface InvoicesConfig {
  schema_version?: 1;
  header?: HeaderOverride;
  kpis?: ItemOverride[];
  columns?: ItemOverride[];
  empty?: EmptyOverride;
}
export interface PageConfigs {
  theme?: ThemeConfig;
  navigation?: NavigationConfig;
  overview?: OverviewConfig;
  customers?: CustomersConfig;
  invoices?: InvoicesConfig;
  [specPage: string]: object | undefined;
}

export interface ListDef {
  key: string;
  label: string;
  /** Cannot be hidden (enforced server-side too). */
  required?: boolean;
  /** Default secondary line, for lists with captions. */
  caption?: string;
}
export interface ResolvedItem {
  key: string;
  label: string;
  hidden: boolean;
  caption?: string;
}

// --- defaults (the labels the application shipped with) ------------------------------------------

export const NAV_SECTION_DEFS: ListDef[] = [
  { key: 'workspace', label: 'WORKSPACE' },
  { key: 'revenue', label: 'REVENUE' },
  { key: 'subscriptions', label: 'SUBSCRIPTIONS' },
  { key: 'customer_experience', label: 'CUSTOMER EXPERIENCE' },
  { key: 'operations', label: 'OPERATIONS' },
  { key: 'insights', label: 'INSIGHTS' },
  { key: 'platforms', label: 'PLATFORMS' },
  { key: 'control_center', label: 'CONTROL CENTER' },
  { key: 'system', label: 'SYSTEM', required: true },
];
export const NAV_LAYOUT = KEYS.nav_layout as Record<string, string[]>;

export const OVERVIEW_KPI_DEFS: ListDef[] = [
  { key: 'total_invoices', label: 'Total Invoices' },
  { key: 'total_revenue', label: 'Total Revenue' },
  { key: 'payments_received', label: 'Payments Received' },
  { key: 'outstanding', label: 'Outstanding' },
  { key: 'mrr', label: 'MRR ({currency})' },
  { key: 'churn_rate', label: 'Churn Rate' },
];
export const OVERVIEW_MAIN_WIDGET_DEFS: ListDef[] = [
  { key: 'revenue_overview', label: 'Revenue Overview' },
  { key: 'recent_invoices', label: 'Recent Invoices' },
  { key: 'billing_pipeline', label: 'Billing Pipeline' },
  { key: 'customer_health', label: 'Customer Health' },
  { key: 'payment_recovery', label: 'Payment Recovery (Dunning)' },
];
export const OVERVIEW_SIDE_WIDGET_DEFS: ListDef[] = [
  { key: 'payment_status', label: 'Payment Status' },
  { key: 'quick_actions', label: 'Quick Actions' },
  { key: 'billing_promo', label: 'Streamline Your Billing' },
  { key: 'action_center', label: 'Action Center' },
  { key: 'activity_timeline', label: 'Recent Activity Timeline' },
];
export const OVERVIEW_HEADER_DEFAULTS = {
  title: 'Welcome back, {first_name}!',
  subtitle: "Here's what's happening with your billing & revenue operations today.",
};

export const CUSTOMERS_HEADER_DEFAULTS = {
  title: 'Customers',
  eyebrow: 'Workspace',
  subtitle:
    'Every organisation and individual you bill. Open a customer to see contacts, invoices, payments and subscriptions in one place.',
};
export const CUSTOMERS_STAT_DEFS: ListDef[] = [
  { key: 'total', label: 'Total customers' },
  { key: 'active', label: 'Active' },
  { key: 'inactive', label: 'Inactive' },
  { key: 'matching', label: 'Matching filters' },
];
export const CUSTOMERS_COLUMN_DEFS: ListDef[] = [
  { key: 'customer_number', label: 'Customer #' },
  { key: 'customer', label: 'Customer', required: true },
  { key: 'company', label: 'Company / GSTIN' },
  { key: 'status', label: 'Status' },
  { key: 'currency_terms', label: 'Currency / Terms' },
  { key: 'created', label: 'Created' },
];
export const CUSTOMERS_EMPTY_DEFAULTS = {
  title: 'No customers yet',
  description:
    'Customers are the organisations and people you invoice. Add your first customer to start creating quotes, invoices and subscriptions.',
};

export const INVOICES_HEADER_DEFAULTS = {
  title: 'Invoices',
  subtitle: 'Manage billing, track client balances, and collect payments',
};
export const INVOICES_KPI_DEFS: ListDef[] = [
  { key: 'outstanding', label: 'Total Outstanding' },
  { key: 'paid', label: 'Paid Invoices' },
  { key: 'overdue', label: 'Overdue' },
  { key: 'revenue', label: 'Total Revenue' },
];
export const INVOICES_COLUMN_DEFS: ListDef[] = [
  { key: 'invoice_number', label: 'Invoice #', required: true },
  { key: 'customer', label: 'Customer' },
  { key: 'date', label: 'Date' },
  { key: 'due_date', label: 'Due Date' },
  { key: 'total', label: 'Total' },
  { key: 'paid', label: 'Paid' },
  { key: 'balance', label: 'Balance' },
  { key: 'status', label: 'Status' },
  { key: 'actions', label: 'Actions' },
];
export const INVOICES_EMPTY_DEFAULTS = {
  title: 'No invoices found',
  description: 'Create your first invoice to start billing your customers.',
};

/** Theme tokens and their built-in values (frontend/src/index.css, Sidebar). */
export const THEME_DEFAULTS: Required<Omit<ThemeConfig, 'schema_version'>> = {
  brand_500: '#3f51c9',
  brand_600: '#25247a',
  brand_700: '#1f1e6b',
  sidebar_background: '#171B63',
  sidebar_active: '#25247A',
};
export const THEME_CSS_VARS: Record<keyof typeof THEME_DEFAULTS, string> = {
  brand_500: '--brand-500',
  brand_600: '--brand-600',
  brand_700: '--brand-700',
  sidebar_background: '--sidebar-bg',
  sidebar_active: '--sidebar-active',
};

// --- merging ---------------------------------------------------------------------------------------

/** Ordered list: overridden keys first (in their configured order), then any remaining defaults
 *  in their default order - so entries added to the application later always appear. */
export function resolveList(defs: ListDef[], overrides?: ItemOverride[]): ResolvedItem[] {
  const byKey = new Map(defs.map((d) => [d.key, d]));
  const seen = new Set<string>();
  const out: ResolvedItem[] = [];
  for (const o of overrides ?? []) {
    const def = byKey.get(o.key);
    if (!def || seen.has(o.key)) continue;
    seen.add(o.key);
    out.push({
      key: def.key, label: o.label || def.label, hidden: def.required ? false : Boolean(o.hidden),
      ...(def.caption !== undefined ? { caption: o.caption || def.caption } : {}),
    });
  }
  for (const def of defs) {
    if (!seen.has(def.key)) {
      out.push({ key: def.key, label: def.label, hidden: false, ...(def.caption !== undefined ? { caption: def.caption } : {}) });
    }
  }
  return out;
}

export function visible(items: ResolvedItem[]): ResolvedItem[] {
  return items.filter((i) => !i.hidden);
}

export function labelOf(items: ResolvedItem[], key: string, fallback = ''): string {
  return items.find((i) => i.key === key)?.label ?? fallback;
}

/** Replace the supported {tokens} with plain text (no markup is ever interpreted). */
export function fillTokens(text: string, tokens: Record<string, string>): string {
  return text.replace(/\{(\w+)\}/g, (m, name: string) => (name in tokens ? tokens[name] : m));
}
