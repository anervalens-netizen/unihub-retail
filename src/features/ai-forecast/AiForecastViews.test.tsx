// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  current: vi.fn(),
  rolling: vi.fn(),
}));

vi.mock('../../api/aiForecast', () => ({
  getAiForecastCurrent: api.current,
  getAiForecastRolling12: api.rolling,
}));

vi.mock('recharts', () => {
  const Element = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  const Tooltip = ({ formatter, labelFormatter }: {
    formatter?: (value: unknown, name: unknown) => unknown;
    labelFormatter?: (label: unknown, items?: Array<{ payload: Record<string, unknown> }>) => unknown;
  }) => <div>{JSON.stringify([
    formatter?.(123, null),
    labelFormatter?.('', []),
    labelFormatter?.('', [{ payload: { forecast_month: '2026-09', date: '2026-08-01', isWeekend: true } }]),
  ])}</div>;
  return {
    Bar: Element,
    CartesianGrid: Element,
    Cell: Element,
    ComposedChart: Element,
    Legend: Element,
    Line: Element,
    ResponsiveContainer: Element,
    Tooltip,
    XAxis: Element,
    YAxis: Element,
  };
});

vi.mock('../../components/ExportTableButton', () => ({
  ExportTableButton: ({ rows, columns, filename }: { rows: Array<Record<string, unknown>>; columns: Array<{ value: (row: Record<string, unknown>, index: number) => unknown }>; filename: string }) => (
    <button type="button" onClick={() => rows.forEach((row, index) => columns.forEach((column) => column.value(row, index)))}>{`Export fixture ${filename}`}</button>
  ),
}));

import { defaultAppFilters } from '../../lib/filterValues';
import { AiForecastPanel } from './AiForecastPage';
import { ForecastDailyCurveCard, RollingMonthlyChartCard } from './ForecastCharts';
import { ForecastDetailDrawer, ForecastManagerTable, ForecastStoreTable } from './ForecastCurrentTables';
import { ForecastDefinition, ForecastLine } from './ForecastPrimitives';
import { RollingManagerTable, RollingStoreTable } from './ForecastRollingTables';
import {
  buildDailyCurve,
  compareForecastValues,
  deltaTone,
  formatGeneratedAt,
  formatMetricValue,
  formatSignedAmount,
  nextSortDirection,
  riskLabel,
} from './model';

