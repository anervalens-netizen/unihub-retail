// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('recharts', () => ({
  Bar: () => null,
  CartesianGrid: () => null,
  ComposedChart: ({ children, data }: { children?: ReactNode; data?: unknown[] }) => (
    <div data-testid="daily-composed-chart" data-points={data?.length ?? 0}>{children}</div>
  ),
  Legend: () => null,
  Line: () => null,
  ResponsiveContainer: ({ children }: { children?: ReactNode }) => <>{children}</>,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

vi.mock('../../components/common/DataGrid', () => ({
  DataGrid: ({
    title,
    rows,
    columns,
    initialSort,
    onSortChange,
    exportColumns,
  }: {
    title: string;
    rows: unknown[];
    columns: Array<{ filter?: { kind: string } }>;
    initialSort: Array<{ key: string }>;
    onSortChange?: (sorts: Array<{ key: string; direction: 'asc' | 'desc' }>) => void;
    exportColumns?: Array<{ header: string }>;
  }) => (
    <div data-testid={`grid-${title}`}>
      <span data-testid={`grid-${title}-state`}>
        {rows.length}|{columns[0]?.filter?.kind}|{initialSort.map((sort) => sort.key).join(',')}
      </span>
      <span data-testid={`grid-${title}-export`}>
        {exportColumns?.map((column) => column.header).join('|') ?? 'derived'}
      </span>
      <button
        type="button"
        onClick={() => onSortChange?.(
          title === 'RM'
            ? [
                { key: 'regional', direction: 'asc' },
                { key: 'target', direction: 'desc' },
              ]
            : [
                { key: 'locatie', direction: 'asc' },
                { key: 'target', direction: 'desc' },
              ],
        )}
      >
        persist-{title}-sort
      </button>
    </div>
  ),
}));

vi.mock('./BreakdownTable', () => ({
  BreakdownTable: ({ title, rows }: { title: string; rows: unknown[] }) => (
    <div data-testid={`legacy-${title}`}>{rows.length}</div>
  ),
}));

vi.mock('./DashboardWidgets', () => ({
  CompactPieSection: ({ title, pieData }: { title: string; pieData: unknown[] }) => (
    <div data-testid={`pie-${title}`} data-points={pieData.length}>{title}</div>
  ),
  formatCompactAxisValue: String,
  formatCompactDonutValue: String,
  sumChartValues: () => 0,
}));

import { HistoryBreakdowns, HistoryDetailCharts } from './HistoryDashboardDetails';

const onRegionalGridSortsChange = vi.fn();
const onStoreGridSortsChange = vi.fn();

const props = {
  selectionSlug: '2026-08',
  regionals: [
    { regional: 'Nord', target: 100 },
    { regional: 'Sud', target: 200 },
  ],
  sortedRegionals: [{ regional: 'Sud', target: 200 }],
  regionalColumns: [
    { key: 'regional', label: 'Regional', render: (row: { regional: string }) => row.regional },
    { key: 'target', label: 'Target', render: (row: { target: number }) => row.target },
  ],
  regionalSort: { key: 'target', direction: 'desc' },
  onSortRegionals: vi.fn(),
  regionalGridSorts: [
    { key: 'target', direction: 'desc' },
    { key: 'regional', direction: 'asc' },
  ],
  onRegionalGridSortsChange,
  stores: [
    { site_code: 'S1', firma: 'Mobiup', locatie: 'Promenada', target: 100 },
    { site_code: 'S2', firma: 'Arsis', locatie: 'Baneasa', target: 200 },
  ],
  sortedStores: [{ site_code: 'S2', firma: 'Arsis', locatie: 'Baneasa', target: 200 }],
  storeColumns: [
    { key: 'locatie', label: 'Magazin', render: (row: { locatie: string }) => row.locatie },
    { key: 'target', label: 'Target', render: (row: { target: number }) => row.target },
  ],
  storeSort: { key: 'total_vanzari', direction: 'desc' },
  onSortStores: vi.fn(),
  storeGridSorts: [
    { key: 'total_vanzari', direction: 'desc' },
  ],
  onStoreGridSortsChange,
  agents: [{ agent: 'Ana', site_code: 'S1' }],
  sortedAgents: [{ agent: 'Ana', site_code: 'S1' }],
  agentColumns: [{ key: 'agent', label: 'Agent', render: () => 'Ana' }],
  agentSort: { key: 'agent', direction: 'asc' },
  onSortAgents: vi.fn(),
};

