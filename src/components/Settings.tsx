import { useEffect, useState } from 'react';

import { ThemeSwitcher } from './ThemeSwitcher';
import { FileSpreadsheet, Upload } from 'lucide-react';
import { getImportHistory, uploadSalesFile } from '../api/imports';
import type { ImportHistoryEntry } from '../api/types';
import { cn } from '../lib/utils';
import { getCachedView, setCachedView } from '../lib/viewCache';

interface SettingsProps {
  theme: string;
  setTheme: (theme: string) => void;
  onImportCompleted: (month: string) => void;
}

const SETTINGS_CACHE_TTL_MS = 5 * 60 * 1000;
const CACHE_KEY = 'settings:imports';

export function Settings({
  theme,
  setTheme,
  onImportCompleted,
}: SettingsProps) {
  const [history, setHistory] = useState<ImportHistoryEntry[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error'>('success');

  useEffect(() => {
    const cached = getCachedView<{ history: ImportHistoryEntry[] }>(CACHE_KEY, SETTINGS_CACHE_TTL_MS);
    if (cached.value) {
      setHistory(cached.value.history);
      if (cached.isFresh) {
        return;
      }
    }

    getImportHistory()
      .then((historyData) => {
        setHistory(historyData);
        setCachedView(CACHE_KEY, { history: historyData });
      })
      .catch(() => {
        setHistory([]);
        setMessage('Nu am putut încărca istoricul importurilor.');
        setMessageType('error');
      });
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    try {
      setUploading(true);
      setMessage('');
      setMessageType('success');
      const response = await uploadSalesFile(file);
      setHistory((previous) => [
        {
          id: response.snapshot_id,
          import_month: response.import_month,
          filename: response.filename,
          upload_date: new Date().toISOString().slice(0, 10),
          is_month_final: response.is_month_final,
          rows_in_file: response.rows_in_file,
          rows_imported: response.rows_imported,
          status: 'completed',
          error_message: null,
          created_at: new Date().toISOString(),
        },
        ...previous,
      ]);
      onImportCompleted(response.import_month);
      const parts = [
        `Import ${response.import_month}: ${response.rows_imported} rânduri importate`,
      ];
      if (response.rows_filtered > 0) {
        parts.push(`${response.rows_filtered} rânduri non-ASM filtrate`);
      }
      if (response.is_month_final) {
        parts.push('Luna a fost marcată ca FINALĂ');
      } else {
        parts.push('Import intermediar (lună în curs)');
      }
      setMessage(parts.join(' · '));
      setFile(null);
    } catch {
      setMessage('Importul a eșuat. Verifică fișierul și încearcă din nou.');
      setMessageType('error');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-3 p-3 pb-24 pt-2">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Setări</h1>
        <p className="text-xs text-slate-500 dark:text-slate-400">Administrare aplicație</p>
      </div>


        <>
          <div className="glass rounded-3xl p-4 lg:hidden">
            <h3 className="mb-3 text-sm font-bold">Temă</h3>
            <ThemeSwitcher theme={theme} setTheme={setTheme} />
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center gap-2">
              <Upload size={16} className="text-indigo-500" />
              <h3 className="text-sm font-bold">Import fișier vânzări</h3>
            </div>
            <label
              htmlFor="upload-sales-file"
              className={cn(
                'mb-3 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-4 py-6 text-center transition-all',
                file
                  ? 'border-emerald-400 bg-emerald-50 dark:border-emerald-600 dark:bg-emerald-950/20'
                  : 'border-slate-300 bg-slate-50 hover:border-indigo-400 hover:bg-indigo-50/50 dark:border-slate-600 dark:bg-slate-800/60 dark:hover:border-indigo-500'
              )}
            >
              {file ? (
                <>
                  <FileSpreadsheet size={20} className="mb-1 text-emerald-500" />
                  <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                    {file.name}
                  </span>
                  <span className="mt-0.5 text-[11px] text-slate-400">
                    {(file.size / 1024).toFixed(1)} KB · Click pentru a schimba
                  </span>
                </>
              ) : (
                <>
                  <Upload size={20} className="mb-1 text-slate-400" />
                  <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                    Click sau drag & drop pentru a încărca
                  </span>
                  <span className="mt-0.5 text-[11px] text-slate-400">.xlsx, .xls</span>
                </>
              )}
              <input
                id="upload-sales-file"
                type="file"
                accept=".xlsx,.xls"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="hidden"
              />
            </label>
            <button
              onClick={() => void handleUpload()}
              disabled={!file || uploading}
              className="w-full rounded-2xl bg-indigo-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-indigo-500/30 disabled:opacity-60"
            >
              {uploading ? 'Se încarcă...' : 'Importă fișier'}
            </button>
            {message && (
              <div className={`mt-3 rounded-2xl px-3 py-2 text-xs font-semibold ${
                messageType === 'error'
                  ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/30 dark:text-rose-300'
                  : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
              }`}>
                {message}
              </div>
            )}
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-bold">Istoric importuri</h3>
              <span className="text-[11px] text-slate-500">{history.length} snapshot-uri</span>
            </div>
            <div className="max-h-40 space-y-2 overflow-y-auto">
              {history.slice(0, 8).map((entry) => (
                <div key={entry.id} className="rounded-2xl bg-slate-50 p-3 text-xs dark:bg-slate-800/60">
                  <div className="font-semibold">
                    {entry.import_month} · {entry.filename}
                  </div>
                  <div className="mt-1 text-slate-500">
                    {entry.rows_imported ?? 0} rânduri · {entry.status} ·{' '}
                    {entry.is_month_final ? '✓ Final' : 'Intermediar'} ·{' '}
                    {entry.created_at.slice(0, 16).replace('T', ' ')}
                  </div>
                </div>
              ))}
              {history.length === 0 && (
                <div className="text-sm font-semibold text-slate-500">Nu există istoric încă.</div>
              )}
            </div>
          </div>
        </>

    </div>
  );
}
