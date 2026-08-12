import { lazy, Suspense } from 'react';

import { PageHeader } from '../../components/common/DesktopLayout';
import { SegmentedTabs, type SegmentedTabOption } from '../../components/common/SegmentedTabs';
import { ErrorCard, LoadingCard } from '../../components/common/DataDisplay';
import { CurrentDashboard } from './CurrentDashboard';
import { HistoryDashboard } from './HistoryDashboard';
import { PerformanceDetailDrawer } from './PerformanceDetailDrawer';
import type { DashboardSection, DashboardViewProps } from './dashboardTypes';

const SECTIONS: SegmentedTabOption<DashboardSection>[] = [
  { value: 'current', label: 'Luna în curs' }, { value: 'history', label: 'Istoric' },
  { value: 'visits', label: 'Vizite' },
];
const VisiteSubtab = lazy(async () => ({ default: (await import('../../components/VisiteSubtab')).VisiteSubtab }));

function CurrentSection({ model }: { model: DashboardViewProps }) {
  if (!model.summary) return null;
  return <CurrentDashboard
    currentMonth={model.currentMonth} filters={model.filters} mode={model.currentMode}
    onModeChange={model.onCurrentModeChange} statusLabel={model.currentStatusLabel}
    summary={model.summary} receiptBucketChartData={model.receiptBucketChartData}
    focusSubcategoryChartData={model.focusSubcategoryChartData}
    periodComparison={model.periodComparison} comparisonDeltas={model.comparisonDeltas}
    dailyChartData={model.dailyChartData} categoryMixChartData={model.categoryMixChartData}
    brandMixChartData={model.brandMixChartData} filterScopeLabel={model.filterScopeLabel}
    regionals={model.regionals} sortedRegionals={model.sortedRegionals}
    regionalColumns={model.currentRegionalColumns} regionalSort={model.regionalSort}
    onSortRegionals={model.handleSortRegionals} stores={model.stores}
    sortedStores={model.sortedStores} storeColumns={model.currentStoreColumns}
    storeSort={model.storeSort} onSortStores={model.handleSortStores}
    agents={model.agents} sortedAgents={model.sortedAgents}
    agentColumns={model.currentAgentColumns} agentSort={model.agentSort}
    onSortAgents={model.handleSortAgents}
  />;
}

function HistorySection({ model }: { model: DashboardViewProps }) {
  if (!model.summary) return null;
  return <HistoryDashboard
    loading={model.historyLoading} error={model.historyError} onRetry={model.onRetryHistory}
    selectedPoint={model.selectedHistoryPoint} currentSummary={model.summary}
    historySummary={model.historySummary} yearFilter={model.historyYearFilter}
    onYearFilterChange={model.onHistoryYearFilterChange} availableYears={model.availableYears}
    currentHistoryLoading={model.currentHistoryLoading} yearHistoryLoading={model.yearHistoryLoading}
    currentHistoryChartData={model.currentHistoryChartData} yearHistoryChartData={model.yearHistoryChartData}
    kpiMetric={model.kpiMetric} onKpiMetricChange={model.onKpiMetricChange}
    kpiChartData={model.kpiChartData} includeClosedStores={model.includeClosedStores}
    onIncludeClosedStoresChange={model.onIncludeClosedStoresChange}
    dropdownRef={model.historyMonthDropdownRef} onDropdownToggle={model.handleHistoryDropdownToggle}
    dropdownOpen={model.historyMonthDropdownOpen} draftSelectionLabel={model.draftHistorySelectionLabel}
    selectionLabel={model.historySelectionLabel} months={model.months}
    draftSelectedMonths={model.draftSelectedHistoryMonths} onToggleMonth={model.handleToggleHistoryMonth}
    onApplyMonths={model.handleApplyHistoryMonths} onApplyPreset={model.handleApplyHistoryPreset}
    historyStatusLabel={model.historyStatusLabel}
    historyReceiptBucketChartData={model.historyReceiptBucketChartData}
    historyFocusSubcategoryChartData={model.historyFocusSubcategoryChartData}
    historyDailyChartData={model.historyDailyChartData}
    historyCategoryMixChartData={model.historyCategoryMixChartData}
    historyBrandMixChartData={model.historyBrandMixChartData} selectionSlug={model.historySelectionSlug}
    regionals={model.historyRegionals} sortedRegionals={model.sortedHistoryRegionals}
    regionalColumns={model.historyRegionalColumns} regionalSort={model.historyRegionalSort}
    onSortRegionals={model.handleSortHistoryRegionals} stores={model.historyStores}
    sortedStores={model.sortedHistoryStores} storeColumns={model.historyStoreColumns}
    storeSort={model.historyStoreSort} onSortStores={model.handleSortHistoryStores}
    agents={model.historyAgents} sortedAgents={model.sortedHistoryAgents}
    agentColumns={model.historyAgentColumns} agentSort={model.historyAgentSort}
    onSortAgents={model.handleSortHistoryAgents}
  />;
}

function DashboardContent({ model }: { model: DashboardViewProps }) {
  if (model.activeSection === 'visits') return <Suspense fallback={<LoadingCard label="Se incarca modulul Vizite..." />}><VisiteSubtab currentMonth={model.currentMonth} months={model.months} /></Suspense>;
  if (model.loading) return <LoadingCard label="Se incarca luna in curs..." />;
  if (model.error || !model.summary) return <ErrorCard message={model.error ?? 'Datele pentru luna in curs nu au putut fi incarcate.'} onRetry={model.onRetryCurrent} />;
  return model.activeSection === 'current' ? <CurrentSection model={model} /> : <HistorySection model={model} />;
}

export function DashboardSurface(model: DashboardViewProps) {
  return <div className="space-y-3 p-3 pb-24 pt-2 lg:space-y-4 lg:px-6 lg:py-3 lg:pb-6 xl:px-8">
    <PageHeader className="lg:hidden" title="Sales Hub" description={<>Luna in curs este fixata pe {model.currentMonth}, iar istoricul se analizeaza separat.</>} />
    <SegmentedTabs<DashboardSection> ariaLabel="Secțiuni Sales Hub" className="glass" options={SECTIONS} value={model.activeSection} onChange={model.onSectionChange} />
    <DashboardContent model={model} />
    <PerformanceDetailDrawer open={model.performanceSelection !== null} selection={model.performanceSelection} detail={model.performanceDetail} loading={model.performanceLoading} error={model.performanceError} canViewSalaries={model.canViewSalaries} onClose={() => model.onClosePerformance(null)} />
  </div>;
}
