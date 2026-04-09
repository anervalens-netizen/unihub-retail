import { useEffect, useState } from 'react';
import { RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import {
  fetchAsmPerformance,
  fetchAsmHistory,
  type AsmPerformance,
  type AsmHistoryPoint,
} from '../api/hr';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const CURRENT_MONTH = new Date().toISOString().slice(0, 7);

function TargetBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-white/30 text-xs">—</span>;
  const color = pct >= 90 ? 'text-green-400' : pct >= 70 ? 'text-yellow-400' : 'text-red-400';
  return <span className={`text-sm font-bold ${color}`}>{pct}%</span>;
}

function ScoreDot({ value }: { value: number | null }) {
  if (value === null) return <span className="text-white/30 text-xs">—</span>;
  const pct = value / 100;
  const color = pct >= 0.7 ? 'bg-green-500' : pct >= 0.4 ? 'bg-yellow-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-sm text-white/80">{value}</span>
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
    <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
      <button
        onClick={handleExpand}
        className="w-full px-4 py-3 flex items-center gap-3 hover:bg-white/5 transition-colors text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-white">{row.asm}</span>
            <span className="text-xs text-white/40">{row.regional}</span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5 text-xs text-white/60">
            <span>Vânzări: <strong className="text-white">{(row.total_sales / 1000).toFixed(1)}k</strong></span>
            <span>Target: <TargetBadge pct={row.target_pct} /></span>
            <span>Magazine: <strong className="text-white">{row.active_stores}</strong></span>
            <span>Agenți: <strong className="text-white">{row.active_agents}</strong></span>
            <span>Bon2+: <strong className="text-white">{row.pct_bon2acc}%</strong></span>
            <span>Focus: <strong className="text-white">{row.pct_focus}%</strong></span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-xs text-white/60">
            <span>Vizite: <strong className="text-white">{row.total_visits}</strong></span>
            {row.avg_completion !== null && <span>Completion: <strong className="text-white">{row.avg_completion}%</strong></span>}
            {row.checklist_score !== null && <span>Checklist: <ScoreDot value={row.checklist_score} /></span>}
            {row.avg_duration !== null && <span>Durată: <strong className="text-white">{row.avg_duration}h</strong></span>}
          </div>
        </div>
        {expanded ? <ChevronUp size={16} className="text-white/40 shrink-0" /> : <ChevronDown size={16} className="text-white/40 shrink-0" />}
      </button>

      {expanded && (
        <div className="border-t border-white/10 px-4 py-3">
          {loadingHistory ? (
            <div className="text-center text-white/40 text-xs py-4">Se încarcă...</div>
          ) : history.length === 0 ? (
            <div className="text-center text-white/40 text-xs py-4">Fără date istorice</div>
          ) : (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={history} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="month" tickFormatter={formatMonth} tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }} />
                  <YAxis yAxisId="left" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: '#1e1e2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }}
                    labelFormatter={formatMonth}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }} />
                  <Bar yAxisId="left" dataKey="total_sales" name="Vânzări" fill="#6366f1" opacity={0.7} radius={[4, 4, 0, 0]} />
                  <Line yAxisId="right" type="monotone" dataKey="target_pct" name="% Target" stroke="#22d3ee" strokeWidth={2} dot={false} />
                  <Line yAxisId="right" type="monotone" dataKey="total_visits" name="Vizite" stroke="#f59e0b" strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
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
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white/80 uppercase tracking-wide">Performanță ASM</h3>
        <div className="flex items-center gap-2">
          <input
            type="month"
            className="bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
          <button onClick={load} className="p-1.5 rounded bg-white/10 hover:bg-white/20">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {data.length === 0 && !loading && (
          <div className="text-center text-white/40 py-8 text-sm">Fără date pentru {month}</div>
        )}
        {data.map((row) => (
          <ASMRow key={row.asm} row={row} />
        ))}
      </div>
    </div>
  );
}
