import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, Search, Bell, Plus, Settings, ChevronDown, Check, Building2 } from 'lucide-react';
import { useToast } from '../common/Toast';

export interface HeaderProps {
  onMenuClick: () => void;
  onQuickCreateClick: () => void;
  onOpenSearch: () => void;
}

const WORKSPACES = [
  { id: 'ws-1', name: 'Rooman Technologies', region: 'Enterprise · Primary', badge: 'Active' },
  { id: 'ws-2', name: 'Rooman APAC', region: 'Singapore · Production', badge: 'Production' },
  { id: 'ws-3', name: 'Rooman US Sandbox', region: 'Oregon · Staging', badge: 'Sandbox' },
];

export function Header({
  onMenuClick,
  onQuickCreateClick,
  onOpenSearch,
}: HeaderProps) {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [selectedWorkspace, setSelectedWorkspace] = useState('Rooman Technologies');
  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = useState(false);
  const workspaceDropdownRef = useRef<HTMLDivElement>(null);

  // Close workspace dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (workspaceDropdownRef.current && !workspaceDropdownRef.current.contains(e.target as Node)) {
        setIsWorkspaceMenuOpen(false);
      }
    }
    if (isWorkspaceMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isWorkspaceMenuOpen]);

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

        {/* Global Search Input Button (Opens Search Modal) */}
        <div
          onClick={onOpenSearch}
          className="relative w-full cursor-pointer group"
        >
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 group-hover:text-slate-600 transition-colors pointer-events-none" />
          <input
            type="text"
            readOnly
            placeholder="Search customers, invoices, subscriptions, payments... (Ctrl + K)"
            className="w-full pl-10 pr-12 py-2 text-xs bg-slate-50 group-hover:bg-slate-100/70 border border-slate-200/90 rounded-xl text-slate-900 placeholder:text-slate-400 cursor-pointer transition-colors outline-none"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-0.5 pointer-events-none">
            <span className="text-[10px] font-mono bg-white text-slate-400 px-1.5 py-0.5 rounded border border-slate-200 shadow-2xs">
              ⌘K
            </span>
          </div>
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-2.5 sm:gap-3">
        {/* Workspace Selector Dropdown */}
        <div className="relative hidden sm:block" ref={workspaceDropdownRef}>
          <button
            type="button"
            onClick={() => setIsWorkspaceMenuOpen((prev) => !prev)}
            aria-expanded={isWorkspaceMenuOpen}
            aria-haspopup="true"
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200/90 rounded-xl hover:bg-slate-50 transition-colors cursor-pointer select-none"
          >
            <img src="/logos/rooman-shield-logo.png" alt="Rooman" className="w-4 h-4 object-contain" />
            <span>{selectedWorkspace}</span>
            <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${isWorkspaceMenuOpen ? 'rotate-180 text-brand-600' : ''}`} />
          </button>

          {isWorkspaceMenuOpen && (
            <div className="absolute right-0 mt-2 w-72 bg-white border border-slate-200 rounded-2xl shadow-xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-100">
              <div className="px-3 py-2 border-b border-slate-100">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Switch Workspace
                </p>
              </div>
              <div className="py-1 space-y-0.5">
                {WORKSPACES.map((ws) => {
                  const isCurrent = ws.name === selectedWorkspace;
                  return (
                    <button
                      key={ws.id}
                      type="button"
                      onClick={() => {
                        setSelectedWorkspace(ws.name);
                        setIsWorkspaceMenuOpen(false);
                        showToast('success', 'Workspace Switched', `Active workspace is now: ${ws.name}`);
                      }}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs transition-colors cursor-pointer text-left ${
                        isCurrent
                          ? 'bg-blue-50/80 text-brand-700 font-semibold'
                          : 'text-slate-700 hover:bg-slate-50 hover:text-slate-900'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className={`p-1.5 rounded-lg border shrink-0 ${
                          isCurrent ? 'bg-white border-blue-200 text-brand-600' : 'bg-slate-50 border-slate-200 text-slate-400'
                        }`}>
                          <Building2 className="w-3.5 h-3.5" />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate leading-snug">{ws.name}</p>
                          <p className="text-[10px] text-slate-400 font-normal truncate">{ws.region}</p>
                        </div>
                      </div>
                      {isCurrent && <Check className="w-4 h-4 text-brand-600 shrink-0 ml-2" />}
                    </button>
                  );
                })}
              </div>
              <div className="border-t border-slate-100 mt-1 pt-1">
                <button
                  type="button"
                  onClick={() => {
                    setIsWorkspaceMenuOpen(false);
                    showToast('info', 'Workspace Settings', 'Opening workspace management modal...');
                  }}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs text-slate-500 hover:text-brand-600 hover:bg-slate-50 rounded-lg transition-colors cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add or Manage Workspaces</span>
                </button>
              </div>
            </div>
          )}
        </div>

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
          onClick={() => {
            showToast('info', 'Settings', 'Navigating to system settings');
            navigate('/system/settings');
          }}
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
