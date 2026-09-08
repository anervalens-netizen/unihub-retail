import type { RegionalStat } from '../../api/generated/runtime-types';
import type { DataGridColumn } from '../../components/common/DataGrid';
import { formatAmount, formatInt, formatPercent } from '../../lib/formatters';
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

function regionalValue(row: RegionalStat, key: string): unknown {
  return row[key as keyof RegionalStat];
}

function regionalSearchValue(row: RegionalStat, key: string): unknown {
  const value = regionalValue(row, key);
  if (key === 'regional') return value;
  if (CURRENCY_KEYS.has(key)) return formatAmount(Number(value ?? 0));
  if (PERCENT_KEYS.has(key)) {
    return formatPercent(typeof value === 'number' ? value : null);
  }
  return formatInt(Number(value ?? 0));
}

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
    cellClassName: typeof column.cellClassName === 'string'
      ? column.cellClassName
      : undefined,
    value: (row) => regionalValue(row, column.key),
    searchValue: (row) => regionalSearchValue(row, column.key),
    filter: column.key === 'regional'
      ? { kind: 'text' as const, placeholder: 'Regional' }
      : { kind: 'number' as const },
    defaultDirection: column.key === 'regional' ? 'asc' as const : 'desc' as const,
    hideable: column.key !== 'regional',
    exportHeader: EXPORT_HEADERS[column.key] ?? column.label,
    exportValue: (row) => {
      const value = regionalValue(row, column.key);
      return typeof value === 'string' || typeof value === 'number' || value == null
        ? value
        : String(value);
    },
    exportFormat: exportFormat(column.key),
  }));
}
