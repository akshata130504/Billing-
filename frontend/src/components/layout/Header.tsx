import { useNavigate } from 'react-router-dom';
import { Menu, Search, Bell, Plus, Settings, ChevronDown } from 'lucide-react';
import { useToast } from '../common/Toast';

export interface HeaderProps {
  onMenuClick: () => void;
  onQuickCreateClick: () => void;
  onOpenSearch: () => void;
}

export function Header({
  onMenuClick,
  onQuickCreateClick,
  onOpenSearch,
}: HeaderProps) {
  const { showToast } = useToast();
  const navigate = useNavigate();

  return (
    <header className="h-16 bg-white border-b border-slate-200/80 px-4 sm:px-6 flex items-center justify-between gap-4 sticky top-0 z-30">
      {/* Left: Mobile Toggle & Global Search trigger */}
      <div className="flex items-center gap-3 flex-1 max-w-xl">
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 rounded-xl text-slate-600 hover:bg-slate-100 focus:outline-none"
          aria-label="Open sidebar"
        >
          <Menu className="w-5 h-5" />
        </button>

        {/* Global Search Trigger (Opens Search Modal) */}
        <button
          type="button"
          onClick={onOpenSearch}
          aria-label="Open global search (Ctrl + K)"
          className="relative w-full text-left cursor-pointer group pl-10 pr-12 py-2 text-xs bg-slate-50 hover:bg-slate-100/70 border border-slate-200/90 rounded-xl text-slate-400 transition-colors"
        >
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 group-hover:text-slate-600 transition-colors pointer-events-none" />
          <span className="block truncate">
            Search customers, invoices, subscriptions, payments...
          </span>
          <span className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-0.5 pointer-events-none">
            <span className="text-[10px] font-mono bg-white text-slate-400 px-1.5 py-0.5 rounded border border-slate-200 shadow-2xs">
              ⌘K
            </span>
          </span>
        </button>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-2.5 sm:gap-3">
        {/* Organization Selector */}
        <button
          type="button"
          onClick={() => showToast('info', 'Workspace', 'Active workspace: Rooman Technologies')}
          className="hidden sm:inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200/90 rounded-xl hover:bg-slate-50 transition-colors cursor-pointer"
        >
          <img src="/logos/rooman-shield-logo.png" alt="Rooman" className="w-4 h-4 object-contain" />
          <span>Rooman Technologies</span>
          <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
        </button>

        {/* Quick Create '+' Button */}
        <button
          type="button"
          onClick={onQuickCreateClick}
          className="w-8 h-8 rounded-xl bg-brand-600 hover:bg-brand-700 active:bg-brand-800 text-white flex items-center justify-center shadow-xs transition-colors cursor-pointer"
          aria-label="Quick Create"
          title="Quick Create"
        >
          <Plus className="w-4 h-4 stroke-[2.5]" />
        </button>

        {/* Notifications */}
        <button
          type="button"
          onClick={() => showToast('info', 'Notifications', 'No unread critical alerts.')}
          className="relative p-2 rounded-xl text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
          aria-label="Notifications"
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500 ring-2 ring-white" />
        </button>

        {/* Settings Cog */}
        <button
          type="button"
          onClick={() => navigate('/system/settings')}
          className="p-2 rounded-xl text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
          aria-label="Settings"
        >
          <Settings className="w-4 h-4" />
        </button>

        {/* User Profile */}
        <div className="flex items-center gap-2 pl-2 border-l border-slate-200/70">
          <div className="w-8 h-8 rounded-full bg-slate-300 text-slate-700 font-semibold text-xs flex items-center justify-center">
            AR
          </div>
          <div className="hidden md:block text-left leading-tight">
            <p className="text-xs font-bold text-slate-900">
              Akshata R.
            </p>
            <p className="text-[10px] text-slate-400 font-medium">Admin</p>
          </div>
        </div>
      </div>
    </header>
  );
}
