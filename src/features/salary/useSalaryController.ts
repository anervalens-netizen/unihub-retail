import { useCallback, useEffect, useMemo, useState } from 'react';

import { getApiErrorMessage } from '../../api/client';
import { fetchSalariiOverview, fetchSalaryAgents, fetchSalaryEvolution, fetchSalarySummary, fetchSalaryTrend, type SalariiOverview, type SalaryAgentSummary, type SalaryComparisonPoint, type SalaryEvolutionPoint, type SalaryTrendMonth } from '../../api/salarii';
import type { AppFilters } from '../../lib/appFilters';
import { ALL_FIRMS, ALL_SCOPE } from '../../lib/filterValues';
import { useSalaryExport } from './SalaryExportControls';
import { PAGE_SIZE, sortSummary, sortTrend, weightedRatioAverage, type SortState, type SummarySort, type TrendSort } from './model';

export interface SalaryDrawerState { personId: string; fullName: string }
export type SalaryView = 'overview' | 'stores' | 'agents';
type ReadPath = 'overview' | 'summary' | 'trend' | 'agents';
const EMPTY_ERROR = {
  overview: 'Datele de tip statistici nu au putut fi încărcate.',
  summary: 'Comparația salarii vs vânzări nu a putut fi încărcată.',
  trend: 'Evoluția lunară nu a putut fi încărcată.',
  agents: 'Lista de agenți nu a putut fi încărcată.',
} as const;

type SetReadErrors = (
  next: Partial<Record<ReadPath, string>> | ((previous: Partial<Record<ReadPath, string>>) => Partial<Record<ReadPath, string>>),
) => void;

function updateReadErrors(setter: SetReadErrors, path: ReadPath, mutator: (previous: Partial<Record<ReadPath, string>>) => Partial<Record<ReadPath, string>>) {
  setter((previous) => mutator(previous));
}

