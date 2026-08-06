import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getCampaignSnapshot,
  getFocusHistory,
  getPromotionsIncentives,
  type CampaignPromotionsQuery,
} from "../../api/campaigns";
import { getActiveContests } from "../../api/contests";
import { getPremiumGlassAnalysis } from "../../api/dashboard";
import type {
  CampaignSnapshot,
  CampaignsPromotionsResponse,
  ContestResponse,
  FocusHistoryPoint,
  PremiumGlassAnalysis,
  PremiumGlassSurfaceMode,
} from "../../api/generated/runtime-types";
import type { AppFilters } from "../../lib/appFilters";
import { buildScopedMonthQuery } from "../../lib/filterQueries";
import { queryKeys } from "../../lib/queryKeys";
import { getMonthEndDate } from "./formatters";
import type { CampaignSection } from "./types";

const EMPTY_SNAPSHOT: CampaignSnapshot = {
  overview: {
    month: "",
    total_focus_sales: 0,
    total_focus_qty: 0,
    focus_share_pct: null,
    active_focus_products: 0,
    active_focus_stores: 0,
  },
  products: [],
  stores: [],
};
const EMPTY_FOCUS_HISTORY: FocusHistoryPoint[] = [];
const EMPTY_CONTESTS: ContestResponse[] = [];
const CAMPAIGNS_STALE_MS = 3 * 60 * 1000;

type CampaignCurrentCache = {
  snapshot?: CampaignSnapshot;
  promoData?: CampaignsPromotionsResponse | null;
  premiumGlass?: PremiumGlassAnalysis | null;
};

