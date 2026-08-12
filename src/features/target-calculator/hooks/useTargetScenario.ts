import { useCallback, useEffect, useRef, useState, type Dispatch, type MutableRefObject, type RefObject, type SetStateAction } from 'react';

import {
  fetchTargetCalculatorContext,
  fetchTargetScenario,
  fetchTargetScenarios,
  type TargetCalculatorContext,
  type TargetScenario,
  type TargetScenarioRow,
} from '../api';
import { getApiErrorMessage } from '../../../api/client';
import { resolveSeasonalityMode } from '../../../lib/targetSeasonality';
import type { SeasonalityMode } from '../../../components/SeasonalityControl';
import type { TargetRegionalViewRow, TargetSourceViewRow } from '../TargetScenarioView';
import { useTargetScenarioActions } from './useTargetScenarioActions';
import { useTargetScenarioProjections } from './useTargetScenarioProjections';

type TargetAllocationViewRow = {
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

type TargetTableTotals = {
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


function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(query);
    setMatches(media.matches);
    const listener = (event: MediaQueryListEvent) => setMatches(event.matches);
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }, [query]);

  return matches;
}

function useLocationFilterEffects(
  locationOptions: TargetScenarioRow[],
  setSelectedLocationCodes: Dispatch<SetStateAction<string[]>>,
  locationDropdownOpen: boolean,
  locationFilterRef: RefObject<HTMLDivElement | null>,
  setLocationDropdownOpen: Dispatch<SetStateAction<boolean>>,
) {
  useEffect(() => {
    const available = new Set(locationOptions.map((row) => row.site_code));
    setSelectedLocationCodes((current) => current.filter((siteCode) => available.has(siteCode)));
  }, [locationOptions, setSelectedLocationCodes]);
  useEffect(() => {
    if (!locationDropdownOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (!locationFilterRef.current?.contains(event.target as Node)) setLocationDropdownOpen(false);
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setLocationDropdownOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [locationDropdownOpen, locationFilterRef, setLocationDropdownOpen]);
}

const asTargetScenarioViewModel = (
  model: TargetScenarioViewModel & { loading: boolean },
) => model;

type InitialLoadDeps = {
  scenarioRef: MutableRefObject<TargetScenario | null>;
  dirtyRowsRef: MutableRefObject<Set<string>>;
  seasonalityManualModeRef: MutableRefObject<Exclude<SeasonalityMode, null> | null>;
  replaceScenario: (next: TargetScenario | null) => void;
  clearLocalEdits: () => void;
  setContext: Dispatch<SetStateAction<TargetCalculatorContext | null>>;
  setTargetMonth: Dispatch<SetStateAction<string>>;
  setTotalTarget: Dispatch<SetStateAction<string>>;
  setMinFloor: Dispatch<SetStateAction<string>>;
  setSeasonalityMode: Dispatch<SetStateAction<SeasonalityMode>>;
  setLoading: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
};

function useTargetInitialLoad(deps: InitialLoadDeps) {
  const {
    scenarioRef, dirtyRowsRef, seasonalityManualModeRef, replaceScenario,
    clearLocalEdits, setContext, setTargetMonth, setTotalTarget, setMinFloor,
    setSeasonalityMode, setLoading, setError,
  } = deps;
  const applyScenarioSeasonality = useCallback((loaded: TargetScenario, defaultYears: number) => {
    setSeasonalityMode(resolveSeasonalityMode({
      manualMode: seasonalityManualModeRef.current,
      scenarioYears: Number(loaded.calculation_params?.seasonality_years ?? 1),
      backendDefaultYears: defaultYears,
    }));
  }, [seasonalityManualModeRef, setSeasonalityMode]);
  const loadInitial = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [context, recent] = await Promise.all([
        fetchTargetCalculatorContext(), fetchTargetScenarios(),
      ]);
      setContext(context);
      setTargetMonth((current) => current || context.suggested_target_month);
      setTotalTarget((current) => current || String(context.suggested_total_target));
      setMinFloor((current) => current || String(context.default_min_floor));
      setSeasonalityMode(resolveSeasonalityMode({
        manualMode: seasonalityManualModeRef.current,
        backendDefaultYears: context.default_seasonality_years,
      }));
      const activeId = scenarioRef.current?.id;
      if (activeId && dirtyRowsRef.current.size === 0) {
        const loaded = await fetchTargetScenario(activeId);
        replaceScenario(loaded);
        applyScenarioSeasonality(loaded, context.default_seasonality_years);
      } else if (!scenarioRef.current) {
        const draft = recent.find((item) => item.target_month === context.suggested_target_month);
        const loaded = draft ? await fetchTargetScenario(draft.id) : null;
        replaceScenario(loaded);
        if (loaded) applyScenarioSeasonality(loaded, context.default_seasonality_years);
        clearLocalEdits();
      }
    } catch (error) {
      console.error(error);
      setError(getApiErrorMessage(error, 'Nu am putut incarca calculatorul de target.'));
    } finally { setLoading(false); }
  }, [
    applyScenarioSeasonality, clearLocalEdits, dirtyRowsRef, replaceScenario,
    scenarioRef, seasonalityManualModeRef, setContext, setError, setLoading,
    setMinFloor, setSeasonalityMode, setTargetMonth, setTotalTarget,
  ]);
  useEffect(() => { void loadInitial(); }, [loadInitial]);
  return loadInitial;
}

