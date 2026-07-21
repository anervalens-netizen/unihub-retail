import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { installPreloadRecovery } from './lib/preloadRecovery.ts';

import * as Sentry from '@sentry/react';

const sentryDsn = import.meta.env.VITE_GLITCHTIP_DSN;
if (sentryDsn) {
  const supportsBrowserTracing = typeof Array.prototype.at === 'function';
  const connection = (
    navigator as Navigator & {
      connection?: { effectiveType?: string; saveData?: boolean };
    }
  ).connection;
  Sentry.init({
    dsn: sentryDsn,
    environment: import.meta.env.MODE,
    integrations: supportsBrowserTracing ? [Sentry.browserTracingIntegration()] : [],
    tracesSampleRate: supportsBrowserTracing ? 0.1 : 0,
    tracePropagationTargets: [/^\//, window.location.origin],
  });
  Sentry.setTag('network.effective_type', connection?.effectiveType ?? 'unknown');
  Sentry.setTag('network.save_data', String(connection?.saveData ?? false));
}

installPreloadRecovery();

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './auth/AuthContext.tsx';
import { ErrorBoundary } from './components/ErrorBoundary.tsx';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary
      title="UniHub Retail nu a putut afisa aplicatia"
      description="Am inregistrat eroarea. Poti reincerca randarea sau reincarca aplicatia."
    >
      <AuthProvider>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </AuthProvider>
    </ErrorBoundary>
  </StrictMode>,
);
