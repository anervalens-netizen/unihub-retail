import { useCallback, useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import {
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
import { SortableHeader } from './dashboard/DashboardWidgets';

type SortDir = 'asc' | 'desc';
interface SortState<K extends string> { key: K; dir: SortDir }

type SummarySort = 'locatie' | 'company_name' | 'total_salary' | 'total_sales' | 'ratio';
type TrendSort = 'month' | 'total_salary' | 'total_sales' | 'ratio';

function toggleSort<K extends string>(prev: SortState<K>, key: K): SortState<K> {
  if (prev.key === key) return { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' };
  return { key, dir: 'desc' };
}

const MONTHS = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];

function formatMonthSpan(span?: [number, number, number, number] | null): string {
  if (!span || !Array.isArray(span) || span.length !== 4) return '—';
  const [minY, minM, maxY, maxM] = span;
  return `${MONTHS[minM - 1]}-${String(minY).slice(2)} → ${MONTHS[maxM - 1]}-${String(maxY).slice(2)}`;
}

function formatCurrency(val: any): string {
  if (val === undefined || val === null) return '0';
  const value = typeof val === 'string' ? parseFloat(val) : val;
  if (isNaN(value)) return '0';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
  return value.toFixed(0);
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
  cnp: string;
  fullName: string;
}

interface SalariiSubtabProps {
  globalFilters?: AppFilters;
}

export function SalariiSubtab({ globalFilters }: SalariiSubtabProps) {
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

  const filterCompany = globalFilters?.firma !== 'Toate' ? globalFilters?.firma : undefined;
  const filterRegional = globalFilters?.rm !== 'Toti' ? globalFilters?.rm : undefined;
  const filterAsm = globalFilters?.asm !== 'Toti' ? globalFilters?.asm : undefined;

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const loadOverview = useCallback(async () => {
    try {
      const [ov, ev] = await Promise.all([
        fetchSalariiOverview({ company_name: filterCompany, regional: filterRegional, asm: filterAsm }),
        fetchSalaryEvolution({ company_name: filterCompany, regional: filterRegional, asm: filterAsm }),
      ]);
      setOverview(ov);
      setEvolution(ev);
    } catch (e) {
      console.error('Failed to load overview:', e);
    }
  }, [filterCompany, filterRegional, filterAsm]);

  const loadSummary = useCallback(async () => {
    setLoadingCards(true);
    try {
      let year: number | undefined;
      let month: number | undefined;
      if (selectedSummaryMonth && /^\d{4}-\d{2}$/.test(selectedSummaryMonth)) {
        [year, month] = selectedSummaryMonth.split('-').map(Number);
      }
      const data = await fetchSalarySummary({ company_name: filterCompany, regional: filterRegional, asm: filterAsm, year, month });
      setSummary(data.items || []);
      setSummaryMonth(data.month);
    } catch (e) {
      console.error('Failed to load summary:', e);
    } finally {
      setLoadingCards(false);
    }
  }, [filterCompany, filterRegional, filterAsm, selectedSummaryMonth]);

  const loadTrend = useCallback(async () => {
    setLoadingCards(true);
    try {
      const data = await fetchSalaryTrend({ company_name: filterCompany, regional: filterRegional, asm: filterAsm });
      setTrend(data || []);
    } catch (e) {
      console.error('Failed to load trend:', e);
    } finally {
      setLoadingCards(false);
    }
  }, [filterCompany, filterRegional, filterAsm]);

  const loadAgents = useCallback(
    async (offset = 0) => {
      setLoading(true);
      try {
        const res = await fetchSalaryAgents({
          q: debouncedSearch || undefined,
          company_name: filterCompany,
          regional: filterRegional,
          asm: filterAsm,
          limit: PAGE_SIZE,
          offset,
        });
        setAgents(offset === 0 ? res?.items || [] : (prev) => [...(prev || []), ...(res?.items || [])]);
        setTotalAgents(res?.total || 0);
      } catch (e) {
        console.error('Failed to load agents:', e);
      } finally {
        setLoading(false);
      }
    },
    [debouncedSearch, filterCompany, filterRegional, filterAsm]
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
      {/* ===== Card 1: Statistici Salarii (2x2 grid) ===== */}
      <div className="glass rounded-3xl p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-600 dark:text-slate-300">Statistici Salarii</h3>
          {loadingCards && <RefreshCw size={14} className="animate-spin text-slate-400" />}
        </div>
        <div className="grid grid-cols-2 gap-3">
          {/* Row 1: Total Salarii + Perioada */}
          <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <div className="text-xs font-bold text-slate-500">Total Salarii</div>
            <div className="mt-1 text-2xl font-black text-slate-800 dark:text-white">
              {overview ? `${formatCurrency(overview.total)} RON` : '—'}
            </div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
            <div className="text-xs font-bold text-slate-500">Perioada</div>
            <div className="mt-1 text-sm font-bold text-slate-700 dark:text-slate-300">
              {overview ? formatMonthSpan(overview.months_span) : '—'}
            </div>
            <div className="text-xs text-slate-400">{overview?.agent_count ?? 0} agenti</div>
          </div>
          {/* Row 2: Mobiup + Mobicell */}
          <div className="rounded-2xl bg-emerald-50 p-3 dark:bg-emerald-950/30">
            <div className="text-xs font-bold text-emerald-600 dark:text-emerald-400">Mobiup</div>
            <div className="mt-1 text-2xl font-black text-emerald-600 dark:text-emerald-400">
              {overview ? `${formatCurrency(mobiupTotal)} RON` : '—'}
            </div>
          </div>
          <div className="rounded-2xl bg-indigo-50 p-3 dark:bg-indigo-950/30">
            <div className="text-xs font-bold text-indigo-600 dark:text-indigo-400">Mobicell</div>
            <div className="mt-1 text-2xl font-black text-indigo-600 dark:text-indigo-400">
              {overview ? `${formatCurrency(mobicellTotal)} RON` : '—'}
            </div>
          </div>
        </div>
      </div>

      {/* ===== Card 2: Salarii vs Vanzari (unificat) ===== */}
      <div className="glass rounded-3xl p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-bold text-slate-600 dark:text-slate-300">
            Salarii vs Vânzări
          </h3>
          <div className="flex items-center gap-2">
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
        <div className="max-h-60 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white dark:bg-slate-900">
              <tr className="border-b border-slate-200 text-xs uppercase text-slate-500 dark:border-slate-700">
                <SortableHeader label="Locatie" active={summarySort.key === 'locatie'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'locatie'))} className="pb-2 text-left text-xs" />
                <SortableHeader label="Firma" active={summarySort.key === 'company_name'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'company_name'))} className="pb-2 text-left text-xs" />
                <SortableHeader label="Salariu" active={summarySort.key === 'total_salary'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'total_salary'))} className="pb-2 text-right text-xs" />
                <SortableHeader label="Vanzari" active={summarySort.key === 'total_sales'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'total_sales'))} className="pb-2 text-right text-xs" />
                <SortableHeader label="%*" title={RATIO_HELP_TEXT} active={summarySort.key === 'ratio'} direction={summarySort.dir} onClick={() => setSummarySort(s => toggleSort(s, 'ratio'))} className="pb-2 text-right text-xs" />
              </tr>
            </thead>
            <tbody>
              {sortedSummary.length === 0 && !loadingCards && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-xs text-slate-400">Fara date</td>
                </tr>
              )}
              {sortedSummary.map((item) => (
                <tr key={`${item.locatie ?? item.site_code}-${item.company_name}`} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-medium text-slate-700 dark:text-slate-200">
                    {item.locatie ?? item.site_code}
                  </td>
                  <td className={`py-2 text-xs font-bold ${COMPANY_COLORS[item.company_name] ?? 'text-slate-500'}`}>
                    {item.company_name}
                  </td>
                  <td className="py-2 text-right font-mono text-slate-600 dark:text-slate-300">
                    {formatCurrency(item.total_salary)}
                  </td>
                  <td className="py-2 text-right font-mono text-slate-500">
                    {formatCurrency(item.total_sales)}
                  </td>
                  <td
                    className="py-2 text-right text-xs font-semibold tabular-nums"
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
          * % = salarii / vanzari; culorile sunt raportate la media ponderata a randurilor afisate.
        </p>
      </div>

      {/* ===== Card 3: Trend (Evolutie Salarii vs Vanzari) ===== */}
      <div className="glass rounded-3xl p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-600 dark:text-slate-300">Evolutie Salarii vs Vanzari</h3>
          {loadingCards && <RefreshCw size={14} className="animate-spin text-slate-400" />}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase text-slate-500 dark:border-slate-700">
                <SortableHeader label="Luna" active={trendSort.key === 'month'} direction={trendSort.dir} onClick={() => setTrendSort(s => toggleSort(s, 'month'))} className="pb-2 text-left text-xs" />
                <SortableHeader label="Salarii" active={trendSort.key === 'total_salary'} direction={trendSort.dir} onClick={() => setTrendSort(s => toggleSort(s, 'total_salary'))} className="pb-2 text-right text-xs" />
                <SortableHeader label="Vanzari" active={trendSort.key === 'total_sales'} direction={trendSort.dir} onClick={() => setTrendSort(s => toggleSort(s, 'total_sales'))} className="pb-2 text-right text-xs" />
                <SortableHeader label="%*" title={RATIO_HELP_TEXT} active={trendSort.key === 'ratio'} direction={trendSort.dir} onClick={() => setTrendSort(s => toggleSort(s, 'ratio'))} className="pb-2 text-right text-xs" />
              </tr>
            </thead>
            <tbody>
              {sortedTrend.length === 0 && !loadingCards && (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-xs text-slate-400">Fara date</td>
                </tr>
              )}
              {sortedTrend.map((t) => {
                const ratio = getSalarySalesRatio(t.total_salary, t.total_sales);
                return (
                  <tr key={t.month} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-medium text-slate-700 dark:text-slate-200">{t.month}</td>
                    <td className="py-2 text-right font-mono text-slate-600 dark:text-slate-300">{formatCurrency(t.total_salary)}</td>
                    <td className="py-2 text-right font-mono text-slate-500">{formatCurrency(t.total_sales)}</td>
                    <td
                      className="py-2 text-right text-xs font-semibold tabular-nums"
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
            * % = salarii / vanzari; culorile sunt raportate la media ponderata a randurilor afisate.
          </p>
        </div>
      </div>

      {/* ===== Card 4: Evolutie Salarii Lunar (Area Chart) ===== */}
      <div className="glass rounded-3xl p-4">
        <h3 className="mb-3 text-sm font-bold text-slate-600 dark:text-slate-300">Evolutie Salarii Lunara</h3>
        <SalaryAreaChart data={evolution} />
      </div>

      {/* ===== Card 5: Agenti (unificat) ===== */}
      <div className="glass rounded-3xl overflow-hidden">
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
              {/* Search */}
              <div className="relative">
                <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Cauta..."
                  value={search}
                  onChange={(e) => handleSearchChange(e.target.value)}
                  className="w-32 rounded-lg border border-slate-200 bg-white/80 py-1.5 pl-7 pr-2 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-200"
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

        {/* Table Header */}
        <div className="grid grid-cols-6 bg-slate-100 px-4 py-2 text-xs font-bold uppercase tracking-wider text-slate-500 dark:bg-slate-800">
          <div className="col-span-2">Nume</div>
          <div>Magazin</div>
          <div className="text-right">Nr Luni</div>
          <div className="text-right">Medie/Luna</div>
          <div className="text-right">Total</div>
        </div>

        {/* Table Body */}
        <div className="max-h-72 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
          {(!agents || agents.length === 0) && !loading && (
            <div className="py-12 text-center text-sm text-slate-400">
              Nu s-au gasit agenti
            </div>
          )}
          {agents?.map((agent) => (
            <div
              key={`${agent.cnp}-${agent.company_name}`}
              onClick={() => setDrawer({ cnp: agent.cnp ?? '', fullName: agent.full_name })}
              className="grid grid-cols-6 cursor-pointer items-center px-4 py-3 text-sm transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50"
            >
              <div className="col-span-2 font-semibold text-slate-800 dark:text-white">
                {agent.full_name}
              </div>
              <div className={`font-medium ${COMPANY_COLORS[agent.company_name] ?? 'text-slate-500'}`}>
                {agent.locatie ?? agent.company_name}
              </div>
              <div className="text-right text-slate-500">{agent.month_count}</div>
              <div className="text-right font-mono text-slate-500">
                {formatCurrency(agent.avg_salary)} RON
              </div>
              <div className="text-right font-bold text-slate-800 dark:text-white">
                {formatCurrency(agent.total_salary)} RON
              </div>
            </div>
          ))}
          {loading && (!agents || agents.length === 0) && (
            <div className="flex items-center justify-center py-12">
              <RefreshCw size={20} className="animate-spin text-indigo-500" />
            </div>
          )}
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
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 disabled:opacity-40 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
              >
                Inapoi
              </button>
              <button
                onClick={() => { const p = page + 1; setPage(p); loadAgents(p * PAGE_SIZE); }}
                disabled={!hasMore}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 disabled:opacity-40 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
              >
                Inainte
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Drawer */}
      <SalaryDrawer
        cnp={drawer?.cnp ?? ''}
        fullName={drawer?.fullName ?? ''}
        isOpen={!!drawer}
        onClose={() => setDrawer(null)}
      />
    </div>
  );
}
