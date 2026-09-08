// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

const rechartsCalls = vi.hoisted(() => ({
  bar: vi.fn(),
  grid: vi.fn(),
  composed: vi.fn(),
  legend: vi.fn(),
  line: vi.fn(),
  responsive: vi.fn(),
  tooltip: vi.fn(),
  xAxis: vi.fn(),
  yAxis: vi.fn(),
}));

vi.mock('recharts', () => ({
  Bar: (chartProps: Record<string, unknown>) => {
    rechartsCalls.bar(chartProps);
    return null;
  },
  CartesianGrid: (chartProps: Record<string, unknown>) => {
    rechartsCalls.grid(chartProps);
    return null;
  },
  ComposedChart: ({ children, ...chartProps }: { children?: ReactNode } & Record<string, unknown>) => {
    rechartsCalls.composed(chartProps);
    return <>{children}</>;
  },
  Legend: (chartProps: Record<string, unknown>) => {
    rechartsCalls.legend(chartProps);
    return null;
  },
  Line: (chartProps: Record<string, unknown>) => {
    rechartsCalls.line(chartProps);
    return null;
  },
  ResponsiveContainer: ({ children, ...chartProps }: { children?: ReactNode } & Record<string, unknown>) => {
    rechartsCalls.responsive(chartProps);
    return <>{children}</>;
  },
  Tooltip: (chartProps: Record<string, unknown>) => {
    rechartsCalls.tooltip(chartProps);
    return null;
  },
  XAxis: (chartProps: Record<string, unknown>) => {
    rechartsCalls.xAxis(chartProps);
    return null;
  },
  YAxis: (chartProps: Record<string, unknown>) => {
    rechartsCalls.yAxis(chartProps);
    return null;
  },
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
  formatCompactAxisValue: (value: unknown) => `axis:${String(value)}`,
  formatCompactDonutValue: String,
  sumChartValues: () => 0,
}));

