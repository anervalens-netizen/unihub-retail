// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

const rechartsCalls = vi.hoisted(() => ({
  area: vi.fn(),
  areaChart: vi.fn(),
  grid: vi.fn(),
  line: vi.fn(),
  lineChart: vi.fn(),
  responsive: vi.fn(),
  tooltip: vi.fn(),
  xAxis: vi.fn(),
  yAxis: vi.fn(),
}));

vi.mock('recharts', () => ({
  Area: (chartProps: Record<string, unknown>) => {
    rechartsCalls.area(chartProps);
    return null;
  },
  AreaChart: ({ children, ...chartProps }: { children?: ReactNode } & Record<string, unknown>) => {
    rechartsCalls.areaChart(chartProps);
    return <div data-testid="area-chart">{children}</div>;
  },
  Bar: ({ children }: { children?: ReactNode }) => <>{children}</>,
  CartesianGrid: (chartProps: Record<string, unknown>) => {
    rechartsCalls.grid(chartProps);
    return null;
  },
  Cell: () => null,
  ComposedChart: ({ children, data }: { children?: ReactNode; data?: unknown[] }) => (
    <div data-testid="composed-chart" data-points={data?.length ?? 0}>{children}</div>
  ),
  Legend: () => null,
  Line: (chartProps: Record<string, unknown>) => {
    rechartsCalls.line(chartProps);
    return null;
  },
  LineChart: ({ children, ...chartProps }: { children?: ReactNode } & Record<string, unknown>) => {
    rechartsCalls.lineChart(chartProps);
    return <div data-testid="line-chart">{children}</div>;
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

import { formatInt } from '../../lib/formatters';
import { HistoryKpiTrend, HistoryMonthlyTrend } from './HistoryDashboardTrend';

function trendProps(overrides: Record<string, unknown> = {}) {
  return {
    currentSummary: { is_month_final: false },
    yearFilter: null,
    onYearFilterChange: vi.fn(),
    availableYears: [2025, 2026],
    currentHistoryLoading: false,
    yearHistoryLoading: false,
    currentHistoryChartData: [
      {
        month: '2026-07',
        sales: 100,
        target: 90,
        progress: 111.11,
        isForecast: false,
      },
    ],
    yearHistoryChartData: [
      {
        label: 'Ian',
        sales: 100,
        target: 90,
        progress: 111.11,
        isAggregate: false,
      },
      {
        label: 'Feb',
        sales: 120,
        target: 110,
        progress: 109.09,
        isAggregate: false,
      },
    ],
    kpiMetric: 'proc_bon2acc',
    onKpiMetricChange: vi.fn(),
    kpiChartData: [{ month: '2026-07', value: 60 }],
    ...overrides,
  };
}

describe('HistoryDashboardTrend ChartFrame pilot', () => {
  it('preserves monthly subtitle, year control and current/year data routing', () => {
    const onYearFilterChange = vi.fn();
    const props = trendProps({ onYearFilterChange });
    const { rerender } = render(
      <HistoryMonthlyTrend props={props as never} visible />,
    );

    expect(screen.getByRole('heading', { name: 'Evolutie lunara' })).toBeInTheDocument();
    expect(screen.getByText(
      'Ultimele 13 luni finalizate + previziune luna in curs',
    )).toBeInTheDocument();
    expect(screen.getByTestId('composed-chart')).toHaveAttribute('data-points', '1');

    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2025' } });
    expect(onYearFilterChange).toHaveBeenCalledWith(2025);

    rerender(
      <HistoryMonthlyTrend
        props={trendProps({ yearFilter: 2025 }) as never}
        visible
      />,
    );
    expect(screen.getByText('Toate lunile disponibile — 2025')).toBeInTheDocument();
    expect(screen.getByTestId('composed-chart')).toHaveAttribute('data-points', '2');

    rerender(
      <HistoryMonthlyTrend
        props={trendProps({ yearFilter: 2025, yearHistoryChartData: [] }) as never}
        visible
      />,
    );

    expect(screen.getByText(
      'Nu exista date pentru 2025 cu filtrele curente.',
    )).toBeInTheDocument();
    expect(screen.queryByTestId('composed-chart')).not.toBeInTheDocument();
  });

  it('switches KPI Area/Line locally while preserving data, formatting and metric controls', () => {
    for (const mock of Object.values(rechartsCalls)) mock.mockClear();
    const onKpiMetricChange = vi.fn();
    const kpiChartData = [
      { month: '2026-06', value: 59.75 },
      { month: '2026-07', value: 60.25 },
    ];
    const initialProps = trendProps({ onKpiMetricChange, kpiChartData });
    const { rerender } = render(
      <HistoryKpiTrend props={initialProps as never} visible />,
    );

    const heading = screen.getByRole('heading', { name: 'Trend KPI' });
    expect(heading.closest('.glass')).not.toHaveClass('hidden');
    const chartType = screen.getByRole('combobox', { name: 'Tip grafic KPI' });
    expect(chartType).toHaveValue('area');
    expect(screen.getByTestId('area-chart')).toBeInTheDocument();
    expect(screen.queryByTestId('line-chart')).not.toBeInTheDocument();

    const areaChartProps = rechartsCalls.areaChart.mock.calls[0]?.[0] as { data: unknown };
    expect(areaChartProps.data).toBe(kpiChartData);
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
    expect(rechartsCalls.xAxis).toHaveBeenCalledWith(expect.objectContaining({
      dataKey: 'month',
      tick: { fontSize: 10 },
      axisLine: false,
      tickLine: false,
    }));
    expect(rechartsCalls.yAxis).toHaveBeenCalledWith(expect.objectContaining({
      tick: { fontSize: 10 },
      axisLine: false,
      tickLine: false,
    }));
    expect(rechartsCalls.area).toHaveBeenCalledWith(expect.objectContaining({
      type: 'monotone',
      dataKey: 'value',
      name: 'ProcBon2Acc',
      stroke: '#4f46e5',
      fill: 'url(#kpiTrendArea)',
      strokeWidth: 2,
    }));
    const areaTooltip = rechartsCalls.tooltip.mock.calls.at(-1)?.[0] as {
      formatter: (value: unknown) => unknown;
    };
    expect(areaTooltip.formatter(60.25)).toBe('60.3%');

    fireEvent.click(screen.getByRole('button', { name: 'Focus' }));
    expect(onKpiMetricChange).toHaveBeenCalledWith('prc_focus_acc_qty');

    fireEvent.change(chartType, { target: { value: 'line' } });
    expect(chartType).toHaveValue('line');
    expect(screen.queryByTestId('area-chart')).not.toBeInTheDocument();
    expect(screen.getByTestId('line-chart')).toBeInTheDocument();
    const lineChartProps = rechartsCalls.lineChart.mock.calls.at(-1)?.[0] as { data: unknown };
    expect(lineChartProps.data).toBe(kpiChartData);
    expect(rechartsCalls.line.mock.calls.at(-1)?.[0]).toEqual(expect.objectContaining({
      type: 'monotone',
      dataKey: 'value',
      name: 'ProcBon2Acc',
      stroke: '#4f46e5',
      strokeWidth: 2,
      dot: false,
    }));
    const lineTooltip = rechartsCalls.tooltip.mock.calls.at(-1)?.[0] as {
      formatter: (value: unknown) => unknown;
    };
    expect(lineTooltip.formatter(60.25)).toBe('60.3%');

    rerender(
      <HistoryKpiTrend
        props={trendProps({
          onKpiMetricChange,
          kpiChartData,
          kpiMetric: 'total_receipts',
        }) as never}
        visible={false}
      />,
    );
    expect(screen.getByRole('combobox', { name: 'Tip grafic KPI' })).toHaveValue('line');
    expect(screen.getByRole('heading', { name: 'Trend KPI' }).closest('.glass')).toHaveClass(
      'hidden',
      'lg:block',
    );
    expect(rechartsCalls.line.mock.calls.at(-1)?.[0]).toEqual(expect.objectContaining({
      dataKey: 'value',
      name: 'Total bonuri',
      stroke: '#4f46e5',
      strokeWidth: 2,
      dot: false,
    }));
    const receiptsTooltip = rechartsCalls.tooltip.mock.calls.at(-1)?.[0] as {
      formatter: (value: unknown) => unknown;
    };
    expect(receiptsTooltip.formatter(60.25)).toBe(formatInt(60.25));

    rerender(
      <HistoryKpiTrend
        props={trendProps({ onKpiMetricChange, kpiChartData }) as never}
        visible
      />,
    );
    expect(screen.getByRole('combobox', { name: 'Tip grafic KPI' })).toHaveValue('line');
    expect(screen.getByTestId('line-chart')).toBeInTheDocument();
  });
});