export function useSalaryController(globalFilters?: AppFilters) {
  const [salaryView, setSalaryView] = useState<SalaryView>('overview');
  const [overview, setOverview] = useState<SalariiOverview | null>(null);
  const [evolution, setEvolution] = useState<SalaryEvolutionPoint[]>([]);
  const [agents, setAgents] = useState<SalaryAgentSummary[]>([]);
  const [totalAgents, setTotalAgents] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(0);
  const [drawer, setDrawer] = useState<SalaryDrawerState | null>(null);
  const [summary, setSummary] = useState<SalaryComparisonPoint[]>([]);
  const [trend, setTrend] = useState<SalaryTrendMonth[]>([]);
  const [summaryMonth, setSummaryMonth] = useState<string | null>(null);
  const [selectedSummaryMonth, setSelectedSummaryMonth] = useState('');
  const [loadingCards, setLoadingCards] = useState(false);
  const [summarySort, setSummarySort] = useState<SortState<SummarySort>>({ key: 'total_salary', dir: 'desc' });
  const [trendSort, setTrendSort] = useState<SortState<TrendSort>>({ key: 'month', dir: 'desc' });
  const [readErrors, setReadErrors] = useState<Partial<Record<ReadPath, string>>>({});
  const salaryExport = useSalaryExport();
  const filterCompany = globalFilters?.firma !== ALL_FIRMS ? globalFilters?.firma : undefined;
  const filterRegional = globalFilters?.rm !== ALL_SCOPE ? globalFilters?.rm : undefined;
  const filterSiteCode = globalFilters?.magazin.length ? globalFilters.magazin : undefined;
  const scope = useMemo(() => ({ company_name: filterCompany, site_code: filterSiteCode, regional: filterRegional }), [filterCompany, filterRegional, filterSiteCode]);

  useEffect(() => { const timer = setTimeout(() => setDebouncedSearch(search), 300); return () => clearTimeout(timer); }, [search]);

  const clearError = useCallback((path: ReadPath) => {
    updateReadErrors(setReadErrors, path, (previous) => {
      if (previous[path] === undefined) return previous;
      const { [path]: _drop, ...rest } = previous;
      return rest;
    });
  }, []);

  const setError = useCallback((path: ReadPath, message: string) => {
    updateReadErrors(setReadErrors, path, (previous) => ({ ...previous, [path]: message }));
  }, []);

  const loadOverview = useCallback(async () => {
    setOverview(null); setEvolution([]); clearError('overview');
    try {
      const [nextOverview, nextEvolution] = await Promise.all([fetchSalariiOverview(scope), fetchSalaryEvolution(scope)]);
      setOverview(nextOverview); setEvolution(nextEvolution);
    } catch (error) {
      console.error('Failed to load overview:', error);
      setError('overview', getApiErrorMessage(error, EMPTY_ERROR.overview));
    }
  }, [clearError, scope, setError]);

  const loadSummary = useCallback(async () => {
    setLoadingCards(true); setSummary([]); setSummaryMonth(null); clearError('summary');
    try {
      let year: number | undefined; let month: number | undefined;
      if (/^\d{4}-\d{2}$/.test(selectedSummaryMonth)) [year, month] = selectedSummaryMonth.split('-').map(Number);
      const data = await fetchSalarySummary({ ...scope, year, month });
      setSummary(data.items || []); setSummaryMonth(data.month);
    } catch (error) {
      console.error('Failed to load summary:', error);
      setError('summary', getApiErrorMessage(error, EMPTY_ERROR.summary));
    } finally { setLoadingCards(false); }
  }, [clearError, scope, selectedSummaryMonth, setError]);

  const loadTrend = useCallback(async () => {
    setLoadingCards(true); setTrend([]); clearError('trend');
    try { setTrend(await fetchSalaryTrend(scope)); }
    catch (error) {
      console.error('Failed to load trend:', error);
      setError('trend', getApiErrorMessage(error, EMPTY_ERROR.trend));
    } finally { setLoadingCards(false); }
  }, [clearError, scope, setError]);

  const loadAgents = useCallback(async (offset = 0, reset = false) => {
    setLoading(true);
    if (reset) { setAgents([]); setTotalAgents(0); }
    clearError('agents');
    try {
      const response = await fetchSalaryAgents({ ...scope, q: debouncedSearch || undefined, limit: PAGE_SIZE, offset });
      setAgents(response?.items || []); setTotalAgents(response?.total || 0);
    } catch (error) {
      console.error('Failed to load agents:', error);
      setError('agents', getApiErrorMessage(error, EMPTY_ERROR.agents));
    } finally { setLoading(false); }
  }, [clearError, debouncedSearch, scope, setError]);

  useEffect(() => { void loadOverview(); }, [loadOverview]);
  useEffect(() => { void loadSummary(); }, [loadSummary]);
  useEffect(() => { void loadTrend(); }, [loadTrend]);
  useEffect(() => { setPage(0); void loadAgents(0, true); }, [loadAgents]);

  const retryRead = useCallback((path: ReadPath) => {
    clearError(path);
    if (path === 'overview') void loadOverview();
    else if (path === 'summary') void loadSummary();
    else if (path === 'trend') void loadTrend();
    else void loadAgents(page * PAGE_SIZE);
  }, [clearError, loadAgents, loadOverview, loadSummary, loadTrend, page]);

  const handleSearchChange = (value: string) => { setSearch(value); setPage(0); };
  const resetSearch = () => { setSearch(''); setDebouncedSearch(''); setPage(0); };
  const goToPage = (nextPage: number) => { setPage(nextPage); void loadAgents(nextPage * PAGE_SIZE); };
  const sortedSummary = useMemo(() => sortSummary(summary, summarySort), [summary, summarySort]);
  const sortedTrend = useMemo(() => sortTrend(trend, trendSort), [trend, trendSort]);
  const startStoreExport = () => { const period = summaryMonth?.match(/^(\d{4})-(\d{2})$/); return salaryExport.start({ export_kind: 'store_summary', ...scope, site_code: filterSiteCode ?? [], year: period ? Number(period[1]) : undefined, month: period ? Number(period[2]) : undefined }); };
  const startTrendExport = () => salaryExport.start({ export_kind: 'monthly_trend', ...scope, site_code: filterSiteCode ?? [] });
  const startAgentsExport = () => salaryExport.start({ export_kind: 'agents', ...scope, site_code: filterSiteCode ?? [], q: debouncedSearch || undefined });
  return {
    salaryView, setSalaryView, overview, evolution, agents, totalAgents, loading, search, debouncedSearch, page, drawer, setDrawer,
    selectedSummaryMonth, setSelectedSummaryMonth, summaryMonth, loadingCards, summarySort, setSummarySort, trendSort, setTrendSort,
    sortedSummary, sortedTrend, summaryRatioAverage: weightedRatioAverage(summary), trendRatioAverage: weightedRatioAverage(trend),
    hasMore: (page + 1) * PAGE_SIZE < totalAgents, salaryExport, handleSearchChange, resetSearch, goToPage,
    startStoreExport, startTrendExport, startAgentsExport,
    readErrors, retryRead,
  };
}

export type SalaryController = ReturnType<typeof useSalaryController>;
