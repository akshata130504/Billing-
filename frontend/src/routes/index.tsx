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
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />

        {/* WORKSPACE */}
        <Route path="customers" element={<PlaceholderPage />} />
        <Route path="catalog" element={<PlaceholderPage />} />

        {/* REVENUE */}
        <Route path="revenue/quotes" element={<PlaceholderPage />} />
        <Route path="revenue/cpq" element={<PlaceholderPage />} />
        <Route path="revenue/invoices" element={<PlaceholderPage />} />
        <Route path="revenue/payments" element={<PlaceholderPage />} />
        <Route path="revenue/collections" element={<PlaceholderPage />} />

        {/* SUBSCRIPTIONS */}
        <Route path="subscriptions/plans" element={<PlaceholderPage />} />
        <Route path="subscriptions/all" element={<PlaceholderPage />} />
        <Route path="subscriptions/trials" element={<PlaceholderPage />} />
        <Route path="subscriptions/usage" element={<PlaceholderPage />} />
        <Route path="subscriptions/proration" element={<PlaceholderPage />} />
        <Route path="subscriptions/dunning" element={<PlaceholderPage />} />

        {/* CUSTOMER EXPERIENCE */}
        <Route path="customer-experience/lifecycle" element={<PlaceholderPage />} />
        <Route path="customer-experience/portal" element={<PlaceholderPage />} />
        <Route path="customer-experience/payment-pages" element={<PlaceholderPage />} />

        {/* OPERATIONS */}
        <Route path="operations/expenses" element={<PlaceholderPage />} />
        <Route path="operations/projects" element={<PlaceholderPage />} />
        <Route path="operations/timesheets" element={<PlaceholderPage />} />

        {/* INSIGHTS */}
        <Route path="insights/revenue" element={<PlaceholderPage />} />
        <Route path="insights/reports" element={<PlaceholderPage />} />
        <Route path="insights/ai" element={<PlaceholderPage />} />
        <Route path="insights/activity" element={<PlaceholderPage />} />

        {/* PLATFORMS */}
        <Route path="platforms/mobile" element={<PlaceholderPage />} />
        <Route path="platforms/desktop" element={<PlaceholderPage />} />

        {/* CONTROL CENTER */}
        <Route path="control-center/action-center" element={<ActionCenterPage />} />
        <Route path="control-center/approvals" element={<ApprovalCenterPage />} />
        <Route path="control-center/calendar" element={<BillingCalendarPage />} />
        <Route path="control-center/reconciliation" element={<ReconciliationPage />} />
        <Route path="control-center/audit-log" element={<AuditLogPage />} />
        <Route path="control-center/migration" element={<DataMigrationPage />} />

        {/* SYSTEM */}
        <Route path="system/automation" element={<PlaceholderPage />} />
        <Route path="system/customization" element={<PlaceholderPage />} />
        <Route path="system/integrations" element={<PlaceholderPage />} />
        <Route path="system/settings" element={<PlaceholderPage />} />

        {/* Catch-all 404 */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
