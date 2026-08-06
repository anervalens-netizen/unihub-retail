import { getApiErrorMessage } from '../../api/client';

export function formatReconciliationValue(value: number | null, unit: string): string {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  const number = Number(value);
  return unit === 'RON' ? `${number.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} RON` : `${number.toLocaleString('ro-RO', { maximumFractionDigits: 2 })} ${unit}`;
}
export function formatReconciliationDate(value: string): string { const [year, month, day] = value.split('-'); return year && month && day ? `${day}.${month}.${year}` : value; }
export function formatReconciliationNumber(value: number | null): string { return value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('ro-RO', { maximumFractionDigits: 2 }); }
export function formatSignedReconciliationNumber(value: number | null): string { if (value == null || !Number.isFinite(Number(value))) return '—'; const number = Number(value); const formatted = Math.abs(number).toLocaleString('ro-RO', { maximumFractionDigits: 2 }); return number > 0 ? `+${formatted}` : number < 0 ? `-${formatted}` : '0'; }
export function formatExportFilename(mode: 'table' | 'daily_comparison', dataset: string, months: string[], days: number[]): string { const sortedMonths = [...months].sort(); const suffix = sortedMonths.length <= 4 ? sortedMonths.join('_') : `${sortedMonths[0]}_${sortedMonths[sortedMonths.length - 1]}_${sortedMonths.length}luni`; const daySuffix = days.length === 31 ? '' : `_zile_${days.length <= 10 ? days.join('-') : `${days.length}selectate`}`; return mode === 'daily_comparison' ? `export_retail_evolutie_zilnica_${suffix}${daySuffix}` : `export_retail_${dataset}_${suffix}${daySuffix}`; }
export function formatExportError(error: unknown, fallback: string): string { return getApiErrorMessage(error, fallback); }
