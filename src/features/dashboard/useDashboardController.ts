import { useEffect, useMemo, useState } from 'react';

import { useAuth } from '../../auth/AuthContext';
import { canAccessSalaries } from '../../auth/permissions';
import { describeFilterScope } from './DashboardWidgets';
import {
  agentBreakdownColumns, CURRENT_AGENT_COLUMNS, CURRENT_REGIONAL_COLUMNS, CURRENT_STORE_COLUMNS,
  HIST_AGENT_COLUMNS, HIST_REGIONAL_COLUMNS, HIST_STORE_COLUMNS, regionalBreakdownColumns,
  storeBreakdownColumns,
} from './dashboardColumns';
import type { DashboardProps, DashboardViewProps } from './dashboardTypes';
import { useDashboardCurrentCharts } from './useDashboardCurrentCharts';
import { useDashboardData } from './useDashboardData';
import { useDashboardHistorySelection } from './useDashboardHistorySelection';
import { useDashboardMixCharts } from './useDashboardMixCharts';
import { useDashboardPerformanceDetail } from './useDashboardPerformanceDetail';
import { useDashboardSorts } from './useDashboardSorts';
import * as dashboardPresenters from './presenters';

const HISTORY_START_YEAR = 2018;

function useDashboardState(props: DashboardProps) {
  const { user } = useAuth();
  const [currentMode, setCurrentMode] = useState<'overview' | 'forecast'>('overview');
  const [historyYearFilter, setHistoryYearFilter] = useState<number | null>(null);
  const [kpiMetric, setKpiMetric] = useState<'proc_bon2acc' | 'prc_focus_acc_qty' | 'total_receipts'>('proc_bon2acc');
  const [includeClosedStores, setIncludeClosedStores] = useState(false);
  const performance = useDashboardPerformanceDetail({ currentMonth: props.currentMonth, firma: props.filters.firma });
  const historySelection = useDashboardHistorySelection({
    currentMonth: props.currentMonth, months: props.months, initialSection: props.initialSection ?? 'current',
  });
  const data = useDashboardData({
    currentMonth: props.currentMonth,
    filters: props.filters,
    historyMonth: historySelection.historyMonth,
    selectedHistoryMonths: historySelection.selectedHistoryMonths,
    includeClosedStores,
    activeSection: historySelection.activeSection,
    historyYearFilter,
    aggregateDetails: dashboardPresenters.aggregateDashboardDetails,
  });
  useEffect(() => {
    props.onSectionChange?.(historySelection.activeSection);
  }, [historySelection.activeSection, props.onSectionChange]);
  const availableYears = useMemo(() => {
    const currentYear = parseInt(props.currentMonth.slice(0, 4));
    return Array.from({ length: currentYear - HISTORY_START_YEAR + 1 }, (_, index) => HISTORY_START_YEAR + index);
  }, [props.currentMonth]);
  return {
    canViewSalaries: canAccessSalaries(user?.profile), currentMode, setCurrentMode,
    historyYearFilter, setHistoryYearFilter, kpiMetric, setKpiMetric,
    includeClosedStores, setIncludeClosedStores, performance, historySelection, data, availableYears,
  };
}

function useDashboardCharts(props: DashboardProps, state: ReturnType<typeof useDashboardState>) {
  const { data, historySelection: history } = state;
  const current = useDashboardCurrentCharts({
    currentMonth: props.currentMonth, summary: data.summary, dailySales: data.dailySales,
    dailyLastYear: data.dailyLastYear, currentHistory: data.currentHistory, yearHistory: data.yearHistory,
    kpiMetric: state.kpiMetric, historySummary: data.historySummary, history: data.history,
    historyMonth: history.historyMonth, periodComparison: data.periodComparison,
  });
  const mix = useDashboardMixCharts({
    categoryMix: data.categoryMix, receiptBucketMix: data.receiptBucketMix,
    focusSubcategoryMix: data.focusSubcategoryMix, brandMix: data.brandMix,
    historyReceiptBucketMix: data.historyReceiptBucketMix,
    historyFocusSubcategoryMix: data.historyFocusSubcategoryMix,
    historyDailySales: data.historyDailySales, historyCategoryMix: data.historyCategoryMix,
    historyBrandMix: data.historyBrandMix, historySummary: data.historySummary,
    historyMonth: history.historyMonth, selectedHistoryMonths: history.selectedHistoryMonths,
  });
  return { current, mix };
}

