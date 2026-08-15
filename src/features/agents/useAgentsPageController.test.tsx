// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  AgentListItem,
  AgentMovementResponse,
  AgentsOverviewResponse,
  StoreCoverageResponse,
} from '../../api/agents';
import type { FilterOptions } from '../../api/generated/runtime-types';
import type { AppFilters } from '../../lib/appFilters';
import { ALL_FIRMS, ALL_SCOPE } from '../../lib/filterValues';

const api = vi.hoisted(() => ({
  fetchAgentsList: vi.fn(),
  fetchAgentsMovement: vi.fn(),
  fetchAgentsOverview: vi.fn(),
  fetchStoreCoverage: vi.fn(),
  getFilterOptions: vi.fn(),
}));

vi.mock('../../api/agents', () => ({
  fetchAgentsList: api.fetchAgentsList,
  fetchAgentsMovement: api.fetchAgentsMovement,
  fetchAgentsOverview: api.fetchAgentsOverview,
  fetchStoreCoverage: api.fetchStoreCoverage,
}));

vi.mock('../../api/filters', () => ({ getFilterOptions: api.getFilterOptions }));

import { useAgentsPageController } from './useAgentsPageController';

const CURRENT_MONTH = '2025-03';

const defaultFilters: AppFilters = { firma: ALL_FIRMS, rm: ALL_SCOPE, magazin: [], agent: [] };

function createWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

const movementHistory: AgentMovementResponse = {
  history: [
    { month: '2024-12', active: 40, new: 2, reactivated: 1, churned: 3, net_growth: -1, is_baseline: true },
    { month: '2025-01', active: 50, new: 3, reactivated: 1, churned: 2, net_growth: 1, is_baseline: false },
    { month: '2025-02', active: 55, new: 7, reactivated: 2, churned: 1, net_growth: 6, is_baseline: false },
    { month: '2025-03', active: 52, new: 1, reactivated: 0, churned: 5, net_growth: -4, is_baseline: false },
  ],
};

const coverageResponse: StoreCoverageResponse = {
  active_stores_count: 6,
  closed_stores_count: 0,
  uncovered_stores_count: 1,
  items: [
    { locatie: 'A', site_code: 'SA', firma: 'Mobiup', regional: 'Nord', asm: 'ASM1', status: 'covered', agent_count: 9, has_changes: true, added_agents_count: 3, removed_agents_count: 3, previous_agent_count: 9, change_reason: null },
    { locatie: 'B', site_code: 'SB', firma: 'Mobiup', regional: 'Nord', asm: 'ASM1', status: 'covered', agent_count: 5, has_changes: true, added_agents_count: 2, removed_agents_count: 1, previous_agent_count: 4, change_reason: null },
    { locatie: 'C', site_code: 'SC', firma: 'Mobicell', regional: 'Sud', asm: 'ASM2', status: 'covered', agent_count: 7, has_changes: true, added_agents_count: 1, removed_agents_count: 1, previous_agent_count: 7, change_reason: null },
    { locatie: 'D', site_code: 'SD', firma: 'Mobicell', regional: 'Sud', asm: 'ASM2', status: 'covered', agent_count: 4, has_changes: true, added_agents_count: 1, removed_agents_count: 1, previous_agent_count: 4, change_reason: null },
    { locatie: 'E', site_code: 'SE', firma: 'Mobiup', regional: 'Nord', asm: 'ASM1', status: 'covered', agent_count: 4, has_changes: true, added_agents_count: 0, removed_agents_count: 2, previous_agent_count: 6, change_reason: null },
    { locatie: 'F', site_code: 'SF', firma: 'Mobiup', regional: 'Nord', asm: 'ASM1', status: 'covered', agent_count: 2, has_changes: true, added_agents_count: 1, removed_agents_count: 0, previous_agent_count: 1, change_reason: null },
    { locatie: 'G', site_code: 'SG', firma: 'Mobicell', regional: 'Sud', asm: 'ASM2', status: 'uncovered', agent_count: 0, has_changes: false, added_agents_count: 0, removed_agents_count: 0, previous_agent_count: 0, change_reason: null },
  ],
} as unknown as StoreCoverageResponse;

