import { useState, type RefObject } from 'react';
import { Building2, CalendarRange, ChevronDown, MapPin, PieChart as PieChartIcon, TrendingUp } from 'lucide-react';
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

import type { AgentStat, DashboardSummary, RegionalStat, StoreStat } from '../../api/types';
import { MAX_DASHBOARD_BATCH_MONTHS } from '../../api/dashboard';
import { formatAmount, formatInt, formatPercent } from '../../lib/formatters';
import { BreakdownTable, type BreakdownColumn } from './BreakdownTable';
import {
  CompactCurrency,
  CompactPieSection,
  ErrorCard,
  KpiPerformanceCard,
  LoadingCard,
  Metric,
  formatCompactDonutValue,
  getBon2AccTone,
  getFocusTone,
  sumChartValues,
} from './DashboardWidgets';
import { SegmentedTabs } from '../common/SegmentedTabs';

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

interface CurrentHistoryChartPoint {
  month: string;
  sales: number;
  target: number;
  progress: number;
  isForecast: boolean;
}

interface YearHistoryChartPoint {
  label: string;
  sales: number;
  target: number;
  progress: number;
  isAggregate: boolean;
}

interface KpiChartPoint {
  month: string;
  value: number;
}

interface HistoryDailyChartPoint {
  day: string;
  sales: number;
  qty: number;
  receipts: number;
}

interface ReceiptBucketChartPoint extends Record<string, string | number> {
  bucket: string;
  receipt_count: number;
  share_pct: number;
}

interface FocusChartPoint extends Record<string, string | number> {
  category: string;
  quantity_total: number;
  share_pct: number;
}

interface CategoryMixChartPoint extends Record<string, string | number> {
  category: string;
  sales_total: number;
  quantity_total: number;
  share_pct: number;
}

interface BrandMixChartPoint extends Record<string, string | number> {
  brand: string;
  sales_total: number;
  share_pct: number;
}

interface SortState<Key extends string> {
  key: Key;
  direction: 'asc' | 'desc';
}

