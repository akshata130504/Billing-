import { useState, useEffect, useMemo, useRef } from 'react';
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
  title: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
}

interface SidebarSection {
  title: string;
  items: SidebarItem[];
}

export const sidebarSections: SidebarSection[] = [
  {
    title: 'WORKSPACE',
    items: [
      { title: 'Overview', path: '/dashboard', icon: LayoutDashboard },
      { title: 'Customers', path: '/customers', icon: Users },
      { title: 'Catalog', path: '/catalog', icon: Package },
    ],
  },
  {
    title: 'REVENUE',
    items: [
      { title: 'Quotes', path: '/quotes', icon: FileText },
      { title: 'CPQ', path: '/cpq', icon: Calculator },
      { title: 'Invoices', path: '/invoices', icon: Receipt },
      { title: 'Payments', path: '/payments', icon: CreditCard },
      { title: 'Collections', path: '/collections', icon: ShieldCheck },
    ],
  },
  {
    title: 'SUBSCRIPTIONS',
    items: [
      { title: 'Plans & Pricing', path: '/plans-pricing', icon: Layers },
      { title: 'Subscriptions', path: '/subscriptions', icon: Repeat },
      { title: 'Trials', path: '/trials', icon: Clock },
      { title: 'Usage / Metering', path: '/usage', icon: Gauge },
      { title: 'Proration', path: '/proration', icon: Percent },
      { title: 'Dunning', path: '/dunning', icon: AlertTriangle },
    ],
  },
  {
    title: 'CUSTOMER EXPERIENCE',
    items: [
      { title: 'Customer Lifecycle', path: '/customer-lifecycle', icon: UserCheck },
      { title: 'Customer Portal', path: '/customer-portal', icon: Globe },
      { title: 'Hosted Payment Pages', path: '/hosted-payment-pages', icon: ExternalLink },
    ],
  },
  {
    title: 'OPERATIONS',
    items: [
      { title: 'Expenses', path: '/expenses', icon: Coins },
      { title: 'Projects', path: '/projects', icon: Briefcase },
      { title: 'Timesheets', path: '/timesheets', icon: Timer },
    ],
  },
  {
    title: 'INSIGHTS',
    items: [
      { title: 'Revenue Intelligence', path: '/revenue-intelligence', icon: LineChart },
      { title: 'Reports & Analytics', path: '/reports', icon: BarChart3 },
      { title: 'AI in Billing', path: '/ai-billing', icon: Sparkles },
      { title: 'Activity', path: '/activity', icon: Activity },
    ],
  },
  {
    title: 'PLATFORMS',
    items: [
      { title: 'Mobile', path: '/platforms/mobile', icon: Smartphone },
      { title: 'Desktop', path: '/platforms/desktop', icon: Monitor },
    ],
  },
  {
    title: 'CONTROL CENTER',
    items: [
      { title: 'Action Center', path: '/control-center/action-center', icon: Inbox },
      { title: 'Approval Center', path: '/control-center/approvals', icon: FileCheck },
      { title: 'Billing Calendar', path: '/control-center/calendar', icon: Calendar },
      { title: 'Reconciliation', path: '/control-center/reconciliation', icon: ArrowLeftRight },
      { title: 'Audit Log', path: '/control-center/audit-log', icon: History },
      { title: 'Data Migration', path: '/control-center/migration', icon: UploadCloud },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { title: 'Automation', path: '/automation', icon: Zap },
      { title: 'Customization', path: '/customization', icon: Palette },
      { title: 'Integrations', path: '/integrations', icon: Boxes },
      { title: 'Settings', path: '/system/settings', icon: Settings },
    ],
  },
];

const STORAGE_KEY = 'rooman_sidebar_expanded';