const agentItem = (overrides: Partial<AgentListItem>): AgentListItem => ({
  active_in_month: true,
  agent: 'Agent Test',
  current_status: 'active',
  firma: 'Mobiup',
  is_new: false,
  is_reactivated: false,
  store_name: 'Mag A',
  total_quantity: 10,
  total_sales: '1000',
  ...overrides,
} as unknown as AgentListItem);

const listResponse = {
  items: [
    agentItem({ agent: 'Ana', current_status: 'active', store_name: 'Mag A' }),
    agentItem({ agent: 'Bogdan', current_status: 'active', is_new: true, store_name: 'Mag B', firma: 'Mobicell' }),
    agentItem({ agent: 'Cristi', current_status: 'inactive_recent', store_name: 'Mag A' }),
    agentItem({ agent: 'Dana', current_status: 'churned', store_name: 'Mag B', firma: 'Mobicell' }),
  ],
};

const filterOptionsFixture: FilterOptions = {
  agenti: [],
  asmi: [],
  firme: ['Mobiup', 'Mobicell'],
  regionali: [],
  magazine: [
    { firma: 'Mobiup', locatie: 'Mag A', site_code: 'MA', asm: 'ASM1', regional: 'Nord' },
    { firma: 'Mobicell', locatie: 'Mag B', site_code: 'MB', asm: 'ASM1', regional: 'Nord' },
  ],
} as unknown as FilterOptions;

