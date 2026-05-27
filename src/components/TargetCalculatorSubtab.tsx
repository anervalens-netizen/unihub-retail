import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Calculator,
  CheckCircle2,
  Download,
  RefreshCw,
  RotateCcw,
  Save,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
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
  finalizeTargetScenario,
  saveTargetFinalValues,
  type TargetCalculatorContext,
  type TargetScenario,
  type TargetScenarioRow,
} from '../api/targetCalculator';
import { formatCurrency, formatPercent } from '../lib/formatters';

const inputCls = 'rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';

function monthLabel(month: string): string {
  const [year, monthNumber] = month.split('-');
  const labels = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];
  return `${labels[Number(monthNumber) - 1]} ${year}`;
}

function isPreviousYearPeriod(role: string): boolean {
  return role === 'previous_year_reference' || role === 'year_over_year';
}

function sum(values: number[]): number {
  return Math.round(values.reduce((total, value) => total + value, 0) * 100) / 100;
}

function recalculateVisibleScenario(scenario: TargetScenario, rows: TargetScenarioRow[]): TargetScenario {
  const regional = new Map<string, { regional: string; store_count: number; floor_total: number; proposed_total: number; final_total: number }>();
  rows.forEach((row) => {
    const item = regional.get(row.regional) ?? {
      regional: row.regional,
      store_count: 0,
      floor_total: 0,
      proposed_total: 0,
      final_total: 0,
    };
    item.store_count += 1;
    item.floor_total += row.floor_target;
    item.proposed_total += row.proposed_target;
    item.final_total += row.final_target;
    regional.set(row.regional, item);
  });
  const finalTotal = sum(rows.map((row) => row.final_target));
  return {
    ...scenario,
    rows,
    final_total: finalTotal,
    remaining_difference: Math.round((scenario.total_target - finalTotal) * 100) / 100,
    manual_adjustments_count: rows.filter((row) => Math.abs(row.final_target - row.proposed_target) > 0.01).length,
    regional_summary: Array.from(regional.values()).sort((left, right) => left.regional.localeCompare(right.regional)),
  };
}