export function useCampaignsData({
  currentMonth,
  months,
  filters,
  activeSection,
  onFilterMonthChange,
}: {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
  activeSection: CampaignSection;
  onFilterMonthChange?: (month: string) => void;
}) {
  const latestMonth = useMemo(
    () => months[0] ?? currentMonth,
    [months, currentMonth],
  );
  const [historyMonth, setHistoryMonth] = useState(latestMonth);
  const [promoMonth, setPromoMonth] = useState(latestMonth);
  const [selectedPromotionKey, setSelectedPromotionKey] = useState("");
  const [selectedContestKey, setSelectedContestKey] = useState("");
  const [premiumSurfaceMode, setPremiumSurfaceMode] =
    useState<PremiumGlassSurfaceMode>("all");

  useEffect(() => {
    const fallbackMonth = latestMonth || currentMonth;
    setHistoryMonth((previous) =>
      months.includes(previous) ? previous : fallbackMonth,
    );
    setPromoMonth((previous) => {
      if (!fallbackMonth) return "";
      if (!months.length) return fallbackMonth;
      if (!previous || previous === currentMonth) return fallbackMonth;
      return months.includes(previous) ? previous : fallbackMonth;
    });
  }, [months, currentMonth, latestMonth]);

  useEffect(() => {
    if (promoMonth) onFilterMonthChange?.(promoMonth);
  }, [promoMonth, onFilterMonthChange]);

  const buildQuery = useCallback(
    (month: string) => buildScopedMonthQuery(month, filters),
    [filters],
  );
  const promoQuery = useMemo(
    () => buildQuery(promoMonth),
    [buildQuery, promoMonth],
  );
  const promoScopeQuery = useMemo(
    () => ({
      ...promoQuery,
      current_scope: promoMonth === latestMonth,
      include_closed_stores: false,
    }),
    [latestMonth, promoMonth, promoQuery],
  );
  const historyQueryParams = useMemo(
    () => ({ ...buildQuery(historyMonth), months_back: 12 }),
    [buildQuery, historyMonth],
  );
  const shouldLoadPromoData =
    activeSection === "promo" || activeSection === "incentive";
  const shouldLoadSnapshot = activeSection === "focus";
  const shouldLoadPremiumGlass = activeSection === "premium";
  const shouldLoadCurrent =
    shouldLoadPromoData || shouldLoadSnapshot || shouldLoadPremiumGlass;

  const currentQuery = useQuery({
    queryKey: queryKeys.campaigns.current(
      activeSection,
      promoMonth,
      selectedPromotionKey,
      shouldLoadPremiumGlass
        ? { ...promoScopeQuery, surface: premiumSurfaceMode }
        : promoScopeQuery,
    ),
    enabled: Boolean(promoMonth) && shouldLoadCurrent,
    staleTime: CAMPAIGNS_STALE_MS,
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) => {
      const result: CampaignCurrentCache = {};
      const requests: Promise<void>[] = [];
      if (shouldLoadSnapshot)
        requests.push(
          getCampaignSnapshot(promoQuery, signal).then((data) => {
            result.snapshot = data;
          }),
        );
      if (shouldLoadPromoData)
        requests.push((async () => {
          const { month: _month, ...scope } = promoScopeQuery;
          const query: CampaignPromotionsQuery = {
            ...scope,
            start_date: `${promoMonth}-01`,
            end_date: getMonthEndDate(promoMonth),
            view: activeSection === "promo" ? "promo" : "incentive",
            ...(selectedPromotionKey && {
              promotion_key: selectedPromotionKey,
            }),
          };
          result.promoData = await getPromotionsIncentives(query, signal);
        })());
      if (shouldLoadPremiumGlass)
        requests.push(
          getPremiumGlassAnalysis(
            {
              ...promoQuery,
              surface: premiumSurfaceMode,
              current_scope: true,
              include_closed_stores: false,
            },
            signal,
          ).then((data) => {
            result.premiumGlass = data;
          }),
        );
      await Promise.all(requests);
      return result;
    },
  });
  const focusHistoryQuery = useQuery({
    queryKey: queryKeys.campaigns.history(historyMonth, historyQueryParams),
    enabled: activeSection === "focus" && Boolean(historyMonth),
    staleTime: CAMPAIGNS_STALE_MS,
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) => getFocusHistory(historyQueryParams, signal),
  });
  const contestsQuery = useQuery({
    queryKey: queryKeys.campaigns.contests(promoMonth),
    enabled: activeSection === "concurs" && Boolean(promoMonth),
    staleTime: CAMPAIGNS_STALE_MS,
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) => getActiveContests(promoMonth, signal),
  });

  const currentData = currentQuery.data ?? {};
  const promoData = currentData.promoData ?? null;
  const contests = contestsQuery.data ?? EMPTY_CONTESTS;
  const focusHistory = focusHistoryQuery.data?.history ?? EMPTY_FOCUS_HISTORY;
  const promoSelectionPending = Boolean(
    shouldLoadPromoData &&
    selectedPromotionKey &&
    promoData?.selected_promotion_key &&
    promoData.selected_promotion_key !== selectedPromotionKey,
  );

  useEffect(() => {
    if (!promoData) return;
    const availableKeys = promoData.promotions.map(
      (promotion) => promotion.key,
    );
    if (
      selectedPromotionKey &&
      availableKeys.length > 0 &&
      !availableKeys.includes(selectedPromotionKey)
    ) {
      setSelectedPromotionKey(availableKeys[0] ?? selectedPromotionKey);
    }
  }, [promoData, selectedPromotionKey]);
  useEffect(() => {
    if (activeSection !== "concurs") return;
    setSelectedContestKey((previous) =>
      contests.some((contest) => contest.key === previous)
        ? previous
        : (contests[0]?.key ?? ""),
    );
  }, [activeSection, contests]);

  const hasCurrentData =
    !shouldLoadCurrent ||
    (shouldLoadPromoData &&
      currentData.promoData !== undefined &&
      !promoSelectionPending) ||
    (shouldLoadSnapshot && currentData.snapshot !== undefined) ||
    (shouldLoadPremiumGlass && currentData.premiumGlass !== undefined);
  const currentError =
    currentQuery.isError && !hasCurrentData
      ? "Datele pentru campanii si focus nu au putut fi incarcate."
      : "";
  const historyError = focusHistoryQuery.isError
    ? "Istoricul focus nu a putut fi incarcat."
    : focusHistoryQuery.isSuccess && focusHistory.length === 0
      ? "Nu exista istoric focus pentru filtrarea curenta."
      : "";
  const contestError =
    contestsQuery.isError && !contestsQuery.data
      ? "Concursul nu a putut fi incarcat."
      : "";

  return {
    latestMonth,
    promoMonth,
    setPromoMonth,
    historyMonth,
    setHistoryMonth,
    selectedPromotionKey,
    setSelectedPromotionKey,
    selectedContestKey,
    setSelectedContestKey,
    premiumSurfaceMode,
    setPremiumSurfaceMode,
    promoData,
    contests,
    focusHistory,
    snapshot: currentData.snapshot ?? EMPTY_SNAPSHOT,
    premiumGlass: currentData.premiumGlass ?? null,
    loading:
      shouldLoadCurrent &&
      currentQuery.isFetching &&
      (!hasCurrentData || promoSelectionPending),
    currentError,
    historyLoading:
      activeSection === "focus" &&
      focusHistoryQuery.isFetching &&
      !focusHistoryQuery.data,
    historyError,
    contestLoading:
      activeSection === "concurs" &&
      contestsQuery.isFetching &&
      !contestsQuery.data,
    contestError,
    refetchCurrent: currentQuery.refetch,
    refetchHistory: focusHistoryQuery.refetch,
    refetchContests: contestsQuery.refetch,
  };
}
