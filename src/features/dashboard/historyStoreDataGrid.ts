import type { StoreStat } from '../../api/generated/runtime-types';
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
const ASC_KEYS = new Set(['locatie', 'site_code']);

function storeValue(row: StoreStat, key: string): unknown {
  if (key === 'medie_zilnica') {
    return row.zile_active > 0 ? row.total_vanzari / row.zile_active : 0;
  }
  return row[key as keyof StoreStat];
}

function storeSearchValue(row: StoreStat, key: string): unknown {
  const value = storeValue(row, key);
  if (key === 'locatie') return `${row.firma} ${row.locatie}`;
  if (key === 'site_code') return row.firma;
  if (typeof value === 'string') return value;
  if (CURRENCY_KEYS.has(key)) return formatAmount(Number(value ?? 0));
  if (PERCENT_KEYS.has(key)) {
    return formatPercent(typeof value === 'number' ? value : null);
  }
  return formatInt(Number(value ?? 0));
}

function exportFormat(key: string): ExportColumn<StoreStat>['format'] {
  if (CURRENCY_KEYS.has(key)) return 'currency';
  if (PERCENT_KEYS.has(key)) return 'percentPoints';
  return ASC_KEYS.has(key) ? undefined : 'integer';
}

export function historyStoreDataGridColumns<Key extends string>(
  columns: readonly BreakdownColumn<StoreStat, Key>[],
): DataGridColumn<StoreStat, Key>[] {
  return columns.map((column) => ({
    ...column,
    cellClassName: typeof column.cellClassName === 'string'
      ? column.cellClassName
      : undefined,
    value: (row) => storeValue(row, column.key),
    searchValue: (row) => storeSearchValue(row, column.key),
    filter: ASC_KEYS.has(column.key)
      ? { kind: 'text' as const, placeholder: column.label }
      : { kind: 'number' as const },
    defaultDirection: ASC_KEYS.has(column.key) ? 'asc' as const : 'desc' as const,
    hideable: column.key !== 'locatie',
    exportHeader: column.label,
    exportValue: (row) => {
      const value = storeValue(row, column.key);
      return typeof value === 'string' || typeof value === 'number' || value == null
        ? value
        : String(value);
    },
    exportFormat: exportFormat(column.key),
  }));
}

export function historyStoreLegacyExportColumns(): ExportColumn<StoreStat>[] {
  return [
    { header: 'Firma', value: (row) => row.firma },
    { header: 'Magazin', value: (row) => row.locatie },
    { header: 'Target', value: (row) => row.target, format: 'currency' },
    { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' },
    {
      header: 'Procent',
      value: (row) => row.proc_realizare_target,
      format: 'percentPoints',
    },
    { header: 'Cantitate', value: (row) => row.qty_total, format: 'integer' },
    { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' },
    {
      header: 'Retururi',
      value: (row) => row.return_receipt_count,
      format: 'integer',
    },
    { header: 'Agenti', value: (row) => row.nr_agenti, format: 'integer' },
    { header: 'Zile active', value: (row) => row.zile_active, format: 'integer' },
  ];
}
