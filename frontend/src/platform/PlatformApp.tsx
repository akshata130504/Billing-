/**
 * The Rooman platform (staff) console. A separate app and bundle from the tenant SPA, served only
 * from the platform origin: it shares no router, auth provider, API client or storage with it.
 */
import type { ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { ShieldOff } from 'lucide-react';
import { EmptyState } from '../components/common/EmptyState';
import { ToastProvider } from '../components/common/Toast';
import { PlatformLoginPage } from './PlatformLoginPage';
import type { PlatformRole } from './platformApi';
import { AccountPage } from './console/AccountPage';
import { AuditPage } from './console/AuditPage';
import { ADMIN, useConsole } from './console/ConsoleContext';
import { ConsoleLayout } from './console/ConsoleLayout';
import { DashboardPage } from './console/DashboardPage';
import { HealthPage } from './console/HealthPage';
import { OrganizationDetailPage } from './console/OrganizationDetailPage';
import { OrganizationsPage } from './console/OrganizationsPage';
import { StaffPage } from './console/StaffPage';
import { WebsitePage } from './console/website/WebsitePage';

/** Hides a page the role cannot use. The server refuses the API calls regardless. */
function RequireRole({ roles, children }: { roles: PlatformRole[]; children: ReactNode }) {
  const { hasRole } = useConsole();
  if (!hasRole(...roles)) {
    return (
      <EmptyState
        icon={<ShieldOff className="h-6 w-6" />}
        title="Not available for your role"
        description="This page is limited to Platform Administrators."
      />
    );
  }
  return <>{children}</>;
}

export function PlatformRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<PlatformLoginPage />} />
      <Route element={<ConsoleLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="organizations" element={<OrganizationsPage />} />
        <Route path="organizations/:organizationId" element={<OrganizationDetailPage />} />
        <Route path="staff" element={<RequireRole roles={[ADMIN]}><StaffPage /></RequireRole>} />
        <Route path="audit" element={<RequireRole roles={[ADMIN]}><AuditPage /></RequireRole>} />
        <Route path="website" element={<RequireRole roles={[ADMIN]}><WebsitePage /></RequireRole>} />
        <Route path="health" element={<HealthPage />} />
        <Route path="account" element={<AccountPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function PlatformApp() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <PlatformRoutes />
      </BrowserRouter>
    </ToastProvider>
  );
}