export function useDashboardController(props: DashboardProps): DashboardViewProps {
  const state = useDashboardState(props);
  const { data, historySelection: history, performance } = state;
  const { current, mix } = useDashboardCharts(props, state);
  const sorts = useDashboardSorts({
    agents: data.agents, stores: data.stores, regionals: data.regionals,
    historyAgents: data.historyAgents, historyStores: data.historyStores, historyRegionals: data.historyRegionals,
  });
  const openPerformance = performance.setPerformanceSelection;
  return {
    activeSection: history.activeSection, agents: data.agents, agentSort: sorts.agentSort,
    availableYears: state.availableYears, brandMixChartData: mix.brandMixChartData,
    canViewSalaries: state.canViewSalaries, comparisonDeltas: current.comparisonDeltas,
    currentHistoryChartData: current.currentHistoryChartData, currentHistoryLoading: data.currentHistoryLoading,
    currentMode: state.currentMode, currentMonth: props.currentMonth,
    currentRegionalColumns: regionalBreakdownColumns(CURRENT_REGIONAL_COLUMNS, openPerformance),
    currentStoreColumns: storeBreakdownColumns(CURRENT_STORE_COLUMNS, openPerformance),
    currentAgentColumns: agentBreakdownColumns(CURRENT_AGENT_COLUMNS, openPerformance),
    currentStatusLabel: current.currentStatusLabel, categoryMixChartData: mix.categoryMixChartData,
    dailyChartData: current.dailyChartData,
    draftHistorySelectionLabel: history.draftHistorySelectionLabel,
    draftSelectedHistoryMonths: history.draftSelectedHistoryMonths,
    error: data.error, filters: props.filters, filterScopeLabel: describeFilterScope(props.filters),
    focusSubcategoryChartData: mix.focusSubcategoryChartData,
    handleApplyHistoryMonths: history.handleApplyHistoryMonths,
    handleApplyHistoryPreset: history.handleApplyHistoryPreset,
    handleHistoryDropdownToggle: history.handleHistoryDropdownToggle,
    handleSortAgents: sorts.currentAgent.handleSort,
    handleSortHistoryAgents: sorts.historyAgent.handleSort,
    handleSortHistoryRegionals: sorts.historyRegional.handleSort,
    handleSortHistoryStores: sorts.historyStore.handleSort,
    handleSortRegionals: sorts.currentRegional.handleSort,
    handleSortStores: sorts.currentStore.handleSort,
    handleToggleHistoryMonth: history.handleToggleHistoryMonth,
    historyAgentSort: sorts.historyAgentSort, historyAgents: data.historyAgents,
    historyBrandMixChartData: mix.historyBrandMixChartData,
    historyCategoryMixChartData: mix.historyCategoryMixChartData,
    historyDailyChartData: mix.historyDailyChartData, historyError: data.historyError,
    historyFocusSubcategoryChartData: mix.historyFocusSubcategoryChartData,
    historyLoading: data.historyLoading, historyMonthDropdownOpen: history.historyMonthDropdownOpen,
    historyMonthDropdownRef: history.historyMonthDropdownRef,
    historyRegionalColumns: regionalBreakdownColumns(HIST_REGIONAL_COLUMNS),
    historyReceiptBucketChartData: mix.historyReceiptBucketChartData,
    historyRegionalSort: sorts.historyRegionalSort, historyRegionals: data.historyRegionals,
    historySelectionLabel: history.historySelectionLabel,
    historySelectionSlug: history.historySelectionSlug,
    historyStoreSort: sorts.historyStoreSort,
    historyStoreColumns: storeBreakdownColumns(HIST_STORE_COLUMNS),
    historyStores: data.historyStores, historyStatusLabel: mix.historyStatusLabel,
    historyAgentColumns: agentBreakdownColumns(HIST_AGENT_COLUMNS),
    historySummary: data.historySummary, historyYearFilter: state.historyYearFilter,
    includeClosedStores: state.includeClosedStores, kpiChartData: current.kpiChartData,
    kpiMetric: state.kpiMetric, loading: data.loading, months: props.months,
    onClosePerformance: performance.setPerformanceSelection,
    onCurrentModeChange: state.setCurrentMode,
    onHistoryYearFilterChange: state.setHistoryYearFilter,
    onIncludeClosedStoresChange: state.setIncludeClosedStores,
    onKpiMetricChange: state.setKpiMetric,
    onRetryCurrent: data.refetchCurrentData, onRetryHistory: data.refetchHistoryData,
    onSectionChange: history.setActiveSection,
    performanceDetail: performance.performanceDetail,
    performanceError: performance.performanceError,
    performanceLoading: performance.performanceLoading,
    performanceSelection: performance.performanceSelection,
    periodComparison: data.periodComparison, receiptBucketChartData: mix.receiptBucketChartData,
    regionals: data.regionals, regionalSort: sorts.regionalSort,
    selectedHistoryPoint: current.selectedHistoryPoint,
    sortedAgents: sorts.currentAgent.sorted, sortedHistoryAgents: sorts.historyAgent.sorted,
    sortedHistoryRegionals: sorts.historyRegional.sorted, sortedHistoryStores: sorts.historyStore.sorted,
    sortedRegionals: sorts.currentRegional.sorted, sortedStores: sorts.currentStore.sorted,
    storeSort: sorts.storeSort, stores: data.stores, summary: data.summary,
    yearHistoryChartData: current.yearHistoryChartData, yearHistoryLoading: data.yearHistoryLoading,
  };
}
