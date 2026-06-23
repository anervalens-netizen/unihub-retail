import { Download } from 'lucide-react';
import { useState } from 'react';
import { downloadExcelTable, type ExportColumn } from '../lib/tableExport';

export function ExportTableButton<T>({
  filename,
  sheetName,
  columns,
  rows,
  label = 'Excel',
  beforeExport,
}: {
  filename: string;
  sheetName: string;
  columns: ExportColumn<T>[];
  rows: T[];
  label?: string;
  beforeExport?: () => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);

  const handleExport = async () => {
    setBusy(true);
    try {
      await beforeExport?.();
      downloadExcelTable({ filename, sheetName, columns, rows });
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleExport()}
      disabled={rows.length === 0 || busy}
      className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-bold text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-indigo-800 dark:hover:text-indigo-300"
      title="Export Excel"
    >
      <Download size={12} />
      {busy ? 'Pregatire...' : label}
    </button>
  );
}
