import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { installPreloadRecovery } from './lib/preloadRecovery.ts';
import { observeCoreWebVitals, webVitalDistributionName } from './lib/webVitals.ts';

import * as Sentry from '@sentry/react';

const sentryDsn = import.meta.env.VITE_GLITCHTIP_DSN;
const supportsSentry = typeof Array.prototype.at === 'function';
if (sentryDsn && supportsSentry) {
  const connection = (
    navigator as Navigator & {
      connection?: { effectiveType?: string; saveData?: boolean };
    }
  ).connection;
  Sentry.init({
    dsn: sentryDsn,
    environment: import.meta.env.MODE,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: 0.1,
    tracePropagationTargets: [/^\//, window.location.origin],
  });
  Sentry.setTag('network.effective_type', connection?.effectiveType ?? 'unknown');
  Sentry.setTag('network.save_data', String(connection?.saveData ?? false));
  void observeCoreWebVitals((metric) => {
    Sentry.setMeasurement(metric.name.toLowerCase(), metric.value, 'millisecond');
    Sentry.metrics.distribution(webVitalDistributionName(metric), metric.value, {
      unit: 'millisecond',
      attributes: {
        rating: metric.rating,
        navigation_type: metric.navigationType,
      },
    });
  }).catch((error: unknown) => {
    Sentry.captureException(error);
  });
}

installPreloadRecovery();

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './auth/AuthContext.tsx';
import { ErrorBoundary } from './components/ErrorBoundary.tsx';
import { clearAvailableMonthsCache } from './hooks/useAvailableMonths.ts';
import { clearCachedViews } from './lib/viewCache.ts';

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
      <AuthProvider
        onSessionCleared={() => {
          queryClient.clear();
          clearAvailableMonthsCache();
          clearCachedViews();
        }}
      >
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </AuthProvider>
    </ErrorBoundary>
  </StrictMode>,
);
