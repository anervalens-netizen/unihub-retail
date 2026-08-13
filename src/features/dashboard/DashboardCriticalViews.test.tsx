// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('recharts', () => {
  const Element = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  const Tooltip = ({ formatter }: { formatter?: (value: unknown) => unknown }) => <span>{String(formatter?.(123) ?? '')}</span>;
  return { Cell: Element, Pie: Element, PieChart: Element, ResponsiveContainer: Element, Tooltip };
});
vi.mock('../ai-forecast/AiForecastPage', () => ({ AiForecastPanel: () => <div>Forecast fixture</div> }));
vi.mock('./PerformanceDetailSections', () => ({ PerformanceDetailContent: ({ canViewSalaries }: { canViewSalaries: boolean }) => <div>{canViewSalaries ? 'Detaliu cu salarii' : 'Detaliu fara salarii'}</div> }));
vi.mock('./usePerformanceDetailModel', () => ({ usePerformanceDetailModel: () => ({}) }));

import { CurrentDashboard } from './CurrentDashboard';
import { PerformanceDetailDrawer } from './PerformanceDetailDrawer';
import { CompactCurrency, CompactPieSection, DeltaCard, KpiPerformanceCard, PeriodTable } from './DashboardWidgets';
import { getBon2AccTone } from './DashboardWidgets';
import { defaultAppFilters } from '../../lib/filterValues';

const point = { label: 'Curent', month: '2026-08', day_range: '1-9', total_sales: 1000, total_quantity: 10, total_receipts: 5, working_days: 9, daily_average: 111, avg_receipt_value: 200, medie_produs: 100, proc_bon2acc: 40, prc_focus_acc_qty: 20, cartele_qty: 1 };

describe('Dashboard critical view branches', () => {
  it('renders KPI donuts in compact, side-by-side, regular and empty variants', () => {
    const data = Array.from({ length: 7 }, (_, index) => ({ name: `N${index}`, value: index + 1, share_pct: index * 10 }));
    render(<>
      <KpiPerformanceCard title="KPI" value={40} tone={getBon2AccTone(40)} chartData={data} dataKey="value" nameKey="name" formatValue={String} />
      <CompactPieSection title="Gol" emptyLabel="Fara date" pieData={[]} dataKey="value" nameKey="name" valueFormatter={String} centerValue="0" />
      <CompactPieSection title="Compact" emptyLabel="Fara" pieData={data} dataKey="value" nameKey="name" valueFormatter={String} centerValue="28" compact />
      <CompactPieSection title="Normal" emptyLabel="Fara" pieData={data} dataKey="value" nameKey="name" valueFormatter={String} centerValue="28" />
    </>);
    expect(screen.getByText('Fara date')).toBeInTheDocument();
    expect(screen.getAllByTestId('donut-legend-layout').length).toBeGreaterThan(2);
  });

  it('renders period rows, compact currency and every delta polarity/null branch', () => {
    render(<>
      <PeriodTable current={point as never} previous={{ ...point, label: 'Anterior', daily_average: null, medie_produs: null, avg_receipt_value: null, proc_bon2acc: null, prc_focus_acc_qty: null, cartele_qty: null } as never} yoy={{ ...point, label: 'An anterior' } as never} />
      <DeltaCard title="Pozitiv" salesDelta={10} salesPct={1} receiptsDelta={2} receiptsPct={2} quantityDelta={3} quantityPct={3} compact />
      <DeltaCard title="Negativ" salesDelta={-10} salesPct={null} receiptsDelta={-2} receiptsPct={null} quantityDelta={-3} quantityPct={null} />
      <CompactCurrency value={1234} />
    </>);
    expect(screen.getByText('Pozitiv')).toBeInTheDocument();
    expect(screen.getByText('Negativ')).toBeInTheDocument();
    expect(screen.getAllByTestId('hub-delta-value')).toHaveLength(6);
  });

  it('renders forecast mode and all performance drawer conditional content', () => {
    const currentProps = { currentMonth: '2026-08', filters: defaultAppFilters(), mode: 'forecast', onModeChange: vi.fn(), statusLabel: '', summary: {}, receiptBucketChartData: [], focusSubcategoryChartData: [], periodComparison: null, comparisonDeltas: null, dailyChartData: [], categoryMixChartData: [], brandMixChartData: [], filterScopeLabel: '', regionals: [], sortedRegionals: [], regionalColumns: [], regionalSort: { key: 'regional', direction: 'asc' }, onSortRegionals: vi.fn(), stores: [], sortedStores: [], storeColumns: [], storeSort: { key: 'locatie', direction: 'asc' }, onSortStores: vi.fn(), agents: [], sortedAgents: [], agentColumns: [], agentSort: { key: 'agent', direction: 'asc' }, onSortAgents: vi.fn() };
    const close = vi.fn();
    const { rerender } = render(<><CurrentDashboard {...currentProps as unknown as ComponentProps<typeof CurrentDashboard>} /><PerformanceDetailDrawer open selection={null} detail={null} loading error="" canViewSalaries={false} onClose={close} /></>);
    expect(screen.getByText('Forecast fixture')).toBeInTheDocument();
    expect(screen.getByText('Incarc detaliile de performanta...')).toBeInTheDocument();
    rerender(<PerformanceDetailDrawer open selection={{ level: 'regional', key: 'Nord' }} detail={{ title: 'Nord' } as never} loading={false} error="Eroare" canViewSalaries onClose={close} />);
    expect(screen.getByText('Performanta · Nord')).toBeInTheDocument();
    expect(screen.getByText('Eroare')).toBeInTheDocument();
    expect(screen.getByText('Detaliu cu salarii')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Inchide' }));
    expect(close).toHaveBeenCalled();
  });
});
