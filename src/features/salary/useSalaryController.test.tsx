// @vitest-environment jsdom

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  SalariiOverview,
  SalaryAgentSummary,
  SalaryComparisonPoint,
  SalaryEvolutionPoint,
  SalaryTrendMonth,
} from '../../api/salarii';
import type { AppFilters } from '../../lib/appFilters';
import { ALL_FIRMS, ALL_SCOPE } from '../../lib/filterValues';

const api = vi.hoisted(() => ({
  fetchSalariiOverview: vi.fn(),
  fetchSalaryAgents: vi.fn(),
  fetchSalaryEvolution: vi.fn(),
  fetchSalarySummary: vi.fn(),
  fetchSalaryTrend: vi.fn(),
  startExport: vi.fn(),
}));

vi.mock('../../api/salarii', () => ({
  fetchSalariiOverview: api.fetchSalariiOverview,
  fetchSalaryAgents: api.fetchSalaryAgents,
  fetchSalaryEvolution: api.fetchSalaryEvolution,
  fetchSalarySummary: api.fetchSalarySummary,
  fetchSalaryTrend: api.fetchSalaryTrend,
}));

vi.mock('./SalaryExportControls', () => ({
  useSalaryExport: () => ({
    busy: null,
    message: '',
    operationId: null,
    resume: vi.fn(),
    start: api.startExport,
  }),
}));

import { useSalaryController } from './useSalaryController';

const defaultFilters: AppFilters = { firma: ALL_FIRMS, rm: ALL_SCOPE, magazin: [], agent: [] };
const scopedFilters: AppFilters = { firma: 'Mobiup', rm: 'Nord', magazin: ['MA'], agent: [] };
const scopedScope = { company_name: 'Mobiup', site_code: ['MA'], regional: 'Nord' };

const comparisonPoint = (overrides: Partial<SalaryComparisonPoint>): SalaryComparisonPoint => ({
  agent_count: 1,
  avg_agent_count: 1,
  avg_salary: 1000,
  company_name: 'Mobiup',
  locatie: 'Beta',
  ratio: 10,
  site_code: 'SB',
  total_salary: 3000,
  total_sales: 30000,
  ...overrides,
} as unknown as SalaryComparisonPoint);

const summaryItems = [
  comparisonPoint({ locatie: 'Beta', site_code: 'SB', total_salary: 3000, total_sales: 30000 }),
  comparisonPoint({ locatie: 'Alpha', site_code: 'SA', company_name: 'Mobicell', total_salary: 1000, total_sales: 20000 }),
  comparisonPoint({ locatie: 'Gamma', site_code: 'SG', total_salary: 2000, total_sales: 10000 }),
];

const trendPoints: SalaryTrendMonth[] = [
  { month: '2026-04', total_salary: 100, total_sales: 1000, agent_count: 1, avg_agent_count: 1, avg_salary: 100 },
  { month: '2026-05', total_salary: 200, total_sales: 1000, agent_count: 1, avg_agent_count: 1, avg_salary: 200 },
] as unknown as SalaryTrendMonth[];

const evolutionPoints: SalaryEvolutionPoint[] = [
  { month: '2026-05', total: '9000', mobicell: '4000', mobiup: '5000' },
] as unknown as SalaryEvolutionPoint[];

const agentSummary: SalaryAgentSummary = {
  avg_month_count: 3,
  avg_salary: '1500',
  company_name: 'Mobiup',
  full_name: 'Ion Pop',
  locatie: 'Mag A',
  month_count: 3,
  person_id: 'p1',
  total_salary: '4500',
} as unknown as SalaryAgentSummary;

const overviewFixture = { total_agents: 7 } as unknown as SalariiOverview;