describe('useAgentsPageController', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    api.getFilterOptions.mockResolvedValue(filterOptionsFixture);
    api.fetchAgentsOverview.mockResolvedValue({} as AgentsOverviewResponse);
    api.fetchAgentsMovement.mockResolvedValue(movementHistory);
    api.fetchStoreCoverage.mockResolvedValue(coverageResponse);
    api.fetchAgentsList.mockResolvedValue(listResponse);
  });

  it('builds the query scope and transforms movement/coverage data', async () => {
    const { result } = renderHook(
      () => useAgentsPageController(CURRENT_MONTH, defaultFilters),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.list).toHaveLength(4));

    expect(api.fetchAgentsOverview).toHaveBeenCalledWith(
      { selected_month: CURRENT_MONTH },
      expect.any(AbortSignal),
    );
    expect(api.fetchAgentsMovement).toHaveBeenCalledWith(
      { selected_month: CURRENT_MONTH },
      expect.any(AbortSignal),
    );
    expect(api.fetchStoreCoverage).toHaveBeenCalledWith(
      { selected_month: CURRENT_MONTH },
      expect.any(AbortSignal),
    );
    expect(api.fetchAgentsList).toHaveBeenCalledWith(
      { selected_month: CURRENT_MONTH },
      expect.any(AbortSignal),
    );
    expect(api.getFilterOptions).toHaveBeenCalledWith(CURRENT_MONTH, expect.any(AbortSignal));
    await waitFor(() => expect(result.current.filterOptions).toBe(filterOptionsFixture));

    // 2024-12 drops out (< 2025-01); 2025-01 becomes the zeroed baseline.
    expect(result.current.chartData.map((point) => point.month)).toEqual(['2025-01', '2025-02', '2025-03']);
    const [baseline, february, march] = result.current.chartData;
    expect(baseline).toMatchObject({ is_baseline: true, new: 0, reactivated: 0, churned: 0, net_growth: 0 });
    // derived exit 50 + 7 + 2 - 55 = 4 beats the reported churned value 1.
    expect(february).toMatchObject({ is_baseline: false, new: 7, reactivated: 2, churned: 4, net_growth: 5, churned_negative: -4 });
    // reported churned 5 beats derived 55 + 1 + 0 - 52 = 4.
    expect(march).toMatchObject({ is_baseline: false, new: 1, reactivated: 0, churned: 5, net_growth: -3, churned_negative: -5 });

    expect(result.current.maxMovement).toBe(9);
    expect(result.current.churnAnalysis.currentChurnRate).toBeCloseTo((5 / 55) * 100);
    expect(result.current.churnAnalysis.avgChurnRate).toBeCloseTo((8 + (5 / 55) * 100) / 2);
    expect(result.current.churnAnalysis.totalExited).toBe(9);
    expect(result.current.churnAnalysis.currentExited).toBe(5);
    expect(result.current.churnAnalysis.currentNetGrowth).toBe(-3);

    expect(result.current.topFluxStores.map((store) => store.locatie)).toEqual(['A', 'B', 'C', 'D', 'E']);
    expect(result.current.topFluxStores[0]?.change_count).toBe(6);
    expect(result.current.filterLabel).toBe('Toata selectia activa');
  });

  it('includes firma, regional, store and agent filters in every query', async () => {
    const filters: AppFilters = { firma: 'Mobiup', rm: 'Nord', magazin: ['MA'], agent: ['Ana'] };
    const { result } = renderHook(
      () => useAgentsPageController(CURRENT_MONTH, filters),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.list).toHaveLength(4));

    const scopedQuery = {
      selected_month: CURRENT_MONTH,
      firma: 'Mobiup',
      regional: 'Nord',
      site_code: ['MA'],
      agent: ['Ana'],
    };
    expect(api.fetchAgentsOverview).toHaveBeenCalledWith(scopedQuery, expect.any(AbortSignal));
    expect(api.fetchAgentsMovement).toHaveBeenCalledWith(scopedQuery, expect.any(AbortSignal));
    expect(api.fetchStoreCoverage).toHaveBeenCalledWith(scopedQuery, expect.any(AbortSignal));
    expect(api.fetchAgentsList).toHaveBeenCalledWith(scopedQuery, expect.any(AbortSignal));
    expect(result.current.filterLabel).toBe('Agent: Ana');
  });

  it('reports filter labels by priority', () => {
    const cases: Array<[AppFilters, string]> = [
      [{ firma: ALL_FIRMS, rm: ALL_SCOPE, magazin: [], agent: ['Ana', 'Bogdan'] }, '2 agenți selectați'],
      [{ firma: ALL_FIRMS, rm: ALL_SCOPE, magazin: ['MA', 'MB'], agent: [] }, '2 magazine selectate'],
      [{ firma: ALL_FIRMS, rm: ALL_SCOPE, magazin: ['MA'], agent: [] }, 'Magazin: MA'],
      [{ firma: ALL_FIRMS, rm: 'Nord', magazin: [], agent: [] }, 'Regional: Nord'],
      [{ firma: 'Mobiup', rm: ALL_SCOPE, magazin: [], agent: [] }, 'Firma: Mobiup'],
    ];
    for (const [filters, label] of cases) {
      const { result, unmount } = renderHook(
        () => useAgentsPageController(CURRENT_MONTH, filters),
        { wrapper: createWrapper() },
      );
      expect(result.current.filterLabel).toBe(label);
      unmount();
    }
  });

  it('filters the list by tab, firma and store', async () => {
    const { result } = renderHook(
      () => useAgentsPageController(CURRENT_MONTH, defaultFilters),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.list).toHaveLength(4));
    await waitFor(() => expect(result.current.filterOptions).toBe(filterOptionsFixture));

    expect(result.current.activeTab).toBe('active');
    expect(result.current.filteredList.map((agent) => agent.agent)).toEqual(['Ana', 'Bogdan']);

    act(() => result.current.setActiveTab('movement'));
    expect(result.current.filteredList.map((agent) => agent.agent)).toEqual(['Bogdan']);
    act(() => result.current.setActiveTab('inactive'));
    expect(result.current.filteredList.map((agent) => agent.agent)).toEqual(['Cristi']);
    act(() => result.current.setActiveTab('churned'));
    expect(result.current.filteredList.map((agent) => agent.agent)).toEqual(['Dana']);
    act(() => result.current.setActiveTab('all'));
    expect(result.current.filteredList).toHaveLength(4);

    act(() => result.current.setCardFirma('Mobiup'));
    expect(result.current.filteredList.map((agent) => agent.agent)).toEqual(['Ana', 'Cristi']);
    act(() => result.current.setCardMagazin('Mag B'));
    expect(result.current.filteredList).toEqual([]);
    act(() => result.current.setCardFirma(ALL_FIRMS));
    expect(result.current.filteredList.map((agent) => agent.agent)).toEqual(['Bogdan', 'Dana']);

    expect(window.sessionStorage.getItem('agents_activeTab')).toBe('all');
    act(() => result.current.setActiveTab('active'));
    expect(window.sessionStorage.getItem('agents_activeTab')).toBe('active');
  });

  it('debounces the search value into the list query', async () => {
    const { result } = renderHook(
      () => useAgentsPageController(CURRENT_MONTH, defaultFilters),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.list).toHaveLength(4));
    expect(api.fetchAgentsList).toHaveBeenCalledTimes(1);

    act(() => result.current.setSearch('ana'));
    expect(result.current.search).toBe('ana');

    await waitFor(() => expect(api.fetchAgentsList).toHaveBeenCalledWith(
      expect.objectContaining({ search: 'ana' }),
      expect.any(AbortSignal),
    ));
    expect(api.fetchAgentsList).toHaveBeenCalledTimes(2);
  });

  it('tracks persistent tabs, preferred section and selected agent', async () => {
    const { result, rerender } = renderHook(
      ({ section }: { section?: 'overview' | 'grile' | 'analysis' }) =>
        useAgentsPageController(CURRENT_MONTH, defaultFilters, section),
      { wrapper: createWrapper(), initialProps: { section: 'grile' as 'overview' | 'grile' | 'analysis' } },
    );

    await waitFor(() => expect(result.current.mainTab).toBe('grile'));
    act(() => result.current.setMainTab('analysis'));
    expect(result.current.mainTab).toBe('analysis');
    expect(window.sessionStorage.getItem('agents_mainTab')).toBe('analysis');

    rerender({ section: 'overview' });
    await waitFor(() => expect(result.current.mainTab).toBe('overview'));

    act(() => result.current.setSelectedAgent('Ana'));
    expect(window.sessionStorage.getItem('agents_selectedAgent')).toBe('Ana');
    act(() => result.current.setSelectedAgent(null));
    expect(window.sessionStorage.getItem('agents_selectedAgent')).toBeNull();

    act(() => result.current.selectOverviewSection('coverage'));
    expect(result.current.overviewSection).toBe('coverage');
    act(() => result.current.setExpandedSection('modified'));
    expect(result.current.expandedSection).toBe('modified');
  });

  it('keeps card firma filtering inert when filter options fail to load', async () => {
    api.getFilterOptions.mockRejectedValueOnce(new Error('options down'));
    const { result } = renderHook(
      () => useAgentsPageController(CURRENT_MONTH, defaultFilters),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.list).toHaveLength(4));
    expect(result.current.filterOptions).toBeNull();

    act(() => result.current.setCardFirma('Mobiup'));
    expect(result.current.filteredList.map((agent) => agent.agent)).toEqual(['Ana', 'Bogdan']);
  });

  it('survives query failures with empty derived state', async () => {
    api.fetchAgentsMovement.mockRejectedValueOnce(new Error('movement down'));
    api.fetchAgentsList.mockRejectedValueOnce(new Error('list down'));
    api.fetchStoreCoverage.mockRejectedValueOnce(new Error('coverage down'));
    const { result } = renderHook(
      () => useAgentsPageController(CURRENT_MONTH, defaultFilters),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.loadingList).toBe(false));
    await waitFor(() => expect(result.current.loadingOverview).toBe(false));

    expect(result.current.chartData).toEqual([]);
    expect(result.current.maxMovement).toBe(7);
    expect(result.current.churnAnalysis).toEqual({
      currentChurnRate: null,
      avgChurnRate: null,
      totalExited: 0,
      currentExited: 0,
      currentNetGrowth: 0,
    });
    expect(result.current.list).toEqual([]);
    expect(result.current.filteredList).toEqual([]);
    expect(result.current.topFluxStores).toEqual([]);
  });
});
