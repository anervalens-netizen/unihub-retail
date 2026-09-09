// @vitest-environment jsdom

import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('recharts', () => {
  const Chart = ({ children }: { children?: ReactNode }) => (
    <svg data-testid="kpi-chart">{children}</svg>
  );
  const Empty = () => null;
  return {
    Area: Empty, AreaChart: Chart, Bar: Empty, CartesianGrid: Empty,
    Cell: Empty, ComposedChart: Chart, Legend: Empty, Line: Empty,
    LineChart: Chart, Tooltip: Empty, XAxis: Empty, YAxis: Empty,
    ResponsiveContainer: ({ children }: { children?: ReactNode }) => <>{children}</>,
  };
});

import { formatInt } from '../../lib/formatters';
import { HistoryKpiTrend } from './HistoryDashboardTrend';

type KpiProps = ComponentProps<typeof HistoryKpiTrend>['props'];

function kpiProps(overrides: Partial<KpiProps> = {}): KpiProps {
  return {
    currentHistoryLoading: false,
    kpiMetric: 'proc_bon2acc',
    onKpiMetricChange: vi.fn(),
    kpiChartData: [
      { month: '2026-06', value: 59.75 },
      { month: '2026-07', value: 60.25 },
    ],
    ...overrides,
  };
}

function selectTable() {
  fireEvent.change(screen.getByRole('combobox', { name: 'Tip grafic KPI' }), {
    target: { value: 'table' },
  });
}

describe('History KPI accessible data table', () => {
  it('shows the same ordered values and metric formatters, with local view persistence', () => {
    const props = kpiProps();
    const originalRows = props.kpiChartData.map((point) => ({ ...point }));
    const { rerender } = render(<HistoryKpiTrend props={props} visible />);
    expect(screen.getByRole('combobox', { name: 'Tip grafic KPI' })).toHaveValue('area');
    selectTable();

    const table = screen.getByRole('table', { name: 'Trend KPI — ProcBon2Acc' });
    expect(within(table).getAllByRole('rowheader').map((cell) => cell.textContent))
      .toEqual(['2026-06', '2026-07']);
    expect(within(table).getAllByRole('cell').map((cell) => cell.textContent))
      .toEqual(['59.8%', '60.3%']);
    expect(within(table).getByRole('columnheader', { name: 'Luna' })).toHaveAttribute('scope', 'col');
    expect(screen.getByRole('region', { name: 'Date Trend KPI' })).toHaveAttribute('tabindex', '0');
    expect(screen.queryByTestId('kpi-chart')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Bon2Acc' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'Focus' }));
    expect(props.onKpiMetricChange).toHaveBeenLastCalledWith('prc_focus_acc_qty');
    rerender(<HistoryKpiTrend props={{ ...props, kpiMetric: 'prc_focus_acc_qty' }} visible />);
    expect(screen.getByRole('table', { name: 'Trend KPI — PrcFocus/AccQtty' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Focus' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Bon2Acc' })).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'Bonuri' }));
    expect(props.onKpiMetricChange).toHaveBeenLastCalledWith('total_receipts');
    const receipts = { ...props, kpiMetric: 'total_receipts' as const };
    rerender(<HistoryKpiTrend props={receipts} visible />);
    const receiptTable = screen.getByRole('table', { name: 'Trend KPI — Total bonuri' });
    expect(within(receiptTable).getAllByRole('cell').map((cell) => cell.textContent))
      .toEqual(originalRows.map((point) => formatInt(point.value)));

    rerender(<HistoryKpiTrend props={receipts} visible={false} />);
    rerender(<HistoryKpiTrend props={receipts} visible />);
    expect(screen.getByRole('combobox', { name: 'Tip grafic KPI' })).toHaveValue('table');
    expect(props.kpiChartData).toEqual(originalRows);

    fireEvent.change(screen.getByRole('combobox', { name: 'Tip grafic KPI' }), {
      target: { value: 'area' },
    });
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByTestId('kpi-chart')).toBeInTheDocument();
  });

  it('distinguishes empty data from loading without inventing zero values', () => {
    const props = kpiProps({ kpiChartData: [] });
    const { rerender } = render(<HistoryKpiTrend props={props} visible />);
    selectTable();
    expect(screen.getByRole('status')).toHaveTextContent('Nu există date KPI pentru filtrele selectate.');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();

    const loadedProps = kpiProps();
    rerender(<HistoryKpiTrend props={{ ...loadedProps, currentHistoryLoading: true }} visible />);
    expect(screen.getByText('Se incarca...')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    rerender(<HistoryKpiTrend props={loadedProps} visible />);
    expect(screen.getByRole('combobox', { name: 'Tip grafic KPI' })).toHaveValue('table');
    expect(screen.getByRole('table', { name: 'Trend KPI — ProcBon2Acc' })).toBeInTheDocument();
  });
});
