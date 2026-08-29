// @vitest-environment jsdom

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { createRef } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ detail: vi.fn() }));
vi.mock('./api', () => ({ fetchTargetStoreDetail: api.detail }));
vi.mock('recharts', () => {
  const Element = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  const Formatter = ({ tickFormatter, formatter }: { tickFormatter?: (value: unknown) => unknown; formatter?: (value: unknown) => unknown }) => <span>{String(tickFormatter?.(1200) ?? formatter?.(1200) ?? '')}</span>;
  return { Bar: Element, BarChart: Element, CartesianGrid: Element, ComposedChart: Element, Legend: Element, Line: Element, ResponsiveContainer: Element, Tooltip: Formatter, XAxis: Formatter, YAxis: Formatter };
});

import { TargetAgentDetails } from './TargetAgentDetails';
import { TargetAllocationTable } from './TargetAllocationTable';
import { TargetConfiguration } from './TargetConfiguration';
import { TargetRegionalOverview } from './TargetRegionalOverview';
import { TargetStoreAllocation } from './TargetStoreAllocation';

const scenario = { id: 7, status: 'draft', target_month: '2026-09', store_count: 1 };
const baseRow = {
  site_code: 'S1', locatie: 'Alfa', firma: 'Mobiup', regional: 'Nord', proposed_target: 1000, final_target: 1050, normalized_weight: 1, note: null,
  history: [{ month: '2026-07', target: 900, realized: 950, attainment_pct: 105 }], calculation_details: { flags: [] },
  profitability: { agent_count: 1, base_salary_per_agent: 1, salary_cost_at_90_pct: 100, operating_costs: 200, accessory_margin_pct: 30, break_even_gross_sales: 800, forecast_sales: 1100, anomaly_flags: [] },
};

function model(overrides: Record<string, unknown> = {}) {
  return {
    scenario, context: { can_finalize: true }, busy: false, filteredRows: [baseRow], resetToProposal: vi.fn(), handleSave: vi.fn(), handleFinalize: vi.fn(), handleExport: vi.fn(), profitabilitySummary: null, regionalFilter: 'all', dirty: true,
    locationFilterRef: createRef<HTMLDivElement>(), locationDropdownOpen: true, setLocationDropdownOpen: vi.fn(), selectedLocationCodes: ['S1', 'missing'], selectedLocationSet: new Set(['S1']), setSelectedLocationCodes: vi.fn(), locationOptions: [baseRow], toggleLocationFilter: vi.fn(), removeLocationFilter: vi.fn(),
    displaySourceMonths: [{ month: '2026-07', label: 'Iulie', role: 'history' }], tableTotals: { history: [{ month: '2026-07', target: 900, realized: 950, attainment: 105 }], normalizedWeight: 1, proposedTarget: 1000, finalTarget: 1050, salary: 100, operatingCosts: 200, breakEven: 800, forecast: 1100 }, updateRow: vi.fn(), setDetailSiteCode: vi.fn(),
    regionalChart: [], sourceChart: [], isDesktop: false,
    ...overrides,
  };
}

const history = [
  { month: '2026-07', total_sales: 1000, target_value: 900, target_pct: 111, total_quantity: 10, receipt_count: 5, avg_receipt: 200, bon2acc_pct: 30, focus_pct: 8, working_days: 20, cartele_qty: 2, active_agents: 1 },
  { month: '2026-08', total_sales: 1200, target_value: 1100, target_pct: 109, total_quantity: 12, receipt_count: 6, avg_receipt: null, bon2acc_pct: null, focus_pct: null, working_days: 21, cartele_qty: 1, active_agents: 2 },
];
const detail = {
  site_code: 'S1', locatie: 'Alfa', firma: 'Mobiup', regional: 'Nord', asm: 'ASM', cohort_month: '2026-08', target_month: '2026-09', avg_sales_16m: 1100, proposed_target: 1300, final_target: null,
  latest: history[1], best_month: history[0], history,
  agents: [{ agent: 'Ana', total_sales: 800, sales_16m: 8000, sales_share_pct: 80, active_months_16: 12, receipt_count: 4, total_quantity: 8, avg_receipt: 200, bon2acc_pct: 30, focus_pct: 8 }],
};

