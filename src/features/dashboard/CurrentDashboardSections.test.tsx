// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../components/common/DataDisplay', () => ({
  Metric: ({ label, value }: { label: string; value: ReactNode }) => (
    <div><span>{label}</span><span>{value}</span></div>
  ),
}));

vi.mock('./CurrentDailyTrend', () => ({
  CurrentDailyTrend: ({ currentMonth }: { currentMonth: string }) => (
    <div>Daily trend {currentMonth}</div>
  ),
}));

vi.mock('./DashboardWidgets', () => ({
  CompactCurrency: ({ value }: { value: number }) => <span>{value}</span>,
  CompactPieSection: ({ title }: { title: string }) => <div>{title}</div>,
  DeltaCard: ({ title }: { title: string }) => <div>{title}</div>,
  KpiPerformanceCard: ({ title }: { title: string }) => <div>{title}</div>,
  PeriodTable: () => <div>Period table</div>,
  formatCompactDonutValue: (value: number) => String(value),
  getBon2AccTone: () => ({}),
  getFocusTone: () => ({}),
  sumChartValues: (rows: Array<Record<string, string | number>>, key: string) =>
    rows.reduce((total, row) => total + Number(row[key] ?? 0), 0),
}));

vi.mock('./BreakdownTable', () => ({
  BreakdownTable: (props: {
    title: string;
    rows: readonly unknown[];
    columns: readonly { key: string }[];
    sortKey: string;
    onSort: (key: string) => void;
    rowKey: (row: never, index: number) => string;
    exportColumns: readonly { value: (row: never) => unknown }[];
  }) => {
    props.onSort(props.sortKey);
    props.rows.forEach((row, index) => {
      props.rowKey(row as never, index);
      props.exportColumns.forEach((column) => column.value(row as never));
    });
    return <div>{props.title}</div>;
  },
}));

import { CurrentOverview } from './CurrentDashboardSections';
import { defaultAppFilters } from '../../lib/filterValues';

type OverviewProps = ComponentProps<typeof CurrentOverview>['model'];

const regional = {
  regional: 'Nord', target: 1000, total_vanzari: 900, proc_realizare_target: 90,
  forecast_target_pct: 95, promo_qty: 2, promo_discount_value: 10, qty_total: 9,
  medie_produs: 100, nr_bonuri: 5, proc_bon2acc: 40, prc_focus_acc_qty: 30,
};
const store = {
  firma: 'Mobiup', locatie: 'Promenada', site_code: 'S1', target: 1000,
  total_vanzari: 900, proc_realizare_target: 90, forecast_target_pct: 95,
  promo_qty: 2, promo_discount_value: 10, qty_total: 9, medie_produs: 100,
  nr_bonuri: 5, proc_bon2acc: 40, prc_focus_acc_qty: 30,
  return_receipt_count: 1, nr_agenti: 2, zile_active: 10,
};
const agent = {
  agent: 'Ana', firma: 'Mobiup', locatie: 'Promenada', site_code: 'S1', target: 500,
  total_vanzari: 450, proc_realizare_target: 90, promo_qty: 1,
  promo_discount_value: 5, acc_qty_realizat: 5, medie_produs: 90, nr_bonuri: 3,
  proc_bon2acc: 50, prc_focus_acc_qty: 25, return_receipt_count: 1,
  zile_lucrate: 8, medie_zilnica: 56,
};
const periodPoint = {
  label: 'Curent', month: '2026-09', day_range: '1-10', total_sales: 900,
  total_quantity: 9, total_receipts: 5, working_days: 10, daily_average: 90,
  avg_receipt_value: 180, medie_produs: 100, proc_bon2acc: 40,
  prc_focus_acc_qty: 30, cartele_qty: 0,
};

