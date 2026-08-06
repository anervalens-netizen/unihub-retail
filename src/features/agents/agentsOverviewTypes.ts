import type { Dispatch, RefObject, SetStateAction } from "react";
import type { FilterOptions } from "../../api/generated/runtime-types";
import type {
  AgentListItem,
  AgentMovementPoint,
  AgentsOverviewResponse,
  StoreCoverageItem,
  StoreCoverageResponse,
} from "../../api/agents";

export type AgentListTab =
  "active" | "movement" | "inactive" | "churned" | "all";
export type AgentsOverviewSection = "team" | "coverage" | "list";
export type AgentMovementChartPoint = AgentMovementPoint & {
  is_baseline: boolean;
  net_growth: number;
  churned_negative: number;
};
export type ChurnAnalysis = {
  currentChurnRate: number | null;
  avgChurnRate: number | null;
  totalExited: number;
  currentExited: number;
  currentNetGrowth: number;
};
export type ExpandedCoverageSection = "active" | "modified" | "inactive" | null;

export interface AgentsTeamMovementViewProps {
  currentMonth: string;
  filterLabel: string;
  loadingOverview: boolean;
  overview: AgentsOverviewResponse | undefined;
  chartData: AgentMovementChartPoint[];
  maxMovement: number;
  churnAnalysis: ChurnAnalysis;
  topFluxStores: Array<StoreCoverageItem & { change_count: number }>;
  teamSectionRef: RefObject<HTMLDivElement | null>;
}

export interface AgentsCoverageViewProps {
  coverage: StoreCoverageResponse | undefined;
  loadingCoverage: boolean;
  expandedSection: ExpandedCoverageSection;
  setExpandedSection: Dispatch<SetStateAction<ExpandedCoverageSection>>;
  coverageSectionRef: RefObject<HTMLDivElement | null>;
}

export interface AgentsListViewProps {
  currentMonth: string;
  list: AgentListItem[];
  filteredList: AgentListItem[];
  loadingList: boolean;
  activeTab: AgentListTab;
  setActiveTab: Dispatch<SetStateAction<AgentListTab>>;
  search: string;
  setSearch: Dispatch<SetStateAction<string>>;
  cardFirma: string;
  setCardFirma: Dispatch<SetStateAction<string>>;
  cardMagazin: string;
  setCardMagazin: Dispatch<SetStateAction<string>>;
  filterOptions: FilterOptions | null;
  setSelectedAgent: Dispatch<SetStateAction<string | null>>;
  listSectionRef: RefObject<HTMLDivElement | null>;
}

export interface AgentsOverviewViewProps
  extends
    AgentsTeamMovementViewProps,
    AgentsCoverageViewProps,
    AgentsListViewProps {
  overviewSection: AgentsOverviewSection;
  selectOverviewSection: (section: AgentsOverviewSection) => void;
}
