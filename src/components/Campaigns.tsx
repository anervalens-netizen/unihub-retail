import React, { type ComponentType, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  BadgePercent,
  Building2,
  Gift,
  PackageSearch,
  RefreshCw,
  Sparkles,
  Tag,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getCampaignSnapshot, getFocusHistory, getPromotionsIncentives } from '../api/campaigns';
import type { CampaignSnapshot, CampaignsPromotionsResponse, FocusHistoryPoint, IncentiveCategory, IncentiveTopAgent, PromoTopStore } from '../api/types';
import { buildScopedMonthQuery } from '../lib/filterQueries';
import { formatCurrency, formatInt, formatPercent } from '../lib/formatters';
import { getCachedView, setCachedView } from '../lib/viewCache';
import type { AppFilters } from './MainLayout';

interface CampaignsProps {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
  preferredSection: 'campaigns' | 'focus';
  onSectionChange: (section: 'campaigns' | 'focus') => void;
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
const CAMPAIGNS_CACHE_TTL_MS = 3 * 60 * 1000;

const STAT_ACCENT_CLASSES: Record<string, string> = {
  amber: 'bg-amber-50 text-amber-600 dark:bg-amber-900/20',
  indigo: 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20',
  emerald: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20',
  rose: 'bg-rose-50 text-rose-600 dark:bg-rose-900/20',
};

export function Campaigns({
  currentMonth,
  months,
  filters,
  preferredSection,
  onSectionChange,
}: CampaignsProps) {
  const [activeSection, setActiveSection] = useState<'campaigns' | 'focus'>(preferredSection);
  const [historyMonth, setHistoryMonth] = useState(currentMonth);
  const [promoMonth, setPromoMonth] = useState(currentMonth);
  const [snapshot, setSnapshot] = useState<CampaignSnapshot>(emptySnapshot);
  const [focusHistory, setFocusHistory] = useState<FocusHistoryPoint[]>([]);
  const [promoData, setPromoData] = useState<CampaignsPromotionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const isMountedRef = useRef(true);

  useEffect(() => {
    setHistoryMonth((previous) => (months.includes(previous) ? previous : currentMonth));
    setPromoMonth((previous) => (months.includes(previous) ? previous : currentMonth));
  }, [months, currentMonth]);

  useEffect(() => {
    setActiveSection(preferredSection);
  }, [preferredSection]);

  useEffect(() => {
    onSectionChange(activeSection);
  }, [activeSection, onSectionChange]);

  const buildQuery = useCallback(
    (month: string) => buildScopedMonthQuery(month, filters),
    [filters]
  );

  const currentCacheKey = useMemo(
    () => `campaigns:current:${promoMonth}:${JSON.stringify(buildQuery(promoMonth))}`,
    [buildQuery, promoMonth]
  );
  const historyCacheKey = useMemo(
    () => `campaigns:history:${historyMonth}:${JSON.stringify({ ...buildQuery(historyMonth), months_back: 12 })}`,
    [buildQuery, historyMonth]
  );

  const loadCurrentFocus = useCallback(() => {
    if (!isMountedRef.current) return;
    const cached = getCachedView<{
      snapshot: CampaignSnapshot;
      promoData: CampaignsPromotionsResponse | null;
    }>(currentCacheKey, CAMPAIGNS_CACHE_TTL_MS);
    if (cached.value) {
      setSnapshot(cached.value.snapshot);
      setPromoData(cached.value.promoData);
      setLoading(false);
      setError('');
      if (cached.isFresh) {
        return;
      }
    }

    setLoading(true);
    setError('');
    Promise.all([
      getCampaignSnapshot(buildQuery(promoMonth)),
      getPromotionsIncentives(`${promoMonth}-01`, (() => { const [yr, mo] = promoMonth.split('-').map(Number); return `${promoMonth}-${String(new Date(yr, mo, 0).getDate()).padStart(2, '0')}`; })(), buildQuery(promoMonth)),
    ])
      .then(([snapshotData, promoResponse]) => {
        if (!isMountedRef.current) return;
        setSnapshot(snapshotData);
        setPromoData(promoResponse);
        setCachedView(currentCacheKey, {
          snapshot: snapshotData,
          promoData: promoResponse,
        });
      })
      .catch(() => {
        if (!isMountedRef.current) return;
        setSnapshot(emptySnapshot);
        setPromoData(null);
        setError('Datele pentru campanii si focus nu au putut fi incarcate.');
      })
      .finally(() => {
        if (isMountedRef.current) setLoading(false);
      });
  }, [buildQuery, currentCacheKey, promoMonth, filters]);

  const loadFocusHistory = useCallback(() => {
    if (!isMountedRef.current) return;
    const cached = getCachedView<FocusHistoryPoint[]>(historyCacheKey, CAMPAIGNS_CACHE_TTL_MS);
    if (cached.value) {
      setFocusHistory(cached.value);
      setHistoryError(cached.value.length === 0 ? 'Nu exista istoric focus pentru filtrarea curenta.' : '');
      setHistoryLoading(false);
      if (cached.isFresh) {
        return;
      }
    }

    setHistoryLoading(true);
    setHistoryError('');
    getFocusHistory({ ...buildQuery(historyMonth), months_back: 12 })
      .then((data) => {
        if (!isMountedRef.current) return;
        setFocusHistory(data.history);
        setCachedView(historyCacheKey, data.history);
        if (data.history.length === 0) {
          setHistoryError('Nu exista istoric focus pentru filtrarea curenta.');
        }
      })
      .catch(() => {
        if (!isMountedRef.current) return;
        setFocusHistory([]);
        setHistoryError('Istoricul focus nu a putut fi incarcat.');
      })
      .finally(() => {
        if (isMountedRef.current) setHistoryLoading(false);
      });
  }, [buildQuery, historyCacheKey, historyMonth]);

  useEffect(() => {
    isMountedRef.current = true;
    loadCurrentFocus();
    return () => {
      isMountedRef.current = false;
    };
  }, [loadCurrentFocus]);

  useEffect(() => {
    setFocusHistory([]);
    setHistoryError('');
    if (activeSection === 'focus') {
      loadFocusHistory();
    }
  }, [activeSection, historyMonth, loadFocusHistory]);

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

  const headline = useMemo(() => {
    if (snapshot.products.length === 0) {
      return `Nu exista inca focus products vandute in ${promoMonth} pentru filtrarea selectata.`;
    }
    const leader = snapshot.products[0];
    return `${leader.item_name} conduce ${promoMonth} cu ${formatInt(leader.qty_total)} bucati si ${formatCurrency(leader.sales_total)}.`;
  }, [snapshot.products, promoMonth]);

  return (
    <div className="mx-auto max-w-6xl space-y-3 p-3 pb-24 pt-2">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Focus</h1>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Campaniile folosesc luna {promoMonth}, iar istoricul focus se analizeaza separat.
        </p>
      </div>

      <div className="glass flex rounded-2xl p-1">
        <button
          onClick={() => setActiveSection('campaigns')}
          className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
            activeSection === 'campaigns'
              ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
              : 'text-slate-500'
          }`}
        >
          Campanii
        </button>
        <button
          onClick={() => setActiveSection('focus')}
          className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
            activeSection === 'focus'
              ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
              : 'text-slate-500'
          }`}
        >
          Focus
        </button>
      </div>

