import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vitest/config';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig(() => {
  const backendTarget = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000';
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
        includeAssets: [
          'favicon-64.png',
          'apple-touch-icon.png',
          'logo-mark.png',
          'logo-horizontal.png',
          'logo-inverted.png',
        ],
        manifest: {
          name: 'UniHub Retail',
          short_name: 'UniHub Retail',
          description: 'Platforma Mobiup pentru management vanzari si agenti',
          theme_color: '#0f1a3a',
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
              src: 'pwa-maskable-512x512.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'maskable',
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
          globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        },
      }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
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
      include: ['src/**/*.test.ts'],
    },
  };
});
