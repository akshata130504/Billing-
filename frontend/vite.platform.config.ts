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
import fs from 'fs';
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
  // Uploaded website media (read-only) for the landing-page preview.
  '/uploads/website': {
    target: process.env.PLATFORM_API_PROXY || 'http://localhost:8000',
    changeOrigin: false,
  },
};

// The landing-page preview needs the brand logos and bundled hero videos. Ship exactly those
// files (never the rest of the tenant's public/ folder) in the platform bundle.
const SHARED_PUBLIC = path.resolve(__dirname, 'public');
function sharedMediaFiles(): string[] {
  const logos = ['rooman-shield-logo.png', 'rooman-full-logo.png', 'rooman-billing-logo.png'].map((f) => `logos/${f}`);
  const videosDir = path.join(SHARED_PUBLIC, 'videos');
  const videos = fs.existsSync(videosDir)
    ? fs.readdirSync(videosDir).filter((f) => f.toLowerCase().endsWith('.mp4')).map((f) => `videos/${f}`)
    : [];
  return [...logos, ...videos].filter((f) => fs.existsSync(path.join(SHARED_PUBLIC, f)));
}

function sharedMedia(): Plugin {
  const files = new Set(sharedMediaFiles());
  const serve: Connect.NextHandleFunction = (req, res, next) => {
    const rel = decodeURIComponent((req.url || '').split('?')[0]).replace(/^\//, '');
    if (!files.has(rel)) return next();
    res.setHeader('Content-Type', rel.endsWith('.png') ? 'image/png' : 'video/mp4');
    fs.createReadStream(path.join(SHARED_PUBLIC, rel)).pipe(res);
  };
  return {
    name: 'platform-shared-media',
    configureServer(server) {
      server.middlewares.use(serve);
    },
    configurePreviewServer(server) {
      server.middlewares.use(serve);
    },
    generateBundle() {
      for (const rel of files) {
        this.emitFile({ type: 'asset', fileName: rel, source: fs.readFileSync(path.join(SHARED_PUBLIC, rel)) });
      }
    },
  };
}

// The dev/preview server must never hand out the tenant app: no SPA fallback to index.html
// (appType 'mpa' below), every page route serves the platform entry, and any API path other than
// the proxied platform API is a 404 on this origin.
function platformEntry(): Plugin {
  const rewrite: Connect.NextHandleFunction = (req, res, next) => {
    const url = req.url || '/';
    const pathname = url.split('?')[0];
    if (pathname.startsWith('/api/v1/platform/') || pathname.startsWith('/uploads/website/')) return next();
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
  cacheDir: 'node_modules/.vite-platform',
  appType: 'mpa',
  plugins: [react(), sharedMedia(), platformEntry()],
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
