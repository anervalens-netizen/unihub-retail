import type { RefObject } from "react";
import type {
  AgentStat,
  DashboardSummary,
  PeriodComparisonPayload,
  PerformanceDetailResponse,
  RegionalStat,
  StoreStat,
} from "../../api/generated/runtime-types";
import type { AppFilters } from "../../lib/appFilters";
import type { PerformanceSelection } from "./PerformanceDetailDrawer";
import type { BreakdownColumn } from "./BreakdownTable";
import type { HistoryPointView } from "./HistoryDashboard";
import type * as dashboardPresenters from "./presenters";

export type DashboardSection = "current" | "history" | "visits";
export type StoreSortKey =
  | "locatie"
  | "site_code"
  | "target"
  | "total_vanzari"
  | "proc_realizare_target"
  | "forecast_target_pct"
  | "promo_qty"
  | "incentive_qty"
  | "qty_total"
  | "nr_bonuri"
  | "nr_agenti"
  | "zile_active"
  | "medie_zilnica"
  | "medie_produs"
  | "proc_bon2acc"
  | "prc_focus_acc_qty"
  | "return_receipt_count";
export type AgentSortKey =
  | "locatie"
  | "agent"
  | "target"
  | "total_vanzari"
  | "proc_realizare_target"
  | "promo_qty"
  | "incentive_qty"
  | "acc_qty_realizat"
  | "nr_bonuri"
  | "zile_lucrate"
  | "medie_zilnica"
  | "medie_produs"
  | "proc_bon2acc"
  | "prc_focus_acc_qty"
  | "return_receipt_count";
export type RegionalSortKey =
  | "regional"
  | "target"
  | "total_vanzari"
  | "proc_realizare_target"
  | "forecast_target_pct"
  | "promo_qty"
  | "incentive_qty"
  | "qty_total"
  | "nr_bonuri"
  | "medie_zilnica"
  | "medie_produs"
  | "proc_bon2acc"
  | "prc_focus_acc_qty"
  | "return_receipt_count";

export interface DashboardProps {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
  initialSection?: DashboardSection;
  onSectionChange?: (section: DashboardSection) => void;
}

