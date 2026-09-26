import { Suspense, type ReactNode } from 'react';
import { Link, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { AlertCircle, ShieldOff } from 'lucide-react';
import { AppLayout } from '../components/layout/AppLayout';
import { Button } from '../components/common/Button';
import { LoadingState } from '../components/common/LoadingState';
import { PageLoader } from '../components/common/PageLoader';
import { lazyNamed } from './lazyNamed';
import { useAuth } from '../hooks/useAuth';
import type { MemberRole } from '../types/api';
import { ROLE_LABELS } from '../utils/format';

// Route components are code-split: each page downloads on first visit.
const DashboardPage = lazyNamed(() => import('../pages/dashboard/DashboardPage'), 'DashboardPage');
const LoginPage = lazyNamed(() => import('../pages/auth/LoginPage'), 'LoginPage');
const SignupPage = lazyNamed(() => import('../pages/auth/SignupPage'), 'SignupPage');
const ForgotPasswordPage = lazyNamed(() => import('../pages/auth/ForgotPasswordPage'), 'ForgotPasswordPage');
const ResetPasswordPage = lazyNamed(() => import('../pages/auth/ResetPasswordPage'), 'ResetPasswordPage');
const AcceptInvitationPage = lazyNamed(() => import('../pages/auth/AcceptInvitationPage'), 'AcceptInvitationPage');
const CustomersListPage = lazyNamed(() => import('../pages/customers/CustomersListPage'), 'CustomersListPage');
const CustomerFormPage = lazyNamed(() => import('../pages/customers/CustomerFormPage'), 'CustomerFormPage');
const CustomerDetailPage = lazyNamed(() => import('../pages/customers/CustomerDetailPage'), 'CustomerDetailPage');
const CatalogPage = lazyNamed(() => import('../pages/catalog/CatalogPage'), 'CatalogPage');
const PlansPricingPage = lazyNamed(() => import('../pages/plans-pricing/PlansPricingPage'), 'PlansPricingPage');
const PricingSimulatorPage = lazyNamed(() => import('../pages/plans-pricing/PricingSimulatorPage'), 'PricingSimulatorPage');
const CPQPage = lazyNamed(() => import('../pages/cpq/CPQPage'), 'CPQPage');
const QuotesListPage = lazyNamed(() => import('../pages/quotes/QuotesListPage'), 'QuotesListPage');
const QuoteFormPage = lazyNamed(() => import('../pages/quotes/QuoteFormPage'), 'QuoteFormPage');
const QuoteDetailPage = lazyNamed(() => import('../pages/quotes/QuoteDetailPage'), 'QuoteDetailPage');
const SubscriptionsListPage = lazyNamed(() => import('../pages/subscriptions/SubscriptionsListPage'), 'SubscriptionsListPage');
const SubscriptionFormPage = lazyNamed(() => import('../pages/subscriptions/SubscriptionFormPage'), 'SubscriptionFormPage');
const SubscriptionDetailPage = lazyNamed(() => import('../pages/subscriptions/SubscriptionDetailPage'), 'SubscriptionDetailPage');
const TrialsPage = lazyNamed(() => import('../pages/subscriptions/TrialsPage'), 'TrialsPage');
const InvoicesListPage = lazyNamed(() => import('../pages/invoices/InvoicesListPage'), 'InvoicesListPage');
const InvoiceFormPage = lazyNamed(() => import('../pages/invoices/InvoiceFormPage'), 'InvoiceFormPage');
const InvoiceDetailPage = lazyNamed(() => import('../pages/invoices/InvoiceDetailPage'), 'InvoiceDetailPage');
const CreditNotesListPage = lazyNamed(() => import('../pages/credit-notes/CreditNotesListPage'), 'CreditNotesListPage');
const CreditNoteDetailPage = lazyNamed(() => import('../pages/credit-notes/CreditNoteDetailPage'), 'CreditNoteDetailPage');
const PaymentsListPage = lazyNamed(() => import('../pages/payments/PaymentsPage'), 'PaymentsPage');
const PaymentDetailPage = lazyNamed(() => import('../pages/payments/PaymentDetailsPage'), 'PaymentDetailsPage');
const PaymentsProvider = lazyNamed(() => import('../pages/payments/PaymentsContext'), 'PaymentsProvider');
const CollectionsDashboardPage = lazyNamed(() => import('../pages/collections/CollectionsDashboardPage'), 'CollectionsDashboardPage');
const CollectionsInvoiceListPage = lazyNamed(() => import('../pages/collections/CollectionsInvoiceListPage'), 'CollectionsInvoiceListPage');
const CollectionsInvoiceDetailPage = lazyNamed(() => import('../pages/collections/CollectionsInvoiceDetailPage'), 'CollectionsInvoiceDetailPage');
const PayInvoicePage = lazyNamed(() => import('../pages/public/PayInvoicePage'), 'PayInvoicePage');
const PublicQuotePage = lazyNamed(() => import('../pages/public/PublicQuotePage'), 'PublicQuotePage');
const LandingPage = lazyNamed(() => import('../pages/public/LandingPage'), 'LandingPage');
const PublicCheckoutPage = lazyNamed(() => import('../pages/public/PublicCheckoutPage'), 'PublicCheckoutPage');
const CustomerLifecycleCinematicPage = lazyNamed(() => import('../pages/public/CustomerLifecycleCinematicPage'), 'CustomerLifecycleCinematicPage');
const ActivityPage = lazyNamed(() => import('../pages/activity/ActivityPage'), 'ActivityPage');
const ActionCenterPage = lazyNamed(() => import('../pages/control-center/ActionCenterPage'), 'ActionCenterPage');
const ApprovalCenterPage = lazyNamed(() => import('../pages/control-center/ApprovalCenterPage'), 'ApprovalCenterPage');
const BillingCalendarPage = lazyNamed(() => import('../pages/control-center/BillingCalendarPage'), 'BillingCalendarPage');
const ReconciliationPage = lazyNamed(() => import('../pages/control-center/ReconciliationPage'), 'ReconciliationPage');
const AuditLogPage = lazyNamed(() => import('../pages/control-center/AuditLogPage'), 'AuditLogPage');
const DataMigrationPage = lazyNamed(() => import('../pages/control-center/DataMigrationPage'), 'DataMigrationPage');
const ProjectsPage = lazyNamed(() => import('../pages/projects/ProjectsPage'), 'ProjectsPage');
const ProjectDetailsPage = lazyNamed(() => import('../pages/projects/ProjectDetailsPage'), 'ProjectDetailsPage');
const ProjectsProvider = lazyNamed(() => import('../pages/projects/ProjectsContext'), 'ProjectsProvider');
const ExpensesPage = lazyNamed(() => import('../pages/expenses/ExpensesPage'), 'ExpensesPage');
const RecurringExpensesPage = lazyNamed(() => import('../pages/expenses/RecurringExpensesPage'), 'RecurringExpensesPage');
const ExpenseDetailsPage = lazyNamed(() => import('../pages/expenses/ExpenseDetailsPage'), 'ExpenseDetailsPage');
const ExpensesProvider = lazyNamed(() => import('../pages/expenses/ExpensesContext'), 'ExpensesProvider');
const CustomerLifecycleListPage = lazyNamed(() => import('../pages/customer-lifecycle/CustomerLifecycleListPage'), 'CustomerLifecycleListPage');
const CustomerLifecycleDetailPage = lazyNamed(() => import('../pages/customer-lifecycle/CustomerLifecycleDetailPage'), 'CustomerLifecycleDetailPage');
const TimesheetsPage = lazyNamed(() => import('../pages/timesheets/TimesheetsPage'), 'TimesheetsPage');
const ReportsPage = lazyNamed(() => import('../pages/reports/ReportsPage'), 'ReportsPage');
const SettingsPage = lazyNamed(() => import('../pages/settings/SettingsPage'), 'SettingsPage');
const MobilePlatformPage = lazyNamed(() => import('../pages/platforms/MobilePlatformPage'), 'MobilePlatformPage');
const DesktopPlatformPage = lazyNamed(() => import('../pages/platforms/DesktopPlatformPage'), 'DesktopPlatformPage');
const AIBillingPage = lazyNamed(() => import('../pages/ai-billing/AIBillingPage'), 'AIBillingPage');
const UsageMeteringPage = lazyNamed(() => import('../pages/usage/UsageMeteringPage'), 'UsageMeteringPage');
const ProrationPage = lazyNamed(() => import('../pages/proration/ProrationPage'), 'ProrationPage');
const DunningPage = lazyNamed(() => import('../pages/dunning/DunningPage'), 'DunningPage');
const CustomerPortalPage = lazyNamed(() => import('../pages/customer-portal/CustomerPortalPage'), 'CustomerPortalPage');
const HostedPaymentPagesPage = lazyNamed(() => import('../pages/hosted-payment-pages/HostedPaymentPagesPage'), 'HostedPaymentPagesPage');
const RevenueIntelligencePage = lazyNamed(() => import('../pages/revenue-intelligence/RevenueIntelligencePage'), 'RevenueIntelligencePage');
const AutomationPage = lazyNamed(() => import('../pages/automation/AutomationPage'), 'AutomationPage');
const CustomizationPage = lazyNamed(() => import('../pages/customization/CustomizationPage'), 'CustomizationPage');
const PortalAuthProvider = lazyNamed(() => import('../pages/portal-customer/PortalAuthContext'), 'PortalAuthProvider');
const PortalLayout = lazyNamed(() => import('../pages/portal-customer/PortalLayout'), 'PortalLayout');
const PortalLoginPage = lazyNamed(() => import('../pages/portal-customer/PortalLoginPage'), 'PortalLoginPage');
const PortalDashboardPage = lazyNamed(() => import('../pages/portal-customer/PortalDashboardPage'), 'PortalDashboardPage');
const PortalInvoicesPage = lazyNamed(() => import('../pages/portal-customer/PortalInvoicesPage'), 'PortalInvoicesPage');
const PortalPaymentsPage = lazyNamed(() => import('../pages/portal-customer/PortalPaymentsPage'), 'PortalPaymentsPage');
const PortalSubscriptionsPage = lazyNamed(() => import('../pages/portal-customer/PortalSubscriptionsPage'), 'PortalSubscriptionsPage');
const PortalProfilePage = lazyNamed(() => import('../pages/portal-customer/PortalProfilePage'), 'PortalProfilePage');
const PortalActivationPage = lazyNamed(() => import('../pages/portal-customer/PortalActivationPage'), 'PortalActivationPage');

// ---------------------------------------------------------------------------
// Guards
// ---------------------------------------------------------------------------

/** Redirects unauthenticated users to /login, remembering where they wanted to go. */
export function ProtectedRoute({ children }: { children?: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <LoadingState message="Loading your workspace..." />
      </div>
    );
  }
  if (!isAuthenticated) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: { pathname: location.pathname, search: location.search } }}
      />
    );
  }
  return children ? <>{children}</> : <Outlet />;
}