export function Sidebar({
  isOpen,
  onClose,
  collapsed = false,
  onToggleCollapse,
}: SidebarProps) {
  const location = useLocation();

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

interface SectionVisualConfig {
  icon: React.ComponentType<{ className?: string }>;
  headerBg: string;
  iconColor: string;
  labelColor: string;
}

const SECTION_VISUALS: Record<string, SectionVisualConfig> = {
  WORKSPACE: {
    icon: Building2,
    headerBg: 'bg-blue-50/70 hover:bg-blue-100/60 border border-blue-100/80',
    iconColor: 'text-blue-600',
    labelColor: 'text-blue-900',
  },
  REVENUE: {
    icon: Receipt,
    headerBg: 'bg-emerald-50/70 hover:bg-emerald-100/60 border border-emerald-100/80',
    iconColor: 'text-emerald-600',
    labelColor: 'text-emerald-900',
  },
  SUBSCRIPTIONS: {
    icon: Repeat,
    headerBg: 'bg-amber-50/70 hover:bg-amber-100/60 border border-amber-100/80',
    iconColor: 'text-amber-600',
    labelColor: 'text-amber-900',
  },
  'CUSTOMER EXPERIENCE': {
    icon: UserCheck,
    headerBg: 'bg-rose-50/70 hover:bg-rose-100/60 border border-rose-100/80',
    iconColor: 'text-rose-600',
    labelColor: 'text-rose-900',
  },
  OPERATIONS: {
    icon: Briefcase,
    headerBg: 'bg-sky-50/70 hover:bg-sky-100/60 border border-sky-100/80',
    iconColor: 'text-sky-600',
    labelColor: 'text-sky-900',
  },
  INSIGHTS: {
    icon: Sparkles,
    headerBg: 'bg-purple-50/70 hover:bg-purple-100/60 border border-purple-100/80',
    iconColor: 'text-purple-600',
    labelColor: 'text-purple-900',
  },
  PLATFORMS: {
    icon: Monitor,
    headerBg: 'bg-indigo-50/60 hover:bg-indigo-100/50 border border-indigo-100/70',
    iconColor: 'text-indigo-600',
    labelColor: 'text-indigo-900',
  },
  'CONTROL CENTER': {
    icon: ShieldCheck,
    headerBg: 'bg-indigo-50/80 hover:bg-indigo-100/70 border border-indigo-200/70',
    iconColor: 'text-indigo-600',
    labelColor: 'text-indigo-900',
  },
  SYSTEM: {
    icon: Settings,
    headerBg: 'bg-slate-100/80 hover:bg-slate-200/60 border border-slate-200/80',
    iconColor: 'text-slate-600',
    labelColor: 'text-slate-800',
  },
};

  const navItemClass = (isActive: boolean) =>
    cn(
      'group flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 select-none',
      collapsed && 'lg:justify-center lg:px-2',
      isActive
        ? 'bg-brand-50 text-brand-700 font-semibold shadow-2xs'
        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50/90'
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
          'fixed top-0 bottom-0 left-0 z-50 w-60 bg-white border-r border-slate-200/80 flex flex-col justify-between transition-[transform,width] duration-200 ease-in-out lg:translate-x-0 lg:static lg:z-auto',
          collapsed && 'lg:w-[72px]',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Brand Header */}
        <div
          className={cn(
            'h-16 px-3.5 sm:px-4 flex items-center justify-between border-b border-slate-100 shrink-0',
            collapsed && 'lg:flex-col lg:justify-center lg:gap-1 lg:px-2 lg:h-auto lg:py-2'
          )}
        >
          <NavLink to="/dashboard" className="flex items-center group py-1 min-w-0">
            <span className={cn(collapsed && 'lg:hidden')}>
              <RoomanLogo variant="brand" size="md" showBillingBadge={true} />
            </span>
            <span className={cn('hidden', collapsed && 'lg:inline-flex')}>
              <RoomanLogo variant="shield" size="md" />
            </span>
          </NavLink>

          {onToggleCollapse && (
            <button
              type="button"
              onClick={onToggleCollapse}
              className="hidden lg:flex p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              aria-expanded={!collapsed}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <CollapseIcon className="w-4 h-4" />
            </button>
          )}

          <button
            onClick={onClose}
            className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Collapsible Accordion Navigation Sections */}
        <div className={cn('flex-1 overflow-y-auto px-3 py-3.5 space-y-3', collapsed && 'lg:px-2')}>
          {sidebarSections.map((section) => {
            const isExpanded = expandedSections.includes(section.title);
            const visual = SECTION_VISUALS[section.title] || {
              icon: Layers,
              headerBg: 'bg-slate-50 hover:bg-slate-100 border border-slate-200/60',
              iconColor: 'text-slate-500',
              labelColor: 'text-slate-800',
            };
            const SectionIcon = visual.icon;

            return (
              <div key={section.title} className="space-y-1">
                {/* Clickable Section Header */}
                <button
                  type="button"
                  onClick={() => toggleSection(section.title)}
                  className={cn(
                    'w-full flex items-center justify-between px-2.5 py-1.5 rounded-[9px] text-[10.5px] font-bold tracking-wider uppercase transition-all duration-150 cursor-pointer select-none group',
                    visual.headerBg,
                    collapsed && 'lg:justify-center lg:px-1.5'
                  )}
                  aria-expanded={isExpanded}
                  title={collapsed ? section.title : undefined}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <SectionIcon className={cn('w-3.5 h-3.5 shrink-0', visual.iconColor)} />
                    <span className={cn('truncate', visual.labelColor, collapsed && 'lg:hidden')}>
                      {section.title}
                    </span>
                  </div>
                  <span className={cn('shrink-0 text-slate-400 group-hover:text-slate-600 transition-transform', collapsed && 'lg:hidden')}>
                    {isExpanded ? (
                      <ChevronDown className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5" />
                    )}
                  </span>
                </button>

                {/* Collapsible Child Items */}
                <div
                  className={cn(
                    'overflow-hidden transition-all duration-200 ease-in-out',
                    isExpanded || (collapsed && 'lg:max-h-none lg:opacity-100')
                      ? 'max-h-96 opacity-100 pt-1 pb-0.5'
                      : 'max-h-0 opacity-0 pointer-events-none'
                  )}
                >
                  <div
                    className={cn(
                      'ml-2.5 pl-2.5 border-l border-slate-200/60 space-y-0.5',
                      collapsed && 'lg:ml-0 lg:pl-0 lg:border-l-0'
                    )}
                  >
                    {section.items.map((item) => {
                      const Icon = item.icon;
                      return (
                        <NavLink
                          key={item.path}
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
                                  isActive ? 'text-brand-600' : 'text-slate-400 group-hover:text-slate-600'
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

        {/* Footer Tenant Info */}
        <div className={cn('p-3 border-t border-slate-100 shrink-0', collapsed && 'lg:p-2')}>
          <div
            className={cn(
              'flex items-center gap-2.5 px-2 py-1.5 rounded-xl bg-slate-50 border border-slate-200/60',
              collapsed && 'lg:justify-center lg:px-1'
            )}
            title={collapsed ? 'Rooman Technologies · Enterprise Workspace' : undefined}
          >
            <div className="w-7 h-7 rounded-lg bg-white p-0.5 border border-slate-200/80 flex items-center justify-center shrink-0 shadow-2xs overflow-hidden">
              <RoomanLogo variant="shield" size="sm" />
            </div>
            <div className={cn('min-w-0 flex-1 leading-tight', collapsed && 'lg:hidden')}>
              <p className="text-xs font-bold text-slate-900 truncate">
                Rooman Technologies
              </p>
              <p className="text-[10px] text-slate-400 font-medium truncate">
                Enterprise Workspace
              </p>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
