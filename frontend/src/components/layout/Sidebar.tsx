import { useState, useEffect } from 'react';
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
  X,
} from 'lucide-react';

export interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  /** Desktop-only icon rail mode */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

interface SidebarSection {
  title: string;
  items: {
    title: string;
    path: string;
    icon: React.ComponentType<{ className?: string }>;
  }[];
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
      { title: 'Quotes', path: '/revenue/quotes', icon: FileText },
      { title: 'CPQ', path: '/revenue/cpq', icon: Calculator },
      { title: 'Invoices', path: '/revenue/invoices', icon: Receipt },
      { title: 'Payments', path: '/revenue/payments', icon: CreditCard },
      { title: 'Collections', path: '/revenue/collections', icon: ShieldCheck },
    ],
  },
  {
    title: 'SUBSCRIPTIONS',
    items: [
      { title: 'Plans & Pricing', path: '/subscriptions/plans', icon: Layers },
      { title: 'Subscriptions', path: '/subscriptions/all', icon: Repeat },
      { title: 'Trials', path: '/subscriptions/trials', icon: Clock },
      { title: 'Usage / Metering', path: '/subscriptions/usage', icon: Gauge },
      { title: 'Proration', path: '/subscriptions/proration', icon: Percent },
      { title: 'Dunning', path: '/subscriptions/dunning', icon: AlertTriangle },
    ],
  },
  {
    title: 'CUSTOMER EXPERIENCE',
    items: [
      { title: 'Customer Lifecycle', path: '/customer-experience/lifecycle', icon: UserCheck },
      { title: 'Customer Portal', path: '/customer-experience/portal', icon: Globe },
      { title: 'Hosted Payment Pages', path: '/customer-experience/payment-pages', icon: ExternalLink },
    ],
  },
  {
    title: 'OPERATIONS',
    items: [
      { title: 'Expenses', path: '/operations/expenses', icon: Coins },
      { title: 'Projects', path: '/operations/projects', icon: Briefcase },
      { title: 'Timesheets', path: '/operations/timesheets', icon: Timer },
    ],
  },
  {
    title: 'INSIGHTS',
    items: [
      { title: 'Revenue Intelligence', path: '/insights/revenue', icon: LineChart },
      { title: 'Reports & Analytics', path: '/insights/reports', icon: BarChart3 },
      { title: 'AI in Billing', path: '/insights/ai', icon: Sparkles },
      { title: 'Activity', path: '/insights/activity', icon: Activity },
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
      { title: 'Automation', path: '/system/automation', icon: Zap },
      { title: 'Customization', path: '/system/customization', icon: Palette },
      { title: 'Integrations', path: '/system/integrations', icon: Boxes },
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

  // Initialize expanded sections from sessionStorage or default to WORKSPACE
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

  // Auto-expand section when navigating to one of its child routes
  useEffect(() => {
    const activeSection = sidebarSections.find((sec) =>
      sec.items.some((item) => location.pathname === item.path || (item.path !== '/dashboard' && location.pathname.startsWith(item.path)))
    );

    if (activeSection && !expandedSections.includes(activeSection.title)) {
      setExpandedSections((prev) => {
        const next = [...prev, activeSection.title];
        try {
          sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {
          // ignore
        }
        return next;
      });
    }
  }, [location.pathname]);

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
      'flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition-colors select-none',
      collapsed && 'lg:justify-center lg:px-2',
      isActive
        ? 'bg-blue-50/90 text-brand-600 font-semibold shadow-subtle'
        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
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
          <button
            onClick={onClose}
            className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Collapsible Accordion Navigation Sections */}
        <div className={cn('flex-1 overflow-y-auto px-3 py-3 space-y-2', collapsed && 'lg:px-2')}>
          {sidebarSections.map((section) => {
            const isExpanded = expandedSections.includes(section.title);
            const hasActiveItem = section.items.some(
              (item) => location.pathname === item.path
            );

            return (
              <div key={section.title} className="space-y-1">
                {/* Clickable Collapsible Section Header */}
                <button
                  type="button"
                  onClick={() => toggleSection(section.title)}
                  className={cn(
                    'w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-[10px] font-bold tracking-wider uppercase transition-colors cursor-pointer group select-none',
                    collapsed && 'lg:justify-center lg:px-1',
                    hasActiveItem
                      ? 'text-brand-700 bg-brand-50/40'
                      : 'text-slate-400 hover:text-slate-700 hover:bg-slate-50'
                  )}
                  aria-expanded={isExpanded}
                  title={collapsed ? section.title : undefined}
                >
                  <span className={cn('truncate', collapsed && 'lg:hidden')}>{section.title}</span>
                  <span className={cn(collapsed && 'lg:hidden')}>
                    {isExpanded ? (
                      <ChevronDown className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-600 transition-transform" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-600 transition-transform" />
                    )}
                  </span>
                </button>

                {/* Collapsible Accordion Child Items with smooth height animation */}
                <div
                  className={cn(
                    'space-y-0.5 overflow-hidden transition-all duration-200 ease-in-out',
                    isExpanded || (collapsed && 'lg:max-h-none lg:opacity-100')
                      ? 'max-h-96 opacity-100 pt-0.5'
                      : 'max-h-0 opacity-0 pointer-events-none'
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
                        <Icon className="w-4 h-4 shrink-0 opacity-75" />
                        <span className={cn('truncate', collapsed && 'lg:sr-only')}>{item.title}</span>
                      </NavLink>
                    );
                  })}
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
