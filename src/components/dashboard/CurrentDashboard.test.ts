import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import type { DashboardSummary } from '../../api/generated/runtime-types';
import { CurrentDashboard } from '../../features/dashboard/CurrentDashboard';

const summary: DashboardSummary = {
  month: '2026-07',
  total_sales: 125_000,
  total_target: 150_000,
  target_progress_pct: 83.33,
  forecast_sales: 155_000,
  forecast_target_progress_pct: 103.33,
  total_quantity: 500,
  total_receipts: 300,
  proc_bon2acc: 62,
  prc_focus_acc_qty: 24,
  total_stores: 10,
  total_agents: 18,
  working_days: 12,
  daily_average: 10_416.67,
  medie_produs: 250,
  is_month_final: false,
  last_sale_date: '2026-07-12',
  imported_day_of_month: 12,
  days_in_month: 31,
  cartele_qty: 8,
};

describe('CurrentDashboard', () => {
  it('renders the current overview from the prepared view model', () => {
    const html = renderToStaticMarkup(
      createElement(CurrentDashboard, {
        currentMonth: '2026-07',
        filters: { firma: 'all', rm: 'all', magazin: [], agent: [] },
        mode: 'overview',
        onModeChange: vi.fn(),
        statusLabel: 'Luna in curs este in actualizare.',
        summary,
        receiptBucketChartData: [],
        focusSubcategoryChartData: [],
        periodComparison: null,
        comparisonDeltas: null,
        dailyChartData: [],
        categoryMixChartData: [],
        brandMixChartData: [],
        filterScopeLabel: 'Toate magazinele',
        regionals: [],
        sortedRegionals: [],
        regionalColumns: [],
        regionalSort: { key: 'regional', direction: 'asc' },
        onSortRegionals: vi.fn(),
        stores: [],
        sortedStores: [],
        storeColumns: [],
        storeSort: { key: 'locatie', direction: 'asc' },
        onSortStores: vi.fn(),
        agents: [],
        sortedAgents: [],
        agentColumns: [],
        agentSort: { key: 'agent', direction: 'asc' },
        onSortAgents: vi.fn(),
      }),
    );

    expect(html).toContain('Overview — 2026-07');
    expect(html).toContain('Luna in curs este in actualizare.');
    expect(html).toContain('Comparatie perioade');
    expect(html).toContain('Accesorii nete');
    expect(html).toContain('RM — Regional Manager');
    expect(html).toContain('Magazine');
    expect(html).toContain('Agenti - Toti agentii');
    expect(html).toContain('AI Forecast');
  });
});
