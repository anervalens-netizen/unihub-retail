import { describe, expect, it } from 'vitest';

import { buildDailyCurve, nextSortDirection } from './model';

describe('AI forecast model', () => {
  it('projects daily actuals only after a sale is present', () => {
    expect(buildDailyCurve([
      { forecast_date: '2026-08-01', forecast_sales: 10, actual_sales: 0, cumulative_forecast: 10, cumulative_actual: 0 },
      { forecast_date: '2026-08-02', forecast_sales: 12, actual_sales: 3, cumulative_forecast: 22, cumulative_actual: 3 },
    ])).toMatchObject([
      { day: '01', actualDaily: null },
      { day: '02', actualDaily: 3 },
    ]);
  });

  it('keeps the sort toggle deterministic', () => {
    expect(nextSortDirection('forecast_sales', 'forecast_sales', 'asc')).toBe('desc');
    expect(nextSortDirection('forecast_sales', 'manager', 'desc')).toBe('asc');
  });
});
