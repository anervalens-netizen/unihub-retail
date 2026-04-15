import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCheck, RefreshCw, X } from 'lucide-react';
import { cn } from '../lib/utils';
import {
  getErrorLogs,
  markAllSeen,
  type ErrorLogEntry,
} from '../api/errors';
import type { AuthUser } from '../api/types';

interface Props {
  user: AuthUser | null;
  token: string | null;
  onUnseenCountChange: (count: number) => void;
}

const SOURCE_LABELS: Record<string, string> = {
  backend: 'Backend',
  frontend: 'Frontend',
};

export function ErrorLogsTab({ user: _user, token, onUnseenCountChange }: Props) {
  const [logs, setLogs] = useState<ErrorLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedLog, setSelectedLog] = useState<ErrorLogEntry | null>(null);
  const [filterSource, setFilterSource] = useState('');
  const [filterSeen, setFilterSeen] = useState<'' | 'false' | 'true'>('');

  async function load() {
    if (!token) return;
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page_size: 100 };
      if (filterSource) params.source = filterSource;
      if (filterSeen !== '') params.seen = filterSeen === 'true';
      const data = await getErrorLogs(token, params);
      setLogs(data);
      const unseen = data.filter((l) => !l.seen).length;
      onUnseenCountChange(unseen);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [filterSource, filterSeen, token]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleMarkAllSeen() {
    if (!token) return;
    await markAllSeen(token);
    await load();
  }

  const unseenCount = logs.filter((l) => !l.seen).length;

  return (
    <div className="space-y-4">
      {/* Header + actions */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <AlertTriangle size={16} className="text-red-500" />
          <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
            Erori sistem
          </span>
          {unseenCount > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">
              {unseenCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
          >
            <RefreshCw size={12} /> Reîncarcă
          </button>
          <button
            onClick={handleMarkAllSeen}
            disabled={unseenCount === 0}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-40 hover:bg-indigo-700"
          >
            <CheckCheck size={12} /> Marchează toate ca văzute
          </button>
        </div>
      </div>

      {/* Filtre */}
      <div className="flex gap-3 flex-wrap">
        <select
          value={filterSource}
          onChange={(e) => setFilterSource(e.target.value)}
          className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300"
        >
          <option value="">Toate sursele</option>
          <option value="backend">Backend</option>
          <option value="frontend">Frontend</option>
        </select>
        <select
          value={filterSeen}
          onChange={(e) => setFilterSeen(e.target.value as '' | 'false' | 'true')}
          className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300"
        >
          <option value="">Toate</option>
          <option value="false">Nevăzute</option>
          <option value="true">Văzute</option>
        </select>
      </div>

      {/* Tabel */}
      {loading ? (
        <div className="text-xs text-slate-400 py-4 text-center">Se încarcă...</div>
      ) : logs.length === 0 ? (
        <div className="text-xs text-slate-400 py-8 text-center">Nicio eroare înregistrată.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">Timestamp</th>
                <th className="px-3 py-2 text-left font-semibold">Sursă</th>
                <th className="px-3 py-2 text-left font-semibold">Mesaj</th>
                <th className="px-3 py-2 text-left font-semibold">Path</th>
                <th className="px-3 py-2 text-left font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {logs.map((log) => (
                <tr
                  key={log.id}
                  onClick={() => setSelectedLog(log)}
                  className={cn(
                    'cursor-pointer hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors',
                    !log.seen && 'bg-red-50/40 dark:bg-red-900/10'
                  )}
                >
                  <td className="px-3 py-2 whitespace-nowrap font-mono text-[10px] text-slate-500">
                    {new Date(log.ts).toLocaleString('ro-RO')}
                  </td>
                  <td className="px-3 py-2">
                    <span className={cn(
                      'rounded px-1.5 py-0.5 text-[10px] font-bold',
                      log.source === 'backend'
                        ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                        : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                    )}>
                      {SOURCE_LABELS[log.source] ?? log.source}
                    </span>
                  </td>
                  <td className="px-3 py-2 max-w-[300px] truncate text-slate-700 dark:text-slate-300">
                    {log.message}
                  </td>
                  <td className="px-3 py-2 max-w-[150px] truncate text-slate-500 font-mono text-[10px]">
                    {log.path ?? '—'}
                  </td>
                  <td className="px-3 py-2">
                    {log.seen ? (
                      <span className="text-slate-400 text-[10px]">văzut</span>
                    ) : (
                      <span className="h-2 w-2 rounded-full bg-red-500 inline-block" />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal detalii */}
      {selectedLog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={() => setSelectedLog(null)}
        >
          <div
            className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto p-6 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className={cn(
                    'rounded px-1.5 py-0.5 text-[10px] font-bold',
                    selectedLog.source === 'backend'
                      ? 'bg-orange-100 text-orange-700'
                      : 'bg-blue-100 text-blue-700'
                  )}>
                    {SOURCE_LABELS[selectedLog.source]}
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    {new Date(selectedLog.ts).toLocaleString('ro-RO')}
                  </span>
                </div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                  {selectedLog.message}
                </p>
              </div>
              <button
                onClick={() => setSelectedLog(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 shrink-0"
              >
                <X size={16} />
              </button>
            </div>
            {selectedLog.path && (
              <div>
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Path</span>
                <p className="font-mono text-xs text-slate-700 dark:text-slate-300 mt-0.5">{selectedLog.path}</p>
              </div>
            )}
            {selectedLog.traceback && (
              <div>
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Stack Trace</span>
                <pre className="mt-1 p-3 rounded-lg bg-slate-950 text-green-400 text-[10px] overflow-x-auto whitespace-pre-wrap font-mono">
                  {selectedLog.traceback}
                </pre>
              </div>
            )}
            {selectedLog.extra && (
              <div>
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Extra</span>
                <pre className="mt-1 p-3 rounded-lg bg-slate-100 dark:bg-slate-800 text-[10px] overflow-x-auto font-mono">
                  {(() => { try { return JSON.stringify(JSON.parse(selectedLog.extra!), null, 2); } catch { return selectedLog.extra; } })()}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