/** Renders children only when the current member has at least `min` role. */
export function RequireRole({ min, children }: { min: MemberRole; children?: ReactNode }) {
  const { hasRole } = useAuth();
  if (!hasRole(min)) return <AccessDeniedPage min={min} />;
  return children ? <>{children}</> : <Outlet />;
}

function AccessDeniedPage({ min }: { min: MemberRole }) {
  const { membership } = useAuth();
  return (
    <div className="py-16 flex flex-col items-center justify-center text-center">
      <div className="p-3 bg-amber-50 border border-amber-100 rounded-full text-amber-600 mb-3">
        <ShieldOff className="w-8 h-8" />
      </div>
      <h2 className="text-xl font-bold text-slate-900">You do not have access to this page</h2>
      <p className="text-xs text-slate-500 mt-1 max-w-sm">
        This area requires the {ROLE_LABELS[min]} role or higher. Your role in this organization is{' '}
        {membership ? ROLE_LABELS[membership.role] : 'unknown'}.
      </p>
      <div className="mt-4">
        <Link to="/dashboard">
          <Button variant="primary" size="sm">
            Return to Overview
          </Button>
        </Link>
      </div>
    </div>
  );
}

function NotFoundPage() {
  return (
    <div className="py-16 flex flex-col items-center justify-center text-center">
      <div className="p-3 bg-slate-100 rounded-full text-slate-500 mb-3">
        <AlertCircle className="w-8 h-8" />
      </div>
      <h2 className="text-xl font-bold text-slate-900">Page not found</h2>
      <p className="text-xs text-slate-500 mt-1 max-w-sm">The requested URL does not exist.</p>
      <div className="mt-4">
        <Link to="/dashboard">
          <Button variant="primary" size="sm">
            Return to Overview
          </Button>
        </Link>
      </div>
    </div>
  );
}