export interface DashboardViewProps {
  activeSection: DashboardSection;
  agents: AgentStat[];
  agentSort: { key: AgentSortKey; direction: "asc" | "desc" };
  availableYears: number[];
  brandMixChartData: Array<{
    brand: string;
    sales_total: number;
    share_pct: number;
  }>;
  canViewSalaries: boolean;
  comparisonDeltas: ReturnType<
    typeof dashboardPresenters.aggregateDashboardDetails
  > extends never
    ? never
    : {
        previousSales: number;
        previousSalesPct: number | null;
        previousReceipts: number;
        previousReceiptsPct: number | null;
        previousQuantity: number;
        previousQuantityPct: number | null;
        yearSales: number;
        yearSalesPct: number | null;
        yearReceipts: number;
        yearReceiptsPct: number | null;
        yearQuantity: number;
        yearQuantityPct: number | null;
      } | null;
  currentHistoryChartData: Array<{
    month: string;
    sales: number;
    target: number;
    progress: number;
    isForecast: boolean;
  }>;
  currentHistoryLoading: boolean;
  currentMode: "overview" | "forecast";
  currentMonth: string;
  currentStatusLabel: string;
  categoryMixChartData: Array<{
    category: string;
    sales_total: number;
    quantity_total: number;
    share_pct: number;
  }>;
  dailyChartData: Array<{
    day: string;
    sales: number | null;
    qty: number | null;
    receipts: number | null;
    sales_last_year: number | null;
    sales_forecast: number | null;
  }>;
  draftHistorySelectionLabel: string;
  draftSelectedHistoryMonths: string[];
  error: string | null;
  filters: AppFilters;
  filterScopeLabel: string;
  focusSubcategoryChartData: Array<{
    category: string;
    quantity_total: number;
    share_pct: number;
  }>;
  handleApplyHistoryMonths: () => void;
  handleApplyHistoryPreset: (count: number) => void;
  handleHistoryDropdownToggle: () => void;
  handleSortAgents: (key: AgentSortKey) => void;
  handleSortHistoryAgents: (key: AgentSortKey) => void;
  handleSortHistoryRegionals: (key: RegionalSortKey) => void;
  handleSortHistoryStores: (key: StoreSortKey) => void;
  handleSortRegionals: (key: RegionalSortKey) => void;
  handleSortStores: (key: StoreSortKey) => void;
  handleToggleHistoryMonth: (month: string) => void;
  historyAgentSort: { key: AgentSortKey; direction: "asc" | "desc" };
  historyAgents: AgentStat[];
  historyBrandMixChartData: Array<{
    brand: string;
    sales_total: number;
    share_pct: number;
  }>;
  historyCategoryMixChartData: Array<{
    category: string;
    sales_total: number;
    quantity_total: number;
    share_pct: number;
  }>;
  historyDailyChartData: Array<{
    day: string;
    sales: number;
    qty: number;
    receipts: number;
  }>;
  historyError: string | null;
  historyFocusSubcategoryChartData: Array<{
    category: string;
    quantity_total: number;
    share_pct: number;
  }>;
  historyLoading: boolean;
  historyMonthDropdownOpen: boolean;
  historyMonthDropdownRef: RefObject<HTMLDetailsElement | null>;
  historyReceiptBucketChartData: Array<{
    bucket: string;
    receipt_count: number;
    share_pct: number;
  }>;
  historyRegionalSort: { key: RegionalSortKey; direction: "asc" | "desc" };
  historyRegionals: RegionalStat[];
  historySelectionLabel: string;
  historySelectionSlug: string;
  historyStoreSort: { key: StoreSortKey; direction: "asc" | "desc" };
  historyStores: StoreStat[];
  historyStatusLabel: string;
  historySummary: DashboardSummary | null;
  historyYearFilter: number | null;
  includeClosedStores: boolean;
  kpiChartData: Array<{ month: string; value: number }>;
  kpiMetric: "proc_bon2acc" | "prc_focus_acc_qty" | "total_receipts";
  loading: boolean;
  months: string[];
  onClosePerformance: (selection: PerformanceSelection | null) => void;
  onCurrentModeChange: (mode: "overview" | "forecast") => void;
  onHistoryYearFilterChange: (year: number | null) => void;
  onIncludeClosedStoresChange: (value: boolean) => void;
  onKpiMetricChange: (
    metric: "proc_bon2acc" | "prc_focus_acc_qty" | "total_receipts",
  ) => void;
  onRetryCurrent: () => void;
  onRetryHistory: () => void;
  onSectionChange: (section: DashboardSection) => void;
  performanceDetail: PerformanceDetailResponse | null;
  performanceError: string;
  performanceLoading: boolean;
  performanceSelection: PerformanceSelection | null;
  periodComparison: PeriodComparisonPayload | null;
  receiptBucketChartData: Array<{
    bucket: string;
    receipt_count: number;
    share_pct: number;
  }>;
  regionals: RegionalStat[];
  regionalSort: { key: RegionalSortKey; direction: "asc" | "desc" };
  selectedHistoryPoint: HistoryPointView | null;
  sortedAgents: AgentStat[];
  sortedHistoryAgents: AgentStat[];
  sortedHistoryRegionals: RegionalStat[];
  sortedHistoryStores: StoreStat[];
  sortedRegionals: RegionalStat[];
  sortedStores: StoreStat[];
  storeSort: { key: StoreSortKey; direction: "asc" | "desc" };
  stores: StoreStat[];
  summary: DashboardSummary | null;
  yearHistoryChartData: Array<{
    label: string;
    sales: number;
    target: number;
    progress: number;
    isAggregate: boolean;
  }>;
  yearHistoryLoading: boolean;
  currentRegionalColumns: BreakdownColumn<RegionalStat, RegionalSortKey>[];
  currentStoreColumns: BreakdownColumn<StoreStat, StoreSortKey>[];
  currentAgentColumns: BreakdownColumn<AgentStat, AgentSortKey>[];
  historyRegionalColumns: BreakdownColumn<RegionalStat, RegionalSortKey>[];
  historyStoreColumns: BreakdownColumn<StoreStat, StoreSortKey>[];
  historyAgentColumns: BreakdownColumn<AgentStat, AgentSortKey>[];
}