const detailProps = {
  selectionLabel: '2026-08',
  historyDailyChartData: [
    { day: '01', sales: 100, qty: 2, receipts: 1 },
    { day: '02', sales: 200, qty: 3, receipts: 2 },
  ],
  historyCategoryMixChartData: [
    { category: 'Huse', sales_total: 100, quantity_total: 2, share_pct: 100 },
  ],
  historyBrandMixChartData: [
    { brand: 'Apple', sales_total: 60, share_pct: 60 },
    { brand: 'Samsung', sales_total: 40, share_pct: 40 },
  ],
};

describe('HistoryDetailCharts V4 ChartFrame consumers', () => {
  it('preserves daily chart and pie content inside the compact mobile ChartFrame shell', () => {
    render(<HistoryDetailCharts props={detailProps as never} visible={false} />);

    const dailyHeading = screen.getByRole('heading', {
      name: 'Evolutie zilnica pentru 2026-08',
    });
    const dailyFrame = dailyHeading.closest('.glass');
    expect(dailyFrame).toHaveClass('p-3', 'sm:p-4', 'flex', 'min-w-0', 'flex-col');
    expect(dailyFrame?.parentElement).toHaveClass('grid', 'hidden', 'lg:grid');

    const dailyChart = screen.getByTestId('daily-composed-chart');
    expect(dailyChart).toHaveAttribute('data-points', '2');
    expect(dailyChart.parentElement).toHaveClass(
      '-mx-2',
      'aspect-[16/6]',
      'min-[1500px]:flex-1',
    );

    const pieHeading = screen.getByRole('heading', { name: 'Top categorii si branduri' });
    expect(pieHeading.closest('.glass')).toHaveClass('p-3', 'sm:p-4', 'flex', 'flex-col');
    expect(screen.getByTestId('pie-Top categorii')).toHaveAttribute('data-points', '1');
    expect(screen.getByTestId('pie-Branduri compatibile')).toHaveAttribute('data-points', '2');
    expect(screen.getByTestId('pie-Top categorii').parentElement).toHaveClass(
      'grid',
      'flex-1',
      'min-[1500px]:grid-rows-2',
    );
  });
});

describe('HistoryBreakdowns V3 DataGrid consumers', () => {
  it('uses raw RM and Store rows, persists both sort chains and leaves Agenti legacy', () => {
    onRegionalGridSortsChange.mockClear();
    onStoreGridSortsChange.mockClear();
    render(<HistoryBreakdowns props={props as never} visible />);

    expect(screen.getByTestId('grid-RM-state')).toHaveTextContent('2|text|target,regional');
    expect(screen.getByTestId('grid-Magazine-state')).toHaveTextContent(
      '2|text|total_vanzari',
    );
    expect(screen.getByTestId('grid-RM-export')).toHaveTextContent('derived');
    expect(screen.getByTestId('grid-Magazine-export')).toHaveTextContent(
      'Firma|Magazin|Target|Vanzari|Procent|Cantitate|Nr bonuri|Retururi|Agenti|Zile active',
    );
    expect(screen.getByTestId('legacy-Agenti')).toHaveTextContent('1');
    expect(screen.queryByTestId('legacy-Magazine')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'persist-RM-sort' }));
    expect(onRegionalGridSortsChange).toHaveBeenCalledWith([
      { key: 'regional', direction: 'asc' },
      { key: 'target', direction: 'desc' },
    ]);

    fireEvent.click(screen.getByRole('button', { name: 'persist-Magazine-sort' }));
    expect(onStoreGridSortsChange).toHaveBeenCalledWith([
      { key: 'locatie', direction: 'asc' },
      { key: 'target', direction: 'desc' },
    ]);
  });
});
