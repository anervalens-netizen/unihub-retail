import type { AgentStat } from '../../api/generated/runtime-types';
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
  'proc_bon2acc',
  'prc_focus_acc_qty',
]);
const ASC_KEYS = new Set(['agent', 'locatie']);

function agentValue(row: AgentStat, key: string): unknown {
  if (key === 'medie_zilnica') {
    return row.zile_lucrate > 0 ? row.total_vanzari / row.zile_lucrate : 0;
  }
  return row[key as keyof AgentStat];
}

function agentSearchValue(row: AgentStat, key: string): unknown {
  const value = agentValue(row, key);
  if (typeof value === 'string') return value;
  if (CURRENCY_KEYS.has(key)) return formatAmount(Number(value ?? 0));
  if (PERCENT_KEYS.has(key)) {
    return formatPercent(typeof value === 'number' ? value : null);
  }
  return formatInt(Number(value ?? 0));
}

function exportFormat(key: string): ExportColumn<AgentStat>['format'] {
  if (CURRENCY_KEYS.has(key)) return 'currency';
  if (PERCENT_KEYS.has(key)) return 'percentPoints';
  return ASC_KEYS.has(key) ? undefined : 'integer';
}

export function historyAgentDataGridColumns<Key extends string>(
  columns: readonly BreakdownColumn<AgentStat, Key>[],
): DataGridColumn<AgentStat, Key>[] {
  return columns.map((column) => ({
    ...column,
    cellClassName: typeof column.cellClassName === 'string'
      ? column.cellClassName
      : undefined,
    value: (row) => agentValue(row, column.key),
    searchValue: (row) => agentSearchValue(row, column.key),
    filter: ASC_KEYS.has(column.key)
      ? { kind: 'text' as const, placeholder: column.label }
      : { kind: 'number' as const },
    defaultDirection: ASC_KEYS.has(column.key) ? 'asc' as const : 'desc' as const,
    hideable: column.key !== 'agent',
    fixedLeft: column.key === 'agent',
    exportHeader: column.label,
    exportValue: (row) => {
      const value = agentValue(row, column.key);
      return typeof value === 'string' || typeof value === 'number' || value == null
        ? value
        : String(value);
    },
    exportFormat: exportFormat(column.key),
  }));
}

export function historyAgentLegacyExportColumns(): ExportColumn<AgentStat>[] {
  return [
    { header: 'Agent', value: (row) => row.agent },
    { header: 'Firma', value: (row) => row.firma },
    { header: 'Magazin', value: (row) => row.locatie },
    { header: 'Target', value: (row) => row.target, format: 'currency' },
    { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' },
    {
      header: 'Procent',
      value: (row) => row.proc_realizare_target,
      format: 'percentPoints',
    },
    {
      header: 'Cantitate',
      value: (row) => row.acc_qty_realizat,
      format: 'integer',
    },
    { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' },
    {
      header: 'Retururi',
      value: (row) => row.return_receipt_count,
      format: 'integer',
    },
    {
      header: 'Zile lucrate',
      value: (row) => row.zile_lucrate,
      format: 'integer',
    },
    {
      header: 'Medie zilnica',
      value: (row) => row.medie_zilnica,
      format: 'currency',
    },
    {
      header: 'ProcBon2Acc',
      value: (row) => row.proc_bon2acc,
      format: 'percentPoints',
    },
    {
      header: 'Focus%',
      value: (row) => row.prc_focus_acc_qty,
      format: 'percentPoints',
    },
  ];
}
