import { useEffect, useState } from 'react';
import { RefreshCw, AlertTriangle, BarChart2 } from 'lucide-react';
import { fetchScores, fetchAlerts, recalculateScores, type StoreScore, type StoreAlert } from '../api/crm';
import { createTask } from '../api/tasks';

const CURRENT_MONTH = new Date().toISOString().slice(0, 7);

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' :
    score >= 40 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' :
    score === -1 ? 'bg-slate-100 text-slate-400 dark:bg-slate-800' :
    'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
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

      {/* Alerte */}
      {view === 'alerts' && (
        <div className="space-y-2">
          {alerts.length === 0 && !loading && (
            <div className="text-center text-slate-400 py-8 text-sm">
              Nicio alertă pentru {month}. Apasă Recalculează dacă nu s-au calculat scorurile.
            </div>
          )}
          {alerts.map((alertItem) => (
            <div key={alertItem.site_code} className="rounded-2xl border border-red-200 bg-red-50 dark:border-red-900/40 dark:bg-red-900/10 px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{alertItem.site_code}</span>
                    <ScoreBadge score={alertItem.score} />
                  </div>
                  <ul className="mt-1 space-y-0.5">
                    {alertItem.reasons.map((r, i) => (
                      <li key={i} className="text-xs text-red-600 dark:text-red-400 flex items-center gap-1.5">
                        <span className="w-1 h-1 rounded-full bg-red-500 shrink-0" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
                <button
                  onClick={() => handleCreateTaskFromAlert(alertItem)}
                  className="shrink-0 px-3 py-1.5 rounded-xl bg-indigo-100 hover:bg-indigo-200 dark:bg-indigo-900/40 dark:hover:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300 text-xs font-medium"
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
            <div className="text-center text-slate-400 py-8 text-sm">Niciun scor calculat pentru {month}. Apasă Recalculează.</div>
          )}
          {scores.map((s) => (
            <div key={s.site_code} className="glass rounded-2xl px-4 py-2.5 flex items-center gap-3">
              <ScoreBadge score={s.score} />
              <div className="flex-1 min-w-0">
                <span className="text-sm text-slate-800 dark:text-slate-200 font-medium">{s.site_code}</span>
                {s.breakdown && (
                  <p className="text-xs text-slate-400 mt-0.5">
                    Target {s.breakdown.target_attainment}% · Zile {s.breakdown.active_days_pct.toFixed(0)}/20
                  </p>
                )}
              </div>
              <div className="w-24 bg-slate-200 dark:bg-slate-700 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full ${s.score >= 70 ? 'bg-green-500' : s.score >= 40 ? 'bg-amber-500' : 'bg-red-500'}`}
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
