import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Calculator,
  CheckCircle2,
  ChevronDown,
  Download,
  PencilLine,
  RefreshCw,
  RotateCcw,
  Save,
  Store,
  Users,
  X,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  ComposedChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  calculateTargetScenario,
  downloadTargetScenario,
  fetchTargetCalculatorContext,
  fetchTargetScenario,
  fetchTargetScenarios,
  fetchTargetStoreDetail,
  finalizeTargetScenario,
  saveTargetFinalValues,
  type TargetCalculatorContext,
  type TargetRegionalSummary,
  type TargetScenario,
  type TargetScenarioRow,
  type TargetSourceMonth,
  type TargetStoreDetail,
} from '../api/targetCalculator';
import { formatCurrency, formatPercent } from '../lib/formatters';
import { formatMonthLabel, shiftMonth } from '../lib/dates';

const inputCls = 'rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';
const finalInputCls = 'rounded-xl border-2 border-amber-300 bg-amber-50 px-3 py-2 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-400 dark:border-amber-600 dark:bg-amber-950/30 dark:text-slate-100';

function monthLabel(month: string): string {
  return formatMonthLabel(month);
}

function isPreviousYearPeriod(role: string): boolean {
  return role === 'previous_year_reference'
    || role === 'year_over_year'
    || role.startsWith('seasonality_');
}

const HIDDEN_DISPLAY_SOURCE_MONTHS = new Set(['2023-06', '2023-07']);

function shouldHideSourcePeriod(period: TargetSourceMonth): boolean {
  return HIDDEN_DISPLAY_SOURCE_MONTHS.has(period.month);
}

function shouldShowHistoricalTarget(period: { month: string }): boolean {
  return !period.month.startsWith('2024-');
}

function sum(values: number[]): number {
  return Math.round(values.reduce((total, value) => total + value, 0) * 100) / 100;
}

function percentChangeValue(newValue: number, baseValue: number): number | null {
  if (baseValue <= 0) return null;
  return Math.round(((newValue - baseValue) * 100 / baseValue) * 100) / 100;
}

function formatOptionalCurrency(value: number | null): string {
  return value == null ? 'Necompletat' : formatCurrency(value);
}

function formatFactor(value?: number | null): string {
  return value == null ? '-' : `${value.toFixed(2)}x`;
}

function formatSignedPercent(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value > 0 ? '+' : ''}${formatPercent(value)}`;
}

function percentTone(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return 'text-slate-500 dark:text-slate-400';
  if (value > 0.01) return 'text-emerald-600 dark:text-emerald-400';
  if (value < -0.01) return 'text-red-600 dark:text-red-400';
  return 'text-slate-600 dark:text-slate-300';
}

function flagLabel(flag: string): string {
  const labels: Record<string, string> = {
    NEW_STORE: 'nou',
    LOW_HISTORY: 'istoric redus',
    EXTREME_SEASONALITY: 'sez. extrema',
    FLOOR_APPLIED: 'floor',
    CAP_APPLIED: 'cap',
    SEASONALITY_CAPPED: 'sez. limitata',
    TREND_ADJUSTMENT_CAPPED: 'trend limitat',
  };
  return labels[flag] ?? flag.toLowerCase().replaceAll('_', ' ');
}

type StoreChartMode = 'sales' | 'bon2acc' | 'focus';

const STORE_CHART_MODES: Array<{ mode: StoreChartMode; label: string }> = [
  { mode: 'sales', label: 'Vanzari' },
  { mode: 'bon2acc', label: 'Bon2Acc' },
  { mode: 'focus', label: 'Focus/Acc' },
];

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(query);
    setMatches(media.matches);
    const listener = (event: MediaQueryListEvent) => setMatches(event.matches);
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }, [query]);

  return matches;
}

function recalculateVisibleScenario(scenario: TargetScenario, rows: TargetScenarioRow[]): TargetScenario {
  const regional = new Map<string, TargetRegionalSummary>();
  rows.forEach((row) => {
    const item = regional.get(row.regional) ?? {
      regional: row.regional,
      store_count: 0,
      floor_total: 0,
      proposed_total: 0,
      final_total: 0,
      current_month: null,
      current_forecast_total: 0,
      proposed_growth_vs_current_pct: null,
      final_growth_vs_current_pct: null,
      last_year_base_month: null,
      last_year_target_month: null,
      last_year_base_total: 0,
      last_year_target_total: 0,
      last_year_growth_pct: null,
    };
    item.store_count += 1;
    item.floor_total += row.floor_target;
    item.proposed_total += row.proposed_target;
    item.final_total += row.final_target ?? 0;
    const currentPeriod = row.history.find((period) => period.role === 'floor_reference');
    item.current_month = row.calculation_details.current_month ?? currentPeriod?.month ?? item.current_month;
    item.current_forecast_total += Number(row.calculation_details.current_forecast ?? currentPeriod?.realized ?? 0);

    const lastYear = row.calculation_details.seasonality?.store_years?.find((period) => period.year_offset === 1);
    const basePeriod = row.history.find((period) => period.role === 'seasonality_base_y1');
    const targetPeriod = row.history.find((period) => period.role === 'seasonality_target_y1');
    item.last_year_base_month = lastYear?.base_month ?? basePeriod?.month ?? item.last_year_base_month;
    item.last_year_target_month = lastYear?.target_month ?? targetPeriod?.month ?? item.last_year_target_month;
    item.last_year_base_total += Number(lastYear?.base_value ?? basePeriod?.realized ?? 0);
    item.last_year_target_total += Number(lastYear?.target_value ?? targetPeriod?.realized ?? 0);
    regional.set(row.regional, item);
  });
  const regionalSummary = Array.from(regional.values()).map((item) => ({
    ...item,
    proposed_growth_vs_current_pct: percentChangeValue(item.proposed_total, item.current_forecast_total),
    final_growth_vs_current_pct: percentChangeValue(item.final_total, item.current_forecast_total),
    last_year_growth_pct: percentChangeValue(item.last_year_target_total, item.last_year_base_total),
  }));
  const finalTotal = sum(rows.map((row) => row.final_target ?? 0));
  return {
    ...scenario,
    rows,
    final_total: finalTotal,
    remaining_difference: Math.round((scenario.total_target - finalTotal) * 100) / 100,
    pending_final_count: rows.filter((row) => row.final_target == null).length,
    manual_adjustments_count: rows.filter((row) => row.final_target != null && Math.abs(row.final_target - row.proposed_target) > 0.01).length,
    regional_summary: regionalSummary.sort((left, right) => left.regional.localeCompare(right.regional)),
  };
}

function SummaryCard({ label, value, detail, emphasis }: {
  label: string;
  value: string;
  detail?: string;
  emphasis?: 'good' | 'warning' | 'attention';
}) {
  const color = emphasis === 'good'
    ? 'text-emerald-600 dark:text-emerald-400'
    : emphasis === 'warning'
      ? 'text-amber-600 dark:text-amber-400'
      : emphasis === 'attention'
        ? 'text-amber-700 dark:text-amber-300'
      : 'text-slate-900 dark:text-slate-100';
  const surface = emphasis === 'attention'
    ? 'rounded-2xl border border-amber-300 bg-amber-50/80 p-4 min-w-0 dark:border-amber-700 dark:bg-amber-950/20'
    : 'glass rounded-2xl p-4 min-w-0';
  return (
    <div className={surface}>
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 text-xl font-bold tabular-nums ${color}`}>{value}</p>
      {detail && <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{detail}</p>}
    </div>
  );
}

