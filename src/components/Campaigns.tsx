import React, { type ComponentType, useCallback, useEffect, useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { FirmaBadge } from './FirmaBadge';
import {
  BadgePercent,
  Building2,
  Gift,
  Medal,
  PackageSearch,
  Sparkles,
  Tag,
  Trophy,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getCampaignSnapshot, getFocusHistory, getPromotionsIncentives } from '../api/campaigns';
import { getActiveContests } from '../api/contests';
import { getPremiumGlassAnalysis } from '../api/dashboard';
import type {
  CampaignSnapshot,
  CampaignPromotionOption,
  CampaignsPromotionsResponse,
  ContestResponse,
  FocusHistoryPoint,
  IncentiveCategory,
  IncentiveCategoryBreakdown,
  IncentiveTopAgent,
  PremiumGlassAnalysis,
  PremiumGlassAgentStat,
  PremiumGlassManagerStat,
  PremiumGlassModelStat,
  PremiumGlassStoreStat,
  PremiumGlassSurfaceStat,
  PremiumGlassSurfaceMode,
  PromoTopAgent,
  PromoTopStore,
} from '../api/types';
import { buildScopedMonthQuery } from '../lib/filterQueries';
import { formatCurrency, formatInt, formatPercent } from '../lib/formatters';
import { queryKeys } from '../lib/queryKeys';
import type { ExportColumn } from '../lib/tableExport';
import { useSortable, type SortDirection } from '../lib/useSortable';
import { ExportTableButton } from './ExportTableButton';
import type { AppFilters } from './MainLayout';
import { SegmentedTabs, type SegmentedTabOption } from './common/SegmentedTabs';
import { ErrorCard, LoadingCard, Metric } from './dashboard/DashboardWidgets';

type CampaignSection = 'incentive' | 'promo' | 'concurs' | 'premium' | 'focus';

interface CampaignsProps {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
  preferredSection: CampaignSection;
  onSectionChange: (section: CampaignSection) => void;
  onFilterMonthChange?: (month: string) => void;
}

const emptySnapshot: CampaignSnapshot = {
  overview: {
    month: '',
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

const STAT_ACCENT_CLASSES: Record<string, string> = {
  amber: 'bg-amber-50 text-amber-600 dark:bg-amber-900/20',
  indigo: 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20',
  emerald: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20',
  rose: 'bg-rose-50 text-rose-600 dark:bg-rose-900/20',
};

const SECTION_TABS: SegmentedTabOption<CampaignSection>[] = [
  { value: 'incentive', label: 'Incentive' },
  { value: 'promo', label: 'Promo' },
  { value: 'concurs', label: 'Concurs' },
  { value: 'premium', label: 'Folii premium' },
  { value: 'focus', label: 'Focus' },
];

function getMonthEndDate(month: string): string {
  const [year = 0, monthIndex = 1] = month.split('-').map(Number);
  const lastDay = new Date(year, monthIndex, 0).getDate();
  return `${month}-${String(lastDay).padStart(2, '0')}`;
}

function displayStoreName(storeName: string | null | undefined): string {
  if (!storeName) return '';
  return storeName.includes(' - ') ? storeName.split(' - ').slice(1).join(' - ') : storeName;
}

export function Campaigns({
  currentMonth,
  months,
  filters,
  preferredSection,
  onSectionChange,
  onFilterMonthChange,
}: CampaignsProps) {
  const latestMonth = useMemo(() => months[0] ?? currentMonth, [months, currentMonth]);
  const [activeSection, setActiveSection] = useState<CampaignSection>(preferredSection);
  const [historyMonth, setHistoryMonth] = useState(latestMonth);
  const [promoMonth, setPromoMonth] = useState(latestMonth);
  const [selectedPromotionKey, setSelectedPromotionKey] = useState('');
  const [selectedContestKey, setSelectedContestKey] = useState('');
  const [premiumSurfaceMode, setPremiumSurfaceMode] = useState<PremiumGlassSurfaceMode>('all');

  useEffect(() => {
    const fallbackMonth = latestMonth || currentMonth;
    setHistoryMonth((previous) => (months.includes(previous) ? previous : fallbackMonth));
    setPromoMonth((previous) => {
      if (!fallbackMonth) return '';
      if (!months.length) return fallbackMonth;
      if (!previous || previous === currentMonth) return fallbackMonth;
      return months.includes(previous) ? previous : fallbackMonth;
    });
  }, [months, currentMonth, latestMonth]);

  useEffect(() => {
    setActiveSection(preferredSection);
  }, [preferredSection]);

  useEffect(() => {
    onSectionChange(activeSection);
  }, [activeSection, onSectionChange]);

  useEffect(() => {
    if (promoMonth) onFilterMonthChange?.(promoMonth);
  }, [promoMonth, onFilterMonthChange]);

  const buildQuery = useCallback(
    (month: string) => buildScopedMonthQuery(month, filters),
    [filters]
  );

  const promoQuery = useMemo(() => buildQuery(promoMonth), [buildQuery, promoMonth]);
  const historyQueryParams = useMemo(
    () => ({ ...buildQuery(historyMonth), months_back: 12 }),
    [buildQuery, historyMonth],
  );
  const shouldLoadPromoData = activeSection === 'promo' || activeSection === 'incentive';
  const shouldLoadSnapshot = activeSection === 'focus';
  const shouldLoadPremiumGlass = activeSection === 'premium';
  const shouldLoadCurrent = shouldLoadPromoData || shouldLoadSnapshot || shouldLoadPremiumGlass;

  const currentQuery = useQuery({
    queryKey: queryKeys.campaigns.current(
      activeSection,
      promoMonth,
      selectedPromotionKey,
      shouldLoadPremiumGlass ? { ...promoQuery, surface: premiumSurfaceMode } : promoQuery,
    ),
    enabled: Boolean(promoMonth) && shouldLoadCurrent,
    staleTime: CAMPAIGNS_STALE_MS,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const result: CampaignCurrentCache = {};
      const requests: Promise<void>[] = [];

      if (shouldLoadSnapshot) {
        requests.push(
          getCampaignSnapshot(promoQuery).then((snapshotData) => {
            result.snapshot = snapshotData;
          }),
        );
      }

      if (shouldLoadPromoData) {
        requests.push(
          getPromotionsIncentives(`${promoMonth}-01`, getMonthEndDate(promoMonth), {
            ...promoQuery,
            view: activeSection === 'promo' ? 'promo' : 'incentive',
            ...(selectedPromotionKey && { promotion_key: selectedPromotionKey }),
          }).then((promoResponse) => {
            result.promoData = promoResponse;
          }),
        );
      }

      if (shouldLoadPremiumGlass) {
        requests.push(
          getPremiumGlassAnalysis({
            ...promoQuery,
            surface: premiumSurfaceMode,
            current_scope: true,
            include_closed_stores: false,
          }).then((premiumResponse) => {
            result.premiumGlass = premiumResponse;
          }),
        );
      }

      await Promise.all(requests);
      return result;
    },
  });

  const focusHistoryQuery = useQuery({
    queryKey: queryKeys.campaigns.history(historyMonth, historyQueryParams),
    enabled: activeSection === 'focus' && Boolean(historyMonth),
    staleTime: CAMPAIGNS_STALE_MS,
    placeholderData: keepPreviousData,
    queryFn: () => getFocusHistory(historyQueryParams),
  });

  const contestsQuery = useQuery({
    queryKey: queryKeys.campaigns.contests(promoMonth),
    enabled: activeSection === 'concurs' && Boolean(promoMonth),
    staleTime: CAMPAIGNS_STALE_MS,
    placeholderData: keepPreviousData,
    queryFn: () => getActiveContests(promoMonth),
  });

  const currentData = currentQuery.data ?? {};
  const snapshot = currentData.snapshot ?? emptySnapshot;
  const promoData = currentData.promoData ?? null;
  const premiumGlass = currentData.premiumGlass ?? null;
  const focusHistory = focusHistoryQuery.data?.history ?? EMPTY_FOCUS_HISTORY;
  const contests = contestsQuery.data ?? EMPTY_CONTESTS;
  const promoSelectionPending = Boolean(
    shouldLoadPromoData &&
    selectedPromotionKey &&
    promoData?.selected_promotion_key &&
    promoData.selected_promotion_key !== selectedPromotionKey
  );

  useEffect(() => {
    if (!promoData) return;
    const availableKeys = promoData.promotions.map((promotion) => promotion.key);
    if (
      selectedPromotionKey &&
      availableKeys.length > 0 &&
      !availableKeys.includes(selectedPromotionKey)
    ) {
      setSelectedPromotionKey(availableKeys[0]);
    }
  }, [promoData, selectedPromotionKey]);

  useEffect(() => {
    if (activeSection !== 'concurs') return;
    setSelectedContestKey((previous) => (
      contests.some((contest) => contest.key === previous)
        ? previous
        : (contests[0]?.key ?? '')
    ));
  }, [activeSection, contests]);

  const hasCurrentData = !shouldLoadCurrent ||
    (shouldLoadPromoData && currentData.promoData !== undefined && !promoSelectionPending) ||
    (shouldLoadSnapshot && currentData.snapshot !== undefined) ||
    (shouldLoadPremiumGlass && currentData.premiumGlass !== undefined);
  const loading = shouldLoadCurrent && currentQuery.isFetching && (!hasCurrentData || promoSelectionPending);
  const error = currentQuery.isError && !hasCurrentData
    ? 'Datele pentru campanii si focus nu au putut fi incarcate.'
    : '';
  const historyLoading = activeSection === 'focus' && focusHistoryQuery.isFetching && !focusHistoryQuery.data;
  const historyError = focusHistoryQuery.isError
    ? 'Istoricul focus nu a putut fi incarcat.'
    : focusHistoryQuery.isSuccess && focusHistory.length === 0
      ? 'Nu exista istoric focus pentru filtrarea curenta.'
      : '';
  const contestLoading = activeSection === 'concurs' && contestsQuery.isFetching && !contestsQuery.data;
  const contestError = contestsQuery.isError && !contestsQuery.data
    ? 'Concursul nu a putut fi incarcat.'
    : '';

  const selectedHistoryPoint = useMemo(
    () =>
      focusHistory.find((item) => item.month === historyMonth) ??
      focusHistory[focusHistory.length - 1] ??
      null,
    [focusHistory, historyMonth]
  );

  const focusHistoryChart = useMemo(
    () =>
      focusHistory.map((item) => ({
        month: item.month.slice(2),
        sales: Number(item.total_focus_sales),
        qty: Number(item.total_focus_qty),
        share: Number(item.focus_share_pct ?? 0),
      })),
    [focusHistory]
  );

  const selectedContest = useMemo(
    () => contests.find((contest) => contest.key === selectedContestKey) ?? contests[0] ?? null,
    [contests, selectedContestKey]
  );

  const headline = useMemo(() => {
    if (snapshot.products.length === 0) {
      return `Nu exista inca focus products vandute in ${promoMonth} pentru filtrarea selectata.`;
    }
    const leader = snapshot.products[0];
    return `${leader.item_name} conduce ${promoMonth} cu ${formatInt(leader.qty_total)} bucati si ${formatCurrency(leader.sales_total)}.`;
  }, [snapshot.products, promoMonth]);
  const loadingLabel = activeSection === 'promo'
    ? 'Se incarca promotia...'
    : activeSection === 'incentive'
      ? 'Se incarca incentive-ul...'
      : activeSection === 'premium'
        ? 'Se incarca analiza foliilor premium...'
        : 'Se incarca datele de focus...';

  return (
    <div className="mx-auto max-w-6xl space-y-3 p-3 pb-24 pt-2">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Focus</h1>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Incentive, promo, concurs si folii premium folosesc luna {promoMonth}; istoricul focus se analizeaza separat.
        </p>
      </div>

      <SegmentedTabs<CampaignSection>
        ariaLabel="Sectiuni Focus"
        className="glass"
        options={SECTION_TABS}
        value={activeSection}
        onChange={setActiveSection}
      />

      {activeSection === 'concurs' ? (
        contestLoading ? (
          <LoadingCard label="Se incarca concursul..." />
        ) : contestError ? (
          <ErrorCard message={contestError} onRetry={() => { void contestsQuery.refetch(); }} />
        ) : (
          <>
            <CampaignMonthBar title="Concurs" icon={Trophy} months={months} value={promoMonth} onChange={setPromoMonth} currentMonth={latestMonth} />
            {contests.length > 0 ? (
              <div className="space-y-3">
                {contests.length > 1 && (
                  <ContestSelector
                    contests={contests}
                    selectedKey={selectedContest?.key ?? ''}
                    onSelect={setSelectedContestKey}
                  />
                )}
                {selectedContest && <ContestView contest={selectedContest} />}
              </div>
            ) : (
              <EmptyCard message={`Nu exista concurs activ in ${promoMonth}.`} />
            )}
          </>
        )
      ) : loading ? (
        <LoadingCard label={loadingLabel} />
      ) : error ? (
        <ErrorCard message={error} onRetry={() => { void currentQuery.refetch(); }} />
      ) : activeSection === 'promo' ? (
        <>
          <CampaignMonthBar title="Promotie" icon={BadgePercent} months={months} value={promoMonth} onChange={setPromoMonth} currentMonth={latestMonth} />
          {promoData && promoData.promotions.length > 1 && (
            <PromotionSelector
              promotions={promoData.promotions}
              selectedKey={selectedPromotionKey || promoData.selected_promotion_key}
              onSelect={setSelectedPromotionKey}
            />
          )}
          {!promoData?.has_active_promotion ? (
            <EmptyCard message={`Nu exista promotie activa in ${promoMonth}.`} />
          ) : (
            <>
              <div className="glass rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900">
                <div className="mb-3 flex items-center gap-2 text-amber-600 dark:text-amber-400">
                  <BadgePercent size={16} />
                  <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Promotii</span>
                </div>
                <div className="mb-1">
                  <h4 className="text-base font-black tracking-tight">{promoData.promo_title || 'Promotie'}</h4>
                  {promoData.promo_description && (
                    <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{promoData.promo_description}</p>
                  )}
                </div>

                <div className="mb-3">
                  <div className="text-3xl font-black">{formatInt(promoData.promo_qualifying_bons)}</div>
                  <div className="text-[11px] text-slate-500">unitati promo efective / bonuri calificate</div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <div className="text-lg font-black text-amber-600">{formatInt(promoData.promo_discounted_units)}</div>
                    <div className="text-[10px] text-slate-500">Produse reduse</div>
                  </div>
                  <div>
                    <div className="text-lg font-black">{formatInt(promoData.promo_active_stores)}</div>
                    <div className="text-[10px] text-slate-500">Magazine</div>
                  </div>
                  <div>
                    <div className="text-lg font-black">{formatInt(promoData.promo_active_agents)}</div>
                    <div className="text-[10px] text-slate-500">Agenti</div>
                  </div>
                </div>
              </div>

              {promoData.top_stores.length > 0 && (
                <div className="glass rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900">
                  <div className="mb-3 flex items-center gap-2 text-amber-600 dark:text-amber-400">
                    <Building2 size={16} />
                    <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Magazine</span>
                  </div>
                  <SortableTable<PromoTopStore & Record<string, unknown>>
                    rows={promoData.top_stores as (PromoTopStore & Record<string, unknown>)[]}
                    defaultSortKey="promo_bons"
                    exportFilename={`focus-promo-magazine-${promoMonth}-${promoData.selected_promotion_key}`}
                    exportSheetName="Magazine promo"
                    exportColumns={[
                      { header: '#', value: (_row, index) => index + 1 },
                      { header: 'Firma', value: (row) => row.firma },
                      { header: 'Magazin', value: (row) => displayStoreName(row.store_name) },
                      { header: 'Bonuri', value: (row) => row.promo_bons },
                    ]}
                    columns={[
                      {
                        key: 'rank',
                        label: '#',
                        sortable: false,
                        render: (_row, index) => (
                          <span className="font-bold text-slate-400">{index + 1}</span>
                        ),
                      },
                      {
                        key: 'store_name',
                        label: 'Magazin',
                        render: (row) => {
                          const store = row as unknown as PromoTopStore;
                          const displayName = store.store_name.includes(' - ')
                            ? store.store_name.split(' - ').slice(1).join(' - ')
                            : store.store_name;
                          return (
                            <span className="flex items-center">
                              <FirmaBadge firma={store.firma} />
                              <span className="max-w-[150px] truncate font-semibold sm:max-w-[240px]" title={store.store_name}>
                                {displayName}
                              </span>
                            </span>
                          );
                        },
                      },
                      {
                        key: 'promo_bons',
                        label: 'Bonuri',
                        align: 'right',
                        render: (row) => (
                          <span className="font-black text-amber-600">{formatInt((row as unknown as PromoTopStore).promo_bons ?? 0)}</span>
                        ),
                      },
                    ]}
                  />
                </div>
              )}

              {(promoData.promo_agents ?? []).length > 0 && (
                <div className="glass rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900">
                  <div className="mb-3 flex items-center gap-2 text-amber-600 dark:text-amber-400">
                    <Sparkles size={16} />
                    <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Agenti</span>
                  </div>
                  <SortableTable<PromoTopAgent & Record<string, unknown>>
                    rows={(promoData.promo_agents ?? []) as (PromoTopAgent & Record<string, unknown>)[]}
                    defaultSortKey="promo_bons"
                    exportFilename={`focus-promo-agenti-${promoMonth}-${promoData.selected_promotion_key}`}
                    exportSheetName="Agenti promo"
                    exportColumns={[
                      { header: '#', value: (_row, index) => index + 1 },
                      { header: 'Agent', value: (row) => row.agent_name },
                      { header: 'Firma', value: (row) => row.firma },
                      { header: 'Magazin', value: (row) => displayStoreName(row.store_name) },
                      { header: 'Bonuri', value: (row) => row.promo_bons },
                    ]}
                    columns={[
                      {
                        key: 'rank',
                        label: '#',
                        sortable: false,
                        render: (_row, index) => <span className="font-bold text-slate-400">{index + 1}</span>,
                      },
                      {
                        key: 'agent_name',
                        label: 'Agent',
                        render: (row) => (
                          <span className="truncate font-semibold" title={(row as unknown as PromoTopAgent).agent_name}>
                            {(row as unknown as PromoTopAgent).agent_name}
                          </span>
                        ),
                      },
                      {
                        key: 'store_name',
                        label: 'Magazin',
                        render: (row) => {
                          const agent = row as unknown as PromoTopAgent;
                          const displayName = agent.store_name.includes(' - ')
                            ? agent.store_name.split(' - ').slice(1).join(' - ')
                            : agent.store_name;
                          return (
                            <span className="flex items-center">
                              <FirmaBadge firma={agent.firma} />
                              <span className="max-w-[100px] truncate" title={agent.store_name}>{displayName || '—'}</span>
                            </span>
                          );
                        },
                      },
                      {
                        key: 'promo_bons',
                        label: 'Bonuri',
                        align: 'right',
                        render: (row) => (
                          <span className="font-black text-amber-600">{formatInt((row as unknown as PromoTopAgent).promo_bons)}</span>
                        ),
                      },
                    ]}
                  />
                </div>
              )}
            </>
          )}
        </>
      ) : activeSection === 'incentive' ? (
        <>
          <CampaignMonthBar title="Incentive" icon={Gift} months={months} value={promoMonth} onChange={setPromoMonth} currentMonth={latestMonth} />

          <IncentiveCard promoData={promoData} />

          <IncentiveCategoryCard promoData={promoData} month={promoMonth} />

          {promoData && promoData.top_agents.length > 0 && (
            <div className="glass rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900">
              <div className="mb-3 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
                <Sparkles size={16} />
                <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Agenti</span>
              </div>
              <SortableTable<IncentiveTopAgent & Record<string, unknown>>
                rows={promoData.top_agents as (IncentiveTopAgent & Record<string, unknown>)[]}
                defaultSortKey="val_incentive"
                exportFilename={`focus-incentive-agenti-${promoMonth}`}
                exportSheetName="Agenti incentive"
                exportColumns={[
                  { header: '#', value: (_row, index) => index + 1 },
                  { header: 'Agent', value: (row) => row.agent_name },
                  { header: 'Firma', value: (row) => row.firma },
                  { header: 'Magazin', value: (row) => displayStoreName(row.store_name) },
                  { header: '%Prev.', value: (row) => row.achievement, format: 'percent' },
                  { header: 'Cant.', value: (row) => row.qty_sold, format: 'integer' },
                  { header: 'Val Inc.', value: (row) => row.val_incentive, format: 'currency' },
                  { header: 'Incentive potential', value: (row) => row.incentive_potential ?? 0, format: 'currency' },
                ]}
                columns={[
                  {
                    key: 'rank',
                    label: '#',
                    sortable: false,
                    render: (_row, index) => (
                      <span className="font-bold text-slate-400">{index + 1}</span>
                    ),
                  },
                  {
                    key: 'agent_name',
                    label: 'Agent',
                    render: (row) => (
                      <span className="truncate font-semibold" title={(row as unknown as IncentiveTopAgent).agent_name}>
                        {(row as unknown as IncentiveTopAgent).agent_name}
                      </span>
                    ),
                  },
                  {
                    key: 'achievement',
                    label: '%Prev.',
                    align: 'right',
                    exportValue: (row) => achievementLabel((row as unknown as IncentiveTopAgent).achievement),
                    render: (row) => (
                      <span className={achievementColor((row as unknown as IncentiveTopAgent).achievement)}>
                        {achievementLabel((row as unknown as IncentiveTopAgent).achievement)}
                      </span>
                    ),
                  },
                  {
                    key: 'qty_sold',
                    label: 'Cant.',
                    align: 'right',
                    render: (row) => (
                      <span className="text-slate-500">{formatInt((row as unknown as IncentiveTopAgent).qty_sold)}</span>
                    ),
                  },
                  {
                    key: 'val_incentive',
                    label: 'Val Inc.',
                    align: 'right',
                    render: (row) => (
                      <span className={(row as unknown as IncentiveTopAgent).val_incentive > 0 ? 'font-black text-indigo-600' : 'text-slate-400'}>
                        {(row as unknown as IncentiveTopAgent).val_incentive > 0 ? formatCurrency((row as unknown as IncentiveTopAgent).val_incentive) : '0 RON'}
                      </span>
                    ),
                  },
                  {
                    key: 'incentive_potential',
                    label: 'Incentive potential',
                    align: 'right',
                    render: (row) => (
                      <span className="font-black text-emerald-600">
                        {formatCurrency((row as unknown as IncentiveTopAgent).incentive_potential ?? 0)}
                      </span>
                    ),
                  },
                ]}
              />
            </div>
          )}

          {promoData && promoData.top_stores.length > 0 && (
            <div className="glass rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900">
              <div className="mb-3 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
                <Building2 size={16} />
                <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Magazine</span>
              </div>
              <SortableTable<PromoTopStore & Record<string, unknown>>
                rows={promoData.top_stores as (PromoTopStore & Record<string, unknown>)[]}
                defaultSortKey="incentive_value"
                exportFilename={`focus-incentive-magazine-${promoMonth}`}
                exportSheetName="Magazine incentive"
                exportColumns={[
                  { header: '#', value: (_row, index) => index + 1 },
                  { header: 'Firma', value: (row) => row.firma },
                  { header: 'Magazin', value: (row) => displayStoreName(row.store_name) },
                  { header: '%Prev.', value: (row) => row.achievement, format: 'percent' },
                  { header: 'Cant.', value: (row) => row.qty, format: 'integer' },
                  { header: 'Val Inc.', value: (row) => row.incentive_value, format: 'currency' },
                  { header: 'Incentive potential', value: (row) => row.incentive_potential ?? 0, format: 'currency' },
                ]}
                columns={[
                  {
                    key: 'rank',
                    label: '#',
                    sortable: false,
                    render: (_row, index) => (
                      <span className="font-bold text-slate-400">{index + 1}</span>
                    ),
                  },
                  {
                    key: 'store_name',
                    label: 'Magazin',
                    render: (row) => {
                      const store = row as unknown as PromoTopStore;
                      const displayName = store.store_name.includes(' - ')
                        ? store.store_name.split(' - ').slice(1).join(' - ')
                        : store.store_name;
                      return (
                        <span className="flex items-center">
                          <FirmaBadge firma={store.firma} />
                          <span className="max-w-[90px] truncate font-semibold" title={store.store_name}>
                            {displayName}
                          </span>
                        </span>
                      );
                    },
                  },
                  {
                    key: 'achievement',
                    label: '%Prev.',
                    align: 'right',
                    exportValue: (row) => achievementLabel((row as unknown as PromoTopStore).achievement),
                    render: (row) => {
                      const ach = (row as unknown as PromoTopStore).achievement;
                      return <span className={achievementColor(ach)}>{achievementLabel(ach)}</span>;
                    },
                  },
                  {
                    key: 'qty',
                    label: 'Cant.',
                    align: 'right',
                    render: (row) => (
                      <span className="text-slate-500">{formatInt((row as unknown as PromoTopStore).qty)}</span>
                    ),
                  },
                  {
                    key: 'incentive_value',
                    label: 'Val Inc.',
                    align: 'right',
                    render: (row) => {
                      const val = (row as unknown as PromoTopStore).incentive_value;
                      return (
                        <span className={val > 0 ? 'font-black text-indigo-600' : 'text-slate-400'}>
                          {val > 0 ? formatCurrency(val) : '—'}
                        </span>
                      );
                    },
                  },
                  {
                    key: 'incentive_potential',
                    label: 'Incentive potential',
                    align: 'right',
                    render: (row) => (
                      <span className="font-black text-emerald-600">
                        {formatCurrency((row as unknown as PromoTopStore).incentive_potential ?? 0)}
                      </span>
                    ),
                  },
                ]}
              />
            </div>
          )}
        </>
      ) : activeSection === 'premium' ? (
        <>
          <CampaignMonthBar title="Folii premium" icon={Sparkles} months={months} value={promoMonth} onChange={setPromoMonth} currentMonth={latestMonth} />
          <PremiumGlassFocusSection
            analysis={premiumGlass}
            surfaceMode={premiumSurfaceMode}
            onSurfaceModeChange={setPremiumSurfaceMode}
          />
        </>
      ) : (
        <>
          <div className="glass rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900">
            <div className="mb-3 flex items-center gap-2 text-amber-600 dark:text-amber-400">
              <Sparkles size={16} />
              <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Focus Products</span>
            </div>
            <div className="text-lg font-black">Indicator permanent de performanta</div>
            <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">{headline}</p>
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard icon={Tag} label="Vanzari focus" value={formatCurrency(snapshot.overview.total_focus_sales)} accent="amber" />
            <StatCard icon={PackageSearch} label="Cantitate focus" value={formatInt(snapshot.overview.total_focus_qty)} accent="indigo" />
            <StatCard icon={Sparkles} label="Share focus" value={formatPercent(snapshot.overview.focus_share_pct)} accent="emerald" />
            <StatCard icon={Building2} label="Magazine active" value={formatInt(snapshot.overview.active_focus_stores)} accent="rose" />
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold">Luna de referinta pentru istoric</h3>
                <p className="text-[11px] text-slate-500">Selector local doar pentru istoricul focus</p>
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

          {historyLoading ? (
            <LoadingCard label="Se incarca istoricul focus..." />
          ) : historyError ? (
            <ErrorCard message={historyError} onRetry={() => { void focusHistoryQuery.refetch(); }} />
          ) : !selectedHistoryPoint ? (
            <ErrorCard message="Nu exista indicatori focus pentru luna selectata." onRetry={() => { void focusHistoryQuery.refetch(); }} />
          ) : (
            <>
              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold">Istoric focus</h3>
                    <p className="text-[11px] text-slate-500">
                      Evolutia indicatorului permanent pana la {historyMonth}
                    </p>
                  </div>
                  <div className="rounded-2xl bg-slate-50 px-3 py-2 text-right dark:bg-slate-800/60">
                    <div className="text-[10px] uppercase tracking-wide text-slate-500">Luna selectata</div>
                    <div className="text-lg font-black">{selectedHistoryPoint.month}</div>
                  </div>
                </div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                    <AreaChart data={focusHistoryChart}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                      <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis yAxisId="share" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <Tooltip
                        formatter={(value: number, name: string) =>
                          name === 'Share' ? `${value.toFixed(2)}%` : formatCurrency(value)
                        }
                      />
                      <Legend />
                      <Area
                        yAxisId="sales"
                        type="monotone"
                        dataKey="sales"
                        name="Vanzari focus"
                        stroke="#d97706"
                        fill="#fbbf24"
                        fillOpacity={0.2}
                        strokeWidth={3}
                      />
                      <Line yAxisId="share" type="monotone" dataKey="share" name="Share" stroke="#4f46e5" strokeWidth={2} dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="glass rounded-3xl p-4">
                <div className="grid grid-cols-2 gap-3 text-xs lg:grid-cols-4">
                  <Metric label="Vanzari focus" value={formatCurrency(selectedHistoryPoint.total_focus_sales)} />
                  <Metric label="Cantitate focus" value={formatInt(selectedHistoryPoint.total_focus_qty)} />
                  <Metric label="Pondere in volum" value={formatPercent(selectedHistoryPoint.focus_share_pct)} />
                  <Metric label="Magazine active" value={formatInt(selectedHistoryPoint.active_focus_stores)} />
                </div>
              </div>

              <DataTable
                title="Top produse focus"
                subtitle={`Snapshot pentru luna ${promoMonth}`}
                emptyLabel="Nu exista produse focus vandute pe filtrarea selectata."
                rows={snapshot.products.map((item) => ({
                  key: item.item_code,
                  primary: item.item_name,
                  secondary: item.item_code,
                  rightTop: formatCurrency(item.sales_total),
                  rightBottom: `${formatInt(item.qty_total)} buc · ${formatInt(item.store_count)} magazine`,
                }))}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}

const PREMIUM_SURFACE_OPTIONS: Array<{ value: PremiumGlassSurfaceMode; label: string }> = [
  { value: 'all', label: 'Toate' },
  { value: 'screen', label: 'Ecran' },
  { value: 'camera', label: 'Camera' },
];

function PremiumGlassFocusSection({
  analysis,
  surfaceMode,
  onSurfaceModeChange,
}: {
  analysis: PremiumGlassAnalysis | null;
  surfaceMode: PremiumGlassSurfaceMode;
  onSurfaceModeChange: (mode: PremiumGlassSurfaceMode) => void;
}) {
  const summary = analysis?.summary;
  const modelChartData = (analysis?.models ?? []).map((model) => ({
    model: model.model_label.replace('Samsung ', 'S. '),
    Premium: model.premium_qty,
    Rest: model.regular_qty,
  }));
  const modelChartHeight = Math.max(224, modelChartData.length * 30);

  return (
    <div className="space-y-3">
      <div className="glass rounded-4xl border border-emerald-100 bg-linear-to-br from-emerald-50 via-white to-white p-4 dark:border-emerald-900/30 dark:from-emerald-950/20 dark:via-slate-900 dark:to-slate-900">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
            <Sparkles size={16} />
            <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Folii Premium</span>
          </div>
          <div className="inline-flex rounded-xl border border-emerald-200 bg-white p-1 text-[11px] font-bold shadow-xs dark:border-emerald-900/60 dark:bg-slate-900">
            {PREMIUM_SURFACE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => onSurfaceModeChange(option.value)}
                className={`rounded-lg px-3 py-1.5 transition ${
                  surfaceMode === option.value
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-500 hover:bg-emerald-50 hover:text-emerald-700 dark:text-slate-300 dark:hover:bg-emerald-950/50 dark:hover:text-emerald-200'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        <h4 className="text-base font-black tracking-tight">Ecran + camera premium</h4>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          Categoria Folii Sticla: ecran premium dupa SAPPHIRE, CERAMIC si CORNING, plus camera premium din lista operationala.
        </p>
        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Metric label="Total folii" value={formatInt(summary?.total_qty ?? 0)} />
          <Metric label="Premium" value={formatInt(summary?.premium_qty ?? 0)} />
          <Metric label="Rest modele" value={formatInt(summary?.regular_qty ?? 0)} />
          <Metric label="Share cant." value={formatPercent(summary?.premium_qty_share_pct ?? null)} />
        </div>
      </div>

      {analysis && (
        <>
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(280px,360px)]">
            <div className="glass rounded-3xl p-4">
              <div className="mb-3">
                <h3 className="text-sm font-bold">Premium vs rest pe modele</h3>
                <p className="text-[11px] text-slate-500">Modelele compatibile pe suprafata selectata</p>
              </div>
              <div className="min-w-0" style={{ height: modelChartData.length === 0 ? 224 : modelChartHeight }}>
                {modelChartData.length === 0 ? (
                  <div className="flex h-full items-center justify-center rounded-2xl bg-slate-50 text-xs font-semibold text-slate-500 dark:bg-slate-800/50">
                    Nu exista vanzari eligibile pentru filtrarea curenta.
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                    <BarChart data={modelChartData} layout="vertical" margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.15} />
                      <XAxis type="number" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis dataKey="model" type="category" width={104} tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <Tooltip formatter={(value: number) => formatInt(value)} />
                      <Legend />
                      <Bar dataKey="Premium" stackId="qty" fill="#059669" radius={[0, 6, 6, 0]} />
                      <Bar dataKey="Rest" stackId="qty" fill="#cbd5e1" radius={[0, 6, 6, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
            <PremiumGlassSurfaceBreakdown rows={analysis.surfaces ?? []} />
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <PremiumGlassModelTable rows={analysis.models} />
            <PremiumGlassManagerTable rows={analysis.managers} />
            <PremiumGlassStoreTable rows={analysis.stores} />
            <PremiumGlassAgentTable rows={analysis.agents} />
          </div>
        </>
      )}
    </div>
  );
}

function PremiumGlassSurfaceBreakdown({ rows }: { rows: PremiumGlassSurfaceStat[] }) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3">
        <h3 className="text-sm font-bold">Ecran vs camera</h3>
        <p className="text-[11px] text-slate-500">Camera vine din lista operationala cu Premium = da/nu</p>
      </div>
      <SortableTable<PremiumGlassSurfaceStat & Record<string, unknown>>
        rows={rows as (PremiumGlassSurfaceStat & Record<string, unknown>)[]}
        defaultSortKey="total_qty"
        exportFilename="focus-folii-premium-ecran-camera"
        exportSheetName="Ecran camera folii"
        columns={[
          { key: 'surface_label', label: 'Tip', render: (row) => <span className="font-semibold">{(row as PremiumGlassSurfaceStat).surface_label}</span> },
          { key: 'premium_qty', label: 'Premium', align: 'right', render: (row) => <span className="font-black text-emerald-600">{formatInt((row as PremiumGlassSurfaceStat).premium_qty)}</span> },
          { key: 'regular_qty', label: 'Rest', align: 'right', render: (row) => formatInt((row as PremiumGlassSurfaceStat).regular_qty) },
          { key: 'premium_qty_share_pct', label: 'Share', align: 'right', render: (row) => formatPercent((row as PremiumGlassSurfaceStat).premium_qty_share_pct) },
        ]}
      />
    </div>
  );
}

function PremiumGlassModelTable({ rows }: { rows: PremiumGlassModelStat[] }) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3">
        <h3 className="text-sm font-bold">Comparatie pe modele</h3>
        <p className="text-[11px] text-slate-500">Premium vs rest pentru acelasi model compatibil</p>
      </div>
      <SortableTable<PremiumGlassModelStat & Record<string, unknown>>
        rows={rows as (PremiumGlassModelStat & Record<string, unknown>)[]}
        defaultSortKey="total_qty"
        exportFilename="focus-folii-premium-modele"
        exportSheetName="Modele folii premium"
        columns={[
          { key: 'model_label', label: 'Model', render: (row) => <span className="font-semibold">{(row as PremiumGlassModelStat).model_label}</span> },
          { key: 'premium_qty', label: 'Premium', align: 'right', render: (row) => <span className="font-black text-emerald-600">{formatInt((row as PremiumGlassModelStat).premium_qty)}</span> },
          { key: 'regular_qty', label: 'Rest', align: 'right', render: (row) => formatInt((row as PremiumGlassModelStat).regular_qty) },
          { key: 'premium_qty_share_pct', label: 'Share', align: 'right', render: (row) => formatPercent((row as PremiumGlassModelStat).premium_qty_share_pct) },
        ]}
      />
    </div>
  );
}

function PremiumGlassManagerTable({ rows }: { rows: PremiumGlassManagerStat[] }) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3">
        <h3 className="text-sm font-bold">Manageri</h3>
        <p className="text-[11px] text-slate-500">Cei 6 manageri activi, dupa cantitate premium</p>
      </div>
      <SortableTable<PremiumGlassManagerStat & Record<string, unknown>>
        rows={rows as (PremiumGlassManagerStat & Record<string, unknown>)[]}
        defaultSortKey="premium_qty"
        exportFilename="focus-folii-premium-manageri"
        exportSheetName="Manageri folii premium"
        columns={[
          { key: 'manager', label: 'Manager', render: (row) => <span className="font-semibold">{(row as PremiumGlassManagerStat).manager}</span> },
          { key: 'premium_qty', label: 'Premium', align: 'right', render: (row) => <span className="font-black text-emerald-600">{formatInt((row as PremiumGlassManagerStat).premium_qty)}</span> },
          { key: 'regular_qty', label: 'Rest', align: 'right', render: (row) => formatInt((row as PremiumGlassManagerStat).regular_qty) },
          { key: 'premium_qty_share_pct', label: 'Share', align: 'right', render: (row) => formatPercent((row as PremiumGlassManagerStat).premium_qty_share_pct) },
          { key: 'store_count', label: 'Mag.', align: 'right', render: (row) => formatInt((row as PremiumGlassManagerStat).store_count) },
          { key: 'agent_count', label: 'Ag.', align: 'right', render: (row) => formatInt((row as PremiumGlassManagerStat).agent_count) },
        ]}
      />
    </div>
  );
}

function PremiumGlassStoreTable({ rows }: { rows: PremiumGlassStoreStat[] }) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3">
        <h3 className="text-sm font-bold">Magazine</h3>
        <p className="text-[11px] text-slate-500">Toate magazinele cu vanzari eligibile, dupa cantitate premium</p>
      </div>
      <SortableTable<PremiumGlassStoreStat & Record<string, unknown>>
        rows={rows as (PremiumGlassStoreStat & Record<string, unknown>)[]}
        defaultSortKey="premium_qty"
        exportFilename="focus-folii-premium-magazine"
        exportSheetName="Magazine folii premium"
        exportColumns={[
          { header: 'Firma', value: (row) => row.firma },
          { header: 'Magazin', value: (row) => row.locatie },
          { header: 'Premium', value: (row) => row.premium_qty },
          { header: 'Rest', value: (row) => row.regular_qty },
          { header: 'Share', value: (row) => formatPercent(row.premium_qty_share_pct) },
        ]}
        columns={[
          {
            key: 'locatie',
            label: 'Magazin',
            render: (row) => {
              const store = row as PremiumGlassStoreStat;
              return (
                <span className="flex items-center">
                  <FirmaBadge firma={store.firma} />
                  <span className="max-w-[110px] truncate font-semibold" title={store.locatie}>{store.locatie}</span>
                </span>
              );
            },
          },
          { key: 'premium_qty', label: 'Premium', align: 'right', render: (row) => <span className="font-black text-emerald-600">{formatInt((row as PremiumGlassStoreStat).premium_qty)}</span> },
          { key: 'regular_qty', label: 'Rest', align: 'right', render: (row) => formatInt((row as PremiumGlassStoreStat).regular_qty) },
          { key: 'premium_qty_share_pct', label: 'Share', align: 'right', render: (row) => formatPercent((row as PremiumGlassStoreStat).premium_qty_share_pct) },
        ]}
      />
    </div>
  );
}

function PremiumGlassAgentTable({ rows }: { rows: PremiumGlassAgentStat[] }) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3">
        <h3 className="text-sm font-bold">Agenti</h3>
        <p className="text-[11px] text-slate-500">Toti agentii cu vanzari eligibile, dupa cantitate premium</p>
      </div>
      <SortableTable<PremiumGlassAgentStat & Record<string, unknown>>
        rows={rows as (PremiumGlassAgentStat & Record<string, unknown>)[]}
        defaultSortKey="premium_qty"
        exportFilename="focus-folii-premium-agenti"
        exportSheetName="Agenti folii premium"
        exportColumns={[
          { header: 'Agent', value: (row) => row.agent },
          { header: 'Firma', value: (row) => row.firma },
          { header: 'Magazin', value: (row) => row.locatie },
          { header: 'Premium', value: (row) => row.premium_qty },
          { header: 'Rest', value: (row) => row.regular_qty },
          { header: 'Share', value: (row) => formatPercent(row.premium_qty_share_pct) },
        ]}
        columns={[
          {
            key: 'agent',
            label: 'Agent',
            render: (row) => {
              const agent = row as PremiumGlassAgentStat;
              return (
                <span className="block max-w-[120px] truncate font-semibold" title={`${agent.agent} - ${agent.locatie}`}>
                  {agent.agent}
                </span>
              );
            },
          },
          { key: 'premium_qty', label: 'Premium', align: 'right', render: (row) => <span className="font-black text-emerald-600">{formatInt((row as PremiumGlassAgentStat).premium_qty)}</span> },
          { key: 'regular_qty', label: 'Rest', align: 'right', render: (row) => formatInt((row as PremiumGlassAgentStat).regular_qty) },
          { key: 'premium_qty_share_pct', label: 'Share', align: 'right', render: (row) => formatPercent((row as PremiumGlassAgentStat).premium_qty_share_pct) },
        ]}
      />
    </div>
  );
}

function IncentiveCard({ promoData }: { promoData: CampaignsPromotionsResponse | null }) {
  const tiers: IncentiveCategory[] = promoData?.incentive_categories ?? [];
  const periods = promoData?.incentive_periods ?? [];

  return (
    <div className="glass rounded-4xl border border-indigo-100 p-4 dark:border-indigo-900/30">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="mb-2 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
            <Gift size={16} />
            <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Incentive</span>
          </div>
          <h4 className="text-base font-black tracking-tight">{promoData?.incentive_title || 'Incentive'}</h4>
          <p className="mt-1 max-w-3xl text-xs text-slate-500 dark:text-slate-300">
            {periods.length > 1
              ? 'Valoarea fiecarui produs este cea activa la data vanzarii. Calificarea se aplica o singura data, pe targetul lunar al magazinului.'
              : promoData?.incentive_description || 'Bonus calculat pe produs eligibil vandut.'}
          </p>
        </div>
        {promoData && promoData.incentive_product_count > 0 && (
          <div className="flex items-center gap-1 rounded-lg bg-indigo-50 px-2 py-1 text-[11px] font-bold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
            <Tag size={11} />
            {formatInt(promoData.incentive_product_count)} coduri unice
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-y border-slate-200 py-3 sm:grid-cols-4 dark:border-slate-700">
        <div><div className="text-2xl font-black">{promoData ? formatInt(promoData.incentive_qty) : '-'}</div><div className="text-[11px] text-slate-500">unitati eligibile dupa promo</div></div>
        <div><div className="text-2xl font-black text-indigo-600">{promoData ? formatCurrency(promoData.incentive_value) : '-'}</div><div className="text-[11px] text-slate-500">incentive calculat acum</div></div>
        <div><div className="text-2xl font-black text-emerald-600">{promoData ? formatCurrency(promoData.incentive_potential) : '-'}</div><div className="text-[11px] text-slate-500">potential la calificare 100%</div></div>
        <div><div className="text-2xl font-black">{promoData ? formatInt(promoData.incentive_qualified_qty) : '-'}</div><div className="text-[11px] text-slate-500">unitati in magazine calificate</div></div>
      </div>

      {periods.length > 0 && (
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {periods.map((period) => (
            <div key={`${period.start_date}-${period.end_date}`} className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700">
              <div className="flex flex-wrap items-center justify-between gap-1">
                <div><div className="text-xs font-black">{period.label}</div><div className="text-[10px] text-slate-500">{period.start_date} – {period.end_date} · {formatInt(period.product_count)} coduri</div></div>
                <div className="text-right text-xs font-black text-indigo-600">{formatCurrency(period.value)}</div>
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-slate-500">
                <span><strong className="text-slate-700 dark:text-slate-200">{formatInt(period.qty)}</strong> unitati</span>
                <span><strong className="text-slate-700 dark:text-slate-200">{formatCurrency(period.potential)}</strong> potential</span>
                <span>{period.reward_values.map((value) => `${formatInt(value)} RON`).join(' · ')}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {promoData && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px]">
          <div className="flex gap-4 text-slate-500">
            <span><strong className="text-slate-800 dark:text-slate-100">{formatInt(promoData.incentive_qualified_stores)}</strong> magazine calificate</span>
            <span><strong className="text-slate-800 dark:text-slate-100">{formatInt(promoData.incentive_qualified_agents)}</strong> agenti</span>
          </div>
          <div className="font-semibold text-slate-500">90–99,99% = 50% · minimum 100% = integral</div>
        </div>
      )}

      {tiers.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-200 pt-3 text-[10px] dark:border-slate-700">
          <span className="font-bold uppercase text-slate-400">Tier-uri vandute</span>
          {tiers.map((tier) => <span key={tier.label} className="rounded-full bg-indigo-50 px-2 py-1 font-bold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">{tier.label}: {formatInt(tier.qty)}</span>)}
        </div>
      )}
    </div>
  );
}

function IncentiveCategoryCard({ promoData, month }: { promoData: CampaignsPromotionsResponse | null; month: string }) {
  const rows: IncentiveCategoryBreakdown[] = promoData?.incentive_category_breakdown ?? [];
  if (rows.length === 0) return null;
  const maxPotential = Math.max(...rows.map((row) => row.potential), 1);

  return (
    <div className="glass rounded-4xl border border-indigo-100 p-4 dark:border-indigo-900/30">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div><div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400"><BadgePercent size={16} /><span className="text-[11px] font-bold uppercase tracking-[0.22em]">Categorii incentive</span></div><p className="mt-1 text-[11px] text-slate-500">Cantitate eligibila si valoare dupa mecanismul activ la data vanzarii.</p></div>
        <ExportTableButton filename={`focus-incentive-categorii-${month}`} sheetName="Categorii incentive" rows={rows} columns={[
          { header: 'Categorie', value: (row) => row.label },
          { header: 'Cantitate', value: (row) => row.qty, format: 'integer' },
          { header: 'Potential', value: (row) => row.potential, format: 'currency' },
          { header: 'Incentive calculat', value: (row) => row.value, format: 'currency' },
        ]} />
      </div>
      <div className="grid gap-x-6 gap-y-2 md:grid-cols-2">
        {rows.map((row) => (
          <div key={row.label} className="min-w-0">
            <div className="flex items-center gap-2 text-xs"><span className="min-w-0 flex-1 truncate font-semibold" title={row.label}>{row.label}</span><span className="font-black">{formatInt(row.qty)}</span><span className="w-20 text-right font-black text-indigo-600">{formatCurrency(row.value)}</span></div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"><div className="h-full rounded-full bg-indigo-500" style={{ width: `${Math.max(2, (row.potential / maxPotential) * 100)}%` }} /></div>
            <div className="mt-0.5 text-[10px] text-slate-400">Potential {formatCurrency(row.potential)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CampaignMonthBar({
  title,
  icon: Icon,
  months,
  value,
  onChange,
  currentMonth,
}: {
  title: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  months: string[];
  value: string;
  onChange: (month: string) => void;
  currentMonth: string;
}) {
  return (
    <div className="glass flex items-center justify-between rounded-3xl p-3">
      <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
        <Icon size={16} />
        <span className="text-[11px] font-bold uppercase tracking-[0.22em]">{title}</span>
      </div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-amber-200 bg-white px-2 py-1 text-xs font-bold text-amber-700 dark:border-amber-800 dark:bg-slate-800 dark:text-amber-300"
      >
        {months.map((m) => (
          <option key={m} value={m}>
            {m}{m === currentMonth ? ' (curent)' : ''}
          </option>
        ))}
      </select>
    </div>
  );
}

function EmptyCard({ message }: { message: string }) {
  return <div className="glass rounded-3xl p-6 text-sm font-semibold text-slate-500">{message}</div>;
}

function ContestSelector({
  contests,
  selectedKey,
  onSelect,
}: {
  contests: ContestResponse[];
  selectedKey: string;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="glass grid grid-cols-2 gap-1 rounded-2xl p-1">
      {contests.map((contest) => (
        <button
          key={contest.key}
          type="button"
          onClick={() => onSelect(contest.key)}
          className={`min-w-0 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
            selectedKey === contest.key
              ? 'bg-white text-amber-700 shadow-sm dark:bg-slate-800 dark:text-amber-300'
              : 'text-slate-500 hover:bg-white/60 dark:hover:bg-slate-800/60'
          }`}
          title={contest.scope_label || contest.title}
        >
          <span className="block truncate">{contest.scope_label || contest.title}</span>
        </button>
      ))}
    </div>
  );
}

function PromotionSelector({
  promotions,
  selectedKey,
  onSelect,
}: {
  promotions: CampaignPromotionOption[];
  selectedKey: string;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="glass grid grid-cols-1 gap-1 rounded-2xl p-1 sm:grid-cols-3">
      {promotions.map((promotion) => (
        <button
          key={promotion.key}
          type="button"
          onClick={() => onSelect(promotion.key)}
          className={`min-w-0 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
            selectedKey === promotion.key
              ? 'bg-white text-amber-700 shadow-sm dark:bg-slate-800 dark:text-amber-300'
              : 'text-slate-500 hover:bg-white/60 dark:hover:bg-slate-800/60'
          }`}
          title={promotion.label}
        >
          <span className="block truncate">{promotion.label}</span>
        </button>
      ))}
    </div>
  );
}

function ContestView({ contest }: { contest: ContestResponse }) {
  return (
    <>
      <div className="glass rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900">
        <div className="mb-2 flex items-center gap-2 text-amber-600 dark:text-amber-400">
          <Trophy size={16} />
          <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Concurs</span>
        </div>
        <h4 className="text-base font-black tracking-tight">{contest.title}</h4>
        {contest.scope_label && (
          <p className="mt-1 text-xs font-bold text-amber-700 dark:text-amber-300">{contest.scope_label}</p>
        )}
        {contest.subtitle && <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{contest.subtitle}</p>}
        <p className="mt-1 text-[11px] text-slate-400">
          {contest.start_date} – {contest.end_date} · {formatInt(contest.store_count)} magazine
        </p>
        {contest.rules.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {contest.rules.map((rule) => (
              <span
                key={rule.type}
                className="rounded-full bg-amber-100 px-2 py-1 text-[10px] font-bold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
              >
                {rule.label} = {rule.points}p
              </span>
            ))}
          </div>
        )}
      </div>

      {contest.prizes.length > 0 && (
        <div className="glass rounded-3xl p-4">
          <div className="mb-2 flex items-center gap-2 text-amber-600 dark:text-amber-400">
            <Gift size={16} />
            <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Premii</span>
          </div>
          <div className="space-y-1">
            {contest.prizes.map((prize) => (
              <div
                key={`${prize.rank_from}-${prize.rank_to}`}
                className="flex items-center justify-between rounded-xl bg-amber-50/60 px-3 py-1.5 text-xs dark:bg-amber-900/10"
              >
                <span className="font-bold text-slate-500">
                  {prize.rank_from === prize.rank_to
                    ? `Locul ${prize.rank_from}`
                    : `Locurile ${prize.rank_from}–${prize.rank_to}`}
                </span>
                <span className="font-black text-amber-700 dark:text-amber-300">{prize.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="glass rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
            <Trophy size={16} />
            <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Clasament agenti</span>
          </div>
          <ExportTableButton
            filename={`focus-concurs-${contest.month}-${contest.key}`}
            sheetName="Clasament agenti"
            rows={contest.leaderboard}
            columns={[
              { header: '#', value: (row) => row.rank },
              { header: 'Agent', value: (row) => row.agent },
              { header: 'Magazin', value: (row) => row.store_name },
              { header: 'Firma', value: (row) => row.firma },
              { header: 'Focus', value: (row) => row.focus_points },
              { header: 'Promo', value: (row) => row.promo_points },
              { header: '>150', value: (row) => row.price_points },
              { header: 'Total', value: (row) => row.total_points },
              { header: 'Premiu', value: (row) => row.prize },
            ]}
          />
        </div>
        {contest.leaderboard.length === 0 ? (
          <div className="rounded-2xl bg-slate-50 p-4 text-xs font-semibold text-slate-500 dark:bg-slate-800/60">
            Nu exista inca vanzari punctate in {contest.month}.
          </div>
        ) : (
          <div
            className="max-h-[480px] overflow-y-auto rounded-xl"
            style={{ scrollbarWidth: 'thin', scrollbarColor: '#c7d2fe transparent' }}
          >
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr>
                  {['#', 'Agent', 'Focus', 'Promo', '>150', 'Total', 'Premiu'].map((label, index) => (
                    <th
                      key={label}
                      className={`sticky top-0 z-10 bg-indigo-50/80 px-2 py-2 text-[9px] font-bold uppercase tracking-wide text-slate-500 backdrop-blur-sm dark:bg-indigo-950/60 ${
                        index >= 2 && index <= 5 ? 'text-right' : 'text-left'
                      }`}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {contest.leaderboard.map((row) => (
                  <tr
                    key={row.agent}
                    className={
                      row.prize
                        ? 'bg-amber-50/50 dark:bg-amber-900/10'
                        : row.rank % 2 === 0
                          ? 'bg-indigo-50/30 dark:bg-indigo-900/10'
                          : ''
                    }
                  >
                    <td className="px-2 py-1.5">
                      <span className={`font-bold ${row.rank <= 3 ? 'text-amber-500' : 'text-slate-400'}`}>{row.rank}</span>
                    </td>
                    <td className="px-2 py-1.5">
                      <span className="truncate font-semibold" title={row.agent}>{row.agent}</span>
                    </td>
                    <td className="px-2 py-1.5 text-right text-slate-500">{formatInt(row.focus_points)}</td>
                    <td className="px-2 py-1.5 text-right text-slate-500">{formatInt(row.promo_points)}</td>
                    <td className="px-2 py-1.5 text-right text-slate-500">{formatInt(row.price_points)}</td>
                    <td className="px-2 py-1.5 text-right font-black text-indigo-600">{formatInt(row.total_points)}</td>
                    <td className="px-2 py-1.5">
                      {row.prize ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                          <Medal size={11} />
                          {row.prize}
                        </span>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: string;
  accent: 'amber' | 'indigo' | 'emerald' | 'rose';
}) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className={`mb-3 flex h-10 w-10 items-center justify-center rounded-2xl ${STAT_ACCENT_CLASSES[accent]}`}>
        <Icon size={18} />
      </div>
      <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-black">{value}</div>
    </div>
  );
}

function DataTable({
  title,
  subtitle,
  emptyLabel,
  rows,
}: {
  title: string;
  subtitle: string;
  emptyLabel: string;
  rows: Array<{
    key: string;
    primary: string;
    secondary: string;
    rightTop: string;
    rightBottom: string;
  }>;
}) {
  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold">{title}</h3>
          <p className="text-[11px] text-slate-500">{subtitle}</p>
        </div>
        <ExportTableButton
          filename={title}
          sheetName={title}
          rows={rows}
          columns={[
            { header: 'Denumire', value: (row) => row.primary },
            { header: 'Cod', value: (row) => row.secondary },
            { header: 'Valoare', value: (row) => row.rightTop },
            { header: 'Detalii', value: (row) => row.rightBottom },
          ]}
        />
      </div>
      <div className="space-y-2">
        {rows.map((row) => (
          <div key={row.key} className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-bold">{row.primary}</div>
                <div className="text-[11px] text-slate-500">{row.secondary}</div>
              </div>
              <div className="text-right">
                <div className="text-sm font-black text-amber-600 dark:text-amber-400">{row.rightTop}</div>
                <div className="text-[11px] text-slate-500">{row.rightBottom}</div>
              </div>
            </div>
          </div>
        ))}
        {rows.length === 0 && (
          <div className="rounded-2xl bg-slate-50 p-4 text-xs font-semibold text-slate-500 dark:bg-slate-800/60">
            {emptyLabel}
          </div>
        )}
      </div>
    </div>
  );
}

interface ColDef<T> {
  key: keyof T | 'rank';
  label: string;
  align?: 'left' | 'right';
  sortable?: boolean;
  exportValue?: (row: T, index: number) => string | number | null | undefined;
  render: (row: T, index: number) => React.ReactNode;
}

function SortableTable<T extends Record<string, unknown>>({
  rows,
  columns,
  defaultSortKey,
  defaultSortDir = 'desc',
  maxHeightClass = 'max-h-[360px]',
  exportFilename,
  exportSheetName,
  exportColumns,
}: {
  rows: T[];
  columns: ColDef<T>[];
  defaultSortKey: keyof T;
  defaultSortDir?: SortDirection;
  maxHeightClass?: string;
  exportFilename: string;
  exportSheetName: string;
  exportColumns?: ExportColumn<T>[];
}) {
  const {
    sorted,
    sortKey,
    direction: sortDir,
    handleSort: handleSortableSort,
  } = useSortable<T, keyof T>({
    rows,
    key: defaultSortKey,
    direction: defaultSortDir,
  });

  function handleSort(key: keyof T | 'rank') {
    if (key === 'rank') return;
    handleSortableSort(key as keyof T);
  }

  return (
    <div>
      <div className="mb-2 flex justify-end">
        <ExportTableButton<T>
          filename={exportFilename}
          sheetName={exportSheetName}
          rows={sorted}
          columns={exportColumns ?? columns.map((column): ExportColumn<T> => ({
            header: column.label,
            value: (row, index): string | number | null | undefined => {
              if (column.exportValue) return column.exportValue(row, index);
              if (column.key === 'rank') return index + 1;
              const value: unknown = row[column.key as keyof T];
              if (value === null || value === undefined) return null;
              if (typeof value === 'string' || typeof value === 'number') return value;
              return String(value);
            },
          }))}
        />
      </div>
      <div
        className={`${maxHeightClass} overflow-auto rounded-xl`}
        style={{ scrollbarWidth: 'thin', scrollbarColor: '#c7d2fe transparent' }}
      >
        <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={String(col.key)}
                onClick={() => handleSort(col.key)}
                className={`sticky top-0 z-10 bg-indigo-50/80 px-2 py-2 text-[9px] font-bold uppercase tracking-wide text-slate-500 backdrop-blur-sm dark:bg-indigo-950/60 ${
                  col.align === 'right' ? 'text-right' : 'text-left'
                } ${col.sortable !== false && col.key !== 'rank' ? 'cursor-pointer select-none hover:text-indigo-600' : ''}`}
              >
                {col.label}
                {col.sortable !== false && col.key !== 'rank' && (
                  <span className="ml-1 inline-block w-2 text-center">
                    {sortKey === col.key ? (sortDir === 'asc' ? '▲' : '▼') : '⇅'}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, index) => (
            <tr
              key={index}
              className={index % 2 === 0 ? 'bg-indigo-50/30 dark:bg-indigo-900/10' : ''}
            >
              {columns.map((col) => (
                <td
                  key={String(col.key)}
                  className={`px-2 py-1.5 ${col.align === 'right' ? 'text-right' : 'text-left'}`}
                >
                  {col.render(row, index)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        </table>
      </div>
    </div>
  );
}

function achievementColor(ach: number | null): string {
  if (ach === null || ach === undefined) return 'text-slate-400';
  if (ach >= 1) return 'text-emerald-600 font-black';
  if (ach >= 0.9) return 'text-amber-500 font-semibold';
  return 'text-red-500';
}

function achievementLabel(ach: number | null): string {
  if (ach === null || ach === undefined) return '—';
  return `${Math.round(ach * 100)}%`;
}
