/**
 * The Rooman platform (staff) console. A separate app and bundle from the tenant SPA, served only
 * from the platform origin: it shares no router, auth provider, API client or storage with it.
 */
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { PlatformHomePage } from './PlatformHomePage';
import { PlatformLoginPage } from './PlatformLoginPage';

export function PlatformRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<PlatformLoginPage />} />
      <Route path="/" element={<PlatformHomePage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function PlatformApp() {
  return (
    <BrowserRouter>
      <PlatformRoutes />
    </BrowserRouter>
  );
}
