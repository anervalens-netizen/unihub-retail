import { useCallback, useEffect, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getDashboardAll,
  getDashboardHistory,
  getDashboardHistoryDetailsBatch,
  getDashboardHistoryYear,
} from "../../api/dashboard";
import type { DashboardQuery } from "../../api/dashboard";
import type {
  AgentStat,
  AsmStat,
  BrandMixItem,
  CategoryMixItem,
  DailySalesPoint,
  DashboardAllResponse,
  DashboardSummary,
  MonthlyHistoryPoint,
  PeriodComparisonPayload,
  ReceiptBucketItem,
  RegionalStat,
  StoreStat,
  YearHistoryPoint,
} from "../../api/generated/runtime-types";
import {
  buildCurrentDashboardQuery,
  buildScopedMonthQuery,
} from "../../lib/filterQueries";
import { queryKeys } from "../../lib/queryKeys";
import type { AppFilters } from "../../lib/appFilters";
import { DASHBOARD_STALE_MS } from "./dashboardDefaults";
import type { DashboardSection } from "./dashboardTypes";

export interface AggregatedDashboardDetails {
  summary: DashboardSummary;
  receiptBucketMix: ReceiptBucketItem[];
  focusSubcategoryMix: CategoryMixItem[];
  dailySales: DailySalesPoint[];
  dailyLastYear: DailySalesPoint[];
  categoryMix: CategoryMixItem[];
  brandMix: BrandMixItem[];
  periodComparison: PeriodComparisonPayload | null;
  regionals: RegionalStat[];
  asms: AsmStat[];
  stores: StoreStat[];
  agents: AgentStat[];
}

interface UseDashboardDataParams {
  currentMonth: string;
  filters: AppFilters;
  historyMonth: string;
  selectedHistoryMonths: string[];
  includeClosedStores: boolean;
  activeSection: DashboardSection;
  historyYearFilter: number | null;
  aggregateDetails: (
    responses: DashboardAllResponse[],
    selectedMonths: string[],
  ) => AggregatedDashboardDetails;
}

const EMPTY_AGENT_STATS: AgentStat[] = [];
const EMPTY_BRAND_MIX: BrandMixItem[] = [];
const EMPTY_CATEGORY_MIX: CategoryMixItem[] = [];
const EMPTY_DAILY_SALES: DailySalesPoint[] = [];
const EMPTY_HISTORY: MonthlyHistoryPoint[] = [];
const EMPTY_RECEIPT_BUCKETS: ReceiptBucketItem[] = [];
const EMPTY_REGIONAL_STATS: RegionalStat[] = [];
const EMPTY_STORE_STATS: StoreStat[] = [];
const EMPTY_YEAR_HISTORY: YearHistoryPoint[] = [];

type NetworkInformation = {
  effectiveType?: string;
  saveData?: boolean;
};

export function shouldPrefetchDashboardHistory(): boolean {
  if (typeof navigator === "undefined") return false;
  const connection = (
    navigator as Navigator & { connection?: NetworkInformation }
  ).connection;
  if (connection?.saveData) return false;
  return (
    connection?.effectiveType !== "slow-2g" &&
    connection?.effectiveType !== "2g"
  );
}

