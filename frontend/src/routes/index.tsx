import { Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from '../components/layout/AppLayout';
import { DashboardPage } from '../pages/dashboard/DashboardPage';
import { PlaceholderPage } from '../pages/PlaceholderPage';
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
import { Button } from '../components/common/Button';
import { Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';

function NotFoundPage() {
  return (
    <div className="py-16 flex flex-col items-center justify-center text-center">
      <div className="p-3 bg-slate-100 rounded-full text-slate-500 mb-3">
        <AlertCircle className="w-8 h-8" />
      </div>
      <h2 className="text-xl font-bold text-slate-900">Page Not Found</h2>
      <p className="text-xs text-slate-500 mt-1 max-w-sm">
        The requested URL was not found in the Rooman Billing workspace.
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

export function AppRoutes() {
  return (
    <ProjectsProvider>
      <ExpensesProvider>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardPage />} />

        {/* WORKSPACE */}
        <Route path="customers" element={<PlaceholderPage />} />
        <Route path="catalog" element={<PlaceholderPage />} />

        {/* REVENUE */}
        <Route path="quotes" element={<PlaceholderPage />} />
        <Route path="cpq" element={<PlaceholderPage />} />
        <Route path="invoices" element={<PlaceholderPage />} />
        <Route path="payments" element={<PlaceholderPage />} />
        <Route path="collections" element={<PlaceholderPage />} />

        {/* SUBSCRIPTIONS */}
        <Route path="plans-pricing" element={<PlaceholderPage />} />
        <Route path="subscriptions" element={<PlaceholderPage />} />
        <Route path="trials" element={<PlaceholderPage />} />
        <Route path="usage" element={<PlaceholderPage />} />
        <Route path="proration" element={<PlaceholderPage />} />
        <Route path="dunning" element={<PlaceholderPage />} />

        {/* CUSTOMER EXPERIENCE */}
        <Route path="customer-lifecycle" element={<PlaceholderPage />} />
        <Route path="customer-portal" element={<PlaceholderPage />} />
        <Route path="hosted-payment-pages" element={<PlaceholderPage />} />

        {/* OPERATIONS */}
        <Route path="expenses" element={<ExpensesPage />} />
        <Route path="expenses/recurring" element={<RecurringExpensesPage />} />
        <Route path="expenses/:expenseId" element={<ExpenseDetailsPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectDetailsPage />} />
        <Route path="timesheets" element={<PlaceholderPage />} />

        {/* INSIGHTS */}
        <Route path="revenue-intelligence" element={<PlaceholderPage />} />
        <Route path="reports" element={<PlaceholderPage />} />
        <Route path="ai-billing" element={<PlaceholderPage />} />
        <Route path="activity" element={<PlaceholderPage />} />

        {/* PLATFORMS */}
        <Route path="platforms/mobile" element={<PlaceholderPage />} />
        <Route path="platforms/desktop" element={<PlaceholderPage />} />

        {/* CONTROL CENTER (Dedicated Pages) */}
        <Route path="control-center/action-center" element={<ActionCenterPage />} />
        <Route path="control-center/approvals" element={<ApprovalCenterPage />} />
        <Route path="control-center/calendar" element={<BillingCalendarPage />} />
        <Route path="control-center/reconciliation" element={<ReconciliationPage />} />
        <Route path="control-center/audit-log" element={<AuditLogPage />} />
        <Route path="control-center/migration" element={<DataMigrationPage />} />

        {/* SYSTEM */}
        <Route path="automation" element={<PlaceholderPage />} />
        <Route path="customization" element={<PlaceholderPage />} />
        <Route path="integrations" element={<PlaceholderPage />} />
        <Route path="system/settings" element={<PlaceholderPage />} />

        {/* Legacy / Alternate Path Compatibility Redirects */}
        <Route path="revenue/quotes" element={<Navigate to="/quotes" replace />} />
        <Route path="revenue/cpq" element={<Navigate to="/cpq" replace />} />
        <Route path="revenue/invoices" element={<Navigate to="/invoices" replace />} />
        <Route path="revenue/payments" element={<Navigate to="/payments" replace />} />
        <Route path="revenue/collections" element={<Navigate to="/collections" replace />} />
        <Route path="subscriptions/plans" element={<Navigate to="/plans-pricing" replace />} />
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

        {/* Catch-all 404 */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
      </ExpensesProvider>
    </ProjectsProvider>
  );
}
