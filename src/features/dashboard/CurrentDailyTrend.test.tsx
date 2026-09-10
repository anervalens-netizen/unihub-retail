// @vitest-environment jsdom

import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('recharts', () => {
  const Element = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return {
    Bar: Element,
    CartesianGrid: Element,
    ComposedChart: Element,
    Legend: Element,
    Line: Element,
    ResponsiveContainer: Element,
    Tooltip: Element,
    XAxis: Element,
    YAxis: Element,
  };
});

import { CurrentDailyTrend } from './CurrentDailyTrend';

const data = [
  {
    day: '01',
    sales: 1234,
    qty: 12,
    receipts: 8,
    sales_last_year: 1000,
    sales_forecast: null,
  },
  {
    day: '02',
    sales: null,
    qty: null,
    receipts: null,
    sales_last_year: 1100,
    sales_forecast: 1200,
  },
];

describe('CurrentDailyTrend', () => {
  it('defaults to the chart and exposes the same data as an accessible table without refetch', () => {
    render(<CurrentDailyTrend currentMonth="2026-09" data={data} />);

    expect(screen.getByRole('heading', { name: 'Evolutie zilnica pentru 2026-09' })).toBeInTheDocument();
    expect(screen.getByTestId('current-daily-chart')).toBeInTheDocument();

    const viewSelect = screen.getByRole('combobox', { name: 'Vizualizare evolutie zilnica' });
    fireEvent.change(viewSelect, { target: { value: 'table' } });

    expect(screen.queryByTestId('current-daily-chart')).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Date evolutie zilnica 2026-09' })).toHaveAttribute('tabindex', '0');

    const table = screen.getByRole('table');
    expect(within(table).getByText('Evolutie zilnica pentru 2026-09')).toHaveClass('sr-only');
    expect(within(table).getByRole('columnheader', { name: 'Ziua' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'Vanzari' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'Anul trecut' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'Prognoza' })).toBeInTheDocument();

    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(3);
    expect(within(rows[1]!).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      '1.234',
      '1.000',
      '—',
    ]);
    expect(within(rows[2]!).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      '—',
      '1.100',
      '1.200',
    ]);

    fireEvent.change(viewSelect, { target: { value: 'chart' } });
    expect(screen.getByTestId('current-daily-chart')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});
