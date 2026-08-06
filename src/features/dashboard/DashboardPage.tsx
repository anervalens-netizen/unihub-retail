import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { canAccessSalaries } from "../../auth/permissions";
import type {
  AgentStat,
  RegionalStat,
  StoreStat,
} from "../../api/generated/runtime-types";
import { useSortable } from "../../lib/useSortable";
import { DashboardSurface } from "./DashboardSurface";
import { type PerformanceSelection } from "./PerformanceDetailDrawer";
import {
  describeFilterScope,
  getAgentSortValue,
  getRegionalSortValue,
  getStoreSortValue,
} from "./DashboardWidgets";
import {
  AGENT_ASC_SORT_KEYS,
  agentBreakdownColumns,
  CURRENT_AGENT_COLUMNS,
  CURRENT_REGIONAL_COLUMNS,
  CURRENT_STORE_COLUMNS,
  HIST_AGENT_COLUMNS,
  HIST_REGIONAL_COLUMNS,
  HIST_STORE_COLUMNS,
  regionalBreakdownColumns,
  REGIONAL_ASC_SORT_KEYS,
  storeBreakdownColumns,
  STORE_ASC_SORT_KEYS,
} from "./dashboardColumns";
import type {
  AgentSortKey,
  DashboardProps,
  RegionalSortKey,
  StoreSortKey,
} from "./dashboardTypes";
import { useDashboardCurrentCharts } from "./useDashboardCurrentCharts";
import { useDashboardData } from "./useDashboardData";
import { useDashboardHistorySelection } from "./useDashboardHistorySelection";
import { useDashboardMixCharts } from "./useDashboardMixCharts";
import { useDashboardPerformanceDetail } from "./useDashboardPerformanceDetail";
import * as dashboardPresenters from "./presenters";

const HISTORY_START_YEAR = 2018;

export type {
  DashboardProps,
  DashboardSection,
  DashboardViewProps,
} from "./dashboardTypes";

