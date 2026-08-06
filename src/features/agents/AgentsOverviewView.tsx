import {
  SegmentedTabs,
  type SegmentedTabOption,
} from "../../components/common/SegmentedTabs";
import { AgentsCoverageView } from "./AgentsCoverageView";
import { AgentsListView } from "./AgentsListView";
import { AgentsTeamMovementView } from "./AgentsTeamMovementView";
import type {
  AgentsOverviewSection,
  AgentsOverviewViewProps,
} from "./agentsOverviewTypes";

const AGENTS_OVERVIEW_OPTIONS: SegmentedTabOption<AgentsOverviewSection>[] = [
  { value: "team", label: "Echipă" },
  { value: "coverage", label: "Acoperire magazine" },
  { value: "list", label: "Lista agenților" },
];

export function AgentsOverviewView({
  overviewSection,
  selectOverviewSection,
  ...props
}: AgentsOverviewViewProps) {
  return (
    <>
      <div className="sticky top-2 z-20 !mt-0 lg:static">
        <SegmentedTabs<AgentsOverviewSection>
          ariaLabel="Zone prezentare generală agenți"
          level="secondary"
          options={AGENTS_OVERVIEW_OPTIONS}
          value={overviewSection}
          onChange={selectOverviewSection}
        />
      </div>
      <AgentsTeamMovementView
        currentMonth={props.currentMonth}
        filterLabel={props.filterLabel}
        loadingOverview={props.loadingOverview}
        overview={props.overview}
        chartData={props.chartData}
        maxMovement={props.maxMovement}
        churnAnalysis={props.churnAnalysis}
        topFluxStores={props.topFluxStores}
        teamSectionRef={props.teamSectionRef}
      />
      <AgentsCoverageView
        coverage={props.coverage}
        loadingCoverage={props.loadingCoverage}
        expandedSection={props.expandedSection}
        setExpandedSection={props.setExpandedSection}
        coverageSectionRef={props.coverageSectionRef}
      />
      <AgentsListView
        currentMonth={props.currentMonth}
        list={props.list}
        filteredList={props.filteredList}
        loadingList={props.loadingList}
        activeTab={props.activeTab}
        setActiveTab={props.setActiveTab}
        search={props.search}
        setSearch={props.setSearch}
        cardFirma={props.cardFirma}
        setCardFirma={props.setCardFirma}
        cardMagazin={props.cardMagazin}
        setCardMagazin={props.setCardMagazin}
        filterOptions={props.filterOptions}
        setSelectedAgent={props.setSelectedAgent}
        listSectionRef={props.listSectionRef}
      />
    </>
  );
}