describe('Target critical views', () => {
  beforeEach(() => { vi.clearAllMocks(); api.detail.mockResolvedValue(detail); vi.spyOn(console, 'error').mockImplementation(() => undefined); });

  it('covers configuration authorization, controls, formula and busy states', () => {
    const reload = vi.fn(async () => undefined); const calculate = vi.fn(async () => undefined); const setLogic = vi.fn();
    const setTargetMonth = vi.fn(); const setTotalTarget = vi.fn(); const setMinFloor = vi.fn();
    const { rerender } = render(<TargetConfiguration context={null} busy={false} loadInitial={reload} targetMonth="2026-09" setTargetMonth={vi.fn()} totalTarget="1000" setTotalTarget={vi.fn()} minFloor="100" setMinFloor={vi.fn()} seasonalityMode="multi" selectSeasonalityMode={vi.fn()} handleCalculate={calculate} logicOpen={false} setLogicOpen={setLogic} />);
    expect(screen.queryByText('Calculator Target')).not.toBeInTheDocument();
    rerender(<TargetConfiguration context={{ can_finalize: true, latest_sales_month: '2026-08', active_store_count: 2 } as never} busy={false} loadInitial={reload} targetMonth="2026-09" setTargetMonth={setTargetMonth} totalTarget="1000" setTotalTarget={setTotalTarget} minFloor="100" setMinFloor={setMinFloor} seasonalityMode="multi" selectSeasonalityMode={vi.fn()} handleCalculate={calculate} logicOpen setLogicOpen={setLogic} />);
    fireEvent.change(screen.getByLabelText('Luna target'), { target: { value: '2026-10' } });
    fireEvent.change(screen.getByLabelText('Target total (RON)'), { target: { value: '2000' } });
    fireEvent.change(screen.getByLabelText('Prag minim (RON)'), { target: { value: '200' } });
    fireEvent.click(screen.getByTitle('Reincarca'));
    fireEvent.click(screen.getByRole('button', { name: /Calculeaza propunerea/ }));
    fireEvent.click(screen.getByRole('button', { name: /Logica de calcul/ }));
    expect(screen.getByText(/Estimare bruta/)).toBeInTheDocument();
    expect(setTargetMonth).toHaveBeenCalledWith('2026-10'); expect(setTotalTarget).toHaveBeenCalledWith('2000'); expect(setMinFloor).toHaveBeenCalledWith('200');
    expect(reload).toHaveBeenCalled(); expect(calculate).toHaveBeenCalled(); expect(setLogic).toHaveBeenCalled();
  });

  it('renders allocation signals and null/rich regional variants', () => {
    const allocations = ['Peste AI', 'Peste sezonier', 'OK'].map((signal, index) => ({ manager: `M${index}`, storeCount: 1, targetShare: 30, targetVsPreviousSharePp: index - 1, target: 100, targetVsPreviousPct: 1, targetVsSeasonalPct: 2, targetVsPreviousYearPct: 3, targetVsForecastPct: 4, signal }));
    const { rerender } = render(<><TargetAllocationTable regionalAllocation={allocations} /><TargetRegionalOverview model={model({ scenario: null }) as never} /><TargetStoreAllocation model={model({ scenario: null }) as never} /></>);
    expect(screen.getByText('Peste AI')).toBeInTheDocument();
    const regionals = [
      { regional: 'Sub', store_count: 1, proposed_total: 100, final_total: 90, current_month: null, current_forecast_total: 80, proposed_growth_vs_current_pct: 25, last_year_base_month: null, last_year_target_month: null, last_year_base_total: 60, last_year_target_total: 70, last_year_growth_pct: 16 },
      { regional: 'Peste', store_count: 1, proposed_total: 100, final_total: 110, current_month: '2026-08', current_forecast_total: 100, proposed_growth_vs_current_pct: 0, last_year_base_month: '2025-08', last_year_target_month: '2025-09', last_year_base_total: 90, last_year_target_total: 95, last_year_growth_pct: 5 },
      { regional: 'Limita', store_count: 1, proposed_total: 0, final_total: 0, current_month: '2026-08', current_forecast_total: 0, proposed_growth_vs_current_pct: null, last_year_base_month: null, last_year_target_month: null, last_year_base_total: 0, last_year_target_total: 0, last_year_growth_pct: null },
    ];
    const sources = [{ month: '2026-08', target: 100, realized: 90, actualRealized: 80, isForecast: true, showTarget: true }, { month: '2026-07', target: 80, realized: 75, actualRealized: 75, isForecast: false, showTarget: false }];
    rerender(<><TargetRegionalOverview model={model({ regionalChart: regionals, sourceChart: sources, isDesktop: true, regionalFilter: 'Nord' }) as never} /><TargetStoreAllocation model={model() as never} /></>);
    expect(screen.getAllByText('Sub calculator').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Peste +5%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('In limita').length).toBeGreaterThan(0);
    expect(screen.getByText('Baza istorica - Nord')).toBeInTheDocument();
  });

  it('loads store detail, switches all chart modes and closes both ways', async () => {
    const close = vi.fn();
    const { rerender } = render(<TargetAgentDetails scenarioId={7} siteCode={null} onClose={close} />);
    expect(screen.queryByText('Detalii locatie')).not.toBeInTheDocument();
    rerender(<TargetAgentDetails scenarioId={7} siteCode="S1" onClose={close} />);
    expect(screen.getByText('Se incarca detaliile...')).toBeInTheDocument();
    expect(await screen.findByText('KPI ultima luna')).toBeInTheDocument();
    expect(screen.getByText('Ana')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Bon2Acc' }));
    expect(screen.getByText(/Bon2Acc - 16 luni/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Focus/Acc' }));
    expect(screen.getByText(/Focus\/Acc - 16 luni/)).toBeInTheDocument();
    const overlay = screen.getByText('Detalii locatie').closest('.fixed') as HTMLElement;
    fireEvent.click(overlay.querySelector('button')!);
    expect(close).toHaveBeenCalled();
    fireEvent.click(overlay);
    expect(close).toHaveBeenCalledTimes(2);
  });

  it('shows detail errors and empty agent/latest branches', async () => {
    api.detail.mockRejectedValueOnce(new Error('offline'));
    const { rerender } = render(<TargetAgentDetails scenarioId={7} siteCode="bad" onClose={vi.fn()} />);
    expect(await screen.findByText('Nu am putut incarca detaliile locatiei.')).toBeInTheDocument();
    api.detail.mockResolvedValueOnce({ ...detail, latest: null, best_month: null, agents: [], final_target: 1200 });
    rerender(<TargetAgentDetails key="empty" scenarioId={8} siteCode="S2" onClose={vi.fn()} />);
    expect(await screen.findByText('Nu exista agenti activi in luna cohortei.')).toBeInTheDocument();
    await waitFor(() => expect(api.detail).toHaveBeenCalledTimes(2));
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const storeDetailA = { ...detail, site_code: 'S1', locatie: 'Alfa' };
const storeDetailB = { ...detail, site_code: 'S2', locatie: 'Beta' };
const storeDetailBHeader = 'Detalii locatie';

describe('TargetAgentDetails latest-request-wins', () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    vi.clearAllMocks();
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });
  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('discards a stale success when a newer site request already published B', async () => {
    const a = deferred<typeof detail>();
    const b = deferred<typeof detail>();
    api.detail.mockImplementationOnce(() => a.promise).mockImplementationOnce(() => b.promise);

    const { rerender } = render(<TargetAgentDetails scenarioId={7} siteCode="S1" onClose={vi.fn()} />);
    expect(await screen.findByText('Se incarca detaliile...')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('S1');
    await waitFor(() => expect(api.detail).toHaveBeenCalledWith(7, 'S1'));

    rerender(<TargetAgentDetails scenarioId={7} siteCode="S2" onClose={vi.fn()} />);
    expect(await screen.findByText('Se incarca detaliile...')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('S2');
    await waitFor(() => expect(api.detail).toHaveBeenCalledWith(7, 'S2'));

    await act(async () => { b.resolve(storeDetailB); });
    expect(await screen.findByText(storeDetailBHeader)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Beta');
    expect(api.detail).toHaveBeenCalledTimes(2);

    await act(async () => { a.resolve(storeDetailA); });
    await waitFor(() => expect(api.detail).toHaveBeenCalledTimes(2));

    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Beta');
    expect(screen.queryByText('Alfa')).not.toBeInTheDocument();
    expect(screen.getByText(storeDetailBHeader)).toBeInTheDocument();
    expect(api.detail).toHaveBeenCalledTimes(2);
  });

  it('discards a stale failure so no obsolete error appears for the newer selection', async () => {
    const a = deferred<typeof detail>();
    const b = deferred<typeof detail>();
    api.detail.mockImplementationOnce(() => a.promise).mockImplementationOnce(() => b.promise);

    const { rerender } = render(<TargetAgentDetails scenarioId={7} siteCode="S1" onClose={vi.fn()} />);
    expect(await screen.findByText('Se incarca detaliile...')).toBeInTheDocument();
    await waitFor(() => expect(api.detail).toHaveBeenCalledWith(7, 'S1'));

    rerender(<TargetAgentDetails scenarioId={7} siteCode="S2" onClose={vi.fn()} />);
    expect(await screen.findByText('Se incarca detaliile...')).toBeInTheDocument();
    await waitFor(() => expect(api.detail).toHaveBeenCalledWith(7, 'S2'));

    await act(async () => { b.resolve(storeDetailB); });
    expect(await screen.findByText('Beta')).toBeInTheDocument();
    expect(api.detail).toHaveBeenCalledTimes(2);

    await act(async () => { a.reject(new Error('A failed late')); });
    await waitFor(() => expect(api.detail).toHaveBeenCalledTimes(2));

    expect(consoleErrorSpy).not.toHaveBeenCalled();
    expect(screen.queryByText(/Nu am putut incarca/)).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Beta');
  });

  it('keeps the newer request in a loading state when an older request settles first', async () => {
    const a = deferred<typeof detail>();
    const b = deferred<typeof detail>();
    api.detail.mockImplementationOnce(() => a.promise).mockImplementationOnce(() => b.promise);

    const { rerender } = render(<TargetAgentDetails scenarioId={7} siteCode="S1" onClose={vi.fn()} />);
    expect(await screen.findByText('Se incarca detaliile...')).toBeInTheDocument();
    await waitFor(() => expect(api.detail).toHaveBeenCalledWith(7, 'S1'));

    rerender(<TargetAgentDetails scenarioId={7} siteCode="S2" onClose={vi.fn()} />);
    expect(await screen.findByText('Se incarca detaliile...')).toBeInTheDocument();
    await waitFor(() => expect(api.detail).toHaveBeenCalledWith(7, 'S2'));

    await act(async () => { a.resolve(storeDetailA); });
    await waitFor(() => expect(api.detail).toHaveBeenCalledTimes(2));

    expect(screen.getByText('Se incarca detaliile...')).toBeInTheDocument();
    expect(screen.queryByText('Alfa')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('S2');

    await act(async () => { b.resolve(storeDetailB); });
    expect(await screen.findByText('Beta')).toBeInTheDocument();
    expect(screen.getByText(storeDetailBHeader)).toBeInTheDocument();
  });

  it('treats completion after unmount as a no-op (no visible effect, no console.error)', async () => {
    const a = deferred<typeof detail>();
    api.detail.mockImplementationOnce(() => a.promise);

    const { unmount } = render(<TargetAgentDetails scenarioId={7} siteCode="S1" onClose={vi.fn()} />);
    expect(await screen.findByText('Se incarca detaliile...')).toBeInTheDocument();
    await waitFor(() => expect(api.detail).toHaveBeenCalledWith(7, 'S1'));

    unmount();

    await act(async () => { a.reject(new Error('rejected after unmount')); });
    await waitFor(() => expect(api.detail).toHaveBeenCalledTimes(1));

    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });
});