export function Dashboard({
  currentMonth,
  months,
  filters,
  initialSection = "current",
  onSectionChange,
}: DashboardProps) {
  const { user } = useAuth();
  const canViewSalaries = canAccessSalaries(user?.profile);
  const [currentMode, setCurrentMode] = useState<"overview" | "forecast">(
    "overview",
  );
  const [historyYearFilter, setHistoryYearFilter] = useState<number | null>(
    null,
  );
  const [kpiMetric, setKpiMetric] = useState<
    "proc_bon2acc" | "prc_focus_acc_qty" | "total_receipts"
  >("proc_bon2acc");
  const [includeClosedStores, setIncludeClosedStores] = useState(false);
  const {
    performanceSelection,
    setPerformanceSelection,
    performanceDetail,
    performanceLoading,
    performanceError,
  } = useDashboardPerformanceDetail({
    currentMonth,
    firma: filters.firma,
  });
  const historySelection = useDashboardHistorySelection({
    currentMonth,
    months,
    initialSection,
  });
  const {
    activeSection,
    setActiveSection,
    historyMonth,
    selectedHistoryMonths,
    historySelectionLabel,
    historySelectionSlug,
    draftSelectedHistoryMonths,
    draftHistorySelectionLabel,
    historyMonthDropdownOpen,
    historyMonthDropdownRef,
    handleToggleHistoryMonth,
    handleApplyHistoryMonths,
    handleApplyHistoryPreset,
    handleHistoryDropdownToggle,
  } = historySelection;
  const {
    summary,
    agents,
    stores,
    dailySales,
    dailyLastYear,
    periodComparison,
    categoryMix,
    receiptBucketMix,
    focusSubcategoryMix,
    brandMix,
    regionals,
    currentHistory,
    currentHistoryLoading,
    yearHistory,
    yearHistoryLoading,
    history,
    historySummary,
    historyReceiptBucketMix,
    historyFocusSubcategoryMix,
    historyDailySales,
    historyCategoryMix,
    historyBrandMix,
    historyRegionals,
    historyStores,
    historyAgents,
    loading,
    error,
    historyLoading,
    historyError,
    refetchCurrentData,
    refetchHistoryData,
  } = useDashboardData({
    currentMonth,
    filters,
    historyMonth,
    selectedHistoryMonths,
    includeClosedStores,
    activeSection,
    historyYearFilter,
    aggregateDetails: dashboardPresenters.aggregateDashboardDetails,
  });

  useEffect(() => {
    onSectionChange?.(activeSection);
  }, [activeSection, onSectionChange]);
  const availableYears = useMemo(() => {
    const currentYear = parseInt(currentMonth.slice(0, 4));
    return Array.from(
      { length: currentYear - HISTORY_START_YEAR + 1 },
      (_, index) => HISTORY_START_YEAR + index,
    );
  }, [currentMonth]);
  const {
    dailyChartData,
    currentHistoryChartData,
    yearHistoryChartData,
    kpiChartData,
    selectedHistoryPoint,
    comparisonDeltas,
    currentStatusLabel,
  } = useDashboardCurrentCharts({
    currentMonth,
    summary,
    dailySales,
    dailyLastYear,
    currentHistory,
    yearHistory,
    kpiMetric,
    historySummary,
    history,
    historyMonth,
    periodComparison,
  });
  const {
    categoryMixChartData,
    receiptBucketChartData,
    focusSubcategoryChartData,
    historyReceiptBucketChartData,
    historyFocusSubcategoryChartData,
    historyDailyChartData,
    historyCategoryMixChartData,
    historyBrandMixChartData,
    brandMixChartData,
    historyStatusLabel,
  } = useDashboardMixCharts({
    categoryMix,
    receiptBucketMix,
    focusSubcategoryMix,
    brandMix,
    historyReceiptBucketMix,
    historyFocusSubcategoryMix,
    historyDailySales,
    historyCategoryMix,
    historyBrandMix,
    historySummary,
    historyMonth,
    selectedHistoryMonths,
  });

  const currentStoreSort = useSortable<StoreStat, StoreSortKey>({
    rows: stores,
    key: "proc_realizare_target",
    defaultAscKeys: STORE_ASC_SORT_KEYS,
    getValue: getStoreSortValue,
  });
  const currentAgentSort = useSortable<AgentStat, AgentSortKey>({
    rows: agents,
    key: "total_vanzari",
    defaultAscKeys: AGENT_ASC_SORT_KEYS,
    getValue: getAgentSortValue,
  });
  const currentRegionalSort = useSortable<RegionalStat, RegionalSortKey>({
    rows: regionals,
    key: "total_vanzari",
    defaultAscKeys: REGIONAL_ASC_SORT_KEYS,
    getValue: getRegionalSortValue,
  });
  const historicalRegionalSort = useSortable<RegionalStat, RegionalSortKey>({
    rows: historyRegionals,
    key: "total_vanzari",
    defaultAscKeys: REGIONAL_ASC_SORT_KEYS,
    getValue: getRegionalSortValue,
  });
  const historicalStoreSort = useSortable<StoreStat, StoreSortKey>({
    rows: historyStores,
    key: "total_vanzari",
    defaultAscKeys: STORE_ASC_SORT_KEYS,
    getValue: getStoreSortValue,
  });
  const historicalAgentSort = useSortable<AgentStat, AgentSortKey>({
    rows: historyAgents,
    key: "total_vanzari",
    defaultAscKeys: AGENT_ASC_SORT_KEYS,
    getValue: getAgentSortValue,
  });
  const storeSort = useMemo(
    () => ({
      key: currentStoreSort.sortKey,
      direction: currentStoreSort.direction,
    }),
    [currentStoreSort.direction, currentStoreSort.sortKey],
  );
  const agentSort = useMemo(
    () => ({
      key: currentAgentSort.sortKey,
      direction: currentAgentSort.direction,
    }),
    [currentAgentSort.direction, currentAgentSort.sortKey],
  );
  const regionalSort = useMemo(
    () => ({
      key: currentRegionalSort.sortKey,
      direction: currentRegionalSort.direction,
    }),
    [currentRegionalSort.direction, currentRegionalSort.sortKey],
  );
  const historyRegionalSort = useMemo(
    () => ({
      key: historicalRegionalSort.sortKey,
      direction: historicalRegionalSort.direction,
    }),
    [historicalRegionalSort.direction, historicalRegionalSort.sortKey],
  );
  const historyStoreSort = useMemo(
    () => ({
      key: historicalStoreSort.sortKey,
      direction: historicalStoreSort.direction,
    }),
    [historicalStoreSort.direction, historicalStoreSort.sortKey],
  );
  const historyAgentSort = useMemo(
    () => ({
      key: historicalAgentSort.sortKey,
      direction: historicalAgentSort.direction,
    }),
    [historicalAgentSort.direction, historicalAgentSort.sortKey],
  );
  const filterScopeLabel = useMemo(
    () => describeFilterScope(filters),
    [filters],
  );
  const openPerformanceDetail = (selection: PerformanceSelection) =>
    setPerformanceSelection(selection);

  return (
    <DashboardSurface
      activeSection={activeSection}
      agents={agents}
      agentSort={agentSort}
      availableYears={availableYears}
      brandMixChartData={brandMixChartData}
      canViewSalaries={canViewSalaries}
      comparisonDeltas={comparisonDeltas}
      currentHistoryChartData={currentHistoryChartData}
      currentHistoryLoading={currentHistoryLoading}
      currentMode={currentMode}
      currentMonth={currentMonth}
      currentRegionalColumns={regionalBreakdownColumns(
        CURRENT_REGIONAL_COLUMNS,
        openPerformanceDetail,
      )}
      currentStoreColumns={storeBreakdownColumns(
        CURRENT_STORE_COLUMNS,
        openPerformanceDetail,
      )}
      currentAgentColumns={agentBreakdownColumns(
        CURRENT_AGENT_COLUMNS,
        openPerformanceDetail,
      )}
      currentStatusLabel={currentStatusLabel}
      categoryMixChartData={categoryMixChartData}
      dailyChartData={dailyChartData}
      draftHistorySelectionLabel={draftHistorySelectionLabel}
      draftSelectedHistoryMonths={draftSelectedHistoryMonths}
      error={error}
      filters={filters}
      filterScopeLabel={filterScopeLabel}
      focusSubcategoryChartData={focusSubcategoryChartData}
      handleApplyHistoryMonths={handleApplyHistoryMonths}
      handleApplyHistoryPreset={handleApplyHistoryPreset}
      handleHistoryDropdownToggle={handleHistoryDropdownToggle}
      handleSortAgents={currentAgentSort.handleSort}
      handleSortHistoryAgents={historicalAgentSort.handleSort}
      handleSortHistoryRegionals={historicalRegionalSort.handleSort}
      handleSortHistoryStores={historicalStoreSort.handleSort}
      handleSortRegionals={currentRegionalSort.handleSort}
      handleSortStores={currentStoreSort.handleSort}
      handleToggleHistoryMonth={handleToggleHistoryMonth}
      historyAgentSort={historyAgentSort}
      historyAgents={historyAgents}
      historyBrandMixChartData={historyBrandMixChartData}
      historyCategoryMixChartData={historyCategoryMixChartData}
      historyDailyChartData={historyDailyChartData}
      historyError={historyError}
      historyFocusSubcategoryChartData={historyFocusSubcategoryChartData}
      historyLoading={historyLoading}
      historyMonthDropdownOpen={historyMonthDropdownOpen}
      historyMonthDropdownRef={historyMonthDropdownRef}
      historyRegionalColumns={regionalBreakdownColumns(HIST_REGIONAL_COLUMNS)}
      historyReceiptBucketChartData={historyReceiptBucketChartData}
      historyRegionalSort={historyRegionalSort}
      historyRegionals={historyRegionals}
      historySelectionLabel={historySelectionLabel}
      historySelectionSlug={historySelectionSlug}
      historyStoreSort={historyStoreSort}
      historyStoreColumns={storeBreakdownColumns(HIST_STORE_COLUMNS)}
      historyStores={historyStores}
      historyStatusLabel={historyStatusLabel}
      historyAgentColumns={agentBreakdownColumns(HIST_AGENT_COLUMNS)}
      historySummary={historySummary}
      historyYearFilter={historyYearFilter}
      includeClosedStores={includeClosedStores}
      kpiChartData={kpiChartData}
      kpiMetric={kpiMetric}
      loading={loading}
      months={months}
      onClosePerformance={setPerformanceSelection}
      onCurrentModeChange={setCurrentMode}
      onHistoryYearFilterChange={setHistoryYearFilter}
      onIncludeClosedStoresChange={setIncludeClosedStores}
      onKpiMetricChange={setKpiMetric}
      onRetryCurrent={refetchCurrentData}
      onRetryHistory={refetchHistoryData}
      onSectionChange={setActiveSection}
      performanceDetail={performanceDetail}
      performanceError={performanceError}
      performanceLoading={performanceLoading}
      performanceSelection={performanceSelection}
      periodComparison={periodComparison}
      receiptBucketChartData={receiptBucketChartData}
      regionals={regionals}
      regionalSort={regionalSort}
      selectedHistoryPoint={selectedHistoryPoint}
      sortedAgents={currentAgentSort.sorted}
      sortedHistoryAgents={historicalAgentSort.sorted}
      sortedHistoryRegionals={historicalRegionalSort.sorted}
      sortedHistoryStores={historicalStoreSort.sorted}
      sortedRegionals={currentRegionalSort.sorted}
      sortedStores={currentStoreSort.sorted}
      storeSort={storeSort}
      stores={stores}
      summary={summary}
      yearHistoryChartData={yearHistoryChartData}
      yearHistoryLoading={yearHistoryLoading}
    />
  );
}
