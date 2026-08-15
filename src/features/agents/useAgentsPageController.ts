import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import type { AppFilters } from '../../lib/appFilters';
import { getFilterOptions } from '../../api/filters';
import {
  fetchAgentsList,
  fetchAgentsMovement,
  fetchAgentsOverview,
  fetchStoreCoverage,
  type AgentListItem,
  type AgentsQuery,
} from '../../api/agents';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from '../../lib/filterValues';
import { queryKeys } from '../../lib/queryKeys';
import { usePersistentState } from '../../lib/usePersistentState';
import * as agentsModel from './model';
import type { AgentListTab, AgentsOverviewSection } from './agentsOverviewTypes';

export type AgentsMainTab = 'overview' | 'grile' | 'analysis';

function buildQuery(currentMonth: string, filters: AppFilters): AgentsQuery {
  const query: AgentsQuery = { selected_month: currentMonth };
  if (filters.firma !== ALL_FIRMS) query.firma = filters.firma;
  if (filters.rm !== ALL_SCOPE) query.regional = filters.rm;
  if (filters.magazin.length > 0) query.site_code = filters.magazin;
  if (filters.agent.length > 0) query.agent = filters.agent;
  return query;
}

function useAgentsQueries(currentMonth: string, filters: AppFilters, search: string) {
  const queryParams = useMemo(() => buildQuery(currentMonth, filters), [currentMonth, filters]);
  const overview = useQuery({ queryKey: queryKeys.agents.overview(currentMonth, queryParams), queryFn: ({ signal }) => fetchAgentsOverview(queryParams, signal) });
  const movement = useQuery({ queryKey: queryKeys.agents.movement(queryParams), queryFn: ({ signal }) => fetchAgentsMovement(queryParams, signal) });
  const coverage = useQuery({ queryKey: queryKeys.agents.coverage(queryParams), queryFn: ({ signal }) => fetchStoreCoverage(queryParams, signal) });
  const listParams = useMemo(() => ({ ...queryParams, search: search || undefined }), [queryParams, search]);
  const list = useQuery({ queryKey: queryKeys.agents.list(listParams), queryFn: ({ signal }) => fetchAgentsList(listParams, signal) });
  return { overview, movement, coverage, list };
}

function movementChart(history: Awaited<ReturnType<typeof fetchAgentsMovement>>['history']) {
  const points = history.filter((point) => point.month >= '2025-01');
  return points.map((point, index) => {
    const isBaseline = point.is_baseline || point.month === '2025-01';
    const previous = index > 0 ? points[index - 1] : null;
    const newAgents = isBaseline ? 0 : point.new;
    const reactivated = isBaseline ? 0 : point.reactivated;
    const derivedExited = previous ? Math.max(0, previous.active + newAgents + reactivated - point.active) : 0;
    const exited = isBaseline ? 0 : Math.max(point.churned ?? 0, derivedExited);
    const netGrowth = isBaseline || !previous ? 0 : point.active - previous.active;
    return { ...point, is_baseline: isBaseline, new: newAgents, reactivated, churned: exited, net_growth: netGrowth, churned_negative: -exited };
  });
}

function filterAgents(list: AgentListItem[], tab: AgentListTab, firma: string, store: string, options: Awaited<ReturnType<typeof getFilterOptions>> | null) {
  let result = list;
  if (tab === 'active') result = result.filter((agent) => agent.current_status === 'active');
  if (tab === 'movement') result = result.filter((agent) => agent.is_new || agent.is_reactivated);
  if (tab === 'inactive') result = result.filter((agent) => agent.current_status === 'inactive_recent');
  if (tab === 'churned') result = result.filter((agent) => agent.current_status === 'churned');
  if (firma !== ALL_FIRMS && options) {
    const stores = options.magazine.filter((item) => item.firma === firma).map((item) => item.locatie || item.site_code);
    result = result.filter((agent) => stores.includes(agent.store_name || ''));
  }
  return store === ALL_STORES ? result : result.filter((agent) => agent.store_name === store);
}

function filterLabel(filters: AppFilters) {
  if (filters.agent.length > 0) return filters.agent.length > 1 ? `${filters.agent.length} agenți selectați` : `Agent: ${filters.agent[0]}`;
  if (filters.magazin.length > 0) return filters.magazin.length > 1 ? `${filters.magazin.length} magazine selectate` : `Magazin: ${filters.magazin[0]}`;
  if (filters.rm !== ALL_SCOPE) return `Regional: ${filters.rm}`;
  if (filters.firma !== ALL_FIRMS) return `Firma: ${filters.firma}`;
  return 'Toata selectia activa';
}

