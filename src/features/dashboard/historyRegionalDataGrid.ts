import type { RegionalStat } from '../../api/generated/runtime-types';
import type { DataGridColumn } from '../../components/common/DataGrid';
import type { ExportColumn } from '../../lib/tableExport';
import type { BreakdownColumn } from './BreakdownTable';

const CURRENCY_KEYS = new Set([
  'target',
  'total_vanzari',
  'medie_zilnica',
  'medie_produs',
]);
const PERCENT_KEYS = new Set([
  'proc_realizare_target',
  'forecast_target_pct',
  'proc_bon2acc',
  'prc_focus_acc_qty',
]);
const EXPORT_HEADERS: Record<string, string> = {
  regional: 'Regional',
  target: 'Target',
  total_vanzari: 'Vanzari',
  proc_realizare_target: 'Procent',
  qty_total: 'Cantitate',
  nr_bonuri: 'Nr bonuri',
  proc_bon2acc: 'ProcBon2Acc',
  prc_focus_acc_qty: 'Focus%',
};

function exportFormat(key: string): ExportColumn<RegionalStat>['format'] {
  if (CURRENCY_KEYS.has(key)) return 'currency';
  if (PERCENT_KEYS.has(key)) return 'percentPoints';
  return key === 'regional' ? undefined : 'integer';
}

export function historyRegionalDataGridColumns<Key extends string>(
  columns: readonly BreakdownColumn<RegionalStat, Key>[],
): DataGridColumn<RegionalStat, Key>[] {
  return columns.map((column) => ({
    ...column,
    value: (row) => row[column.key as keyof RegionalStat],
    filter: column.key === 'regional'
      ? { kind: 'text' as const, placeholder: 'Regional' }
      : { kind: 'number' as const },
    defaultDirection: column.key === 'regional' ? 'asc' as const : 'desc' as const,
    hideable: column.key !== 'regional',
    exportHeader: EXPORT_HEADERS[column.key] ?? column.label,
    exportValue: (row) => {
      const value = row[column.key as keyof RegionalStat];
      return typeof value === 'string' || typeof value === 'number' || value == null
        ? value
        : String(value);
    },
    exportFormat: exportFormat(column.key),
  }));
}
