import { useState, useEffect, useMemo, useRef } from 'react';
import type { LucideIcon } from 'lucide-react';
import { uiIcon } from '../../appUi/icons';
import { NAV_SECTION_DEFS, resolveList, visible, type NavigationConfig } from '../../appUi/registry';
import { usePageUi, useUiEditable } from '../../appUi/UiConfigContext';
import { NavLink, useLocation } from 'react-router-dom';
import { cn } from '../../utils/cn';
import { RoomanLogo } from '../common/RoomanLogo';
import {
  LayoutDashboard,
  Users,
  Package,
  FileText,
  Calculator,
  Receipt,
  ReceiptText,
  CreditCard,
  ShieldCheck,
  Layers,
  Repeat,
  Clock,
  Gauge,
  Percent,
  AlertTriangle,
  UserCheck,
  Globe,
  ExternalLink,
  Coins,
  Briefcase,
  Timer,
  LineChart,
  BarChart3,
  Sparkles,
  Activity,
  Smartphone,
  Monitor,
  Inbox,
  FileCheck,
  Calendar,
  ArrowLeftRight,
  History,
  UploadCloud,
  Zap,
  Palette,
  Boxes,
  Settings,
  ChevronsLeft,
  ChevronsRight,
  ChevronDown,
  ChevronRight,
  Building2,
  X,
} from 'lucide-react';

export interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  /** Desktop-only icon rail mode */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

interface SidebarItem {
  /** Stable key for UI configuration (appUi/keys.json). */
  key: string;
  title: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
}

interface SidebarSection {
  /** Stable key for UI configuration (appUi/keys.json). */
  key: string;
  title: string;
  items: SidebarItem[];
}

export const sidebarSections: SidebarSection[] = [
  {
    key: 'workspace',
    title: 'WORKSPACE',
    items: [
      { key: 'overview', title: 'Overview', path: '/dashboard', icon: LayoutDashboard },
      { key: 'customers', title: 'Customers', path: '/customers', icon: Users },
      { key: 'catalog', title: 'Catalog', path: '/catalog', icon: Package },
    ],
  },
  {
    key: 'revenue',
    title: 'REVENUE',
    items: [
      { key: 'quotes', title: 'Quotes', path: '/quotes', icon: FileText },
      { key: 'cpq', title: 'CPQ', path: '/cpq', icon: Calculator },
      { key: 'invoices', title: 'Invoices', path: '/invoices', icon: Receipt },
      { key: 'credit_notes', title: 'Credit Notes', path: '/credit-notes', icon: ReceiptText },
      { key: 'payments', title: 'Payments', path: '/payments', icon: CreditCard },
      { key: 'collections', title: 'Collections', path: '/collections', icon: ShieldCheck },
    ],
  },
  {
    key: 'subscriptions',
    title: 'SUBSCRIPTIONS',
    items: [
      { key: 'plans_pricing', title: 'Plans & Pricing', path: '/plans-pricing', icon: Layers },
      { key: 'subscriptions', title: 'Subscriptions', path: '/subscriptions', icon: Repeat },
      { key: 'trials', title: 'Trials', path: '/trials', icon: Clock },
      { key: 'usage', title: 'Usage / Metering', path: '/usage', icon: Gauge },
      { key: 'proration', title: 'Proration', path: '/proration', icon: Percent },
      { key: 'dunning', title: 'Dunning', path: '/dunning', icon: AlertTriangle },
    ],
  },
  {
    key: 'customer_experience',
    title: 'CUSTOMER EXPERIENCE',
    items: [
      { key: 'customer_lifecycle', title: 'Customer Lifecycle', path: '/customer-lifecycle', icon: UserCheck },
      { key: 'customer_portal', title: 'Customer Portal', path: '/customer-portal', icon: Globe },
      { key: 'hosted_payment_pages', title: 'Hosted Payment Pages', path: '/hosted-payment-pages', icon: ExternalLink },
    ],
  },
  {
    key: 'operations',
    title: 'OPERATIONS',
    items: [
      { key: 'expenses', title: 'Expenses', path: '/expenses', icon: Coins },
      { key: 'projects', title: 'Projects', path: '/projects', icon: Briefcase },
      { key: 'timesheets', title: 'Timesheets', path: '/timesheets', icon: Timer },
    ],
  },
  {
    key: 'insights',
    title: 'INSIGHTS',
    items: [
      { key: 'revenue_intelligence', title: 'Revenue Intelligence', path: '/revenue-intelligence', icon: LineChart },
      { key: 'reports', title: 'Reports & Analytics', path: '/reports', icon: BarChart3 },
      { key: 'ai_billing', title: 'AI in Billing', path: '/ai-billing', icon: Sparkles },
      { key: 'activity', title: 'Activity', path: '/activity', icon: Activity },
    ],
  },
  {
    key: 'platforms',
    title: 'PLATFORMS',
    items: [
      { key: 'mobile', title: 'Mobile', path: '/platforms/mobile', icon: Smartphone },
      { key: 'desktop', title: 'Desktop', path: '/platforms/desktop', icon: Monitor },
    ],
  },
  {
    key: 'control_center',
    title: 'CONTROL CENTER',
    items: [
      { key: 'action_center', title: 'Action Center', path: '/control-center/action-center', icon: Inbox },
      { key: 'approvals', title: 'Approval Center', path: '/control-center/approvals', icon: FileCheck },
      { key: 'billing_calendar', title: 'Billing Calendar', path: '/control-center/calendar', icon: Calendar },
      { key: 'reconciliation', title: 'Reconciliation', path: '/control-center/reconciliation', icon: ArrowLeftRight },
      { key: 'audit_log', title: 'Audit Log', path: '/control-center/audit-log', icon: History },
      { key: 'data_migration', title: 'Data Migration', path: '/control-center/migration', icon: UploadCloud },
    ],
  },
  {
    key: 'system',
    title: 'SYSTEM',
    items: [
      { key: 'automation', title: 'Automation', path: '/automation', icon: Zap },
      { key: 'customization', title: 'Customization', path: '/customization', icon: Palette },
      { key: 'integrations', title: 'Integrations', path: '/integrations', icon: Boxes },
      { key: 'settings', title: 'Settings', path: '/settings', icon: Settings },
    ],
  },
];

