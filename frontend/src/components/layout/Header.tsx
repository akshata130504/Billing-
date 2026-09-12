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
  Bell,
  CheckCheck,
  X,
  FileText,
  CreditCard,
  AlertCircle,
  Clock,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useToast } from '../common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';
import { controlCenterService } from '../../services/controlCenterService';
import { queryKeys } from '../../hooks/queries';
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

  interface HeaderNotificationItem {
    id: string;
    title: string;
    description: string;
    time: string;
    read: boolean;
    type: 'invoice' | 'payment' | 'approval' | 'customer' | 'alert';
    link: string;
  }

  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notificationTab, setNotificationTab] = useState<'all' | 'unread'>('all');
  const notificationsRef = useRef<HTMLDivElement>(null);
  useDismiss(notificationsOpen, () => setNotificationsOpen(false), notificationsRef);

  const [notifications, setNotifications] = useState<HeaderNotificationItem[]>([
    {
      id: 'notif-1',
      title: 'Invoice #INV-2025-001 Overdue',
      description: 'Acme Corp payment of ₹48,000 is 3 days past due date.',
      time: '15m ago',
      read: false,
      type: 'invoice',
      link: '/invoices',
    },
    {
      id: 'notif-2',
      title: 'Payment Received',
      description: '₹10,32,000 recorded via Stripe for September billing.',
      time: '1h ago',
      read: false,
      type: 'payment',
      link: '/payments',
    },
    {
      id: 'notif-3',
      title: 'Discount Approval Required',
      description: 'Quote #QT-2025-084 requires manager sign-off (25% discount).',
      time: '3h ago',
      read: false,
      type: 'approval',
      link: '/approvals',
    },
  ]);

  const actionCenterQuery = useQuery({
    queryKey: queryKeys.controlCenter.actionCenter(),
    queryFn: () => controlCenterService.actionCenter(),
    staleTime: 30000,
    refetchInterval: 60000,
  });

  useEffect(() => {
    if (actionCenterQuery.data?.items && actionCenterQuery.data.items.length > 0) {
      const mapped: HeaderNotificationItem[] = actionCenterQuery.data.items.slice(0, 5).map((item) => {
        let link = '/invoices';
        let type: HeaderNotificationItem['type'] = 'alert';
        if (item.category === 'pending_approval') {
          link = '/approvals';
          type = 'approval';
        } else if (item.category === 'pending_quote') {
          link = '/quotes';
          type = 'invoice';
        } else if (item.category === 'failed_payment') {
          link = '/payments';
          type = 'payment';
        } else if (item.category === 'expiring_trial') {
          link = '/subscriptions';
          type = 'customer';
        }

        return {
          id: item.id,
          title: item.title,
          description: item.description,
          time: item.due_info || 'Today',
          read: false,
          type,
          link,
        };
      });
      setNotifications(mapped);
    }
  }, [actionCenterQuery.data]);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const handleMarkAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    showToast('info', 'Notifications Updated', 'All notifications marked as read.');
  };

  const handleNotificationClick = (item: HeaderNotificationItem) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === item.id ? { ...n, read: true } : n))
    );
    setNotificationsOpen(false);
    navigate(item.link);
  };

  const handleDismissNotification = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  };

  const displayedNotifications =
    notificationTab === 'unread'
      ? notifications.filter((n) => !n.read)
      : notifications;

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
    <header className="h-16 bg-white border-b border-[#E7E9F2] px-4 sm:px-6 flex items-center justify-between gap-4 sticky top-0 z-30">
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
            className="w-full pl-10 pr-12 py-2 text-xs bg-[#F7F8FC] group-hover:bg-[#F0F2FA] border border-[#E7E9F2] rounded-xl text-[#11194F] placeholder:text-[#7B829A] cursor-pointer transition-colors outline-none focus:border-brand-500"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-0.5 pointer-events-none">
            <span className="text-[10px] font-mono bg-white text-[#7B829A] px-1.5 py-0.5 rounded border border-[#E7E9F2] shadow-2xs">
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
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-[#11194F] bg-white border border-[#E7E9F2] rounded-xl hover:bg-[#F7F8FC] transition-colors cursor-pointer select-none max-w-[240px]"
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
            <div className="absolute right-0 mt-2 w-72 bg-white border border-[#E7E9F2] rounded-2xl shadow-xl p-1.5 z-50">
              <div className="px-3 py-2 border-b border-[#E7E9F2]">
                <p className="text-[10px] font-bold uppercase tracking-wider text-[#7B829A]">
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
                          ? 'bg-[#E8EBFC] text-[#25247A] font-semibold'
                          : 'text-[#59617D] hover:bg-[#F7F8FC] hover:text-[#11194F]'
                      )}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div
                          className={cn(
                            'p-1.5 rounded-lg border shrink-0',
                            isCurrent
                              ? 'bg-white border-[#D0D7F9] text-[#3F51C9]'
                              : 'bg-[#F7F8FC] border-[#E7E9F2] text-[#7B829A]'
                          )}
                        >
                          <Building2 className="w-3.5 h-3.5" />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate leading-snug">{org.name}</p>
                          <p className="text-[10px] text-[#7B829A] font-normal truncate">
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
                  <p className="px-3 py-2 text-xs text-[#7B829A]">No organizations found.</p>
                )}
              </div>
              <div className="border-t border-[#E7E9F2] mt-1 pt-1">
                <Link
                  to="/settings?tab=organization"
                  onClick={() => setWorkspaceOpen(false)}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs text-[#59617D] hover:text-brand-600 hover:bg-[#F7F8FC] rounded-lg transition-colors"
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
          className="w-8 h-8 rounded-xl bg-gradient-to-r from-[#E83E8C] to-[#D81B60] hover:from-[#D81B60] hover:to-[#C2185B] active:opacity-90 text-white flex items-center justify-center shadow-xs transition-all cursor-pointer"
          aria-label="Quick create"
          title="Quick create"
        >
          <Plus className="w-4 h-4 stroke-[2.5]" />
        </button>

        {/* Dynamic Notifications */}
        <div className="relative" ref={notificationsRef}>
          <button
            type="button"
            onClick={() => setNotificationsOpen((prev) => !prev)}
            className={cn(
              "relative p-2 rounded-xl transition-colors cursor-pointer",
              notificationsOpen
                ? "bg-[#E8EBFC] text-[#25247A]"
                : "text-[#7B829A] hover:text-[#11194F] hover:bg-[#F7F8FC]"
            )}
            aria-label="Notifications"
            title="Notifications"
            aria-expanded={notificationsOpen}
            aria-haspopup="true"
          >
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 min-w-[14px] h-3.5 px-0.5 bg-[#E83E8C] text-white text-[9px] font-bold rounded-full flex items-center justify-center leading-none animate-in zoom-in-75">
                {unreadCount}
              </span>
            )}
          </button>

          {/* Dynamic Notification Panel Dropdown */}
          {notificationsOpen && (
            <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-white rounded-2xl shadow-modal border border-[#E7E9F2] overflow-hidden z-40 animate-in fade-in zoom-in-95 duration-150">
              {/* Header */}
              <div className="px-4 py-3 bg-white border-b border-slate-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-[#11194F]">Notifications</span>
                  {unreadCount > 0 && (
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-[#E83E8C]/10 text-[#E83E8C]">
                      {unreadCount} new
                    </span>
                  )}
                </div>
                {unreadCount > 0 && (
                  <button
                    type="button"
                    onClick={handleMarkAllRead}
                    className="text-[11px] font-semibold text-[#3F51C9] hover:text-[#25247A] flex items-center gap-1 cursor-pointer transition-colors"
                  >
                    <CheckCheck className="w-3.5 h-3.5" />
                    <span>Mark all read</span>
                  </button>
                )}
              </div>

              {/* Filter Tabs */}
              <div className="px-3 pt-2 pb-1.5 bg-[#F7F8FC] border-b border-slate-100 flex items-center gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => setNotificationTab('all')}
                  className={cn(
                    "px-2.5 py-1 rounded-lg font-medium transition-colors cursor-pointer",
                    notificationTab === 'all'
                      ? "bg-white text-[#25247A] font-bold shadow-2xs"
                      : "text-slate-500 hover:text-slate-800"
                  )}
                >
                  All ({notifications.length})
                </button>
                <button
                  type="button"
                  onClick={() => setNotificationTab('unread')}
                  className={cn(
                    "px-2.5 py-1 rounded-lg font-medium transition-colors cursor-pointer",
                    notificationTab === 'unread'
                      ? "bg-white text-[#25247A] font-bold shadow-2xs"
                      : "text-slate-500 hover:text-slate-800"
                  )}
                >
                  Unread ({unreadCount})
                </button>
              </div>

              {/* List */}
              <div className="max-h-80 overflow-y-auto divide-y divide-slate-100">
                {displayedNotifications.length === 0 ? (
                  <div className="py-8 px-4 text-center">
                    <div className="w-10 h-10 rounded-full bg-emerald-50 text-emerald-600 mx-auto flex items-center justify-center mb-2">
                      <Check className="w-5 h-5" />
                    </div>
                    <p className="text-xs font-semibold text-slate-700">All caught up!</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">No new notifications to show.</p>
                  </div>
                ) : (
                  displayedNotifications.map((notif) => (
                    <div
                      key={notif.id}
                      onClick={() => handleNotificationClick(notif)}
                      className={cn(
                        "p-3.5 flex items-start gap-3 hover:bg-slate-50 transition-colors cursor-pointer group relative",
                        !notif.read && "bg-[#E8EBFC]/25"
                      )}
                    >
                      <div className="mt-0.5 shrink-0">
                        {notif.type === 'invoice' && (
                          <div className="w-7 h-7 rounded-lg bg-[#E8EBFC] text-[#3F51C9] flex items-center justify-center">
                            <FileText className="w-3.5 h-3.5" />
                          </div>
                        )}
                        {notif.type === 'payment' && (
                          <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                            <CreditCard className="w-3.5 h-3.5" />
                          </div>
                        )}
                        {notif.type === 'approval' && (
                          <div className="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                            <AlertCircle className="w-3.5 h-3.5" />
                          </div>
                        )}
                        {notif.type === 'customer' && (
                          <div className="w-7 h-7 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
                            <Clock className="w-3.5 h-3.5" />
                          </div>
                        )}
                        {notif.type === 'alert' && (
                          <div className="w-7 h-7 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
                            <AlertCircle className="w-3.5 h-3.5" />
                          </div>
                        )}
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-1">
                          <p className={cn("text-xs truncate", notif.read ? "text-slate-700 font-medium" : "text-[#11194F] font-bold")}>
                            {notif.title}
                          </p>
                          <span className="text-[10px] text-slate-400 shrink-0">{notif.time}</span>
                        </div>
                        <p className="text-[11px] text-slate-500 line-clamp-2 mt-0.5 leading-snug">
                          {notif.description}
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={(e) => handleDismissNotification(notif.id, e)}
                        className="opacity-0 group-hover:opacity-100 p-1 hover:bg-slate-200 rounded text-slate-400 hover:text-slate-600 transition-opacity cursor-pointer shrink-0"
                        title="Dismiss"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))
                )}
              </div>

              {/* Footer */}
              <div className="p-2.5 bg-[#F7F8FC] border-t border-slate-100 text-center">
                <button
                  type="button"
                  onClick={() => {
                    setNotificationsOpen(false);
                    navigate('/dashboard');
                  }}
                  className="text-xs font-semibold text-[#3F51C9] hover:text-[#25247A] transition-colors cursor-pointer"
                >
                  View all in Action Center &rarr;
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Settings */}
        <Link
          to="/settings"
          className="p-2 rounded-xl text-[#7B829A] hover:text-[#11194F] hover:bg-[#F7F8FC] transition-colors cursor-pointer"
          aria-label="Settings"
          title="Settings"
        >
          <Settings className="w-4 h-4" />
        </Link>

        {/* User menu */}
        <div className="relative pl-2 border-l border-[#E7E9F2]" ref={userMenuRef}>
          <button
            type="button"
            onClick={() => setUserMenuOpen((prev) => !prev)}
            aria-expanded={userMenuOpen}
            aria-haspopup="true"
            className="flex items-center gap-2 rounded-xl px-1 py-0.5 hover:bg-[#F7F8FC] transition-colors"
          >
            <div className="w-8 h-8 rounded-full bg-[#D81B60] text-white font-bold text-xs flex items-center justify-center shadow-xs overflow-hidden">
              {user?.avatar_url ? (
                <img
                  src={user.avatar_url}
                  alt={user?.full_name || 'Profile'}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    (e.target as HTMLElement).style.display = 'none';
                  }}
                />
              ) : (
                initials(user?.full_name, user?.email?.[0]?.toUpperCase() ?? '?')
              )}
            </div>
            <div className="hidden md:block text-left leading-tight max-w-[140px]">
              <p className="text-xs font-bold text-[#11194F] truncate">{user?.full_name ?? ''}</p>
              <p className="text-[10px] text-[#7B829A] font-medium truncate">{roleLabel}</p>
            </div>
            <ChevronDown
              className={cn(
                'hidden md:block w-3.5 h-3.5 text-[#7B829A] transition-transform',
                userMenuOpen && 'rotate-180'
              )}
            />
          </button>

          {userMenuOpen && (
            <div className="absolute right-0 mt-2 w-64 bg-white border border-[#E7E9F2] rounded-2xl shadow-xl p-1.5 z-50">
              <div className="px-3 py-2.5 border-b border-[#E7E9F2] flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-full bg-[#D81B60] text-white font-bold text-xs flex items-center justify-center shrink-0 overflow-hidden">
                  {user?.avatar_url ? (
                    <img
                      src={user.avatar_url}
                      alt={user?.full_name || 'Profile'}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                      }}
                    />
                  ) : (
                    initials(user?.full_name, user?.email?.[0]?.toUpperCase() ?? '?')
                  )}
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-[#11194F] truncate">{user?.full_name}</p>
                  <p className="text-[11px] text-[#59617D] truncate">{user?.email}</p>
                  {roleLabel && (
                    <p className="text-[10px] text-[#7B829A] mt-0.5">
                      {roleLabel} · {organization?.name}
                    </p>
                  )}
                </div>
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
                  className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-[#59617D] hover:bg-[#F7F8FC] hover:text-[#11194F]"
                >
                  <Settings className="w-4 h-4 text-[#7B829A]" />
                  Settings
                </Link>
                <Link
                  to="/settings?tab=security"
                  onClick={() => setUserMenuOpen(false)}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-[#59617D] hover:bg-[#F7F8FC] hover:text-[#11194F]"
                >
                  <KeyRound className="w-4 h-4 text-[#7B829A]" />
                  Change password
                </Link>
              </div>
              <div className="border-t border-[#E7E9F2] pt-1">
                <button
                  type="button"
                  onClick={() => void handleSignOut()}
                  disabled={signingOut}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-[#D81B60] hover:bg-[#F9D9E8]/30 disabled:opacity-60"
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
