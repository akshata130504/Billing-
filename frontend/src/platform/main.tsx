import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { PlatformApp } from './PlatformApp';
import { PREVIEW_PATH } from './uiPreview/protocol';
import '../index.css';

// The visual editor's preview frame renders tenant pages with sample data; it is a separate,
// lazily loaded entry so the console itself does not ship the tenant application.
const PreviewHost = lazy(() => import('./uiPreview/PreviewHost'));
const isPreview = window.location.pathname === PREVIEW_PATH && window.parent !== window;

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    {isPreview ? (
      <Suspense fallback={null}>
        <PreviewHost />
      </Suspense>
    ) : (
      <PlatformApp />
    )}
  </React.StrictMode>
);
