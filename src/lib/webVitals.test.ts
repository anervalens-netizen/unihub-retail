import { describe, expect, it, vi } from 'vitest';
import type { INPMetric, LCPMetric, MetricType } from 'web-vitals';

import { observeCoreWebVitals, webVitalDistributionName } from './webVitals';

describe('observeCoreWebVitals', () => {
  it('registers and forwards LCP and INP metrics', async () => {
    const report = vi.fn();
    const lcp = { name: 'LCP', value: 1234 } as LCPMetric;
    const inp = { name: 'INP', value: 87 } as INPMetric;

    await observeCoreWebVitals(report, async () => ({
      onLCP: (callback) => callback(lcp),
      onINP: (callback) => callback(inp),
    }));

    expect(report).toHaveBeenNthCalledWith(1, lcp);
    expect(report).toHaveBeenNthCalledWith(2, inp);
  });

  it('uses low-cardinality metric names', () => {
    expect(webVitalDistributionName({ name: 'LCP' } as MetricType)).toBe('web_vitals.lcp');
    expect(webVitalDistributionName({ name: 'INP' } as MetricType)).toBe('web_vitals.inp');
  });
});