interface HistoryDashboardProps<RegionalKey extends string, StoreKey extends string, AgentKey extends string> {
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

export function HistoryDashboard<RegionalKey extends string, StoreKey extends string, AgentKey extends string>({
  loading,
  error,
  onRetry,
  selectedPoint,
  currentSummary,
  historySummary,
  yearFilter,
  onYearFilterChange,
  availableYears,
  currentHistoryLoading,
  yearHistoryLoading,
  currentHistoryChartData,
  yearHistoryChartData,
  kpiMetric,
  onKpiMetricChange,
  kpiChartData,
  includeClosedStores,
  onIncludeClosedStoresChange,
  dropdownRef,
  onDropdownToggle,
  dropdownOpen,
  draftSelectionLabel,
  selectionLabel,
  months,
  draftSelectedMonths,
  onToggleMonth,
  onApplyMonths,
  onApplyPreset,
  historyStatusLabel,
  historyReceiptBucketChartData,
  historyFocusSubcategoryChartData,
  historyDailyChartData,
  historyCategoryMixChartData,
  historyBrandMixChartData,
  selectionSlug,
  regionals,
  sortedRegionals,
  regionalColumns,
  regionalSort,
  onSortRegionals,
  stores,
  sortedStores,
  storeColumns,
  storeSort,
  onSortStores,
  agents,
  sortedAgents,
  agentColumns,
  agentSort,
  onSortAgents,
}: HistoryDashboardProps<RegionalKey, StoreKey, AgentKey>) {
  const [mobileSection, setMobileSection] = useState<'summary' | 'trend' | 'details'>('summary');
  if (loading) return <LoadingCard label="Se incarca istoricul..." />;
  if (error) return <ErrorCard message={error} onRetry={onRetry} />;
  if (!selectedPoint) return <ErrorCard message="Nu exista valori istorice pentru luna selectata." onRetry={onRetry} />;

  return (
    <>
      <SegmentedTabs<'summary' | 'trend' | 'details'>
        ariaLabel="Conținut istoric mobil"
        className="glass lg:hidden"
        options={[
          { value: 'summary', label: 'Sumar' },
          { value: 'trend', label: 'Trend' },
          { value: 'details', label: 'Detalii' },
        ]}
        value={mobileSection}
        onChange={setMobileSection}
      />

      <div className={`glass rounded-3xl p-4 ${mobileSection !== 'trend' ? 'hidden lg:block' : ''}`}>
        <div className="mb-3 flex items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-bold">Evolutie lunara</h3>
            <p className="text-[11px] text-slate-500">
              {yearFilter === null
                ? `Ultimele 13 luni finalizate${!currentSummary.is_month_final ? ' + previziune luna in curs' : ''}`
                : `Toate lunile disponibile — ${yearFilter}`}
            </p>
          </div>
          <select
            value={yearFilter ?? ''}
            onChange={(event) => onYearFilterChange(event.target.value === '' ? null : parseInt(event.target.value))}
            className="rounded-xl border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
          >
            <option value="">Standard</option>
            {availableYears.map((year) => <option key={year} value={year}>{year}</option>)}
          </select>
        </div>
        {(yearFilter === null ? currentHistoryLoading : yearHistoryLoading) ? (
          <div className="flex h-64 items-center justify-center text-xs text-slate-400">Se incarca...</div>
        ) : yearFilter === null ? (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
              <ComposedChart data={currentHistoryChartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="progress" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(value: number, name: string) => (name === '% target' ? `${value.toFixed(2)}%` : formatAmount(value))} />
                <Legend />
                <Bar yAxisId="sales" dataKey="sales" name="Vanzari" radius={[8, 8, 0, 0]}>
                  {currentHistoryChartData.map((entry, index) => <Cell key={index} fill={entry.isForecast ? '#a78bfa' : '#4f46e5'} />)}
                </Bar>
                <Line yAxisId="sales" type="monotone" dataKey="target" name="Target" stroke="#10b981" strokeWidth={2} dot={false} />
                <Line yAxisId="progress" type="monotone" dataKey="progress" name="% target" stroke="#f59e0b" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : yearHistoryChartData.length === 0 ? (
          <div className="flex h-64 items-center justify-center text-xs text-slate-400">Nu exista date pentru {yearFilter} cu filtrele curente.</div>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
              <ComposedChart data={yearHistoryChartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="progress" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(value: number, name: string) => (name === '% target' ? `${value.toFixed(2)}%` : formatAmount(value))} />
                <Legend />
                <Bar yAxisId="sales" dataKey="sales" name="Vanzari" radius={[8, 8, 0, 0]}>
                  {yearHistoryChartData.map((entry, index) => <Cell key={index} fill={entry.isAggregate ? '#818cf8' : '#4f46e5'} />)}
                </Bar>
                {yearHistoryChartData.some((point) => point.target > 0) && <Line yAxisId="sales" type="monotone" dataKey="target" name="Target" stroke="#10b981" strokeWidth={2} dot={false} />}
                {yearHistoryChartData.some((point) => point.progress > 0) && <Line yAxisId="progress" type="monotone" dataKey="progress" name="% target" stroke="#f59e0b" strokeWidth={2} dot={false} />}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className={`glass rounded-3xl p-4 ${mobileSection !== 'trend' ? 'hidden lg:block' : ''}`}>
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2"><TrendingUp size={16} className="text-indigo-500" /><h3 className="text-sm font-bold">Trend KPI</h3></div>
          <div className="flex gap-1">
            {([
              { key: 'proc_bon2acc', label: 'Bon2Acc' },
              { key: 'prc_focus_acc_qty', label: 'Focus' },
              { key: 'total_receipts', label: 'Bonuri' },
            ] as const).map(({ key, label }) => (
              <button
                key={key}
                onClick={() => onKpiMetricChange(key)}
                className={`rounded-full px-2.5 py-1 text-[10px] font-bold transition-colors ${kpiMetric === key ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400'}`}
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
                <defs><linearGradient id="kpiTrendArea" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#4f46e5" stopOpacity={0.35} /><stop offset="95%" stopColor="#4f46e5" stopOpacity={0.03} /></linearGradient></defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(value: number) => kpiMetric === 'total_receipts' ? formatInt(value) : `${value.toFixed(1)}%`} />
                <Area type="monotone" dataKey="value" name={kpiMetric === 'proc_bon2acc' ? 'ProcBon2Acc' : kpiMetric === 'prc_focus_acc_qty' ? 'PrcFocus/AccQtty' : 'Total bonuri'} stroke="#4f46e5" fill="url(#kpiTrendArea)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className={`glass relative z-50 rounded-3xl p-4 ${mobileSection !== 'summary' ? 'hidden lg:block' : ''}`}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold">Luni analizate</h3>
            <p className="text-[11px] text-slate-500">Alege un interval rapid sau bifează lunile; rezultatele se agregă automat.</p>
            <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Intervale rapide">
              {[3, 6, 12].map((count) => (
                <button
                  key={count}
                  type="button"
                  onClick={() => onApplyPreset?.(count)}
                  className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:border-indigo-300 hover:text-indigo-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                >
                  Ultimele {count} luni
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap items-start gap-2">
            <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
              <input type="checkbox" checked={includeClosedStores} onChange={(event) => onIncludeClosedStoresChange(event.target.checked)} className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
              Include magazine inchise
            </label>
            <details ref={dropdownRef} onToggle={onDropdownToggle} className="group relative z-50">
              <summary className="flex min-w-60 cursor-pointer list-none items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold outline-none transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700">
                <span className="truncate">{dropdownOpen ? draftSelectionLabel : selectionLabel}</span>
                <ChevronDown size={14} className="shrink-0 text-slate-400 transition-transform group-open:rotate-180" />
              </summary>
              <div className="absolute right-0 z-[100] mt-2 w-64 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-700 dark:bg-slate-900">
                <div className="max-h-72 overflow-auto pr-1">
                  {months.map((month) => {
                    const checked = draftSelectedMonths.includes(month);
                    const disabled = !checked && draftSelectedMonths.length >= MAX_DASHBOARD_BATCH_MONTHS;
                    return (
                      <label key={month} className={`flex items-center gap-2 rounded-xl px-2.5 py-2 text-xs font-semibold transition-colors ${disabled ? 'cursor-not-allowed opacity-40' : 'cursor-pointer'} ${checked ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300' : 'text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800'}`}>
                        <input type="checkbox" checked={checked} disabled={disabled} onChange={() => onToggleMonth(month)} className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
                        <span>{month}</span>
                      </label>
                    );
                  })}
                </div>
                <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2 dark:border-slate-800">
                  <span className="text-[10px] font-semibold text-slate-400">{draftSelectedMonths.length}/{MAX_DASHBOARD_BATCH_MONTHS} selectate</span>
                  <button type="button" onClick={onApplyMonths} className="rounded-xl bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white shadow-sm transition-colors hover:bg-indigo-700">OK</button>
                </div>
              </div>
            </details>
          </div>
        </div>
        <p className="mt-3 rounded-xl bg-indigo-50 px-3 py-2 text-xs text-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-300">
          Implicit, comparația păstrează doar magazinele active în cohorta curentă. Activează „Include magazine închise” pentru o vedere istorică completă.
        </p>
      </div>

      <div className={`glass space-y-4 rounded-3xl p-4 ${mobileSection !== 'summary' ? 'hidden lg:block' : ''}`}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0"><h3 className="truncate text-sm font-bold">Overview — {selectionLabel}</h3><p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">{historyStatusLabel}</p></div>
          <span className="shrink-0 rounded-xl bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">{historySummary?.last_sale_date ?? '-'}</span>
        </div>
        <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
          <div className="mb-3 grid grid-cols-3 gap-2 text-center">
            <div><div className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Target</div><div className="mt-0.5 text-[13px] font-bold text-slate-600 dark:text-slate-300"><CompactCurrency value={Number(historySummary?.total_target ?? selectedPoint.total_target)} /></div></div>
            <div><div className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Realizat</div><div className="mt-0.5 text-[13px] font-bold text-slate-800 dark:text-slate-100"><CompactCurrency value={Number(historySummary?.total_sales ?? selectedPoint.total_sales)} /></div></div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">{historySummary?.is_month_final === false ? 'Previziune' : 'Realizat %'}</div>
              <div className="mt-0.5 text-[13px] font-bold text-indigo-600 dark:text-indigo-400">{historySummary?.is_month_final === false ? <CompactCurrency value={Number(historySummary.forecast_sales ?? historySummary.total_sales)} /> : formatPercent(historySummary?.target_progress_pct ?? selectedPoint.target_progress_pct)}</div>
            </div>
          </div>
          <div className="relative h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            {historySummary?.is_month_final === false && <div className="absolute inset-y-0 left-0 rounded-full bg-indigo-200 dark:bg-indigo-700" style={{ width: `${Math.min(Number(historySummary.forecast_target_progress_pct ?? 0), 100)}%` }} />}
            <div className="absolute inset-y-0 left-0 rounded-full bg-indigo-600" style={{ width: `${Math.min(Number(historySummary?.target_progress_pct ?? selectedPoint.target_progress_pct ?? 0), 100)}%` }} />
          </div>
          <div className="mt-1.5 flex justify-between text-[10px] font-semibold">
            <span className="text-indigo-600">Actual {formatPercent(historySummary?.target_progress_pct ?? selectedPoint.target_progress_pct)}</span>
            {historySummary?.is_month_final === false && <span className="text-slate-600 dark:text-slate-300">Forecast {formatPercent(historySummary.forecast_target_progress_pct)}</span>}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          <KpiPerformanceCard title="Bonuri cu accesorii" value={historySummary?.proc_bon2acc ?? selectedPoint.proc_bon2acc} tone={getBon2AccTone(Number(historySummary?.proc_bon2acc ?? selectedPoint.proc_bon2acc ?? 0))} chartData={historyReceiptBucketChartData} dataKey="receipt_count" nameKey="bucket" formatValue={formatInt} />
          <KpiPerformanceCard title="Pondere produse Focus" value={historySummary?.prc_focus_acc_qty ?? selectedPoint.prc_focus_acc_qty} tone={getFocusTone(Number(historySummary?.prc_focus_acc_qty ?? selectedPoint.prc_focus_acc_qty ?? 0))} chartData={historyFocusSubcategoryChartData} dataKey="quantity_total" nameKey="category" formatValue={formatInt} />
        </div>
        <div className="grid grid-cols-4 gap-2 lg:grid-cols-8">
          <Metric label="Bonuri" value={formatInt(historySummary?.total_receipts ?? selectedPoint.total_receipts)} className="p-2" />
          <Metric label="Accesorii nete" value={formatInt(historySummary?.total_quantity ?? selectedPoint.total_quantity)} className="p-2" />
          <Metric label="Magazine / Agenți" value={<span className="flex items-baseline gap-1.5"><span>{formatInt(historySummary?.total_stores ?? selectedPoint.total_stores)}</span><span className="text-slate-300 dark:text-slate-600">/</span><span>{formatInt(historySummary?.total_agents ?? selectedPoint.total_agents)}</span></span>} className="p-2" />
          <Metric label="Zile lucrate" value={formatInt(historySummary?.working_days ?? selectedPoint.working_days)} className="p-2" />
          <Metric label="Med. zilnica" value={formatAmount(historySummary?.daily_average ?? selectedPoint.daily_average ?? 0)} className="p-2" />
          <Metric label="Medie produs" value={formatAmount(historySummary?.medie_produs ?? selectedPoint.medie_produs ?? 0)} className="p-2" />
          <Metric label="Val. medie bon" value={formatAmount((historySummary?.total_receipts ?? selectedPoint.total_receipts) > 0 ? Number(historySummary?.total_sales ?? selectedPoint.total_sales) / Number(historySummary?.total_receipts ?? selectedPoint.total_receipts) : 0)} className="p-2" />
          <Metric label="Cartele" value={formatInt(historySummary?.cartele_qty ?? 0)} className="p-2" />
        </div>
      </div>

      <div className={`grid gap-3 lg:grid-cols-[1.2fr_1fr] ${mobileSection !== 'details' ? 'hidden lg:grid' : ''}`}>
        <div className="glass rounded-3xl p-4">
          <div className="mb-3 flex items-center gap-2"><CalendarRange size={16} className="text-indigo-500" /><h3 className="text-sm font-bold">Evolutie zilnica pentru {selectionLabel}</h3></div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
              <ComposedChart data={historyDailyChartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                <XAxis dataKey="day" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="qty" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(value: number, name: string) => name === 'Vanzari' ? formatAmount(value) : formatInt(value)} />
                <Legend />
                <Bar yAxisId="sales" dataKey="sales" name="Vanzari" fill="#4f46e5" radius={[8, 8, 0, 0]} />
                <Line yAxisId="qty" type="monotone" dataKey="qty" name="Cantitate" stroke="#f59e0b" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="glass rounded-3xl p-4">
          <div className="mb-3 flex items-center gap-2"><PieChartIcon size={16} className="text-indigo-500" /><h3 className="text-sm font-bold">Top categorii si branduri</h3></div>
          <div className="space-y-4">
            <CompactPieSection title="Top categorii" emptyLabel="Nu exista categorii disponibile pentru filtrarea curenta." pieData={historyCategoryMixChartData} dataKey="sales_total" nameKey="category" valueFormatter={formatAmount} centerValue={formatCompactDonutValue(sumChartValues(historyCategoryMixChartData, 'sales_total'))} />
            <CompactPieSection title="Branduri compatibile" emptyLabel="Nu exista date pentru brandurile urmarite." pieData={historyBrandMixChartData} dataKey="sales_total" nameKey="brand" valueFormatter={formatAmount} centerValue={formatCompactDonutValue(sumChartValues(historyBrandMixChartData, 'sales_total'))} />
          </div>
        </div>
      </div>

      <div className={mobileSection !== 'details' ? 'hidden lg:contents' : 'contents'}>
      <BreakdownTable
        title="RM"
        icon={<MapPin size={16} className="text-indigo-500" />}
        subtitle={`Sortare: ${regionalColumns.find((column) => column.key === regionalSort.key)?.label} (${regionalSort.direction}) · ${regionals.length} regionali`}
        rows={sortedRegionals}
        columns={regionalColumns}
        sortKey={regionalSort.key}
        sortDirection={regionalSort.direction}
        onSort={onSortRegionals}
        rowKey={(row) => row.regional}
        exportFilename={`hub_${selectionSlug}_istoric_rm`}
        exportSheetName="RM istoric"
        exportColumns={[
          { header: 'Regional', value: (row) => row.regional },
          { header: 'Target', value: (row) => row.target, format: 'currency' },
          { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' },
          { header: 'Procent', value: (row) => row.proc_realizare_target, format: 'percentPoints' },
          { header: 'Cantitate', value: (row) => row.qty_total, format: 'integer' },
          { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' },
          { header: 'ProcBon2Acc', value: (row) => row.proc_bon2acc, format: 'percentPoints' },
          { header: 'Focus%', value: (row) => row.prc_focus_acc_qty, format: 'percentPoints' },
        ]}
      />
      <BreakdownTable
        title="Magazine"
        icon={<Building2 size={16} className="text-indigo-500" />}
        subtitle={`Sortare: ${storeColumns.find((column) => column.key === storeSort.key)?.label} (${storeSort.direction}) · ${stores.length} magazine`}
        rows={sortedStores}
        columns={storeColumns}
        sortKey={storeSort.key}
        sortDirection={storeSort.direction}
        onSort={onSortStores}
        rowKey={(row) => row.site_code}
        exportFilename={`hub_${selectionSlug}_istoric_magazine`}
        exportSheetName="Magazine istoric"
        exportColumns={[
          { header: 'Firma', value: (row) => row.firma },
          { header: 'Magazin', value: (row) => row.locatie },
          { header: 'Target', value: (row) => row.target, format: 'currency' },
          { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' },
          { header: 'Procent', value: (row) => row.proc_realizare_target, format: 'percentPoints' },
          { header: 'Cantitate', value: (row) => row.qty_total, format: 'integer' },
          { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' },
          { header: 'Retururi', value: (row) => row.return_receipt_count, format: 'integer' },
          { header: 'Agenti', value: (row) => row.nr_agenti, format: 'integer' },
          { header: 'Zile active', value: (row) => row.zile_active, format: 'integer' },
        ]}
      />
      <BreakdownTable
        title="Agenti"
        subtitle={`Sortare: ${agentColumns.find((column) => column.key === agentSort.key)?.label} (${agentSort.direction}) · ${agents.length} agenti`}
        rows={sortedAgents}
        columns={agentColumns}
        sortKey={agentSort.key}
        sortDirection={agentSort.direction}
        onSort={onSortAgents}
        rowKey={(row) => `${row.agent}-${row.site_code}`}
        exportFilename={`hub_${selectionSlug}_istoric_agenti`}
        exportSheetName="Agenti istoric"
        exportColumns={[
          { header: 'Agent', value: (row) => row.agent },
          { header: 'Firma', value: (row) => row.firma },
          { header: 'Magazin', value: (row) => row.locatie },
          { header: 'Target', value: (row) => row.target, format: 'currency' },
          { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' },
          { header: 'Procent', value: (row) => row.proc_realizare_target, format: 'percentPoints' },
          { header: 'Cantitate', value: (row) => row.acc_qty_realizat, format: 'integer' },
          { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' },
          { header: 'Retururi', value: (row) => row.return_receipt_count, format: 'integer' },
          { header: 'Zile lucrate', value: (row) => row.zile_lucrate, format: 'integer' },
          { header: 'Medie zilnica', value: (row) => row.medie_zilnica, format: 'currency' },
          { header: 'ProcBon2Acc', value: (row) => row.proc_bon2acc, format: 'percentPoints' },
          { header: 'Focus%', value: (row) => row.prc_focus_acc_qty, format: 'percentPoints' },
        ]}
      />
      </div>
    </>
  );
}
