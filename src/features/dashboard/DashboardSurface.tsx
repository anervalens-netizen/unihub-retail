import { lazy, Suspense } from "react";
import { PageHeader } from "../../components/common/DesktopLayout";
import {
  SegmentedTabs,
  type SegmentedTabOption,
} from "../../components/common/SegmentedTabs";
import { ErrorCard, LoadingCard } from "../../components/common/DataDisplay";
import { CurrentDashboard } from "./CurrentDashboard";
import { HistoryDashboard } from "./HistoryDashboard";
import { PerformanceDetailDrawer } from "./PerformanceDetailDrawer";
import type { DashboardSection, DashboardViewProps } from "./dashboardTypes";

const DASHBOARD_SECTIONS: SegmentedTabOption<DashboardSection>[] = [
  { value: "current", label: "Luna în curs" },
  { value: "history", label: "Istoric" },
  { value: "visits", label: "Vizite" },
];
const VisiteSubtab = lazy(async () => {
  const module = await import("../../components/VisiteSubtab");
  return { default: module.VisiteSubtab };
});

export function DashboardSurface({
  activeSection,
  agents,
  agentSort,
  availableYears,
  brandMixChartData,
  canViewSalaries,
  comparisonDeltas,
  currentHistoryChartData,
  currentHistoryLoading,
  currentMode,
  currentMonth,
  currentRegionalColumns,
  currentStoreColumns,
  currentAgentColumns,
  currentStatusLabel,
  categoryMixChartData,
  dailyChartData,
  draftHistorySelectionLabel,
  draftSelectedHistoryMonths,
  error,
  filters,
  filterScopeLabel,
  focusSubcategoryChartData,
  handleApplyHistoryMonths,
  handleApplyHistoryPreset,
  handleHistoryDropdownToggle,
  handleSortAgents,
  handleSortHistoryAgents,
  handleSortHistoryRegionals,
  handleSortHistoryStores,
  handleSortRegionals,
  handleSortStores,
  handleToggleHistoryMonth,
  historyAgentSort,
  historyAgents,
  historyBrandMixChartData,
  historyCategoryMixChartData,
  historyDailyChartData,
  historyError,
  historyFocusSubcategoryChartData,
  historyLoading,
  historyMonthDropdownOpen,
  historyMonthDropdownRef,
  historyRegionalColumns,
  historyReceiptBucketChartData,
  historyRegionalSort,
  historyRegionals,
  historySelectionLabel,
  historySelectionSlug,
  historyStoreSort,
  historyStoreColumns,
  historyStores,
  historyStatusLabel,
  historyAgentColumns,
  historySummary,
  historyYearFilter,
  includeClosedStores,
  kpiChartData,
  kpiMetric,
  loading,
  months,
  storeSort,
  yearHistoryLoading,
  onClosePerformance,
  onCurrentModeChange: setCurrentMode,
  onHistoryYearFilterChange: setHistoryYearFilter,
  onIncludeClosedStoresChange: setIncludeClosedStores,
  onKpiMetricChange: setKpiMetric,
  onRetryCurrent: refetchCurrentData,
  onRetryHistory: refetchHistoryData,
  onSectionChange: setActiveSection,
  performanceDetail,
  performanceError,
  performanceLoading,
  performanceSelection,
  periodComparison,
  receiptBucketChartData,
  regionals,
  regionalSort,
  selectedHistoryPoint,
  sortedAgents,
  sortedHistoryAgents,
  sortedHistoryRegionals,
  sortedHistoryStores,
  sortedRegionals,
  sortedStores,
  stores,
  summary,
  yearHistoryChartData,
}: DashboardViewProps) {
  return (
    <div className="space-y-3 p-3 pb-24 pt-2 lg:space-y-4 lg:px-6 lg:py-3 lg:pb-6 xl:px-8">
      <PageHeader
        className="lg:hidden"
        title="Sales Hub"
        description={
          <>
            Luna in curs este fixata pe {currentMonth}, iar istoricul se
            analizeaza separat.
          </>
        }
      />

      <SegmentedTabs<DashboardSection>
        ariaLabel="Secțiuni Sales Hub"
        className="glass"
        options={DASHBOARD_SECTIONS}
        value={activeSection}
        onChange={setActiveSection}
      />

      {activeSection === "visits" ? (
        <Suspense
          fallback={<LoadingCard label="Se incarca modulul Vizite..." />}
        >
          <VisiteSubtab currentMonth={currentMonth} months={months} />
        </Suspense>
      ) : loading ? (
        <LoadingCard label="Se incarca luna in curs..." />
      ) : error || !summary ? (
        <ErrorCard
          message={
            error ?? "Datele pentru luna in curs nu au putut fi incarcate."
          }
          onRetry={refetchCurrentData}
        />
      ) : activeSection === "current" ? (
        <CurrentDashboard
          currentMonth={currentMonth}
          filters={filters}
          mode={currentMode}
          onModeChange={setCurrentMode}
          statusLabel={currentStatusLabel}
          summary={summary}
          receiptBucketChartData={receiptBucketChartData}
          focusSubcategoryChartData={focusSubcategoryChartData}
          periodComparison={periodComparison}
          comparisonDeltas={comparisonDeltas}
          dailyChartData={dailyChartData}
          categoryMixChartData={categoryMixChartData}
          brandMixChartData={brandMixChartData}
          filterScopeLabel={filterScopeLabel}
          regionals={regionals}
          sortedRegionals={sortedRegionals}
          regionalColumns={currentRegionalColumns}
          regionalSort={regionalSort}
          onSortRegionals={handleSortRegionals}
          stores={stores}
          sortedStores={sortedStores}
          storeColumns={currentStoreColumns}
          storeSort={storeSort}
          onSortStores={handleSortStores}
          agents={agents}
          sortedAgents={sortedAgents}
          agentColumns={currentAgentColumns}
          agentSort={agentSort}
          onSortAgents={handleSortAgents}
        />
      ) : (
        <HistoryDashboard
          loading={historyLoading}
          error={historyError}
          onRetry={refetchHistoryData}
          selectedPoint={selectedHistoryPoint}
          currentSummary={summary}
          historySummary={historySummary}
          yearFilter={historyYearFilter}
          onYearFilterChange={setHistoryYearFilter}
          availableYears={availableYears}
          currentHistoryLoading={currentHistoryLoading}
          yearHistoryLoading={yearHistoryLoading}
          currentHistoryChartData={currentHistoryChartData}
          yearHistoryChartData={yearHistoryChartData}
          kpiMetric={kpiMetric}
          onKpiMetricChange={setKpiMetric}
          kpiChartData={kpiChartData}
          includeClosedStores={includeClosedStores}
          onIncludeClosedStoresChange={setIncludeClosedStores}
          dropdownRef={historyMonthDropdownRef}
          onDropdownToggle={handleHistoryDropdownToggle}
          dropdownOpen={historyMonthDropdownOpen}
          draftSelectionLabel={draftHistorySelectionLabel}
          selectionLabel={historySelectionLabel}
          months={months}
          draftSelectedMonths={draftSelectedHistoryMonths}
          onToggleMonth={handleToggleHistoryMonth}
          onApplyMonths={handleApplyHistoryMonths}
          onApplyPreset={handleApplyHistoryPreset}
          historyStatusLabel={historyStatusLabel}
          historyReceiptBucketChartData={historyReceiptBucketChartData}
          historyFocusSubcategoryChartData={historyFocusSubcategoryChartData}
          historyDailyChartData={historyDailyChartData}
          historyCategoryMixChartData={historyCategoryMixChartData}
          historyBrandMixChartData={historyBrandMixChartData}
          selectionSlug={historySelectionSlug}
          regionals={historyRegionals}
          sortedRegionals={sortedHistoryRegionals}
          regionalColumns={historyRegionalColumns}
          regionalSort={historyRegionalSort}
          onSortRegionals={handleSortHistoryRegionals}
          stores={historyStores}
          sortedStores={sortedHistoryStores}
          storeColumns={historyStoreColumns}
          storeSort={historyStoreSort}
          onSortStores={handleSortHistoryStores}
          agents={historyAgents}
          sortedAgents={sortedHistoryAgents}
          agentColumns={historyAgentColumns}
          agentSort={historyAgentSort}
          onSortAgents={handleSortHistoryAgents}
        />
      )}
      <PerformanceDetailDrawer
        open={performanceSelection !== null}
        selection={performanceSelection}
        detail={performanceDetail}
        loading={performanceLoading}
        error={performanceError}
        canViewSalaries={canViewSalaries}
        onClose={() => onClosePerformance(null)}
      />
    </div>
  );
}
