import { lazy, Suspense } from 'react';

import type { AppFilters } from '../../lib/appFilters';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import { SegmentedTabs, type SegmentedTabOption } from '../../components/common/SegmentedTabs';
import { PageHeader } from '../../components/common/DesktopLayout';
import { AgentDrawer } from './AgentDetails';
import { AgentsOverviewView } from './AgentsOverviewView';
import { useAgentsPageController, type AgentsMainTab } from './useAgentsPageController';

const GrileSubtab = lazy(async () => ({ default: (await import('../../components/GrileSubtab')).GrileSubtab }));
const AgentEvaluationSubtab = lazy(async () => ({ default: (await import('../agent-evaluation/AgentEvaluationPage')).AgentEvaluationSubtab }));
const OPTIONS: SegmentedTabOption<AgentsMainTab>[] = [
  { value: 'overview', label: 'Prezentare generală' }, { value: 'grile', label: 'Grile' },
  { value: 'analysis', label: 'Analiză agenți' },
];

interface AgentsProps {
  currentMonth: string; months: string[]; filters: AppFilters;
  preferredSection?: AgentsMainTab; preferredGrileMonth?: string;
}

function LazyAgentsSection({ model, currentMonth, months, preferredGrileMonth }: {
  model: ReturnType<typeof useAgentsPageController>; currentMonth: string;
  months: string[]; preferredGrileMonth?: string;
}) {
  if (model.mainTab === 'analysis') return <ErrorBoundary><Suspense fallback={<div className="glass rounded-2xl p-4 text-sm text-slate-500">Se încarcă analiza agenților...</div>}><AgentEvaluationSubtab currentMonth={currentMonth} months={months} /></Suspense></ErrorBoundary>;
  if (model.mainTab === 'grile') return <ErrorBoundary><Suspense fallback={<div className="glass rounded-2xl p-4 text-sm text-slate-500">Se încarcă Grile...</div>}><GrileSubtab initialMonth={preferredGrileMonth} /></Suspense></ErrorBoundary>;
  return <AgentsOverviewView
    overviewSection={model.overviewSection} selectOverviewSection={model.selectOverviewSection}
    currentMonth={currentMonth} filterLabel={model.filterLabel} loadingOverview={model.loadingOverview}
    overview={model.overview} chartData={model.chartData} maxMovement={model.maxMovement}
    churnAnalysis={model.churnAnalysis} coverage={model.coverage} loadingCoverage={model.loadingCoverage}
    expandedSection={model.expandedSection} setExpandedSection={model.setExpandedSection}
    topFluxStores={model.topFluxStores} list={model.list} filteredList={model.filteredList}
    loadingList={model.loadingList} activeTab={model.activeTab} setActiveTab={model.setActiveTab}
    search={model.search} setSearch={model.setSearch} cardFirma={model.cardFirma}
    setCardFirma={model.setCardFirma} cardMagazin={model.cardMagazin} setCardMagazin={model.setCardMagazin}
    filterOptions={model.filterOptions} setSelectedAgent={model.setSelectedAgent}
    teamSectionRef={model.teamSectionRef} coverageSectionRef={model.coverageSectionRef}
    listSectionRef={model.listSectionRef}
  />;
}

export function Agents({ currentMonth, months, filters, preferredSection, preferredGrileMonth }: AgentsProps) {
  const model = useAgentsPageController(currentMonth, filters, preferredSection);
  if (model.selectedAgent) return <AgentDrawer agent={model.selectedAgent} currentMonth={currentMonth} isOpen onClose={() => model.setSelectedAgent(null)} />;
  return <div className="space-y-3 p-3 pb-24 pt-2 lg:space-y-4 lg:px-6 lg:py-3 lg:pb-6">
    <PageHeader className="lg:hidden" title="Agenti" description="Analiza echipei, miscare de personal si retentie" />
    <SegmentedTabs<AgentsMainTab> ariaLabel="Secțiuni Agenți" className="glass" options={OPTIONS} value={model.mainTab} onChange={model.setMainTab} />
    <LazyAgentsSection model={model} currentMonth={currentMonth} months={months} preferredGrileMonth={preferredGrileMonth} />
  </div>;
}
