import { Suspense, type ReactNode } from 'react';
import { Link, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { AlertCircle, ShieldOff } from 'lucide-react';
import { AppLayout } from '../components/layout/AppLayout';
import { PLANS_ROUTE } from '../components/layout/TrialBanner';
import { Button } from '../components/common/Button';
import { LoadingState } from '../components/common/LoadingState';
import { PageLoader } from '../components/common/PageLoader';
import { lazyNamed } from './lazyNamed';
import { useAuth } from '../hooks/useAuth';
import type { MemberRole } from '../types/api';
import { ROLE_LABELS } from '../utils/format';
import { postLoginRedirect } from '../utils/redirect';

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
// Rooman platform staff under an approved access grant (token handed over by the platform console).
const PlatformAccessWorkspace = lazyNamed(() => import('../pages/platformAccess/PlatformAccessWorkspace'), 'PlatformAccessWorkspace');
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
const SubscriptionRequestPage = lazyNamed(() => import('../pages/subscription-access/SubscriptionRequestPage'), 'SubscriptionRequestPage');
const TrialExpiredScreen = lazyNamed(() => import('../pages/subscription-access/SubscriptionRequestPage'), 'TrialExpiredScreen');

// ---------------------------------------------------------------------------
// Guards
// ---------------------------------------------------------------------------

/** Redirects unauthenticated users to /login, remembering where they wanted to go.
 *
 * Also applies the organization lifecycle policy (docs/platform-administration-design.md §8),
 * mirroring backend/app/api/deps.py `_check_org_active`:
 * - rejected / deleted: a status screen only.
 * - suspended: Owner and Admin keep read-only access under a banner; Finance and Viewer get a screen.
 * - pending_deletion: the Owner keeps read-only access under a banner; everyone else gets a screen.
 * - trial: everything, under a banner counting down to trial_ends_at.
 * - trial_expired: the subscription request screen only (the API allows nothing else).
 * The status is the server's effective one (/auth/me `access.status`), so a trial that ended
 * since the last scheduler run already shows as ended.
 */
export function ProtectedRoute({ children }: { children?: ReactNode }) {
  const { isAuthenticated, isLoading, organization, access, logout, hasRole } = useAuth();
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

  const content = children ? <>{children}</> : <Outlet />;
  const onLogout = () => void logout();

  if (!organization) return content;
  switch (access?.status ?? organization.status) {
    case 'trial_expired':
      return (
        <Suspense fallback={<PageLoader fullScreen />}>
          <TrialExpiredScreen organizationName={organization.name} onLogout={onLogout} />
        </Suspense>
      );
    case 'trial':
      return content; // AppLayout shows the trial banner
    case 'rejected':
      return <OrgRejectedScreen organization={organization} onLogout={onLogout} />;
    case 'suspended':
      if (hasRole('admin')) {
        return (
          <>
            <OrgReadOnlyBanner
              title="Your organization is suspended"
              message="Your workspace is read-only until Rooman Billing reactivates it. No charges, renewals or reminder emails run while suspended."
              reason={organization.status_reason}
            />
            {content}
          </>
        );
      }
      return (
        <OrgLockedScreen
          title="Organization Suspended"
          message={`${organization.name} has been suspended by Rooman Billing administration. Contact your organization Owner.`}
          onLogout={onLogout}
        />
      );
    case 'pending_deletion':
      if (hasRole('owner')) {
        return (
          <>
            <OrgReadOnlyBanner
              title="Your organization is scheduled for deletion"
              message="Your workspace is read-only. You can still view and export your data."
              reason={organization.status_reason}
            />
            {content}
          </>
        );
      }
      return (
        <OrgLockedScreen
          title="Organization Scheduled for Deletion"
          message={`${organization.name} is scheduled for deletion. Contact your organization Owner.`}
          onLogout={onLogout}
        />
      );
    case 'deleted':
      return <OrgLockedScreen title="Organization Closed" message={`${organization.name} is no longer active.`} onLogout={onLogout} />;
    default:
      return content;
  }
}

/**
 * /subscription is the old request-and-approve page. Plans now live at /settings/subscription; only an
 * organization still on the legacy module trial (access.module_access === 'trial') keeps the request page,
 * because that is the flow its trial was granted through.
 */
export function LegacySubscriptionRoute() {
  const { access } = useAuth();
  if (access?.module_access === 'trial') return <SubscriptionRequestPage />;
  return <Navigate to={PLANS_ROUTE} replace />;
}

/** Lets a user who belongs to other organizations leave a locked one without signing out. */
function OtherOrganizations() {
  const { organization, organizations, switchOrganization } = useAuth();
  const others = organizations.filter((o) => o.id !== organization?.id);
  if (others.length === 0) return null;
  return (
    <div className="mt-6 border-t border-slate-200 pt-4 text-left">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Switch to another organization</p>
      <div className="mt-2 flex flex-col gap-2">
        {others.map((o) => (
          <Button key={o.id} variant="outline" className="w-full justify-start" onClick={() => void switchOrganization(o.id)}>
            {o.name}
          </Button>
        ))}
      </div>
    </div>
  );
}

function OrgReadOnlyBanner({ title, message, reason }: { title: string; message: string; reason?: string | null }) {
  return (
    <div role="status" className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
      <div className="mx-auto flex max-w-7xl items-start gap-2">
        <ShieldOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>
          <span className="font-semibold">{title}.</span> {message}
          {reason ? <span className="block text-amber-800">Reason: {reason}</span> : null}
        </p>
      </div>
    </div>
  );
}

function OrgRejectedScreen({
  organization,
  onLogout,
}: {
  organization: { name: string; status_reason?: string | null };
  onLogout: () => void;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-2xl border border-rose-200 bg-white p-8 shadow-sm text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-rose-50 text-rose-600 border border-rose-200">
          <ShieldOff className="h-7 w-7" />
        </div>
        <h1 className="text-xl font-bold text-slate-900">Registration Not Approved</h1>
        <p className="mt-2 text-sm text-slate-600">
          Your organization registration for <span className="font-semibold text-slate-800">{organization.name}</span> was rejected by Rooman Billing.
        </p>
        {organization.status_reason && (
          <div className="mt-4 rounded-lg bg-rose-50 border border-rose-200 p-3 text-left">
            <p className="text-xs font-semibold text-rose-800 uppercase tracking-wide">Reason Provided</p>
            <p className="mt-1 text-sm text-rose-900">{organization.status_reason}</p>
          </div>
        )}
        <div className="mt-6">
          <Button variant="outline" className="w-full" onClick={onLogout}>
            Sign Out
          </Button>
        </div>
        <OtherOrganizations />
      </div>
    </div>
  );
}

function OrgLockedScreen({ title, message, onLogout }: { title: string; message: string; onLogout: () => void }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-amber-50 text-amber-600 border border-amber-200">
          <ShieldOff className="h-7 w-7" />
        </div>
        <h1 className="text-xl font-bold text-slate-900">{title}</h1>
        <p className="mt-2 text-sm text-slate-600">{message}</p>
        <div className="mt-6">
          <Button variant="outline" className="w-full" onClick={onLogout}>
            Sign Out
          </Button>
        </div>
        <OtherOrganizations />
      </div>
    </div>
  );
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
  const location = useLocation();
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <LoadingState message="Checking your session..." />
      </div>
    );
  }
  // Signing in flips isAuthenticated before LoginPage can navigate, so this redirect decides
  // where the user lands: honour the page ProtectedRoute sent them away from.
  if (isAuthenticated) return <Navigate to={postLoginRedirect(location.state)} replace />;
  return <>{children}</>;
}