export function useAgentsPageController(currentMonth: string, filters: AppFilters, preferredSection?: AgentsMainTab) {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedAgent, setSelectedAgent] = usePersistentState<string | null>('agents_selectedAgent', null, { deserialize: agentsModel.deserializeSelectedAgent, removeWhen: agentsModel.hasNoSelectedAgent });
  const [activeTab, setActiveTab] = usePersistentState<AgentListTab>('agents_activeTab', 'active', { deserialize: agentsModel.deserializeAgentListTab });
  const [mainTab, setMainTab] = usePersistentState<AgentsMainTab>('agents_mainTab', preferredSection ?? 'overview', { deserialize: agentsModel.deserializeAgentsMainTab });
  const [cardFirma, setCardFirma] = useState(ALL_FIRMS);
  const [cardMagazin, setCardMagazin] = useState(ALL_STORES);
  const [filterOptions, setFilterOptions] = useState<Awaited<ReturnType<typeof getFilterOptions>> | null>(null);
  const [expandedSection, setExpandedSection] = useState<'active' | 'modified' | 'inactive' | null>(null);
  const [overviewSection, setOverviewSection] = useState<AgentsOverviewSection>('team');
  const teamSectionRef = useRef<HTMLDivElement>(null);
  const coverageSectionRef = useRef<HTMLDivElement>(null);
  const listSectionRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (preferredSection) setMainTab(preferredSection); }, [preferredSection, setMainTab]);
  useEffect(() => { const timer = setTimeout(() => setDebouncedSearch(search), 300); return () => clearTimeout(timer); }, [search]);
  useEffect(() => {
    const controller = new AbortController();
    getFilterOptions(currentMonth, controller.signal).then(setFilterOptions).catch(() => { if (!controller.signal.aborted) setFilterOptions(null); });
    return () => controller.abort();
  }, [currentMonth]);
  const queries = useAgentsQueries(currentMonth, filters, debouncedSearch);
  const list = useMemo(() => queries.list.data?.items || [], [queries.list.data?.items]);
  const filteredList = useMemo(() => filterAgents(list, activeTab, cardFirma, cardMagazin, filterOptions), [activeTab, cardFirma, cardMagazin, filterOptions, list]);
  const chartData = useMemo(() => movementChart(queries.movement.data?.history ?? []), [queries.movement.data?.history]);
  const maxMovement = useMemo(() => Math.max(5, ...chartData.flatMap((point) => [point.new, point.reactivated, point.churned, Math.abs(point.net_growth)])) + 2, [chartData]);
  const churnAnalysis = useMemo(() => {
    const points = chartData.filter((point) => !point.is_baseline);
    const current = chartData.find((point) => point.month === currentMonth) ?? chartData.at(-1);
    const previousActive = current && !current.is_baseline ? Math.max(0, current.active - current.net_growth) : 0;
    const lastThree = points.slice(-3);
    return {
      currentChurnRate: previousActive > 0 && current ? current.churned / previousActive * 100 : null,
      avgChurnRate: lastThree.length ? lastThree.reduce((sum, point) => { const previous = Math.max(0, point.active - point.net_growth); return sum + (previous > 0 ? point.churned / previous * 100 : 0); }, 0) / lastThree.length : null,
      totalExited: points.reduce((sum, point) => sum + point.churned, 0), currentExited: current?.churned ?? 0,
      currentNetGrowth: current?.is_baseline ? 0 : current?.net_growth ?? 0,
    };
  }, [chartData, currentMonth]);
  const topFluxStores = useMemo(() => (queries.coverage.data?.items ?? []).filter((item) => item.has_changes).map((item) => ({ ...item, change_count: item.added_agents_count + item.removed_agents_count })).sort((a, b) => b.change_count - a.change_count || b.agent_count - a.agent_count || a.locatie.localeCompare(b.locatie)).slice(0, 5), [queries.coverage.data?.items]);
  const selectOverviewSection = (section: AgentsOverviewSection) => {
    setOverviewSection(section);
    (section === 'team' ? teamSectionRef.current : section === 'coverage' ? coverageSectionRef.current : listSectionRef.current)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  return {
    search, setSearch, selectedAgent, setSelectedAgent, activeTab, setActiveTab,
    mainTab, setMainTab, cardFirma, setCardFirma, cardMagazin, setCardMagazin,
    filterOptions, expandedSection, setExpandedSection, overviewSection,
    selectOverviewSection, teamSectionRef, coverageSectionRef, listSectionRef,
    overview: queries.overview.data, loadingOverview: queries.overview.isLoading,
    coverage: queries.coverage.data, loadingCoverage: queries.coverage.isLoading,
    list, filteredList, loadingList: queries.list.isLoading, chartData, maxMovement,
    churnAnalysis, topFluxStores, filterLabel: filterLabel(filters),
  };
}

