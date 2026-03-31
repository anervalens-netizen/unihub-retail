import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

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
    plugins: [react(), tailwindcss()],
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
  };
});
