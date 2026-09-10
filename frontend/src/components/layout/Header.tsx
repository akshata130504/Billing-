import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Menu,
  Search,
  Plus,
  Settings,
  User,
  ChevronDown,
  Check,
  Building2,
  KeyRound,
  LogOut,
  Loader2,
} from 'lucide-react';
import { useToast } from '../common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';
import { cn } from '../../utils/cn';
import { initials, ROLE_LABELS } from '../../utils/format';

export interface HeaderProps {
  onMenuClick: () => void;
  onQuickCreateClick: () => void;
  onOpenSearch: () => void;
}

/** Closes a dropdown on outside click / Escape. */
function useDismiss(isOpen: boolean, onClose: () => void, ref: React.RefObject<HTMLElement>) {
  useEffect(() => {
    if (!isOpen) return;
    const onMouseDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [isOpen, onClose, ref]);
}

export function Header({ onMenuClick, onQuickCreateClick, onOpenSearch }: HeaderProps) {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { user, organization, membership, organizations, switchOrganization, logout } = useAuth();

  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [switchingTo, setSwitchingTo] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  const workspaceRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  useDismiss(workspaceOpen, () => setWorkspaceOpen(false), workspaceRef);
  useDismiss(userMenuOpen, () => setUserMenuOpen(false), userMenuRef);

  const roleLabel = membership ? ROLE_LABELS[membership.role] ?? membership.role : '';

  const handleSwitch = async (organizationId: string, name: string) => {
    if (!organization || organizationId === organization.id) {
      setWorkspaceOpen(false);
      return;
    }
    setSwitchingTo(organizationId);
    try {
      await switchOrganization(organizationId);
      setWorkspaceOpen(false);
      showToast('success', 'Organization switched', `You are now working in ${name}.`);
      navigate('/dashboard');
    } catch (err) {
      showToast('error', 'Could not switch organization', toApiError(err).message);
    } finally {
      setSwitchingTo(null);
    }
  };

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await logout();
      navigate('/login', { replace: true });
    } finally {
      setSigningOut(false);
      setUserMenuOpen(false);
    }
  };

  return (
    <header className="h-16 bg-white border-b border-slate-200/80 px-4 sm:px-6 flex items-center justify-between gap-4 sticky top-0 z-30">
      {/* Left: mobile toggle + search trigger */}
      <div className="flex items-center gap-3 flex-1 max-w-xl">
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 rounded-xl text-slate-600 hover:bg-slate-100 focus:outline-none"
          aria-label="Open sidebar"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div onClick={onOpenSearch} className="relative w-full cursor-pointer group">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 group-hover:text-slate-600 transition-colors pointer-events-none" />
          <input
            type="text"
            readOnly
            role="button"
            aria-label="Open global search (Ctrl + K)"
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onOpenSearch();
              }
            }}
            placeholder="Search customers, invoices, subscriptions, payments... (Ctrl + K)"
            className="w-full pl-10 pr-12 py-2 text-xs bg-slate-50 group-hover:bg-slate-100/70 border border-slate-200/90 rounded-xl text-slate-900 placeholder:text-slate-400 cursor-pointer transition-colors outline-none"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-0.5 pointer-events-none">
            <span className="text-[10px] font-mono bg-white text-slate-400 px-1.5 py-0.5 rounded border border-slate-200 shadow-2xs">
              Ctrl K
            </span>
          </div>
        </div>
      </div>

      {/* Right controls */}
      <div className="flex items-center gap-2.5 sm:gap-3">
        {/* Organization selector */}
        <div className="relative hidden sm:block" ref={workspaceRef}>
          <button
            type="button"
            onClick={() => setWorkspaceOpen((prev) => !prev)}
            aria-expanded={workspaceOpen}
            aria-haspopup="true"
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200/90 rounded-xl hover:bg-slate-50 transition-colors cursor-pointer select-none max-w-[240px]"
          >
            {organization?.logo_url ? (
              <img
                src={organization.logo_url}
                alt=""
                className="w-4 h-4 object-contain rounded-sm"
              />
            ) : (
              <Building2 className="w-4 h-4 text-slate-400" />
            )}
            <span className="truncate">{organization?.name ?? 'Organization'}</span>
            <ChevronDown
              className={cn(
                'w-3.5 h-3.5 text-slate-400 transition-transform shrink-0',
                workspaceOpen && 'rotate-180 text-brand-600'
              )}
            />
          </button>

          {workspaceOpen && (
            <div className="absolute right-0 mt-2 w-72 bg-white border border-slate-200 rounded-2xl shadow-xl p-1.5 z-50">
              <div className="px-3 py-2 border-b border-slate-100">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Your organizations
                </p>
              </div>
              <div className="py-1 space-y-0.5 max-h-72 overflow-y-auto">
                {organizations.map((org) => {
                  const isCurrent = org.id === organization?.id;
                  const isSwitching = switchingTo === org.id;
                  return (
                    <button
                      key={org.id}
                      type="button"
                      disabled={switchingTo !== null}
                      onClick={() => void handleSwitch(org.id, org.name)}
                      className={cn(
                        'w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs transition-colors cursor-pointer text-left disabled:cursor-wait',
                        isCurrent
                          ? 'bg-blue-50/80 text-brand-700 font-semibold'
                          : 'text-slate-700 hover:bg-slate-50 hover:text-slate-900'
                      )}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div
                          className={cn(
                            'p-1.5 rounded-lg border shrink-0',
                            isCurrent
                              ? 'bg-white border-blue-200 text-brand-600'
                              : 'bg-slate-50 border-slate-200 text-slate-400'
                          )}
                        >
                          <Building2 className="w-3.5 h-3.5" />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate leading-snug">{org.name}</p>
                          <p className="text-[10px] text-slate-400 font-normal truncate">
                            {ROLE_LABELS[org.role] ?? org.role}
                          </p>
                        </div>
                      </div>
                      {isSwitching ? (
                        <Loader2 className="w-4 h-4 text-brand-600 animate-spin shrink-0 ml-2" />
                      ) : (
                        isCurrent && <Check className="w-4 h-4 text-brand-600 shrink-0 ml-2" />
                      )}
                    </button>
                  );
                })}
                {organizations.length === 0 && (
                  <p className="px-3 py-2 text-xs text-slate-400">No organizations found.</p>
                )}
              </div>
              <div className="border-t border-slate-100 mt-1 pt-1">
                <Link
                  to="/settings?tab=organization"
                  onClick={() => setWorkspaceOpen(false)}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs text-slate-500 hover:text-brand-600 hover:bg-slate-50 rounded-lg transition-colors"
                >
                  <Settings className="w-3.5 h-3.5" />
                  <span>Organization settings</span>
                </Link>
              </div>
            </div>
          )}
        </div>

        {/* Quick create */}
        <button
          type="button"
          onClick={onQuickCreateClick}
          className="w-8 h-8 rounded-xl bg-brand-600 hover:bg-brand-700 active:bg-brand-800 text-white flex items-center justify-center shadow-xs transition-colors cursor-pointer"
          aria-label="Quick create"
          title="Quick create"
        >
          <Plus className="w-4 h-4 stroke-[2.5]" />
        </button>

        {/* Settings */}
        <Link
          to="/settings"
          className="p-2 rounded-xl text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
          aria-label="Settings"
          title="Settings"
        >
          <Settings className="w-4 h-4" />
        </Link>

        {/* User menu */}
        <div className="relative pl-2 border-l border-slate-200/70" ref={userMenuRef}>
          <button
            type="button"
            onClick={() => setUserMenuOpen((prev) => !prev)}
            aria-expanded={userMenuOpen}
            aria-haspopup="true"
            className="flex items-center gap-2 rounded-xl px-1 py-0.5 hover:bg-slate-50 transition-colors"
          >
            <div className="w-8 h-8 rounded-full bg-brand-100 text-brand-700 font-semibold text-xs flex items-center justify-center">
              {initials(user?.full_name, user?.email?.[0]?.toUpperCase() ?? '?')}
            </div>
            <div className="hidden md:block text-left leading-tight max-w-[140px]">
              <p className="text-xs font-bold text-slate-900 truncate">{user?.full_name ?? ''}</p>
              <p className="text-[10px] text-slate-400 font-medium truncate">{roleLabel}</p>
            </div>
            <ChevronDown
              className={cn(
                'hidden md:block w-3.5 h-3.5 text-slate-400 transition-transform',
                userMenuOpen && 'rotate-180'
              )}
            />
          </button>

          {userMenuOpen && (
            <div className="absolute right-0 mt-2 w-64 bg-white border border-slate-200 rounded-2xl shadow-xl p-1.5 z-50">
              <div className="px-3 py-2.5 border-b border-slate-100">
                <p className="text-xs font-semibold text-slate-900 truncate">{user?.full_name}</p>
                <p className="text-[11px] text-slate-500 truncate">{user?.email}</p>
                {roleLabel && (
                  <p className="text-[10px] text-slate-400 mt-0.5">
                    {roleLabel} · {organization?.name}
                  </p>
                )}
              </div>
              <div className="py-1 space-y-0.5">
                <Link
                  to="/settings?tab=profile"
                  onClick={() => setUserMenuOpen(false)}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-slate-700 hover:bg-slate-50"
                >
                  <User className="w-4 h-4 text-slate-400" />
                  My Profile
                </Link>
                <Link
                  to="/settings"
                  onClick={() => setUserMenuOpen(false)}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-slate-700 hover:bg-slate-50"
                >
                  <Settings className="w-4 h-4 text-slate-400" />
                  Settings
                </Link>
                <Link
                  to="/settings?tab=security"
                  onClick={() => setUserMenuOpen(false)}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-slate-700 hover:bg-slate-50"
                >
                  <KeyRound className="w-4 h-4 text-slate-400" />
                  Change password
                </Link>
              </div>
              <div className="border-t border-slate-100 pt-1">
                <button
                  type="button"
                  onClick={() => void handleSignOut()}
                  disabled={signingOut}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-rose-600 hover:bg-rose-50 disabled:opacity-60"
                >
                  {signingOut ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <LogOut className="w-4 h-4" />
                  )}
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
