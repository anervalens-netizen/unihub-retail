import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  Building2,
  CalendarRange,
  MapPin,
  PieChart as PieChartIcon,
  Sparkles,
  TrendingUp,
  Users,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getDashboardAll, getDashboardHistory, getDashboardHistoryYear } from '../api/dashboard';
import type {
  AgentStat,
  AsmStat,
  BrandMixItem,
  CategoryMixItem,
  DailySalesPoint,
  DashboardSpecialCard,
  DashboardSummary,
  MonthlyHistoryPoint,
  PeriodComparisonPayload,
  PeriodComparisonPoint,
  PromoIncentiveSummary,
  ReceiptBucketItem,
  RegionalStat,
  StoreStat,
  YearHistoryPoint,
} from '../api/types';
import { buildScopedMonthQuery } from '../lib/filterQueries';
import { formatCurrency, formatInt, formatPercent } from '../lib/formatters';
import { getCachedView, setCachedView } from '../lib/viewCache';
import type { AppFilters } from './MainLayout';
import { VisiteSubtab } from './VisiteSubtab';
import {
  CampaignMiniCard,
  CompactCurrency,
  CompactPieSection,
  DeltaCard,
  ErrorCard,
  KpiPerformanceCard,
  LoadingCard,
  Metric,
  PeriodTable,
  SortableHeader,
  describeFilterScope,
  formatCompactDonutValue,
  getAgentSortValue,
  getAsmSortValue,
  getBon2AccTone,
  getFocusTone,
  getRegionalSortValue,
  getStoreDailyAverage,
  getStoreSortValue,
  sumChartValues,
} from './dashboard/DashboardWidgets';

interface DashboardProps {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
  onSectionChange?: (section: DashboardSection) => void;
}

type DashboardSection = 'current' | 'history' | 'visits';
type SortDirection = 'asc' | 'desc';
type StoreSortKey =
  | 'locatie'
  | 'site_code'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'forecast_target_pct'
  | 'incentive_qty'
  | 'qty_total'
  | 'nr_bonuri'
  | 'nr_agenti'
  | 'zile_active'
  | 'medie_zilnica';
type AgentSortKey =
  | 'locatie'
  | 'agent'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'promo_qty'
  | 'incentive_qty'
  | 'acc_qty_realizat'
  | 'nr_bonuri'
  | 'zile_lucrate'
  | 'medie_zilnica'
  | 'proc_bon2acc'
  | 'prc_focus_acc_qty';

type RegionalSortKey =
  | 'regional'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'forecast_target_pct'
  | 'promo_qty'
  | 'incentive_qty'
  | 'qty_total'
  | 'nr_bonuri'
  | 'medie_zilnica'
  | 'proc_bon2acc'
  | 'prc_focus_acc_qty';

type AsmSortKey =
  | 'asm'
  | 'regional'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'promo_qty'
  | 'incentive_qty'
  | 'qty_total'
  | 'nr_bonuri'
  | 'medie_zilnica'
  | 'proc_bon2acc'
  | 'prc_focus_acc_qty';

const DEFAULT_PROMO_INCENTIVE: PromoIncentiveSummary = {
  promo_qty: 0,
  promo_sales: 0,
  promo_impact: 0,
  incentive_qty: 0,
  incentive_value: 0,
  incentive_qualified_stores: 0,
  incentive_qualified_agents: 0,
};
const DASHBOARD_CACHE_TTL_MS = 3 * 60 * 1000;
const TABLE_MAX_HEIGHT_CLASS = 'max-h-[30rem]';
const COMPACT_TH_CLASS = 'px-2 py-2 whitespace-nowrap';
const COMPACT_TD_CLASS = 'px-2 py-1.5 whitespace-nowrap';
const REGIONAL_TABLE_CLASS = 'w-max min-w-[980px] border-collapse text-[11px]';
const STORE_TABLE_CLASS = 'w-max min-w-[1080px] border-collapse text-[11px]';

const CATEGORY_SHORT: Record<string, string> = {
  'Casti intraauriculare': 'Casti intraaur.',
  'Baterie Externa': 'Baterie Ext.',
  'Suport telescopic': 'Suport telesk.',
  'Suport auto': 'Suport auto',
};

const STORE_COLUMNS: Array<{ key: StoreSortKey; label: string }> = [
  { key: 'locatie', label: 'Magazin' },
  { key: 'site_code', label: 'Firma' },
  { key: 'target', label: 'Target' },
  { key: 'total_vanzari', label: 'Vanzari' },
  { key: 'proc_realizare_target', label: 'Procent' },
  { key: 'forecast_target_pct', label: 'Forecast%' },
  { key: 'incentive_qty', label: 'Incentive' },
  { key: 'qty_total', label: 'Cantitate' },
  { key: 'nr_bonuri', label: 'Nr bonuri' },
  { key: 'nr_agenti', label: 'Agenti' },
  { key: 'zile_active', label: 'Zile active' },
  { key: 'medie_zilnica', label: 'Medie zilnica' },
];

const AGENT_COLUMNS: Array<{ key: AgentSortKey; label: string }> = [
  { key: 'agent', label: 'Agent' },
  { key: 'locatie', label: 'Magazin' },
  { key: 'target', label: 'Target' },
  { key: 'total_vanzari', label: 'Vanzari' },
  { key: 'proc_realizare_target', label: 'Procent' },
  { key: 'promo_qty', label: 'Promo' },
  { key: 'incentive_qty', label: 'Incentive' },
  { key: 'acc_qty_realizat', label: 'Cantitate' },
  { key: 'nr_bonuri', label: 'Nr bonuri' },
  { key: 'zile_lucrate', label: 'Zile lucrate' },
  { key: 'medie_zilnica', label: 'Medie zilnica' },
  { key: 'proc_bon2acc', label: 'ProcBon2Acc' },
  { key: 'prc_focus_acc_qty', label: 'Focus%' },
];

const REGIONAL_COLUMNS: Array<{ key: RegionalSortKey; label: string }> = [
  { key: 'regional', label: 'Regional' },
  { key: 'target', label: 'Target' },
  { key: 'total_vanzari', label: 'Vanzari' },
  { key: 'proc_realizare_target', label: 'Procent' },
  { key: 'forecast_target_pct', label: 'Forecast%' },
  { key: 'promo_qty', label: 'Promo' },
  { key: 'incentive_qty', label: 'Incentive' },
  { key: 'qty_total', label: 'Cantitate' },
  { key: 'nr_bonuri', label: 'Nr bonuri' },
  { key: 'medie_zilnica', label: 'Medie zilnica' },
  { key: 'proc_bon2acc', label: 'ProcBon2Acc' },
  { key: 'prc_focus_acc_qty', label: 'Focus%' },
];

const ASM_COLUMNS: Array<{ key: AsmSortKey; label: string }> = [
  { key: 'asm', label: 'ASM' },
  { key: 'target', label: 'Target' },
  { key: 'total_vanzari', label: 'Vanzari' },
  { key: 'proc_realizare_target', label: 'Procent' },
  { key: 'promo_qty', label: 'Promo' },
  { key: 'incentive_qty', label: 'Incentive' },
  { key: 'qty_total', label: 'Cantitate' },
  { key: 'nr_bonuri', label: 'Nr bonuri' },
  { key: 'medie_zilnica', label: 'Medie zilnica' },
  { key: 'proc_bon2acc', label: 'ProcBon2Acc' },
  { key: 'prc_focus_acc_qty', label: 'Focus%' },
];

const HIST_REGIONAL_COLUMNS = REGIONAL_COLUMNS.filter((c) => c.key !== 'promo_qty' && c.key !== 'forecast_target_pct');
const HIST_ASM_COLUMNS = ASM_COLUMNS.filter((c) => c.key !== 'promo_qty');
const HIST_STORE_COLUMNS = STORE_COLUMNS.filter((c) => c.key !== 'forecast_target_pct');
const HIST_AGENT_COLUMNS = AGENT_COLUMNS.filter((c) => c.key !== 'promo_qty');

