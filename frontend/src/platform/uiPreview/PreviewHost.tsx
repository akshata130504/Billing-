/**
 * Visual-editor preview (runs inside the editor's same-origin iframe at /superadmin/ui-preview).
 *
 * Renders the REAL tenant components (Sidebar, Overview, Customers, Invoices) with the editor's
 * draft configuration, so real responsive breakpoints apply to the iframe's width.
 *
 * Design mode, never operations:
 * - every tenant API request is answered by the local read-only sample-data adapter; writes are
 *   refused before anything is sent, and there is no tenant session in this window anyway;
 * - every click and form submit is cancelled (no navigation, no actions) and only reports which
 *   configurable component was clicked;
 * - messages are accepted only from the parent window on the same origin.
 */
import { useCallback, useEffect, useMemo, useState, type MouseEvent, type ReactNode, type SyntheticEvent } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from '../../components/layout/Sidebar';
import { ToastProvider } from '../../components/common/Toast';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { CustomersListPage } from '../../pages/customers/CustomersListPage';
import { InvoicesListPage } from '../../pages/invoices/InvoicesListPage';
import { QuotesListPage } from '../../pages/quotes/QuotesListPage';
import { CatalogPage } from '../../pages/catalog/CatalogPage';
import { PlansPricingPage } from '../../pages/plans-pricing/PlansPricingPage';
import { SubscriptionsListPage } from '../../pages/subscriptions/SubscriptionsListPage';
import { CPQPage } from '../../pages/cpq/CPQPage';
import { PaymentsPage } from '../../pages/payments/PaymentsPage';
import { PaymentsProvider } from '../../pages/payments/PaymentsContext';
import { ReconciliationPage } from '../../pages/control-center/ReconciliationPage';
import { CreditNotesListPage } from '../../pages/credit-notes/CreditNotesListPage';
import { DunningPage } from '../../pages/dunning/DunningPage';
import { CollectionsDashboardPage } from '../../pages/collections/CollectionsDashboardPage';
import { ExpensesPage } from '../../pages/expenses/ExpensesPage';
import { ExpensesProvider } from '../../pages/expenses/ExpensesContext';
import { ProjectsPage } from '../../pages/projects/ProjectsPage';
import { ProjectsProvider } from '../../pages/projects/ProjectsContext';
import { TimesheetsPage } from '../../pages/timesheets/TimesheetsPage';
import { ReportsPage } from '../../pages/reports/ReportsPage';
import { CustomizationPage } from '../../pages/customization/CustomizationPage';
import { AutomationPage } from '../../pages/automation/AutomationPage';
import { SettingsPage } from '../../pages/settings/SettingsPage';
import { ActivityPage } from '../../pages/activity/ActivityPage';
import { ActionCenterPage } from '../../pages/control-center/ActionCenterPage';
import { ApprovalCenterPage } from '../../pages/control-center/ApprovalCenterPage';
import { BillingCalendarPage } from '../../pages/control-center/BillingCalendarPage';
import { AuditLogPage } from '../../pages/control-center/AuditLogPage';
import { DataMigrationPage } from '../../pages/control-center/DataMigrationPage';
import { MobilePlatformPage } from '../../pages/platforms/MobilePlatformPage';
import { DesktopPlatformPage } from '../../pages/platforms/DesktopPlatformPage';
import { CustomerPortalPage } from '../../pages/customer-portal/CustomerPortalPage';
import { HostedPaymentPagesPage } from '../../pages/hosted-payment-pages/HostedPaymentPagesPage';
import { RevenueIntelligencePage } from '../../pages/revenue-intelligence/RevenueIntelligencePage';
import { AIBillingPage } from '../../pages/ai-billing/AIBillingPage';
import { TrialsPage } from '../../pages/subscriptions/TrialsPage';
import { UsageMeteringPage } from '../../pages/usage/UsageMeteringPage';
import { ProrationPage } from '../../pages/proration/ProrationPage';
import { CustomerLifecycleListPage } from '../../pages/customer-lifecycle/CustomerLifecycleListPage';
import { AuthContext, type AuthContextValue } from '../../hooks/useAuth';
import { apiClient } from '../../services/apiClient';
import { UiConfigOverride, type UiSelection } from '../../appUi/UiConfigContext';
import { PAGE_SPECS, type PageConfigs, type PageKey } from '../../appUi/registry';
import { previewAdapter } from './sampleData';
import { isRenderMessage, type RenderMessage, type SelectMessage } from './protocol';

// Installed at module load, before any tenant component can issue a request.
apiClient.defaults.adapter = previewAdapter;

const NOW = '2026-10-01T09:00:00Z';
const notInPreview = async (): Promise<never> => {
  throw new Error('Not available in the visual-editor preview.');
};

