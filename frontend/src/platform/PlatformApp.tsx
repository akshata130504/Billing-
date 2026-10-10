/**
 * The Rooman platform (staff) console, served at /superadmin on the same origin as the tenant app
 * (/admin). It is a separate entry point (superadmin.html -> platform/main.tsx) of the same build:
 * it shares no router, auth provider, API client or storage with the tenant SPA.
 */
import { useEffect, useRef, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { ShieldOff } from 'lucide-react';
import { EmptyState } from '../components/common/EmptyState';
import { ToastProvider } from '../components/common/Toast';
import { PlatformLoginPage } from './PlatformLoginPage';
import { setPlatformSessionExpiredHandler, type PlatformRole } from './platformApi';
import { AccessGrantsPage } from './console/AccessGrantsPage';
import { AccountPage } from './console/AccountPage';
import { AuditPage } from './console/AuditPage';
import { ADMIN, useConsole } from './console/ConsoleContext';
const SUPPORT: PlatformRole = 'platform_support';
import { ConsoleLayout } from './console/ConsoleLayout';
import { DashboardPage } from './console/DashboardPage';
import { HealthPage } from './console/HealthPage';
import { OrganizationDetailPage } from './console/OrganizationDetailPage';
import { SubscriptionRequestsPage } from './console/SubscriptionRequestsPage';
import { OrganizationsPage } from './console/OrganizationsPage';
import { StaffPage } from './console/StaffPage';
import { WebsitePage } from './console/website/WebsitePage';
import { VisualEditorPage } from './console/app-ui/VisualEditorPage';

/** Hides a page the role cannot use. The server refuses the API calls regardless. */
function RequireRole({ roles, children }: { roles: PlatformRole[]; children: ReactNode }) {
  const { hasRole } = useConsole();
  if (!hasRole(...roles)) {
    return (
      <EmptyState
        icon={<ShieldOff className="h-6 w-6" />}
        title="Not available for your role"
        description="Your platform role does not include this page."
      />
    );
  }
  return <>{children}</>;
}

/** When the platform session has expired, go to sign-in and come back here afterwards. */
function SessionExpiryRedirect() {
  const navigate = useNavigate();
  const location = useLocation();
  const here = useRef(location);
  here.current = location;
  useEffect(
    () =>
      setPlatformSessionExpiredHandler(() => {
        const { pathname, search } = here.current;
        if (pathname === '/login') return;
        navigate(`/login?expired=1&next=${encodeURIComponent(pathname + search)}`, { replace: true });
      }),
    [navigate]
  );
  return null;
}

export function PlatformRoutes() {
  return (
    <>
    <SessionExpiryRedirect />
    <Routes>
      <Route path="/login" element={<PlatformLoginPage />} />
      <Route element={<ConsoleLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="organizations" element={<OrganizationsPage />} />
        <Route path="organizations/:organizationId" element={<OrganizationDetailPage />} />
        <Route path="subscription-requests" element={<SubscriptionRequestsPage />} />
        <Route path="staff" element={<RequireRole roles={[ADMIN]}><StaffPage /></RequireRole>} />
        <Route path="audit" element={<RequireRole roles={[ADMIN]}><AuditPage /></RequireRole>} />
        <Route path="website" element={<RequireRole roles={[ADMIN]}><WebsitePage /></RequireRole>} />
        <Route path="visual-editor" element={<VisualEditorPage />} />
        <Route path="access-grants" element={<RequireRole roles={[ADMIN, SUPPORT]}><AccessGrantsPage /></RequireRole>} />
        <Route path="health" element={<HealthPage />} />
        <Route path="account" element={<AccountPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  );
}

/** Every console route lives under this path (e.g. /superadmin/organizations). */
export const SUPERADMIN_BASE = '/superadmin';

export function PlatformApp() {
  return (
    <ToastProvider>
      <BrowserRouter basename={SUPERADMIN_BASE}>
        <PlatformRoutes />
      </BrowserRouter>
    </ToastProvider>
  );
}
