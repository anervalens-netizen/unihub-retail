import { useEffect, useState } from 'react';
import { RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import {
  fetchAsmPerformance,
  fetchAsmHistory,
  type AsmPerformance,
  type AsmHistoryPoint,
} from '../api/hr';
import {
  ComposedChart, Bar, Cell, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const CURRENT_MONTH = new Date().toISOString().slice(0, 7);

function TargetBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-slate-400 text-xs">—</span>;
  const color = pct >= 90 ? 'text-green-600 dark:text-green-400' : pct >= 70 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400';
  return <span className={`text-sm font-bold ${color}`}>{pct}%</span>;
}

function ScoreDot({ value }: { value: number | null }) {
  if (value === null) return <span className="text-slate-400 text-xs">—</span>;
  const pct = value / 100;
  const color = pct >= 0.7 ? 'bg-green-500' : pct >= 0.4 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-sm text-slate-700 dark:text-slate-300">{value}</span>
      <div className={`w-2 h-2 rounded-full ${color}`} />
    </div>
  );
}

function formatMonth(m: string) {
  const [y, mo] = m.split('-');
  const labels = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Noi', 'Dec'];
  return `${labels[parseInt(mo) - 1]} ${y.slice(2)}`;
}

function ASMRow({ row }: { row: AsmPerformance }) {
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

  return (
    <div className="glass rounded-2xl overflow-hidden">
      <button
        onClick={handleExpand}
        className="w-full px-4 py-3 flex items-center gap-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">{row.asm}</span>
            <span className="text-xs text-slate-400">{row.regional}</span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5 text-xs text-slate-500">
            <span>Vânzări: <strong className="text-slate-700 dark:text-slate-300">{(row.total_sales / 1000).toFixed(1)}k</strong></span>
            <span>Target: <TargetBadge pct={row.target_pct} /></span>
            <span>Magazine: <strong className="text-slate-700 dark:text-slate-300">{row.active_stores}</strong></span>
            <span>Agenți: <strong className="text-slate-700 dark:text-slate-300">{row.active_agents}</strong></span>
            <span>Bon2+: <strong className="text-slate-700 dark:text-slate-300">{row.pct_bon2acc}%</strong></span>
            <span>Focus: <strong className="text-slate-700 dark:text-slate-300">{row.pct_focus}%</strong></span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-xs text-slate-500">
            <span>Vizite: <strong className="text-slate-700 dark:text-slate-300">{row.total_visits}</strong></span>
            {row.avg_completion !== null && <span>Completion: <strong className="text-slate-700 dark:text-slate-300">{row.avg_completion}%</strong></span>}
            {row.checklist_score !== null && <span>Checklist: <ScoreDot value={row.checklist_score} /></span>}
            {row.avg_duration !== null && <span>Durată: <strong className="text-slate-700 dark:text-slate-300">{row.avg_duration}h</strong></span>}
          </div>
        </div>
        {expanded ? <ChevronUp size={16} className="text-slate-400 shrink-0" /> : <ChevronDown size={16} className="text-slate-400 shrink-0" />}
      </button>

      {expanded && (
        <div className="border-t border-slate-200 dark:border-slate-700 px-4 py-3 bg-slate-50 dark:bg-slate-800/50">
          {loadingHistory ? (
            <div className="text-center text-slate-400 text-xs py-4">Se încarcă...</div>
          ) : history.length === 0 ? (
            <div className="text-center text-slate-400 text-xs py-4">Fără date istorice</div>
          ) : (
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
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
                        const label = isForecast ? 'Previziune vânzări' : 'Vânzări';
                        return [`${(value / 1000).toFixed(1)}k`, label];
                      }
                      if (name === '% Target') {
                        const label = isForecast ? 'Previziune % Target' : '% Target';
                        return [`${value}%`, label];
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
                  <Line yAxisId="right" type="monotone" dataKey="display_target_pct" name="% Target" stroke="#0ea5e9" strokeWidth={2} dot={false} strokeDasharray="0" />
                  <Line yAxisId="right" type="monotone" dataKey="total_visits" name="Vizite" stroke="#f59e0b" strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
              {history.some((p) => p.is_forecast) && (
                <p className="text-[10px] text-slate-400 text-center mt-1">
                  Bara transparentă = previziune luna curentă (extrapolare la finalul lunii)
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ASMSubtab() {
  const [data, setData] = useState<AsmPerformance[]>([]);
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState(CURRENT_MONTH);

  const load = async () => {
    setLoading(true);
    try {
      setData(await fetchAsmPerformance(month));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [month]);

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Performanță ASM</h3>
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
          <ASMRow key={row.asm} row={row} />
        ))}
      </div>
    </div>
  );
}