import { formatAmount, formatInt } from '../../lib/formatters';
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
  it('preserves the complete responsive shell and daily Recharts contract', () => {
    for (const mock of Object.values(rechartsCalls)) mock.mockClear();
    render(<HistoryDetailCharts props={detailProps as never} visible={false} />);

    const dailyHeading = screen.getByRole('heading', {
      name: 'Evolutie zilnica pentru 2026-08',
    });
    const dailyFrame = dailyHeading.closest('.glass');
    expect(dailyFrame).toHaveClass(
      'glass',
      'rounded-3xl',
      'p-3',
      'sm:p-4',
      'flex',
      'min-w-0',
      'flex-col',
    );
    expect(dailyHeading.closest('.mb-2')).toHaveClass(
      'mb-2',
      'sm:mb-3',
      'flex',
      'justify-between',
      'gap-2',
      'items-center',
    );

    const outerGrid = dailyFrame?.parentElement;
    expect(outerGrid).toHaveClass(
      'grid',
      'min-w-0',
      'items-stretch',
      'gap-3',
      'min-[1500px]:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]',
      'hidden',
      'lg:grid',
    );

    const dailyContent = dailyFrame?.querySelector('.aspect-\\[16\\/6\\]');
    expect(dailyContent).toHaveClass(
      '-mx-2',
      'aspect-[16/6]',
      'min-h-56',
      'max-h-72',
      'w-auto',
      'rounded-xl',
      'bg-slate-50/80',
      'p-0.5',
      'sm:mx-0',
      'sm:w-full',
      'sm:rounded-2xl',
      'sm:p-2',
      'dark:bg-slate-800/40',
      'min-[1500px]:aspect-auto',
      'min-[1500px]:min-h-[24rem]',
      'min-[1500px]:max-h-none',
      'min-[1500px]:flex-1',
    );

    const composedProps = rechartsCalls.composed.mock.calls[0]?.[0] as {
      data: unknown;
      margin: Record<string, number>;
    };
    expect(composedProps.data).toBe(detailProps.historyDailyChartData);
    expect(composedProps.margin).toEqual({ top: 4, right: 0, bottom: 0, left: 0 });

    expect(rechartsCalls.responsive).toHaveBeenCalledWith(expect.objectContaining({
      width: '100%',
      height: '100%',
      minWidth: 1,
      minHeight: 1,
    }));
    expect(rechartsCalls.grid).toHaveBeenCalledWith(expect.objectContaining({
      strokeDasharray: '3 3',
      vertical: false,
      opacity: 0.15,
    }));
    expect(rechartsCalls.legend).toHaveBeenCalledTimes(1);

    const xAxisProps = rechartsCalls.xAxis.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(xAxisProps).toMatchObject({
      dataKey: 'day',
      tick: { fontSize: 10 },
      axisLine: false,
      tickLine: false,
    });

    const [salesAxisProps, qtyAxisProps] = rechartsCalls.yAxis.mock.calls.map(
      ([callProps]) => callProps as {
        yAxisId: string;
        width: number;
        orientation?: string;
        tick: { fontSize: number };
        tickFormatter: (value: unknown) => unknown;
        axisLine: boolean;
        tickLine: boolean;
      },
    );
    expect(salesAxisProps).toMatchObject({
      yAxisId: 'sales',
      width: 38,
      tick: { fontSize: 10 },
      axisLine: false,
      tickLine: false,
    });
    expect(salesAxisProps.orientation).toBeUndefined();
    expect(salesAxisProps.tickFormatter(1234)).toBe('axis:1234');
    expect(qtyAxisProps).toMatchObject({
      yAxisId: 'qty',
      width: 30,
      orientation: 'right',
      tick: { fontSize: 10 },
      axisLine: false,
      tickLine: false,
    });
    expect(qtyAxisProps.tickFormatter(1234)).toBe('axis:1234');

    const tooltipProps = rechartsCalls.tooltip.mock.calls[0]?.[0] as {
      formatter: (value: unknown, name: unknown) => unknown;
    };
    const fractionalTooltipValue = 100.25;
    expect(formatAmount(fractionalTooltipValue)).not.toBe(formatInt(fractionalTooltipValue));
    expect(tooltipProps.formatter(fractionalTooltipValue, 'Vanzari')).toBe(
      formatAmount(fractionalTooltipValue),
    );
    expect(tooltipProps.formatter(fractionalTooltipValue, 'Cantitate')).toBe(
      formatInt(fractionalTooltipValue),
    );

    const barProps = rechartsCalls.bar.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(barProps).toMatchObject({
      yAxisId: 'sales',
      dataKey: 'sales',
      name: 'Vanzari',
      fill: '#4f46e5',
      radius: [8, 8, 0, 0],
    });

    const lineProps = rechartsCalls.line.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(lineProps).toMatchObject({
      yAxisId: 'qty',
      type: 'monotone',
      dataKey: 'qty',
      name: 'Cantitate',
      stroke: '#f59e0b',
      strokeWidth: 2,
      dot: false,
    });

    const pieHeading = screen.getByRole('heading', { name: 'Top categorii si branduri' });
    const pieFrame = pieHeading.closest('.glass');
    expect(pieFrame).toHaveClass(
      'glass',
      'rounded-3xl',
      'p-3',
      'sm:p-4',
      'flex',
      'min-w-0',
      'flex-col',
    );
    expect(pieHeading.closest('.mb-2')).toHaveClass(
      'mb-2',
      'sm:mb-3',
      'flex',
      'justify-between',
      'gap-2',
      'items-center',
    );
    expect(screen.getByTestId('pie-Top categorii')).toHaveAttribute('data-points', '1');
    expect(screen.getByTestId('pie-Branduri compatibile')).toHaveAttribute('data-points', '2');
    expect(screen.getByTestId('pie-Top categorii').parentElement).toHaveClass(
      'grid',
      'min-w-0',
      'flex-1',
      'gap-2',
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