/** A fictional signed-in owner, so role-gated UI renders as it does for an organization owner. */
const PREVIEW_AUTH: AuthContextValue = {
  user: {
    id: 'preview-user', email: 'asha@example.com', full_name: 'Asha Sharma', last_login_at: NOW, created_at: NOW,
    two_factor_enabled: false,
  },
  organization: {
    id: 'preview-org', name: 'Acme Traders', slug: 'acme-traders', legal_name: 'Acme Traders Pvt Ltd',
    email: 'billing@example.com', phone: null, website: null, address_line1: null, address_line2: null, city: 'Bengaluru',
    state: 'Karnataka', postal_code: null, country: 'IN', gstin: null, pan: null, default_currency: 'INR',
    timezone: 'Asia/Kolkata', invoice_prefix: 'INV-', invoice_next_number: 1, quote_prefix: 'QT-', quote_next_number: 1,
    payment_prefix: 'PAY-', payment_next_number: 1, subscription_prefix: 'SUB-', subscription_next_number: 1,
    customer_prefix: 'CUS-', customer_next_number: 1, default_payment_terms_days: 15, default_tax_rate_pct: '18',
    discount_approval_threshold_pct: '20', invoice_notes: null, invoice_terms: null, logo_url: null, status: 'active',
    created_at: NOW, updated_at: NOW,
  },
  membership: { id: 'preview-membership', role: 'owner', status: 'active', joined_at: NOW },
  organizations: [{ id: 'preview-org', name: 'Acme Traders', slug: 'acme-traders', role: 'owner' }],
  isAuthenticated: true,
  isLoading: false,
  login: notInPreview,
  completeMfaLogin: notInPreview,
  logout: async () => undefined,
  switchOrganization: notInPreview,
  refreshMe: async () => null,
  applyTokens: notInPreview,
  hasRole: () => true,
};

const ROUTES: Record<string, string> = {
  theme: '/dashboard', navigation: '/dashboard', overview: '/dashboard', customers: '/customers', invoices: '/invoices',
};

function PageBody({ page }: { page: PageKey }): ReactNode {
  switch (page) {
    case 'customers': return <CustomersListPage />;
    case 'invoices': return <InvoicesListPage />;
    case 'quotes': return <QuotesListPage />;
    case 'catalog': return <CatalogPage />;
    case 'plans_pricing': return <PlansPricingPage />;
    case 'subscriptions': return <SubscriptionsListPage />;
    case 'cpq': return <CPQPage />;
    case 'payments': return <PaymentsProvider><PaymentsPage /></PaymentsProvider>;
    case 'reconciliation': return <ReconciliationPage />;
    case 'credit_notes': return <CreditNotesListPage />;
    case 'dunning': return <DunningPage />;
    case 'collections': return <CollectionsDashboardPage />;
    case 'expenses': return <ExpensesProvider><ExpensesPage /></ExpensesProvider>;
    case 'projects': return <ProjectsProvider><ProjectsPage /></ProjectsProvider>;
    case 'timesheets': return <TimesheetsPage />;
    case 'reports': return <ReportsPage />;
    case 'customization': return <CustomizationPage />;
    case 'automation': return <AutomationPage />;
    case 'settings': return <SettingsPage />;
    case 'integrations': return <SettingsPage />;
    case 'activity': return <ActivityPage />;
    case 'action_center': return <ActionCenterPage />;
    case 'approvals': return <ApprovalCenterPage />;
    case 'billing_calendar': return <BillingCalendarPage />;
    case 'audit_log': return <AuditLogPage />;
    case 'data_migration': return <DataMigrationPage />;
    case 'mobile': return <MobilePlatformPage />;
    case 'desktop': return <DesktopPlatformPage />;
    case 'customer_portal': return <CustomerPortalPage />;
    case 'hosted_payment_pages': return <HostedPaymentPagesPage />;
    case 'revenue_intelligence': return <RevenueIntelligencePage />;
    case 'ai_billing': return <AIBillingPage />;
    case 'trials': return <TrialsPage />;
    case 'usage': return <UsageMeteringPage />;
    case 'proration': return <ProrationPage />;
    case 'customer_lifecycle': return <CustomerLifecycleListPage />;
    default: return <DashboardPage />;
  }
}

export function PreviewHost() {
  const [render, setRender] = useState<RenderMessage | null>(null);
  const queryClient = useMemo(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: Infinity } } }),
    []
  );

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== window.parent) return;
      if (isRenderMessage(event.data)) setRender(event.data);
    };
    window.addEventListener('message', onMessage);
    window.parent.postMessage({ type: 'rb-ui-preview:ready' }, window.location.origin);
    return () => window.removeEventListener('message', onMessage);
  }, []);

  const select = useCallback((id: string) => {
    const message: SelectMessage = { type: 'rb-ui-preview:select', id };
    window.parent.postMessage(message, window.location.origin);
  }, []);
  const selection = useMemo<UiSelection>(() => ({ selectedId: render?.selectedId ?? null, select }), [render?.selectedId, select]);

  // Design mode: cancel every interaction; report the configurable component that was clicked.
  const onClickCapture = (event: MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const target = (event.target as HTMLElement).closest('[data-ui-id]');
    const id = target?.getAttribute('data-ui-id');
    if (id) select(id);
  };
  const block = (event: SyntheticEvent) => {
    event.preventDefault();
    event.stopPropagation();
  };

  if (!render) return <div className="p-6 text-sm text-slate-500">Loading preview…</div>;
  const pages: PageConfigs = render.pages;
  return (
    <div onClickCapture={onClickCapture} onSubmitCapture={block} onKeyDownCapture={(e) => e.key === 'Enter' && block(e)}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AuthContext.Provider value={PREVIEW_AUTH}>
            <UiConfigOverride pages={pages} selection={selection}>
              <MemoryRouter initialEntries={[PAGE_SPECS[render.page]?.route || ROUTES[render.page] || '/dashboard']} key={render.page}>
                <div className="flex h-screen bg-slate-50 overflow-hidden font-sans">
                  <Sidebar isOpen={render.page === 'navigation'} onClose={() => undefined} />
                  <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-slate-50">
                    <div className="max-w-7xl mx-auto">
                      <PageBody page={render.page} />
                    </div>
                  </main>
                </div>
              </MemoryRouter>
            </UiConfigOverride>
          </AuthContext.Provider>
        </ToastProvider>
      </QueryClientProvider>
    </div>
  );
}

export default PreviewHost;
