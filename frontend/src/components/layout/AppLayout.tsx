import { useState, useEffect, Suspense } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { QuickCreateModal } from '../common/QuickCreateModal';
import { GlobalSearchModal } from '../common/GlobalSearchModal';
import { RoomiChatbot } from '../chat/RoomiChatbot';
import { ErrorBoundary } from '../common/ErrorBoundary';
import { PageLoader } from '../common/PageLoader';
import { PlatformAccessBanner } from './PlatformAccessBanner';
import { UiConfigProvider } from '../../appUi/UiConfigContext';

export function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [quickCreateOpen, setQuickCreateOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const { pathname } = useLocation();

  // Global Ctrl + K / Cmd + K listener (single owner of the toggle)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <UiConfigProvider>
      <div className="flex h-screen bg-slate-50 overflow-hidden font-sans">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-brand-600 focus:text-white focus:text-sm focus:font-semibold focus:shadow-lg"
        >
          Skip to main content
        </a>

        {/* Sidebar Navigation */}
        <Sidebar
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
        />

        {/* Main App Content Viewport */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <Header
            onMenuClick={() => setSidebarOpen(true)}
            onQuickCreateClick={() => setQuickCreateOpen(true)}
            onOpenSearch={() => setSearchOpen(true)}
          />
          <PlatformAccessBanner />

          {/* Scrollable Page Body */}
          <main
            id="main-content"
            tabIndex={-1}
            className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-slate-50 focus:outline-none"
          >
            <div className="max-w-7xl mx-auto">
              {/* Reset on navigation so one crashed page doesn't break the rest of the app. */}
              <ErrorBoundary resetKey={pathname}>
                <Suspense fallback={<PageLoader />}>
                  <Outlet />
                </Suspense>
              </ErrorBoundary>
            </div>
          </main>
        </div>

        {/* Quick Create Modal */}
        <QuickCreateModal
          isOpen={quickCreateOpen}
          onClose={() => setQuickCreateOpen(false)}
        />

        {/* Global Search Omnibox Modal */}
        <GlobalSearchModal
          isOpen={searchOpen}
          onClose={() => setSearchOpen(false)}
        />

        {/* Authenticated Roomi AI Assistant */}
        <RoomiChatbot />
      </div>
    </UiConfigProvider>
  );
}