const STORAGE_KEY = 'rooman_sidebar_expanded';

interface SectionVisualConfig {
  icon: React.ComponentType<{ className?: string }>;
  headerBg: string;
  iconColor: string;
  labelColor: string;
}

const DEFAULT_SECTION_VISUAL: SectionVisualConfig = {
  icon: Layers,
  headerBg: 'bg-white/5 hover:bg-white/10 border border-white/5',
  iconColor: 'text-slate-300',
  labelColor: 'text-slate-200',
};

const SECTION_VISUALS: Record<string, SectionVisualConfig> = {
  WORKSPACE: {
    icon: Building2,
    headerBg: 'bg-white/5 hover:bg-white/10 border border-white/5',
    iconColor: 'text-[#8EA5FF]',
    labelColor: 'text-slate-200',
  },
  REVENUE: {
    icon: Receipt,
    headerBg: 'bg-white/5 hover:bg-white/10 border border-white/5',
    iconColor: 'text-[#48D597]',
    labelColor: 'text-slate-200',
  },
  SUBSCRIPTIONS: {
    icon: Repeat,
    headerBg: 'bg-white/5 hover:bg-white/10 border border-white/5',
    iconColor: 'text-[#FFB86C]',
    labelColor: 'text-slate-200',
  },
  'CUSTOMER EXPERIENCE': {
    icon: UserCheck,
    headerBg: 'bg-white/5 hover:bg-white/10 border border-white/5',
    iconColor: 'text-[#FF7BB0]',
    labelColor: 'text-slate-200',
  },
  OPERATIONS: {
    icon: Briefcase,
    headerBg: 'bg-white/5 hover:bg-white/10 border border-white/5',
    iconColor: 'text-[#70CFF8]',
    labelColor: 'text-slate-200',
  },
  INSIGHTS: {
    icon: Sparkles,
    headerBg: 'bg-white/5 hover:bg-white/10 border border-white/5',
    iconColor: 'text-[#C4B5FD]',
    labelColor: 'text-slate-200',
  },
  PLATFORMS: {
    icon: Monitor,
    headerBg: 'bg-white/5 hover:bg-white/10 border border-white/5',
    iconColor: 'text-[#A5B4FC]',
    labelColor: 'text-slate-200',
  },
  'CONTROL CENTER': {
    icon: ShieldCheck,
    headerBg: 'bg-white/5 hover:bg-white/10 border border-white/5',
    iconColor: 'text-[#818CF8]',
    labelColor: 'text-slate-200',
  },
  SYSTEM: {
    icon: Settings,
    headerBg: 'bg-white/5 hover:bg-white/10 border border-white/5',
    iconColor: 'text-slate-400',
    labelColor: 'text-slate-200',
  },
};