export function Dashboard({ currentMonth, months, filters, onSectionChange }: DashboardProps) {
  const [activeSection, setActiveSection] = useState<DashboardSection>('current');
  const [historyMonth, setHistoryMonth] = useState(currentMonth);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [agents, setAgents] = useState<AgentStat[]>([]);
  const [stores, setStores] = useState<StoreStat[]>([]);
  const [dailySales, setDailySales] = useState<DailySalesPoint[]>([]);
  const [specialCards, setSpecialCards] = useState<DashboardSpecialCard[]>([]);
  const [periodComparison, setPeriodComparison] = useState<PeriodComparisonPayload | null>(null);
  const [categoryMix, setCategoryMix] = useState<CategoryMixItem[]>([]);
  const [receiptBucketMix, setReceiptBucketMix] = useState<ReceiptBucketItem[]>([]);
  const [focusSubcategoryMix, setFocusSubcategoryMix] = useState<CategoryMixItem[]>([]);
  const [brandMix, setBrandMix] = useState<BrandMixItem[]>([]);
  const [promoIncentive, setPromoIncentive] =
    useState<PromoIncentiveSummary>(DEFAULT_PROMO_INCENTIVE);
  const [currentHistory, setCurrentHistory] = useState<MonthlyHistoryPoint[]>([]);
  const [currentHistoryLoading, setCurrentHistoryLoading] = useState(false);
  const [historyYearFilter, setHistoryYearFilter] = useState<number | null>(null);
  const [yearHistory, setYearHistory] = useState<YearHistoryPoint[]>([]);
  const [yearHistoryLoading, setYearHistoryLoading] = useState(false);
  const [history, setHistory] = useState<MonthlyHistoryPoint[]>([]);
  const [historySummary, setHistorySummary] = useState<DashboardSummary | null>(null);
  const [historyReceiptBucketMix, setHistoryReceiptBucketMix] = useState<ReceiptBucketItem[]>([]);
  const [historyFocusSubcategoryMix, setHistoryFocusSubcategoryMix] = useState<CategoryMixItem[]>([]);
  const [historyDailySales, setHistoryDailySales] = useState<DailySalesPoint[]>([]);
  const [historyCategoryMix, setHistoryCategoryMix] = useState<CategoryMixItem[]>([]);
  const [historyBrandMix, setHistoryBrandMix] = useState<BrandMixItem[]>([]);
  const [historySpecialCards, setHistorySpecialCards] = useState<DashboardSpecialCard[]>([]);
  const [historyPeriodComparison, setHistoryPeriodComparison] = useState<PeriodComparisonPayload | null>(null);
  const [historyPromoIncentive, setHistoryPromoIncentive] = useState<PromoIncentiveSummary>(DEFAULT_PROMO_INCENTIVE);
  const [historyRegionals, setHistoryRegionals] = useState<RegionalStat[]>([]);
  const [historyAsms, setHistoryAsms] = useState<AsmStat[]>([]);
  const [historyStores, setHistoryStores] = useState<StoreStat[]>([]);
  const [historyAgents, setHistoryAgents] = useState<AgentStat[]>([]);
  const [kpiMetric, setKpiMetric] = useState<'proc_bon2acc' | 'prc_focus_acc_qty' | 'total_receipts'>('proc_bon2acc');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [storeSort, setStoreSort] = useState<{ key: StoreSortKey; direction: SortDirection }>({
    key: 'proc_realizare_target',
    direction: 'desc',
  });
  const [agentSort, setAgentSort] = useState<{ key: AgentSortKey; direction: SortDirection }>({
    key: 'total_vanzari',
    direction: 'desc',
  });
  const [regionalSort, setRegionalSort] = useState<{ key: RegionalSortKey; direction: SortDirection }>({
    key: 'total_vanzari',
    direction: 'desc',
  });
  const [asmSort, setAsmSort] = useState<{ key: AsmSortKey; direction: SortDirection }>({
    key: 'total_vanzari',
    direction: 'desc',
  });
  const [historyRegionalSort, setHistoryRegionalSort] = useState<{ key: RegionalSortKey; direction: SortDirection }>({ key: 'total_vanzari', direction: 'desc' });
  const [historyAsmSort, setHistoryAsmSort] = useState<{ key: AsmSortKey; direction: SortDirection }>({ key: 'total_vanzari', direction: 'desc' });
  const [historyStoreSort, setHistoryStoreSort] = useState<{ key: StoreSortKey; direction: SortDirection }>({ key: 'total_vanzari', direction: 'desc' });
  const [historyAgentSort, setHistoryAgentSort] = useState<{ key: AgentSortKey; direction: SortDirection }>({ key: 'total_vanzari', direction: 'desc' });
  const [regionals, setRegionals] = useState<RegionalStat[]>([]);
  const [asms, setAsms] = useState<AsmStat[]>([]);
  const isMountedRef = useRef(true);

  useEffect(() => {
    setHistoryMonth((previous) => (months.includes(previous) ? previous : currentMonth));
  }, [months, currentMonth]);

  const buildQuery = useCallback(
    (month: string) => buildScopedMonthQuery(month, filters),
    [filters]
  );

  const currentCacheKey = useMemo(
    () => `dashboard:current:${currentMonth}:${JSON.stringify(buildQuery(currentMonth))}`,
    [buildQuery, currentMonth]
  );
  const historyCacheKey = useMemo(
    () => `dashboard:history:${historyMonth}:${JSON.stringify({ ...buildQuery(historyMonth), months_back: 12 })}`,
    [buildQuery, historyMonth]
  );
  const historyDetailCacheKey = useMemo(
    () => `dashboard:history-detail:${historyMonth}:${JSON.stringify(buildQuery(historyMonth))}`,
    [buildQuery, historyMonth]
  );

  const prefetchHistory = useCallback(
    (monthToPrefetch: string) => {
      const query = { ...buildQuery(monthToPrefetch), months_back: 12 };
      const cacheKey = `dashboard:history:${monthToPrefetch}:${JSON.stringify(query)}`;
      const cached = getCachedView<MonthlyHistoryPoint[]>(cacheKey, DASHBOARD_CACHE_TTL_MS);
      if (cached.isFresh) {
        return;
      }

      getDashboardHistory(query)
        .then((data) => {
          setCachedView(cacheKey, data.history);
        })
        .catch(() => {
          // background prefetch stays silent
        });
    },
    [buildQuery]
  );

  const fetchCurrentData = useCallback(() => {
    if (!isMountedRef.current) return;
    const cached = getCachedView<{
      summary: DashboardSummary;
      agents: AgentStat[];
      stores: StoreStat[];
      regionals: RegionalStat[];
      asms: AsmStat[];
      dailySales: DailySalesPoint[];
      specialCards: DashboardSpecialCard[];
      periodComparison: PeriodComparisonPayload | null;
      categoryMix: CategoryMixItem[];
      receiptBucketMix: ReceiptBucketItem[];
      focusSubcategoryMix: CategoryMixItem[];
      brandMix: BrandMixItem[];
      promoIncentive: PromoIncentiveSummary;
    }>(currentCacheKey, DASHBOARD_CACHE_TTL_MS);

    if (cached.value) {
      setSummary(cached.value.summary);
      setAgents(cached.value.agents);
      setStores(cached.value.stores);
      setRegionals(cached.value.regionals);
      setAsms(cached.value.asms);
      setDailySales(cached.value.dailySales);
      setSpecialCards(cached.value.specialCards);
      setPeriodComparison(cached.value.periodComparison);
      setCategoryMix(cached.value.categoryMix);
      setReceiptBucketMix(cached.value.receiptBucketMix);
      setFocusSubcategoryMix(cached.value.focusSubcategoryMix);
      setBrandMix(cached.value.brandMix);
      setPromoIncentive(cached.value.promoIncentive);
      setLoading(false);
      setError(null);
      if (cached.isFresh) {
        return;
      }
    }

    setLoading(true);
    setError(null);
    getDashboardAll(buildQuery(currentMonth))
      .then((data) => {
        if (!isMountedRef.current) return;
        setSummary(data.summary);
        setAgents(data.agents);
        setStores(data.stores);
        setRegionals(data.regionals || []);
        setAsms(data.asms || []);
        setDailySales(data.daily);
        setSpecialCards(data.special_cards);
        setPeriodComparison(data.period_comparison);
        setCategoryMix(data.category_mix);
        setReceiptBucketMix(data.receipt_bucket_mix);
        setFocusSubcategoryMix(data.focus_subcategory_mix);
        setBrandMix(data.brand_mix);
        setPromoIncentive(data.promo_incentive ?? DEFAULT_PROMO_INCENTIVE);
        setCachedView(currentCacheKey, {
          summary: data.summary,
          agents: data.agents,
          stores: data.stores,
          regionals: data.regionals || [],
          asms: data.asms || [],
          dailySales: data.daily,
          specialCards: data.special_cards,
          periodComparison: data.period_comparison,
          categoryMix: data.category_mix,
          receiptBucketMix: data.receipt_bucket_mix,
          focusSubcategoryMix: data.focus_subcategory_mix,
          brandMix: data.brand_mix,
          promoIncentive: data.promo_incentive ?? DEFAULT_PROMO_INCENTIVE,
        });
      })
      .catch((err: Error) => {
        if (!isMountedRef.current) return;
        setError(err.message || 'Eroare la incarcarea lunii in curs');
      })
      .finally(() => {
        if (isMountedRef.current) setLoading(false);
      });
  }, [buildQuery, currentCacheKey, currentMonth]);

  const loadHistory = useCallback(() => {
    if (!isMountedRef.current) return;
    const cached = getCachedView<MonthlyHistoryPoint[]>(historyCacheKey, DASHBOARD_CACHE_TTL_MS);
    const cachedDetail = getCachedView<{
      summary: DashboardSummary;
      receiptBucketMix: ReceiptBucketItem[];
      focusSubcategoryMix: CategoryMixItem[];
      dailySales: DailySalesPoint[];
      categoryMix: CategoryMixItem[];
      brandMix: BrandMixItem[];
      specialCards: DashboardSpecialCard[];
      periodComparison: PeriodComparisonPayload | null;
      promoIncentive: PromoIncentiveSummary;
      regionals: RegionalStat[];
      asms: AsmStat[];
      stores: StoreStat[];
      agents: AgentStat[];
    }>(historyDetailCacheKey, DASHBOARD_CACHE_TTL_MS);

    if (cached.value) {
      setHistory(cached.value);
      setHistoryError(cached.value.length === 0 ? 'Nu exista date istorice pentru filtrarea curenta.' : '');
      if (cachedDetail.value) {
        setHistorySummary(cachedDetail.value.summary);
        setHistoryReceiptBucketMix(cachedDetail.value.receiptBucketMix);
        setHistoryFocusSubcategoryMix(cachedDetail.value.focusSubcategoryMix);
        setHistoryDailySales(cachedDetail.value.dailySales);
        setHistoryCategoryMix(cachedDetail.value.categoryMix);
        setHistoryBrandMix(cachedDetail.value.brandMix);
        setHistorySpecialCards(cachedDetail.value.specialCards);
        setHistoryPeriodComparison(cachedDetail.value.periodComparison);
        setHistoryPromoIncentive(cachedDetail.value.promoIncentive);
        setHistoryRegionals(cachedDetail.value.regionals ?? []);
        setHistoryAsms(cachedDetail.value.asms ?? []);
        setHistoryStores(cachedDetail.value.stores ?? []);
        setHistoryAgents(cachedDetail.value.agents ?? []);
      }
      setHistoryLoading(false);
      if (cached.isFresh && cachedDetail.isFresh) {
        return;
      }
    }

    setHistoryLoading(true);
    setHistoryError(null);
    Promise.all([
      getDashboardHistory({ ...buildQuery(historyMonth), months_back: 12 }),
      getDashboardAll(buildQuery(historyMonth)),
    ])
      .then(([histData, allData]) => {
        if (!isMountedRef.current) return;
        setHistory(histData.history);
        setCachedView(historyCacheKey, histData.history);
        setHistorySummary(allData.summary);
        setHistoryReceiptBucketMix(allData.receipt_bucket_mix);
        setHistoryFocusSubcategoryMix(allData.focus_subcategory_mix);
        setHistoryDailySales(allData.daily);
        setHistoryCategoryMix(allData.category_mix);
        setHistoryBrandMix(allData.brand_mix);
        setHistorySpecialCards(allData.special_cards);
        setHistoryPeriodComparison(allData.period_comparison);
        setHistoryPromoIncentive(allData.promo_incentive ?? DEFAULT_PROMO_INCENTIVE);
        setHistoryRegionals(allData.regionals ?? []);
        setHistoryAsms(allData.asms ?? []);
        setHistoryStores(allData.stores ?? []);
        setHistoryAgents(allData.agents ?? []);
        setCachedView(historyDetailCacheKey, {
          summary: allData.summary,
          receiptBucketMix: allData.receipt_bucket_mix,
          focusSubcategoryMix: allData.focus_subcategory_mix,
          dailySales: allData.daily,
          categoryMix: allData.category_mix,
          brandMix: allData.brand_mix,
          specialCards: allData.special_cards,
          periodComparison: allData.period_comparison,
          promoIncentive: allData.promo_incentive ?? DEFAULT_PROMO_INCENTIVE,
          regionals: allData.regionals ?? [],
          asms: allData.asms ?? [],
          stores: allData.stores,
          agents: allData.agents,
        });
        if (histData.history.length === 0) {
          setHistoryError('Nu exista date istorice pentru filtrarea curenta.');
        }
      })
      .catch((err: Error) => {
        if (!isMountedRef.current) return;
        setHistory([]);
        setHistoryError(err.message || 'Istoricul nu a putut fi incarcat.');
      })
      .finally(() => {
        if (isMountedRef.current) setHistoryLoading(false);
      });
  }, [buildQuery, historyCacheKey, historyDetailCacheKey, historyMonth]);

  useEffect(() => {
    isMountedRef.current = true;
    fetchCurrentData();
    return () => {
      isMountedRef.current = false;
    };
  }, [fetchCurrentData]);

  // Prefetch history data in background (decoupled from fetchCurrentData to avoid
  // re-fetching current data when only historyMonth changes)
  useEffect(() => {
    if (!loading) {
      prefetchHistory(historyMonth);
    }
  }, [loading, historyMonth, prefetchHistory]);

  useEffect(() => {
    onSectionChange?.(activeSection);
  }, [activeSection, onSectionChange]);

  useEffect(() => {
    setHistory([]);
    setHistorySummary(null);
    setHistoryReceiptBucketMix([]);
    setHistoryFocusSubcategoryMix([]);
    setHistoryDailySales([]);
    setHistoryCategoryMix([]);
    setHistoryBrandMix([]);
    setHistorySpecialCards([]);
    setHistoryPeriodComparison(null);
    setHistoryPromoIncentive(DEFAULT_PROMO_INCENTIVE);
    setHistoryRegionals([]);
    setHistoryAsms([]);
    setHistoryStores([]);
    setHistoryAgents([]);
    setHistoryError(null);
    if (activeSection === 'history') {
      loadHistory();
    }
  }, [activeSection, historyMonth, loadHistory]);

  // Reset currentHistory when filters or month change so it reloads with new params
  useEffect(() => {
    setCurrentHistory([]);
  }, [buildQuery, currentMonth]);

  // Load currentHistory when opening Istoric (or after reset above)
  useEffect(() => {
    if (activeSection !== 'history' || currentHistory.length > 0 || currentHistoryLoading) return;
    setCurrentHistoryLoading(true);
    getDashboardHistory({ ...buildQuery(currentMonth), months_back: 13 })
      .then((data) => { if (isMountedRef.current) setCurrentHistory(data.history); })
      .catch((err: Error) => { if (isMountedRef.current) setCurrentHistory([]); console.warn('currentHistory fetch failed:', err.message); })
      .finally(() => { if (isMountedRef.current) setCurrentHistoryLoading(false); });
  }, [activeSection, currentHistory.length, currentHistoryLoading, buildQuery, currentMonth]);

  // Load year history when a specific year is selected
  useEffect(() => {
    if (historyYearFilter === null || activeSection !== 'history') return;
    setYearHistoryLoading(true);
    setYearHistory([]);
    const { month: _month, ...filterParams } = buildQuery(currentMonth);
    getDashboardHistoryYear({ ...filterParams, year: historyYearFilter })
      .then((data) => { if (isMountedRef.current) setYearHistory(data.points); })
      .catch((err: Error) => { if (isMountedRef.current) setYearHistory([]); console.warn('yearHistory fetch failed:', err.message); })
      .finally(() => { if (isMountedRef.current) setYearHistoryLoading(false); });
  }, [historyYearFilter, activeSection, buildQuery, currentMonth]);

  const availableYears = useMemo(() => {
    const cy = parseInt(currentMonth.slice(0, 4));
    return Array.from({ length: cy - 2022 + 1 }, (_, i) => 2022 + i);
  }, [currentMonth]);

  const promoSummary = useMemo(() => {
    const promotion = specialCards.find((card) => card.key === 'promotion');
    const incentive = specialCards.find((card) => card.key === 'incentive');
    return { promotion, incentive };
  }, [specialCards]);

  const dailyChartData = useMemo(
    () =>
      dailySales.map((item) => ({
        day: item.sale_date.slice(-2),
        sales: Number(item.total_sales),
        qty: Number(item.total_quantity),
        receipts: Number(item.receipt_count),
      })),
    [dailySales]
  );

  const historyChartData = useMemo(
    () =>
      history.map((item) => ({
        month: item.month.slice(2),
        sales: Number(item.total_sales),
        target: Number(item.total_target),
        progress: Number(item.target_progress_pct ?? 0),
      })),
    [history]
  );

  // Card 1 data — always anchored to currentMonth; last bar shows forecast if month not final
  const currentHistoryChartData = useMemo(() => {
    return currentHistory.map((item, idx) => {
      const isLast = idx === currentHistory.length - 1;
      const isForecast = isLast && summary != null && !summary.is_month_final;
      const forecastSales = isForecast ? Number(summary!.forecast_sales ?? item.total_sales) : null;
      const target = Number(item.total_target);
      const progress = isForecast && forecastSales != null && target > 0
        ? Math.round(forecastSales / target * 10000) / 100
        : Number(item.target_progress_pct ?? 0);
      return {
        month: item.month.slice(2),
        sales: isForecast ? forecastSales! : Number(item.total_sales),
        target,
        progress,
        isForecast,
      };
    });
  }, [currentHistory, summary]);

  const yearHistoryChartData = useMemo(
    () =>
      yearHistory.map((pt) => ({
        label: pt.label,
        sales: Number(pt.total_sales),
        target: Number(pt.total_target),
        progress: pt.total_target > 0
          ? Math.round((Number(pt.total_sales) / Number(pt.total_target)) * 100 * 100) / 100
          : 0,
        isAggregate: pt.is_aggregate,
      })),
    [yearHistory]
  );

  // KPI trend data for new Card 2
  const kpiChartData = useMemo(
    () =>
      currentHistory.map((item) => ({
        month: item.month.slice(2),
        value:
          kpiMetric === 'total_receipts'
            ? Number(item.total_receipts)
            : Number(item[kpiMetric] ?? 0),
      })),
    [currentHistory, kpiMetric]
  );

  const selectedHistoryPoint = useMemo(
    () => history.find((item) => item.month === historyMonth) ?? history[history.length - 1] ?? null,
    [history, historyMonth]
  );

  const comparisonDeltas = useMemo(() => {
    if (!periodComparison) return null;
    const current = Number(periodComparison.current.total_sales);
    const previous = Number(periodComparison.previous.total_sales);
    const yearOverYear = Number(periodComparison.year_over_year.total_sales);
    const currentReceipts = Number(periodComparison.current.total_receipts);
    const previousReceipts = Number(periodComparison.previous.total_receipts);
    const yearOverYearReceipts = Number(periodComparison.year_over_year.total_receipts);
    const currentQuantity = Number(periodComparison.current.total_quantity);
    const previousQuantity = Number(periodComparison.previous.total_quantity);
    const yearOverYearQuantity = Number(periodComparison.year_over_year.total_quantity);
    const pct = (delta: number, base: number) => base > 0 ? Math.round((delta / base) * 100) : null;

    return {
      previousSales: current - previous,
      previousSalesPct: pct(current - previous, previous),
      previousReceipts: currentReceipts - previousReceipts,
      previousReceiptsPct: pct(currentReceipts - previousReceipts, previousReceipts),
      previousQuantity: currentQuantity - previousQuantity,
      previousQuantityPct: pct(currentQuantity - previousQuantity, previousQuantity),
      yearSales: current - yearOverYear,
      yearSalesPct: pct(current - yearOverYear, yearOverYear),
      yearReceipts: currentReceipts - yearOverYearReceipts,
      yearReceiptsPct: pct(currentReceipts - yearOverYearReceipts, yearOverYearReceipts),
      yearQuantity: currentQuantity - yearOverYearQuantity,
      yearQuantityPct: pct(currentQuantity - yearOverYearQuantity, yearOverYearQuantity),
    };
  }, [periodComparison]);

  const currentStatusLabel = useMemo(() => {
    if (!summary) return '';
    if (summary.is_month_final) {
      return `Luna finala pentru ${currentMonth}, inchisa la ${summary.last_sale_date ?? currentMonth}.`;
    }
    return `Luna in curs ${currentMonth} este inca in actualizare pana in ziua ${summary.imported_day_of_month ?? '-'} din ${summary.days_in_month ?? '-'}.`;
  }, [summary, currentMonth]);

  const handleOpenFocus = useCallback(() => {
    window.dispatchEvent(
      new CustomEvent('unihub:navigate', {
        detail: { tab: 'focus', section: 'promo' },
      })
    );
  }, []);

  const categoryMixChartData = useMemo(
    () =>
      categoryMix.map((item) => ({
        category: item.category,
        sales_total: Number(item.sales_total),
        quantity_total: Number(item.quantity_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [categoryMix]
  );

  const receiptBucketChartData = useMemo(
    () =>
      receiptBucketMix.map((item) => ({
        bucket: item.bucket,
        receipt_count: Number(item.receipt_count),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [receiptBucketMix]
  );

  const focusSubcategoryChartData = useMemo(
    () =>
      focusSubcategoryMix.map((item) => ({
        category: CATEGORY_SHORT[item.category] ?? item.category,
        quantity_total: Number(item.quantity_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [focusSubcategoryMix]
  );

  const historyReceiptBucketChartData = useMemo(
    () =>
      historyReceiptBucketMix.map((item) => ({
        bucket: item.bucket,
        receipt_count: Number(item.receipt_count),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [historyReceiptBucketMix]
  );

  const historyFocusSubcategoryChartData = useMemo(
    () =>
      historyFocusSubcategoryMix.map((item) => ({
        category: CATEGORY_SHORT[item.category] ?? item.category,
        quantity_total: Number(item.quantity_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [historyFocusSubcategoryMix]
  );

  const historyStatusLabel = useMemo(() => {
    if (!historySummary) return '';
    if (historySummary.is_month_final) {
      return `Luna finala ${historyMonth}, inchisa la ${historySummary.last_sale_date ?? historyMonth}.`;
    }
    return `Luna ${historyMonth} este inca in actualizare pana in ziua ${historySummary.imported_day_of_month ?? '-'} din ${historySummary.days_in_month ?? '-'}.`;
  }, [historySummary, historyMonth]);

  const historyDailyChartData = useMemo(
    () =>
      historyDailySales.map((item) => ({
        day: item.sale_date.slice(-2),
        sales: Number(item.total_sales),
        qty: Number(item.total_quantity),
        receipts: Number(item.receipt_count),
      })),
    [historyDailySales]
  );

  const historyCategoryMixChartData = useMemo(
    () =>
      historyCategoryMix.map((item) => ({
        category: item.category,
        sales_total: Number(item.sales_total),
        quantity_total: Number(item.quantity_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [historyCategoryMix]
  );

  const historyBrandMixChartData = useMemo(
    () =>
      historyBrandMix.map((item) => ({
        brand: item.brand,
        sales_total: Number(item.sales_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [historyBrandMix]
  );

  const historyPromoSummary = useMemo(() => {
    const promotion = historySpecialCards.find((card) => card.key === 'promotion');
    const incentive = historySpecialCards.find((card) => card.key === 'incentive');
    return { promotion, incentive };
  }, [historySpecialCards]);

  const brandMixChartData = useMemo(
    () =>
      brandMix.map((item) => ({
        brand: item.brand,
        sales_total: Number(item.sales_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [brandMix]
  );

  const sortedStores = useMemo(() => {
    const rows = [...stores];
    rows.sort((left, right) => {
      const leftValue = getStoreSortValue(left, storeSort.key);
      const rightValue = getStoreSortValue(right, storeSort.key);
      const result = leftValue - rightValue;
      return storeSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [stores, storeSort]);

  const sortedAgents = useMemo(() => {
    const rows = [...agents];
    rows.sort((left, right) => {
      const leftValue = getAgentSortValue(left, agentSort.key);
      const rightValue = getAgentSortValue(right, agentSort.key);
      const result = leftValue - rightValue;
      return agentSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [agents, agentSort]);

  const handleSortAgents = useCallback((key: AgentSortKey) => {
    setAgentSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'locatie' || key === 'agent' ? 'asc' : 'desc' }
    );
  }, []);

  const handleSortStores = useCallback((key: StoreSortKey) => {
    setStoreSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : {
            key,
            direction:
              key === 'locatie' || key === 'site_code'
                ? 'asc'
                : 'desc',
          }
    );
  }, []);

  const sortedRegionals = useMemo(() => {
    const rows = [...regionals];
    rows.sort((left, right) => {
      const leftValue = getRegionalSortValue(left, regionalSort.key);
      const rightValue = getRegionalSortValue(right, regionalSort.key);
      const result = leftValue - rightValue;
      return regionalSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [regionals, regionalSort]);

  const sortedAsms = useMemo(() => {
    const rows = [...asms];
    rows.sort((left, right) => {
      const leftValue = getAsmSortValue(left, asmSort.key);
      const rightValue = getAsmSortValue(right, asmSort.key);
      const result = leftValue - rightValue;
      return asmSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [asms, asmSort]);

  const sortedHistoryRegionals = useMemo(() => {
    const rows = [...historyRegionals];
    rows.sort((left, right) => {
      const leftValue = getRegionalSortValue(left, historyRegionalSort.key);
      const rightValue = getRegionalSortValue(right, historyRegionalSort.key);
      const result = leftValue - rightValue;
      return historyRegionalSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [historyRegionals, historyRegionalSort]);

  const sortedHistoryAsms = useMemo(() => {
    const rows = [...historyAsms];
    rows.sort((left, right) => {
      const leftValue = getAsmSortValue(left, historyAsmSort.key);
      const rightValue = getAsmSortValue(right, historyAsmSort.key);
      const result = leftValue - rightValue;
      return historyAsmSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [historyAsms, historyAsmSort]);

  const sortedHistoryStores = useMemo(() => {
    const rows = [...historyStores];
    rows.sort((left, right) => {
      const leftValue = getStoreSortValue(left, historyStoreSort.key);
      const rightValue = getStoreSortValue(right, historyStoreSort.key);
      const result = leftValue - rightValue;
      return historyStoreSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [historyStores, historyStoreSort]);

  const sortedHistoryAgents = useMemo(() => {
    const rows = [...historyAgents];
    rows.sort((left, right) => {
      const leftValue = getAgentSortValue(left, historyAgentSort.key);
      const rightValue = getAgentSortValue(right, historyAgentSort.key);
      const result = leftValue - rightValue;
      return historyAgentSort.direction === 'asc' ? result : -result;
    });
    return rows;
  }, [historyAgents, historyAgentSort]);

  const handleSortRegionals = useCallback((key: RegionalSortKey) => {
    setRegionalSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'regional' ? 'asc' : 'desc' }
    );
  }, []);

  const handleSortAsms = useCallback((key: AsmSortKey) => {
    setAsmSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'asm' || key === 'regional' ? 'asc' : 'desc' }
    );
  }, []);

  const handleSortHistoryRegionals = useCallback((key: RegionalSortKey) => {
    setHistoryRegionalSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'regional' ? 'asc' : 'desc' }
    );
  }, []);

  const handleSortHistoryAsms = useCallback((key: AsmSortKey) => {
    setHistoryAsmSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'asm' || key === 'regional' ? 'asc' : 'desc' }
    );
  }, []);

  const handleSortHistoryStores = useCallback((key: StoreSortKey) => {
    setHistoryStoreSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'locatie' || key === 'site_code' ? 'asc' : 'desc' }
    );
  }, []);

  const handleSortHistoryAgents = useCallback((key: AgentSortKey) => {
    setHistoryAgentSort((current) =>
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'locatie' || key === 'agent' ? 'asc' : 'desc' }
    );
  }, []);

  const filterScopeLabel = useMemo(() => describeFilterScope(filters), [filters]);

  const hasActivePromotion = specialCards.some(
    (c) => c.key === 'promotion' && c.status !== 'missing_config' && c.status !== 'inactive'
  );
  const regionalColumnsVisible = hasActivePromotion
    ? REGIONAL_COLUMNS
    : REGIONAL_COLUMNS.filter((c) => c.key !== 'promo_qty');
  const agentColumnsVisible = hasActivePromotion
    ? AGENT_COLUMNS
    : AGENT_COLUMNS.filter((c) => c.key !== 'promo_qty');

  return (
    <div className="space-y-3 p-3 pb-24 lg:pb-6 pt-2">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Sales Hub</h1>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Luna in curs este fixata pe {currentMonth}, iar istoricul se analizeaza separat.
        </p>
      </div>

      <div className="glass flex rounded-2xl p-1">
        <button
          onClick={() => setActiveSection('current')}
          className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
            activeSection === 'current'
              ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
              : 'text-slate-500'
          }`}
        >
          Luna in curs
        </button>
        <button
          onClick={() => setActiveSection('history')}
          className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
            activeSection === 'history'
              ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
              : 'text-slate-500'
          }`}
        >
          Istoric
        </button>
        <button
          onClick={() => setActiveSection('visits')}
          className={`flex-1 flex items-center justify-center gap-1 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
            activeSection === 'visits'
              ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
              : 'text-slate-500'
          }`}
        >
          <MapPin size={11} />
          Vizite
        </button>
      </div>

      {activeSection === 'visits' ? (
        <VisiteSubtab currentMonth={currentMonth} />
      ) : loading ? (
        <LoadingCard label="Se incarca luna in curs..." />
      ) : error || !summary ? (
        <ErrorCard
          message={error ?? 'Datele pentru luna in curs nu au putut fi incarcate.'}
          onRetry={fetchCurrentData}
        />
      ) : activeSection === 'current' ? (
        <>
          <div className="glass rounded-3xl p-4 space-y-4">

            {/* 1. Header compact */}
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="text-sm font-bold truncate">Overview — {currentMonth}</h3>
                <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">{currentStatusLabel}</p>
              </div>
              <span className="shrink-0 rounded-xl bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-500 dark:bg-slate-800">
                {summary.last_sale_date ?? '-'}
              </span>
            </div>

            {/* 2. Bloc financiar cu bara de progres */}
            <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
              {/* Cele trei valori */}
              <div className="mb-3 grid grid-cols-3 gap-2 text-center">
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Target</div>
                  <div className="mt-0.5 text-[13px] font-bold text-slate-600 dark:text-slate-300">
                    <CompactCurrency value={Number(summary.total_target)} />
                  </div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Realizat</div>
                  <div className="mt-0.5 text-[13px] font-bold text-slate-800 dark:text-slate-100">
                    <CompactCurrency value={Number(summary.total_sales)} />
                  </div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-indigo-400">Previziune</div>
                  <div className="mt-0.5 text-[13px] font-bold text-indigo-600 dark:text-indigo-400">
                    <CompactCurrency value={Number(summary.forecast_sales ?? summary.total_sales)} />
                  </div>
                </div>
              </div>

              {/* Bara duala actual + forecast */}
              <div className="relative h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                {/* Forecast (fundal) */}
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-indigo-200 dark:bg-indigo-700"
                  style={{ width: `${Math.min(Number(summary.forecast_target_progress_pct ?? 0), 100)}%` }}
                />
                {/* Actual (prim-plan) */}
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-indigo-600"
                  style={{ width: `${Math.min(Number(summary.target_progress_pct ?? 0), 100)}%` }}
                />
              </div>
              <div className="mt-1.5 flex justify-between text-[10px] font-semibold">
                <span className="text-indigo-600">
                  Actual {formatPercent(summary.target_progress_pct)}
                </span>
                <span className="text-slate-400">
                  Forecast {formatPercent(summary.forecast_target_progress_pct)}
                </span>
              </div>
            </div>

            {/* 3. KPI-uri cheie */}
            <div className="grid grid-cols-2 gap-2.5">
              <KpiPerformanceCard
                title="ProcBon2Acc"
                value={summary.proc_bon2acc}
                tone={getBon2AccTone(Number(summary.proc_bon2acc ?? 0))}
                chartData={receiptBucketChartData}
                dataKey="receipt_count"
                nameKey="bucket"
                formatValue={formatInt}
              />
              <KpiPerformanceCard
                title="PrcFocus/AccQtty"
                value={summary.prc_focus_acc_qty}
                tone={getFocusTone(Number(summary.prc_focus_acc_qty ?? 0))}
                chartData={focusSubcategoryChartData}
                dataKey="quantity_total"
                nameKey="category"
                formatValue={formatInt}
              />
            </div>

            {/* 4. Metrici operationale */}
            <div className="grid grid-cols-4 gap-2 lg:grid-cols-8">
              <Metric label="Bonuri" value={formatInt(summary.total_receipts)} className="p-2" />
              <Metric label="Accesorii" value={formatInt(summary.total_quantity)} className="p-2" />
              <Metric label="Magazine" value={formatInt(summary.total_stores)} className="p-2" />
              <Metric label="Agenti" value={formatInt(summary.total_agents)} className="p-2" />
              <Metric label="Zile lucrate" value={formatInt(summary.working_days)} className="p-2" />
              <Metric label="Med. zilnica" value={formatCurrency(summary.daily_average ?? 0)} className="p-2" />
              <Metric
                label="Val. medie bon"
                value={formatCurrency(
                  summary.total_receipts > 0
                    ? Number(summary.total_sales) / Number(summary.total_receipts)
                    : 0
                )}
                className="p-2"
              />
              <Metric
                label="Cartele"
                value={formatInt(summary.cartele_qty ?? 0)}
                className="p-2"
              />
            </div>

          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <div className="glass rounded-3xl p-4 overflow-hidden min-w-0">
              <div className="mb-4 flex items-center gap-2">
                <CalendarRange size={16} className="text-indigo-500" />
                <h3 className="text-sm font-bold">Comparatie perioade</h3>
              </div>
              {!periodComparison || !comparisonDeltas ? (
                <div className="text-xs text-slate-500">
                  Date indisponibile pentru comparatia de perioade.
                </div>
              ) : (
                <div className="space-y-3">
                  <PeriodTable
                    current={periodComparison.current}
                    previous={periodComparison.previous}
                    yoy={periodComparison.year_over_year}
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <DeltaCard
                      title="Vs luna trecuta"
                      salesDelta={comparisonDeltas.previousSales}
                      salesPct={comparisonDeltas.previousSalesPct}
                      receiptsDelta={comparisonDeltas.previousReceipts}
                      receiptsPct={comparisonDeltas.previousReceiptsPct}
                      quantityDelta={comparisonDeltas.previousQuantity}
                      quantityPct={comparisonDeltas.previousQuantityPct}
                    />
                    <DeltaCard
                      title="Vs anul trecut"
                      salesDelta={comparisonDeltas.yearSales}
                      salesPct={comparisonDeltas.yearSalesPct}
                      receiptsDelta={comparisonDeltas.yearReceipts}
                      receiptsPct={comparisonDeltas.yearReceiptsPct}
                      quantityDelta={comparisonDeltas.yearQuantity}
                      quantityPct={comparisonDeltas.yearQuantityPct}
                    />
                  </div>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={handleOpenFocus}
              className="glass rounded-3xl p-4 text-left transition hover:shadow-xl"
            >
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Sparkles size={16} className="text-indigo-500" />
                  <h3 className="text-sm font-bold">Promo & incentive</h3>
                </div>
                <div className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-600">
                  Deschide Focus
                  <ArrowRight size={14} />
                </div>
              </div>
              <div className="grid gap-3">
                {promoSummary.promotion &&
                  promoSummary.promotion.status !== 'missing_config' && (
                    <CampaignMiniCard
                      label="Promo"
                      title={promoSummary.promotion.title}
                      status={promoSummary.promotion.status_label ?? 'Fara date'}
                      metrics={[
                        { label: 'Cantitate', value: formatInt(promoIncentive.promo_qty) },
                        { label: 'Impact', value: formatCurrency(promoIncentive.promo_impact) },
                      ]}
                      footer={`Vanzari promo: ${formatCurrency(promoIncentive.promo_sales)}`}
                    />
                  )}
                <CampaignMiniCard
                  label="Incentive"
                  title={promoSummary.incentive?.title ?? 'Incentive neconfigurat'}
                  status={promoSummary.incentive?.status_label ?? 'Fara date'}
                  metrics={[
                    { label: 'Cantitate', value: formatInt(promoIncentive.incentive_qty) },
                    { label: 'Valoare', value: formatCurrency(promoIncentive.incentive_value) },
                    ...(promoSummary.incentive ? [
                      { label: 'Magazine calificate', value: formatInt(promoIncentive.incentive_qualified_stores) },
                      { label: 'Agenți calificați', value: formatInt(promoIncentive.incentive_qualified_agents) },
                    ] : []),
                  ]}
                  footer={promoSummary.incentive?.coverage_note ?? 'Bonus per unitate eligibila'}
                />
              </div>
            </button>
          </div>

          <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr]">
            <div className="glass rounded-3xl p-4">
              <div className="mb-3 flex items-center gap-2">
                <CalendarRange size={16} className="text-indigo-500" />
                <h3 className="text-sm font-bold">Evolutie zilnica pentru {currentMonth}</h3>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                  <ComposedChart data={dailyChartData}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                    <XAxis dataKey="day" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis yAxisId="qty" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      formatter={(value: number, name: string) =>
                        name === 'Vanzari' ? formatCurrency(value) : formatInt(value)
                      }
                    />
                    <Legend />
                    <Bar yAxisId="sales" dataKey="sales" name="Vanzari" fill="#4f46e5" radius={[8, 8, 0, 0]} />
                    <Line yAxisId="qty" type="monotone" dataKey="qty" name="Cantitate" stroke="#f59e0b" strokeWidth={2} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="glass rounded-3xl p-4">
              <div className="mb-3 flex items-center gap-2">
                <PieChartIcon size={16} className="text-indigo-500" />
                <h3 className="text-sm font-bold">Top categorii si branduri</h3>
              </div>
              <div className="space-y-4">
                <CompactPieSection
                  title="Top categorii"
                  emptyLabel="Nu exista categorii disponibile pentru filtrarea curenta."
                  pieData={categoryMixChartData}
                  dataKey="sales_total"
                  nameKey="category"
                  valueFormatter={formatCurrency}
                  centerValue={formatCompactDonutValue(sumChartValues(categoryMixChartData, 'sales_total'))}
                />
                <CompactPieSection
                  title="Branduri compatibile"
                  emptyLabel="Nu exista date pentru brandurile urmarite."
                  pieData={brandMixChartData}
                  dataKey="sales_total"
                  nameKey="brand"
                  valueFormatter={formatCurrency}
                  centerValue={formatCompactDonutValue(sumChartValues(brandMixChartData, 'sales_total'))}
                />
              </div>
            </div>
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <Users size={16} className="text-indigo-500" />
                  <h3 className="text-sm font-bold">RM — Regional Manager</h3>
                </div>
                <p className="text-[11px] text-slate-500">
                  Filtrare: {filterScopeLabel} · Sortare: {regionalColumnsVisible.find((column) => column.key === regionalSort.key)?.label} ({regionalSort.direction}) · {regionals.length} regionale
                </p>
              </div>
            </div>
            <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
              <table className={REGIONAL_TABLE_CLASS}>
                <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                  <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {regionalColumnsVisible.map((column, i) => (
                      <React.Fragment key={column.key}>
                        <SortableHeader
                          label={column.label}
                          active={regionalSort.key === column.key}
                          direction={regionalSort.direction}
                          onClick={() => handleSortRegionals(column.key)}
                          className={`${COMPACT_TH_CLASS} ${i === 0 ? 'w-28' : ''}`}
                        />
                      </React.Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedRegionals.map((regional, index) => (
                    <tr
                      key={regional.regional}
                      className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                    >
                      <td className={`max-w-28 truncate font-semibold ${COMPACT_TD_CLASS}`}>{regional.regional}</td>
                      <td className={COMPACT_TD_CLASS}>{formatCurrency(regional.target)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatCurrency(regional.total_vanzari)}</td>
                      <td className={`${COMPACT_TD_CLASS} font-bold text-indigo-600`}>{formatPercent(regional.proc_realizare_target)}</td>
                      <td className={`${COMPACT_TD_CLASS} font-bold text-slate-700 dark:text-slate-200`}>{formatPercent(regional.forecast_target_pct)}</td>
                      {hasActivePromotion && <td className={COMPACT_TD_CLASS}>{formatInt(regional.promo_qty)}</td>}
                      <td className={COMPACT_TD_CLASS}>{formatInt(regional.incentive_qty)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatInt(regional.qty_total)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatInt(regional.nr_bonuri)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatCurrency(regional.medie_zilnica ?? 0)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatPercent(regional.proc_bon2acc)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatPercent(regional.prc_focus_acc_qty)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <Building2 size={16} className="text-indigo-500" />
                  <h3 className="text-sm font-bold">Magazine</h3>
                </div>
                <p className="text-[11px] text-slate-500">
                  Filtrare: {filterScopeLabel} · Sortare: {STORE_COLUMNS.find((column) => column.key === storeSort.key)?.label} ({storeSort.direction}) · {stores.length} magazine
                </p>
              </div>
            </div>
            <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
              <table className={STORE_TABLE_CLASS}>
                <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                  <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {STORE_COLUMNS.map((column, i) => (
                      <React.Fragment key={column.key}>
                        <SortableHeader
                          label={column.label}
                          active={storeSort.key === column.key}
                          direction={storeSort.direction}
                          onClick={() => handleSortStores(column.key)}
                          className={`${COMPACT_TH_CLASS} ${i === 0 ? 'w-36' : ''}`}
                        />
                      </React.Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedStores.map((store, index) => (
                    <tr
                      key={store.site_code}
                      className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                    >
                      <td className={`max-w-36 truncate font-semibold ${COMPACT_TD_CLASS}`}>{store.locatie}</td>
                      <td className={`${COMPACT_TD_CLASS} text-center font-bold`}>
                        {store.firma?.toLowerCase().includes('mobiup')
                          ? <span className="text-red-500">MU</span>
                          : <span className="text-blue-500">MC</span>
                        }
                      </td>
                      <td className={COMPACT_TD_CLASS}>{formatCurrency(store.target)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatCurrency(store.total_vanzari)}</td>
                      <td className={`${COMPACT_TD_CLASS} font-bold text-indigo-600`}>{formatPercent(store.proc_realizare_target)}</td>
                      <td className={`${COMPACT_TD_CLASS} font-bold text-slate-700 dark:text-slate-200`}>{formatPercent(store.forecast_target_pct)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatInt(store.incentive_qty ?? 0)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatInt(store.qty_total ?? 0)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatInt(store.nr_bonuri)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatInt(store.nr_agenti)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatInt(store.zile_active)}</td>
                      <td className={COMPACT_TD_CLASS}>{formatCurrency(getStoreDailyAverage(store))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold">Agenti - Toti agentii</h3>
                  <p className="text-[11px] text-slate-500">
                    Filtrare: {filterScopeLabel} · Sortare: {agentColumnsVisible.find((column) => column.key === agentSort.key)?.label} ({agentSort.direction}) · {agents.length} agenti
                  </p>
                </div>
              </div>
            <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
              <table className="min-w-370 w-full border-collapse text-xs">
                <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                  <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {agentColumnsVisible.map((column, i) => (
                      <React.Fragment key={column.key}>
                        <SortableHeader
                          label={column.label}
                          active={agentSort.key === column.key}
                          direction={agentSort.direction}
                          onClick={() => handleSortAgents(column.key)}
                          className={i === 0 ? 'w-24' : ''}
                        />
                      </React.Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedAgents.map((agentRow, index) => (
                    <tr
                      key={`${agentRow.agent}-${agentRow.site_code}`}
                      className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                    >
                      <td className="max-w-0 w-24 truncate px-3 py-2 font-bold">{agentRow.agent}</td>
                      <td className="max-w-[7rem] truncate px-3 py-2 text-slate-500">{agentRow.locatie}</td>
                      <td className="px-3 py-2">{formatCurrency(agentRow.target ?? 0)}</td>
                      <td className="px-3 py-2 font-bold text-indigo-600">{formatCurrency(agentRow.total_vanzari)}</td>
                      <td className="px-3 py-2">{formatPercent(agentRow.proc_realizare_target)}</td>
                      {hasActivePromotion && <td className="px-3 py-2">{formatInt(agentRow.promo_qty ?? 0)}</td>}
                      <td className="px-3 py-2">{formatInt(agentRow.incentive_qty ?? 0)}</td>
                      <td className="px-3 py-2">{formatInt(agentRow.acc_qty_realizat)}</td>
                      <td className="px-3 py-2">{formatInt(agentRow.nr_bonuri)}</td>
                      <td className="px-3 py-2">{formatInt(agentRow.zile_lucrate)}</td>
                      <td className="px-3 py-2">{formatCurrency(agentRow.medie_zilnica ?? 0)}</td>
                      <td className="px-3 py-2">{formatPercent(agentRow.proc_bon2acc)}</td>
                      <td className="px-3 py-2">{formatPercent(agentRow.prc_focus_acc_qty)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <>
          {historyLoading ? (
            <LoadingCard label="Se incarca istoricul..." />
          ) : historyError ? (
            <ErrorCard message={historyError} onRetry={loadHistory} />
          ) : !selectedHistoryPoint ? (
            <ErrorCard message="Nu exista valori istorice pentru luna selectata." onRetry={loadHistory} />
          ) : (
            <>
              {/* Card 1 — Evolutie lunara (independent de historyMonth) */}
              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-bold">Evolutie lunara</h3>
                    <p className="text-[11px] text-slate-500">
                      {historyYearFilter === null
                        ? `Ultimele 12 luni finalizate${summary && !summary.is_month_final ? ' + previziune luna in curs' : ''}`
                        : `Toate lunile disponibile — ${historyYearFilter}`}
                    </p>
                  </div>
                  <select
                    value={historyYearFilter ?? ''}
                    onChange={(e) => setHistoryYearFilter(e.target.value === '' ? null : parseInt(e.target.value))}
                    className="rounded-xl border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                  >
                    <option value="">Standard</option>
                    {availableYears.map((yr) => (
                      <option key={yr} value={yr}>{yr}</option>
                    ))}
                  </select>
                </div>
                {(historyYearFilter === null ? currentHistoryLoading : yearHistoryLoading) ? (
                  <div className="flex h-64 items-center justify-center text-xs text-slate-400">Se incarca...</div>
                ) : historyYearFilter === null ? (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                      <ComposedChart data={currentHistoryChartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                        <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="progress" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip formatter={(value: number, name: string) => (name === '% target' ? `${value.toFixed(2)}%` : formatCurrency(value))} />
                        <Legend />
                        <Bar yAxisId="sales" dataKey="sales" name="Vanzari" radius={[8, 8, 0, 0]}>
                          {currentHistoryChartData.map((entry, index) => (
                            <Cell key={index} fill={entry.isForecast ? '#a78bfa' : '#4f46e5'} />
                          ))}
                        </Bar>
                        <Line yAxisId="sales" type="monotone" dataKey="target" name="Target" stroke="#10b981" strokeWidth={2} dot={false} />
                        <Line yAxisId="progress" type="monotone" dataKey="progress" name="% target" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                ) : yearHistoryChartData.length === 0 ? (
                  <div className="flex h-64 items-center justify-center text-xs text-slate-400">
                    Nu exista date pentru {historyYearFilter} cu filtrele curente.
                  </div>
                ) : (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                      <ComposedChart data={yearHistoryChartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                        <XAxis dataKey="label" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="progress" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip formatter={(value: number, name: string) => (name === '% target' ? `${value.toFixed(2)}%` : formatCurrency(value))} />
                        <Legend />
                        <Bar yAxisId="sales" dataKey="sales" name="Vanzari" radius={[8, 8, 0, 0]}>
                          {yearHistoryChartData.map((entry, index) => (
                            <Cell key={index} fill={entry.isAggregate ? '#818cf8' : '#4f46e5'} />
                          ))}
                        </Bar>
                        {yearHistoryChartData.some((p) => p.target > 0) && (
                          <Line yAxisId="sales" type="monotone" dataKey="target" name="Target" stroke="#10b981" strokeWidth={2} dot={false} />
                        )}
                        {yearHistoryChartData.some((p) => p.progress > 0) && (
                          <Line yAxisId="progress" type="monotone" dataKey="progress" name="% target" stroke="#f59e0b" strokeWidth={2} dot={false} />
                        )}
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>

              {/* Card 2 — Trend KPI (inlocuieste area chart duplicat) */}
              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <TrendingUp size={16} className="text-indigo-500" />
                    <h3 className="text-sm font-bold">Trend KPI</h3>
                  </div>
                  <div className="flex gap-1">
                    {([
                      { key: 'proc_bon2acc', label: 'Bon2Acc' },
                      { key: 'prc_focus_acc_qty', label: 'Focus' },
                      { key: 'total_receipts', label: 'Bonuri' },
                    ] as const).map(({ key, label }) => (
                      <button
                        key={key}
                        onClick={() => setKpiMetric(key)}
                        className={`rounded-full px-2.5 py-1 text-[10px] font-bold transition-colors ${
                          kpiMetric === key
                            ? 'bg-indigo-600 text-white'
                            : 'bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                {currentHistoryLoading ? (
                  <div className="flex h-48 items-center justify-center text-xs text-slate-400">Se incarca...</div>
                ) : (
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                      <AreaChart data={kpiChartData}>
                        <defs>
                          <linearGradient id="kpiTrendArea" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.35} />
                            <stop offset="95%" stopColor="#4f46e5" stopOpacity={0.03} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                        <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip
                          formatter={(value: number) =>
                            kpiMetric === 'total_receipts' ? formatInt(value) : `${value.toFixed(1)}%`
                          }
                        />
                        <Area type="monotone" dataKey="value" name={kpiMetric === 'proc_bon2acc' ? 'ProcBon2Acc' : kpiMetric === 'prc_focus_acc_qty' ? 'PrcFocus/AccQtty' : 'Total bonuri'} stroke="#4f46e5" fill="url(#kpiTrendArea)" strokeWidth={2} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>

              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold">Luna analizata</h3>
                    <p className="text-[11px] text-slate-500">Selector dedicat doar pentru sectiunea de istoric</p>
                  </div>
                  <select
                    value={historyMonth}
                    onChange={(event) => setHistoryMonth(event.target.value)}
                    className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold outline-none dark:border-slate-700 dark:bg-slate-800"
                  >
                    {months.map((month) => (
                      <option key={month} value={month}>
                        {month}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Overview card — mirrors the first card from Luna in curs */}
              <div className="glass rounded-3xl p-4 space-y-4">
                {/* 1. Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold truncate">Overview — {historyMonth}</h3>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">{historyStatusLabel}</p>
                  </div>
                  <span className="shrink-0 rounded-xl bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-500 dark:bg-slate-800">
                    {historySummary?.last_sale_date ?? '-'}
                  </span>
                </div>

                {/* 2. Financial block with progress bar */}
                <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
                  <div className="mb-3 grid grid-cols-3 gap-2 text-center">
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Target</div>
                      <div className="mt-0.5 text-[13px] font-bold text-slate-600 dark:text-slate-300">
                        <CompactCurrency value={Number(historySummary?.total_target ?? selectedHistoryPoint.total_target)} />
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Realizat</div>
                      <div className="mt-0.5 text-[13px] font-bold text-slate-800 dark:text-slate-100">
                        <CompactCurrency value={Number(historySummary?.total_sales ?? selectedHistoryPoint.total_sales)} />
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-indigo-400">
                        {historySummary?.is_month_final === false ? 'Previziune' : 'Realizat %'}
                      </div>
                      <div className="mt-0.5 text-[13px] font-bold text-indigo-600 dark:text-indigo-400">
                        {historySummary?.is_month_final === false
                          ? <CompactCurrency value={Number(historySummary?.forecast_sales ?? historySummary?.total_sales ?? selectedHistoryPoint.total_sales)} />
                          : formatPercent(historySummary?.target_progress_pct ?? selectedHistoryPoint.target_progress_pct)
                        }
                      </div>
                    </div>
                  </div>

                  {/* Dual progress bar */}
                  <div className="relative h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                    {historySummary?.is_month_final === false && (
                      <div
                        className="absolute inset-y-0 left-0 rounded-full bg-indigo-200 dark:bg-indigo-700"
                        style={{ width: `${Math.min(Number(historySummary?.forecast_target_progress_pct ?? 0), 100)}%` }}
                      />
                    )}
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-indigo-600"
                      style={{ width: `${Math.min(Number(historySummary?.target_progress_pct ?? selectedHistoryPoint.target_progress_pct ?? 0), 100)}%` }}
                    />
                  </div>
                  <div className="mt-1.5 flex justify-between text-[10px] font-semibold">
                    <span className="text-indigo-600">
                      Actual {formatPercent(historySummary?.target_progress_pct ?? selectedHistoryPoint.target_progress_pct)}
                    </span>
                    {historySummary?.is_month_final === false && (
                      <span className="text-slate-400">
                        Forecast {formatPercent(historySummary?.forecast_target_progress_pct)}
                      </span>
                    )}
                  </div>
                </div>

                {/* 3. KPI performance cards */}
                <div className="grid grid-cols-2 gap-2.5">
                  <KpiPerformanceCard
                    title="ProcBon2Acc"
                    value={historySummary?.proc_bon2acc ?? selectedHistoryPoint.proc_bon2acc}
                    tone={getBon2AccTone(Number(historySummary?.proc_bon2acc ?? selectedHistoryPoint.proc_bon2acc ?? 0))}
                    chartData={historyReceiptBucketChartData}
                    dataKey="receipt_count"
                    nameKey="bucket"
                    formatValue={formatInt}
                  />
                  <KpiPerformanceCard
                    title="PrcFocus/AccQtty"
                    value={historySummary?.prc_focus_acc_qty ?? selectedHistoryPoint.prc_focus_acc_qty}
                    tone={getFocusTone(Number(historySummary?.prc_focus_acc_qty ?? selectedHistoryPoint.prc_focus_acc_qty ?? 0))}
                    chartData={historyFocusSubcategoryChartData}
                    dataKey="quantity_total"
                    nameKey="category"
                    formatValue={formatInt}
                  />
                </div>

                {/* 4. Operational metrics */}
                <div className="grid grid-cols-4 gap-2 lg:grid-cols-8">
                  <Metric label="Bonuri" value={formatInt(historySummary?.total_receipts ?? selectedHistoryPoint.total_receipts)} className="p-2" />
                  <Metric label="Accesorii" value={formatInt(historySummary?.total_quantity ?? selectedHistoryPoint.total_quantity)} className="p-2" />
                  <Metric label="Magazine" value={formatInt(historySummary?.total_stores ?? selectedHistoryPoint.total_stores)} className="p-2" />
                  <Metric label="Agenti" value={formatInt(historySummary?.total_agents ?? selectedHistoryPoint.total_agents)} className="p-2" />
                  <Metric label="Zile lucrate" value={formatInt(historySummary?.working_days ?? selectedHistoryPoint.working_days)} className="p-2" />
                  <Metric label="Med. zilnica" value={formatCurrency(historySummary?.daily_average ?? selectedHistoryPoint.daily_average ?? 0)} className="p-2" />
                  <Metric
                    label="Val. medie bon"
                    value={formatCurrency(
                      (historySummary?.total_receipts ?? selectedHistoryPoint.total_receipts) > 0
                        ? Number(historySummary?.total_sales ?? selectedHistoryPoint.total_sales) / Number(historySummary?.total_receipts ?? selectedHistoryPoint.total_receipts)
                        : 0
                    )}
                    className="p-2"
                  />
                  <Metric
                    label="Cartele"
                    value={formatInt(historySummary?.cartele_qty ?? 0)}
                    className="p-2"
                  />
                </div>
              </div>

              {/* Promo & Incentive — only rendered when at least one card is active */}
              {(() => {
                const showPromo = historyPromoSummary.promotion &&
                  !['missing_config', 'inactive'].includes(historyPromoSummary.promotion.status);
                const showIncentive = historyPromoSummary.incentive &&
                  !['missing_config', 'inactive'].includes(historyPromoSummary.incentive.status);
                if (!showPromo && !showIncentive) return null;
                return (
                  <div className="glass rounded-3xl p-4">
                    <div className="mb-4 flex items-center gap-2">
                      <Sparkles size={16} className="text-indigo-500" />
                      <h3 className="text-sm font-bold">Promo & incentive</h3>
                    </div>
                    <div className="grid gap-3">
                      {showPromo && (
                        <CampaignMiniCard
                          label="Promo"
                          title={historyPromoSummary.promotion!.title}
                          status={historyPromoSummary.promotion!.status_label ?? 'Fara date'}
                          metrics={[
                            { label: 'Cantitate', value: formatInt(historyPromoIncentive.promo_qty) },
                            { label: 'Impact', value: formatCurrency(historyPromoIncentive.promo_impact) },
                          ]}
                          footer={`Vanzari promo: ${formatCurrency(historyPromoIncentive.promo_sales)}`}
                        />
                      )}
                      {showIncentive && (
                        <CampaignMiniCard
                          label="Incentive"
                          title={historyPromoSummary.incentive!.title}
                          status={historyPromoSummary.incentive!.status_label ?? 'Fara date'}
                          metrics={[
                            { label: 'Cantitate', value: formatInt(historyPromoIncentive.incentive_qty) },
                            { label: 'Valoare', value: formatCurrency(historyPromoIncentive.incentive_value) },
                            ...(historyPromoSummary.incentive ? [
                              { label: 'Magazine calificate', value: formatInt(historyPromoIncentive.incentive_qualified_stores) },
                              { label: 'Agenți calificați', value: formatInt(historyPromoIncentive.incentive_qualified_agents) },
                            ] : []),
                          ]}
                          footer={historyPromoSummary.incentive!.coverage_note ?? 'Bonus per unitate eligibila'}
                        />
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* Evolutie zilnica + Top categorii si branduri */}
              <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr]">
                <div className="glass rounded-3xl p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <CalendarRange size={16} className="text-indigo-500" />
                    <h3 className="text-sm font-bold">Evolutie zilnica pentru {historyMonth}</h3>
                  </div>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                      <ComposedChart data={historyDailyChartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                        <XAxis dataKey="day" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="qty" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip
                          formatter={(value: number, name: string) =>
                            name === 'Vanzari' ? formatCurrency(value) : formatInt(value)
                          }
                        />
                        <Legend />
                        <Bar yAxisId="sales" dataKey="sales" name="Vanzari" fill="#4f46e5" radius={[8, 8, 0, 0]} />
                        <Line yAxisId="qty" type="monotone" dataKey="qty" name="Cantitate" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="glass rounded-3xl p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <PieChartIcon size={16} className="text-indigo-500" />
                    <h3 className="text-sm font-bold">Top categorii si branduri</h3>
                  </div>
                  <div className="space-y-4">
                    <CompactPieSection
                      title="Top categorii"
                      emptyLabel="Nu exista categorii disponibile pentru filtrarea curenta."
                      pieData={historyCategoryMixChartData}
                      dataKey="sales_total"
                      nameKey="category"
                      valueFormatter={formatCurrency}
                      centerValue={formatCompactDonutValue(sumChartValues(historyCategoryMixChartData, 'sales_total'))}
                    />
                    <CompactPieSection
                      title="Branduri compatibile"
                      emptyLabel="Nu exista date pentru brandurile urmarite."
                      pieData={historyBrandMixChartData}
                      dataKey="sales_total"
                      nameKey="brand"
                      valueFormatter={formatCurrency}
                      centerValue={formatCompactDonutValue(sumChartValues(historyBrandMixChartData, 'sales_total'))}
                    />
                  </div>
                </div>
              </div>

              {/* Breakdown tables — RM / Magazine / Agenti */}
              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <MapPin size={16} className="text-indigo-500" />
                      <h3 className="text-sm font-bold">RM</h3>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Sortare: {HIST_REGIONAL_COLUMNS.find((c) => c.key === historyRegionalSort.key)?.label} ({historyRegionalSort.direction}) · {historyRegionals.length} regionali
                    </p>
                  </div>
                </div>
                <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
                  <table className="min-w-330 w-full border-collapse text-xs">
                    <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                      <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                        {HIST_REGIONAL_COLUMNS.map((column, i) => (
                          <React.Fragment key={column.key}>
                            <SortableHeader
                              label={column.label}
                              active={historyRegionalSort.key === column.key}
                              direction={historyRegionalSort.direction}
                              onClick={() => handleSortHistoryRegionals(column.key)}
                              className={i === 0 ? 'w-28' : ''}
                            />
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedHistoryRegionals.map((row, index) => (
                        <tr
                          key={row.regional}
                          className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                        >
                          <td className="max-w-0 w-28 truncate px-3 py-2 font-semibold">{row.regional}</td>
                          <td className="px-3 py-2">{formatCurrency(row.target)}</td>
                          <td className="px-3 py-2">{formatCurrency(row.total_vanzari)}</td>
                          <td className="px-3 py-2 font-bold text-indigo-600">{formatPercent(row.proc_realizare_target)}</td>
                          <td className="px-3 py-2">{formatInt(row.incentive_qty)}</td>
                          <td className="px-3 py-2">{formatInt(row.qty_total)}</td>
                          <td className="px-3 py-2">{formatInt(row.nr_bonuri)}</td>
                          <td className="px-3 py-2">{formatCurrency(row.medie_zilnica ?? 0)}</td>
                          <td className="px-3 py-2">{formatPercent(row.proc_bon2acc)}</td>
                          <td className="px-3 py-2">{formatPercent(row.prc_focus_acc_qty)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <Building2 size={16} className="text-indigo-500" />
                      <h3 className="text-sm font-bold">Magazine</h3>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Sortare: {HIST_STORE_COLUMNS.find((c) => c.key === historyStoreSort.key)?.label} ({historyStoreSort.direction}) · {historyStores.length} magazine
                    </p>
                  </div>
                </div>
                <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
                  <table className="min-w-330 w-full border-collapse text-xs">
                    <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                      <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                        {HIST_STORE_COLUMNS.map((column, i) => (
                          <React.Fragment key={column.key}>
                            <SortableHeader
                              label={column.label}
                              active={historyStoreSort.key === column.key}
                              direction={historyStoreSort.direction}
                              onClick={() => handleSortHistoryStores(column.key)}
                              className={i === 0 ? 'w-36' : ''}
                            />
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedHistoryStores.map((store, index) => (
                        <tr
                          key={store.site_code}
                          className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                        >
                          <td className="max-w-0 w-36 truncate px-3 py-2 font-semibold">{store.locatie}</td>
                          <td className="px-3 py-2 text-center font-bold">
                            {store.firma?.toLowerCase().includes('mobiup')
                              ? <span className="text-red-500">MU</span>
                              : <span className="text-blue-500">MC</span>
                            }
                          </td>
                          <td className="px-3 py-2">{formatCurrency(store.target)}</td>
                          <td className="px-3 py-2">{formatCurrency(store.total_vanzari)}</td>
                          <td className="px-3 py-2 font-bold text-indigo-600">{formatPercent(store.proc_realizare_target)}</td>
                          <td className="px-3 py-2">{formatInt(store.incentive_qty ?? 0)}</td>
                          <td className="px-3 py-2">{formatInt(store.qty_total ?? 0)}</td>
                          <td className="px-3 py-2">{formatInt(store.nr_bonuri)}</td>
                          <td className="px-3 py-2">{formatInt(store.nr_agenti)}</td>
                          <td className="px-3 py-2">{formatInt(store.zile_active)}</td>
                          <td className="px-3 py-2">{formatCurrency(getStoreDailyAverage(store))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold">Agenti</h3>
                    <p className="text-[11px] text-slate-500">
                      Sortare: {HIST_AGENT_COLUMNS.find((c) => c.key === historyAgentSort.key)?.label} ({historyAgentSort.direction}) · {historyAgents.length} agenti
                    </p>
                  </div>
                </div>
                <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
                  <table className="min-w-370 w-full border-collapse text-xs">
                    <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                      <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                        {HIST_AGENT_COLUMNS.map((column, i) => (
                          <React.Fragment key={column.key}>
                            <SortableHeader
                              label={column.label}
                              active={historyAgentSort.key === column.key}
                              direction={historyAgentSort.direction}
                              onClick={() => handleSortHistoryAgents(column.key)}
                              className={i === 0 ? 'w-24' : ''}
                            />
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedHistoryAgents.map((agentRow, index) => (
                        <tr
                          key={`${agentRow.agent}-${agentRow.site_code}`}
                          className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                        >
                          <td className="max-w-0 w-24 truncate px-3 py-2 font-bold">{agentRow.agent}</td>
                          <td className="max-w-[7rem] truncate px-3 py-2 text-slate-500">{agentRow.locatie}</td>
                          <td className="px-3 py-2">{formatCurrency(agentRow.target ?? 0)}</td>
                          <td className="px-3 py-2 font-bold text-indigo-600">{formatCurrency(agentRow.total_vanzari)}</td>
                          <td className="px-3 py-2">{formatPercent(agentRow.proc_realizare_target)}</td>
                          <td className="px-3 py-2">{formatInt(agentRow.incentive_qty ?? 0)}</td>
                          <td className="px-3 py-2">{formatInt(agentRow.acc_qty_realizat)}</td>
                          <td className="px-3 py-2">{formatInt(agentRow.nr_bonuri)}</td>
                          <td className="px-3 py-2">{formatInt(agentRow.zile_lucrate)}</td>
                          <td className="px-3 py-2">{formatCurrency(agentRow.medie_zilnica ?? 0)}</td>
                          <td className="px-3 py-2">{formatPercent(agentRow.proc_bon2acc)}</td>
                          <td className="px-3 py-2">{formatPercent(agentRow.prc_focus_acc_qty)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