export function useDashboardData({
  currentMonth,
  filters,
  historyMonth,
  selectedHistoryMonths,
  includeClosedStores,
  activeSection,
  historyYearFilter,
  aggregateDetails,
}: UseDashboardDataParams) {
  const queryClient = useQueryClient();
  const buildQuery = useCallback(
    (month: string) => buildScopedMonthQuery(month, filters),
    [filters],
  );
  const buildHistoryQuery = useCallback(
    (month: string) => ({
      ...buildQuery(month),
      current_scope: true,
      include_closed_stores: includeClosedStores,
    }),
    [buildQuery, includeClosedStores],
  );
  const currentQueryParams = useMemo(
    () => buildCurrentDashboardQuery(currentMonth, filters),
    [currentMonth, filters],
  );
  const historyQueryParams = useMemo(
    () => ({ ...buildHistoryQuery(historyMonth), months_back: 12 }),
    [buildHistoryQuery, historyMonth],
  );
  const historyDetailQueries = useMemo(
    () => selectedHistoryMonths.map((month) => buildHistoryQuery(month)),
    [buildHistoryQuery, selectedHistoryMonths],
  );
  const historyDetailQueryParams = useMemo(
    () => ({
      selected_months: selectedHistoryMonths,
      queries: historyDetailQueries,
    }),
    [historyDetailQueries, selectedHistoryMonths],
  );
  const currentHistoryQueryParams = useMemo(
    () => ({ ...buildHistoryQuery(currentMonth), months_back: 14 }),
    [buildHistoryQuery, currentMonth],
  );
  const yearHistoryQueryParams = useMemo<
    (Omit<DashboardQuery, "month"> & { year: number }) | null
  >(() => {
    if (historyYearFilter === null) return null;
    const { month: _month, ...filterParams } = buildHistoryQuery(currentMonth);
    return { ...filterParams, year: historyYearFilter };
  }, [buildHistoryQuery, currentMonth, historyYearFilter]);

  const currentQuery = useQuery({
    queryKey: queryKeys.dashboard.current(currentMonth, currentQueryParams),
    queryFn: ({ signal }) => getDashboardAll(currentQueryParams, signal),
    enabled: activeSection !== "visits",
    staleTime: DASHBOARD_STALE_MS,
  });
  const historyQuery = useQuery({
    queryKey: queryKeys.dashboard.history(historyMonth, historyQueryParams),
    queryFn: ({ signal }) => getDashboardHistory(historyQueryParams, signal),
    enabled: activeSection === "history",
    staleTime: DASHBOARD_STALE_MS,
  });
  const historyDetailQuery = useQuery({
    queryKey: queryKeys.dashboard.historyDetail(
      selectedHistoryMonths,
      historyDetailQueryParams,
    ),
    queryFn: async ({ signal }) =>
      aggregateDetails(
        await getDashboardHistoryDetailsBatch(historyDetailQueries, signal),
        selectedHistoryMonths,
      ),
    enabled: activeSection === "history" && selectedHistoryMonths.length > 0,
    staleTime: DASHBOARD_STALE_MS,
  });
  const currentHistoryQuery = useQuery({
    queryKey: queryKeys.dashboard.currentHistory(
      currentMonth,
      currentHistoryQueryParams,
    ),
    queryFn: ({ signal }) =>
      getDashboardHistory(currentHistoryQueryParams, signal),
    enabled: activeSection === "history",
    staleTime: DASHBOARD_STALE_MS,
  });
  const yearHistoryQuery = useQuery({
    queryKey: queryKeys.dashboard.yearHistory(
      historyYearFilter ?? 0,
      yearHistoryQueryParams ?? { year: 0 },
    ),
    queryFn: ({ signal }) =>
      getDashboardHistoryYear(yearHistoryQueryParams!, signal),
    enabled: activeSection === "history" && yearHistoryQueryParams !== null,
    staleTime: DASHBOARD_STALE_MS,
  });

  const summary = currentQuery.data?.summary ?? null;
  const history = historyQuery.data?.history ?? EMPTY_HISTORY;
  const historyLoading =
    activeSection === "history" &&
    (historyQuery.isPending || historyDetailQuery.isPending);

  const refetchCurrentData = useCallback(() => {
    void currentQuery.refetch();
  }, [currentQuery]);
  const refetchHistoryData = useCallback(() => {
    void historyQuery.refetch();
    void historyDetailQuery.refetch();
  }, [historyDetailQuery, historyQuery]);

  useEffect(() => {
    if (!currentQuery.data || !shouldPrefetchDashboardHistory()) return;
    void queryClient.prefetchQuery({
      queryKey: queryKeys.dashboard.history(historyMonth, historyQueryParams),
      queryFn: ({ signal }) => getDashboardHistory(historyQueryParams, signal),
      staleTime: DASHBOARD_STALE_MS,
    });
  }, [currentQuery.data, historyMonth, historyQueryParams, queryClient]);

  return {
    summary,
    agents: currentQuery.data?.agents ?? EMPTY_AGENT_STATS,
    stores: currentQuery.data?.stores ?? EMPTY_STORE_STATS,
    dailySales: currentQuery.data?.daily ?? EMPTY_DAILY_SALES,
    dailyLastYear: currentQuery.data?.daily_last_year ?? EMPTY_DAILY_SALES,
    periodComparison: currentQuery.data?.period_comparison ?? null,
    categoryMix: currentQuery.data?.category_mix ?? EMPTY_CATEGORY_MIX,
    receiptBucketMix:
      currentQuery.data?.receipt_bucket_mix ?? EMPTY_RECEIPT_BUCKETS,
    focusSubcategoryMix:
      currentQuery.data?.focus_subcategory_mix ?? EMPTY_CATEGORY_MIX,
    brandMix: currentQuery.data?.brand_mix ?? EMPTY_BRAND_MIX,
    regionals: currentQuery.data?.regionals ?? EMPTY_REGIONAL_STATS,
    currentHistory: currentHistoryQuery.data?.history ?? EMPTY_HISTORY,
    currentHistoryLoading:
      currentHistoryQuery.isPending && activeSection === "history",
    yearHistory: yearHistoryQuery.data?.points ?? EMPTY_YEAR_HISTORY,
    yearHistoryLoading:
      yearHistoryQuery.isPending &&
      activeSection === "history" &&
      historyYearFilter !== null,
    history,
    historySummary: historyDetailQuery.data?.summary ?? null,
    historyReceiptBucketMix:
      historyDetailQuery.data?.receiptBucketMix ?? EMPTY_RECEIPT_BUCKETS,
    historyFocusSubcategoryMix:
      historyDetailQuery.data?.focusSubcategoryMix ?? EMPTY_CATEGORY_MIX,
    historyDailySales: historyDetailQuery.data?.dailySales ?? EMPTY_DAILY_SALES,
    historyCategoryMix:
      historyDetailQuery.data?.categoryMix ?? EMPTY_CATEGORY_MIX,
    historyBrandMix: historyDetailQuery.data?.brandMix ?? EMPTY_BRAND_MIX,
    historyRegionals:
      historyDetailQuery.data?.regionals ?? EMPTY_REGIONAL_STATS,
    historyStores: historyDetailQuery.data?.stores ?? EMPTY_STORE_STATS,
    historyAgents: historyDetailQuery.data?.agents ?? EMPTY_AGENT_STATS,
    loading: currentQuery.isPending,
    error:
      currentQuery.isError && !currentQuery.data
        ? currentQuery.error.message || "Eroare la incarcarea lunii in curs"
        : null,
    historyLoading,
    historyError:
      activeSection === "history"
        ? historyQuery.isError && !historyQuery.data
          ? historyQuery.error.message || "Istoricul nu a putut fi incarcat."
          : historyDetailQuery.isError && !historyDetailQuery.data
            ? historyDetailQuery.error.message ||
              "Istoricul nu a putut fi incarcat."
            : !historyLoading && history.length === 0
              ? "Nu exista date istorice pentru filtrarea curenta."
              : null
        : null,
    refetchCurrentData,
    refetchHistoryData,
  };
}
