import type { ReactNode } from 'react';
import { Link, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { AlertCircle, ShieldOff } from 'lucide-react';
import { AppLayout } from '../components/layout/AppLayout';
import { Button } from '../components/common/Button';
import { LoadingState } from '../components/common/LoadingState';
import { useAuth } from '../hooks/useAuth';
import type { MemberRole } from '../types/api';
import { ROLE_LABELS } from '../utils/format';

import { ComingSoonPage } from '../pages/ComingSoonPage';
import { DashboardPage } from '../pages/dashboard/DashboardPage';
import {
  LoginPage,
  SignupPage,
  ForgotPasswordPage,
  ResetPasswordPage,
  AcceptInvitationPage,
} from '../pages/auth';
import { CustomersListPage, CustomerFormPage, CustomerDetailPage } from '../pages/customers';
import { CatalogPage } from '../pages/catalog';
import { PlansPricingPage, PricingSimulatorPage } from '../pages/plans-pricing';
import { CPQPage } from '../pages/cpq';
import { QuotesListPage, QuoteFormPage, QuoteDetailPage } from '../pages/quotes';
import {
  SubscriptionsListPage,
  SubscriptionFormPage,
  SubscriptionDetailPage,
  TrialsPage,
} from '../pages/subscriptions';
import { InvoicesListPage, InvoiceFormPage, InvoiceDetailPage } from '../pages/invoices';
import { PaymentsListPage, PaymentDetailPage, PaymentsProvider } from '../pages/payments';
import {
  CollectionsDashboardPage,
  CollectionsInvoiceListPage,
  CollectionsInvoiceDetailPage,
} from '../pages/collections';
import { PayInvoicePage, PublicQuotePage, LandingPage } from '../pages/public';
import { ActivityPage } from '../pages/activity';
import {
  ActionCenterPage,
  ApprovalCenterPage,
  BillingCalendarPage,
  ReconciliationPage,
  AuditLogPage,
  DataMigrationPage,
} from '../pages/control-center';
import { ProjectsPage, ProjectDetailsPage, ProjectsProvider } from '../pages/projects';
import {
  ExpensesPage,
  RecurringExpensesPage,
  ExpenseDetailsPage,
  ExpensesProvider,
} from '../pages/expenses';
import { SettingsPage } from '../pages/settings';
import { ReportsPage } from '../pages/reports';

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
    <ProjectsProvider>
      <ExpensesProvider>
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
              <Route path="quotes/new" element={<QuoteFormPage />} />
              <Route path="quotes/:id" element={<QuoteDetailPage />} />
              <Route path="quotes/:id/edit" element={<QuoteFormPage />} />
              <Route path="invoices" element={<InvoicesListPage />} />
              <Route path="invoices/new" element={<InvoiceFormPage />} />
              <Route path="invoices/:id" element={<InvoiceDetailPage />} />
              <Route path="invoices/:id/edit" element={<InvoiceFormPage />} />
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
              <Route path="expenses" element={<ExpensesPage />} />
              <Route path="expenses/recurring" element={<RecurringExpensesPage />} />
              <Route path="expenses/:expenseId" element={<ExpenseDetailsPage />} />
              <Route path="projects" element={<ProjectsPage />} />
              <Route path="projects/:projectId" element={<ProjectDetailsPage />} />
              <Route path="timesheets" element={<ComingSoonPage />} />

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

              {/* Settings (tabs via ?tab=) */}
              <Route path="settings" element={<SettingsPage />} />

              <Route path="cpq" element={<CPQPage />} />
              <Route path="usage" element={<ComingSoonPage />} />
              <Route path="proration" element={<ComingSoonPage />} />
              <Route path="dunning" element={<ComingSoonPage />} />
              <Route path="customer-lifecycle" element={<ComingSoonPage />} />
              <Route path="customer-portal" element={<ComingSoonPage />} />
              <Route path="hosted-payment-pages" element={<ComingSoonPage />} />
              <Route path="revenue-intelligence" element={<ComingSoonPage />} />
              <Route path="reports" element={<ReportsPage />} />
              <Route path="ai-billing" element={<ComingSoonPage />} />
              <Route path="automation" element={<Navigate to="/settings?tab=automation" replace />} />
              <Route path="customization" element={<Navigate to="/settings?tab=customization" replace />} />
              <Route path="integrations" element={<Navigate to="/settings?tab=integrations" replace />} />
              <Route path="platforms/mobile" element={<ComingSoonPage />} />
              <Route path="platforms/desktop" element={<ComingSoonPage />} />

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
      </ExpensesProvider>
    </ProjectsProvider>
  );
}