function queryWrapper(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const daily = [
  { forecast_date: '2026-08-01', forecast_sales: 100, actual_sales: 90, has_actual: true, cumulative_forecast: 100, cumulative_actual: 90 },
  { forecast_date: '2026-08-03', forecast_sales: 120, actual_sales: null, has_actual: false, cumulative_forecast: 220, cumulative_actual: null },
];

const managerRows = [
  { manager: 'Zeta', store_count: 1, forecast_sales: 220, expected_sales_to_date: 100, actual_sales: 90, delta_sales: -10, delta_pct: -10 },
  { manager: 'Alfa', store_count: 2, forecast_sales: 440, expected_sales_to_date: 200, actual_sales: 230, delta_sales: 30, delta_pct: 15 },
];

const storeRows = [
  { site_code: 'S2', locatie: 'Zeta Mall', firma: 'Mobiup', asm: 'Zeta', forecast_sales: 220, expected_sales_to_date: 100, actual_sales: 90, delta_sales: -10, delta_pct: -10 },
  { site_code: 'S1', locatie: 'Alfa Mall', firma: 'Mobicell', asm: 'Alfa', forecast_sales: 440, expected_sales_to_date: 200, actual_sales: 230, delta_sales: 30, delta_pct: 15 },
];

const current = {
  summary: {
    forecast_month: '2026-08', source_month: '2025-08', actual_last_date: '2026-08-02',
    forecast_sales: 660, actual_sales: 320, expected_sales_to_date: 300, delta_sales: 20,
    delta_pct: 6.7, store_count: 2, days_elapsed: 2, days_in_month: 31,
  },
  run: { model_mode: 'timesfm', model_name: 'TimesFM 2.5', variant: 'xreg', generated_at: '2026-08-01T10:00:00Z' },
  daily,
  managers: managerRows,
  stores: storeRows,
};

const rolling = {
  summary: {
    start_month: '2026-09', end_month: '2027-08', source_month: '2026-08', forecast_sales: 12000,
    actual_sales: null, delta_sales: null, delta_pct: null, store_count: 2, month_count: 12,
  },
  runs: [{ model_mode: 'timesfm', model_name: 'TimesFM 2.5', variant: 'xreg', generated_at: '2026-08-01T10:00:00Z' }],
  months: [
    { forecast_month: '2026-09', forecast_sales: 1000, actual_sales: null, delta_sales: null, delta_pct: null },
    { forecast_month: '2026-10', forecast_sales: 1100, actual_sales: 1000, delta_sales: -100, delta_pct: -9.1 },
  ],
  managers: managerRows.map(({ expected_sales_to_date: _expected, ...row }) => row),
  stores: storeRows.map(({ expected_sales_to_date: _expected, ...row }) => row),
};

describe('AI forecast critical surfaces', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.current.mockResolvedValue(current);
    api.rolling.mockResolvedValue(rolling);
  });

  it('covers model branches and chart/presentation primitives', () => {
    const curve = buildDailyCurve(daily as never[]);
    expect(curve).toHaveLength(2);
    expect(nextSortDirection('manager', 'manager', 'asc')).toBe('desc');
    expect(nextSortDirection('forecast_sales', 'manager', 'desc')).toBe('asc');
    expect(nextSortDirection('manager', 'forecast_sales', 'asc')).toBe('desc');
    expect(deltaTone(1)).toContain('emerald');
    expect(deltaTone(-1)).toContain('rose');
    expect(deltaTone(null)).toContain('slate');
    expect(formatMetricValue(null, 'units')).toBe('-');
    expect(formatMetricValue(12.4, 'units')).not.toBe('-');
    expect(formatMetricValue(12.4, 'sales_value')).not.toBe('-');
    expect(formatSignedAmount(null, 'units')).toBe('-');
    expect(formatSignedAmount(3, 'units')).toContain('+');
    expect(formatSignedAmount(-3, 'sales_value')).not.toContain('+');
    expect(riskLabel(null)).toBe('Fara reper');
    expect(riskLabel(4)).toBe('Peste ritm');
    expect(riskLabel(-6)).toBe('Risc');
    expect(riskLabel(-1)).toBe('Sub ritm');
    expect(riskLabel(1)).toBe('In ritm');
    expect(formatGeneratedAt(undefined)).toBeTruthy();
    expect(compareForecastValues('forecast_sales', null, null)).toBe(0);
    expect(compareForecastValues('forecast_sales', null, 1)).toBe(-1);
    expect(compareForecastValues('forecast_sales', 1, null)).toBe(1);
    expect(compareForecastValues('forecast_sales', 'bad', 'bad')).toBe(0);
    expect(compareForecastValues('forecast_sales', 'bad', 1)).toBe(-1);
    expect(compareForecastValues('forecast_sales', 1, 'bad')).toBe(1);
    expect(compareForecastValues('forecast_sales', 1, 2)).toBe(-1);
    expect(compareForecastValues('manager', 'Zeta', 'Alfa')).toBeGreaterThan(0);

    render(<><ForecastDefinition term="WAPE" description="eroare" /><ForecastLine label="Model" value="TimesFM" valueClassName="ok" /><ForecastDailyCurveCard title="Curba" subtitle="Detaliu" data={curve} metric="sales_value" /><ForecastDailyCurveCard title="Zero" data={[]} metric="units" /><RollingMonthlyChartCard data={rolling.months as never[]} metric="units" /></>);
    expect(screen.getByText('WAPE:')).toBeInTheDocument();
    expect(screen.getByText('1 zile weekend')).toBeInTheDocument();
  });

  it('renders current data, filters, sorts and opens both detail paths', async () => {
    render(queryWrapper(<AiForecastPanel currentMonth="2026-08" filters={defaultAppFilters()} />));
    expect(await screen.findByText(/AI Forecast — 2026-08/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Cum functioneaza/ }));
    expect(screen.getByText(/TimesFM 2.5 \+ XReg/)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Cauta magazin'), { target: { value: 'alfa' } });
    expect(screen.getByText('1 din 2 magazine in forecast.')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Manager' })[0]!);
    fireEvent.click(screen.getAllByRole('button', { name: 'Forecast' })[0]!);
    fireEvent.click(screen.getAllByRole('button', { name: 'Alfa' })[0]!);
    expect((await screen.findAllByText('RM / ASM')).length).toBeGreaterThan(1);
    fireEvent.click(screen.getByRole('button', { name: 'Inchide' }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Alfa Mall' })[0]!);
    expect((await screen.findAllByText('Magazin')).length).toBeGreaterThan(1);
  }, 30_000);

  it('switches metric and rolling horizon, then searches and sorts', async () => {
    render(queryWrapper(<AiForecastPanel currentMonth="2026-08" filters={defaultAppFilters()} />));
    expect(await screen.findByText(/AI Forecast — 2026-08/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Bucati' }));
    await waitFor(() => expect(api.current).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole('button', { name: '12 luni' }));
    expect(await screen.findByText(/AI Forecast 12 luni/)).toBeInTheDocument();
    expect(screen.getByText(/Nu exista inca realizat/)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('Cauta magazin'), { target: { value: 'zeta' } });
    expect(screen.getByText('1 din 2 magazine in forecast.')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Manager' })[0]!);
    fireEvent.click(screen.getAllByRole('button', { name: 'Magazin' })[0]!);
  });

  it('renders table and drawer branch states directly', () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    const onRetry = vi.fn();
    const { rerender } = render(<><ForecastManagerTable rows={managerRows as never[]} metric="units" onSelect={onSelect} /><ForecastStoreTable rows={storeRows as never[]} metric="sales_value" onSelect={onSelect} /><RollingManagerTable rows={rolling.managers as never[]} metric="sales_value" /><RollingStoreTable rows={rolling.stores as never[]} metric="units" /><ForecastDetailDrawer title="Detaliu" type="store" data={null} metric="units" isLoading isError={false} onClose={onClose} onRetry={onRetry} /></>);
    expect(screen.getByText('Se incarca detaliul forecast...')).toBeInTheDocument();
    screen.getAllByRole('button', { name: /Export fixture/ }).forEach((button) => fireEvent.click(button));
    screen.getAllByRole('button', { name: 'Manager' }).forEach((button) => fireEvent.click(button));
    screen.getAllByRole('button', { name: 'Magazin' }).forEach((button) => fireEvent.click(button));
    rerender(<ForecastDetailDrawer title="Eroare" type="manager" data={null} metric="sales_value" isLoading={false} isError onClose={onClose} onRetry={onRetry} />);
    fireEvent.click(screen.getByRole('button', { name: 'Reincearca' }));
    fireEvent.click(screen.getByRole('button', { name: 'Inchide' }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
    rerender(<ForecastDetailDrawer title="Succes" type="store" data={current as never} metric="sales_value" isLoading={false} isError={false} onClose={onClose} onRetry={onRetry} />);
    expect(screen.getByText(/Curba zilnica/)).toBeInTheDocument();
  });
});
