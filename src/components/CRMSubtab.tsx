import { useEffect, useState } from 'react';
import { RefreshCw, AlertTriangle, BarChart2 } from 'lucide-react';
import { fetchScores, fetchAlerts, recalculateScores, type StoreScore, type StoreAlert } from '../api/crm';
import { createTask } from '../api/tasks';

const CURRENT_MONTH = new Date().toISOString().slice(0, 7);

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? 'bg-green-500/20 text-green-300' :
    score >= 40 ? 'bg-yellow-500/20 text-yellow-300' :
    score === -1 ? 'bg-white/10 text-white/40' :
    'bg-red-500/20 text-red-300';
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${color}`}>
      {score === -1 ? '—' : score}
    </span>
  );
}

export function CRMSubtab() {
  const [view, setView] = useState<'scores' | 'alerts'>('alerts');
  const [month, setMonth] = useState(CURRENT_MONTH);
  const [scores, setScores] = useState<StoreScore[]>([]);
  const [alerts, setAlerts] = useState<StoreAlert[]>([]);
  const [loading, setLoading] = useState(false);
  const [recalculating, setRecalculating] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      if (view === 'scores') {
        setScores(await fetchScores(month));
      } else {
        setAlerts(await fetchAlerts(month));
      }
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
      alert(`Recalculat ${result.recalculated} magazine pentru ${month}`);
    } finally {
      setRecalculating(false);
    }
  };

  const handleCreateTaskFromAlert = async (alertItem: StoreAlert) => {
    await createTask({
      title: `${alertItem.site_code}: ${alertItem.reasons[0]}`,
      site_code: alertItem.site_code,
      source: 'crm_alert',
      source_meta: { score: alertItem.score, reasons: alertItem.reasons, month },
    });
    window.dispatchEvent(new CustomEvent('unihub:navigate', { detail: { tab: 'management', subtab: 'tasks' } }));
  };

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex gap-1">
          <button
            onClick={() => setView('alerts')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              view === 'alerts' ? 'bg-red-500/20 text-red-300' : 'bg-white/10 text-white/50 hover:bg-white/20'
            }`}
          >
            <AlertTriangle size={12} /> Alerte
          </button>
          <button
            onClick={() => setView('scores')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              view === 'scores' ? 'bg-indigo-600 text-white' : 'bg-white/10 text-white/50 hover:bg-white/20'
            }`}
          >
            <BarChart2 size={12} /> Scoruri
          </button>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="month"
            className="bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
          <button
            onClick={handleRecalculate}
            disabled={recalculating}
            className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white/70 text-xs font-medium disabled:opacity-50"
          >
            {recalculating ? 'Se calculează...' : 'Recalculează'}
          </button>
          <button onClick={load} className="p-1.5 rounded bg-white/10 hover:bg-white/20">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Alerte */}
      {view === 'alerts' && (
        <div className="space-y-2">
          {alerts.length === 0 && !loading && (
            <div className="text-center text-white/40 py-8 text-sm">
              Nicio alertă pentru {month}. Apasă Recalculează dacă nu s-au calculat scorurile.
            </div>
          )}
          {alerts.map((alertItem) => (
            <div key={alertItem.site_code} className="bg-red-500/5 border border-red-500/20 rounded-xl px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-white">{alertItem.site_code}</span>
                    <ScoreBadge score={alertItem.score} />
                  </div>
                  <ul className="mt-1 space-y-0.5">
                    {alertItem.reasons.map((r, i) => (
                      <li key={i} className="text-xs text-red-300/80 flex items-center gap-1.5">
                        <span className="w-1 h-1 rounded-full bg-red-400 shrink-0" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
                <button
                  onClick={() => handleCreateTaskFromAlert(alertItem)}
                  className="shrink-0 px-3 py-1.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 text-xs font-medium"
                >
                  + Task
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Scoruri */}
      {view === 'scores' && (
        <div className="space-y-1.5">
          {scores.length === 0 && !loading && (
            <div className="text-center text-white/40 py-8 text-sm">
              Niciun scor calculat pentru {month}. Apasă Recalculează.
            </div>
          )}
          {scores.map((s) => (
            <div key={s.site_code} className="bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 flex items-center gap-3">
              <ScoreBadge score={s.score} />
              <div className="flex-1 min-w-0">
                <span className="text-sm text-white font-medium">{s.site_code}</span>
                {s.breakdown && (
                  <p className="text-xs text-white/40 mt-0.5">
                    Target {s.breakdown.target_attainment}% · Zile {s.breakdown.active_days_pct.toFixed(0)}/20
                  </p>
                )}
              </div>
              <div className="w-24 bg-white/10 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full ${s.score >= 70 ? 'bg-green-500' : s.score >= 40 ? 'bg-yellow-500' : 'bg-red-500'}`}
                  style={{ width: `${s.score}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
