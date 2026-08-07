import { describe, expect, it } from 'vitest';

import { buildDailyCurve, nextSortDirection } from './model';

describe('AI forecast model', () => {
  it('uses explicit actual coverage for zero and negative days', () => {
    expect(buildDailyCurve([
      { forecast_date: '2026-08-01', forecast_sales: 10, actual_sales: 0, has_actual: true, cumulative_forecast: 10, cumulative_actual: 0 },
      { forecast_date: '2026-08-02', forecast_sales: 12, actual_sales: -3, has_actual: true, cumulative_forecast: 22, cumulative_actual: -3 },
      { forecast_date: '2026-08-03', forecast_sales: 8, actual_sales: 0, has_actual: false, cumulative_forecast: 30, cumulative_actual: -3 },
    ])).toMatchObject([
      { day: '01', actualDaily: 0, cumulativeActual: 0 },
      { day: '02', actualDaily: -3, cumulativeActual: -3 },
      { day: '03', actualDaily: null, cumulativeActual: null },
    ]);
  });

  it('keeps the sort toggle deterministic', () => {
    expect(nextSortDirection('forecast_sales', 'forecast_sales', 'asc')).toBe('desc');
    expect(nextSortDirection('forecast_sales', 'manager', 'desc')).toBe('asc');
  });
});
