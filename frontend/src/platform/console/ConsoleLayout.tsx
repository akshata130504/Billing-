import { useCallback, useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  Building2,
  Globe,
  LayoutDashboard,
  LogOut,
  Menu,
  ScrollText,
  ShieldCheck,
  UserCircle,
  Users,
  X,
} from 'lucide-react';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingState } from '../../components/common/LoadingState';
import { cn } from '../../utils/cn';
import { PlatformApiError, PlatformMe, PlatformRole, ROLE_LABELS, platformApi } from '../platformApi';
import { loadPlatformMe } from '../platformSession';
import { ADMIN, ConsoleContext, ConsoleSession } from './ConsoleContext';

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  roles?: PlatformRole[];
  end?: boolean;
}

// Visibility follows the server's authorization (docs section 9); the server still decides.
export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/organizations', label: 'Organizations', icon: Building2 },
  { to: '/staff', label: 'Platform staff', icon: Users, roles: [ADMIN] },
  { to: '/audit', label: 'Audit log', icon: ScrollText, roles: [ADMIN] },
  { to: '/website', label: 'Website', icon: Globe, roles: [ADMIN] },
  { to: '/health', label: 'System health', icon: Activity },
  { to: '/account', label: 'My account', icon: UserCircle },
];

/** Authenticated shell of the platform console: session gate, sidebar, content outlet. */
export function ConsoleLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [me, setMe] = useState<PlatformMe | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const current = await loadPlatformMe();
      if (!current) {
        navigate('/login', { replace: true });
        return;
      }
      setMe(current);
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : 'Could not reach the platform API.');
    }
  }, [navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => setMenuOpen(false), [location.pathname]);

  const session = useMemo<ConsoleSession | null>(() => {
    if (!me) return null;
    return {
      me,
      role: me.staff.role,
      hasRole: (...roles) => roles.includes(me.staff.role),
      signOut: async () => {
        try {
          await platformApi.logout();
        } finally {
          navigate('/login', { replace: true });
        }
      },
    };
  }, [me, navigate]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <ErrorState title="Platform console unavailable" message={error} onRetry={() => void load()} />
      </div>
    );
  }
  if (!session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <LoadingState message="Loading platform session..." />
      </div>
    );
  }

  const items = NAV_ITEMS.filter((item) => !item.roles || session.hasRole(...item.roles));
  const nav = (
    <nav aria-label="Platform console" className="flex flex-1 flex-col gap-1 px-3 py-4">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              isActive ? 'bg-white/10 text-white' : 'text-slate-300 hover:bg-white/5 hover:text-white'
            )
          }
        >
          <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
  const identity = (
    <div className="border-t border-white/10 px-4 py-4">
      <p className="truncate text-sm font-semibold text-white">{session.me.staff.full_name}</p>
      <p className="truncate text-xs text-slate-400">{session.me.staff.email}</p>
      <p className="mt-2 inline-flex items-center gap-1 rounded bg-white/10 px-2 py-0.5 text-[11px] font-semibold text-slate-200">
        <ShieldCheck className="h-3 w-3" aria-hidden="true" />
        {ROLE_LABELS[session.role] ?? session.role}
      </p>
      <button
        type="button"
        onClick={() => void session.signOut()}
        className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-white/15 px-3 py-2 text-sm font-medium text-slate-200 hover:bg-white/10"
      >
        <LogOut className="h-4 w-4" aria-hidden="true" />
        Sign out
      </button>
    </div>
  );
  const brand = (
    <div className="px-5 py-5">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">Rooman Billing</p>
      <p className="text-base font-bold text-white">Platform Console</p>
    </div>
  );

  return (
    <ConsoleContext.Provider value={session}>
      <div className="min-h-screen bg-slate-50 lg:flex">
        {/* Desktop sidebar */}
        <aside className="hidden w-64 shrink-0 flex-col bg-slate-900 lg:sticky lg:top-0 lg:flex lg:h-screen">
          {brand}
          {nav}
          {identity}
        </aside>

        {/* Mobile / tablet top bar */}
        <header className="sticky top-0 z-30 flex items-center justify-between bg-slate-900 px-4 py-3 lg:hidden">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Rooman Billing</p>
            <p className="text-sm font-bold text-white">Platform Console</p>
          </div>
          <button
            type="button"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
            className="rounded-lg p-2 text-slate-200 hover:bg-white/10"
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </header>
        {menuOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <button type="button" aria-label="Close menu" className="absolute inset-0 bg-slate-900/60" onClick={() => setMenuOpen(false)} />
            <aside className="relative flex h-full w-72 max-w-[85%] flex-col bg-slate-900">
              {brand}
              {nav}
              {identity}
            </aside>
          </div>
        )}

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>
    </ConsoleContext.Provider>
  );
}