describe('useSalaryController', () => {
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    api.fetchSalariiOverview.mockResolvedValue(overviewFixture);
    api.fetchSalaryEvolution.mockResolvedValue(evolutionPoints);
    api.fetchSalarySummary.mockResolvedValue({ items: summaryItems, month: '2026-05' });
    api.fetchSalaryTrend.mockResolvedValue(trendPoints);
    api.fetchSalaryAgents.mockResolvedValue({ items: [agentSummary], total: 1 });
    api.startExport.mockResolvedValue(undefined);
  });

  afterEach(() => {
    consoleError.mockRestore();
  });

  it('loads every salary section with the scoped global filters', async () => {
    const { result } = renderHook(() => useSalaryController(scopedFilters));

    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(result.current.overview).toBe(overviewFixture));

    expect(api.fetchSalariiOverview).toHaveBeenCalledWith(scopedScope);
    expect(api.fetchSalaryEvolution).toHaveBeenCalledWith(scopedScope);
    expect(api.fetchSalaryTrend).toHaveBeenCalledWith(scopedScope);
    expect(api.fetchSalarySummary).toHaveBeenCalledWith({ ...scopedScope, year: undefined, month: undefined });
    expect(api.fetchSalaryAgents).toHaveBeenCalledWith({
      ...scopedScope, q: undefined, limit: 50, offset: 0,
    });

    expect(result.current.evolution).toBe(evolutionPoints);
    expect(result.current.summaryMonth).toBe('2026-05');
    expect(result.current.sortedSummary.map((row) => row.locatie)).toEqual(['Beta', 'Gamma', 'Alpha']);
    expect(result.current.agents).toEqual([agentSummary]);
    expect(result.current.totalAgents).toBe(1);
    expect(result.current.page).toBe(0);
    expect(result.current.hasMore).toBe(false);
    expect(result.current.loadingCards).toBe(false);
    expect(result.current.salaryView).toBe('overview');
    act(() => result.current.setSalaryView('agents'));
    expect(result.current.salaryView).toBe('agents');
  });

  it('clears the scope when global filters select everything', async () => {
    const { result } = renderHook(() => useSalaryController(defaultFilters));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(api.fetchSalaryTrend).toHaveBeenLastCalledWith({
      company_name: undefined,
      site_code: undefined,
      regional: undefined,
    });
  });

  it('reloads summary cards only for valid YYYY-MM summary months', async () => {
    const { result } = renderHook(() => useSalaryController(defaultFilters));
    await waitFor(() => expect(result.current.summaryMonth).toBe('2026-05'));

    api.fetchSalarySummary.mockResolvedValueOnce({ items: [], month: '2026-04' });
    act(() => result.current.setSelectedSummaryMonth('2026-04'));
    await waitFor(() => expect(api.fetchSalarySummary).toHaveBeenCalledWith(
      expect.objectContaining({ year: 2026, month: 4 }),
    ));
    await waitFor(() => expect(result.current.summaryMonth).toBe('2026-04'));

    act(() => result.current.setSelectedSummaryMonth('2026-4'));
    await waitFor(() => expect(api.fetchSalarySummary).toHaveBeenLastCalledWith(
      expect.objectContaining({ year: undefined, month: undefined }),
    ));
    await waitFor(() => expect(result.current.summaryMonth).toBe('2026-05'));
  });

  it('debounces agent search and resets pagination', async () => {
    const { result } = renderHook(() => useSalaryController(defaultFilters));
    await waitFor(() => expect(api.fetchSalaryAgents).toHaveBeenCalledTimes(1));

    act(() => result.current.handleSearchChange('ion'));
    expect(result.current.search).toBe('ion');
    expect(result.current.page).toBe(0);

    await waitFor(() => expect(api.fetchSalaryAgents).toHaveBeenCalledWith(
      expect.objectContaining({ q: 'ion', offset: 0 }),
    ));
    expect(result.current.debouncedSearch).toBe('ion');

    act(() => result.current.resetSearch());
    expect(result.current.search).toBe('');
    await waitFor(() => expect(api.fetchSalaryAgents).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: undefined }),
    ));
    expect(result.current.debouncedSearch).toBe('');
  });

  it('paginates agents in PAGE_SIZE windows', async () => {
    api.fetchSalaryAgents.mockResolvedValue({ items: [], total: 120 });
    const { result } = renderHook(() => useSalaryController(defaultFilters));

    await waitFor(() => expect(result.current.hasMore).toBe(true));

    act(() => result.current.goToPage(1));
    expect(result.current.page).toBe(1);
    await waitFor(() => expect(api.fetchSalaryAgents).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 50 }),
    ));
    expect(result.current.hasMore).toBe(true);

    act(() => result.current.goToPage(2));
    await waitFor(() => expect(api.fetchSalaryAgents).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 100 }),
    ));
    expect(result.current.hasMore).toBe(false);
  });

  it('sorts summary and trend tables and computes weighted ratios', async () => {
    const { result } = renderHook(() => useSalaryController(defaultFilters));
    await waitFor(() => expect(result.current.sortedSummary).toHaveLength(3));

    // Default: total_salary desc.
    expect(result.current.sortedSummary.map((row) => row.locatie)).toEqual(['Beta', 'Gamma', 'Alpha']);
    act(() => result.current.setSummarySort({ key: 'locatie', dir: 'asc' }));
    expect(result.current.sortedSummary.map((row) => row.locatie)).toEqual(['Alpha', 'Beta', 'Gamma']);
    expect(result.current.summaryRatioAverage).toBeCloseTo(10);

    // Default: month desc.
    expect(result.current.sortedTrend.map((row) => row.month)).toEqual(['2026-05', '2026-04']);
    act(() => result.current.setTrendSort({ key: 'ratio', dir: 'asc' }));
    expect(result.current.sortedTrend.map((row) => row.month)).toEqual(['2026-04', '2026-05']);
    expect(result.current.trendRatioAverage).toBeCloseTo(15);
  });

  it('starts scoped exports for store summary, trend and agents', async () => {
    const { result } = renderHook(() => useSalaryController(scopedFilters));
    await waitFor(() => expect(result.current.summaryMonth).toBe('2026-05'));

    act(() => {
      result.current.startStoreExport();
    });
    expect(api.startExport).toHaveBeenCalledWith({
      export_kind: 'store_summary',
      ...scopedScope,
      site_code: ['MA'],
      year: 2026,
      month: 5,
    });

    act(() => {
      result.current.startTrendExport();
    });
    expect(api.startExport).toHaveBeenCalledWith({
      export_kind: 'monthly_trend',
      ...scopedScope,
      site_code: ['MA'],
    });

    act(() => {
      result.current.startAgentsExport();
    });
    expect(api.startExport).toHaveBeenCalledWith({
      export_kind: 'agents',
      ...scopedScope,
      site_code: ['MA'],
      q: undefined,
    });

    act(() => result.current.handleSearchChange('ion'));
    await waitFor(() => expect(result.current.debouncedSearch).toBe('ion'));
    act(() => {
      result.current.startAgentsExport();
    });
    expect(api.startExport).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'ion' }));
  });

  it('surfaces every loader read error without leaking the previous scope', async () => {
    api.fetchSalariiOverview.mockRejectedValueOnce(new Error('overview down'));
    api.fetchSalaryEvolution.mockRejectedValueOnce(new Error('evolution down'));
    api.fetchSalarySummary.mockRejectedValueOnce(new Error('summary down'));
    api.fetchSalaryTrend.mockRejectedValueOnce(new Error('trend down'));
    api.fetchSalaryAgents.mockRejectedValueOnce(new Error('agents down'));

    const { result } = renderHook(() => useSalaryController(defaultFilters));

    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(result.current.loadingCards).toBe(false));

    expect(result.current.overview).toBeNull();
    expect(result.current.evolution).toEqual([]);
    expect(result.current.sortedSummary).toEqual([]);
    expect(result.current.summaryMonth).toBeNull();
    expect(result.current.sortedTrend).toEqual([]);
    expect(result.current.agents).toEqual([]);
    expect(result.current.totalAgents).toBe(0);
    expect(result.current.hasMore).toBe(false);

    expect(result.current.readErrors.overview).toBe('Datele de tip statistici nu au putut fi încărcate.');
    expect(result.current.readErrors.summary).toBe('Comparația salarii vs vânzări nu a putut fi încărcată.');
    expect(result.current.readErrors.trend).toBe('Evoluția lunară nu a putut fi încărcată.');
    expect(result.current.readErrors.agents).toBe('Lista de agenți nu a putut fi încărcată.');

    const logged = consoleError.mock.calls.map((call: unknown[]) => call[0]);
    expect(logged).toContain('Failed to load overview:');
    expect(logged).toContain('Failed to load summary:');
    expect(logged).toContain('Failed to load trend:');
    expect(logged).toContain('Failed to load agents:');
  });

  it('does not let a successful sibling loader clear a sibling read error', async () => {
    api.fetchSalarySummary.mockRejectedValueOnce(new Error('summary permanently down')).mockResolvedValueOnce({ items: summaryItems, month: '2026-05' });
    api.fetchSalariiOverview.mockResolvedValue(overviewFixture);
    api.fetchSalaryEvolution.mockResolvedValue(evolutionPoints);
    api.fetchSalaryTrend.mockResolvedValue(trendPoints);
    api.fetchSalaryAgents.mockResolvedValue({ items: [agentSummary], total: 1 });

    const { result } = renderHook(() => useSalaryController(defaultFilters));

    await waitFor(() => expect(result.current.readErrors.summary).toBe('Comparația salarii vs vânzări nu a putut fi încărcată.'));
    await waitFor(() => expect(result.current.overview).toBe(overviewFixture));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(result.current.loadingCards).toBe(false));

    expect(result.current.readErrors.summary).toBe('Comparația salarii vs vânzări nu a putut fi încărcată.');
    expect(result.current.readErrors.overview).toBeUndefined();
    expect(result.current.readErrors.trend).toBeUndefined();
    expect(result.current.readErrors.agents).toBeUndefined();

    act(() => result.current.retryRead('summary'));
    await waitFor(() => expect(result.current.readErrors.summary).toBeUndefined());
    await waitFor(() => expect(result.current.summaryMonth).toBe('2026-05'));
  });

  it('replaces last-good data with the new request identity when scope changes', async () => {
    api.fetchSalariiOverview.mockResolvedValueOnce(overviewFixture);
    api.fetchSalaryEvolution.mockResolvedValueOnce(evolutionPoints);
    api.fetchSalarySummary.mockResolvedValueOnce({ items: summaryItems, month: '2026-05' });
    api.fetchSalaryTrend.mockResolvedValueOnce(trendPoints);
    api.fetchSalaryAgents.mockResolvedValueOnce({ items: [agentSummary], total: 1 });

    const { result, rerender } = renderHook(({ filters }: { filters: AppFilters }) => useSalaryController(filters), {
      initialProps: { filters: defaultFilters },
    });

    await waitFor(() => expect(result.current.overview).toBe(overviewFixture));
    await waitFor(() => expect(result.current.agents).toEqual([agentSummary]));

    api.fetchSalaryTrend.mockRejectedValueOnce(new Error('trend down for scope B'));
    api.fetchSalarySummary.mockResolvedValueOnce({ items: [], month: '2026-06' });
    api.fetchSalariiOverview.mockRejectedValueOnce(new Error('overview down for scope B'));
    api.fetchSalaryAgents.mockRejectedValueOnce(new Error('agents down for scope B'));

    rerender({ filters: scopedFilters });

    await waitFor(() => expect(result.current.readErrors.trend).toBe('Evoluția lunară nu a putut fi încărcată.'));
    expect(result.current.overview).toBeNull();
    expect(result.current.agents).toEqual([]);
    expect(result.current.sortedTrend).toEqual([]);
    expect(result.current.summaryMonth).toBe('2026-06');
    expect(result.current.readErrors.overview).toBe('Datele de tip statistici nu au putut fi încărcate.');
    expect(result.current.readErrors.agents).toBe('Lista de agenți nu a putut fi încărcată.');
  });

  it('preserves legitimate empty successful responses without surfacing an error', async () => {
    api.fetchSalariiOverview.mockResolvedValue(overviewFixture);
    api.fetchSalaryEvolution.mockResolvedValue([]);
    api.fetchSalarySummary.mockResolvedValue({ items: [], month: '2026-05' });
    api.fetchSalaryTrend.mockResolvedValue([]);
    api.fetchSalaryAgents.mockResolvedValue({ items: [], total: 0 });

    const { result } = renderHook(() => useSalaryController(defaultFilters));

    await waitFor(() => expect(result.current.loading).toBe(false));
    await waitFor(() => expect(result.current.loadingCards).toBe(false));

    expect(result.current.readErrors).toEqual({});
    expect(result.current.sortedSummary).toEqual([]);
    expect(result.current.summaryMonth).toBe('2026-05');
    expect(result.current.sortedTrend).toEqual([]);
    expect(result.current.agents).toEqual([]);
    expect(result.current.totalAgents).toBe(0);
    expect(result.current.hasMore).toBe(false);
  });

  it('surfaces the ApiError detail when a loader rejects with an ApiError', async () => {
    const { ApiError } = await import('../../api/client');
    api.fetchSalaryTrend.mockRejectedValueOnce(new ApiError(403, 'Nu ai acces la evoluția lunară.', null));

    const { result } = renderHook(() => useSalaryController(defaultFilters));

    await waitFor(() => expect(result.current.loadingCards).toBe(false));
    expect(result.current.readErrors.trend).toBe('Nu ai acces la evoluția lunară.');
    expect(result.current.readErrors.overview).toBeUndefined();
    expect(result.current.readErrors.summary).toBeUndefined();
    expect(result.current.readErrors.agents).toBeUndefined();
  });
});
