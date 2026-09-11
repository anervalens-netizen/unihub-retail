import { describe, expect, it } from 'vitest';

import {
  getMetricDefinition,
  METRIC_CATALOG,
  METRIC_CATALOG_VERSION,
  searchMetricCatalog,
  type MetricThreshold,
} from './metricCatalog';

describe('Metric Catalog v1', () => {
  it('keeps a bounded stable set of unique critical KPI ids', () => {
    expect(METRIC_CATALOG_VERSION).toBe(1);
    expect(METRIC_CATALOG).toHaveLength(11);
    const ids = METRIC_CATALOG.map((metric) => metric.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual([
      'retail.sales.net_value',
      'retail.target.value',
      'retail.target.attainment_pct',
      'retail.accessories.net_quantity',
      'retail.receipts.positive_count',
      'retail.receipts.bon2acc_pct',
      'retail.focus.accessory_pct',
      'retail.sales.avg_product_value',
      'retail.sales.daily_average',
      'retail.sales.avg_receipt_value',
      'retail.receipts.return_count',
    ]);
  });

  it('requires explanatory metadata and stable code/test references for every metric', () => {
    for (const metric of METRIC_CATALOG) {
      expect(metric.version).toBe(METRIC_CATALOG_VERSION);
      expect(metric.name.trim()).not.toBe('');
      expect(metric.description.trim()).not.toBe('');
      expect(metric.formula.trim()).not.toBe('');
      expect(metric.aggregation.trim()).not.toBe('');
      expect(metric.granularities.length).toBeGreaterThan(0);
      expect(metric.sources.length).toBeGreaterThan(0);
      expect(metric.freshness.trim()).not.toBe('');
      expect(metric.organizationSemantics.current.trim()).not.toBe('');
      expect(metric.organizationSemantics.historical.trim()).not.toBe('');
      expect(metric.implementationRefs.length).toBeGreaterThan(0);
      expect(metric.verificationRefs.length).toBeGreaterThan(0);
      expect(metric.implementationRefs.every((ref) => /^(backend|src)\/.+(::.+|\.sql)$/.test(ref))).toBe(true);
      expect(metric.verificationRefs.every((ref) => /^(backend\/tests|src)\//.test(ref))).toBe(true);
      if (metric.unit === 'count') expect(metric.precision).toBe(0);
      else expect(metric.precision).toBe(2);
    }
  });

  it('documents only the real Bon2Acc and Focus visual threshold bands', () => {
    expect(getMetricDefinition('retail.receipts.bon2acc_pct')?.visualThresholds).toEqual([
      { label: 'Critic', maxExclusive: 28 },
      { label: 'Atenție', minInclusive: 28, maxExclusive: 30 },
      { label: 'Solid', minInclusive: 30, maxExclusive: 31 },
      { label: 'Foarte bun', minInclusive: 31 },
    ]);
    expect(getMetricDefinition('retail.focus.accessory_pct')?.visualThresholds).toEqual([
      { label: 'Critic', maxExclusive: 6 },
      { label: 'Sub țintă', minInclusive: 6, maxExclusive: 7 },
      { label: 'În target', minInclusive: 7, maxExclusive: 8 },
      { label: 'Foarte bun', minInclusive: 8 },
    ]);
    expect(
      METRIC_CATALOG.filter(
        (metric) =>
          metric.id !== 'retail.receipts.bon2acc_pct' &&
          metric.id !== 'retail.focus.accessory_pct',
      ).every((metric) => metric.visualThresholds === null),
    ).toBe(true);
  });

  it('keeps threshold ranges ordered and contiguous', () => {
    for (const metric of METRIC_CATALOG) {
      const thresholds = metric.visualThresholds as readonly MetricThreshold[] | null;
      if (!thresholds) continue;
      expect(thresholds[0]?.minInclusive).toBeUndefined();
      expect(thresholds.at(-1)?.maxExclusive).toBeUndefined();
      for (let index = 1; index < thresholds.length; index += 1) {
        expect(thresholds[index - 1]?.maxExclusive).toBe(thresholds[index]?.minInclusive);
      }
    }
  });

  it('states the current-store ownership caveat for historical return counts', () => {
    const returns = getMetricDefinition('retail.receipts.return_count');
    expect(returns?.organizationSemantics.historical).toContain('stores.regional curent');
    expect(returns?.limitations.join(' ')).toContain('magazin mutat între regiuni');
    expect(returns?.limitations.join(' ')).toContain('nu îl tratează ca istoric-authoritative');
  });

  it('does not publish the equal-agent target fallback as the canonical allocation rule', () => {
    const target = getMetricDefinition('retail.target.value');
    expect(target?.formula).toContain('zile_vânzare_magazin');
    expect(target?.formula).toContain('zile_vânzare_agent');
    expect(target?.formula).toContain('_agent_base_query');
    expect(target?.limitations.join(' ')).toContain('active_agents');
    expect(target?.limitations.join(' ')).toContain('deviație de implementare');
  });

  it('states that target attainment can refresh independently from sales reporting', () => {
    const attainment = getMetricDefinition('retail.target.attainment_pct');
    expect(attainment?.freshness).toContain('freshness independent');
    expect(attainment?.freshness).toContain('store_targets/agent_targets');
    expect(attainment?.limitations.join(' ')).toContain('retail.target.value');
  });

  it('documents current-store ownership for historical targets and derived attainment', () => {
    for (const id of ['retail.target.value', 'retail.target.attainment_pct']) {
      const metric = getMetricDefinition(id);
      expect(metric?.organizationSemantics.historical).toContain('stores curent');
      expect(metric?.organizationSemantics.historical).toContain('vânzările rămân în ownership-ul istoric');
      expect(metric?.limitations.join(' ')).toContain('History filtrat pe firmă/RM/ASM');
      expect(metric?.limitations.join(' ')).toContain('ownership');
    }
  });

  it('documents legacy Year History sources, freshness and ownership for net sales', () => {
    const sales = getMetricDefinition('retail.sales.net_value');
    expect(sales?.sources).toContain('historical_monthly_sales.total_value');
    expect(sales?.sources).toContain('historical_annual_sales.total_value');
    expect(sales?.freshness).toContain('surse legacy');
    expect(sales?.freshness).toContain('nu sunt reconstruite');
    expect(sales?.organizationSemantics.historical).toContain('historical_monthly_sales');
    expect(sales?.organizationSemantics.historical).toContain('stores curent');
    expect(sales?.limitations.join(' ')).toContain('anii <= 2023');
    expect(sales?.limitations.join(' ')).toContain('RM/ASM');
  });

  it('documents signed-quantity guard differences instead of claiming one ratio rule', () => {
    const focus = getMetricDefinition('retail.focus.accessory_pct');
    const averageProduct = getMetricDefinition('retail.sales.avg_product_value');
    for (const metric of [focus, averageProduct]) {
      expect(metric?.formula).toContain('!= 0');
      expect(metric?.formula).toContain('> 0');
      expect(metric?.limitations.join(' ')).toContain('negativ');
      expect(metric?.limitations.join(' ')).toContain('Dashboard');
      expect(metric?.limitations.join(' ')).toContain('returnează null');
    }
  });

  it('searches by human name, id, formula source and granularity without mutating the catalog', () => {
    expect(searchMetricCatalog('Bon2Acc').map((metric) => metric.id)).toContain('retail.receipts.bon2acc_pct');
    expect(searchMetricCatalog('return_receipt_count').map((metric) => metric.id)).toContain('retail.receipts.return_count');
    expect(searchMetricCatalog('agent').length).toBeGreaterThan(1);
    expect(searchMetricCatalog('')).toBe(METRIC_CATALOG);
    expect(getMetricDefinition('missing.metric')).toBeUndefined();
  });
});