function managerTargetStatus(proposed: number, finalValue: number): {
  label: string;
  badgeClass: string;
  valueClass: string;
} {
  const difference = finalValue - proposed;
  const increasePct = proposed > 0 ? (difference / proposed) * 100 : 0;
  if (difference < -0.01) {
    return {
      label: 'Sub calculator',
      badgeClass: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
      valueClass: 'text-red-600 dark:text-red-400',
    };
  }
  if (increasePct > 5) {
    return {
      label: 'Peste +5%',
      badgeClass: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
      valueClass: 'text-amber-600 dark:text-amber-400',
    };
  }
  return {
    label: 'In limita',
    badgeClass: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    valueClass: 'text-emerald-600 dark:text-emerald-400',
  };
}

function StoreDetailDrawer({ scenarioId, siteCode, onClose }: {
  scenarioId: number;
  siteCode: string | null;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<TargetStoreDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chartMode, setChartMode] = useState<StoreChartMode>('sales');
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!siteCode) return;
    setChartMode('sales');
    setLoading(true);
    setError(null);
    void fetchTargetStoreDetail(scenarioId, siteCode)
      .then(setDetail)
      .catch((err) => {
        console.error(err);
        setError('Nu am putut incarca detaliile locatiei.');
      })
      .finally(() => setLoading(false));
  }, [scenarioId, siteCode]);

  if (!siteCode) return null;

  const latest = detail?.latest;
  const best = detail?.best_month;
  const percentageMetric = chartMode === 'bon2acc' ? 'bon2acc_pct' : 'focus_pct';
  const percentageLabel = chartMode === 'bon2acc' ? 'Bon2Acc' : 'Focus/Acc';
  const chartTitle = chartMode === 'sales'
    ? 'Vanzari vs target - 16 luni'
    : `${percentageLabel} - 16 luni`;

  return (
    <div
      ref={overlayRef}
      onClick={(event) => {
        if (event.target === overlayRef.current) onClose();
      }}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm"
    >
      <div className="animate-slide-in-right flex h-full w-full flex-col bg-white shadow-2xl dark:bg-slate-950 sm:max-w-2xl">
        <div className="flex items-start justify-between border-b border-slate-200 px-4 py-4 dark:border-slate-800 sm:px-6">
          <div>
            <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-indigo-500">
              <Store size={14} /> Detalii locatie
            </p>
            <h2 className="mt-1 text-lg font-bold text-slate-900 dark:text-slate-100">
              {detail?.locatie ?? siteCode}
            </h2>
            {detail && (
              <p className="text-xs text-slate-500">
                {detail.site_code} · {detail.firma} · {detail.regional}
              </p>
            )}
          </div>
          <button onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {loading && <div className="py-12 text-center text-sm text-slate-500">Se incarca detaliile...</div>}
          {error && <div className="rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
          {!loading && detail && (
            <div className="space-y-4 pb-8">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <SummaryCard label="Vanzari ultima luna" value={formatCurrency(latest?.total_sales ?? 0)} detail={detail.cohort_month} />
                <SummaryCard label="% target" value={formatPercent(latest?.target_pct ?? null)} detail={formatCurrency(latest?.target_value ?? 0)} />
                <SummaryCard label="Bon mediu" value={latest?.avg_receipt == null ? '-' : formatCurrency(latest.avg_receipt)} detail={`${latest?.receipt_count ?? 0} bonuri`} />
                <SummaryCard label="Agenti activi" value={`${latest?.active_agents ?? 0}`} detail={`${detail.agents.length} in lista`} />
              </div>

              <div className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{chartTitle}</h3>
                    <p className="text-xs text-slate-500">
                      {chartMode === 'sales'
                        ? `Media: ${formatCurrency(detail.avg_sales_16m)}${best ? ` · Varf: ${monthLabel(best.month)} (${formatCurrency(best.total_sales)})` : ''}`
                        : 'Evolutie procentuala pe aceleasi 16 luni'}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {STORE_CHART_MODES.map((item) => (
                      <button
                        key={item.mode}
                        type="button"
                        onClick={() => setChartMode(item.mode)}
                        className={`rounded-full px-3 py-1.5 text-[11px] font-semibold transition-colors ${
                          chartMode === item.mode
                            ? 'bg-indigo-600 text-white shadow-sm'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                        }`}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="h-64">
                  {chartMode === 'sales' ? (
                    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                      <ComposedChart data={detail.history} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.16)" />
                        <XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={monthLabel} />
                        <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={(value) => `${Math.round(Number(value) / 1000)}k`} />
                        <Tooltip formatter={(value: number | string) => formatCurrency(Number(value))} />
                        <Legend />
                        <Bar dataKey="total_sales" name="Vanzari" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                        <Line type="monotone" dataKey="target_value" name="Target" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                      <ComposedChart data={detail.history} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.16)" />
                        <XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={monthLabel} />
                        <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={(value) => `${Number(value).toFixed(0)}%`} />
                        <Tooltip formatter={(value: number | string) => formatPercent(Number(value))} />
                        <Legend />
                        <Line
                          type="monotone"
                          dataKey={percentageMetric}
                          name={percentageLabel}
                          stroke={chartMode === 'bon2acc' ? '#10b981' : '#8b5cf6'}
                          strokeWidth={2.5}
                          dot={{ r: 3 }}
                          connectNulls
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
                  <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">KPI ultima luna</h3>
                  <div className="mt-3 space-y-2 text-xs">
                    <KpiRow label="Cantitate" value={(latest?.total_quantity ?? 0).toLocaleString('ro-RO')} />
                    <KpiRow label="Cartele" value={(latest?.cartele_qty ?? 0).toLocaleString('ro-RO')} />
                    <KpiRow label="Bon2Acc" value={formatPercent(latest?.bon2acc_pct ?? null)} />
                    <KpiRow label="Focus/Acc" value={formatPercent(latest?.focus_pct ?? null)} />
                    <KpiRow label="Zile cu vanzari" value={`${latest?.working_days ?? 0}`} />
                    <KpiRow label="Target calculat" value={formatCurrency(detail.proposed_target)} />
                    <KpiRow label="Final manager" value={formatOptionalCurrency(detail.final_target)} />
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
                    <Users size={15} /> Pondere agenti
                  </h3>
                  <div className="mt-3 space-y-3">
                    {detail.agents.length === 0 && <p className="text-xs text-slate-500">Nu exista agenti activi in luna cohortei.</p>}
                    {detail.agents.slice(0, 8).map((agent) => (
                      <div key={agent.agent}>
                        <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                          <span className="font-medium text-slate-700 dark:text-slate-200">{agent.agent}</span>
                          <span className="font-semibold text-indigo-600 dark:text-indigo-300">{formatPercent(agent.sales_share_pct)}</span>
                        </div>
                        <progress
                          className="target-agent-share"
                          max={100}
                          value={Math.min(Math.max(agent.sales_share_pct, 0), 100)}
                        >
                          {formatPercent(agent.sales_share_pct)}
                        </progress>
                        <div className="mt-1 flex justify-between text-[10px] text-slate-400">
                          <span>{formatCurrency(agent.total_sales)}</span>
                          <span>{agent.active_months_16}/16 luni active</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

    </div>
  );
}

function KpiRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2 dark:bg-slate-900/60">
      <span className="text-slate-500">{label}</span>
      <span className="font-semibold tabular-nums text-slate-800 dark:text-slate-100">{value}</span>
    </div>
  );
}

export function TargetCalculatorSubtab() {
  const [context, setContext] = useState<TargetCalculatorContext | null>(null);
  const [scenario, setScenario] = useState<TargetScenario | null>(null);
  const [regionalFilter, setRegionalFilter] = useState('all');
  const [targetMonth, setTargetMonth] = useState('');
  const [totalTarget, setTotalTarget] = useState('');
  const [minFloor, setMinFloor] = useState('');
  const [floorPct, setFloorPct] = useState('');
  const [seasonalityMode, setSeasonalityMode] = useState<'multi' | 'single'>('multi');
  const [logicOpen, setLogicOpen] = useState(false);
  const [selectedLocationCodes, setSelectedLocationCodes] = useState<string[]>([]);
  const [locationDropdownOpen, setLocationDropdownOpen] = useState(false);
  const [detailSiteCode, setDetailSiteCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dirtyRows, setDirtyRows] = useState<Set<string>>(() => new Set());
  const [savingRows, setSavingRows] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  const scenarioRef = useRef<TargetScenario | null>(null);
  const dirtyRowsRef = useRef<Set<string>>(new Set());
  const editVersionsRef = useRef<Map<string, number>>(new Map());
  const locationFilterRef = useRef<HTMLDivElement>(null);
  const dirty = dirtyRows.size > 0;
  const isDesktop = useMediaQuery('(min-width: 768px)');

  const replaceScenario = useCallback((next: TargetScenario | null) => {
    scenarioRef.current = next;
    setScenario(next);
  }, []);

  const clearLocalEdits = useCallback(() => {
    dirtyRowsRef.current = new Set();
    setDirtyRows(new Set());
    editVersionsRef.current.clear();
  }, []);

  const loadInitial = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextContext, recentScenarios] = await Promise.all([
        fetchTargetCalculatorContext(),
        fetchTargetScenarios(),
      ]);
      setContext(nextContext);
      setTargetMonth((current) => current || nextContext.suggested_target_month);
      setTotalTarget((current) => current || String(nextContext.suggested_total_target));
      setMinFloor((current) => current || String(nextContext.default_min_floor));
      setFloorPct((current) => current || String(nextContext.default_previous_month_floor_pct * 100));
      setSeasonalityMode((current) => current || (nextContext.default_seasonality_years > 1 ? 'multi' : 'single'));
      const activeScenarioId = scenarioRef.current?.id;
      if (activeScenarioId && dirtyRowsRef.current.size === 0) {
        replaceScenario(await fetchTargetScenario(activeScenarioId));
      } else if (!scenarioRef.current) {
        const currentDraft = recentScenarios.find((item) => item.target_month === nextContext.suggested_target_month);
        replaceScenario(currentDraft ? await fetchTargetScenario(currentDraft.id) : null);
        clearLocalEdits();
      }
    } catch (err) {
      console.error(err);
      setError('Nu am putut incarca calculatorul de target.');
    } finally {
      setLoading(false);
    }
  }, [clearLocalEdits, replaceScenario]);

  useEffect(() => {
    void loadInitial();
  }, [loadInitial]);

  useEffect(() => {
    scenarioRef.current = scenario;
  }, [scenario]);

  const regionals = useMemo(
    () => scenario?.regional_summary.map((item) => item.regional) ?? context?.regionals ?? [],
    [scenario, context],
  );
  const baseRows = useMemo(
    () => scenario?.rows.filter((row) => regionalFilter === 'all' || row.regional === regionalFilter) ?? [],
    [scenario, regionalFilter],
  );
  const locationOptions = useMemo(
    () => baseRows
      .slice()
      .sort((left, right) => left.locatie.localeCompare(right.locatie)),
    [baseRows],
  );
  const selectedLocationSet = useMemo(() => new Set(selectedLocationCodes), [selectedLocationCodes]);
  const filteredRows = useMemo(
    () => baseRows.filter((row) => selectedLocationSet.size === 0 || selectedLocationSet.has(row.site_code)),
    [baseRows, selectedLocationSet],
  );
  const forecastMonths = useMemo(() => {
    const months = new Set<string>();
    scenario?.rows.forEach((row) => {
      row.history.forEach((period) => {
        if (period.is_forecast) months.add(period.month);
      });
    });
    return months;
  }, [scenario]);
  const displaySourceMonths = useMemo(
    () => scenario?.source_months.filter((period) => !shouldHideSourcePeriod(period)) ?? [],
    [scenario],
  );
  const sourceChart = useMemo(() => {
    if (!scenario) return [];
    return displaySourceMonths.map((source) => {
      const values = filteredRows.map((row) => row.history.find((history) => history.month === source.month));
      const showTarget = shouldShowHistoricalTarget(source);
      return {
        month: monthLabel(source.month),
        target: showTarget ? sum(values.map((value) => value?.target ?? 0)) : 0,
        realized: sum(values.map((value) => value?.realized ?? 0)),
        actualRealized: sum(values.map((value) => value?.actual_realized ?? value?.realized ?? 0)),
        isForecast: values.some((value) => value?.is_forecast),
        showTarget,
      };
    });
  }, [scenario, displaySourceMonths, filteredRows]);
  const regionalChart = useMemo(
    () => scenario?.regional_summary.filter((item) => regionalFilter === 'all' || item.regional === regionalFilter) ?? [],
    [scenario, regionalFilter],
  );
  const activeSeasonalityLabel = useMemo(() => {
    const years = Number(scenario?.calculation_params?.seasonality_years ?? 1);
    return years > 1 ? `Multi-year ${years} ani` : 'Sezonalitate anul trecut';
  }, [scenario]);
  const displayWarnings = useMemo(
    () => scenario?.warnings.filter((warning) => {
      if (warning.startsWith('Formula foloseste sezonalitate')) return false;
      return !Array.from(HIDDEN_DISPLAY_SOURCE_MONTHS).some((month) => warning.includes(month));
    }) ?? [],
    [scenario],
  );

  useEffect(() => {
    const available = new Set(locationOptions.map((row) => row.site_code));
    setSelectedLocationCodes((current) => current.filter((siteCode) => available.has(siteCode)));
  }, [locationOptions]);

  useEffect(() => {
    if (!locationDropdownOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (!locationFilterRef.current?.contains(event.target as Node)) {
        setLocationDropdownOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setLocationDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [locationDropdownOpen]);

  const toggleLocationFilter = (siteCode: string) => {
    if (!siteCode) return;
    setSelectedLocationCodes((current) => (
      current.includes(siteCode)
        ? current.filter((item) => item !== siteCode)
        : [...current, siteCode]
    ));
  };

  const removeLocationFilter = (siteCode: string) => {
    setSelectedLocationCodes((current) => current.filter((item) => item !== siteCode));
  };

  const handleCalculate = async () => {
    const parsedTarget = Number(totalTarget);
    const parsedFloor = Number(minFloor);
    const parsedPct = Number(floorPct);
    if (!targetMonth || parsedTarget <= 0 || parsedFloor < 0 || parsedPct < 0) {
      setError('Completeaza parametrii de calcul cu valori valide.');
      return;
    }
    const existingTarget = scenarioRef.current;
    const recalculatingCurrentDraft = existingTarget?.target_month === targetMonth && existingTarget.status === 'draft';
    if (existingTarget?.target_month === targetMonth && existingTarget.status === 'finalized') {
      setError('Targetul acestei luni este finalizat si nu mai poate fi recalculat.');
      return;
    }
    if (recalculatingCurrentDraft && !window.confirm(
      'Recalculezi targetul acestei luni? Valorile finale si observatiile introduse pana acum vor fi resetate la noul calcul.',
    )) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (dirtyRowsRef.current.size > 0 && !recalculatingCurrentDraft) {
        await persistDraft();
      }
      const calculated = await calculateTargetScenario({
        target_month: targetMonth,
        total_target: parsedTarget,
        min_floor: parsedFloor,
        previous_month_floor_pct: parsedPct / 100,
        previous_month_cap_pct: context?.default_previous_month_cap_pct ?? 1.7,
        seasonality_years: seasonalityMode === 'multi' ? 3 : 1,
        expected_revision: recalculatingCurrentDraft
          ? existingTarget.revision
          : undefined,
      });
      replaceScenario(calculated);
      setRegionalFilter('all');
      clearLocalEdits();
    } catch (err) {
      console.error(err);
      setError('Calculul nu a putut fi salvat. Verifica parametrii si lunile cu date disponibile.');
    } finally {
      setBusy(false);
    }
  };

  const updateRow = (siteCode: string, field: 'final_target' | 'note', value: number | string | null) => {
    const current = scenarioRef.current;
    if (!current || current.status === 'finalized') return;
    const rows = current.rows.map((row) => (
      row.site_code === siteCode ? { ...row, [field]: value } : row
    ));
    replaceScenario(recalculateVisibleScenario(current, rows));
    editVersionsRef.current.set(siteCode, (editVersionsRef.current.get(siteCode) ?? 0) + 1);
    setDirtyRows((previous) => {
      const next = new Set(previous).add(siteCode);
      dirtyRowsRef.current = next;
      return next;
    });
  };

  const resetToProposal = () => {
    const current = scenarioRef.current;
    if (!current || current.status === 'finalized') return;
    const selectedCodes = new Set(
      current.rows
        .filter((row) => regionalFilter === 'all' || row.regional === regionalFilter)
        .map((row) => row.site_code),
    );
    const rows = current.rows.map((row) => (
      selectedCodes.has(row.site_code)
        ? { ...row, final_target: row.proposed_target, note: null }
        : row
    ));
    replaceScenario(recalculateVisibleScenario(current, rows));
    selectedCodes.forEach((siteCode) => {
      editVersionsRef.current.set(siteCode, (editVersionsRef.current.get(siteCode) ?? 0) + 1);
    });
    setDirtyRows((previous) => {
      const next = new Set(previous);
      selectedCodes.forEach((siteCode) => next.add(siteCode));
      dirtyRowsRef.current = next;
      return next;
    });
  };

  const persistRows = useCallback(async (siteCodes: string[]): Promise<TargetScenario | null> => {
    const current = scenarioRef.current;
    if (!current || current.status === 'finalized' || siteCodes.length === 0) return current;
    const rowSet = new Set(siteCodes);
    const rowsToSave = current.rows.filter((row) => rowSet.has(row.site_code));
    const submittedVersions = new Map(
      rowsToSave.map((row) => [row.site_code, editVersionsRef.current.get(row.site_code) ?? 0]),
    );
    setSavingRows((previous) => new Set([...previous, ...siteCodes]));
    try {
      const saved = await saveTargetFinalValues(
        current.id,
        current.revision,
        rowsToSave.map((row) => ({
          site_code: row.site_code,
          final_target: row.final_target,
          note: row.note,
        })),
      );
      const remainingDirty = new Set(dirtyRowsRef.current);
      submittedVersions.forEach((version, siteCode) => {
        if ((editVersionsRef.current.get(siteCode) ?? 0) === version) {
          remainingDirty.delete(siteCode);
        }
      });
      dirtyRowsRef.current = remainingDirty;
      setDirtyRows(remainingDirty);

      const latestLocal = scenarioRef.current;
      const localRows = new Map(
        latestLocal?.id === saved.id
          ? latestLocal.rows.map((row) => [row.site_code, row])
          : [],
      );
      const mergedRows = saved.rows.map((row) => (
        remainingDirty.has(row.site_code)
          ? localRows.get(row.site_code) ?? row
          : row
      ));
      replaceScenario(recalculateVisibleScenario(saved, mergedRows));
      setError(null);
      return saved;
    } catch (err) {
      try {
        const latest = await fetchTargetScenario(current.id);
        const latestLocal = scenarioRef.current;
        const localRows = new Map(
          latestLocal?.id === latest.id
            ? latestLocal.rows.map((row) => [row.site_code, row])
            : [],
        );
        const mergedRows = latest.rows.map((row) => (
          dirtyRowsRef.current.has(row.site_code)
            ? localRows.get(row.site_code) ?? row
            : row
        ));
        replaceScenario(recalculateVisibleScenario(latest, mergedRows));
      } catch {
        // Preserve local edits if the conflict refresh is also unavailable.
      }
      throw err;
    } finally {
      setSavingRows((previous) => {
        const next = new Set(previous);
        siteCodes.forEach((siteCode) => next.delete(siteCode));
        return next;
      });
    }
  }, [replaceScenario]);

  const persistDraft = async (): Promise<TargetScenario | null> => {
    const current = scenarioRef.current;
    if (!current || current.status === 'finalized') return current;
    return persistRows(Array.from(dirtyRowsRef.current));
  };

  const handleSave = async () => {
    setBusy(true);
    setError(null);
    try {
      await persistDraft();
    } catch (err) {
      console.error(err);
      setError('Targetele finale nu au putut fi salvate.');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!scenario || scenario.status === 'finalized' || dirtyRows.size === 0) return;
    const pendingCodes = Array.from(dirtyRows).filter((siteCode) => !savingRows.has(siteCode));
    if (pendingCodes.length === 0) return;
    const timeoutId = window.setTimeout(() => {
      void persistRows(pendingCodes).catch((err) => {
        console.error(err);
        setError('Salvarea automata a targetelor finale nu a reusit.');
      });
    }, 700);
    return () => window.clearTimeout(timeoutId);
  }, [scenario, dirtyRows, savingRows, persistRows]);

  useEffect(() => {
    if (!scenario || dirtyRows.size > 0 || savingRows.size > 0) return;
    const scenarioId = scenario.id;
    const intervalId = window.setInterval(() => {
      void fetchTargetScenario(scenarioId).then((latest) => {
        if (scenarioRef.current?.id === scenarioId && dirtyRowsRef.current.size === 0) {
          replaceScenario(latest);
        }
      }).catch(() => {
        // Keep the user's current view if a background collaboration refresh fails.
      });
    }, 15000);
    return () => window.clearInterval(intervalId);
  }, [scenario, dirtyRows.size, savingRows.size, replaceScenario]);

  const handleFinalize = async () => {
    if (!scenario) return;
    setBusy(true);
    setError(null);
    try {
      if (dirty) {
        await persistDraft();
      }
      const latest = await fetchTargetScenario(scenario.id);
      replaceScenario(latest);
      if (latest.pending_final_count > 0) {
        setError(`Mai sunt ${latest.pending_final_count} locatii fara Final manager completat.`);
        return;
      }
      if (Math.abs(latest.remaining_difference) > 0.01) {
        setError('Pentru finalizare, suma targetelor finale trebuie sa fie egala cu targetul total.');
        return;
      }
      if (!window.confirm(
        `Finalizezi scenariul pentru exact cele ${latest.store_count} magazine active? `
        + 'Valorile vor deveni targetele oficiale din Hub si CRM, iar orice target existent in afara acestei cohorte va fi eliminat.',
      )) return;
      replaceScenario(await finalizeTargetScenario(latest.id, latest.revision));
      clearLocalEdits();
    } catch (err) {
      console.error(err);
      setError('Targetul nu a putut fi finalizat.');
    } finally {
      setBusy(false);
    }
  };

  const handleExport = async () => {
    if (!scenario) return;
    setBusy(true);
    setError(null);
    try {
      if (dirty && scenario.status === 'draft') {
        await persistDraft();
      }
      await downloadTargetScenario(scenario.id, `targete_${scenario.target_month}.xlsx`);
    } catch (err) {
      console.error(err);
      setError('Exportul Excel nu a putut fi generat.');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-sm text-slate-500">Se incarca calculatorul de target...</div>;
  }

  return (
    <div className="p-4 lg:p-6 space-y-4">
      {context?.can_finalize && (
        <div className="glass rounded-2xl p-4 space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900 dark:text-slate-100">
                <Calculator size={18} className="text-indigo-500" />
                Calculator Target
              </h2>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Propunerea se calculeaza si se salveaza ca draft comun pentru magazinele cu vanzari in ultima luna disponibila anterior targetului.
                Daca referinta curenta este partiala, vanzarile utilizate sunt forecastate din importul disponibil.
              </p>
            </div>
            <button
              onClick={() => void loadInitial()}
              disabled={busy}
              className="rounded-xl bg-slate-100 p-2 text-slate-500 hover:bg-slate-200 disabled:opacity-50 dark:bg-slate-800 dark:hover:bg-slate-700"
              title="Reincarca"
            >
              <RefreshCw size={15} className={busy ? 'animate-spin' : ''} />
            </button>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <label className="space-y-1 text-xs text-slate-500">
              Luna target
              <input className={`w-full ${inputCls}`} type="month" value={targetMonth} onChange={(event) => setTargetMonth(event.target.value)} />
            </label>
            <label className="space-y-1 text-xs text-slate-500">
              Target total (RON)
              <input className={`w-full ${inputCls}`} type="number" min="1" value={totalTarget} onChange={(event) => setTotalTarget(event.target.value)} />
            </label>
            <label className="space-y-1 text-xs text-slate-500">
              Prag minim (RON)
              <input className={`w-full ${inputCls}`} type="number" min="0" value={minFloor} onChange={(event) => setMinFloor(event.target.value)} />
            </label>
            <label className="space-y-1 text-xs text-slate-500">
              Floor vs luna anterioara (%)
              <input className={`w-full ${inputCls}`} type="number" min="0" max="200" step="0.1" value={floorPct} onChange={(event) => setFloorPct(event.target.value)} />
            </label>
            <div className="space-y-1 text-xs text-slate-500">
              Sezonalitate
              <div className="grid grid-cols-2 rounded-xl border border-slate-200 bg-slate-100 p-1 dark:border-slate-700 dark:bg-slate-800">
                <button
                  type="button"
                  onClick={() => setSeasonalityMode('single')}
                  className={`rounded-lg px-2 py-1.5 text-xs font-semibold ${
                    seasonalityMode === 'single'
                      ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100'
                      : 'text-slate-500 hover:text-slate-700 dark:text-slate-400'
                  }`}
                >
                  Anul trecut
                </button>
                <button
                  type="button"
                  onClick={() => setSeasonalityMode('multi')}
                  className={`rounded-lg px-2 py-1.5 text-xs font-semibold ${
                    seasonalityMode === 'multi'
                      ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100'
                      : 'text-slate-500 hover:text-slate-700 dark:text-slate-400'
                  }`}
                >
                  Multi-year
                </button>
              </div>
            </div>
            <div className="flex items-end">
              <button
                onClick={handleCalculate}
                disabled={busy}
                className="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {busy ? 'Se proceseaza...' : 'Calculeaza propunerea'}
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white/70 dark:border-slate-700 dark:bg-slate-900/50">
            <button
              type="button"
              onClick={() => setLogicOpen((open) => !open)}
              aria-expanded={logicOpen}
              className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-xs font-semibold text-slate-700 hover:text-indigo-600 dark:text-slate-200 dark:hover:text-indigo-300"
            >
              <span className="flex items-center gap-2">
                <Calculator size={14} className="text-indigo-500" />
                Logica de calcul si formula
              </span>
              <ChevronDown size={14} className={`shrink-0 transition-transform ${logicOpen ? 'rotate-180' : ''}`} />
            </button>
            {logicOpen && (
              <div className="border-t border-slate-200 px-3 py-3 text-xs leading-5 text-slate-600 dark:border-slate-700 dark:text-slate-300">
                <p>
                  Calculatorul porneste de la forecastul lunii curente si il transforma intr-o estimare pentru luna target cu sezonalitate, trend, floor si cap.
                </p>
                <p className="mt-2 font-semibold text-slate-800 dark:text-slate-100">
                  Estimare bruta = Forecast luna curenta x Factor sezonier folosit x Ajustare trend.
                </p>
                <p className="mt-2">
                  Factor sezonier folosit = factor magazin x pondere magazin + factor manager x pondere manager + factor retea x pondere retea. Un magazin stabil foloseste 50% / 30% / 20%; istoricul slab muta greutatea spre manager si retea.
                </p>
                <p className="mt-2">
                  In modul Anul trecut se compara luna target cu luna baza din Y-1. In modul Multi-year se folosesc pana la 3 ani, cu pondere mai mare pentru anii recenti; anii fara date suficiente sunt sariti automat.
                </p>
                <p className="mt-2">
                  Propunerea finala distribuie targetul total top-down proportional cu estimarile brute, apoi aplica pragul minim, floor/cap fata de luna anterioara si rotunjirea. Valoarea Final manager ramane decizia editabila si trebuie sa insumeze targetul total la finalizare.
                </p>
              </div>
            )}
          </div>

          <p className="text-xs text-slate-500 dark:text-slate-400">
            Ultima luna cu vanzari: <strong>{monthLabel(context.latest_sales_month)}</strong>.
            Pentru noul target, cohorta curenta contine <strong>{context.active_store_count}</strong> magazine active.
            Magazinele fara vanzari in luna cohortei nu vor fi publicate in targetul final.
          </p>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-900/20 dark:text-red-300">
          <AlertTriangle size={15} />
          {error}
        </div>
      )}

      {scenario && <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          Target {monthLabel(scenario.target_month)}
        </span>
        {scenario && (
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
            scenario.status === 'finalized'
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
              : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
          }`}>
            {scenario.status === 'finalized'
              ? 'Finalizat'
              : savingRows.size > 0
                ? 'Se salveaza automat...'
                : dirty
                  ? 'Modificari in curs...'
                  : 'Salvat in baza de date'}
          </span>
        )}
      </div>}

      {scenario && (
        <>
          {displayWarnings.length > 0 && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-900/20 dark:text-amber-300">
              {displayWarnings.map((warning) => <p key={warning}>{warning}</p>)}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard label="Target total" value={formatCurrency(scenario.total_target)} detail={monthLabel(scenario.target_month)} />
            <SummaryCard label="Calculat" value={formatCurrency(scenario.proposed_total)} detail={`${scenario.store_count} magazine active · ${activeSeasonalityLabel}`} />
            <SummaryCard
              label="Final manager"
              value={formatCurrency(scenario.final_total)}
              detail={scenario.status === 'draft'
                ? `${scenario.pending_final_count} necompletate · ${scenario.manual_adjustments_count} ajustari`
                : 'Publicat in targetele oficiale'}
              emphasis="attention"
            />
            <SummaryCard
              label="Ramas de distribuit"
              value={formatCurrency(scenario.remaining_difference)}
              detail="trebuie sa fie 0 la finalizare"
              emphasis={Math.abs(scenario.remaining_difference) <= 0.01 ? 'good' : 'warning'}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="glass rounded-2xl p-4">
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Calculator si Final manager</h3>
              <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                Rosu = sub calculator · Verde = egal sau pana la +5% · Galben = peste +5%
              </p>
              <div className="mt-3 space-y-2 md:hidden">
                {regionalChart.map((manager) => {
                  const difference = manager.final_total - manager.proposed_total;
                  const status = managerTargetStatus(manager.proposed_total, manager.final_total);
                  const currentMonth = monthLabel(manager.current_month ?? shiftMonth(scenario.target_month, -1));
                  const lastYearLabel = manager.last_year_base_month && manager.last_year_target_month
                    ? `${monthLabel(manager.last_year_target_month)} vs ${monthLabel(manager.last_year_base_month)}`
                    : 'Anul trecut';
                  return (
                    <div key={manager.regional} className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900/60">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-slate-800 dark:text-slate-100">{manager.regional}</p>
                          <p className="text-[11px] text-slate-400">{manager.store_count} magazine</p>
                        </div>
                        <span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${status.badgeClass}`}>
                          {status.label}
                        </span>
                      </div>
                      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
                        <div className="rounded-lg bg-indigo-50 p-2 dark:bg-indigo-900/20">
                          <p className="uppercase tracking-wide text-indigo-400">Calculator</p>
                          <p className="mt-1 font-semibold tabular-nums text-indigo-700 dark:text-indigo-300">{formatCurrency(manager.proposed_total)}</p>
                        </div>
                        <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-800">
                          <p className="uppercase tracking-wide text-slate-400">Final</p>
                          <p className={`mt-1 font-semibold tabular-nums ${status.valueClass}`}>{formatCurrency(manager.final_total)}</p>
                        </div>
                        <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-800">
                          <p className="uppercase tracking-wide text-slate-400">Diferenta</p>
                          <p className={`mt-1 font-semibold tabular-nums ${status.valueClass}`}>{difference > 0 ? '+' : ''}{formatCurrency(difference)}</p>
                        </div>
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
                        <div className="rounded-lg bg-emerald-50 p-2 dark:bg-emerald-900/20">
                          <p className="uppercase tracking-wide text-emerald-500">Propus vs {currentMonth}</p>
                          <p className={`mt-1 font-semibold tabular-nums ${percentTone(manager.proposed_growth_vs_current_pct)}`}>
                            {formatSignedPercent(manager.proposed_growth_vs_current_pct)}
                          </p>
                          <p className="mt-1 text-[10px] text-slate-400">{formatCurrency(manager.current_forecast_total)}</p>
                        </div>
                        <div className="rounded-lg bg-sky-50 p-2 dark:bg-sky-900/20">
                          <p className="uppercase tracking-wide text-sky-500">{lastYearLabel}</p>
                          <p className={`mt-1 font-semibold tabular-nums ${percentTone(manager.last_year_growth_pct)}`}>
                            {formatSignedPercent(manager.last_year_growth_pct)}
                          </p>
                          <p className="mt-1 text-[10px] text-slate-400">{formatCurrency(manager.last_year_base_total)} {'->'} {formatCurrency(manager.last_year_target_total)}</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-3 hidden overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700 md:block">
                <div className="min-w-[820px]">
                  <div className="grid grid-cols-[minmax(130px,1fr)_115px_115px_115px_115px_100px_110px] bg-slate-50 px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:bg-slate-800">
                    <span>Manager</span>
                    <span className="text-right">Calculator</span>
                    <span className="text-right">Vs luna curenta</span>
                    <span className="text-right">LY target/baza</span>
                    <span className="text-right">Final manager</span>
                    <span className="text-right">Diferenta</span>
                    <span className="text-right">Status</span>
                  </div>
                  <div className="divide-y divide-slate-100 dark:divide-slate-800">
                    {regionalChart.map((manager) => {
                      const difference = manager.final_total - manager.proposed_total;
                      const status = managerTargetStatus(manager.proposed_total, manager.final_total);
                      const currentMonth = monthLabel(manager.current_month ?? shiftMonth(scenario.target_month, -1));
                      const lastYearLabel = manager.last_year_base_month && manager.last_year_target_month
                        ? `${monthLabel(manager.last_year_target_month)} / ${monthLabel(manager.last_year_base_month)}`
                        : 'LY';
                      return (
                        <div key={manager.regional} className="grid grid-cols-[minmax(130px,1fr)_115px_115px_115px_115px_100px_110px] items-center px-3 py-3 text-xs">
                          <div>
                            <p className="font-semibold text-slate-700 dark:text-slate-200">{manager.regional}</p>
                            <p className="text-[10px] text-slate-400">{manager.store_count} magazine</p>
                          </div>
                          <span className="text-right font-medium tabular-nums text-indigo-600 dark:text-indigo-300">
                            {formatCurrency(manager.proposed_total)}
                          </span>
                          <span className="text-right tabular-nums">
                            <span className={`block font-semibold ${percentTone(manager.proposed_growth_vs_current_pct)}`}>
                              {formatSignedPercent(manager.proposed_growth_vs_current_pct)}
                            </span>
                            <span className="block text-[10px] text-slate-400">{currentMonth}</span>
                          </span>
                          <span className="text-right tabular-nums">
                            <span className={`block font-semibold ${percentTone(manager.last_year_growth_pct)}`}>
                              {formatSignedPercent(manager.last_year_growth_pct)}
                            </span>
                            <span className="block text-[10px] text-slate-400">{lastYearLabel}</span>
                          </span>
                          <span className={`text-right font-semibold tabular-nums ${status.valueClass}`}>
                            {formatCurrency(manager.final_total)}
                          </span>
                          <span className={`text-right font-semibold tabular-nums ${status.valueClass}`}>
                            {difference > 0 ? '+' : ''}{formatCurrency(difference)}
                          </span>
                          <span className={`ml-auto rounded-full px-2 py-1 text-[10px] font-semibold ${status.badgeClass}`}>
                            {status.label}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>

            <div className="glass rounded-2xl p-4">
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                Baza istorica {regionalFilter === 'all' ? '' : `- ${regionalFilter}`}
              </h3>
              {sourceChart.some((period) => period.isForecast) && (
                <p className="mt-1 text-[11px] text-indigo-600 dark:text-indigo-300">
                  Forecast = valoare proiectata din importul partial si folosita in calcul.
                </p>
              )}
              <div className="mt-3 space-y-2 md:hidden">
                {sourceChart.map((period) => (
                  <div key={period.month} className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900/60">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-semibold text-slate-800 dark:text-slate-100">{period.month}</p>
                      {period.isForecast && (
                        <span className="rounded-full bg-sky-100 px-2 py-1 text-[10px] font-semibold text-sky-700 dark:bg-sky-900/30 dark:text-sky-300">
                          Forecast
                        </span>
                      )}
                    </div>
                    <div className={`mt-3 grid gap-2 text-[11px] ${period.showTarget ? 'grid-cols-2' : 'grid-cols-1'}`}>
                      {period.showTarget && (
                        <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-800">
                          <p className="uppercase tracking-wide text-slate-400">Target istoric</p>
                          <p className="mt-1 font-semibold tabular-nums text-slate-700 dark:text-slate-200">{formatCurrency(period.target)}</p>
                        </div>
                      )}
                      <div className="rounded-lg bg-sky-50 p-2 dark:bg-sky-900/20">
                        <p className="uppercase tracking-wide text-sky-500">{period.isForecast ? 'Forecast folosit' : 'Realizat'}</p>
                        <p className="mt-1 font-semibold tabular-nums text-sky-700 dark:text-sky-300">{formatCurrency(period.realized)}</p>
                        {period.isForecast && (
                          <p className="mt-1 text-[10px] text-slate-400">Importat: {formatCurrency(period.actualRealized)}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              {isDesktop && (
                <div className="mt-3 h-64">
                  <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                    <BarChart data={sourceChart} margin={{ top: 4, right: 4, left: 4, bottom: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.15)" />
                      <XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                      <YAxis tickFormatter={(value) => `${Math.round(Number(value) / 1000)}k`} tick={{ fill: '#94a3b8', fontSize: 10 }} />
                      <Tooltip formatter={(value: number) => formatCurrency(value)} />
                      <Legend />
                      {sourceChart.some((period) => period.showTarget) && (
                        <Bar dataKey="target" name="Target istoric" fill="#cbd5e1" radius={[4, 4, 0, 0]} />
                      )}
                      <Bar dataKey="realized" name="Realizat / Forecast folosit" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          <div className="glass rounded-2xl p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-1 text-xs font-medium text-slate-500 dark:text-slate-400">Manager</span>
              {['all', ...regionals].map((regional) => {
                const active = regionalFilter === regional;
                return (
                  <button
                    key={regional}
                    onClick={() => setRegionalFilter(regional)}
                    className={`rounded-xl px-3 py-2 text-xs font-semibold transition-colors ${
                      active
                        ? 'bg-indigo-600 text-white shadow-sm'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                    }`}
                  >
                    {regional === 'all' ? 'Toti managerii' : regional}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="glass rounded-2xl overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
              <div>
                <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Target per locatie</h3>
                <p className="text-xs text-slate-500">
                  {filteredRows.length} locatii afisate · <span className="font-semibold text-amber-700 dark:text-amber-300">Final manager</span> este decizia de completat si se salveaza automat pentru toti managerii
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {scenario.status === 'draft' && (
                  <>
                    {context?.can_finalize && (
                      <button onClick={resetToProposal} disabled={busy} className="flex items-center gap-1.5 rounded-xl bg-slate-100 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-200 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700">
                        <RotateCcw size={13} /> {regionalFilter === 'all' ? 'Reset propunere' : 'Reset manager'}
                      </button>
                    )}
                    <button onClick={handleSave} disabled={busy || !dirty} className="flex items-center gap-1.5 rounded-xl bg-indigo-100 px-3 py-2 text-xs font-medium text-indigo-700 hover:bg-indigo-200 disabled:opacity-50 dark:bg-indigo-900/30 dark:text-indigo-300">
                      <Save size={13} /> Salveaza acum
                    </button>
                    {context?.can_finalize && (
                      <button onClick={handleFinalize} disabled={busy} className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
                        <CheckCircle2 size={13} /> Finalizeaza
                      </button>
                    )}
                  </>
                )}
                {context?.can_finalize && (
                  <button onClick={handleExport} disabled={busy} className="flex items-center gap-1.5 rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900">
                    <Download size={13} /> Export Excel
                  </button>
                )}
              </div>
            </div>

            <div className="border-b border-slate-100 px-4 py-3 dark:border-slate-800">
              <div ref={locationFilterRef} className="flex flex-col gap-3 lg:flex-row lg:items-end">
                <div className="relative min-w-0 flex-1 space-y-1 text-xs font-medium text-slate-500 lg:max-w-sm">
                  <span>Selecteaza locatie</span>
                  <button
                    type="button"
                    onClick={() => setLocationDropdownOpen((current) => !current)}
                    className={`${inputCls} flex w-full items-center justify-between gap-2 text-left`}
                  >
                    <span className="truncate">
                      {selectedLocationCodes.length > 0
                        ? `${selectedLocationCodes.length} locatii selectate`
                        : 'Adauga locatie...'}
                    </span>
                    <ChevronDown size={14} className={`shrink-0 text-slate-400 transition-transform ${locationDropdownOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {locationDropdownOpen && (
                    <div className="absolute left-0 right-0 top-full z-30 mt-2 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-900">
                      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2 dark:border-slate-800">
                        <span className="text-[11px] text-slate-400">{selectedLocationCodes.length} selectate</span>
                        {selectedLocationCodes.length > 0 && (
                          <button
                            type="button"
                            onClick={() => setSelectedLocationCodes([])}
                            className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-700 dark:text-indigo-300"
                          >
                            Goleste
                          </button>
                        )}
                      </div>
                      <div className="max-h-72 overflow-y-auto p-1">
                        {locationOptions.length === 0 && (
                          <p className="px-3 py-3 text-xs text-slate-400">Nu exista locatii disponibile.</p>
                        )}
                        {locationOptions.map((row) => (
                          <label
                            key={row.site_code}
                            className="flex cursor-pointer items-start gap-2 rounded-xl px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800"
                          >
                            <input
                              type="checkbox"
                              checked={selectedLocationSet.has(row.site_code)}
                              onChange={() => toggleLocationFilter(row.site_code)}
                              className="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                            />
                            <span className="min-w-0">
                              <span className="block truncate font-semibold text-slate-700 dark:text-slate-200">{row.locatie}</span>
                              <span className="block truncate text-[10px] text-slate-400">{row.site_code} · {row.firma}</span>
                            </span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                {selectedLocationCodes.length > 0 && (
                  <button
                    onClick={() => setSelectedLocationCodes([])}
                    className="rounded-xl bg-slate-100 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
                  >
                    Toate locatiile
                  </button>
                )}
              </div>
              {selectedLocationCodes.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {selectedLocationCodes.map((siteCode) => {
                    const row = locationOptions.find((item) => item.site_code === siteCode);
                    if (!row) return null;
                    return (
                      <button
                        key={siteCode}
                        onClick={() => removeLocationFilter(siteCode)}
                        className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-900/30 dark:text-indigo-300"
                      >
                        {row.locatie}
                        <X size={12} />
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="space-y-3 p-3 md:hidden">
              {filteredRows.map((row) => (
                <div key={row.site_code} className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                  <button
                    onClick={() => setDetailSiteCode(row.site_code)}
                    className="text-left"
                  >
                    <p className="font-semibold text-slate-800 underline decoration-dotted underline-offset-4 dark:text-slate-100">{row.locatie}</p>
                    <p className="mt-0.5 text-[11px] text-slate-400">{row.site_code} · {row.firma} · {row.regional}</p>
                  </button>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded-xl bg-slate-50 p-2 dark:bg-slate-800/60">
                      <p className="text-[10px] uppercase tracking-wide text-slate-400">Calculat</p>
                      <p className="font-semibold text-indigo-600 dark:text-indigo-300">{formatCurrency(row.proposed_target)}</p>
                    </div>
                    <label className="rounded-xl border border-amber-200 bg-amber-50 p-2 dark:border-amber-900 dark:bg-amber-950/20">
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">Final manager</span>
                      <input
                        type="number"
                        min="0"
                        disabled={scenario.status === 'finalized'}
                        className={`${finalInputCls} mt-1 w-full text-right tabular-nums disabled:opacity-70`}
                        value={row.final_target ?? ''}
                        placeholder="Completeaza"
                        onChange={(event) => updateRow(row.site_code, 'final_target', event.target.value === '' ? null : Number(event.target.value))}
                      />
                    </label>
                  </div>
                  <div className="mt-2 grid grid-cols-3 gap-2 text-[11px]">
                    {displaySourceMonths.map((source) => {
                      const period = row.history.find((history) => history.month === source.month);
                      const showTarget = shouldShowHistoricalTarget(source);
                      return (
                        <div key={source.month} className={`rounded-xl p-2 ${
                          isPreviousYearPeriod(source.role)
                            ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/20 dark:text-indigo-300'
                            : 'bg-slate-50 text-slate-600 dark:bg-slate-800/60 dark:text-slate-300'
                        }`}>
                          <p className="font-semibold">{monthLabel(source.month)}</p>
                          {showTarget && <p>{formatCurrency(period?.target ?? 0)}</p>}
                          <p className="text-slate-400">{formatCurrency(period?.realized ?? 0)}</p>
                        </div>
                      );
                    })}
                  </div>
                  <div className="mt-2 rounded-xl bg-slate-50 p-2 text-[11px] text-slate-500 dark:bg-slate-800/60 dark:text-slate-300">
                    <div className="flex items-center justify-between gap-2">
                      <span>Sezonalitate folosita</span>
                      <span className="font-semibold text-slate-800 dark:text-slate-100">
                        {formatFactor(row.calculation_details.seasonality?.used_factor)}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-slate-400">
                      <span>LY {formatFactor(row.calculation_details.seasonality?.last_year_store_factor)}</span>
                      <span>MY {formatFactor(row.calculation_details.seasonality?.multiyear_store_factor)}</span>
                      <span>Trend {formatFactor(row.calculation_details.trend?.used_adjustment)}</span>
                    </div>
                    {(row.calculation_details.flags ?? []).length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {(row.calculation_details.flags ?? []).slice(0, 3).map((flag) => (
                          <span key={flag} className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                            {flagLabel(flag)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-2 text-xs">
                    <span className="text-slate-400">Delta</span>
                    <span className={`font-semibold ${
                      row.final_target == null
                        ? 'text-amber-600'
                        : row.final_target - row.proposed_target > 0.01
                          ? 'text-emerald-600'
                          : row.final_target - row.proposed_target < -0.01
                            ? 'text-red-600'
                            : 'text-slate-400'
                    }`}>
                      {row.final_target == null ? 'Necompletat' : formatCurrency(row.final_target - row.proposed_target)}
                    </span>
                  </div>
                  <input
                    disabled={scenario.status === 'finalized'}
                    className={`${inputCls} mt-2 w-full disabled:opacity-70`}
                    placeholder="Observatii"
                    value={row.note ?? ''}
                    onChange={(event) => updateRow(row.site_code, 'note', event.target.value)}
                  />
                </div>
              ))}
            </div>

            <div className="hidden overflow-x-auto md:block">
              <table className="min-w-[1680px] w-full text-xs">
                <thead className="bg-slate-50 text-slate-500 dark:bg-slate-800/70 dark:text-slate-400">
                  <tr>
                    <th rowSpan={2} className="px-3 py-2 text-left font-semibold align-bottom">Locatie</th>
                    <th rowSpan={2} className="px-3 py-2 text-left font-semibold align-bottom">Manager</th>
                    {displaySourceMonths.map((period) => (
                      <th key={period.month} colSpan={shouldShowHistoricalTarget(period) ? 2 : 1} className={`border-b px-3 py-2 text-center font-semibold ${
                        isPreviousYearPeriod(period.role)
                          ? 'border-indigo-200 bg-indigo-100/80 text-indigo-700 dark:border-indigo-800 dark:bg-indigo-900/35 dark:text-indigo-300'
                          : 'border-slate-200 dark:border-slate-700'
                      }`}>
                        {monthLabel(period.month)}
                        {isPreviousYearPeriod(period.role) && <p className="text-[9px] uppercase tracking-wide">Anul trecut</p>}
                        {forecastMonths.has(period.month) && <p className="text-[9px] uppercase tracking-wide text-sky-600 dark:text-sky-300">Forecast</p>}
                      </th>
                    ))}
                    <th rowSpan={2} className="px-3 py-2 text-right font-semibold align-bottom">Sezonalitate</th>
                    <th rowSpan={2} className="px-3 py-2 text-right font-semibold align-bottom">Calculat</th>
                    <th rowSpan={2} className="border-x border-amber-200 bg-amber-100/80 px-3 py-2 text-right font-semibold text-amber-800 align-bottom dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                      <span className="flex items-center justify-end gap-1">
                        <PencilLine size={12} />
                        Final manager
                      </span>
                      <span className="mt-1 block text-[9px] uppercase tracking-wide">
                        {scenario.status === 'draft' ? 'De completat' : 'Finalizat'}
                      </span>
                    </th>
                    <th rowSpan={2} className="px-3 py-2 text-right font-semibold align-bottom">Delta</th>
                    <th rowSpan={2} className="px-3 py-2 text-left font-semibold align-bottom">Observatii</th>
                  </tr>
                  <tr>
                    {displaySourceMonths.map((period) => (
                      <Fragment key={period.month}>
                        {shouldShowHistoricalTarget(period) && (
                          <th className={`px-3 py-2 text-right font-medium ${
                            isPreviousYearPeriod(period.role)
                              ? 'bg-indigo-50 text-indigo-500 dark:bg-indigo-900/20 dark:text-indigo-300'
                              : 'text-slate-400'
                          }`}>Target</th>
                        )}
                        <th className={`px-3 py-2 text-right font-medium ${
                          isPreviousYearPeriod(period.role)
                            ? 'bg-indigo-50 text-indigo-500 dark:bg-indigo-900/20 dark:text-indigo-300'
                            : 'text-slate-400'
                        }`}>
                          {forecastMonths.has(period.month)
                            ? 'Forecast'
                            : 'Realizat'}
                        </th>
                      </Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {filteredRows.map((row) => (
                    <tr key={row.site_code}>
                      <td className="px-3 py-2">
                        <button
                          onClick={() => setDetailSiteCode(row.site_code)}
                          className="text-left font-medium text-slate-800 underline decoration-dotted underline-offset-4 hover:text-indigo-600 dark:text-slate-200 dark:hover:text-indigo-300"
                        >
                          {row.locatie}
                        </button>
                        <p className="text-[10px] text-slate-400">{row.site_code} · {row.firma}</p>
                      </td>
                      <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{row.regional}</td>
                      {displaySourceMonths.map((source) => {
                        const period = row.history.find((history) => history.month === source.month);
                        const showTarget = shouldShowHistoricalTarget(source);
                        return (
                          <Fragment key={source.month}>
                            {showTarget && (
                              <td className={`px-3 py-2 text-right tabular-nums ${
                                isPreviousYearPeriod(source.role)
                                  ? 'bg-indigo-50/70 font-medium text-indigo-700 dark:bg-indigo-900/15 dark:text-indigo-300'
                                  : 'text-slate-500 dark:text-slate-400'
                              }`}>
                                {formatCurrency(period?.target ?? 0)}
                              </td>
                            )}
                            <td className={`px-3 py-2 text-right tabular-nums ${
                              isPreviousYearPeriod(source.role)
                                ? 'bg-indigo-50/70 font-medium text-indigo-800 dark:bg-indigo-900/15 dark:text-indigo-200'
                                : 'text-slate-700 dark:text-slate-200'
                            }`}>
                              {formatCurrency(period?.realized ?? 0)}
                              {(showTarget || period?.is_forecast) && (
                                <p className="text-[10px] text-slate-400">
                                  {period?.is_forecast ? 'Forecast ' : ''}{period?.attainment_pct == null ? '-' : formatPercent(period.attainment_pct)}
                                </p>
                              )}
                              {period?.is_forecast && (
                                <p className="text-[10px] text-slate-400">
                                  Real: {formatCurrency(period.actual_realized ?? period.realized)}
                                </p>
                              )}
                            </td>
                          </Fragment>
                        );
                      })}
                      <td className="px-3 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">
                        <p className="font-semibold text-slate-800 dark:text-slate-100">{formatFactor(row.calculation_details.seasonality?.used_factor)}</p>
                        <p className="text-[10px] text-slate-400">
                          LY {formatFactor(row.calculation_details.seasonality?.last_year_store_factor)} · MY {formatFactor(row.calculation_details.seasonality?.multiyear_store_factor)}
                        </p>
                        <p className="text-[10px] text-slate-400">
                          Trend {formatFactor(row.calculation_details.trend?.used_adjustment)}
                        </p>
                        {(row.calculation_details.flags ?? []).length > 0 && (
                          <div className="mt-1 flex flex-wrap justify-end gap-1">
                            {(row.calculation_details.flags ?? []).slice(0, 2).map((flag) => (
                              <span key={flag} className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                                {flagLabel(flag)}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right font-semibold tabular-nums text-indigo-600 dark:text-indigo-300">
                        {formatCurrency(row.proposed_target)}
                      </td>
                      <td className="border-x border-amber-100 bg-amber-50/50 px-3 py-2 text-right dark:border-amber-900 dark:bg-amber-950/10">
                        <input
                          type="number"
                          min="0"
                          disabled={scenario.status === 'finalized'}
                          className={`${finalInputCls} w-32 text-right tabular-nums disabled:opacity-70`}
                          value={row.final_target ?? ''}
                          placeholder="Completeaza"
                          onChange={(event) => updateRow(row.site_code, 'final_target', event.target.value === '' ? null : Number(event.target.value))}
                        />
                      </td>
                      <td className={`px-3 py-2 text-right font-semibold tabular-nums ${
                        row.final_target == null
                          ? 'text-amber-600'
                          : row.final_target - row.proposed_target > 0.01
                          ? 'text-emerald-600'
                          : row.final_target - row.proposed_target < -0.01
                            ? 'text-red-600'
                            : 'text-slate-400'
                      }`}>
                        {row.final_target == null ? 'Necompletat' : formatCurrency(row.final_target - row.proposed_target)}
                      </td>
                      <td className="px-3 py-2">
                        <input
                          disabled={scenario.status === 'finalized'}
                          className={`${inputCls} w-44 disabled:opacity-70`}
                          placeholder="Optional"
                          value={row.note ?? ''}
                          onChange={(event) => updateRow(row.site_code, 'note', event.target.value)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
      {scenario && (
        <StoreDetailDrawer
          scenarioId={scenario.id}
          siteCode={detailSiteCode}
          onClose={() => setDetailSiteCode(null)}
        />
      )}
    </div>
  );
}
