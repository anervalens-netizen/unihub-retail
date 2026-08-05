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
  type TargetStoreDetail,
} from '../api/targetCalculator';
import {getApiErrorMessage} from '../api/client';
import { formatCurrency, formatPercent } from '../lib/formatters';
import { formatMonthLabel, shiftMonth } from '../lib/dates';

const inputCls = 'rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';
const finalInputCls = 'rounded-xl border-2 border-amber-300 bg-amber-50 px-3 py-2 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-400 dark:border-amber-600 dark:bg-amber-950/30 dark:text-slate-100';

function monthLabel(month: string): string {
  return formatMonthLabel(month);
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

function formatSignedPercent(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value > 0 ? '+' : ''}${formatPercent(value)}`;
}

function formatSignedPp(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value > 0 ? '+' : ''}${value.toFixed(1)} pp`;
}

function formatTableNumber(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return Math.round(value).toLocaleString('ro-RO');
}

function attainmentTone(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return 'text-slate-400';
  if (value < 90) return 'font-bold text-red-600 dark:text-red-400';
  if (value < 100) return 'font-bold text-orange-500 dark:text-orange-400';
  return 'font-bold text-emerald-600 dark:text-emerald-400';
}

function profitabilityFlagLabel(flag: string): string {
  const labels: Record<string, string> = {
    PNL_INCOMPLETE: 'P&L incomplet',
    FORECAST_MISSING: 'forecast lipsă',
    TARGET_BELOW_BREAK_EVEN: 'target sub BE',
    FORECAST_BELOW_BREAK_EVEN: 'forecast sub BE',
    FORECAST_BELOW_TARGET: 'forecast sub target',
  };
  return labels[flag] ?? flagLabel(flag);
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

function SummaryCard({ label, value, detail, emphasis, grouped = false }: {
  label: string;
  value: string;
  detail?: string;
  emphasis?: 'good' | 'warning' | 'attention';
  grouped?: boolean;
}) {
  const color = emphasis === 'good'
    ? 'text-emerald-600 dark:text-emerald-400'
    : emphasis === 'warning'
      ? 'text-amber-600 dark:text-amber-400'
      : emphasis === 'attention'
        ? 'text-amber-700 dark:text-amber-300'
      : 'text-slate-900 dark:text-slate-100';
  const surface = grouped
    ? 'min-w-0 p-3'
    : emphasis === 'attention'
    ? 'rounded-2xl border border-amber-300 bg-amber-50/80 p-4 min-w-0 dark:border-amber-700 dark:bg-amber-950/20'
    : 'glass rounded-2xl p-4 min-w-0';
  return (
    <div className={surface}>
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 break-words font-bold tabular-nums ${grouped ? 'text-base sm:text-lg xl:text-xl' : 'text-xl'} ${color}`}>{value}</p>
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
        setError(getApiErrorMessage(err, 'Nu am putut incarca detaliile locatiei.'));
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

function TargetWorkflow({ step }: { step: 1 | 2 | 3 | 4 }) {
  const steps = [
    { number: 1, label: 'Configurare' },
    { number: 2, label: 'Verificare propunere' },
    { number: 3, label: 'Ajustări manageri' },
    { number: 4, label: 'Finalizare' },
  ] as const;
  return (
    <nav aria-label="Flux Calculator Target" className="glass rounded-2xl p-3">
      <div className="lg:hidden">
        <div className="mb-2 flex items-center justify-between text-xs font-semibold text-slate-500"><span>Pasul {step} din 4</span><span>{steps[step - 1].label}</span></div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"><div className="h-full rounded-full bg-indigo-600 transition-all" style={{ width: `${step * 25}%` }} /></div>
      </div>
      <ol className="hidden grid-cols-2 gap-2 lg:grid lg:grid-cols-4">
        {steps.map((item) => {
          const complete = item.number < step;
          const active = item.number === step;
          return (
            <li
              key={item.number}
              aria-current={active ? 'step' : undefined}
              className={`flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold ${
                active
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : complete
                    ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
                    : 'bg-slate-100 text-slate-500 dark:bg-slate-800'
              }`}
            >
              <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full ${active ? 'bg-white/20' : 'bg-white dark:bg-slate-900'}`}>
                {complete ? '✓' : item.number}
              </span>
              {item.label}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function TargetCalculatorSubtab() {
  const [context, setContext] = useState<TargetCalculatorContext | null>(null);
  const [scenario, setScenario] = useState<TargetScenario | null>(null);
  const [regionalFilter, setRegionalFilter] = useState('all');
  const [targetMonth, setTargetMonth] = useState('');
  const [totalTarget, setTotalTarget] = useState('');
  const [minFloor, setMinFloor] = useState('');
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
      setError(getApiErrorMessage(err, 'Nu am putut incarca calculatorul de target.'));
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
  const displaySourceMonths = useMemo(() => {
    if (!scenario) return [];
    return [-13, -12, -1].map((offset) => {
      const month = shiftMonth(scenario.target_month, offset);
      return scenario.source_months.find((period) => period.month === month) ?? {
        month,
        label: monthLabel(month),
        role: offset === -1 ? 'floor_reference' : 'previous_year_reference',
      };
    });
  }, [scenario]);
  const tableTotals = useMemo(() => {
    const history = displaySourceMonths.map((source) => {
      const periods = filteredRows.map((row) => row.history.find((item) => item.month === source.month));
      const target = sum(periods.map((item) => item?.target ?? 0));
      const realized = sum(periods.map((item) => item?.realized ?? 0));
      return {
        month: source.month,
        target,
        realized,
        attainment: target > 0 ? realized * 100 / target : null,
      };
    });
    const completeTotal = (
      selector: (row: TargetScenarioRow) => number | null | undefined,
    ): number | null => {
      const values = filteredRows.map(selector);
      return values.every((value) => value != null)
        ? sum(values.map((value) => Number(value)))
        : null;
    };
    return {
      history,
      normalizedWeight: filteredRows.reduce((total, row) => total + row.normalized_weight, 0),
      proposedTarget: sum(filteredRows.map((row) => row.proposed_target)),
      finalTarget: filteredRows.length > 0 && filteredRows.every((row) => row.final_target != null)
        ? sum(filteredRows.map((row) => Number(row.final_target)))
        : null,
      salary: sum(filteredRows.map((row) => row.profitability.salary_cost_at_90_pct)),
      operatingCosts: completeTotal((row) => row.profitability.operating_costs),
      breakEven: completeTotal((row) => row.profitability.break_even_gross_sales),
      forecast: completeTotal((row) => row.profitability.forecast_sales),
    };
  }, [displaySourceMonths, filteredRows]);
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
  const regionalAllocation = useMemo(() => {
    if (!scenario) return [];
    const previousYearBaseMonth = shiftMonth(scenario.target_month, -13);
    const previousYearTargetMonth = shiftMonth(scenario.target_month, -12);
    const previousMonth = shiftMonth(scenario.target_month, -1);
    const groups = new Map<string, TargetScenarioRow[]>();
    scenario.rows.forEach((row) => {
      groups.set(row.regional, [...(groups.get(row.regional) ?? []), row]);
    });
    const aggregate = (manager: string, rows: TargetScenarioRow[]) => {
      const realized = (row: TargetScenarioRow, month: string) => (
        row.history.find((period) => period.month === month)?.realized ?? 0
      );
      const target = sum(rows.map((row) => row.proposed_target));
      const previous = sum(rows.map((row) => realized(row, previousMonth)));
      const previousYearBase = sum(rows.map((row) => realized(row, previousYearBaseMonth)));
      const previousYearTarget = sum(rows.map((row) => realized(row, previousYearTargetMonth)));
      const forecastValues = rows.map((row) => row.profitability.forecast_sales);
      const forecast = forecastValues.every((value) => value != null)
        ? sum(forecastValues.map((value) => Number(value)))
        : null;
      const seasonalityPct = percentChangeValue(previousYearTarget, previousYearBase);
      const seasonalTarget = seasonalityPct == null ? null : previous * (1 + seasonalityPct / 100);
      const targetVsPreviousPct = percentChangeValue(target, previous);
      const targetVsSeasonalPct = seasonalTarget == null ? null : percentChangeValue(target, seasonalTarget);
      const targetVsForecastPct = forecast == null ? null : percentChangeValue(target, forecast);
      const signal = targetVsForecastPct != null && targetVsForecastPct >= 5
        ? 'Peste AI'
        : targetVsSeasonalPct != null && Math.round(targetVsSeasonalPct * 10) / 10 >= 3
          ? 'Peste sezonier'
          : 'Echilibrat';
      return {
        manager,
        storeCount: rows.length,
        target,
        previous,
        previousYearTarget,
        forecast,
        seasonalityPct,
        seasonalTarget,
        targetVsPreviousPct,
        targetVsSeasonalPct,
        targetVsPreviousYearPct: percentChangeValue(target, previousYearTarget),
        targetVsForecastPct,
        signal,
      };
    };
    const network = aggregate('Rețea', scenario.rows);
    return Array.from(groups.entries())
      .map(([manager, rows]) => {
        const item = aggregate(manager, rows);
        const targetShare = network.target > 0 ? item.target * 100 / network.target : 0;
        const previousShare = network.previous > 0 ? item.previous * 100 / network.previous : 0;
        const previousYearShare = network.previousYearTarget > 0
          ? item.previousYearTarget * 100 / network.previousYearTarget
          : 0;
        const forecastShare = item.forecast != null && network.forecast
          ? item.forecast * 100 / network.forecast
          : null;
        return {
          ...item,
          targetShare,
          targetVsPreviousSharePp: targetShare - previousShare,
          targetVsPreviousYearSharePp: targetShare - previousYearShare,
          targetVsForecastSharePp: forecastShare == null ? null : targetShare - forecastShare,
        };
      })
      .sort((left, right) => right.target - left.target);
  }, [scenario]);
  const activeSeasonalityLabel = useMemo(() => {
    const years = Number(scenario?.calculation_params?.seasonality_years ?? 1);
    return years > 1 ? `Multi-year ${years} ani` : 'Sezonalitate anul trecut';
  }, [scenario]);
  const displayWarnings = useMemo(
    () => scenario?.warnings.filter((warning) => {
      if (warning.startsWith('Formula foloseste sezonalitate')) return false;
      if (warning.startsWith('Perioada ') && warning.includes('forecastate')) return false;
      return !['2023-06', '2023-07'].some((month) => warning.includes(month));
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
    if (!targetMonth || parsedTarget <= 0 || parsedFloor < 0) {
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
        previous_month_floor_pct: 0,
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
      setError(getApiErrorMessage(
        err,
        'Calculul nu a putut fi salvat. Verifica parametrii si lunile cu date disponibile.',
      ));
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
      setError(getApiErrorMessage(err, 'Targetele finale nu au putut fi salvate.'));
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
        setError(getApiErrorMessage(err, 'Salvarea automata a targetelor finale nu a reusit.'));
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
      setError(getApiErrorMessage(err, 'Targetul nu a putut fi finalizat.'));
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
      setError(getApiErrorMessage(err, 'Exportul Excel nu a putut fi generat.'));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-sm text-slate-500">Se incarca calculatorul de target...</div>;
  }

  const workflowStep: 1 | 2 | 3 | 4 = !scenario
    ? 1
    : scenario.status === 'finalized'
      ? 4
      : scenario.manual_adjustments_count === 0 && scenario.pending_final_count === scenario.store_count
        ? 2
        : 3;

  return (
    <div className="p-4 lg:p-6 space-y-4">
      <TargetWorkflow step={workflowStep} />
      {context?.can_finalize && (
        <div className="glass space-y-3 rounded-2xl p-3 sm:p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900 dark:text-slate-100">
                <Calculator size={18} className="text-indigo-500" />
                Calculator Target
              </h2>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Propunerea se calculeaza si se salveaza ca draft comun pentru magazinele cu vanzari in ultima luna disponibila anterior targetului.
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

          <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-5">
            <label className="col-span-2 space-y-1 text-xs text-slate-500 sm:col-span-1">
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
            <div className="col-span-2 space-y-1 text-xs text-slate-500 sm:col-span-1">
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
            <div className="col-span-2 flex items-end sm:col-span-1">
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
                  Calculatorul porneste de la forecastul lunii curente si il transforma intr-o estimare pentru luna target cu sezonalitate, trend, prag minim si cap.
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
                  Daca luna curenta este partiala, vanzarile sunt forecastate din importul disponibil si folosite ca baza curenta. Propunerea finala distribuie targetul total top-down proportional cu estimarile brute, apoi aplica pragul minim, cap-ul operational si rotunjirea. Valoarea Final manager ramane decizia editabila si trebuie sa insumeze targetul total la finalizare.
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

      {scenario && <div className="sticky top-2 z-20 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white/95 px-4 py-3 shadow-sm backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          Target {monthLabel(scenario.target_month)} · revizia {scenario.revision}
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
                  : 'Salvat în baza de date'}
          </span>
        )}
        {scenario.status === 'draft' && (
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {scenario.pending_final_count} locații de completat · {formatCurrency(scenario.remaining_difference)} rămas de distribuit
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

          <div className="glass grid grid-cols-2 divide-x divide-y divide-slate-200 overflow-hidden rounded-2xl sm:grid-cols-4 sm:divide-y-0 dark:divide-slate-700">
            <SummaryCard grouped label="Target total" value={formatCurrency(scenario.total_target)} detail={monthLabel(scenario.target_month)} />
            <SummaryCard grouped label="Calculat" value={formatCurrency(scenario.proposed_total)} detail={`${scenario.store_count} magazine active · ${activeSeasonalityLabel}`} />
            <SummaryCard
              grouped
              label="Final manager"
              value={formatCurrency(scenario.final_total)}
              detail={scenario.status === 'draft'
                ? `${scenario.pending_final_count} necompletate · ${scenario.manual_adjustments_count} ajustari`
                : 'Publicat in targetele oficiale'}
              emphasis="attention"
            />
            <SummaryCard
              grouped
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

          <div className="glass overflow-hidden rounded-2xl">
            <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-700">
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Cum a fost alocat targetul pe manageri</h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Δ mix arată dacă managerul primește o pondere mai mare sau mai mică decât contribuția sa la vânzări. „Peste sezonier” și „Peste AI” cer verificare, nu înseamnă automat alocare greșită.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[990px] table-fixed text-[11px]">
                <colgroup>
                  <col className="w-[150px]" />
                  <col className="w-[55px]" />
                  <col className="w-[100px]" />
                  <col className="w-[90px]" />
                  <col className="w-[95px]" />
                  <col className="w-[75px]" />
                  <col className="w-[90px]" />
                  <col className="w-[125px]" />
                  <col className="w-[100px]" />
                  <col className="w-[110px]" />
                </colgroup>
                <thead className="bg-slate-800 text-white dark:bg-slate-950">
                  <tr>
                    <th className="px-2 py-1.5 text-left">Manager</th>
                    <th className="px-2 py-1.5 text-right">Loc.</th>
                    <th className="px-2 py-1.5 text-right">Pondere target</th>
                    <th className="px-2 py-1.5 text-right">Δ mix vs iulie</th>
                    <th className="px-2 py-1.5 text-right">Target</th>
                    <th className="px-2 py-1.5 text-right">vs iulie</th>
                    <th className="px-2 py-1.5 text-right">vs sezonier</th>
                    <th className="px-2 py-1.5 text-right" title="vs august anul trecut">vs aug. 2025</th>
                    <th className="px-2 py-1.5 text-right">vs forecast AI</th>
                    <th className="px-2 py-1.5 text-center">Semnal</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {regionalAllocation.map((item) => (
                    <tr key={item.manager}>
                      <td className="truncate whitespace-nowrap px-2 py-1.5 font-semibold text-slate-800 dark:text-slate-100" title={item.manager}>{item.manager}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-slate-600 dark:text-slate-300">{item.storeCount}</td>
                      <td className="bg-amber-50 px-2 py-1.5 text-right font-semibold tabular-nums text-amber-800 dark:bg-amber-950/20 dark:text-amber-200">{formatPercent(item.targetShare)}</td>
                      <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${percentTone(item.targetVsPreviousSharePp)}`}>{formatSignedPp(item.targetVsPreviousSharePp)}</td>
                      <td className="px-2 py-1.5 text-right font-semibold tabular-nums text-slate-800 dark:text-slate-100">{formatTableNumber(item.target)}</td>
                      <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${percentTone(item.targetVsPreviousPct)}`}>{formatSignedPercent(item.targetVsPreviousPct)}</td>
                      <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${percentTone(item.targetVsSeasonalPct)}`}>{formatSignedPercent(item.targetVsSeasonalPct)}</td>
                      <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${percentTone(item.targetVsPreviousYearPct)}`}>{formatSignedPercent(item.targetVsPreviousYearPct)}</td>
                      <td className={`px-2 py-1.5 text-right font-semibold tabular-nums ${percentTone(item.targetVsForecastPct)}`}>{formatSignedPercent(item.targetVsForecastPct)}</td>
                      <td className="px-2 py-1.5 text-center">
                        <span className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                          item.signal === 'Peste AI'
                            ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                            : item.signal === 'Peste sezonier'
                              ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                              : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                        }`}>{item.signal}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="glass rounded-2xl overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
              <div>
                <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Target + profitabilitate per locație</h3>
                <p className="text-xs text-slate-500">
                  {filteredRows.length} locații afișate · <span className="font-semibold text-amber-700 dark:text-amber-300">Propunere manager</span> se salvează automat
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

            {scenario.profitability_summary.status !== 'ready' && (
              <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
                Surse financiare parțiale: P&amp;L {scenario.profitability_summary.pnl_store_count}/{scenario.store_count} magazine · forecast {scenario.profitability_summary.forecast_store_count}/{scenario.store_count}. Valorile lipsă rămân marcate, nu sunt estimate.
              </div>
            )}

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
                    <div className={`rounded-xl p-2 ${
                      row.profitability.break_even_gross_sales != null
                      && row.proposed_target < row.profitability.break_even_gross_sales
                        ? 'bg-red-50 dark:bg-red-950/25'
                        : 'bg-slate-50 dark:bg-slate-800/60'
                    }`}>
                      <p className="text-[10px] uppercase tracking-wide text-slate-400">Calcul target</p>
                      <p className={`font-semibold ${
                        row.profitability.break_even_gross_sales != null
                        && row.proposed_target < row.profitability.break_even_gross_sales
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-indigo-600 dark:text-indigo-300'
                      }`}>{formatCurrency(row.proposed_target)}</p>
                    </div>
                    <label className="rounded-xl border border-amber-200 bg-amber-50 p-2 dark:border-amber-900 dark:bg-amber-950/20">
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">Propunere manager</span>
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
                        <div key={source.month} className="rounded-xl bg-slate-50 p-2 text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
                          <p className="font-semibold">{monthLabel(source.month)}</p>
                          {showTarget && <p>T {formatTableNumber(period?.target)}</p>}
                          <p className="text-slate-400">R {formatTableNumber(period?.realized)}</p>
                          <p className={attainmentTone(period?.attainment_pct)}>
                            {period?.attainment_pct == null ? '-' : formatPercent(period.attainment_pct)}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
                    <div className="rounded-xl bg-slate-50 p-2 dark:bg-slate-800/60">
                      <p className="text-slate-400">Cheltuieli salariale</p>
                      <p className="font-semibold text-slate-700 dark:text-slate-200">{formatTableNumber(row.profitability.salary_cost_at_90_pct)}</p>
                    </div>
                    <div className="rounded-xl bg-slate-50 p-2 dark:bg-slate-800/60">
                      <p className="text-slate-400">Cheltuieli operaționale</p>
                      <p className="font-semibold text-slate-700 dark:text-slate-200">{formatTableNumber(row.profitability.operating_costs)}</p>
                    </div>
                    <div className="rounded-xl bg-orange-50 p-2 dark:bg-orange-950/20">
                      <p className="text-orange-700 dark:text-orange-300">Break-even brut</p>
                      <p className="font-semibold text-orange-800 dark:text-orange-200">{formatTableNumber(row.profitability.break_even_gross_sales)}</p>
                    </div>
                    <div className={`rounded-xl p-2 ${
                      row.profitability.forecast_sales != null
                      && row.profitability.break_even_gross_sales != null
                      && row.profitability.forecast_sales < row.profitability.break_even_gross_sales
                        ? 'bg-red-50 dark:bg-red-950/25'
                        : 'bg-emerald-50 dark:bg-emerald-950/20'
                    }`}>
                      <p className="text-slate-500 dark:text-slate-300">Forecast</p>
                      <p className={`font-semibold ${
                        row.profitability.forecast_sales != null
                        && row.profitability.break_even_gross_sales != null
                        && row.profitability.forecast_sales < row.profitability.break_even_gross_sales
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-emerald-600 dark:text-emerald-400'
                      }`}>{formatTableNumber(row.profitability.forecast_sales)}</p>
                    </div>
                  </div>
                  {[...(row.calculation_details.flags ?? []), ...row.profitability.anomaly_flags].length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(row.calculation_details.flags ?? []).slice(0, 2).map((flag) => (
                        <span key={flag} className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                          {flagLabel(flag)}
                        </span>
                      ))}
                      {row.profitability.anomaly_flags.map((flag) => (
                        <span key={flag} className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-700 dark:bg-red-900/30 dark:text-red-300">
                          {profitabilityFlagLabel(flag)}
                        </span>
                      ))}
                    </div>
                  )}
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

            <div className="compact-data-table hidden overflow-x-auto md:block">
              <table className="w-full min-w-[1610px] table-fixed text-[10px] leading-tight">
                <colgroup>
                  <col className="w-[60px]" />
                  <col className="w-[88px]" />
                  <col className="w-[165px]" />
                  <col className="w-[78px]" />
                  {displaySourceMonths.map((period) => (
                    <Fragment key={period.month}>
                      <col className="w-[68px]" />
                      <col className="w-[70px]" />
                      <col className="w-[50px]" />
                    </Fragment>
                  ))}
                  <col className="w-[62px]" />
                  <col className="w-[78px]" />
                  <col className="w-[160px]" />
                  <col className="w-[90px]" />
                  <col className="w-[90px]" />
                  <col className="w-[92px]" />
                  <col className="w-[82px]" />
                </colgroup>
                <thead>
                  <tr className="bg-blue-100 font-bold text-slate-800 dark:bg-blue-950/50 dark:text-slate-100">
                    <th className="px-1.5 py-1 text-left">SUBTOTAL</th>
                    <th colSpan={3} />
                    {tableTotals.history.map((period) => (
                      <Fragment key={period.month}>
                        <th className="px-1 py-1 text-right tabular-nums">{formatTableNumber(period.target)}</th>
                        <th className="px-1 py-1 text-right tabular-nums">{formatTableNumber(period.realized)}</th>
                        <th className={`px-1 py-1 text-right tabular-nums ${attainmentTone(period.attainment)}`}>
                          {period.attainment == null ? '-' : formatPercent(period.attainment)}
                        </th>
                      </Fragment>
                    ))}
                    <th className="px-1 py-1 text-right tabular-nums">{formatPercent(tableTotals.normalizedWeight * 100)}</th>
                    <th className="px-1 py-1 text-right tabular-nums">{formatTableNumber(tableTotals.proposedTarget)}</th>
                    <th className="bg-amber-50 px-1 py-1 text-right tabular-nums dark:bg-amber-950/20">{formatTableNumber(tableTotals.finalTarget)}</th>
                    <th className="px-1 py-1 text-right tabular-nums">{formatTableNumber(tableTotals.salary)}</th>
                    <th className="px-1 py-1 text-right tabular-nums">{formatTableNumber(tableTotals.operatingCosts)}</th>
                    <th className="bg-orange-50 px-1 py-1 text-right tabular-nums dark:bg-orange-950/20">{formatTableNumber(tableTotals.breakEven)}</th>
                    <th className={`px-1 py-1 text-right tabular-nums ${
                      tableTotals.forecast != null
                      && tableTotals.breakEven != null
                      && tableTotals.forecast < tableTotals.breakEven
                        ? 'bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-300'
                        : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-300'
                    }`}>{formatTableNumber(tableTotals.forecast)}</th>
                  </tr>
                  <tr className="bg-slate-800 text-white dark:bg-slate-950">
                    <th className="px-1 py-1 text-left font-semibold">Firma</th>
                    <th className="px-1 py-1 text-left font-semibold">Manager</th>
                    <th className="px-1 py-1 text-left font-semibold">Nume locație</th>
                    <th className="px-1 py-1 text-left font-semibold">Cod</th>
                    {displaySourceMonths.map((period) => (
                      <Fragment key={period.month}>
                        <th className="px-1 py-1 text-right font-semibold">Target<br />{period.month}</th>
                        <th className="px-1 py-1 text-right font-semibold">Realizat<br />{period.month}</th>
                        <th className="px-1 py-1 text-right font-semibold">%<br />{period.month}</th>
                      </Fragment>
                    ))}
                    <th className="px-1 py-1 text-right font-semibold">Pondere</th>
                    <th className="px-1 py-1 text-right font-semibold">Calcul<br />{monthLabel(scenario.target_month)}</th>
                    <th className="bg-red-900 px-1 py-1 text-right font-semibold">
                      <span className="flex items-center justify-end gap-1"><PencilLine size={12} /> Propunere manager</span>
                    </th>
                    <th className="px-1 py-1 text-right font-semibold" title="Cheltuieli salariale la 90% - P&L estimat">Salarii<br />90%</th>
                    <th className="px-1 py-1 text-right font-semibold" title="Cheltuieli operaționale estimate">OPEX<br />estimat</th>
                    <th className="px-1 py-1 text-right font-semibold" title="Break-even vânzări brute">Break-even<br />brut</th>
                    <th className="px-1 py-1 text-right font-semibold">Forecast<br />{monthLabel(scenario.target_month)}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {filteredRows.map((row) => (
                    <tr key={row.site_code}>
                      <td className="whitespace-nowrap px-1.5 py-1 text-slate-600 dark:text-slate-300">{row.firma}</td>
                      <td className="truncate whitespace-nowrap px-1.5 py-1 text-slate-600 dark:text-slate-300" title={row.regional}>{row.regional}</td>
                      <td
                        className={`px-1.5 py-1 ${
                          row.profitability.anomaly_flags.includes('PNL_INCOMPLETE')
                            ? 'bg-red-50 dark:bg-red-950/20'
                            : ''
                        }`}
                        title={
                          row.profitability.anomaly_flags.length > 0
                            ? `Anomalii: ${row.profitability.anomaly_flags.map(profitabilityFlagLabel).join(', ')}`
                            : undefined
                        }
                      >
                        <button
                          onClick={() => setDetailSiteCode(row.site_code)}
                          className="block max-w-full truncate text-left font-medium leading-tight text-slate-800 underline decoration-dotted underline-offset-4 hover:text-indigo-600 dark:text-slate-200 dark:hover:text-indigo-300"
                        >
                          {row.locatie}
                        </button>
                      </td>
                      <td className="truncate whitespace-nowrap px-1.5 py-1 text-slate-500 dark:text-slate-400" title={row.site_code}>{row.site_code}</td>
                      {displaySourceMonths.map((source) => {
                        const period = row.history.find((history) => history.month === source.month);
                        return (
                          <Fragment key={source.month}>
                            <td className="px-1.5 py-1 text-right tabular-nums text-slate-500 dark:text-slate-400">{formatTableNumber(period?.target)}</td>
                            <td className="px-1.5 py-1 text-right tabular-nums text-slate-700 dark:text-slate-200">{formatTableNumber(period?.realized)}</td>
                            <td className={`px-1.5 py-1 text-right tabular-nums ${attainmentTone(period?.attainment_pct)}`}>
                              {period?.attainment_pct == null ? '-' : formatPercent(period.attainment_pct)}
                            </td>
                          </Fragment>
                        );
                      })}
                      <td className="px-1.5 py-1 text-right tabular-nums text-slate-600 dark:text-slate-300">
                        {formatPercent(row.normalized_weight * 100)}
                      </td>
                      <td className={`px-1.5 py-1 text-right font-semibold tabular-nums ${
                        row.profitability.break_even_gross_sales != null
                        && row.proposed_target < row.profitability.break_even_gross_sales
                          ? 'bg-red-50 text-red-600 dark:bg-red-950/20 dark:text-red-400'
                          : 'text-slate-800 dark:text-slate-100'
                      }`}>
                        {formatTableNumber(row.proposed_target)}
                      </td>
                      <td className="border-x border-amber-100 bg-amber-50/50 px-1 py-0.5 text-right dark:border-amber-900 dark:bg-amber-950/10">
                        <div className="flex items-center justify-end gap-1">
                        <input
                          type="number"
                          min="0"
                          disabled={scenario.status === 'finalized'}
                          className="h-7 w-[72px] rounded-md border border-amber-300 bg-amber-50 px-1 text-right text-[10px] font-semibold tabular-nums text-slate-800 focus:outline-none focus:ring-1 focus:ring-amber-400 disabled:opacity-70 dark:border-amber-600 dark:bg-amber-950/30 dark:text-slate-100"
                          value={row.final_target ?? ''}
                          placeholder="Completeaza"
                          onChange={(event) => updateRow(row.site_code, 'final_target', event.target.value === '' ? null : Number(event.target.value))}
                        />
                        <input
                          disabled={scenario.status === 'finalized'}
                          className="h-7 w-[78px] rounded-md border border-slate-200 bg-white px-1 text-[10px] text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-70 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                          placeholder="Observație"
                          title="Observație manager"
                          value={row.note ?? ''}
                          onChange={(event) => updateRow(row.site_code, 'note', event.target.value)}
                        />
                        </div>
                      </td>
                      <td className="px-1.5 py-1 text-right tabular-nums text-slate-700 dark:text-slate-200">{formatTableNumber(row.profitability.salary_cost_at_90_pct)}</td>
                      <td className="px-1.5 py-1 text-right tabular-nums text-slate-700 dark:text-slate-200">{formatTableNumber(row.profitability.operating_costs)}</td>
                      <td className="bg-orange-50 px-1.5 py-1 text-right font-semibold tabular-nums text-orange-800 dark:bg-orange-950/20 dark:text-orange-200">{formatTableNumber(row.profitability.break_even_gross_sales)}</td>
                      <td className={`px-1.5 py-1 text-right font-semibold tabular-nums ${
                        row.profitability.forecast_sales == null
                          ? 'text-slate-400'
                          : row.profitability.break_even_gross_sales != null
                          && row.profitability.forecast_sales < row.profitability.break_even_gross_sales
                            ? 'bg-red-50 text-red-600 dark:bg-red-950/20 dark:text-red-400'
                            : row.profitability.anomaly_flags.includes('FORECAST_BELOW_TARGET')
                              ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/20 dark:text-amber-300'
                            : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-300'
                      }`}>{formatTableNumber(row.profitability.forecast_sales)}</td>
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
