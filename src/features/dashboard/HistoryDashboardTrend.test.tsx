// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('recharts', () => ({
  Area: () => null,
  AreaChart: ({ children, data }: { children?: ReactNode; data?: unknown[] }) => (
    <div data-testid="area-chart" data-points={data?.length ?? 0}>{children}</div>
  ),
  Bar: ({ children }: { children?: ReactNode }) => <>{children}</>,
  CartesianGrid: () => null,
  Cell: () => null,
  ComposedChart: ({ children, data }: { children?: ReactNode; data?: unknown[] }) => (
    <div data-testid="composed-chart" data-points={data?.length ?? 0}>{children}</div>
  ),
  Legend: () => null,
  Line: () => null,
  ResponsiveContainer: ({ children }: { children?: ReactNode }) => <>{children}</>,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

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

  it('preserves KPI controls, chart data and responsive visibility class', () => {
    const onKpiMetricChange = vi.fn();
    render(
      <HistoryKpiTrend
        props={trendProps({ onKpiMetricChange }) as never}
        visible={false}
      />,
    );

    const heading = screen.getByRole('heading', { name: 'Trend KPI' });
    expect(heading.closest('.glass')).toHaveClass('hidden', 'lg:block');
    expect(screen.getByTestId('area-chart')).toHaveAttribute('data-points', '1');

    fireEvent.click(screen.getByRole('button', { name: 'Focus' }));
    expect(onKpiMetricChange).toHaveBeenCalledWith('prc_focus_acc_qty');
  });
});
