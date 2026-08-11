import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getFilterOptions } from '../../api/filters';
import type { AppFilters } from '../../lib/appFilters';
import type { FilterOptions } from '../../api/generated/runtime-types';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from '../../lib/filterValues';
import { usePersistentState } from '../../lib/usePersistentState';
import { SegmentedTabs, type SegmentedTabOption } from '../../components/common/SegmentedTabs';
import { PageHeader } from '../../components/common/DesktopLayout';
import { queryKeys } from '../../lib/queryKeys';
import { 
  fetchAgentsOverview, 
  fetchAgentsMovement, 
  fetchAgentsList,
  fetchStoreCoverage,
  type AgentsQuery,
  type AgentListItem,
} from '../../api/agents';
import * as agentsModel from './model';
import { AgentDrawer } from './AgentDetails';
import { AgentsOverviewView } from './AgentsOverviewView';

const GrileSubtab = lazy(async () => {
  const module = await import('../../components/GrileSubtab');
  return { default: module.GrileSubtab };
});
const AgentEvaluationSubtab = lazy(async () => {
  const module = await import('../agent-evaluation/AgentEvaluationPage');
  return { default: module.AgentEvaluationSubtab };
});

type AgentListTab = 'active' | 'movement' | 'inactive' | 'churned' | 'all';
type AgentsMainTab = 'overview' | 'grile' | 'analysis';
type AgentsOverviewSection = 'team' | 'coverage' | 'list';

const AGENTS_MAIN_OPTIONS: SegmentedTabOption<AgentsMainTab>[] = [
  { value: 'overview', label: 'Prezentare generală' },
  { value: 'grile', label: 'Grile' },
  { value: 'analysis', label: 'Analiză agenți' },
];


// ======================== Main Agents Component ========================

interface AgentsProps {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
  preferredSection?: AgentsMainTab;
  preferredGrileMonth?: string;
}


