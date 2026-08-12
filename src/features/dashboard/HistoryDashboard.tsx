import { useState, type RefObject } from 'react';

import type { AgentStat, DashboardSummary, RegionalStat, StoreStat } from '../../api/generated/runtime-types';
import { ErrorCard, LoadingCard } from '../../components/common/DataDisplay';
import { SegmentedTabs } from '../../components/common/SegmentedTabs';
import type { BreakdownColumn } from './BreakdownTable';
import { HistoryDetailCharts, HistoryBreakdowns } from './HistoryDashboardDetails';
import { HistorySelection, HistorySummary } from './HistoryDashboardSummary';
import { HistoryKpiTrend, HistoryMonthlyTrend } from './HistoryDashboardTrend';

export type HistoryKpiMetric = 'proc_bon2acc' | 'prc_focus_acc_qty' | 'total_receipts';

export interface HistoryPointView {
  month: string;
  total_sales: number;
  total_target: number;
  target_progress_pct: number | null;
  total_quantity: number;
  total_receipts: number;
  proc_bon2acc: number | null;
  prc_focus_acc_qty: number | null;
  total_stores: number;
  total_agents: number;
  working_days: number;
  daily_average: number | null;
  medie_produs: number | null;
}

export interface CurrentHistoryChartPoint {
  month: string;
  sales: number;
  target: number;
  progress: number;
  isForecast: boolean;
}

export interface YearHistoryChartPoint {
  label: string;
  sales: number;
  target: number;
  progress: number;
  isAggregate: boolean;
}

export interface KpiChartPoint {
  month: string;
  value: number;
}

export interface HistoryDailyChartPoint {
  day: string;
  sales: number;
  qty: number;
  receipts: number;
}

export interface ReceiptBucketChartPoint extends Record<string, string | number> {
  bucket: string;
  receipt_count: number;
  share_pct: number;
}

export interface FocusChartPoint extends Record<string, string | number> {
  category: string;
  quantity_total: number;
  share_pct: number;
}

export interface CategoryMixChartPoint extends Record<string, string | number> {
  category: string;
  sales_total: number;
  quantity_total: number;
  share_pct: number;
}

export interface BrandMixChartPoint extends Record<string, string | number> {
  brand: string;
  sales_total: number;
  share_pct: number;
}

export interface SortState<Key extends string> {
  key: Key;
  direction: 'asc' | 'desc';
}

export interface HistoryDashboardProps<RegionalKey extends string, StoreKey extends string, AgentKey extends string> {
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  selectedPoint: HistoryPointView | null;
  currentSummary: DashboardSummary;
  historySummary: DashboardSummary | null;
  yearFilter: number | null;
  onYearFilterChange: (year: number | null) => void;
  availableYears: number[];
  currentHistoryLoading: boolean;
  yearHistoryLoading: boolean;
  currentHistoryChartData: CurrentHistoryChartPoint[];
  yearHistoryChartData: YearHistoryChartPoint[];
  kpiMetric: HistoryKpiMetric;
  onKpiMetricChange: (metric: HistoryKpiMetric) => void;
  kpiChartData: KpiChartPoint[];
  includeClosedStores: boolean;
  onIncludeClosedStoresChange: (include: boolean) => void;
  dropdownRef: RefObject<HTMLDetailsElement | null>;
  onDropdownToggle: () => void;
  dropdownOpen: boolean;
  draftSelectionLabel: string;
  selectionLabel: string;
  months: string[];
  draftSelectedMonths: string[];
  onToggleMonth: (month: string) => void;
  onApplyMonths: () => void;
  onApplyPreset?: (count: number) => void;
  historyStatusLabel: string;
  historyReceiptBucketChartData: ReceiptBucketChartPoint[];
  historyFocusSubcategoryChartData: FocusChartPoint[];
  historyDailyChartData: HistoryDailyChartPoint[];
  historyCategoryMixChartData: CategoryMixChartPoint[];
  historyBrandMixChartData: BrandMixChartPoint[];
  selectionSlug: string;
  regionals: RegionalStat[];
  sortedRegionals: RegionalStat[];
  regionalColumns: BreakdownColumn<RegionalStat, RegionalKey>[];
  regionalSort: SortState<RegionalKey>;
  onSortRegionals: (key: RegionalKey) => void;
  stores: StoreStat[];
  sortedStores: StoreStat[];
  storeColumns: BreakdownColumn<StoreStat, StoreKey>[];
  storeSort: SortState<StoreKey>;
  onSortStores: (key: StoreKey) => void;
  agents: AgentStat[];
  sortedAgents: AgentStat[];
  agentColumns: BreakdownColumn<AgentStat, AgentKey>[];
  agentSort: SortState<AgentKey>;
  onSortAgents: (key: AgentKey) => void;
}

export function HistoryDashboard<RegionalKey extends string, StoreKey extends string, AgentKey extends string>(
  props: HistoryDashboardProps<RegionalKey, StoreKey, AgentKey>,
) {
  const [mobileSection, setMobileSection] = useState<'summary' | 'trend' | 'details'>('summary');
  if (props.loading) return <LoadingCard label="Se incarca istoricul..." />;
  if (props.error) return <ErrorCard message={props.error} onRetry={props.onRetry} />;
  if (!props.selectedPoint) return <ErrorCard message="Nu exista valori istorice pentru luna selectata." onRetry={props.onRetry} />;

  return <>
    <SegmentedTabs<'summary' | 'trend' | 'details'>
      ariaLabel="Conținut istoric mobil"
      className="lg:hidden"
      level="secondary"
      options={[
        { value: 'summary', label: 'Sumar' },
        { value: 'trend', label: 'Trend' },
        { value: 'details', label: 'Detalii' },
      ]}
      value={mobileSection}
      onChange={setMobileSection}
    />
    <HistoryMonthlyTrend props={props} visible={mobileSection === 'trend'} />
    <HistoryKpiTrend props={props} visible={mobileSection === 'trend'} />
    <HistorySelection props={props} visible={mobileSection === 'summary'} />
    <HistorySummary props={props} selectedPoint={props.selectedPoint} visible={mobileSection === 'summary'} />
    <HistoryDetailCharts props={props} visible={mobileSection === 'details'} />
    <HistoryBreakdowns props={props} visible={mobileSection === 'details'} />
  </>;
}
