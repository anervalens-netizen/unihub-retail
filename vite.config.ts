import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { createHash } from 'node:crypto';
import path from 'path';
import type { Plugin } from 'vite';
import {defineConfig} from 'vitest/config';
import { VitePWA } from 'vite-plugin-pwa';

function sriPlugin(): Plugin {
  return {
    name: 'vite-sri',
    enforce: 'post',
    transformIndexHtml: {
      order: 'post',
      handler(html, ctx) {
        const integrityByPath = new Map<string, string>();
        for (const [fileName, output] of Object.entries(ctx.bundle ?? {})) {
          if (!fileName.endsWith('.js') && !fileName.endsWith('.css')) {
            continue;
          }
          const source =
            output.type === 'chunk'
              ? output.code
              : typeof output.source === 'string'
                ? output.source
                : Buffer.from(output.source).toString();
          integrityByPath.set(
            `/${fileName}`,
            `sha384-${createHash('sha384').update(source).digest('base64')}`,
          );
        }
        return html.replace(
          /<(script|link)([^>]+(?:src|href)="([^"]+\.(?:js|css))"[^>]*)>/g,
          (full, tag, attrs, url) => {
            const integrity = integrityByPath.get(url);
            return integrity && !/\sintegrity=/.test(attrs)
              ? `<${tag}${attrs} integrity="${integrity}"${/\scrossorigin(?:=|\s|$)/.test(attrs) ? '' : ' crossorigin="anonymous"'}>`
              : full;
          },
        );
      },
    },
  };
}

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
      sriPlugin(),
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
          runtimeCaching: [
            {
              urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
              handler: 'CacheFirst',
              options: {
                cacheName: 'google-fonts-cache',
                expiration: {
                  maxEntries: 10,
                  maxAgeSeconds: 60 * 60 * 24 * 365,
                },
                cacheableResponse: {
                  statuses: [0, 200],
                },
              },
            },
            {
              urlPattern: /^https:\/\/fonts\.gstatic\.com\/.*/i,
              handler: 'CacheFirst',
              options: {
                cacheName: 'gstatic-fonts-cache',
                expiration: {
                  maxEntries: 10,
                  maxAgeSeconds: 60 * 60 * 24 * 365,
                },
                cacheableResponse: {
                  statuses: [0, 200],
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
    build: {
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
