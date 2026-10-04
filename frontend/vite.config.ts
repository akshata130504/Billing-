/// <reference types="vitest/config" />
import { defineConfig, type Connect, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// One website, one origin, one build with two entry documents:
//   index.html       the tenant app (/admin, /login, /dashboard, ... and the public pages)
//   superadmin.html  the platform (Rooman staff) console, every route under /superadmin
// In production nginx serves superadmin.html for /superadmin and /superadmin/* (with the stricter
// console headers, see docker/nginx.conf). The dev and preview servers do the same here.
export const SUPERADMIN_PATH = '/superadmin';

export function isSuperadminDocument(pathname: string): boolean {
  if (pathname !== SUPERADMIN_PATH && !pathname.startsWith(`${SUPERADMIN_PATH}/`)) return false;
  // Files (Vite modules, assets) are served as they are; only page routes get the console document.
  return !path.extname(pathname);
}

function superadminEntry(): Plugin {
  const rewrite: Connect.NextHandleFunction = (req, _res, next) => {
    const [pathname, query] = (req.url || '/').split('?');
    if (isSuperadminDocument(pathname)) req.url = `/superadmin.html${query ? `?${query}` : ''}`;
    next();
  };
  return {
    name: 'superadmin-entry',
    configureServer(server) {
      server.middlewares.use(rewrite);
    },
    configurePreviewServer(server) {
      server.middlewares.use(rewrite);
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), superadminEntry()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),
        superadmin: path.resolve(__dirname, 'superadmin.html'),
      },
      output: {
        // Long-lived vendor chunks: these change far less often than app code,
        // so browsers keep them cached across deploys.
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-query': ['@tanstack/react-query'],
          'vendor-icons': ['lucide-react'],
        },
      },
    },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    css: false,
    restoreMocks: true,
  },
});
