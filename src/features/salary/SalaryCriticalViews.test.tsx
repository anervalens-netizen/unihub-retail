// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const salaryApi = vi.hoisted(() => ({ history: vi.fn() }));
const hrApi = vi.hoisted(() => ({ asmSalary: vi.fn() }));
const controller = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));

vi.mock('../../api/salarii', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/salarii')>()),
  fetchSalaryAgentHistory: salaryApi.history,
}));

vi.mock('../../api/hr', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/hr')>()),
  fetchAsmSalary: hrApi.asmSalary,
}));

vi.mock('./useSalaryController', () => ({ useSalaryController: () => controller.current }));
vi.mock('../../components/SalaryAreaChart', () => ({ SalaryAreaChart: ({ data }: { data: unknown[] }) => <div>area:{data.length}</div> }));
vi.mock('../../components/SalaryAgentBarChart', () => ({ SalaryAgentBarChart: ({ data }: { data: unknown[] }) => <div>bars:{data.length}</div> }));

import { AsmSalaryGrila } from '../../components/AsmSalaryGrila';
import { SalariiSubtab } from '../../components/SalariiSubtab';
import { SalaryDrawer } from '../../components/SalaryDrawer';
import {
  formatCompactCurrency,
  formatCurrency,
  formatMonthSpan,
  ratioToneStyle,
  salarySalesRatio,
  sortSummary,
  sortTrend,
  summaryMonthOptions,
  toggleSort,
  weightedRatioAverage,
} from './model';

const history = {
  total: 6000,
  avg: 3000,
  month_count: 2,
  avg_month_count: 2,
  records: [
    { year: 2026, month: 8, company_name: 'Mobicell', locatie: 'Promenada', total_salary: 3200 },
    { year: 2026, month: 7, company_name: 'Mobiup', locatie: null, total_salary: 2800 },
  ],
};

const summary = [
  { site_code: 'S2', locatie: null, company_name: 'Unknown', agent_count: 1, avg_agent_count: 1, total_salary: 3000, avg_salary: 3000, total_sales: 30000, ratio: 10 },
  { site_code: 'S1', locatie: 'Alfa', company_name: 'Mobiup', agent_count: 2, avg_agent_count: 1, total_salary: 5000, avg_salary: 2500, total_sales: 100000, ratio: 5 },
];

const trend = [
  { month: '2026-07', agent_count: 2, total_salary: 5000, avg_salary: 2500, total_sales: 100000 },
  { month: '2026-08', agent_count: 1, total_salary: 3000, avg_salary: 3000, total_sales: 0 },
];

function richController() {
  return {
    salaryView: 'overview',
    setSalaryView: vi.fn(),
    overview: { total: 8000, avg_salary: 2667, avg_agent_month_count: 3, agent_count: 2, months_span: [2025, 12, 2026, 2], by_company: [{ name: 'Mobiup', total: 5000 }, { name: 'Mobicell', total: 3000 }] },
    evolution: [{ month: '2026-08', total_salary: 8000 }],
    agents: [
      { person_id: 'p1', full_name: 'Ana Agent', company_name: 'Mobiup', locatie: 'Alfa', total_salary: 5000, avg_salary: 2500, month_count: 2 },
      { person_id: 'p2', full_name: 'Bogdan Agent', company_name: 'Other', locatie: null, total_salary: 3000, avg_salary: 3000, month_count: 1 },
    ],
    totalAgents: 70,
    loading: false,
    search: 'ana',
    debouncedSearch: 'ana',
    page: 1,
    drawer: { personId: 'p1', fullName: 'Ana Agent' },
    setDrawer: vi.fn(),
    selectedSummaryMonth: '2026-02',
    setSelectedSummaryMonth: vi.fn(),
    summaryMonth: '2026-02',
    loadingCards: true,
    summarySort: { key: 'total_salary', dir: 'desc' },
    setSummarySort: vi.fn((updater) => updater({ key: 'total_salary', dir: 'desc' })),
    trendSort: { key: 'month', dir: 'desc' },
    setTrendSort: vi.fn((updater) => updater({ key: 'month', dir: 'desc' })),
    sortedSummary: summary,
    sortedTrend: trend,
    summaryRatioAverage: 6.15,
    trendRatioAverage: 5,
    hasMore: false,
    salaryExport: { busy: null, message: 'Export pregătit', operationId: 17, resume: vi.fn(), start: vi.fn() },
    handleSearchChange: vi.fn(),
    resetSearch: vi.fn(),
    goToPage: vi.fn(),
    startStoreExport: vi.fn(),
    startTrendExport: vi.fn(),
    startAgentsExport: vi.fn(),
    readErrors: {},
    retryRead: vi.fn(),
  };
}

