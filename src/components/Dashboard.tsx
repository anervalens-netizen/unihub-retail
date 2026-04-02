import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  ArrowUpDown,
  Building2,
  CalendarRange,
  ChevronDown,
  ChevronUp,
  MapPin,
  PieChart as PieChartIcon,
  RefreshCw,
  Sparkles,
  Target,
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
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getDashboardAll, getDashboardHistory } from '../api/dashboard';
import type {
  AgentStat,
  AsmStat,
  AuthUser,
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
} from '../api/types';
import { buildScopedMonthQuery } from '../lib/filterQueries';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from '../lib/filterValues';
import { formatCurrency, formatInt, formatPercent } from '../lib/formatters';
import { getCachedView, setCachedView } from '../lib/viewCache';
import type { AppFilters } from './MainLayout';
import { VisiteSubtab } from './VisiteSubtab';

interface DashboardProps {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
  user: AuthUser | null;
}

type DashboardSection = 'current' | 'history' | 'visits';
type SortDirection = 'asc' | 'desc';
type StoreSortKey =
  | 'locatie'
  | 'site_code'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
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

type PerformanceTone = {
  label: string;
  cardClass: string;
  badgeClass: string;
};

const PIE_COLORS = ['#4f46e5', '#0f766e', '#d97706', '#dc2626', '#7c3aed', '#475569'];
const KPI_PIE_COLORS = ['#4f46e5', '#22c55e', '#f59e0b', '#ef4444', '#64748b'];

const DEFAULT_PROMO_INCENTIVE: PromoIncentiveSummary = {
  promo_qty: 0,
  promo_sales: 0,
  promo_impact: 0,
  incentive_qty: 0,
  incentive_value: 0,
};
const DASHBOARD_CACHE_TTL_MS = 3 * 60 * 1000;
const TABLE_MAX_HEIGHT_CLASS = 'max-h-[30rem]';

