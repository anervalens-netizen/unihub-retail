import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import {
  fetchSalariiOverview,
  fetchSalaryAgents,
  fetchSalaryEvolution,
  fetchSalariiStores,
  fetchSalarySummary,
  fetchSalaryTrend,
} from '../api/salarii';
import type {
  SalariiOverview,
  SalaryAgentSummary,
  SalaryEvolutionPoint,
  SalaryStore,
  SalaryComparisonPoint,
  SalaryTrendMonth,
} from '../api/salarii';
import type { AppFilters } from './MainLayout';
import { SalaryAreaChart } from './SalaryAreaChart';
import { SalaryDrawer } from './SalaryDrawer';

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
  const [companyFilter, setCompanyFilter] = useState('');
  const [storeFilter, setStoreFilter] = useState('');
  const [availableStores, setAvailableStores] = useState<SalaryStore[]>([]);
  const [page, setPage] = useState(0);
  const [drawer, setDrawer] = useState<DrawerState | null>(null);
  const [summary, setSummary] = useState<SalaryComparisonPoint[]>([]);
  const [trend, setTrend] = useState<SalaryTrendMonth[]>([]);
  const [summaryMonth, setSummaryMonth] = useState<string | null>(null);
  const [selectedSummaryMonth, setSelectedSummaryMonth] = useState<string>('');
  const [loadingCards, setLoadingCards] = useState(false);
  const PAGE_SIZE = 50;

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const loadOverview = useCallback(async () => {
    try {
      const [ov, ev] = await Promise.all([
        fetchSalariiOverview(),
        fetchSalaryEvolution(),
      ]);
      setOverview(ov);
      setEvolution(ev);
    } catch (e) {
      console.error('Failed to load overview:', e);
    }
  }, []);

  const loadStores = useCallback(async (company?: string) => {
    try {
      const stores = await fetchSalariiStores(company || undefined);
      setAvailableStores(stores);
    } catch (e) {
      console.error('Failed to load stores:', e);
    }
  }, []);

  const loadSummary = useCallback(async () => {
    setLoadingCards(true);
    try {
      const firma = globalFilters?.firma && globalFilters.firma !== 'Toate' ? globalFilters.firma : undefined;
      // Parse year/month from selectedSummaryMonth if set, otherwise API uses latest
      let year: number | undefined;
      let month: number | undefined;
      if (selectedSummaryMonth && /^\d{4}-\d{2}$/.test(selectedSummaryMonth)) {
        [year, month] = selectedSummaryMonth.split('-').map(Number);
      }
      const data = await fetchSalarySummary({ company_name: firma, year, month });
      setSummary(data.items || []);
      setSummaryMonth(data.month);
    } catch (e) {
      console.error('Failed to load summary:', e);
    } finally {
      setLoadingCards(false);
    }
  }, [globalFilters, selectedSummaryMonth]);

  const loadTrend = useCallback(async () => {
    setLoadingCards(true);
    try {
      const firma = globalFilters?.firma && globalFilters.firma !== 'Toate' ? globalFilters.firma : undefined;
      const data = await fetchSalaryTrend({ company_name: firma });
      setTrend(data || []);
    } catch (e) {
      console.error('Failed to load trend:', e);
    } finally {
      setLoadingCards(false);
    }
  }, [globalFilters]);

  const loadAgents = useCallback(
    async (offset = 0) => {
      setLoading(true);
      try {
        const res = await fetchSalaryAgents({
          q: debouncedSearch || undefined,
          company_name: companyFilter || undefined,
          site_code: storeFilter || undefined,
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
    [debouncedSearch, companyFilter, storeFilter]
  );

  useEffect(() => { loadOverview(); loadStores(); }, []);
  useEffect(() => { loadSummary(); }, [globalFilters, selectedSummaryMonth]);
  useEffect(() => { loadTrend(); }, [globalFilters]);
  useEffect(() => { setPage(0); loadAgents(0); }, [loadAgents]);

  function handleSearchChange(val: string) {
    setSearch(val);
    setPage(0);
  }

  function handleCompanyChange(val: string) {
    setCompanyFilter(val);
    setStoreFilter('');
    loadStores(val || undefined);
    setPage(0);
  }

  function handleStoreChange(val: string) {
    setStoreFilter(val);
    setPage(0);
  }

  function resetFilters() {
    setSearch('');
    setDebouncedSearch('');
    setCompanyFilter('');
    setStoreFilter('');
    loadStores();
    setPage(0);
  }

  const hasMore = (page + 1) * PAGE_SIZE < totalAgents;

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
              {overview && (() => {
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
                <th className="pb-2 text-left">Locatie</th>
                <th className="pb-2 text-left">Firma</th>
                <th className="pb-2 text-right">Salariu</th>
                <th className="pb-2 text-right">Vanzari</th>
                <th className="pb-2 text-right">%</th>
              </tr>
            </thead>
            <tbody>
              {summary.length === 0 && !loadingCards && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-xs text-slate-400">Fara date</td>
                </tr>
              )}
              {summary.map((item) => (
                <tr key={`${item.site_code}-${item.company_name}`} className="border-b border-slate-100 dark:border-slate-800">
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
                  <td className={`py-2 text-right text-xs font-medium ${item.ratio > 50 ? 'text-rose-500' : 'text-emerald-500'}`}>
                    {item.ratio.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
                <th className="pb-2 text-left">Luna</th>
                <th className="pb-2 text-right">Salarii</th>
                <th className="pb-2 text-right">Vanzari</th>
                <th className="pb-2 text-right">%</th>
              </tr>
            </thead>
            <tbody>
              {trend.length === 0 && !loadingCards && (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-xs text-slate-400">Fara date</td>
                </tr>
              )}
              {trend.map((t) => {
                const ratio = t.total_sales > 0 ? (t.total_salary / t.total_sales) * 100 : 0;
                return (
                  <tr key={t.month} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-medium text-slate-700 dark:text-slate-200">{t.month}</td>
                    <td className="py-2 text-right font-mono text-slate-600 dark:text-slate-300">{formatCurrency(t.total_salary)}</td>
                    <td className="py-2 text-right font-mono text-slate-500">{formatCurrency(t.total_sales)}</td>
                    <td className={`py-2 text-right text-xs font-medium ${ratio > 50 ? 'text-rose-500' : 'text-emerald-500'}`}>
                      {ratio.toFixed(1)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
              {/* Firma filter */}
              <select
                value={companyFilter}
                onChange={(e) => handleCompanyChange(e.target.value)}
                className="rounded-lg border border-slate-200 bg-white/80 py-1.5 px-2 text-xs text-slate-700 focus:border-indigo-400 focus:outline-none dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-200"
              >
                <option value="">Toate firmele</option>
                <option value="Mobicell">Mobicell</option>
                <option value="Mobiup">Mobiup</option>
              </select>
              {/* Magazin filter */}
              <select
                value={storeFilter}
                onChange={(e) => handleStoreChange(e.target.value)}
                className="rounded-lg border border-slate-200 bg-white/80 py-1.5 px-2 text-xs text-slate-700 focus:border-indigo-400 focus:outline-none dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-200"
              >
                <option value="">Toate magazinele</option>
                {availableStores.map((s) => (
                  <option key={s.site_code} value={s.site_code}>
                    {s.locatie ?? s.site_code}
                  </option>
                ))}
              </select>
              {(search || companyFilter || storeFilter) && (
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
        <div className="grid grid-cols-5 bg-slate-100 px-4 py-2 text-xs font-bold uppercase tracking-wider text-slate-500 dark:bg-slate-800">
          <div className="col-span-2">Nume</div>
          <div>Magazin</div>
          <div className="text-right">Nr Luni</div>
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
              className="grid grid-cols-5 cursor-pointer items-center px-4 py-3 text-sm transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50"
            >
              <div className="col-span-2 font-semibold text-slate-800 dark:text-white">
                {agent.full_name}
              </div>
              <div className={`font-medium ${COMPANY_COLORS[agent.company_name] ?? 'text-slate-500'}`}>
                {agent.locatie ?? agent.company_name}
              </div>
              <div className="text-right text-slate-500">{agent.month_count}</div>
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