function SummaryCard({ label, value, detail, emphasis }: {
  label: string;
  value: string;
  detail?: string;
  emphasis?: 'good' | 'warning';
}) {
  const color = emphasis === 'good'
    ? 'text-emerald-600 dark:text-emerald-400'
    : emphasis === 'warning'
      ? 'text-amber-600 dark:text-amber-400'
      : 'text-slate-900 dark:text-slate-100';
  return (
    <div className="glass rounded-2xl p-4 min-w-0">
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

export function TargetCalculatorSubtab() {
  const [context, setContext] = useState<TargetCalculatorContext | null>(null);
  const [scenario, setScenario] = useState<TargetScenario | null>(null);
  const [regionalFilter, setRegionalFilter] = useState('all');
  const [targetMonth, setTargetMonth] = useState('');
  const [totalTarget, setTotalTarget] = useState('');
  const [minFloor, setMinFloor] = useState('');
  const [floorPct, setFloorPct] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dirtyRows, setDirtyRows] = useState<Set<string>>(() => new Set());
  const [savingRows, setSavingRows] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  const scenarioRef = useRef<TargetScenario | null>(null);
  const dirtyRowsRef = useRef<Set<string>>(new Set());
  const editVersionsRef = useRef<Map<string, number>>(new Map());
  const dirty = dirtyRows.size > 0;

  const replaceScenario = (next: TargetScenario | null) => {
    scenarioRef.current = next;
    setScenario(next);
  };

  const clearLocalEdits = () => {
    dirtyRowsRef.current = new Set();
    setDirtyRows(new Set());
    editVersionsRef.current.clear();
  };

  const loadInitial = async () => {
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
  };

  useEffect(() => {
    void loadInitial();
  }, []);

  useEffect(() => {
    scenarioRef.current = scenario;
  }, [scenario]);

  const regionals = useMemo(
    () => scenario?.regional_summary.map((item) => item.regional) ?? context?.regionals ?? [],
    [scenario, context],
  );
  const filteredRows = useMemo(
    () => scenario?.rows.filter((row) => regionalFilter === 'all' || row.regional === regionalFilter) ?? [],
    [scenario, regionalFilter],
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
  const sourceChart = useMemo(() => {
    if (!scenario) return [];
    return scenario.source_months.map((source) => {
      const values = filteredRows.map((row) => row.history.find((history) => history.month === source.month));
      return {
        month: monthLabel(source.month),
        target: sum(values.map((value) => value?.target ?? 0)),
        realized: sum(values.map((value) => value?.realized ?? 0)),
        actualRealized: sum(values.map((value) => value?.actual_realized ?? value?.realized ?? 0)),
        isForecast: values.some((value) => value?.is_forecast),
      };
    });
  }, [scenario, filteredRows]);
  const regionalChart = useMemo(
    () => scenario?.regional_summary.filter((item) => regionalFilter === 'all' || item.regional === regionalFilter) ?? [],
    [scenario, regionalFilter],
  );

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

  const updateRow = (siteCode: string, field: 'final_target' | 'note', value: number | string) => {
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

  const persistRows = async (siteCodes: string[]): Promise<TargetScenario | null> => {
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
        rowsToSave.map((row) => ({
          site_code: row.site_code,
          final_target: row.final_target,
          note: row.note,
        })),
      );
      setDirtyRows((previous) => {
        const next = new Set(previous);
        submittedVersions.forEach((version, siteCode) => {
          if ((editVersionsRef.current.get(siteCode) ?? 0) === version) {
            next.delete(siteCode);
          }
        });
        dirtyRowsRef.current = next;
        return next;
      });
      setError(null);
      return saved;
    } finally {
      setSavingRows((previous) => {
        const next = new Set(previous);
        siteCodes.forEach((siteCode) => next.delete(siteCode));
        return next;
      });
    }
  };

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
  }, [scenario, dirtyRows, savingRows]);

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
  }, [scenario?.id, dirtyRows.size, savingRows.size]);

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
      if (Math.abs(latest.remaining_difference) > 0.01) {
        setError('Pentru finalizare, suma targetelor finale trebuie sa fie egala cu targetul total.');
        return;
      }
      if (!window.confirm(
        `Finalizezi scenariul pentru exact cele ${latest.store_count} magazine active? `
        + 'Valorile vor deveni targetele oficiale din Hub si CRM, iar orice target existent in afara acestei cohorte va fi eliminat.',
      )) return;
      replaceScenario(await finalizeTargetScenario(latest.id));
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

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
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

        {context && (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Ultima luna cu vanzari: <strong>{monthLabel(context.latest_sales_month)}</strong>.
            Pentru noul target, cohorta curenta contine <strong>{context.active_store_count}</strong> magazine active.
            Magazinele fara vanzari in luna cohortei nu vor fi publicate in targetul final.
          </p>
        )}
      </div>

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

          {scenario.warnings.length > 0 && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-900/20 dark:text-amber-300">
              {scenario.warnings.map((warning) => <p key={warning}>{warning}</p>)}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard label="Target total" value={formatCurrency(scenario.total_target)} detail={monthLabel(scenario.target_month)} />
            <SummaryCard label="Calculat" value={formatCurrency(scenario.proposed_total)} detail={`${scenario.store_count} magazine active`} />
            <SummaryCard
              label="Target final"
              value={formatCurrency(scenario.final_total)}
              detail={`${scenario.manual_adjustments_count} ajustari manuale`}
              emphasis={Math.abs(scenario.remaining_difference) <= 0.01 ? 'good' : 'warning'}
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
              <div className="mt-3 overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
                <div className="min-w-[585px]">
                  <div className="grid grid-cols-[minmax(130px,1fr)_120px_120px_105px_110px] bg-slate-50 px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:bg-slate-800">
                    <span>Manager</span>
                    <span className="text-right">Calculator</span>
                    <span className="text-right">Final manager</span>
                    <span className="text-right">Diferenta</span>
                    <span className="text-right">Status</span>
                  </div>
                  <div className="divide-y divide-slate-100 dark:divide-slate-800">
                    {regionalChart.map((manager) => {
                      const difference = manager.final_total - manager.proposed_total;
                      const status = managerTargetStatus(manager.proposed_total, manager.final_total);
                      return (
                        <div key={manager.regional} className="grid grid-cols-[minmax(130px,1fr)_120px_120px_105px_110px] items-center px-3 py-3 text-xs">
                          <div>
                            <p className="font-semibold text-slate-700 dark:text-slate-200">{manager.regional}</p>
                            <p className="text-[10px] text-slate-400">{manager.store_count} magazine</p>
                          </div>
                          <span className="text-right font-medium tabular-nums text-indigo-600 dark:text-indigo-300">
                            {formatCurrency(manager.proposed_total)}
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
              <div className="mt-3 h-64">
                <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                  <BarChart data={sourceChart} margin={{ top: 4, right: 4, left: 4, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.15)" />
                    <XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                    <YAxis tickFormatter={(value) => `${Math.round(Number(value) / 1000)}k`} tick={{ fill: '#94a3b8', fontSize: 10 }} />
                    <Tooltip formatter={(value: number) => formatCurrency(value)} />
                    <Legend />
                    <Bar dataKey="target" name="Target istoric" fill="#cbd5e1" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="realized" name="Realizat / Forecast folosit" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="glass rounded-2xl overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
              <div>
                <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Target per locatie</h3>
                <p className="text-xs text-slate-500">
                  {filteredRows.length} locatii afisate · targetul final este editabil si se salveaza automat pentru toti managerii
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {scenario.status === 'draft' && (
                  <>
                    <button onClick={resetToProposal} disabled={busy} className="flex items-center gap-1.5 rounded-xl bg-slate-100 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-200 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700">
                      <RotateCcw size={13} /> {regionalFilter === 'all' ? 'Reset propunere' : 'Reset manager'}
                    </button>
                    <button onClick={handleSave} disabled={busy || !dirty} className="flex items-center gap-1.5 rounded-xl bg-indigo-100 px-3 py-2 text-xs font-medium text-indigo-700 hover:bg-indigo-200 disabled:opacity-50 dark:bg-indigo-900/30 dark:text-indigo-300">
                      <Save size={13} /> Salveaza acum
                    </button>
                    <button onClick={handleFinalize} disabled={busy} className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
                      <CheckCircle2 size={13} /> Finalizeaza
                    </button>
                  </>
                )}
                <button onClick={handleExport} disabled={busy} className="flex items-center gap-1.5 rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900">
                  <Download size={13} /> Export Excel
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-[1380px] w-full text-xs">
                <thead className="bg-slate-50 text-slate-500 dark:bg-slate-800/70 dark:text-slate-400">
                  <tr>
                    <th rowSpan={2} className="px-3 py-2 text-left font-semibold align-bottom">Locatie</th>
                    <th rowSpan={2} className="px-3 py-2 text-left font-semibold align-bottom">Manager</th>
                    {scenario.source_months.map((period) => (
                      <th key={period.month} colSpan={2} className={`border-b px-3 py-2 text-center font-semibold ${
                        isPreviousYearPeriod(period.role)
                          ? 'border-indigo-200 bg-indigo-100/80 text-indigo-700 dark:border-indigo-800 dark:bg-indigo-900/35 dark:text-indigo-300'
                          : 'border-slate-200 dark:border-slate-700'
                      }`}>
                        {monthLabel(period.month)}
                        {isPreviousYearPeriod(period.role) && <p className="text-[9px] uppercase tracking-wide">Anul trecut</p>}
                        {forecastMonths.has(period.month) && <p className="text-[9px] uppercase tracking-wide text-sky-600 dark:text-sky-300">Forecast</p>}
                      </th>
                    ))}
                    <th rowSpan={2} className="px-3 py-2 text-right font-semibold align-bottom">Calculat</th>
                    <th rowSpan={2} className="px-3 py-2 text-right font-semibold align-bottom">Final</th>
                    <th rowSpan={2} className="px-3 py-2 text-right font-semibold align-bottom">Delta</th>
                    <th rowSpan={2} className="px-3 py-2 text-left font-semibold align-bottom">Observatii</th>
                  </tr>
                  <tr>
                    {scenario.source_months.map((period) => (
                      <Fragment key={period.month}>
                        <th className={`px-3 py-2 text-right font-medium ${
                          isPreviousYearPeriod(period.role)
                            ? 'bg-indigo-50 text-indigo-500 dark:bg-indigo-900/20 dark:text-indigo-300'
                            : 'text-slate-400'
                        }`}>Target</th>
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
                        <p className="font-medium text-slate-800 dark:text-slate-200">{row.locatie}</p>
                        <p className="text-[10px] text-slate-400">{row.site_code} · {row.firma}</p>
                      </td>
                      <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{row.regional}</td>
                      {row.history.map((period) => (
                        <Fragment key={period.month}>
                          <td className={`px-3 py-2 text-right tabular-nums ${
                            isPreviousYearPeriod(period.role)
                              ? 'bg-indigo-50/70 font-medium text-indigo-700 dark:bg-indigo-900/15 dark:text-indigo-300'
                              : 'text-slate-500 dark:text-slate-400'
                          }`}>
                            {formatCurrency(period.target)}
                          </td>
                          <td className={`px-3 py-2 text-right tabular-nums ${
                            isPreviousYearPeriod(period.role)
                              ? 'bg-indigo-50/70 font-medium text-indigo-800 dark:bg-indigo-900/15 dark:text-indigo-200'
                              : 'text-slate-700 dark:text-slate-200'
                          }`}>
                            {formatCurrency(period.realized)}
                            <p className="text-[10px] text-slate-400">
                              {period.is_forecast ? 'Forecast ' : ''}{formatPercent(period.attainment_pct)}
                            </p>
                            {period.is_forecast && (
                              <p className="text-[10px] text-slate-400">
                                Real: {formatCurrency(period.actual_realized ?? period.realized)}
                              </p>
                            )}
                          </td>
                        </Fragment>
                      ))}
                      <td className="px-3 py-2 text-right font-semibold tabular-nums text-indigo-600 dark:text-indigo-300">{formatCurrency(row.proposed_target)}</td>
                      <td className="px-3 py-2 text-right">
                        <input
                          type="number"
                          min="0"
                          disabled={scenario.status === 'finalized'}
                          className={`${inputCls} w-32 text-right font-semibold tabular-nums disabled:opacity-70`}
                          value={row.final_target}
                          onChange={(event) => updateRow(row.site_code, 'final_target', Number(event.target.value || 0))}
                        />
                      </td>
                      <td className={`px-3 py-2 text-right font-semibold tabular-nums ${
                        row.final_target - row.proposed_target > 0.01
                          ? 'text-emerald-600'
                          : row.final_target - row.proposed_target < -0.01
                            ? 'text-red-600'
                            : 'text-slate-400'
                      }`}>
                        {formatCurrency(row.final_target - row.proposed_target)}
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
    </div>
  );
}
