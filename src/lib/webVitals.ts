import type { MetricType } from 'web-vitals';

export type WebVitalReporter = (metric: MetricType) => void;

type CoreWebVitalsModule = Pick<typeof import('web-vitals'), 'onINP' | 'onLCP'>;

const loadCoreWebVitals = (): Promise<CoreWebVitalsModule> => import('web-vitals');

export async function observeCoreWebVitals(
  report: WebVitalReporter,
  load: () => Promise<CoreWebVitalsModule> = loadCoreWebVitals,
): Promise<void> {
  const { onINP, onLCP } = await load();
  onLCP(report);
  onINP(report);
}

export function webVitalDistributionName(metric: MetricType): string {
  return `web_vitals.${metric.name.toLowerCase()}`;
}