function populatedModel(): OverviewProps {
  return {
    currentMonth: '2026-09',
    filters: defaultAppFilters(),
    mode: 'overview',
    onModeChange: vi.fn(),
    statusLabel: 'Luna in curs.',
    summary: {
      month: '2026-09', total_sales: 900, total_target: 1000,
      target_progress_pct: 90, forecast_sales: 950, forecast_target_progress_pct: 95,
      total_quantity: 9, total_receipts: 5, proc_bon2acc: 40,
      prc_focus_acc_qty: 30, total_stores: 1, total_agents: 1, working_days: 10,
      daily_average: 90, medie_produs: 100, is_month_final: false,
      last_sale_date: '2026-09-10', imported_day_of_month: 10, days_in_month: 30,
      cartele_qty: 0,
    },
    receiptBucketChartData: [{ bucket: '2+', receipt_count: 2, share_pct: 40 }],
    focusSubcategoryChartData: [{ category: 'Focus', quantity_total: 3, share_pct: 33 }],
    periodComparison: {
      current: periodPoint,
      previous: { ...periodPoint, label: 'Anterior', month: '2026-08' },
      year_over_year: { ...periodPoint, label: 'An anterior', month: '2025-09' },
    },
    comparisonDeltas: {
      previousSales: 10, previousSalesPct: 1, previousReceipts: 1,
      previousReceiptsPct: 2, previousQuantity: 1, previousQuantityPct: 3,
      yearSales: -10, yearSalesPct: -1, yearReceipts: -1, yearReceiptsPct: -2,
      yearQuantity: -1, yearQuantityPct: -3,
    },
    dailyChartData: [{
      day: '01', sales: 100, qty: 1, receipts: 1,
      sales_last_year: 90, sales_forecast: null,
    }],
    categoryMixChartData: [{ category: 'Huse', sales_total: 300, quantity_total: 3, share_pct: 33 }],
    brandMixChartData: [{ brand: 'Apple', sales_total: 200, share_pct: 22 }],
    filterScopeLabel: 'Toate',
    regionals: [regional] as never,
    sortedRegionals: [regional] as never,
    regionalColumns: [{ key: 'regional', label: 'Regional', render: () => null }] as never,
    regionalSort: { key: 'regional', direction: 'asc' },
    onSortRegionals: vi.fn(),
    stores: [store] as never,
    sortedStores: [store] as never,
    storeColumns: [{ key: 'locatie', label: 'Magazin', render: () => null }] as never,
    storeSort: { key: 'locatie', direction: 'asc' },
    onSortStores: vi.fn(),
    agents: [agent] as never,
    sortedAgents: [agent] as never,
    agentColumns: [{ key: 'agent', label: 'Agent', render: () => null }] as never,
    agentSort: { key: 'agent', direction: 'asc' },
    onSortAgents: vi.fn(),
  } as OverviewProps;
}

describe('CurrentOverview composition', () => {
  it('executes populated summary, comparison, chart and breakdown projections', () => {
    const model = populatedModel();
    render(<CurrentOverview model={model} />);

    expect(screen.getByText('Overview — 2026-09')).toBeInTheDocument();
    expect(screen.getByText('Period table')).toBeInTheDocument();
    expect(screen.getByText('Daily trend 2026-09')).toBeInTheDocument();
    expect(screen.getByText('RM — Regional Manager')).toBeInTheDocument();
    expect(screen.getByText('Magazine')).toBeInTheDocument();
    expect(screen.getByText('Agenti - Toti agentii')).toBeInTheDocument();
    expect(model.onSortRegionals).toHaveBeenCalledWith('regional');
    expect(model.onSortStores).toHaveBeenCalledWith('locatie');
    expect(model.onSortAgents).toHaveBeenCalledWith('agent');
  });

  it('covers the unavailable comparison branches', () => {
    const model = populatedModel();
    render(<CurrentOverview model={{
      ...model,
      periodComparison: null,
      comparisonDeltas: null,
    }} />);

    expect(screen.getByText('Date indisponibile pentru comparatia de perioade.')).toBeInTheDocument();
    expect(screen.getByText('Date indisponibile pentru variatiile de perioada.')).toBeInTheDocument();
  });
});