export function useTargetScenario(): TargetScenarioViewModel & { loading: boolean } {
  const [context, setContext] = useState<TargetCalculatorContext | null>(null);
  const [scenario, setScenario] = useState<TargetScenario | null>(null);
  const [regionalFilter, setRegionalFilter] = useState('all');
  const [targetMonth, setTargetMonth] = useState('');
  const [totalTarget, setTotalTarget] = useState('');
  const [minFloor, setMinFloor] = useState('');
  const [seasonalityMode, setSeasonalityMode] = useState<SeasonalityMode>(null);
  const [logicOpen, setLogicOpen] = useState(false);
  const [selectedLocationCodes, setSelectedLocationCodes] = useState<string[]>([]);
  const [locationDropdownOpen, setLocationDropdownOpen] = useState(false);
  const [detailSiteCode, setDetailSiteCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dirtyRows, setDirtyRows] = useState<Set<string>>(() => new Set());
  const [savingRows, setSavingRows] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  const [conflictRetryAvailable, setConflictRetryAvailable] = useState(false);
  const scenarioRef = useRef<TargetScenario | null>(null);
  const dirtyRowsRef = useRef<Set<string>>(new Set());
  const editVersionsRef = useRef<Map<string, number>>(new Map());
  const seasonalityManualModeRef = useRef<Exclude<SeasonalityMode, null> | null>(null);
  const locationFilterRef = useRef<HTMLDivElement>(null);
  const dirty = dirtyRows.size > 0;
  const isDesktop = useMediaQuery('(min-width: 768px)');

  const replaceScenario = useCallback((next: TargetScenario | null) => {
    scenarioRef.current = next;
    setScenario(next);
  }, []);

  const clearLocalEdits = useCallback(() => {
    dirtyRowsRef.current = new Set();
    setDirtyRows(new Set());
    editVersionsRef.current.clear();
  }, []);

  const selectSeasonalityMode = useCallback((mode: 'multi' | 'single') => {
    seasonalityManualModeRef.current = mode;
    setSeasonalityMode(mode);
  }, []);

  const loadInitial = useTargetInitialLoad({
    scenarioRef, dirtyRowsRef, seasonalityManualModeRef, replaceScenario,
    clearLocalEdits, setContext, setTargetMonth, setTotalTarget, setMinFloor,
    setSeasonalityMode, setLoading, setError,
  });

  useEffect(() => {
    scenarioRef.current = scenario;
  }, [scenario]);

  const {
    regionals, locationOptions, selectedLocationSet, filteredRows, displaySourceMonths, tableTotals,
    sourceChart, regionalChart, regionalAllocation, activeSeasonalityLabel, displayWarnings,
  } = useTargetScenarioProjections({ scenario, context, regionalFilter, selectedLocationCodes });
  useLocationFilterEffects(
    locationOptions, setSelectedLocationCodes, locationDropdownOpen,
    locationFilterRef, setLocationDropdownOpen,
  );

  const {
    toggleLocationFilter, removeLocationFilter, handleCalculate, updateRow, resetToProposal,
    handleSave, handleFinalize, handleExport,
  } = useTargetScenarioActions({
    context, scenario, regionalFilter, targetMonth, totalTarget, minFloor, seasonalityMode,
    dirty, dirtyRows, savingRows, scenarioRef, dirtyRowsRef, editVersionsRef,
    replaceScenario, clearLocalEdits, setRegionalFilter, setSelectedLocationCodes, setBusy, setError,
    setConflictRetryAvailable, setDirtyRows, setSavingRows,
  });
  const workflowStep: 1 | 2 | 3 | 4 = !scenario
    ? 1
    : scenario.status === 'finalized'
      ? 4
      : scenario.manual_adjustments_count === 0 && scenario.pending_final_count === scenario.store_count
        ? 2
        : 3;

  return asTargetScenarioViewModel({
    loading, workflowStep, context, busy, loadInitial, targetMonth, setTargetMonth,
    totalTarget, setTotalTarget, minFloor, setMinFloor, seasonalityMode,
    selectSeasonalityMode, handleCalculate, logicOpen, setLogicOpen, error,
    conflictRetryAvailable, scenario, savingRows, dirty, displayWarnings,
    activeSeasonalityLabel, regionalChart, sourceChart, isDesktop, regionalFilter,
    setRegionalFilter, regionals, regionalAllocation, filteredRows, resetToProposal,
    handleSave, handleFinalize, handleExport,
    profitabilitySummary: scenario?.profitability_summary ?? null,
    locationFilterRef, locationDropdownOpen, setLocationDropdownOpen,
    selectedLocationCodes, selectedLocationSet, setSelectedLocationCodes,
    locationOptions, toggleLocationFilter, removeLocationFilter, displaySourceMonths,
    tableTotals, updateRow, detailSiteCode, setDetailSiteCode,
  });
}
