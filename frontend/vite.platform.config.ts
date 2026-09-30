/// <reference types="node" />
/**
 * Build/dev config for the Rooman platform (staff) console - a separate bundle served from its own
 * origin (PLATFORM_APP_ORIGIN), never from the tenant app. See docs/platform-console-deployment.md.
 *
 *   npm run dev:platform     -> http://platform.localhost:5174 (start the backend with
 *                               PLATFORM_APP_ORIGIN=http://platform.localhost:5174)
 *   npm run build:platform   -> dist-platform/
 *
 * Only /api/v1/platform is proxied, and the Host header is kept (changeOrigin: false) because the
 * API answers platform requests only on the platform host.
 */
import { defineConfig, type Connect, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// Browsers resolve *.localhost to loopback; the server binds to loopback and only answers requests
// whose Host is the platform host (allowedHosts).
const PLATFORM_HOST = 'platform.localhost';
const PLATFORM_PORT = 5174;
const BIND = '127.0.0.1';
// PLATFORM_API_PROXY: where the local backend listens (default http://localhost:8000).
const platformProxy = {
  '/api/v1/platform': {
    target: process.env.PLATFORM_API_PROXY || 'http://localhost:8000',
    changeOrigin: false,
  },
};

// The dev/preview server must never hand out the tenant app: no SPA fallback to index.html
// (appType 'mpa' below), every page route serves the platform entry, and any API path other than
// the proxied platform API is a 404 on this origin.
function platformEntry(): Plugin {
  const rewrite: Connect.NextHandleFunction = (req, res, next) => {
    const url = req.url || '/';
    const pathname = url.split('?')[0];
    if (pathname.startsWith('/api/v1/platform/')) return next();
    if (pathname.startsWith('/api/') || pathname.startsWith('/uploads/') || pathname === '/index.html') {
      res.statusCode = 404;
      res.end('Not found');
      return;
    }
    if (!pathname.startsWith('/@') && !path.extname(pathname)) req.url = '/platform.html';
    next();
  };
  return {
    name: 'platform-entry',
    configureServer(server) {
      server.middlewares.use(rewrite);
    },
    configurePreviewServer(server) {
      server.middlewares.use(rewrite);
    },
  };
}

export default defineConfig({
  appType: 'mpa',
  plugins: [react(), platformEntry()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // public/ holds tenant assets (videos, logos, theme script); none of it belongs on this origin.
  publicDir: false,
  build: {
    outDir: 'dist-platform',
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, 'platform.html'),
    },
  },
  server: {
    host: BIND,
    port: PLATFORM_PORT,
    strictPort: true,
    allowedHosts: [PLATFORM_HOST],
    proxy: platformProxy,
  },
  preview: {
    host: BIND,
    port: PLATFORM_PORT,
    strictPort: true,
    allowedHosts: [PLATFORM_HOST],
    proxy: platformProxy,
  },
});