/** Sends already-authenticated users away from the auth screens. */
function PublicOnly({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <LoadingState message="Checking your session..." />
      </div>
    );
  }
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

export function AppRoutes() {
  return (
    // Top-level fallback for the public/auth/portal routes. Authenticated pages
    // get their own Suspense inside AppLayout so the shell stays visible.
    <Suspense fallback={<PageLoader fullScreen />}>
    <Routes>
      {/* Public: auth */}
      <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
      <Route path="/signup" element={<PublicOnly><SignupPage /></PublicOnly>} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/accept-invitation" element={<AcceptInvitationPage />} />

      {/* Public: landing & hosted pages */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/landing" element={<LandingPage />} />
      <Route path="/pay/:token" element={<PayInvoicePage />} />
      <Route path="/quote/:token" element={<PublicQuotePage />} />
      <Route path="/checkout/:token" element={<PublicCheckoutPage />} />
      <Route path="/lifecycle-cinematic" element={<CustomerLifecycleCinematicPage />} />

      {/* Customer Self-Service Portal */}
      <Route path="/portal/login" element={<PortalLoginPage />} />
      <Route path="/portal/activate" element={<PortalActivationPage />} />
      <Route
        path="/portal"
        element={
          <PortalAuthProvider>
            <PortalLayout />
          </PortalAuthProvider>
        }
      >
        <Route index element={<PortalDashboardPage />} />
        <Route path="invoices" element={<PortalInvoicesPage />} />
        <Route path="payments" element={<PortalPaymentsPage />} />
        <Route path="subscriptions" element={<PortalSubscriptionsPage />} />
        <Route path="profile" element={<PortalProfilePage />} />
      </Route>

      {/* Private */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="dashboard" element={<DashboardPage />} />

              {/* Workspace */}
              <Route path="customers" element={<CustomersListPage />} />
              <Route path="customers/new" element={<CustomerFormPage />} />
              <Route path="customers/:id" element={<CustomerDetailPage />} />
              <Route path="customers/:id/edit" element={<CustomerFormPage />} />
              <Route path="catalog" element={<CatalogPage />} />

              {/* Revenue */}
              <Route path="quotes" element={<QuotesListPage />} />
              <Route path="quotes/new" element={<RequireRole min="finance"><QuoteFormPage /></RequireRole>} />
              <Route path="quotes/:id" element={<QuoteDetailPage />} />
              <Route path="quotes/:id/edit" element={<RequireRole min="finance"><QuoteFormPage /></RequireRole>} />
              <Route path="invoices" element={<InvoicesListPage />} />
              <Route path="invoices/new" element={<RequireRole min="finance"><InvoiceFormPage /></RequireRole>} />
              <Route path="invoices/:id" element={<InvoiceDetailPage />} />
              <Route path="invoices/:id/edit" element={<RequireRole min="finance"><InvoiceFormPage /></RequireRole>} />
              <Route path="credit-notes" element={<CreditNotesListPage />} />
              <Route path="credit-notes/:id" element={<CreditNoteDetailPage />} />
              {/*
                PaymentsProvider loads payments, customers and totals on mount, so it
                is scoped to these routes only. Mounted app-wide it would issue
                authenticated requests from the login and hosted payment pages.
              */}
              <Route path="payments" element={<PaymentsProvider><Outlet /></PaymentsProvider>}>
                <Route index element={<PaymentsListPage />} />
                <Route path=":id" element={<PaymentDetailPage />} />
              </Route>
              <Route path="collections">
                <Route index element={<CollectionsDashboardPage />} />
                <Route path="invoices" element={<CollectionsInvoiceListPage />} />
                <Route path="invoices/:id" element={<CollectionsInvoiceDetailPage />} />
              </Route>

              {/* Subscriptions & Plans */}
              <Route path="plans-pricing" element={<PlansPricingPage />} />
              <Route path="plans-pricing/simulator" element={<PricingSimulatorPage />} />
              <Route path="subscriptions" element={<SubscriptionsListPage />} />
              <Route path="subscriptions/new" element={<SubscriptionFormPage />} />
              <Route path="subscriptions/:id" element={<SubscriptionDetailPage />} />
              <Route path="trials" element={<TrialsPage />} />

              {/* Operations */}
              {/*
                Like PaymentsProvider, these providers fetch on mount, so they are
                scoped to their own routes instead of wrapping the whole layout.
              */}
              <Route path="expenses" element={<ExpensesProvider><Outlet /></ExpensesProvider>}>
                <Route index element={<ExpensesPage />} />
                <Route path="recurring" element={<RecurringExpensesPage />} />
                <Route path=":expenseId" element={<ExpenseDetailsPage />} />
              </Route>
              <Route path="projects" element={<ProjectsProvider><Outlet /></ProjectsProvider>}>
                <Route index element={<ProjectsPage />} />
                <Route path=":projectId" element={<ProjectDetailsPage />} />
              </Route>
              <Route path="timesheets" element={<TimesheetsPage />} />

              {/* Insights */}
              <Route path="activity" element={<ActivityPage />} />

              {/* Control center */}
              <Route path="control-center/action-center" element={<ActionCenterPage />} />
              <Route path="control-center/approvals" element={<ApprovalCenterPage />} />
              <Route path="control-center/calendar" element={<BillingCalendarPage />} />
              <Route path="control-center/reconciliation" element={<ReconciliationPage />} />
              <Route
                path="control-center/audit-log"
                element={
                  <RequireRole min="admin">
                    <AuditLogPage />
                  </RequireRole>
                }
              />
              <Route path="control-center/migration" element={<DataMigrationPage />} />

              {/* Settings (tabs via path or ?tab=) */}
              <Route path="settings" element={<SettingsPage />} />
              <Route path="settings/:section" element={<SettingsPage />} />

              <Route path="cpq" element={<CPQPage />} />
              <Route path="usage" element={<UsageMeteringPage />} />
              <Route path="proration" element={<ProrationPage />} />
              <Route path="dunning" element={<DunningPage />} />
              <Route path="customer-lifecycle" element={<CustomerLifecycleListPage />} />
              <Route path="customer-lifecycle/:customerId" element={<CustomerLifecycleDetailPage />} />
              <Route path="customer-portal" element={<CustomerPortalPage />} />
              <Route path="hosted-payment-pages" element={<HostedPaymentPagesPage />} />
              <Route path="revenue-intelligence" element={<RevenueIntelligencePage />} />
              <Route path="reports" element={<ReportsPage />} />
              <Route path="ai-billing" element={<AIBillingPage />} />
              <Route path="automation" element={<AutomationPage />} />
              <Route path="customization" element={<CustomizationPage />} />
              <Route path="integrations" element={<Navigate to="/settings?tab=integrations" replace />} />
              <Route path="platforms/mobile" element={<MobilePlatformPage />} />
              <Route path="platforms/desktop" element={<DesktopPlatformPage />} />

              {/* Legacy / alternate path redirects */}
              <Route path="system/settings" element={<Navigate to="/settings" replace />} />
              <Route path="revenue/quotes" element={<Navigate to="/quotes" replace />} />
              <Route path="revenue/cpq" element={<Navigate to="/cpq" replace />} />
              <Route path="revenue/invoices" element={<Navigate to="/invoices" replace />} />
              <Route path="revenue/payments" element={<Navigate to="/payments" replace />} />
              <Route path="revenue/collections" element={<Navigate to="/collections" replace />} />
              <Route path="subscriptions/plans" element={<Navigate to="/catalog" replace />} />
              <Route path="subscriptions/all" element={<Navigate to="/subscriptions" replace />} />
              <Route path="subscriptions/trials" element={<Navigate to="/trials" replace />} />
              <Route path="subscriptions/usage" element={<Navigate to="/usage" replace />} />
              <Route path="subscriptions/proration" element={<Navigate to="/proration" replace />} />
              <Route path="subscriptions/dunning" element={<Navigate to="/dunning" replace />} />
              <Route path="operations/expenses" element={<Navigate to="/expenses" replace />} />
              <Route path="operations/expenses/recurring" element={<Navigate to="/expenses/recurring" replace />} />
              <Route path="operations/projects" element={<Navigate to="/projects" replace />} />
              <Route path="operations/timesheets" element={<Navigate to="/timesheets" replace />} />
              <Route path="insights/revenue" element={<Navigate to="/revenue-intelligence" replace />} />
              <Route path="insights/reports" element={<Navigate to="/reports" replace />} />
              <Route path="insights/activity" element={<Navigate to="/activity" replace />} />
              <Route path="insights/ai" element={<Navigate to="/ai-billing" replace />} />
              <Route path="system/automation" element={<Navigate to="/automation" replace />} />
              <Route path="system/customization" element={<Navigate to="/customization" replace />} />
              <Route path="system/integrations" element={<Navigate to="/integrations" replace />} />

              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
        </Routes>
    </Suspense>
  );
}