/**
 * /admin/<page> is the same tenant page as /<page>: one app and one route table, so a bookmarked
 * or shared /admin/... link lands on the right screen (signed-out users go through sign-in first).
 */
function AdminAlias() {
  const location = useLocation();
  const rest = location.pathname.replace(/^\/admin\/?/, '');
  return (
    <Navigate
      to={{ pathname: rest ? `/${rest}` : '/admin', search: location.search, hash: location.hash }}
      state={location.state}
      replace
    />
  );
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
      {/* Single-origin entry points. /admin is the tenant (organization) app's sign-in, and goes
          straight to the workspace when already signed in. /superadmin is NOT a route of this
          app: it is the separate platform console document (superadmin.html) on the same origin,
          with its own staff sign-in and mandatory 2FA. */}
      <Route path="/admin" element={<PublicOnly><LoginPage /></PublicOnly>} />
      <Route path="/admin/*" element={<AdminAlias />} />
      <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
      <Route path="/signup" element={<PublicOnly><SignupPage /></PublicOnly>} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/accept-invitation" element={<AcceptInvitationPage />} />

      {/* Public: landing & hosted pages */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/landing" element={<LandingPage />} />
      <Route path="/platform-access" element={<PlatformAccessWorkspace />} />
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
              <Route path="subscription" element={<LegacySubscriptionRoute />} />
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