const asmSalary = {
  month: '2026-08', is_forecast: true, forecast_factor: 1.4, fixed_salary: 4000, total_salary: 6200,
  zone: { pct_used: 100, commission: 800 }, islands_commission: 900,
  homogeneity: { qualifying_count: 1, islands_count: 2, min_pct: 99, eligible: false, commission: 0 },
  acc_focus: { pct: 85, commission: 500 },
  islands: [
    { site_code: 'S1', locatie: 'Alfa', firma: 'Mobiup', total_target: 10000, total_sales: 8000, forecast_sales: 11000, target_pct: 80, pct_used: 110, commission: 600, homogeneity_qualifies: true },
    { site_code: 'S2', locatie: 'Beta', firma: 'Mobicell', total_target: 10000, total_sales: 6000, forecast_sales: 7500, target_pct: 60, pct_used: 75, commission: 300, homogeneity_qualifies: false },
  ],
};

describe('salary critical views', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    controller.current = richController();
    salaryApi.history.mockResolvedValue(history);
    hrApi.asmSalary.mockResolvedValue(asmSalary);
  });

  it('covers salary model edge cases', () => {
    expect(toggleSort({ key: 'month', dir: 'asc' }, 'month')).toEqual({ key: 'month', dir: 'desc' });
    expect(toggleSort({ key: 'month', dir: 'asc' }, 'ratio')).toEqual({ key: 'ratio', dir: 'desc' });
    expect(formatMonthSpan(null)).toBeTruthy();
    expect(formatCurrency('bad')).toBe('0');
    expect(formatCurrency('1000')).not.toBe('0');
    expect(formatCompactCurrency(undefined)).toBe('0');
    expect(salarySalesRatio(1, 0)).toBe(0);
    expect(salarySalesRatio(10, 100)).toBe(10);
    expect(weightedRatioAverage([{ total_salary: 10, total_sales: 100 }, { total_salary: 0, total_sales: 0 }])).toBe(10);
    expect(ratioToneStyle(Number.NaN, 4).color).toContain('45');
    expect(ratioToneStyle(5.1, 5).color).toContain('45');
    expect(ratioToneStyle(20, 5).color).toContain('0');
    expect(ratioToneStyle(1, 20).color).toContain('140');
    expect(summaryMonthOptions(null)).toEqual([]);
    expect(summaryMonthOptions([2025, 12, 2026, 2])).toEqual(['2026-02', '2026-01', '2025-12']);
    expect(sortSummary(summary as never[], { key: 'locatie', dir: 'asc' })[0]!.site_code).toBe('S1');
    expect(sortSummary(summary as never[], { key: 'company_name', dir: 'desc' })[0]!.company_name).toBe('Unknown');
    expect(sortSummary(summary as never[], { key: 'ratio', dir: 'asc' })[0]!.ratio).toBe(5);
    expect(sortTrend(trend as never[], { key: 'month', dir: 'asc' })[0]!.month).toBe('2026-07');
    expect(sortTrend(trend as never[], { key: 'ratio', dir: 'desc' })[0]!.month).toBe('2026-07');
    expect(sortTrend(trend as never[], { key: 'total_salary', dir: 'asc' })[0]!.month).toBe('2026-08');
  });

  it('renders all salary panels and executes their accessible controls without exporting live', async () => {
    render(<SalariiSubtab />);
    expect(screen.getByText('Statistici Salarii')).toBeInTheDocument();
    expect(await screen.findByText(/Istoric salarial/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Magazine' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Agenți' }));
    fireEvent.change(screen.getByDisplayValue('2026-02'), { target: { value: '2026-01' } });
    fireEvent.change(screen.getByPlaceholderText('Cauta...'), { target: { value: 'bogdan' } });
    fireEvent.click(screen.getByRole('button', { name: 'Reseteaza' }));
    fireEvent.click(screen.getByRole('button', { name: 'Inapoi' }));
    fireEvent.click(screen.getByRole('button', { name: 'Închide istoricul salarial' }));
    expect((controller.current.setSalaryView as ReturnType<typeof vi.fn>)).toHaveBeenCalled();
    expect((controller.current.resetSearch as ReturnType<typeof vi.fn>)).toHaveBeenCalled();
  });

  it('renders empty panels, drawer retry and overlay close branches', async () => {
    controller.current = { ...richController(), overview: null, sortedSummary: [], sortedTrend: [], agents: [], totalAgents: 0, loading: false, loadingCards: false, search: '', drawer: null, salaryExport: { busy: 'agents', message: null, operationId: null, resume: vi.fn(), start: vi.fn() } };
    const { rerender } = render(<SalariiSubtab />);
    expect(screen.getAllByText('Fără date').length).toBeGreaterThan(1);
    expect(screen.getAllByText('Nu s-au găsit agenți').length).toBeGreaterThan(1);

    salaryApi.history.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(history);
    const onClose = vi.fn();
    rerender(<SalaryDrawer personId="p1" fullName="Ana" isOpen onClose={onClose} />);
    expect(await screen.findByText('Nu s-au putut încărca datele')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Detalii Lunare')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Închide istoricul salarial' }));
    expect(onClose).toHaveBeenCalledOnce();
    rerender(<SalaryDrawer personId="" fullName="" isOpen={false} onClose={onClose} />);
    expect(screen.queryByText('Detalii Lunare')).not.toBeInTheDocument();
  });

  it('surfaces a per-read-path error banner and clears it on retry', async () => {
    controller.current = {
      ...richController(),
      overview: null,
      sortedSummary: [],
      sortedTrend: [],
      agents: [],
      totalAgents: 0,
      loading: false,
      loadingCards: false,
      readErrors: {
        summary: 'Comparația salarii vs vânzări nu a putut fi încărată.',
        agents: 'Lista de agenți nu a putut fi încărcată.',
      },
      retryRead: vi.fn(),
    };
    controller.current.retryRead = vi.fn();
    render(<SalariiSubtab />);
    const banner = screen.getByRole('alert');
    expect(banner.textContent).toMatch(/nu au putut fi încărcate pentru: .*lista de agenți/);
    fireEvent.click(screen.getByRole('button', { name: /Reîncarcă agenți/ }));
    expect((controller.current.retryRead as ReturnType<typeof vi.fn>)).toHaveBeenCalledWith('agents');
  });

  it('renders forecast/final ASM grids and exposes reload/error states', async () => {
    const { rerender } = render(<AsmSalaryGrila asm="Manager" defaultMonth="2026-08" />);
    expect(await screen.findByText(/Salariu estimat/)).toBeInTheDocument();
    expect(screen.getByText(/neeligibil/)).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('Reîncarcă'));
    await waitFor(() => expect(hrApi.asmSalary).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByDisplayValue('2026-08'), { target: { value: '2026-07' } });
    await waitFor(() => expect(hrApi.asmSalary).toHaveBeenCalledWith('Manager', '2026-07'));

    hrApi.asmSalary.mockRejectedValueOnce('offline');
    rerender(<AsmSalaryGrila key="alt" asm="Alt Manager" defaultMonth="2026-06" />);
    expect(await screen.findByText('Eroare la încărcarea grilei')).toBeInTheDocument();
    hrApi.asmSalary.mockResolvedValueOnce({ ...asmSalary, is_forecast: false, month: '2026-05', homogeneity: { ...asmSalary.homogeneity, eligible: true }, zone: { pct_used: null, commission: 0 }, acc_focus: { pct: null, commission: 0 } });
    fireEvent.change(screen.getByDisplayValue('2026-06'), { target: { value: '2026-05' } });
    expect(await screen.findByText(/Salariu final/)).toBeInTheDocument();
  });
});