      {loading ? (
        <LoadingCard label="Se incarca datele de focus..." />
      ) : error ? (
        <ErrorCard message={error} onRetry={loadCurrentFocus} />
      ) : activeSection === 'campaigns' ? (
        <>
          <div className="glass rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
                <Sparkles size={16} />
                <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Campanii</span>
              </div>
              <select
                value={promoMonth}
                onChange={(e) => setPromoMonth(e.target.value)}
                className="rounded-lg border border-amber-200 bg-white px-2 py-1 text-xs font-bold text-amber-700 dark:border-amber-800 dark:bg-slate-800 dark:text-amber-300"
              >
                {months.map((m) => (
                  <option key={m} value={m}>
                    {m}{m === currentMonth ? ' (curent)' : ''}
                  </option>
                ))}
              </select>
            </div>
            <div className="text-lg font-black">Promotii si incentive</div>
            <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
              {promoData && promoData.promo_qty > 0
                ? `${promoData.promo_qty} promotie activ${promoData.promo_qty === 1 ? 'a' : 'i'} in curs`
                : `Nu exista promotii active in ${promoMonth}.`}
            </p>
          </div>

          {/* Card Promotii — ascuns daca nu exista promotie activa */}
          {promoData?.has_active_promotion && (
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
                <div className="text-3xl font-black">{formatInt(promoData.promo_qty)}</div>
                <div className="text-[11px] text-slate-500">bucati vandute</div>
              </div>

              {promoData.promo_total_qty > 0 && (
                <div className="mb-3">
                  <div className="mb-1 flex justify-between text-[10px] text-slate-500">
                    <span>Progres</span>
                    <span>{formatInt(promoData.promo_qty)} / {formatInt(promoData.promo_total_qty)}</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-slate-200 dark:bg-slate-700">
                    <div
                      className="h-2 rounded-full bg-amber-500"
                      style={{ width: `${Math.min((promoData.promo_qty / promoData.promo_total_qty) * 100, 100)}%` }}
                    />
                  </div>
                </div>
              )}

              {promoData.promo_impact > 0 && (
                <div className="mb-3 text-sm">
                  <span className="text-slate-500">Impact: </span>
                  <span className="font-black text-amber-600">{formatCurrency(promoData.promo_impact)}</span>
                  <span className="text-[10px] text-slate-400"> (20% din vanzari)</span>
                </div>
              )}
            </div>
          )}

          {/* Card Magazine — doar cand exista promotie activa (combina promo + incentive) */}
          {promoData && promoData.has_active_promotion && promoData.top_stores.length > 0 && (
            <div className="glass rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900">
              <div className="mb-3 flex items-center gap-2 text-amber-600 dark:text-amber-400">
                <Building2 size={16} />
                <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Top Magazine</span>
              </div>
              <div className="space-y-1">
                <div className="grid grid-cols-12 gap-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                  <div className="col-span-1">#</div>
                  <div className={promoData.has_active_promotion ? 'col-span-4' : 'col-span-6'}>Magazin</div>
                  <div className="col-span-2 text-right">Target%</div>
                  {promoData.has_active_promotion && <div className="col-span-2 text-right">Promo</div>}
                  <div className="col-span-3 text-right">Incentive</div>
                </div>
                {promoData.top_stores.slice(0, 10).map((store, index) => {
                  const ach = store.achievement;
                  const achPct = ach !== null && ach !== undefined ? Math.round(ach * 100) : null;
                  const achColor = ach === null || ach === undefined
                    ? 'text-slate-400'
                    : ach >= 0.99 ? 'text-emerald-600 font-black'
                    : ach >= 0.89 ? 'text-amber-500 font-semibold'
                    : 'text-red-500';
                  return (
                    <div
                      key={store.store_name}
                      className={`grid grid-cols-12 gap-1 rounded-xl p-2 text-xs ${index % 2 === 0 ? 'bg-amber-50/50 dark:bg-amber-900/10' : ''}`}
                    >
                      <div className="col-span-1 font-bold text-slate-400">{index + 1}</div>
                      <div className={`truncate font-semibold ${promoData.has_active_promotion ? 'col-span-4' : 'col-span-6'}`}>{store.store_name}</div>
                      <div className={`col-span-2 text-right ${achColor}`}>
                        {achPct !== null ? `${achPct}%` : '-'}
                      </div>
                      {promoData.has_active_promotion && (
                        <div className="col-span-2 text-right font-black text-amber-600">{formatInt(store.qty)}</div>
                      )}
                      <div className="col-span-3 text-right font-black text-indigo-600">{store.incentive_value > 0 ? formatCurrency(store.incentive_value) : '-'}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Card Incentive — stats + pie chart */}
          <IncentiveCard promoData={promoData} />

          {/* Top Agenti — card separat, sortabil, scroll */}
          {promoData && promoData.top_agents.length > 0 && (
            <div className="glass rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900">
              <div className="mb-3 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
                <Sparkles size={16} />
                <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Top Agenti</span>
              </div>
              <SortableTable<IncentiveTopAgent & Record<string, unknown>>
                rows={promoData.top_agents as (IncentiveTopAgent & Record<string, unknown>)[]}
                defaultSortKey="val_incentive"
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
                ]}
              />
            </div>
          )}

          {/* Top Magazine Incentive — card separat, sortabil, scroll, doar fara promotie activa */}
          {promoData && !promoData.has_active_promotion && promoData.top_stores.length > 0 && (
            <div className="glass rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900">
              <div className="mb-3 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
                <Building2 size={16} />
                <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Top Magazine</span>
              </div>
              <SortableTable<PromoTopStore & Record<string, unknown>>
                rows={promoData.top_stores as (PromoTopStore & Record<string, unknown>)[]}
                defaultSortKey="incentive_value"
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
                ]}
              />
            </div>
          )}
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
            <ErrorCard message={historyError} onRetry={loadFocusHistory} />
          ) : !selectedHistoryPoint ? (
            <ErrorCard message="Nu exista indicatori focus pentru luna selectata." onRetry={loadFocusHistory} />
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
                subtitle={`Snapshot pentru luna curenta ${currentMonth}`}
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

const INCENTIVE_TIER_COLORS = ['#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#ddd6fe'];

function IncentiveCard({ promoData }: { promoData: CampaignsPromotionsResponse | null }) {
  const categories: IncentiveCategory[] = promoData?.incentive_categories ?? [];
  const pieData = categories.map((cat) => ({ name: cat.label, value: cat.qty }));
  const totalQty = categories.reduce((sum, c) => sum + c.qty, 0);

  return (
    <div className="glass rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
        <Gift size={16} />
        <span className="text-[11px] font-bold uppercase tracking-[0.22em]">Incentive</span>
      </div>
      <div className="mb-1">
        <h4 className="text-base font-black tracking-tight">{promoData?.incentive_title || 'Incentive'}</h4>
        {promoData?.incentive_description && (
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{promoData.incentive_description}</p>
        )}
        {promoData && promoData.incentive_product_count > 0 && (
          <div className="mt-1 flex items-center gap-1 text-[11px] text-slate-400">
            <Tag size={11} />
            <span>{promoData.incentive_product_count} coduri eligibile</span>
          </div>
        )}
      </div>

      {/* Stats principale */}
      <div className="mb-4 grid grid-cols-2 gap-3">
        <div>
          <div className="text-3xl font-black">{promoData ? formatInt(promoData.incentive_qty) : '-'}</div>
          <div className="text-[11px] text-slate-500">bucati vandute</div>
        </div>
        <div>
          <div className="text-3xl font-black text-indigo-600">
            {promoData ? formatCurrency(promoData.incentive_value) : '-'}
          </div>
          <div className="text-[11px] text-slate-500">valoare incentive</div>
        </div>
      </div>

      {/* Pie chart pe tiere de reward */}
      {pieData.length > 0 && (
        <div className="mb-4 border-t border-indigo-100 pt-3 dark:border-indigo-900/30">
          <h5 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-slate-500">Distributie pe tier</h5>
          <div className="flex items-center gap-4">
            <div className="h-[120px] w-[120px] shrink-0">
              <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={32}
                    outerRadius={52}
                    dataKey="value"
                    stroke="none"
                  >
                    {pieData.map((_, index) => (
                      <Cell key={index} fill={INCENTIVE_TIER_COLORS[index % INCENTIVE_TIER_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number, name: string) => [
                      `${formatInt(value)} buc (${totalQty > 0 ? Math.round((value / totalQty) * 100) : 0}%)`,
                      name,
                    ]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              {categories.map((cat, index) => (
                <div key={cat.label} className="flex items-center gap-2 text-xs">
                  <div
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: INCENTIVE_TIER_COLORS[index % INCENTIVE_TIER_COLORS.length] }}
                  />
                  <span className="min-w-0 flex-1 truncate font-semibold">{cat.label}</span>
                  <span className="shrink-0 font-black text-indigo-600">{formatInt(cat.qty)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

    </div>
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

function Metric({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
      <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-bold">{value ?? '-'}</div>
    </div>
  );
}

function LoadingCard({ label }: { label: string }) {
  return <div className="glass rounded-3xl p-6 text-sm font-semibold text-slate-500">{label}</div>;
}

function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="glass flex flex-col items-center gap-4 rounded-3xl p-6">
      <div className="flex items-center gap-2 text-rose-600 dark:text-rose-300">
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
      <div className="mb-3">
        <h3 className="text-sm font-bold">{title}</h3>
        <p className="text-[11px] text-slate-500">{subtitle}</p>
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

type SortDir = 'asc' | 'desc';

interface ColDef<T> {
  key: keyof T | 'rank';
  label: string;
  align?: 'left' | 'right';
  sortable?: boolean;
  render: (row: T, index: number) => React.ReactNode;
}

function SortableTable<T extends Record<string, unknown>>({
  rows,
  columns,
  defaultSortKey,
  defaultSortDir = 'desc',
  maxHeightClass = 'max-h-[360px]',
}: {
  rows: T[];
  columns: ColDef<T>[];
  defaultSortKey: keyof T;
  defaultSortDir?: SortDir;
  maxHeightClass?: string;
}) {
  const [sortKey, setSortKey] = useState<keyof T>(defaultSortKey);
  const [sortDir, setSortDir] = useState<SortDir>(defaultSortDir);

  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sortKey);
    if (!col || col.key === 'rank') return rows;
    return [...rows].sort((a, b) => {
      const av = a[sortKey as keyof T];
      const bv = b[sortKey as keyof T];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [rows, columns, sortKey, sortDir]);

  function handleSort(key: keyof T | 'rank') {
    if (key === 'rank') return;
    const k = key as keyof T;
    if (k === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(k);
      setSortDir('desc');
    }
  }

  return (
    <div
      className={`${maxHeightClass} overflow-y-auto rounded-xl`}
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
  );
}

function achievementColor(ach: number | null): string {
  if (ach === null || ach === undefined) return 'text-slate-400';
  if (ach >= 0.99) return 'text-emerald-600 font-black';
  if (ach >= 0.89) return 'text-amber-500 font-semibold';
  return 'text-red-500';
}

function achievementLabel(ach: number | null): string {
  if (ach === null || ach === undefined) return '—';
  return `${Math.round(ach * 100)}%`;
}

function FirmaBadge({ firma }: { firma: string }) {
  const lower = firma.toLowerCase();
  const color = lower.includes('mobicell') ? '#3b82f6'
              : lower.includes('mobiup')   ? '#ef4444'
              : '#9ca3af';
  return (
    <span
      title={firma}
      style={{ background: color }}
      className="mr-1 inline-flex h-[14px] w-[14px] flex-shrink-0 items-center justify-center rounded-[3px] text-[8px] font-black text-white"
    >
      M
    </span>
  );
}
