import { useEffect, useState } from 'react';
import { RefreshCw, AlertTriangle, BarChart2, ChevronDown, ChevronRight, Info, X } from 'lucide-react';
import { fetchScores, fetchAlerts, recalculateScores, type StoreScore, type StoreAlert } from '../api/crm';
import { createTask } from '../api/tasks';

const CURRENT_MONTH = new Date().toISOString().slice(0, 7);

// ─── Utilitare ────────────────────────────────────────────────────────────────

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' :
    score >= 40 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' :
    score === -1 ? 'bg-slate-100 text-slate-400 dark:bg-slate-800' :
    'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold tabular-nums ${color}`}>
      {score === -1 ? '—' : score}
    </span>
  );
}

function ScoreBar({ score }: { score: number }) {
  if (score < 0) return null;
  const color = score >= 70 ? 'bg-green-500' : score >= 40 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="w-20 bg-slate-200 dark:bg-slate-700 rounded-full h-1.5 shrink-0">
      <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${Math.min(score, 100)}%` }} />
    </div>
  );
}

function avgScore(items: { score: number }[]) {
  const valid = items.filter((i) => i.score >= 0);
  if (!valid.length) return -1;
  return Math.round(valid.reduce((s, i) => s + i.score, 0) / valid.length);
}

function toggle(set: Set<string>, key: string): Set<string> {
  const next = new Set(set);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  return next;
}

// ─── Breakdown detaliat per magazin ──────────────────────────────────────────

function ComponentBar({ label, value, max, sublabel, color = 'bg-indigo-500' }: {
  label: string; value: number; max: number; sublabel?: string; color?: string;
}) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-600 dark:text-slate-400">{label}</span>
        <span className="text-xs font-mono font-semibold text-slate-700 dark:text-slate-300">
          {value.toFixed(1)} <span className="text-slate-400 font-normal">/ {max}</span>
        </span>
      </div>
      <div className="h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-2 rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      {sublabel && <p className="text-[10px] text-slate-400 mt-0.5">{sublabel}</p>}
    </div>
  );
}

function KPIComponentBar({ label, storeVal, avg, score, max = 10, color = 'bg-sky-500' }: {
  label: string; storeVal: number; avg: number; score: number; max?: number; color?: string;
}) {
  const pct = Math.min((score / max) * 100, 100);
  // Average marker sits at 50% (score of 5/10 = avg store)
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-600 dark:text-slate-400">{label}</span>
        <span className="text-xs text-slate-700 dark:text-slate-300">
          <strong className="font-mono">{storeVal.toFixed(1)}%</strong>
          <span className="text-slate-400 font-normal"> / med. {avg.toFixed(1)}%</span>
        </span>
      </div>
      <div className="relative h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-2 rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
        <div className="absolute top-0 bottom-0 w-0.5 bg-slate-500/40 dark:bg-slate-400/40" style={{ left: '50%' }} />
      </div>
      <p className="text-[10px] text-slate-400 mt-0.5">{score.toFixed(1)} / {max} pct · linia = media lunii</p>
    </div>
  );
}

function StoreBreakdown({ store }: { store: StoreScore }) {
  const bd = store.breakdown;
  if (!bd) {
    return (
      <div className="px-6 py-3 text-xs text-slate-400 italic">
        Scor necalculat — apasă Recalculează.
      </div>
    );
  }

  const isForecast = bd.forecast_factor > 1.001;
  const trendPct = bd.trend_pct > 0
    ? `+${((bd.trend_pct / 30) * 40 - 20).toFixed(0)}% față de luna anterioară`
    : `scădere față de luna anterioară`;

  return (
    <div className="px-6 py-3 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-800 space-y-3">
      <ComponentBar
        label="Target atins"
        value={bd.target_pct}
        max={40}
        sublabel={`${bd.target_attainment}% din target${isForecast ? ` (previzionat ${bd.forecast_factor.toFixed(2)}×)` : ''}`}
        color={bd.target_pct >= 28 ? 'bg-green-500' : bd.target_pct >= 16 ? 'bg-amber-500' : 'bg-red-500'}
      />
      <ComponentBar
        label="Trend față de luna anterioară"
        value={bd.trend_pct}
        max={30}
        sublabel={trendPct}
        color={bd.trend_pct >= 20 ? 'bg-green-500' : bd.trend_pct >= 10 ? 'bg-amber-500' : 'bg-red-500'}
      />
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-slate-600 dark:text-slate-400">KPI calitate</span>
          <span className="text-xs font-mono font-semibold text-slate-700 dark:text-slate-300">
            {bd.kpi_pct.toFixed(1)} <span className="text-slate-400 font-normal">/ 20</span>
          </span>
        </div>
        <div className="space-y-2 pl-2 border-l-2 border-sky-200 dark:border-sky-800">
          <KPIComponentBar
            label="Bon2+"
            storeVal={bd.kpi_bon2acc}
            avg={bd.kpi_bon2acc_avg}
            score={bd.kpi_bon2acc_score}
            color="bg-sky-500"
          />
          <KPIComponentBar
            label="Focus"
            storeVal={bd.kpi_focus}
            avg={bd.kpi_focus_avg}
            score={bd.kpi_focus_score}
            color="bg-violet-500"
          />
        </div>
      </div>
      <ComponentBar
        label="Vizite ASM"
        value={bd.visits_pct}
        max={10}
        sublabel={
          bd.nr_vizite === 0
            ? 'Nicio vizită înregistrată în această lună'
            : `${bd.nr_vizite} vizită${bd.nr_vizite !== 1 ? 'e' : ''} · completare medie ${bd.avg_completion}%`
        }
        color={bd.visits_pct >= 7 ? 'bg-green-500' : bd.visits_pct >= 4 ? 'bg-amber-500' : 'bg-red-500'}
      />
      <div className="pt-1 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between">
        <span className="text-xs text-slate-500">Scor total</span>
        <ScoreBadge score={store.score} />
      </div>
    </div>
  );
}

function AlertBreakdown({ alert }: { alert: StoreAlert }) {
  return (
    <div className="px-6 py-3 bg-red-50/70 dark:bg-red-900/10 border-t border-red-100 dark:border-red-900/30 space-y-2">
      {alert.reasons.map((r, i) => (
        <div key={i} className="flex items-start gap-2">
          <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
          <p className="text-xs text-red-700 dark:text-red-300">{r}</p>
        </div>
      ))}
      {alert.score >= 0 && (
        <p className="text-[10px] text-slate-400 pt-1">
          Scor curent: {alert.score}/100. Pragul de alertă: sub 40.
        </p>
      )}
    </div>
  );
}

// ─── Panel explicație scoring ─────────────────────────────────────────────────

function ScoringInfo({ onClose }: { onClose: () => void }) {
  return (
    <div className="glass rounded-2xl p-4 space-y-3 border border-indigo-200 dark:border-indigo-800">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">Cum se calculează scorul?</span>
        <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400">
          <X size={14} />
        </button>
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Fiecare magazin primește un scor de la <strong className="text-slate-700 dark:text-slate-300">0 la 100</strong> compus din 4 componente:
      </p>
      <div className="space-y-2.5">
        {[
          {
            label: 'Target atins', pts: '40 pct',
            color: 'bg-indigo-500',
            desc: 'Previziunea lunii curente (vânzări extrapolate la finalul lunii) față de target. 100% target = 40 puncte.',
          },
          {
            label: 'Trend', pts: '30 pct',
            color: 'bg-violet-500',
            desc: 'Previziunea lunii curente față de realizatul lunii anterioare. −20% sau mai mult = 0 pct, +20% sau mai mult = 30 pct.',
          },
          {
            label: 'KPI calitate', pts: '20 pct',
            color: 'bg-sky-500',
            desc: 'Bon2+ și Focus raportate la media lunii. La medie = 10 pct, dublu față de medie = 20 pct. Compus din două sub-scoruri (max 10 fiecare).',
          },
          {
            label: 'Vizite ASM', pts: '10 pct',
            color: 'bg-emerald-500',
            desc: '1 vizită = bază 5 pct, 2+ vizite = bază 10 pct, ponderate cu gradul de completare al formularului (completion_pct). Ex: 2 vizite la 83% → 8.3 pct.',
          },
        ].map(({ label, pts, color, desc }) => (
          <div key={label} className="flex gap-3">
            <div className={`w-1.5 rounded-full shrink-0 mt-1 ${color}`} style={{ minHeight: 32 }} />
            <div>
              <div className="flex items-baseline gap-2">
                <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">{label}</span>
                <span className="text-[10px] font-bold text-slate-400">{pts}</span>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">{desc}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="pt-1 border-t border-slate-200 dark:border-slate-700">
        <p className="text-[10px] text-slate-400">
          <strong className="text-green-600 dark:text-green-400">≥ 70</strong> — performanță bună &nbsp;·&nbsp;
          <strong className="text-amber-600 dark:text-amber-400">40–69</strong> — necesită atenție &nbsp;·&nbsp;
          <strong className="text-red-600 dark:text-red-400">&lt; 40</strong> — alertă
        </p>
      </div>
    </div>
  );
}

// ─── Grupare date ─────────────────────────────────────────────────────────────

type AsmGroup<T> = { asm: string; items: T[] };
type RegionalGroup<T> = { regional: string; asms: AsmGroup<T>[] };

function groupByHierarchy<T extends { regional: string; asm: string }>(
  items: T[]
): RegionalGroup<T>[] {
  const map = new Map<string, Map<string, T[]>>();
  for (const item of items) {
    if (!map.has(item.regional)) map.set(item.regional, new Map());
    const asmMap = map.get(item.regional)!;
    if (!asmMap.has(item.asm)) asmMap.set(item.asm, []);
    asmMap.get(item.asm)!.push(item);
  }
  return Array.from(map.entries()).map(([regional, asmMap]) => ({
    regional,
    asms: Array.from(asmMap.entries()).map(([asm, items]) => ({ asm, items })),
  }));
}

// ─── Scoruri view ─────────────────────────────────────────────────────────────

function ScoresTree({ scores }: { scores: StoreScore[] }) {
  const groups = groupByHierarchy(scores);
  const [expandedRegionals, setExpandedRegionals] = useState<Set<string>>(new Set());
  const [expandedAsms, setExpandedAsms] = useState<Set<string>>(new Set());
  const [expandedStore, setExpandedStore] = useState<string | null>(null);

  if (!scores.length) {
    return (
      <div className="text-center text-slate-400 py-8 text-sm">
        Niciun scor calculat. Apasă Recalculează.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {groups.map(({ regional, asms }) => {
        const allStores = asms.flatMap((a) => a.items);
        const isOpen = expandedRegionals.has(regional);
        const regionalAvg = avgScore(allStores);

        return (
          <div key={regional} className="glass rounded-2xl overflow-hidden">
            <button
              onClick={() => setExpandedRegionals((p) => toggle(p, regional))}
              className="w-full flex items-center gap-2.5 px-4 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
            >
              {isOpen ? <ChevronDown size={14} className="text-slate-400 shrink-0" /> : <ChevronRight size={14} className="text-slate-400 shrink-0" />}
              <span className="flex-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{regional}</span>
              <span className="text-xs text-slate-400">{allStores.length} mag.</span>
              <ScoreBadge score={regionalAvg} />
            </button>

            {isOpen && (
              <div className="border-t border-slate-200 dark:border-slate-700 divide-y divide-slate-100 dark:divide-slate-800">
                {asms.map(({ asm, items }) => {
                  const asmKey = `${regional}::${asm}`;
                  const isAsmOpen = expandedAsms.has(asmKey);
                  const asmAvg = avgScore(items);

                  return (
                    <div key={asm}>
                      <button
                        onClick={() => setExpandedAsms((p) => toggle(p, asmKey))}
                        className="w-full flex items-center gap-2 px-5 py-2.5 text-left hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                      >
                        {isAsmOpen ? <ChevronDown size={12} className="text-slate-300 shrink-0" /> : <ChevronRight size={12} className="text-slate-300 shrink-0" />}
                        <span className="flex-1 text-xs font-semibold text-slate-600 dark:text-slate-300">{asm}</span>
                        <span className="text-[11px] text-slate-400">{items.length} mag.</span>
                        <ScoreBadge score={asmAvg} />
                      </button>

                      {isAsmOpen && (
                        <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
                          {items.map((s) => (
                            <div key={s.site_code}>
                              <button
                                onClick={() => setExpandedStore(expandedStore === s.site_code ? null : s.site_code)}
                                className="w-full flex items-center gap-3 px-6 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors"
                              >
                                {expandedStore === s.site_code
                                  ? <ChevronDown size={11} className="text-slate-300 shrink-0" />
                                  : <ChevronRight size={11} className="text-slate-300 shrink-0" />}
                                <ScoreBadge score={s.score} />
                                <div className="flex-1 min-w-0">
                                  <span className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate block">
                                    {s.locatie}
                                  </span>
                                  <span className="text-[10px] text-slate-400">{s.site_code}</span>
                                </div>
                                {s.breakdown && expandedStore !== s.site_code && (
                                  <span className="text-[10px] text-slate-400 hidden sm:block shrink-0">
                                    {s.breakdown.target_attainment}% target
                                  </span>
                                )}
                                <ScoreBar score={s.score} />
                              </button>
                              {expandedStore === s.site_code && <StoreBreakdown store={s} />}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Alerte view ──────────────────────────────────────────────────────────────

function AlertsTree({ alerts, onCreateTask }: { alerts: StoreAlert[]; onCreateTask: (a: StoreAlert) => void }) {
  const groups = groupByHierarchy(alerts);
  const [expandedRegionals, setExpandedRegionals] = useState<Set<string>>(new Set());
  const [expandedAsms, setExpandedAsms] = useState<Set<string>>(new Set());
  const [expandedStore, setExpandedStore] = useState<string | null>(null);

  if (!alerts.length) {
    return (
      <div className="text-center text-slate-400 py-8 text-sm">
        Nicio alertă pentru luna selectată. Apasă Recalculează dacă nu s-au calculat scorurile.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {groups.map(({ regional, asms }) => {
        const isOpen = expandedRegionals.has(regional);
        const total = asms.reduce((s, a) => s + a.items.length, 0);

        return (
          <div key={regional} className="rounded-2xl border border-red-200 dark:border-red-900/40 overflow-hidden">
            <button
              onClick={() => setExpandedRegionals((p) => toggle(p, regional))}
              className="w-full flex items-center gap-2.5 px-4 py-3 text-left bg-red-50 dark:bg-red-900/10 hover:bg-red-100/60 dark:hover:bg-red-900/20 transition-colors"
            >
              {isOpen ? <ChevronDown size={14} className="text-red-400 shrink-0" /> : <ChevronRight size={14} className="text-red-400 shrink-0" />}
              <AlertTriangle size={13} className="text-red-500 shrink-0" />
              <span className="flex-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{regional}</span>
              <span className="text-xs text-red-500 font-medium">{total} alertă{total !== 1 ? 'e' : ''}</span>
            </button>

            {isOpen && (
              <div className="divide-y divide-red-100 dark:divide-red-900/30">
                {asms.map(({ asm, items }) => {
                  const asmKey = `${regional}::${asm}`;
                  const isAsmOpen = expandedAsms.has(asmKey);

                  return (
                    <div key={asm}>
                      <button
                        onClick={() => setExpandedAsms((p) => toggle(p, asmKey))}
                        className="w-full flex items-center gap-2 px-5 py-2 text-left bg-red-50/50 dark:bg-red-900/5 hover:bg-red-50 dark:hover:bg-red-900/15 transition-colors"
                      >
                        {isAsmOpen ? <ChevronDown size={12} className="text-red-300 shrink-0" /> : <ChevronRight size={12} className="text-red-300 shrink-0" />}
                        <span className="flex-1 text-xs font-semibold text-slate-600 dark:text-slate-300">{asm}</span>
                        <span className="text-[11px] text-red-400">{items.length}</span>
                      </button>

                      {isAsmOpen && (
                        <div className="divide-y divide-red-100/60 dark:divide-red-900/20">
                          {items.map((alertItem) => (
                            <div key={alertItem.site_code}>
                              <div className="flex items-center gap-3 px-6 py-2.5">
                                <button
                                  onClick={() => setExpandedStore(expandedStore === alertItem.site_code ? null : alertItem.site_code)}
                                  className="flex items-center gap-2 flex-1 min-w-0 text-left"
                                >
                                  {expandedStore === alertItem.site_code
                                    ? <ChevronDown size={11} className="text-red-300 shrink-0" />
                                    : <ChevronRight size={11} className="text-red-300 shrink-0" />}
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-2">
                                      <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 truncate">
                                        {alertItem.locatie}
                                      </span>
                                      <ScoreBadge score={alertItem.score} />
                                    </div>
                                    <span className="text-[10px] text-slate-400">{alertItem.site_code}</span>
                                    {expandedStore !== alertItem.site_code && (
                                      <p className="text-[11px] text-red-500 dark:text-red-400 mt-0.5">
                                        {alertItem.reasons.length} problemă{alertItem.reasons.length !== 1 ? 'e' : ''}
                                      </p>
                                    )}
                                  </div>
                                </button>
                                <button
                                  onClick={() => onCreateTask(alertItem)}
                                  className="shrink-0 px-2.5 py-1.5 rounded-xl bg-indigo-100 hover:bg-indigo-200 dark:bg-indigo-900/40 dark:hover:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300 text-xs font-medium"
                                >
                                  + Task
                                </button>
                              </div>
                              {expandedStore === alertItem.site_code && <AlertBreakdown alert={alertItem} />}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function CRMSubtab() {
  const [view, setView] = useState<'scores' | 'alerts'>('alerts');
  const [month, setMonth] = useState(CURRENT_MONTH);
  const [scores, setScores] = useState<StoreScore[]>([]);
  const [alerts, setAlerts] = useState<StoreAlert[]>([]);
  const [loading, setLoading] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [showInfo, setShowInfo] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      if (view === 'scores') setScores(await fetchScores(month));
      else setAlerts(await fetchAlerts(month));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [view, month]);

  const handleRecalculate = async () => {
    setRecalculating(true);
    try {
      const result = await recalculateScores(month);
      await load();
      window.alert(`Recalculat ${result.recalculated} magazine pentru ${month}`);
    } finally {
      setRecalculating(false);
    }
  };

  const handleCreateTaskFromAlert = async (alertItem: StoreAlert) => {
    try {
      await createTask({
        title: `${alertItem.locatie || alertItem.site_code}: ${alertItem.reasons[0] ?? 'Scor scăzut'}`,
        site_code: alertItem.site_code,
        source: 'crm_alert',
        source_meta: { score: alertItem.score, reasons: alertItem.reasons, month },
      });
      window.alert(`Task creat pentru ${alertItem.locatie || alertItem.site_code}.`);
    } catch (err) {
      console.error('Failed to create task from alert', err);
    }
  };

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex gap-1">
          <button
            onClick={() => setView('alerts')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors ${
              view === 'alerts'
                ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
            }`}
          >
            <AlertTriangle size={12} /> Alerte
          </button>
          <button
            onClick={() => setView('scores')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors ${
              view === 'scores'
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
            }`}
          >
            <BarChart2 size={12} /> Scoruri
          </button>
          <button
            onClick={() => setShowInfo((v) => !v)}
            title="Cum se calculează scorul"
            className={`flex items-center justify-center w-7 h-7 rounded-xl text-xs transition-colors ${
              showInfo
                ? 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-400'
                : 'bg-slate-100 text-slate-400 hover:text-slate-600 dark:bg-slate-800 dark:hover:text-slate-300'
            }`}
          >
            <Info size={13} />
          </button>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="month"
            className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
          <button
            onClick={handleRecalculate}
            disabled={recalculating}
            className="px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-400 text-xs font-medium disabled:opacity-50"
          >
            {recalculating ? 'Se calculează...' : 'Recalculează'}
          </button>
          <button onClick={load} className="p-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-500">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {showInfo && <ScoringInfo onClose={() => setShowInfo(false)} />}

      {view === 'alerts' && (
        <AlertsTree alerts={alerts} onCreateTask={handleCreateTaskFromAlert} />
      )}
      {view === 'scores' && (
        <ScoresTree scores={scores} />
      )}
    </div>
  );
}
