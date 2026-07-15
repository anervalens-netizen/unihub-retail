import { useCallback, useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import {
  auditSalaryExport,
  fetchSalariiOverview,
  fetchSalaryAgents,
  fetchSalaryEvolution,
  fetchSalarySummary,
  fetchSalaryTrend,
} from '../api/salarii';
import type {
  SalariiOverview,
  SalaryAgentSummary,
  SalaryEvolutionPoint,
  SalaryComparisonPoint,
  SalaryTrendMonth,
} from '../api/salarii';
import type { AppFilters } from './MainLayout';
import { SalaryAreaChart } from './SalaryAreaChart';
import { SalaryDrawer } from './SalaryDrawer';
import { ExportTableButton } from './ExportTableButton';
import { SortableHeader } from './dashboard/DashboardWidgets';
import { formatMonthSpanLabel } from '../lib/dates';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from '../lib/filterValues';
import { cn } from '../lib/utils';
import { SegmentedTabs } from './common/SegmentedTabs';

type SortDir = 'asc' | 'desc';
interface SortState<K extends string> { key: K; dir: SortDir }

type SummarySort =
  | 'locatie'
  | 'company_name'
  | 'agent_count'
  | 'total_salary'
  | 'avg_salary'
  | 'total_sales'
  | 'ratio';
type TrendSort = 'month' | 'total_salary' | 'total_sales' | 'avg_salary' | 'ratio';

function toggleSort<K extends string>(prev: SortState<K>, key: K): SortState<K> {
  if (prev.key === key) return { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' };
  return { key, dir: 'desc' };
}

function formatMonthSpan(span?: [number, number, number, number] | null): string {
  return formatMonthSpanLabel(span);
}

function formatCurrency(val: unknown): string {
  if (val === undefined || val === null) return '0';
  const value = typeof val === 'string' ? parseFloat(val) : val;
  if (typeof value !== 'number' || Number.isNaN(value)) return '0';
  return value.toLocaleString('ro-RO', { maximumFractionDigits: 0 });
}

function formatCompactCurrency(val: unknown): string {
  if (val === undefined || val === null) return '0';
  const value = typeof val === 'string' ? parseFloat(val) : val;
  if (typeof value !== 'number' || Number.isNaN(value)) return '0';
  return value.toLocaleString('ro-RO', {
    notation: 'compact',
    maximumFractionDigits: 1,
  });
}

const COMPANY_COLORS: Record<string, string> = {
  Mobicell: 'text-indigo-500',
  Mobiup: 'text-emerald-500',
};

const RATIO_HELP_TEXT = '% = Salarii / Vanzari. Culoarea compara procentul cu media ponderata a randurilor afisate.';

function getSalarySalesRatio(totalSalary: number, totalSales: number): number {
  return totalSales > 0 ? (totalSalary / totalSales) * 100 : 0;
}

function getWeightedRatioAverage(rows: Array<{ total_salary: number; total_sales: number }>): number {
  const totals = rows.reduce(
    (acc, row) => {
      acc.salary += row.total_salary || 0;
      acc.sales += row.total_sales || 0;
      return acc;
    },
    { salary: 0, sales: 0 }
  );
  return getSalarySalesRatio(totals.salary, totals.sales);
}

function getRatioToneStyle(ratio: number, average: number): CSSProperties {
  if (!Number.isFinite(ratio) || !Number.isFinite(average) || average <= 0) {
    return { color: 'hsl(45 88% 38%)' };
  }

  const deadband = 0.35;
  const deviation = ratio - average;
  if (Math.abs(deviation) <= deadband) {
    return { color: 'hsl(45 88% 38%)' };
  }

  const maxDeviation = Math.max(average * 0.6, 8);
  const intensity = Math.min(Math.abs(deviation) / maxDeviation, 1);
  const hue = deviation > 0
    ? 45 - 45 * intensity
    : 45 + 95 * intensity;
  const lightness = 38 - 6 * intensity;

  return { color: `hsl(${hue.toFixed(0)} 78% ${lightness.toFixed(0)}%)` };
}

interface DrawerState {
  personId: string;
  fullName: string;
}

interface SalariiSubtabProps {
  globalFilters?: AppFilters;
}

export function SalariiSubtab({ globalFilters }: SalariiSubtabProps) {
  const [salaryView, setSalaryView] = useState<'overview' | 'stores' | 'agents'>('overview');
  const [overview, setOverview] = useState<SalariiOverview | null>(null);
  const [evolution, setEvolution] = useState<SalaryEvolutionPoint[]>([]);
  const [agents, setAgents] = useState<SalaryAgentSummary[]>([]);
  const [totalAgents, setTotalAgents] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(0);
  const [drawer, setDrawer] = useState<DrawerState | null>(null);
  const [summary, setSummary] = useState<SalaryComparisonPoint[]>([]);
  const [trend, setTrend] = useState<SalaryTrendMonth[]>([]);
  const [summaryMonth, setSummaryMonth] = useState<string | null>(null);
  const [selectedSummaryMonth, setSelectedSummaryMonth] = useState<string>('');
  const [loadingCards, setLoadingCards] = useState(false);

  const [summarySort, setSummarySort] = useState<SortState<SummarySort>>({ key: 'total_salary', dir: 'desc' });
  const [trendSort, setTrendSort] = useState<SortState<TrendSort>>({ key: 'month', dir: 'desc' });

  const PAGE_SIZE = 50;

  const filterCompany = globalFilters?.firma !== ALL_FIRMS ? globalFilters?.firma : undefined;
  const filterRegional = globalFilters?.rm !== ALL_SCOPE ? globalFilters?.rm : undefined;
  const filterAsm = globalFilters?.asm !== ALL_SCOPE ? globalFilters?.asm : undefined;
  const filterSiteCode = globalFilters?.magazin !== ALL_STORES ? globalFilters?.magazin : undefined;

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const loadOverview = useCallback(async () => {
    try {
      const [ov, ev] = await Promise.all([
        fetchSalariiOverview({ company_name: filterCompany, site_code: filterSiteCode, regional: filterRegional, asm: filterAsm }),
        fetchSalaryEvolution({ company_name: filterCompany, site_code: filterSiteCode, regional: filterRegional, asm: filterAsm }),
      ]);
      setOverview(ov);
      setEvolution(ev);
    } catch (e) {
      console.error('Failed to load overview:', e);
    }
  }, [filterCompany, filterSiteCode, filterRegional, filterAsm]);

  const loadSummary = useCallback(async () => {
    setLoadingCards(true);
    try {
      let year: number | undefined;
      let month: number | undefined;
      if (selectedSummaryMonth && /^\d{4}-\d{2}$/.test(selectedSummaryMonth)) {
        [year, month] = selectedSummaryMonth.split('-').map(Number);
      }
      const data = await fetchSalarySummary({ company_name: filterCompany, site_code: filterSiteCode, regional: filterRegional, asm: filterAsm, year, month });
      setSummary(data.items || []);
      setSummaryMonth(data.month);
    } catch (e) {
      console.error('Failed to load summary:', e);
    } finally {
      setLoadingCards(false);
    }
  }, [filterCompany, filterSiteCode, filterRegional, filterAsm, selectedSummaryMonth]);

  const loadTrend = useCallback(async () => {
    setLoadingCards(true);
    try {
      const data = await fetchSalaryTrend({ company_name: filterCompany, site_code: filterSiteCode, regional: filterRegional, asm: filterAsm });
      setTrend(data || []);
    } catch (e) {
      console.error('Failed to load trend:', e);
    } finally {
      setLoadingCards(false);
    }
  }, [filterCompany, filterSiteCode, filterRegional, filterAsm]);

  const loadAgents = useCallback(
    async (offset = 0) => {
      setLoading(true);
      try {
        const res = await fetchSalaryAgents({
          q: debouncedSearch || undefined,
          company_name: filterCompany,
          site_code: filterSiteCode,
          regional: filterRegional,
          asm: filterAsm,
          limit: PAGE_SIZE,
          offset,
        });
        setAgents(res?.items || []);
        setTotalAgents(res?.total || 0);
      } catch (e) {
        console.error('Failed to load agents:', e);
      } finally {
        setLoading(false);
      }
    },
    [debouncedSearch, filterCompany, filterSiteCode, filterRegional, filterAsm]
  );

  useEffect(() => { loadOverview(); }, [loadOverview]);
  useEffect(() => { loadSummary(); }, [loadSummary]);
  useEffect(() => { loadTrend(); }, [loadTrend]);
  useEffect(() => { setPage(0); loadAgents(0); }, [loadAgents]);

  function handleSearchChange(val: string) {
    setSearch(val);
    setPage(0);
  }

  function resetFilters() {
    setSearch('');
    setDebouncedSearch('');
    setPage(0);
  }

  const hasMore = (page + 1) * PAGE_SIZE < totalAgents;

  const sortedSummary = useMemo(() => {
    if (!summary.length) return summary;
    const { key, dir } = summarySort;
    const sorted = [...summary].sort((a, b) => {
      let cmp: number;
      if (key === 'locatie') cmp = (a.locatie ?? a.site_code).localeCompare(b.locatie ?? b.site_code);
      else if (key === 'company_name') cmp = a.company_name.localeCompare(b.company_name);
      else cmp = (a[key] as number) - (b[key] as number);
      return dir === 'asc' ? cmp : -cmp;
    });
    return sorted;
  }, [summary, summarySort]);

  const sortedTrend = useMemo(() => {
    if (!trend.length) return trend;
    const { key, dir } = trendSort;
    const sorted = [...trend].sort((a, b) => {
      let cmp: number;
      if (key === 'month') cmp = a.month.localeCompare(b.month);
      else if (key === 'ratio') {
        const rA = a.total_sales > 0 ? a.total_salary / a.total_sales : 0;
        const rB = b.total_sales > 0 ? b.total_salary / b.total_sales : 0;
        cmp = rA - rB;
      } else cmp = (a[key] as number) - (b[key] as number);
      return dir === 'asc' ? cmp : -cmp;
    });
    return sorted;
  }, [trend, trendSort]);

  const summaryRatioAverage = useMemo(() => getWeightedRatioAverage(summary), [summary]);
  const trendRatioAverage = useMemo(() => getWeightedRatioAverage(trend), [trend]);

  const mobicellTotal = overview?.by_company?.find((c) => c.name === 'Mobicell')?.total ?? 0;
  const mobiupTotal = overview?.by_company?.find((c) => c.name === 'Mobiup')?.total ?? 0;

  return (
    <div className="space-y-4 px-4 py-4">
      <SegmentedTabs<'overview' | 'stores' | 'agents'>
        ariaLabel="Vizualizare salarii"
        className="glass"
        options={[
          { value: 'overview', label: 'Overview' },
          { value: 'stores', label: 'Magazine' },
          { value: 'agents', label: 'Agenți' },
        ]}
        value={salaryView}
        onChange={setSalaryView}
      />
      <p className="rounded-2xl border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs text-indigo-700 dark:border-indigo-900/50 dark:bg-indigo-950/30 dark:text-indigo-300">
        Media lunară include doar valorile de cel puțin 2.000 RON. Totalurile, istoricul și numărul de agenți rămân complete.
      </p>
      {/* ===== Card 1: Statistici Salarii ===== */}
      <div className={cn('glass rounded-3xl p-4', salaryView !== 'overview' && 'hidden')}>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-600 dark:text-slate-300">Statistici Salarii</h3>
          {loadingCards && <RefreshCw size={14} className="animate-spin text-slate-400" />}
        </div>
        <div className="grid grid-cols-2 gap-3">
          {/* Row 1: total + average */}
          <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <div className="text-xs font-bold text-slate-500">Total Salarii</div>
            <div className="mt-1 text-2xl font-black text-slate-800 dark:text-white">
              {overview ? `${formatCompactCurrency(overview.total)} RON` : '—'}
            </div>
          </div>
          <div
            className="rounded-2xl bg-indigo-50 p-3 dark:bg-indigo-950/30"
            title="Media include doar salariile lunare de cel putin 2.000 RON. Totalurile raman complete."
          >
            <div className="text-xs font-bold text-indigo-600 dark:text-indigo-400">Medie lunară / agent</div>
            <div className="mt-1 text-2xl font-black text-indigo-600 dark:text-indigo-400">
              {overview ? `${formatCurrency(overview.avg_salary)} RON` : '—'}
            </div>
            <div className="text-xs text-indigo-400">
              {formatCurrency(overview?.avg_agent_month_count ?? 0)} salarii eligibile (≥ 2.000 RON)
            </div>
          </div>
          {/* Row 2: period + unique agents */}
          <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <div className="text-xs font-bold text-slate-500">Perioada</div>
            <div className="mt-1 text-sm font-bold text-slate-700 dark:text-slate-300">
              {overview ? formatMonthSpan(overview.months_span) : '—'}
            </div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <div className="text-xs font-bold text-slate-500">Agenți unici</div>
            <div className="mt-1 text-2xl font-black text-slate-800 dark:text-white">
              {overview ? formatCurrency(overview.agent_count) : '—'}
            </div>
          </div>
          {/* Row 3: Mobiup + Mobicell */}
          <div className="rounded-2xl bg-emerald-50 p-3 dark:bg-emerald-950/30">
            <div className="text-xs font-bold text-emerald-600 dark:text-emerald-400">Mobiup</div>
            <div className="mt-1 text-2xl font-black text-emerald-600 dark:text-emerald-400">
              {overview ? `${formatCompactCurrency(mobiupTotal)} RON` : '—'}
            </div>
          </div>
          <div className="rounded-2xl bg-indigo-50 p-3 dark:bg-indigo-950/30">
            <div className="text-xs font-bold text-indigo-600 dark:text-indigo-400">Mobicell</div>
            <div className="mt-1 text-2xl font-black text-indigo-600 dark:text-indigo-400">
              {overview ? `${formatCompactCurrency(mobicellTotal)} RON` : '—'}
            </div>
          </div>
        </div>
      </div>

      {/* ===== Card 2: Salarii vs Vanzari (unificat) ===== */}
      <div className={cn('glass rounded-3xl p-4', salaryView !== 'stores' && 'hidden')}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-bold text-slate-600 dark:text-slate-300">
            Salarii vs Vânzări
          </h3>
          <div className="flex items-center gap-2">
            <ExportTableButton
              filename={`salarii-magazine-${summaryMonth ?? 'curent'}`}
              sheetName="Salarii magazine"
              rows={sortedSummary}
              beforeExport={() =>
                auditSalaryExport('store_summary', sortedSummary.length)
              }
              columns={[
                { header: 'Locatie', value: (row) => row.locatie ?? row.site_code },
                { header: 'Firma', value: (row) => row.company_name },
                { header: 'Agenti', value: (row) => row.agent_count },
                { header: 'Salarii', value: (row) => row.total_salary },
                { header: 'Medie agent', value: (row) => row.avg_salary },
                { header: 'Vanzari', value: (row) => row.total_sales },
                { header: 'Procent', value: (row) => row.ratio },
              ]}
            />
            <select
              value={selectedSummaryMonth}
              onChange={(e) => setSelectedSummaryMonth(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white/80 py-1.5 px-2 text-xs text-slate-700 focus:border-indigo-400 focus:outline-none dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-200"
            >
              <option value="">Luna curenta</option>
              {overview && overview.months_span && (() => {
                const [minY, minM, maxY, maxM] = overview.months_span;
                const months: string[] = [];
                for (let y = maxY; y >= minY; y--) {
                  const startM = y === maxY ? maxM : 12;
                  const endM = y === minY ? minM : 1;
                  for (let m = startM; m >= endM; m--) {
                    months.push(`${y}-${String(m).padStart(2, '0')}`);
                  }
                }
                return months.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ));
              })()}
            </select>
            {summaryMonth && (
              <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">{summaryMonth}</span>
            )}
          </div>
        </div>
        <div className="space-y-2 lg:hidden">
          {sortedSummary.map((item) => (
            <article key={`${item.locatie ?? item.site_code}-${item.company_name}-mobile`} className="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0"><p className="truncate text-sm font-bold">{item.locatie ?? item.site_code}</p><p className={`text-xs font-bold ${COMPANY_COLORS[item.company_name] ?? 'text-slate-500'}`}>{item.company_name} · {item.agent_count} agenți</p></div>
                <span className="rounded-xl bg-indigo-50 px-2 py-1 text-sm font-black text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">{item.ratio.toFixed(1)}%</span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2">
                <div><p className="text-[10px] text-slate-400">Salarii</p><p className="text-xs font-bold">{formatCompactCurrency(item.total_salary)} RON</p></div>
                <div><p className="text-[10px] text-slate-400">Medie</p><p className="text-xs font-bold">{formatCurrency(item.avg_salary)} RON</p></div>
                <div><p className="text-[10px] text-slate-400">Vânzări</p><p className="text-xs font-bold">{formatCompactCurrency(item.total_sales)} RON</p></div>
              </div>
            </article>
          ))}
          {sortedSummary.length === 0 && !loadingCards && <p className="py-6 text-center text-xs text-slate-400">Fără date</p>}
        </div>
        <div className="hidden max-h-72 overflow-auto lg:block">
          <table className="w-full min-w-[860px] table-fixed text-sm">
            <colgroup>
              <col style={{ width: '23%' }} />
              <col style={{ width: '11%' }} />
              <col style={{ width: '9%' }} />
              <col style={{ width: '14%' }} />
              <col style={{ width: '15%' }} />
              <col style={{ width: '18%' }} />
              <col style={{ width: '10%' }} />
            </colgroup>
            <thead className="sticky top-0 bg-white dark:bg-slate-900">
              <tr className="border-b border-slate-200 text-xs uppercase text-slate-500 dark:border-slate-700">
                <SortableHeader label="Locație" active={summarySort.key === 'locatie'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'locatie'))} className="px-2 py-2 text-left text-xs" />
                <SortableHeader label="Firmă" active={summarySort.key === 'company_name'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'company_name'))} className="px-2 py-2 text-left text-xs" />
                <SortableHeader label="Agenți" active={summarySort.key === 'agent_count'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'agent_count'))} className="px-2 py-2 text-right text-xs" align="right" />
                <SortableHeader label="Salarii" active={summarySort.key === 'total_salary'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'total_salary'))} className="px-2 py-2 text-right text-xs" align="right" />
                <SortableHeader label="Medie / agent" active={summarySort.key === 'avg_salary'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'avg_salary'))} className="px-2 py-2 text-right text-xs" align="right" />
                <SortableHeader label="Vânzări" active={summarySort.key === 'total_sales'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'total_sales'))} className="px-2 py-2 text-right text-xs" align="right" />
                <SortableHeader label="%*" title={RATIO_HELP_TEXT} active={summarySort.key === 'ratio'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'ratio'))} className="px-2 py-2 text-right text-xs" align="right" />
              </tr>
            </thead>
            <tbody>
              {sortedSummary.length === 0 && !loadingCards && (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-xs text-slate-400">Fără date</td>
                </tr>
              )}
              {sortedSummary.map((item) => (
                <tr key={`${item.locatie ?? item.site_code}-${item.company_name}`} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-2 font-medium text-slate-700 dark:text-slate-200">
                    {item.locatie ?? item.site_code}
                  </td>
                  <td className={`px-2 py-2 text-xs font-bold ${COMPANY_COLORS[item.company_name] ?? 'text-slate-500'}`}>
                    {item.company_name}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums text-slate-500">
                    {formatCurrency(item.agent_count)}
                  </td>
                  <td className="px-2 py-2 text-right font-mono text-slate-600 dark:text-slate-300">
                    {formatCurrency(item.total_salary)}
                  </td>
                  <td
                    className="px-2 py-2 text-right font-mono font-semibold text-slate-700 dark:text-slate-200"
                    title={`${item.avg_agent_count} din ${item.agent_count} agenți au salariul lunar de cel puțin 2.000 RON`}
                  >
                    {formatCurrency(item.avg_salary)}
                  </td>
                  <td className="px-2 py-2 text-right font-mono text-slate-500">
                    {formatCurrency(item.total_sales)}
                  </td>
                  <td
                    className="px-2 py-2 text-right text-xs font-semibold tabular-nums"
                    style={getRatioToneStyle(item.ratio, summaryRatioAverage)}
                    title={`Salarii / Vanzari. Media selectiei: ${summaryRatioAverage.toFixed(1)}%`}
                  >
                    {item.ratio.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] font-medium text-slate-400 dark:text-slate-500">
          Media exclude doar din calcul salariile sub 2.000 RON; totalurile și numărul de agenți rămân complete. * % = salarii / vânzări.
        </p>
      </div>

      {/* ===== Card 3: Trend (Evolutie Salarii vs Vanzari) ===== */}
      <div className={cn('glass rounded-3xl p-4', salaryView !== 'overview' && 'hidden')}>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-600 dark:text-slate-300">Evolutie Salarii vs Vanzari</h3>
          <div className="flex items-center gap-2">
            <ExportTableButton
              filename="salarii-evolutie-lunara"
              sheetName="Evolutie salarii"
              rows={sortedTrend}
              beforeExport={() =>
                auditSalaryExport('monthly_trend', sortedTrend.length)
              }
              columns={[
                { header: 'Luna', value: (row) => row.month },
                { header: 'Agenti', value: (row) => row.agent_count },
                { header: 'Salarii', value: (row) => row.total_salary },
                { header: 'Medie agent', value: (row) => row.avg_salary },
                { header: 'Vanzari', value: (row) => row.total_sales },
                {
                  header: 'Procent',
                  value: (row) =>
                    getSalarySalesRatio(row.total_salary, row.total_sales),
                },
              ]}
            />
            {loadingCards && <RefreshCw size={14} className="animate-spin text-slate-400" />}
          </div>
        </div>
        <div className="space-y-2 lg:hidden">
          {sortedTrend.map((item) => {
            const ratio = getSalarySalesRatio(item.total_salary, item.total_sales);
            return (
              <article key={`${item.month}-mobile`} className="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
                <div className="flex items-center justify-between"><p className="text-sm font-bold">{item.month}</p><span className="rounded-xl bg-slate-100 px-2 py-1 text-sm font-black dark:bg-slate-800">{ratio.toFixed(1)}%</span></div>
                <div className="mt-3 grid grid-cols-3 gap-2"><div><p className="text-[10px] text-slate-400">Salarii</p><p className="text-xs font-bold">{formatCompactCurrency(item.total_salary)}</p></div><div><p className="text-[10px] text-slate-400">Medie</p><p className="text-xs font-bold">{formatCurrency(item.avg_salary)}</p></div><div><p className="text-[10px] text-slate-400">Vânzări</p><p className="text-xs font-bold">{formatCompactCurrency(item.total_sales)}</p></div></div>
              </article>
            );
          })}
        </div>
        <div className="hidden overflow-x-auto lg:block">
          <table className="w-full min-w-[760px] table-fixed text-sm">
            <colgroup>
              <col style={{ width: '15%' }} />
              <col style={{ width: '11%' }} />
              <col style={{ width: '19%' }} />
              <col style={{ width: '19%' }} />
              <col style={{ width: '24%' }} />
              <col style={{ width: '12%' }} />
            </colgroup>
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase text-slate-500 dark:border-slate-700">
                <SortableHeader label="Luna" active={trendSort.key === 'month'} direction={trendSort.dir} onClick={() => setTrendSort(s => toggleSort(s, 'month'))} className="px-2 py-2 text-left text-xs" />
                <th className="px-2 py-2 text-right text-xs font-bold">Agenți</th>
                <SortableHeader label="Salarii" active={trendSort.key === 'total_salary'} direction={trendSort.dir} onClick={() => setTrendSort(s => toggleSort(s, 'total_salary'))} className="px-2 py-2 text-right text-xs" align="right" />
                <SortableHeader label="Medie / agent" title="Salariul mediu per agent în luna respectivă" active={trendSort.key === 'avg_salary'} direction={trendSort.dir} onClick={() => setTrendSort(s => toggleSort(s, 'avg_salary'))} className="px-2 py-2 text-right text-xs" align="right" />
                <SortableHeader label="Vânzări" active={trendSort.key === 'total_sales'} direction={trendSort.dir} onClick={() => setTrendSort(s => toggleSort(s, 'total_sales'))} className="px-2 py-2 text-right text-xs" align="right" />
                <SortableHeader label="%*" title={RATIO_HELP_TEXT} active={trendSort.key === 'ratio'} direction={trendSort.dir} onClick={() => setTrendSort(s => toggleSort(s, 'ratio'))} className="px-2 py-2 text-right text-xs" align="right" />
              </tr>
            </thead>
            <tbody>
              {sortedTrend.length === 0 && !loadingCards && (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-xs text-slate-400">Fără date</td>
                </tr>
              )}
              {sortedTrend.map((t) => {
                const ratio = getSalarySalesRatio(t.total_salary, t.total_sales);
                return (
                  <tr key={t.month} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-2 font-medium text-slate-700 dark:text-slate-200">{t.month}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-slate-500">{formatCurrency(t.agent_count)}</td>
                    <td className="px-2 py-2 text-right font-mono text-slate-600 dark:text-slate-300">{formatCurrency(t.total_salary)}</td>
                    <td
                      className="px-2 py-2 text-right font-mono font-semibold text-slate-700 dark:text-slate-200"
                      title={`Salariul mediu în ${t.month}: ${formatCurrency(t.avg_salary)} RON. Eligibili: ${t.avg_agent_count} din ${t.agent_count} agenți (salariu ≥ 2.000 RON).`}
                    >
                      {formatCurrency(t.avg_salary)}
                    </td>
                    <td className="px-2 py-2 text-right font-mono text-slate-500">{formatCurrency(t.total_sales)}</td>
                    <td
                      className="px-2 py-2 text-right text-xs font-semibold tabular-nums"
                      style={getRatioToneStyle(ratio, trendRatioAverage)}
                      title={`Salarii / Vanzari. Media selectiei: ${trendRatioAverage.toFixed(1)}%`}
                    >
                      {ratio.toFixed(1)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] font-medium text-slate-400 dark:text-slate-500">
            Media exclude doar din calcul salariile sub 2.000 RON; totalurile și agenții afișați rămân complete. * % = salarii / vânzări.
          </p>
        </div>
      </div>

      {/* ===== Card 4: Evolutie Salarii Lunar (Area Chart) ===== */}
      <div className={cn('glass rounded-3xl p-4', salaryView !== 'overview' && 'hidden')}>
        <h3 className="mb-3 text-sm font-bold text-slate-600 dark:text-slate-300">Evolutie Salarii Lunara</h3>
        <SalaryAreaChart data={evolution} />
      </div>

      {/* ===== Card 5: Agenti (unificat) ===== */}
      <div className={cn('glass overflow-hidden rounded-3xl', salaryView !== 'agents' && 'hidden')}>
        {/* Card Header */}
        <div className="bg-slate-50 px-4 py-3 dark:bg-slate-800/50">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200">Agenti</h3>
              <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-bold text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-300">
                {totalAgents}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <ExportTableButton
                filename={`salarii-agenti-pagina-${page + 1}`}
                sheetName="Salarii agenti"
                rows={agents}
                beforeExport={() =>
                  auditSalaryExport('agents_page', agents.length)
                }
                columns={[
                  { header: 'Agent', value: (row) => row.full_name },
                  { header: 'Firma', value: (row) => row.company_name },
                  { header: 'Locatie', value: (row) => row.locatie ?? '' },
                  { header: 'Luni', value: (row) => row.month_count },
                  { header: 'Medie lunara', value: (row) => row.avg_salary },
                  { header: 'Total', value: (row) => row.total_salary },
                ]}
              />
              {/* Search */}
              <div className="relative">
                <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Cauta..."
                  value={search}
                  onChange={(e) => handleSearchChange(e.target.value)}
                  className="h-11 w-40 rounded-lg border border-slate-200 bg-white/80 py-2 pl-7 pr-2 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-200 lg:h-auto lg:w-32 lg:py-1.5"
                />
              </div>
              {search && (
                <button
                  onClick={resetFilters}
                  className="rounded-lg border border-slate-200 bg-white/80 py-1.5 px-2 text-xs text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-400"
                >
                  Reseteaza
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Table */}
        <div className="space-y-2 p-3 lg:hidden">
          {agents?.map((agent) => (
            <button key={`${agent.person_id}-mobile`} type="button" onClick={() => setDrawer({ personId: agent.person_id, fullName: agent.full_name })} className="min-h-20 w-full rounded-2xl border border-slate-200 bg-white p-3 text-left dark:border-slate-700 dark:bg-slate-900">
              <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-bold">{agent.full_name}</p><p className="truncate text-xs text-slate-500">{agent.company_name} · {agent.locatie ?? 'Fără locație'}</p></div><p className="shrink-0 text-sm font-black text-indigo-600 dark:text-indigo-300">{formatCurrency(agent.total_salary)} RON</p></div>
              <p className="mt-2 text-xs text-slate-500">{agent.month_count} luni · medie eligibilă {formatCurrency(agent.avg_salary)} RON</p>
            </button>
          ))}
          {(!agents || agents.length === 0) && !loading && <p className="py-8 text-center text-sm text-slate-400">Nu s-au găsit agenți</p>}
        </div>
        <div className="hidden max-h-72 overflow-auto lg:block">
          <table className="w-full min-w-[820px] table-fixed text-sm">
            <colgroup>
              <col style={{ width: '25%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '23%' }} />
              <col style={{ width: '10%' }} />
              <col style={{ width: '15%' }} />
              <col style={{ width: '15%' }} />
            </colgroup>
            <thead className="sticky top-0 z-10 bg-slate-100 text-xs font-bold uppercase tracking-wider text-slate-500 dark:bg-slate-800">
              <tr>
                <th className="px-4 py-2 text-left">Nume agent</th>
                <th className="px-2 py-2 text-left">Firmă</th>
                <th className="px-2 py-2 text-left">Locație curentă</th>
                <th className="px-2 py-2 text-right">Luni</th>
                <th className="px-2 py-2 text-right">Medie / lună</th>
                <th className="px-4 py-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {(!agents || agents.length === 0) && !loading && (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-sm text-slate-400">
                    Nu s-au găsit agenți
                  </td>
                </tr>
              )}
              {agents?.map((agent) => (
                <tr
                  key={agent.person_id}
                  onClick={() => setDrawer({ personId: agent.person_id, fullName: agent.full_name })}
                  className="cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50"
                  title="Deschide istoricul agentului"
                >
                  <td className="px-4 py-3 font-semibold text-slate-800 dark:text-white">{agent.full_name}</td>
                  <td className={`px-2 py-3 text-xs font-bold ${COMPANY_COLORS[agent.company_name] ?? 'text-slate-500'}`}>
                    {agent.company_name}
                  </td>
                  <td className="px-2 py-3 text-slate-500">{agent.locatie ?? '—'}</td>
                  <td className="px-2 py-3 text-right tabular-nums text-slate-500">{formatCurrency(agent.month_count)}</td>
                  <td
                    className="px-2 py-3 text-right font-mono text-slate-600 dark:text-slate-300"
                    title={`${agent.avg_month_count} din ${agent.month_count} luni au salariul de cel puțin 2.000 RON`}
                  >
                    {formatCurrency(agent.avg_salary)} RON
                  </td>
                  <td className="px-4 py-3 text-right font-bold tabular-nums text-slate-800 dark:text-white">
                    {formatCurrency(agent.total_salary)} RON
                  </td>
                </tr>
              ))}
              {loading && (!agents || agents.length === 0) && (
                <tr>
                  <td colSpan={6} className="py-12 text-center">
                    <RefreshCw size={20} className="mx-auto animate-spin text-indigo-500" />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalAgents > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800/50">
            <span className="text-xs text-slate-500">
              {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalAgents)} din {totalAgents}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => { const p = page - 1; setPage(p); loadAgents(p * PAGE_SIZE); }}
                disabled={page === 0}
                className="min-h-11 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 disabled:opacity-40 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 lg:min-h-0 lg:py-1.5"
              >
                Inapoi
              </button>
              <button
                onClick={() => { const p = page + 1; setPage(p); loadAgents(p * PAGE_SIZE); }}
                disabled={!hasMore}
                className="min-h-11 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 disabled:opacity-40 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 lg:min-h-0 lg:py-1.5"
              >
                Inainte
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Drawer */}
      <SalaryDrawer
        personId={drawer?.personId ?? ''}
        fullName={drawer?.fullName ?? ''}
        isOpen={!!drawer}
        onClose={() => setDrawer(null)}
      />
    </div>
  );
}
