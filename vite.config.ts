import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {loadEnv} from 'vite';
import {defineConfig} from 'vitest/config';
import { VitePWA } from 'vite-plugin-pwa';

import {PWA_NAVIGATION_DENYLIST} from './src/lib/pwaNavigation';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendTarget = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000';
  const frontendErrorDsn = env.VITE_FRONTEND_GLITCHTIP_DSN || '';
  const manualChunks = (id: string) => {
    if (!id.includes('node_modules')) {
      return undefined;
    }
    if (id.includes('recharts') || id.includes('d3-') || id.includes('victory-vendor')) {
      return 'charts';
    }
    if (id.includes('lucide-react') || id.includes('motion') || id.includes('framer-motion')) {
      return 'ui';
    }
    return 'vendor';
  };

  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        registerType: 'autoUpdate',
        manifest: {
          name: 'UniHub Retail',
          short_name: 'UniHub Retail',
          description: 'Platforma Mobiup pentru management vanzari si agenti',
          lang: 'ro',
          theme_color: '#062B57',
          background_color: '#ffffff',
          display: 'standalone',
          icons: [
            {
              src: 'pwa-192x192.png',
              sizes: '192x192',
              type: 'image/png',
              purpose: 'any',
            },
            {
              src: 'pwa-512x512.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'any',
            },
            {
              src: 'apple-touch-icon.png',
              sizes: '180x180',
              type: 'image/png',
              purpose: 'any',
            },
          ],
        },
        workbox: {
          // Precache only the shell. Feature chunks (notably charts) are
          // fetched on demand and then retained by the runtime cache.
          globPatterns: [
            '**/*.{html,ico,png,svg,woff2}',
            'assets/index-*.{js,css}',
            'assets/vendor-*.js',
            'assets/ui-*.js',
          ],
          // Server-owned navigations must reach FastAPI. Falling back to the
          // cached SPA for /auth/session/login creates an infinite login loop.
          navigateFallbackDenylist: PWA_NAVIGATION_DENYLIST,
          globIgnores: [
            '**/logo-horizontal.png',
            '**/logo-inverted.png',
            '**/logo-mark.png',
          ],
          runtimeCaching: [
            {
              urlPattern: ({ request }) => request.destination === 'script' || request.destination === 'style',
              // Vite assets are content-hashed: a cached URL is immutable and
              // can be served without a validation round-trip.
              handler: 'CacheFirst',
              options: {
                cacheName: 'retail-feature-assets',
                expiration: {
                  maxEntries: 60,
                  maxAgeSeconds: 30 * 24 * 60 * 60,
                },
              },
            },
          ],
        },
      }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    define: {
      'import.meta.env.VITE_FRONTEND_GLITCHTIP_DSN': JSON.stringify(frontendErrorDsn),
    },
    build: {
      modulePreload: {
        resolveDependencies: (_filename, deps) =>
          deps.filter((dep) => !dep.includes('/charts-')),
      },
      rollupOptions: {
        output: {
          manualChunks,
        },
      },
    },
    server: {
      // Optional fallback for noisy environments where HMR should be disabled.
      hmr: process.env.DISABLE_HMR !== 'true',
      host: '127.0.0.1',
      port: 3000,
      proxy: {
        '/auth': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/api': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/salarii': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/health': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/livez': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/readyz': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/metrics': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/docs': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/openapi.json': {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: 'node',
      include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    },
  };
});