export function Agents({
  currentMonth,
  months,
  filters,
  preferredSection,
  preferredGrileMonth,
}: AgentsProps) {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedAgent, setSelectedAgent] = usePersistentState<string | null>(
    'agents_selectedAgent',
    null,
    {
      deserialize: agentsModel.deserializeSelectedAgent,
      removeWhen: agentsModel.hasNoSelectedAgent,
    },
  );
  const [activeTab, setActiveTab] = usePersistentState<AgentListTab>(
    'agents_activeTab',
    'active',
    { deserialize: agentsModel.deserializeAgentListTab },
  );
  const [mainTab, setMainTab] = usePersistentState<AgentsMainTab>(
    'agents_mainTab',
    preferredSection ?? 'overview',
    { deserialize: agentsModel.deserializeAgentsMainTab },
  );

  useEffect(() => {
    if (preferredSection) setMainTab(preferredSection);
  }, [preferredSection, setMainTab]);

  const [cardFirma, setCardFirma] = useState(ALL_FIRMS);
  const [cardMagazin, setCardMagazin] = useState(ALL_STORES);
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null);
  const [expandedSection, setExpandedSection] = useState<'active' | 'modified' | 'inactive' | null>(null);
  const [overviewSection, setOverviewSection] = useState<AgentsOverviewSection>('team');
  const teamSectionRef = useRef<HTMLDivElement>(null);
  const coverageSectionRef = useRef<HTMLDivElement>(null);
  const listSectionRef = useRef<HTMLDivElement>(null);

  const selectOverviewSection = (section: AgentsOverviewSection) => {
    setOverviewSection(section);
    const target = section === 'team'
      ? teamSectionRef.current
      : section === 'coverage'
        ? coverageSectionRef.current
        : listSectionRef.current;
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const queryParams = useMemo(() => {
    const p: AgentsQuery = { selected_month: currentMonth };
    if (filters.firma !== ALL_FIRMS) p.firma = filters.firma;
    if (filters.rm !== ALL_SCOPE) p.regional = filters.rm;
    if (filters.magazin.length > 0) p.site_code = filters.magazin;
    if (filters.agent.length > 0) p.agent = filters.agent;
    return p;
  }, [currentMonth, filters]);

  const { data: overview, isLoading: loadingOverview } = useQuery({
    queryKey: queryKeys.agents.overview(currentMonth, queryParams),
    queryFn: ({ signal }) => fetchAgentsOverview(queryParams, signal),
  });

  const { data: movement } = useQuery({
    queryKey: queryKeys.agents.movement(queryParams),
    queryFn: ({ signal }) => fetchAgentsMovement(queryParams, signal),
  });

  const { data: coverage, isLoading: loadingCoverage } = useQuery({
    queryKey: queryKeys.agents.coverage(queryParams),
    queryFn: ({ signal }) => fetchStoreCoverage(queryParams, signal),
  });

  const listParams = useMemo(() => ({ ...queryParams, search: debouncedSearch || undefined }), [queryParams, debouncedSearch]);

  const { data: listResponse, isLoading: loadingList } = useQuery({
    queryKey: queryKeys.agents.list(listParams),
    queryFn: ({ signal }) => fetchAgentsList(listParams, signal),
  });

  const list = useMemo(() => listResponse?.items || [], [listResponse?.items]);

  // Fetch filter options for card filters
  useEffect(() => {
    const controller = new AbortController();
    getFilterOptions(currentMonth, controller.signal)
      .then(setFilterOptions)
      .catch(() => {
        if (!controller.signal.aborted) setFilterOptions(null);
      });
    return () => controller.abort();
  }, [currentMonth]);

  const filteredList = useMemo(() => {
    let result = list;
    if (activeTab === 'active') result = result.filter((ag: AgentListItem) => ag.current_status === 'active');
    if (activeTab === 'movement') result = result.filter((ag: AgentListItem) => ag.is_new || ag.is_reactivated);
    if (activeTab === 'inactive') result = result.filter((ag: AgentListItem) => ag.current_status === 'inactive_recent');
    if (activeTab === 'churned') result = result.filter((ag: AgentListItem) => ag.current_status === 'churned');
    if (cardFirma !== ALL_FIRMS && filterOptions) {
      const firmaMagazine = filterOptions.magazine.filter((m) => m.firma === cardFirma).map((m) => m.locatie || m.site_code);
      result = result.filter((ag: AgentListItem) => firmaMagazine.includes(ag.store_name || ''));
    }
    if (cardMagazin !== ALL_STORES) {
      result = result.filter((ag: AgentListItem) => ag.store_name === cardMagazin);
    }
    return result;
  }, [list, activeTab, cardFirma, cardMagazin, filterOptions]);

  const chartData = useMemo(() => {
    const points = (movement?.history ?? []).filter((p) => p.month >= '2025-01');
    return points.map((p, index) => {
      const isBaseline = p.is_baseline || p.month === '2025-01';
      const previous = index > 0 ? points[index - 1] : null;
      const newAgents = isBaseline ? 0 : p.new;
      const reactivatedAgents = isBaseline ? 0 : p.reactivated;
      const derivedExited = previous
        ? Math.max(0, previous.active + newAgents + reactivatedAgents - p.active)
        : 0;
      const exited = isBaseline ? 0 : Math.max(p.churned ?? 0, derivedExited);
      const netGrowth = isBaseline || !previous ? 0 : p.active - previous.active;

      return {
        ...p,
        is_baseline: isBaseline,
        new: newAgents,
        reactivated: reactivatedAgents,
        churned: exited,
        net_growth: netGrowth,
        churned_negative: -exited,
      };
    });
  }, [movement]);

  const maxMovement = useMemo(() => {
    const values = chartData.flatMap((p) => [p.new, p.reactivated, p.churned, Math.abs(p.net_growth)]);
    return Math.max(5, ...values) + 2;
  }, [chartData]);

  const churnAnalysis = useMemo(() => {
    const nonBaseline = chartData.filter((p) => !p.is_baseline);
    const currentPoint = chartData.find((p) => p.month === currentMonth) ?? chartData[chartData.length - 1];
    const currentPrevActive = currentPoint && !currentPoint.is_baseline
      ? Math.max(0, currentPoint.active - currentPoint.net_growth)
      : 0;
    const currentChurnRate = currentPrevActive > 0 && currentPoint
      ? (currentPoint.churned / currentPrevActive) * 100
      : null;
    const lastThree = nonBaseline.slice(-3);
    const avgChurnRate = lastThree.length > 0
      ? lastThree.reduce((sum, p) => {
          const prevActive = Math.max(0, p.active - p.net_growth);
          return sum + (prevActive > 0 ? (p.churned / prevActive) * 100 : 0);
        }, 0) / lastThree.length
      : null;
    const totalExited = nonBaseline.reduce((sum, p) => sum + p.churned, 0);
    return {
      currentChurnRate,
      avgChurnRate,
      totalExited,
      currentExited: currentPoint?.churned ?? 0,
      currentNetGrowth: currentPoint?.is_baseline ? 0 : currentPoint?.net_growth ?? 0,
    };
  }, [chartData, currentMonth]);

  const topFluxStores = useMemo(() => {
    return (coverage?.items ?? [])
      .filter((item) => item.has_changes)
      .map((item) => ({
        ...item,
        change_count: item.added_agents_count + item.removed_agents_count,
      }))
      .sort((a, b) => b.change_count - a.change_count || b.agent_count - a.agent_count || a.locatie.localeCompare(b.locatie))
      .slice(0, 5);
  }, [coverage]);

  const filterLabel = useMemo(() => {
    if (filters.agent.length > 0) return filters.agent.length > 1 ? `${filters.agent.length} agenți selectați` : `Agent: ${filters.agent[0]}`;
    if (filters.magazin.length > 0) return filters.magazin.length > 1 ? `${filters.magazin.length} magazine selectate` : `Magazin: ${filters.magazin[0]}`;
    if (filters.rm !== ALL_SCOPE) return `Regional: ${filters.rm}`;
    if (filters.firma !== ALL_FIRMS) return `Firma: ${filters.firma}`;
    return 'Toata selectia activa';
  }, [filters]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);



  if (selectedAgent) {
    return (
      <AgentDrawer
        agent={selectedAgent}
        currentMonth={currentMonth}
        isOpen={!!selectedAgent}
        onClose={() => setSelectedAgent(null)}
      />
    );
  }

  return (
    <div className="space-y-3 p-3 pb-24 pt-2 lg:space-y-4 lg:px-6 lg:py-3 lg:pb-6">
      <PageHeader
        className="lg:hidden"
        title="Agenti"
        description="Analiza echipei, miscare de personal si retentie"
      />

      <SegmentedTabs<AgentsMainTab>
        ariaLabel="Secțiuni Agenți"
        className="glass"
        options={AGENTS_MAIN_OPTIONS}
        value={mainTab}
        onChange={setMainTab}
      />

      {mainTab === 'analysis' ? (
        <ErrorBoundary>
          <Suspense fallback={<div className="glass rounded-2xl p-4 text-sm text-slate-500">Se încarcă analiza agenților...</div>}>
            <AgentEvaluationSubtab currentMonth={currentMonth} months={months} />
          </Suspense>
        </ErrorBoundary>
      ) : mainTab === 'grile' ? (
        <ErrorBoundary>
          <Suspense fallback={<div className="glass rounded-2xl p-4 text-sm text-slate-500">Se încarcă Grile...</div>}>
            <GrileSubtab initialMonth={preferredGrileMonth} />
          </Suspense>
        </ErrorBoundary>
      ) : (
        <>
          <AgentsOverviewView
            overviewSection={overviewSection}
            selectOverviewSection={selectOverviewSection}
            currentMonth={currentMonth}
            filterLabel={filterLabel}
            loadingOverview={loadingOverview}
            overview={overview}
            chartData={chartData}
            maxMovement={maxMovement}
            churnAnalysis={churnAnalysis}
            coverage={coverage}
            loadingCoverage={loadingCoverage}
            expandedSection={expandedSection}
            setExpandedSection={setExpandedSection}
            topFluxStores={topFluxStores}
            list={list}
            filteredList={filteredList}
            loadingList={loadingList}
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            search={search}
            setSearch={setSearch}
            cardFirma={cardFirma}
            setCardFirma={setCardFirma}
            cardMagazin={cardMagazin}
            setCardMagazin={setCardMagazin}
            filterOptions={filterOptions}
            setSelectedAgent={setSelectedAgent}
            teamSectionRef={teamSectionRef}
            coverageSectionRef={coverageSectionRef}
            listSectionRef={listSectionRef}
          />
      </>
      )}

    </div>
  );
}
