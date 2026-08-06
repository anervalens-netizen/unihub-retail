import { createElement, createRef } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import type { DashboardSummary } from '../../api/generated/runtime-types';
import { HistoryDashboard, type HistoryPointView } from '../../features/dashboard/HistoryDashboard';

const currentSummary: DashboardSummary = {
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

const selectedPoint: HistoryPointView = {
  month: '2026-06',
  total_sales: 120_000,
  total_target: 140_000,
  target_progress_pct: 85.71,
  total_quantity: 480,
  total_receipts: 290,
  proc_bon2acc: 60,
  prc_focus_acc_qty: 22,
  total_stores: 10,
  total_agents: 17,
  working_days: 21,
  daily_average: 5_714.29,
  medie_produs: 250,
};

function historyProps(loading = false) {
  return {
    loading,
    error: null,
    onRetry: vi.fn(),
    selectedPoint,
    currentSummary,
    historySummary: null,
    yearFilter: null,
    onYearFilterChange: vi.fn(),
    availableYears: [2025, 2026],
    currentHistoryLoading: false,
    yearHistoryLoading: false,
    currentHistoryChartData: [],
    yearHistoryChartData: [],
    kpiMetric: 'proc_bon2acc' as const,
    onKpiMetricChange: vi.fn(),
    kpiChartData: [],
    includeClosedStores: false,
    onIncludeClosedStoresChange: vi.fn(),
    dropdownRef: createRef<HTMLDetailsElement>(),
    onDropdownToggle: vi.fn(),
    dropdownOpen: false,
    draftSelectionLabel: '2026-06',
    selectionLabel: '2026-06',
    months: ['2026-06'],
    draftSelectedMonths: ['2026-06'],
    onToggleMonth: vi.fn(),
    onApplyMonths: vi.fn(),
    historyStatusLabel: 'Luna finala 2026-06.',
    historyReceiptBucketChartData: [],
    historyFocusSubcategoryChartData: [],
    historyDailyChartData: [],
    historyCategoryMixChartData: [],
    historyBrandMixChartData: [],
    selectionSlug: '2026-06',
    regionals: [],
    sortedRegionals: [],
    regionalColumns: [],
    regionalSort: { key: 'regional', direction: 'asc' as const },
    onSortRegionals: vi.fn(),
    stores: [],
    sortedStores: [],
    storeColumns: [],
    storeSort: { key: 'locatie', direction: 'asc' as const },
    onSortStores: vi.fn(),
    agents: [],
    sortedAgents: [],
    agentColumns: [],
    agentSort: { key: 'agent', direction: 'asc' as const },
    onSortAgents: vi.fn(),
  };
}

describe('HistoryDashboard', () => {
  it('owns the history loading state', () => {
    const html = renderToStaticMarkup(createElement(HistoryDashboard, historyProps(true)));
    expect(html).toContain('Se incarca istoricul...');
  });

  it('renders the prepared history view model', () => {
    const html = renderToStaticMarkup(createElement(HistoryDashboard, historyProps()));

    expect(html).toContain('Evolutie lunara');
    expect(html).toContain('Trend KPI');
    expect(html).toContain('Luni analizate');
    expect(html).toContain('Overview — 2026-06');
    expect(html).toContain('Luna finala 2026-06.');
    expect(html).toContain('Accesorii nete');
    expect(html).toContain('Magazine');
    expect(html).toContain('Agenti');
  });
});
