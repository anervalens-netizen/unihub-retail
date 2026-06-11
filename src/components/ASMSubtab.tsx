import { useEffect, useState } from 'react';
import { RefreshCw, ChevronDown, ChevronUp, TrendingUp } from 'lucide-react';
import {
  fetchAsmPerformance,
  fetchAsmHistory,
  type AsmPerformance,
  type AsmHistoryPoint,
} from '../api/hr';
import { fetchScores, type StoreScore } from '../api/crm';
import {
  ComposedChart, Bar, Cell, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const CURRENT_MONTH = new Date().toISOString().slice(0, 7);

function formatMonth(m: string) {
  const [y, mo] = m.split('-');
  const labels = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];
  return `${labels[parseInt(mo) - 1]} ${y.slice(2)}`;
}

function pctColor(pct: number | null): string {
  if (pct === null) return 'text-slate-400';
  if (pct >= 90) return 'text-green-600 dark:text-green-400';
  if (pct >= 70) return 'text-amber-600 dark:text-amber-400';
  return 'text-red-600 dark:text-red-400';
}

function barFill(pct: number | null): string {
  if (pct === null) return 'bg-slate-300 dark:bg-slate-600';
  if (pct >= 90) return 'bg-green-500';
  if (pct >= 70) return 'bg-amber-500';
  return 'bg-red-500';
}

type KpiStatus = 'green' | 'amber' | 'red';

function kpiStatus(value: number, greenThreshold: number, amberThreshold?: number): KpiStatus {
  if (value >= greenThreshold) return 'green';
  if (amberThreshold !== undefined && value >= amberThreshold) return 'amber';
  return 'red';
}

const STATUS_DOT: Record<KpiStatus, string> = {
  green: 'bg-green-500',
  amber: 'bg-amber-400',
  red: 'bg-red-500',
};

function KPIChip({ label, value, status, unit = '%' }: {
  label: string;
  value: number;
  status?: KpiStatus;
  unit?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-xs">
      {status && <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${STATUS_DOT[status]}`} />}
      <span className="text-slate-400">{label}</span>
      <strong className="text-slate-700 dark:text-slate-200 font-semibold">{value}{unit}</strong>
    </span>
  );
}

function StoreScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' :
    score >= 40 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' :
    score === -1 ? 'bg-slate-100 text-slate-400 dark:bg-slate-800' :
    'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold tabular-nums ${color}`}>
      {score === -1 ? '-' : score}
    </span>
  );
}