/** The navigation as configured in the visual editor, merged over the built-in definition. */
function resolveNavigation(config: NavigationConfig): Array<SidebarSection & { label: string }> {
  const sectionOverrides = config.sections ?? [];
  return visible(resolveList(NAV_SECTION_DEFS, sectionOverrides))
    .map((resolvedSection) => {
      const base = sidebarSections.find((s) => s.key === resolvedSection.key);
      if (!base) return null;
      const itemOverrides = sectionOverrides.find((s) => s.key === base.key)?.items ?? [];
      const itemDefs = base.items.map((i) => ({ key: i.key, label: i.title, required: i.key === 'settings' }));
      const items: SidebarItem[] = visible(resolveList(itemDefs, itemOverrides)).map((resolvedItem) => {
        const item = base.items.find((i) => i.key === resolvedItem.key)!;
        const icon = itemOverrides.find((o) => o.key === item.key)?.icon;
        return { ...item, title: resolvedItem.label, icon: uiIcon(icon, item.icon as LucideIcon) as SidebarItem['icon'] };
      });
      const section: SidebarSection & { label: string } = { ...base, label: resolvedSection.label, items };
      return section;
    })
    .filter((s): s is SidebarSection & { label: string } => s !== null && s.items.length > 0);
}

export function Sidebar({
  isOpen,
  onClose,
  collapsed = false,
  onToggleCollapse,
}: SidebarProps) {
  const location = useLocation();
  const navigationConfig = usePageUi('navigation');
  const sections = useMemo(() => resolveNavigation(navigationConfig), [navigationConfig]);
  const editable = useUiEditable();

  // Initialize expanded sections from sessionStorage (defaulting to WORKSPACE)
  const [expandedSections, setExpandedSections] = useState<string[]>(() => {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // Fallback
    }
    return ['WORKSPACE'];
  });

  // Map of path to section title for fast lookup
  const pathToSectionMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const section of sidebarSections) {
      for (const item of section.items) {
        map.set(item.path, section.title);
      }
    }
    return map;
  }, []);

  // Close the mobile drawer on Escape (desktop rail has no open/close state to escape from)
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const prevPathRef = useRef<string | null>(null);

  // Automatically expand the section containing the active route on route navigation
  useEffect(() => {
    if (prevPathRef.current === location.pathname) return;
    prevPathRef.current = location.pathname;

    // Check exact match or prefix match
    let matchedSection = pathToSectionMap.get(location.pathname);
    if (!matchedSection) {
      for (const section of sidebarSections) {
        if (
          section.items.some(
            (item) =>
              location.pathname === item.path ||
              (item.path !== '/dashboard' && location.pathname.startsWith(item.path))
          )
        ) {
          matchedSection = section.title;
          break;
        }
      }
    }

    if (matchedSection) {
      setExpandedSections((prev) => {
        if (prev.includes(matchedSection!)) return prev;
        const next = [...prev, matchedSection!];
        try {
          sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {
          // ignore
        }
        return next;
      });
    }
  }, [location.pathname, pathToSectionMap]);

  const toggleSection = (sectionTitle: string) => {
    setExpandedSections((prev) => {
      const next = prev.includes(sectionTitle)
        ? prev.filter((t) => t !== sectionTitle)
        : [...prev, sectionTitle];
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  };

  const navItemClass = (isActive: boolean) =>
    cn(
      'group flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 select-none',
      collapsed && 'lg:justify-center lg:px-2',
      isActive
        ? 'bg-[var(--sidebar-active,#25247A)] text-white font-semibold shadow-xs border border-[#3F51C9]/40'
        : 'text-slate-300 hover:text-white hover:bg-white/5'
    );

  const CollapseIcon = collapsed ? ChevronsRight : ChevronsLeft;

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-xs lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar Aside */}
      <aside
        className={cn(
          'fixed top-0 bottom-0 left-0 z-50 w-60 bg-[var(--sidebar-bg,#171B63)] text-white border-r border-[#25247A] flex flex-col justify-between transition-[transform,width] duration-200 ease-in-out lg:translate-x-0 lg:static lg:z-auto',
          collapsed && 'lg:w-[72px]',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Brand Header */}
        <div
          className={cn(
            'h-16 px-3.5 sm:px-4 flex items-center justify-between border-b border-white/10 shrink-0',
            collapsed && 'lg:flex-col lg:justify-center lg:gap-1 lg:px-2 lg:h-auto lg:py-2'
          )}
        >
          <NavLink to="/dashboard" className="flex items-center group py-1 min-w-0">
            <span className={cn('bg-white/95 px-2 py-1 rounded-lg shadow-2xs', collapsed && 'lg:hidden')}>
              <RoomanLogo variant="brand" size="md" showBillingBadge={true} />
            </span>
            <span className={cn('hidden bg-white/95 p-1 rounded-lg shadow-2xs', collapsed && 'lg:inline-flex')}>
              <RoomanLogo variant="shield" size="md" />
            </span>
          </NavLink>

          {onToggleCollapse && (
            <button
              type="button"
              onClick={onToggleCollapse}
              className="hidden lg:flex p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              aria-expanded={!collapsed}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <CollapseIcon className="w-4 h-4" />
            </button>
          )}

          <button
            onClick={onClose}
            className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Collapsible Accordion Navigation Sections */}
        <div className={cn('flex-1 overflow-y-auto px-3 py-3.5 space-y-3', collapsed && 'lg:px-2')}>
          {sections.map((section) => {
            const isExpanded = expandedSections.includes(section.title);
            const visual = SECTION_VISUALS[section.title] ?? DEFAULT_SECTION_VISUAL;
            const SectionIcon = visual.icon;

            return (
              <div key={section.title} className="space-y-1">
                {/* Clickable Section Header */}
                <button
                  type="button"
                  {...editable(`nav.section.${section.key}`)}
                  onClick={() => toggleSection(section.title)}
                  className={cn(
                    'w-full flex items-center justify-between px-2.5 py-1.5 rounded-[9px] text-[10.5px] font-bold tracking-wider uppercase transition-all duration-150 cursor-pointer select-none group',
                    visual.headerBg,
                    collapsed && 'lg:justify-center lg:px-1.5'
                  )}
                  aria-expanded={isExpanded}
                  title={collapsed ? section.label : undefined}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <SectionIcon className={cn('w-3.5 h-3.5 shrink-0', visual.iconColor)} />
                    <span className={cn('truncate', visual.labelColor, collapsed && 'lg:hidden')}>
                      {section.label}
                    </span>
                  </div>
                  <span className={cn('shrink-0 text-slate-400 group-hover:text-slate-200 transition-transform', collapsed && 'lg:hidden')}>
                    {isExpanded ? (
                      <ChevronDown className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5" />
                    )}
                  </span>
                </button>

                {/* Collapsible Child Items */}
                {/*
                  Items follow the accordion state, except in the desktop icon rail
                  (collapsed) where section headers are unlabeled and every item
                  must stay reachable. The lg: overrides only apply on desktop so
                  the mobile drawer keeps honouring the accordion.
                */}
                <div
                  className={cn(
                    'overflow-hidden transition-all duration-200 ease-in-out',
                    isExpanded
                      ? 'max-h-96 opacity-100 pt-1 pb-0.5'
                      : 'max-h-0 opacity-0 pointer-events-none',
                    !isExpanded &&
                      collapsed &&
                      'lg:max-h-96 lg:opacity-100 lg:pointer-events-auto lg:pt-1 lg:pb-0.5'
                  )}
                >
                  <div
                    className={cn(
                      'ml-2.5 pl-2.5 border-l border-white/10 space-y-0.5',
                      collapsed && 'lg:ml-0 lg:pl-0 lg:border-l-0'
                    )}
                  >
                    {section.items.map((item) => {
                      const Icon = item.icon;
                      return (
                        <NavLink
                          key={item.path}
                          {...editable(`nav.item.${item.key}`)}
                          to={item.path}
                          onClick={() => {
                            if (window.innerWidth < 1024) onClose();
                          }}
                          className={({ isActive }) => navItemClass(isActive)}
                          title={collapsed ? item.title : undefined}
                        >
                          {({ isActive }) => (
                            <>
                              <Icon
                                className={cn(
                                  'w-4 h-4 shrink-0 transition-colors',
                                  isActive ? 'text-[#8EA5FF]' : 'text-slate-400 group-hover:text-white'
                                )}
                              />
                              <span className={cn('truncate', collapsed && 'lg:sr-only')}>{item.title}</span>
                            </>
                          )}
                        </NavLink>
                      );
                    })}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Sidebar Promo Card — Smarter Billing for a Brighter Future */}
        <div className={cn('p-3 border-t border-white/10 shrink-0', collapsed && 'lg:p-2')}>
          {collapsed ? (
            <div
              className="hidden lg:flex items-center justify-center p-2 rounded-xl bg-gradient-to-b from-[#2A1E63] to-[#1A1245] border border-white/10 shadow-xs cursor-pointer group"
              title="Smarter Billing for a Brighter Future — Manage. Track. Grow."
            >
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#E83E8C] to-[#6C2BD9] flex items-center justify-center text-white shadow-xs">
                <Sparkles className="w-4 h-4 text-white" />
              </div>
            </div>
          ) : null}

          <div
            className={cn(
              'relative overflow-hidden rounded-2xl bg-gradient-to-b from-[#281F62] via-[#201852] to-[#17113E] p-4 border border-white/10 shadow-md',
              collapsed && 'lg:hidden'
            )}
          >
            {/* Ambient Wave Graphic at Bottom */}
            <div className="absolute inset-x-0 bottom-0 h-16 pointer-events-none opacity-90 overflow-hidden">
              <svg
                viewBox="0 0 200 80"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className="w-full h-full object-cover"
                preserveAspectRatio="none"
              >
                <path
                  d="M0 45 C 50 15, 110 65, 200 25 L 200 80 L 0 80 Z"
                  fill="url(#sidebarWave1)"
                  opacity="0.4"
                />
                <path
                  d="M0 55 C 60 30, 130 65, 200 38 L 200 80 L 0 80 Z"
                  fill="url(#sidebarWave2)"
                  opacity="0.7"
                />
                <path
                  d="M0 65 C 70 45, 140 70, 200 50 L 200 80 L 0 80 Z"
                  fill="url(#sidebarWave3)"
                  opacity="0.9"
                />
                <defs>
                  <linearGradient id="sidebarWave1" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#7C3AED" />
                    <stop offset="100%" stopColor="#E83E8C" />
                  </linearGradient>
                  <linearGradient id="sidebarWave2" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#E83E8C" />
                    <stop offset="100%" stopColor="#D81B60" />
                  </linearGradient>
                  <linearGradient id="sidebarWave3" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#FF4081" />
                    <stop offset="100%" stopColor="#8E24AA" />
                  </linearGradient>
                </defs>
              </svg>
            </div>

            {/* Content */}
            <div className="relative z-10 space-y-1">
              <h4 className="text-[13px] font-bold text-white tracking-tight leading-snug">
                Smarter Billing
              </h4>
              <h4 className="text-[13px] font-bold text-white tracking-tight leading-snug">
                for a Brighter Future
              </h4>
              <p className="text-[11px] font-medium text-slate-300/90 pt-1">
                Manage. Track. Grow.
              </p>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
