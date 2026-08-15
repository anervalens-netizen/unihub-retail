import type { Dispatch, RefObject, SetStateAction } from 'react';

import type { SeasonalityMode } from '../../../components/SeasonalityControl';
import type { TargetCalculatorContext, TargetScenario, TargetScenarioRow } from '../api';
import type { TargetRegionalViewRow, TargetSourceViewRow } from '../TargetScenarioView';

export type TargetAllocationViewRow = {
  manager: string;
  storeCount: number;
  targetShare: number;
  targetVsPreviousSharePp: number | null;
  target: number;
  targetVsPreviousPct: number | null;
  targetVsSeasonalPct: number | null;
  targetVsPreviousYearPct: number | null;
  targetVsForecastPct: number | null;
  signal: string;
};

export type TargetTableTotals = {
  history: Array<{ month: string; target: number; realized: number; attainment: number | null }>;
  normalizedWeight: number;
  proposedTarget: number;
  finalTarget: number | null;
  salary: number;
  operatingCosts: number | null;
  breakEven: number | null;
  forecast: number | null;
};

export interface TargetScenarioViewModel {
  workflowStep: 1 | 2 | 3 | 4;
  context: TargetCalculatorContext | null;
  busy: boolean;
  loadInitial: () => Promise<void>;
  targetMonth: string;
  setTargetMonth: (value: string) => void;
  totalTarget: string;
  setTotalTarget: (value: string) => void;
  minFloor: string;
  setMinFloor: (value: string) => void;
  seasonalityMode: SeasonalityMode;
  selectSeasonalityMode: (mode: 'multi' | 'single') => void;
  handleCalculate: () => Promise<void>;
  logicOpen: boolean;
  setLogicOpen: Dispatch<SetStateAction<boolean>>;
  error: string | null;
  conflictRetryAvailable: boolean;
  scenario: TargetScenario | null;
  savingRows: Set<string>;
  dirty: boolean;
  displayWarnings: string[];
  activeSeasonalityLabel: string;
  regionalChart: TargetRegionalViewRow[];
  sourceChart: TargetSourceViewRow[];
  isDesktop: boolean;
  regionalFilter: string;
  setRegionalFilter: (value: string) => void;
  regionals: string[];
  regionalAllocation: TargetAllocationViewRow[];
  filteredRows: TargetScenarioRow[];
  resetToProposal: () => void;
  handleSave: () => Promise<void>;
  handleFinalize: () => Promise<void>;
  handleExport: () => Promise<void>;
  profitabilitySummary: TargetScenario['profitability_summary'];
  locationFilterRef: RefObject<HTMLDivElement | null>;
  locationDropdownOpen: boolean;
  setLocationDropdownOpen: Dispatch<SetStateAction<boolean>>;
  selectedLocationCodes: string[];
  selectedLocationSet: Set<string>;
  setSelectedLocationCodes: Dispatch<SetStateAction<string[]>>;
  locationOptions: TargetScenarioRow[];
  toggleLocationFilter: (siteCode: string) => void;
  removeLocationFilter: (siteCode: string) => void;
  displaySourceMonths: Array<{ month: string; label: string; role: string }>;
  tableTotals: TargetTableTotals;
  updateRow: (siteCode: string, field: 'final_target' | 'note', value: number | string | null) => void;
  detailSiteCode: string | null;
  setDetailSiteCode: Dispatch<SetStateAction<string | null>>;
}