const STORE_COLUMNS: Array<{ key: StoreSortKey; label: string }> = [
  { key: 'locatie', label: 'Magazin' },
  { key: 'site_code', label: 'Firma' },
  { key: 'target', label: 'Target' },
  { key: 'total_vanzari', label: 'Vanzari' },
  { key: 'proc_realizare_target', label: 'Procent' },
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

export function Dashboard({ currentMonth, months, filters, user }: DashboardProps) {
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
        prefetchHistory(historyMonth);
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
        prefetchHistory(historyMonth);
      })
      .catch((err: Error) => {
        if (!isMountedRef.current) return;
        setError(err.message || 'Eroare la incarcarea lunii in curs');
      })
      .finally(() => {
        if (isMountedRef.current) setLoading(false);
      });
  }, [buildQuery, currentCacheKey, currentMonth, historyMonth, prefetchHistory]);

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
    setHistoryError(null);
    if (activeSection === 'history') {
      loadHistory();
    }
  }, [activeSection, historyMonth, loadHistory]);

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

  const selectedHistoryPoint = useMemo(
    () => history.find((item) => item.month === historyMonth) ?? history[history.length - 1] ?? null,
    [history, historyMonth]
  );

  const bestHistoryMonth = useMemo(() => {
    if (history.length === 0) return null;
    return [...history].sort((a, b) => Number(b.total_sales) - Number(a.total_sales))[0];
  }, [history]);

  const comparisonDeltas = useMemo(() => {
    if (!periodComparison) return null;
    const current = Number(periodComparison.current.total_sales);
    const previous = Number(periodComparison.previous.total_sales);
    const yearOverYear = Number(periodComparison.year_over_year.total_sales);
    const currentAvg = Number(periodComparison.current.daily_average ?? 0);
    const previousAvg = Number(periodComparison.previous.daily_average ?? 0);
    const yearOverYearAvg = Number(periodComparison.year_over_year.daily_average ?? 0);

    return {
      previousSales: current - previous,
      previousDaily: currentAvg - previousAvg,
      yearSales: current - yearOverYear,
      yearDaily: currentAvg - yearOverYearAvg,
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
        detail: { tab: 'focus', section: 'campaigns' },
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

  const CATEGORY_SHORT: Record<string, string> = {
    'Casti intraauriculare': 'Casti intraaur.',
    'Baterie Externa': 'Baterie Ext.',
    'Suport telescopic': 'Suport telesk.',
    'Suport auto': 'Suport auto',
  };

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

  const historyComparisonDeltas = useMemo(() => {
    if (!historyPeriodComparison) return null;
    const current = Number(historyPeriodComparison.current.total_sales);
    const previous = Number(historyPeriodComparison.previous.total_sales);
    const yearOverYear = Number(historyPeriodComparison.year_over_year.total_sales);
    const currentAvg = Number(historyPeriodComparison.current.daily_average ?? 0);
    const previousAvg = Number(historyPeriodComparison.previous.daily_average ?? 0);
    const yearOverYearAvg = Number(historyPeriodComparison.year_over_year.daily_average ?? 0);
    return {
      previousSales: current - previous,
      previousDaily: currentAvg - previousAvg,
      yearSales: current - yearOverYear,
      yearDaily: currentAvg - yearOverYearAvg,
    };
  }, [historyPeriodComparison]);

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

  const filterScopeLabel = useMemo(() => describeFilterScope(filters), [filters]);

  const hasActivePromotion = specialCards.some(
    (c) => c.key === 'promotion' && c.status !== 'missing_config' && c.status !== 'inactive'
  );
  const regionalColumnsVisible = hasActivePromotion
    ? REGIONAL_COLUMNS
    : REGIONAL_COLUMNS.filter((c) => c.key !== 'promo_qty');
  const asmColumnsVisible = hasActivePromotion
    ? ASM_COLUMNS
    : ASM_COLUMNS.filter((c) => c.key !== 'promo_qty');
  const agentColumnsVisible = hasActivePromotion
    ? AGENT_COLUMNS
    : AGENT_COLUMNS.filter((c) => c.key !== 'promo_qty');

  return (
    <div className="space-y-3 p-3 pb-24 pt-2">
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
        {user?.role === 'management' || user?.role === 'admin' ? (
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
        ) : null}
      </div>

      {activeSection === 'visits' ? (
        <VisiteSubtab currentMonth={currentMonth} filters={filters} />
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
            <div className="grid grid-cols-4 gap-2">
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

          <div className="grid gap-3">
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
                      dailyDelta={comparisonDeltas.previousDaily}
                    />
                    <DeltaCard
                      title="Vs anul trecut"
                      salesDelta={comparisonDeltas.yearSales}
                      dailyDelta={comparisonDeltas.yearDaily}
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
                  ]}
                  footer={promoSummary.incentive?.coverage_note ?? 'Bonus per unitate eligibila'}
                />
              </div>
            </button>
          </div>

          <div className="grid gap-3 xl:grid-cols-[1.2fr_1fr]">
            <div className="glass rounded-3xl p-4">
              <div className="mb-3 flex items-center gap-2">
                <CalendarRange size={16} className="text-indigo-500" />
                <h3 className="text-sm font-bold">Evolutie zilnica pentru {currentMonth}</h3>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
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
                  centerValue={formatCompactDonutValue(sumChartValues(categoryMixChartData, 'sales_total'), 'currency')}
                />
                <CompactPieSection
                  title="Branduri compatibile"
                  emptyLabel="Nu exista date pentru brandurile urmarite."
                  pieData={brandMixChartData}
                  dataKey="sales_total"
                  nameKey="brand"
                  valueFormatter={formatCurrency}
                  centerValue={formatCompactDonutValue(sumChartValues(brandMixChartData, 'sales_total'), 'currency')}
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
              <table className="min-w-330 w-full border-collapse text-xs">
                <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                  <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {regionalColumnsVisible.map((column, i) => (
                      <React.Fragment key={column.key}>
                        <SortableHeader
                          label={column.label}
                          active={regionalSort.key === column.key}
                          direction={regionalSort.direction}
                          onClick={() => handleSortRegionals(column.key)}
                          className={i === 0 ? 'w-24' : ''}
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
                      <td className="max-w-0 w-24 truncate px-3 py-2 font-semibold">{regional.regional}</td>
                      <td className="px-3 py-2">{formatCurrency(regional.target)}</td>
                      <td className="px-3 py-2">{formatCurrency(regional.total_vanzari)}</td>
                      <td className="px-3 py-2 font-bold text-indigo-600">{formatPercent(regional.proc_realizare_target)}</td>
                      {hasActivePromotion && <td className="px-3 py-2">{formatInt(regional.promo_qty)}</td>}
                      <td className="px-3 py-2">{formatInt(regional.incentive_qty)}</td>
                      <td className="px-3 py-2">{formatInt(regional.qty_total)}</td>
                      <td className="px-3 py-2">{formatInt(regional.nr_bonuri)}</td>
                      <td className="px-3 py-2">{formatCurrency(regional.medie_zilnica ?? 0)}</td>
                      <td className="px-3 py-2">{formatPercent(regional.proc_bon2acc)}</td>
                      <td className="px-3 py-2">{formatPercent(regional.prc_focus_acc_qty)}</td>
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
                  <MapPin size={16} className="text-indigo-500" />
                  <h3 className="text-sm font-bold">ASM — Area Sales Manager</h3>
                </div>
                <p className="text-[11px] text-slate-500">
                  Filtrare: {filterScopeLabel} · Sortare: {asmColumnsVisible.find((column) => column.key === asmSort.key)?.label} ({asmSort.direction}) · {asms.length} ASM
                </p>
              </div>
            </div>
            <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
              <table className="min-w-370 w-full border-collapse text-xs">
                <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                  <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {asmColumnsVisible.map((column, i) => (
                      <React.Fragment key={column.key}>
                        <SortableHeader
                          label={column.label}
                          active={asmSort.key === column.key}
                          direction={asmSort.direction}
                          onClick={() => handleSortAsms(column.key)}
                          className={i === 0 ? 'w-24' : ''}
                        />
                      </React.Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedAsms.map((asm, index) => (
                    <tr
                      key={`${asm.asm}-${asm.regional}`}
                      className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                    >
                      <td className="max-w-0 w-24 truncate px-3 py-2 font-semibold">{asm.asm}</td>
                      <td className="px-3 py-2">{formatCurrency(asm.target)}</td>
                      <td className="px-3 py-2">{formatCurrency(asm.total_vanzari)}</td>
                      <td className="px-3 py-2 font-bold text-indigo-600">{formatPercent(asm.proc_realizare_target)}</td>
                      {hasActivePromotion && <td className="px-3 py-2">{formatInt(asm.promo_qty)}</td>}
                      <td className="px-3 py-2">{formatInt(asm.incentive_qty)}</td>
                      <td className="px-3 py-2">{formatInt(asm.qty_total)}</td>
                      <td className="px-3 py-2">{formatInt(asm.nr_bonuri)}</td>
                      <td className="px-3 py-2">{formatCurrency(asm.medie_zilnica ?? 0)}</td>
                      <td className="px-3 py-2">{formatPercent(asm.proc_bon2acc)}</td>
                      <td className="px-3 py-2">{formatPercent(asm.prc_focus_acc_qty)}</td>
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
                  Filtrare: {filterScopeLabel} Â· Sortare: {STORE_COLUMNS.find((column) => column.key === storeSort.key)?.label} ({storeSort.direction}) Â· {stores.length} magazine
                </p>
              </div>
            </div>
            <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
              <table className="min-w-330 w-full border-collapse text-xs">
                <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                  <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {STORE_COLUMNS.map((column, i) => (
                      <React.Fragment key={column.key}>
                        <SortableHeader
                          label={column.label}
                          active={storeSort.key === column.key}
                          direction={storeSort.direction}
                          onClick={() => handleSortStores(column.key)}
                          className={i === 0 ? 'w-36' : ''}
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
              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold">Evolutie lunara</h3>
                    <p className="text-[11px] text-slate-500">Ultimele 12 luni pana la {historyMonth}</p>
                  </div>
                  <div className="rounded-2xl bg-indigo-50 px-3 py-2 text-right dark:bg-indigo-900/20">
                    <div className="text-[10px] uppercase tracking-wide text-slate-500">Best month</div>
                    <div className="text-lg font-black text-indigo-600">{bestHistoryMonth?.month ?? '-'}</div>
                  </div>
                </div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                    <ComposedChart data={historyChartData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                      <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis yAxisId="progress" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <Tooltip formatter={(value: number, name: string) => (name === '% target' ? `${value.toFixed(2)}%` : formatCurrency(value))} />
                      <Legend />
                      <Bar yAxisId="sales" dataKey="sales" name="Vanzari" fill="#4f46e5" radius={[8, 8, 0, 0]} />
                      <Line yAxisId="sales" type="monotone" dataKey="target" name="Target" stroke="#10b981" strokeWidth={2} dot={false} />
                      <Line yAxisId="progress" type="monotone" dataKey="progress" name="% target" stroke="#f59e0b" strokeWidth={2} dot={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center gap-2">
                  <TrendingUp size={16} className="text-indigo-500" />
                  <h3 className="text-sm font-bold">Trend vanzari vs target</h3>
                </div>
                <div className="h-52">
                  <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                    <AreaChart data={historyChartData}>
                      <defs>
                        <linearGradient id="historySalesArea" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.35} />
                          <stop offset="95%" stopColor="#4f46e5" stopOpacity={0.03} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                      <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <Tooltip formatter={(value: number) => formatCurrency(value)} />
                      <Area type="monotone" dataKey="sales" stroke="#4f46e5" fill="url(#historySalesArea)" strokeWidth={3} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
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
                <div className="grid grid-cols-4 gap-2">
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
                          ]}
                          footer={historyPromoSummary.incentive!.coverage_note ?? 'Bonus per unitate eligibila'}
                        />
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* Evolutie zilnica + Top categorii si branduri */}
              <div className="grid gap-3 xl:grid-cols-[1.2fr_1fr]">
                <div className="glass rounded-3xl p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <CalendarRange size={16} className="text-indigo-500" />
                    <h3 className="text-sm font-bold">Evolutie zilnica pentru {historyMonth}</h3>
                  </div>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%" minWidth={0}>
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
                      centerValue={formatCompactDonutValue(sumChartValues(historyCategoryMixChartData, 'sales_total'), 'currency')}
                    />
                    <CompactPieSection
                      title="Branduri compatibile"
                      emptyLabel="Nu exista date pentru brandurile urmarite."
                      pieData={historyBrandMixChartData}
                      dataKey="sales_total"
                      nameKey="brand"
                      valueFormatter={formatCurrency}
                      centerValue={formatCompactDonutValue(sumChartValues(historyBrandMixChartData, 'sales_total'), 'currency')}
                    />
                  </div>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: string;
  accent: 'indigo' | 'emerald' | 'amber' | 'rose';
}) {
  const accentClasses: Record<string, string> = {
    indigo: 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20',
    emerald: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20',
    amber: 'bg-amber-50 text-amber-600 dark:bg-amber-900/20',
    rose: 'bg-rose-50 text-rose-600 dark:bg-rose-900/20',
  };

  return (
    <div className="glass rounded-3xl p-4">
      <div className={`mb-3 flex h-10 w-10 items-center justify-center rounded-2xl ${accentClasses[accent]}`}>
        <Icon size={18} />
      </div>
      <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-black">{value}</div>
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  emphasize = false,
  accent = 'slate',
  className = '',
}: {
  label: string;
  value: React.ReactNode;
  detail?: string;
  emphasize?: boolean;
  accent?: 'slate' | 'indigo';
  className?: string;
}) {
  const accentClasses =
    accent === 'indigo'
      ? 'bg-indigo-50/80 dark:bg-indigo-900/20'
      : 'bg-slate-50 dark:bg-slate-800/60';

  return (
    <div className={`rounded-2xl p-3 ${accentClasses} ${emphasize ? 'flex h-full flex-col justify-between' : ''} ${className}`}>
      <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`${emphasize ? 'mt-4 text-[2rem] leading-none' : 'mt-1 text-base leading-tight'} font-black`}>{value ?? '-'}</div>
      {detail ? <div className="mt-2 text-xs leading-relaxed text-slate-500">{detail}</div> : null}
    </div>
  );
}

function KpiPerformanceCard({
  title,
  value,
  tone,
  chartData,
  dataKey,
  nameKey,
  formatValue,
  className = '',
}: {
  title: string;
  value: number | null;
  tone: PerformanceTone;
  chartData: Array<Record<string, string | number>>;
  dataKey: string;
  nameKey: string;
  formatValue: (value: number) => string;
  className?: string;
}) {
  return (
    <div className={`rounded-3xl border p-2.5 ${tone.cardClass} ${className}`}>
      <div className="mb-1 flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wide opacity-75">{title}</div>
          <div className="mt-0.5 text-[2rem] font-black leading-none">{formatPercent(value)}</div>
        </div>
        <div className="mt-1">
          <span className={`block h-3 w-3 rounded-full ${tone.badgeClass}`} />
        </div>
      </div>
      <DonutLegendChart
        data={chartData}
        dataKey={dataKey}
        nameKey={nameKey}
        colors={KPI_PIE_COLORS}
        valueFormatter={formatValue}
        centerLabel="TOTAL"
        centerValue={formatCompactDonutValue(sumChartValues(chartData, dataKey), 'number')}
        showShare
        compact
      />
    </div>
  );
}

function CampaignMiniCard({
  label,
  title,
  status,
  metrics,
  footer,
}: {
  label: string;
  title: string;
  status: string;
  metrics: Array<{ label: string; value: string }>;
  footer: string;
}) {
  return (
    <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
      <div className="mb-1 flex items-center justify-between gap-2">
        <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</div>
        <div className="text-[11px] font-bold uppercase tracking-wide text-indigo-600">{status}</div>
      </div>
      <div className="text-base font-bold leading-tight">{title}</div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        {metrics.map((metric) => (
          <div key={metric.label} className="rounded-2xl bg-white/70 px-3 py-2 dark:bg-slate-900/30">
            <div className="text-[11px] uppercase tracking-wide text-slate-500">{metric.label}</div>
            <div className="mt-1 text-sm font-bold">{metric.value}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 text-xs leading-relaxed text-slate-500">{footer}</div>
    </div>
  );
}

function CompactPieSection({
  title,
  emptyLabel,
  pieData,
  dataKey,
  nameKey,
  valueFormatter,
  centerValue,
}: {
  title: string;
  emptyLabel: string;
  pieData: Array<Record<string, string | number>>;
  dataKey: string;
  nameKey: string;
  valueFormatter: (value: number) => string;
  centerValue: string;
}) {
  return (
    <div className="rounded-2xl bg-slate-50/80 p-3 dark:bg-slate-800/40">
      <div className="mb-3 text-sm font-bold tracking-wide text-slate-600 dark:text-slate-300">{title}</div>
      {pieData.length === 0 ? (
        <div className="rounded-2xl bg-white/70 p-4 text-xs font-semibold text-slate-500 dark:bg-slate-900/30">
          {emptyLabel}
        </div>
      ) : (
        <DonutLegendChart
          data={pieData}
          dataKey={dataKey}
          nameKey={nameKey}
          colors={PIE_COLORS}
          valueFormatter={valueFormatter}
          centerLabel="TOTAL"
          centerValue={centerValue}
          sideBySide
        />
      )}
    </div>
  );
}

function DonutLegendChart({
  data,
  dataKey,
  nameKey,
  colors,
  valueFormatter,
  centerLabel,
  centerValue,
  showShare = false,
  compact = false,
  sideBySide = false,
}: {
  data: Array<Record<string, string | number>>;
  dataKey: string;
  nameKey: string;
  colors: string[];
  valueFormatter: (value: number) => string;
  centerLabel: string;
  centerValue: string;
  showShare?: boolean;
  compact?: boolean;
  sideBySide?: boolean;
}) {
  const legendRows = data.slice(0, 6);
  const layoutClass = sideBySide
    ? 'grid-cols-[minmax(0,180px)_minmax(0,1fr)]'
    : compact
      ? 'lg:grid-cols-[minmax(0,160px)_minmax(0,1fr)]'
      : 'lg:grid-cols-[minmax(0,190px)_minmax(0,1fr)]';

  return (
    <div className={`grid gap-1.5 ${layoutClass} items-center`}>
      <div className={`mx-auto w-full ${compact ? 'h-36 max-w-45' : 'h-48 max-w-55'}`}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <PieChart>
            <Pie
              data={data}
              dataKey={dataKey}
              nameKey={nameKey}
              innerRadius={compact ? 40 : 46}
              outerRadius={compact ? 66 : 78}
              paddingAngle={2}
              stroke="transparent"
            >
              {data.map((entry, index) => (
                <Cell key={`${entry[nameKey]}-${index}`} fill={colors[index % colors.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(value: number) => valueFormatter(Number(value))} />
            <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle">
              <tspan x="50%" dy="-0.9em" className={`fill-slate-500 font-bold uppercase tracking-wide ${compact ? 'text-[10px]' : 'text-[11px]'}`}>
                {centerLabel}
              </tspan>
              <tspan x="50%" dy="1.2em" className={`fill-slate-900 font-black dark:fill-slate-100 ${compact ? 'text-[18px]' : 'text-[20px]'}`}>
                {centerValue}
              </tspan>
            </text>
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className={sideBySide ? 'space-y-0' : compact ? 'space-y-0.5' : 'space-y-2'}>
        {legendRows.map((item, index) => (
          <div
            key={`${String(item[nameKey])}-${index}`}
            className={`flex items-center justify-between gap-2 text-xs dark:bg-slate-900/30 ${
              sideBySide
                ? 'border-b border-slate-200/70 py-2 last:border-b-0'
                : compact
                  ? 'rounded-2xl bg-white/70 px-2.5 py-0.5'
                  : 'rounded-2xl bg-white/70 px-3 py-2'
            }`}
          >
            <div className="flex min-w-0 items-center gap-2">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: colors[index % colors.length] }}
              />
              <span className="text-[11px] font-semibold text-slate-500">
                {formatPercent(Number(item.share_pct ?? 0))}
              </span>
              <span className="font-bold">{valueFormatter(Number(item[dataKey] ?? 0))}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PeriodTable({
  current,
  previous,
  yoy,
}: {
  current: PeriodComparisonPoint;
  previous: PeriodComparisonPoint;
  yoy: PeriodComparisonPoint;
}) {
  const points = [current, previous, yoy];
  const rows: { label: string; fn: (p: PeriodComparisonPoint) => string }[] = [
    { label: 'Vanzari',      fn: (p) => formatCurrency(p.total_sales) },
    { label: 'Cantitate',    fn: (p) => formatInt(p.total_quantity) },
    { label: 'Bonuri',       fn: (p) => formatInt(p.total_receipts) },
    { label: 'Zile',         fn: (p) => formatInt(p.working_days) },
    { label: 'Med. zilnica', fn: (p) => formatCurrency(p.daily_average ?? 0) },
    { label: 'Med. bon',     fn: (p) => formatCurrency(p.avg_receipt_value ?? 0) },
    { label: 'Bon2Acc',      fn: (p) => formatPercent(p.proc_bon2acc) },
    { label: 'Focus/Acc',    fn: (p) => formatPercent(p.prc_focus_acc_qty) },
  ];

  return (
    <div className="w-full overflow-hidden rounded-2xl bg-slate-50 dark:bg-slate-800/50">
      <table className="w-full table-fixed text-[11px]">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-700">
            <th className="py-2 pl-3 pr-2 text-left font-semibold text-slate-400 w-[22%]" />
            {points.map((p) => (
              <th key={p.label} className="py-2 px-2 text-center w-[26%]">
                <div className="font-bold text-slate-700 dark:text-slate-200">{p.label}</div>
                <div className="text-[10px] font-normal text-slate-400">{p.month}</div>
                <div className="text-[10px] font-normal text-slate-400">{p.day_range}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={row.label}
              className={i % 2 === 0 ? 'bg-white/60 dark:bg-slate-900/20' : ''}
            >
              <td className="py-1.5 pl-3 pr-2 text-slate-500 font-medium truncate">{row.label}</td>
              {points.map((p) => (
                <td key={p.label} className="py-1.5 px-3 text-center font-semibold text-slate-700 dark:text-slate-200 tabular-nums">
                  {row.fn(p)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DeltaCard({
  title,
  salesDelta,
  dailyDelta,
}: {
  title: string;
  salesDelta: number;
  dailyDelta: number;
}) {
  const positive = salesDelta >= 0;
  const tone = positive
    ? 'border-emerald-200 bg-emerald-50/80 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-300'
    : 'border-rose-200 bg-rose-50/80 text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-300';

  return (
    <div className={`rounded-2xl border p-3 ${tone}`}>
      <div className="mb-2 text-[11px] font-bold uppercase tracking-wide">{title}</div>
      <div className="grid gap-2 sm:grid-cols-2">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide opacity-70">Delta vanzari</div>
          <div className="mt-1 text-lg font-black">{formatDeltaCurrency(salesDelta)}</div>
        </div>
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide opacity-70">Delta medie zilnica</div>
          <div className="mt-1 text-lg font-black">{formatDeltaCurrency(dailyDelta)}</div>
        </div>
      </div>
    </div>
  );
}

function SortableHeader({
  label,
  active,
  direction,
  onClick,
  className = '',
}: {
  label: string;
  active: boolean;
  direction: SortDirection;
  onClick: () => void;
  className?: string;
}) {
  return (
    <th className={`px-3 py-3 font-bold ${className}`}>
      <button
        type="button"
        onClick={onClick}
        className="inline-flex items-center gap-1 transition hover:text-slate-700 dark:hover:text-slate-200"
      >
        {label}
        {active ? direction === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} /> : <ArrowUpDown size={12} />}
      </button>
    </th>
  );
}

function formatDeltaCurrency(value: number) {
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${formatCurrency(value)}`;
}

function CompactCurrency({ value }: { value: number }) {
  const formatted = formatCurrency(value);
  const [amount, currency = 'RON'] = formatted.split(/\s(?=[A-Z]{3}$)/);

  return (
    <span className="inline-flex flex-wrap items-end gap-1">
      <span>{amount}</span>
      <span className="text-[0.5em] font-bold opacity-75">{currency}</span>
    </span>
  );
}

function getAgentSortValue(agent: AgentStat, key: AgentSortKey): number {
  const value = agent[key];
  if (value === null || value === undefined) {
    return Number.NEGATIVE_INFINITY;
  }
  const num = Number(value);
  return Number.isNaN(num) ? Number.NEGATIVE_INFINITY : num;
}

function getStoreDailyAverage(store: StoreStat): number {
  if (!store.zile_active) {
    return 0;
  }
  return Number(store.total_vanzari) / Number(store.zile_active);
}

function getStoreSortValue(store: StoreStat, key: StoreSortKey): number {
  if (key === 'medie_zilnica') {
    return getStoreDailyAverage(store);
  }
  const value = store[key];
  if (value === null || value === undefined) {
    return Number.NEGATIVE_INFINITY;
  }
  const num = Number(value);
  return Number.isNaN(num) ? Number.NEGATIVE_INFINITY : num;
}

function getRegionalSortValue(regional: RegionalStat, key: RegionalSortKey): number {
  const value = regional[key];
  if (value === null || value === undefined) {
    return Number.NEGATIVE_INFINITY;
  }
  const num = Number(value);
  return Number.isNaN(num) ? Number.NEGATIVE_INFINITY : num;
}

function getAsmSortValue(asm: AsmStat, key: AsmSortKey): number {
  const value = asm[key];
  if (value === null || value === undefined) {
    return Number.NEGATIVE_INFINITY;
  }
  const num = Number(value);
  return Number.isNaN(num) ? Number.NEGATIVE_INFINITY : num;
}

function sumChartValues(rows: Array<Record<string, string | number>>, key: string): number {
  return rows.reduce((total, row) => total + Number(row[key] ?? 0), 0);
}

function formatCompactDonutValue(value: number, mode: 'number' | 'currency'): string {
  const compact = new Intl.NumberFormat('ro-RO', {
    notation: 'compact',
    maximumFractionDigits: value >= 1000000 ? 1 : 0,
  }).format(value);
  return mode === 'currency' ? compact : compact;
}

function describeFilterScope(filters: AppFilters): string {
  if (filters.agent !== ALL_SCOPE) {
    return `Agent ${filters.agent}`;
  }
  if (filters.magazin !== ALL_STORES) {
    return `Magazin ${filters.magazin}`;
  }
  if (filters.asm !== ALL_SCOPE) {
    return `ASM ${filters.asm}`;
  }
  if (filters.rm !== ALL_SCOPE) {
    return `Regional ${filters.rm}`;
  }
  if (filters.firma !== ALL_FIRMS) {
    return `Firma ${filters.firma}`;
  }
  return 'Toata selectia activa';
}

function getBon2AccTone(value: number): PerformanceTone {
  if (value >= 31) {
    return {
      label: 'Foarte bun',
      cardClass: 'border-emerald-200 bg-emerald-50/80 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-200',
      badgeClass: 'bg-emerald-500 dark:bg-emerald-400',
    };
  }
  if (value >= 30) {
    return {
      label: 'Solid',
      cardClass: 'border-lime-200 bg-lime-50/80 text-lime-800 dark:border-lime-900/40 dark:bg-lime-950/20 dark:text-lime-200',
      badgeClass: 'bg-lime-500 dark:bg-lime-400',
    };
  }
  if (value >= 28) {
    return {
      label: 'Atentie',
      cardClass: 'border-amber-200 bg-amber-50/80 text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200',
      badgeClass: 'bg-amber-500 dark:bg-amber-400',
    };
  }
  return {
    label: 'Critic',
    cardClass: 'border-rose-200 bg-rose-50/80 text-rose-800 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200',
    badgeClass: 'bg-rose-500 dark:bg-rose-400',
  };
}

function getFocusTone(value: number): PerformanceTone {
  if (value >= 8) {
    return {
      label: 'Foarte bun',
      cardClass: 'border-emerald-200 bg-emerald-50/80 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-200',
      badgeClass: 'bg-emerald-500 dark:bg-emerald-400',
    };
  }
  if (value >= 7) {
    return {
      label: 'In target',
      cardClass: 'border-lime-200 bg-lime-50/80 text-lime-800 dark:border-lime-900/40 dark:bg-lime-950/20 dark:text-lime-200',
      badgeClass: 'bg-lime-500 dark:bg-lime-400',
    };
  }
  if (value >= 6) {
    return {
      label: 'Sub tinta',
      cardClass: 'border-amber-200 bg-amber-50/80 text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200',
      badgeClass: 'bg-amber-500 dark:bg-amber-400',
    };
  }
  return {
    label: 'Critic',
    cardClass: 'border-rose-200 bg-rose-50/80 text-rose-800 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200',
    badgeClass: 'bg-rose-500 dark:bg-rose-400',
  };
}

function LoadingCard({ label }: { label: string }) {
  return (
    <div className="glass flex flex-col items-center justify-center gap-3 rounded-3xl p-8">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-200 border-t-indigo-600" />
      <div className="text-sm font-medium text-slate-500">{label}</div>
    </div>
  );
}

function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="glass flex flex-col items-center gap-4 rounded-3xl p-6">
      <div className="flex items-center gap-2 text-amber-600">
        <AlertCircle className="h-5 w-5" />
        <span className="text-sm font-medium">{message}</span>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-indigo-700"
      >
        <RefreshCw className="h-4 w-4" />
        Reincearca
      </button>
    </div>
  );
}