function ManagerStoreCards({ stores }: { stores: StoreScore[] }) {
  if (!stores.length) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 dark:border-slate-700 px-3 py-3 text-xs text-slate-400">
        Nu există scoruri de magazin calculate pentru managerul selectat.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
      {stores.map((store) => (
        <div key={store.site_code} className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white/70 dark:bg-slate-900/40 p-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="text-xs font-semibold text-slate-800 dark:text-slate-100 truncate">{store.locatie}</div>
              <div className="text-[10px] text-slate-400">{store.site_code}</div>
            </div>
            <StoreScoreBadge score={store.score} />
          </div>
          {store.breakdown && (
            <div className="mt-2 grid grid-cols-3 gap-2 text-[10px] text-slate-500 dark:text-slate-400">
              <span>Target <strong className="text-slate-700 dark:text-slate-200">{store.breakdown.target_attainment}%</strong></span>
              <span>Bon2+ <strong className="text-slate-700 dark:text-slate-200">{store.breakdown.kpi_bon2acc}%</strong></span>
              <span>Focus <strong className="text-slate-700 dark:text-slate-200">{store.breakdown.kpi_focus}%</strong></span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ASMRow({ row, stores }: { row: AsmPerformance; stores: StoreScore[] }) {
  const [expanded, setExpanded] = useState(false);
  const [history, setHistory] = useState<AsmHistoryPoint[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const handleExpand = async () => {
    if (!expanded && history.length === 0) {
      setLoadingHistory(true);
      try {
        setHistory(await fetchAsmHistory(row.asm, 6));
      } finally {
        setLoadingHistory(false);
      }
    }
    setExpanded(!expanded);
  };

  const displayPct = row.is_forecast ? row.forecast_target_pct : row.target_pct;
  const pctLabel = row.is_forecast ? 'Previziune target' : '% Target realizat';
  const barWidth = Math.min(displayPct ?? 0, 100);

  return (
    <div className="glass rounded-2xl overflow-hidden">
      <button
        onClick={handleExpand}
        className="w-full px-4 pt-3.5 pb-3 text-left hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition-colors"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div>
            <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">{row.asm}</span>
            <span className="ml-2 text-xs text-slate-400">{row.regional}</span>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {row.is_forecast && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-indigo-100 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-300 font-medium">
                previziune
              </span>
            )}
            {expanded
              ? <ChevronUp size={15} className="text-slate-400" />
              : <ChevronDown size={15} className="text-slate-400" />}
          </div>
        </div>

        {/* Forecast / target progress bar */}
        <div className="mb-3">
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500 flex items-center gap-1">
              <TrendingUp size={11} className="opacity-60" />
              {pctLabel}
            </span>
            <span className={`text-lg font-bold tabular-nums leading-none ${pctColor(displayPct)}`}>
              {displayPct !== null ? `${displayPct}%` : '—'}
            </span>
          </div>
          <div className="h-2.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-2.5 rounded-full transition-all duration-500 ${barFill(displayPct)}`}
              style={{ width: `${barWidth}%` }}
            />
          </div>
        </div>

        {/* Stats row */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 mb-2">
          <span>
            Vânzări{' '}
            <strong className="text-slate-700 dark:text-slate-300">
              {(row.total_sales / 1000).toFixed(1)}k
            </strong>
            {row.is_forecast && (
              <span className="text-slate-400">
                {' '}→ <span className="text-indigo-500 dark:text-indigo-400">{(row.forecast_sales / 1000).toFixed(1)}k</span>
              </span>
            )}
          </span>
          <span>
            Vizite{' '}
            <strong className="text-slate-700 dark:text-slate-300">{row.total_visits}</strong>
            {row.avg_completion !== null && (
              <span className="text-slate-400"> · {row.avg_completion}%</span>
            )}
          </span>
          <span>
            Magazine <strong className="text-slate-700 dark:text-slate-300">{row.active_stores}</strong>
          </span>
          <span>
            Agenți <strong className="text-slate-700 dark:text-slate-300">{row.active_agents}</strong>
          </span>
        </div>

        {/* KPI chips */}
        <div className="flex gap-1.5 flex-wrap">
          <KPIChip
            label="Bon2+"
            value={row.pct_bon2acc}
            status={kpiStatus(row.pct_bon2acc, 30, 29)}
          />
          <KPIChip
            label="Focus"
            value={row.pct_focus}
            status={kpiStatus(row.pct_focus, 6.9, 6)}
          />
          {row.checklist_score !== null && (
            <KPIChip
              label="Checklist"
              value={row.checklist_score}
              status={kpiStatus(row.checklist_score, 95)}
            />
          )}
          {row.avg_duration !== null && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-xs">
              <span className="text-slate-400">Durată</span>
              <strong className="text-slate-700 dark:text-slate-200 font-semibold">{row.avg_duration}h</strong>
            </span>
          )}
        </div>
      </button>

      {/* Expanded history chart */}
      {expanded && (
        <div className="border-t border-slate-200 dark:border-slate-700 px-4 py-3 bg-slate-50 dark:bg-slate-800/50">
          {loadingHistory ? (
            <div className="text-center text-slate-400 text-xs py-4">Se încarcă...</div>
          ) : history.length === 0 ? (
            <div className="text-center text-slate-400 text-xs py-4">Fără date istorice</div>
          ) : (
            <>
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                <ComposedChart
                  data={history.map((p) => ({
                    ...p,
                    display_sales: p.is_forecast ? p.forecast_sales : p.total_sales,
                    display_target_pct: p.is_forecast ? p.forecast_target_pct : p.target_pct,
                  }))}
                  margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.15)" />
                  <XAxis dataKey="month" tickFormatter={formatMonth} tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <YAxis yAxisId="left" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 8, fontSize: 12 }}
                    labelFormatter={formatMonth}
                    formatter={(value: number, name: string, props: { payload?: { is_forecast?: boolean } }) => {
                      const isForecast = props.payload?.is_forecast;
                      if (name === 'Vânzări') {
                        return [`${(value / 1000).toFixed(1)}k`, isForecast ? 'Previziune vânzări' : 'Vânzări'];
                      }
                      if (name === '% Target') {
                        return [`${value}%`, isForecast ? 'Previziune % Target' : '% Target'];
                      }
                      return [value, name];
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                  <Bar yAxisId="left" dataKey="display_sales" name="Vânzări" radius={[4, 4, 0, 0]}>
                    {history.map((p) => (
                      <Cell
                        key={p.month}
                        fill="#6366f1"
                        opacity={p.is_forecast ? 0.35 : 0.7}
                        strokeDasharray={p.is_forecast ? '4 2' : undefined}
                        stroke={p.is_forecast ? '#6366f1' : 'none'}
                        strokeWidth={p.is_forecast ? 1.5 : 0}
                      />
                    ))}
                  </Bar>
                  <Line yAxisId="right" type="monotone" dataKey="display_target_pct" name="% Target" stroke="#0ea5e9" strokeWidth={2} dot={false} />
                  <Line yAxisId="right" type="monotone" dataKey="total_visits" name="Vizite" stroke="#f59e0b" strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            {history.some((p) => p.is_forecast) && (
              <p className="text-[10px] text-slate-400 text-center mt-1">
                Bara transparentă = previziune luna curentă (extrapolare la finalul lunii)
              </p>
            )}
            </>
          )}
          <div className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-700">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Magazine</h4>
              <span className="text-[10px] text-slate-400">{stores.length} magazine</span>
            </div>
            <ManagerStoreCards stores={stores} />
          </div>
        </div>
      )}
    </div>
  );
}

export function ASMSubtab() {
  const [data, setData] = useState<AsmPerformance[]>([]);
  const [storeScores, setStoreScores] = useState<StoreScore[]>([]);
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState(CURRENT_MONTH);

  const load = async () => {
    setLoading(true);
    try {
      const [performance, scores] = await Promise.all([
        fetchAsmPerformance(month),
        fetchScores(month),
      ]);
      setData(performance);
      setStoreScores(scores);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [month]);

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Manageri</h3>
        <div className="flex items-center gap-2">
          <input
            type="month"
            className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
          <button onClick={load} className="p-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-500">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {data.length === 0 && !loading && (
          <div className="text-center text-slate-400 py-8 text-sm">Fără date pentru {month}</div>
        )}
        {data.map((row) => (
          <ASMRow
            key={row.asm}
            row={row}
            stores={storeScores.filter((store) => store.asm === row.asm || store.regional === row.asm)}
          />
        ))}
      </div>
    </div>
  );
}
