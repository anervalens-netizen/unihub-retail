import type { AiForecastDailyPoint, AiForecastMetric } from '../../api/generated/runtime-types';
import { formatAmount, formatInt } from '../../lib/formatters';
import { formatIsoDateTime, isIsoWeekendDate } from '../../lib/dates';

export interface DailyCurvePoint {
  day: string;
  date: string;
  isWeekend: boolean;
  forecastDaily: number;
  actualDaily: number | null;
  cumulativeForecast: number;
  cumulativeActual: number | null;
}

export function buildDailyCurve(points: AiForecastDailyPoint[]): DailyCurvePoint[] {
  return points.map((point) => ({
    day: point.forecast_date.slice(-2),
    date: point.forecast_date,
    isWeekend: isIsoWeekendDate(point.forecast_date),
    forecastDaily: point.forecast_sales,
    actualDaily: point.has_actual ? point.actual_sales : null,
    cumulativeForecast: point.cumulative_forecast,
    cumulativeActual: point.has_actual ? point.cumulative_actual : null,
  }));
}

export function nextSortDirection(currentKey: string, nextKey: string, currentDirection: 'asc' | 'desc'): 'asc' | 'desc' {
  if (currentKey === nextKey) return currentDirection === 'asc' ? 'desc' : 'asc';
  return nextKey === 'manager' || nextKey === 'locatie' || nextKey === 'asm' || nextKey === 'forecast_month' ? 'asc' : 'desc';
}

export function deltaTone(value: number | null | undefined): string {
  const numericValue = value ?? 0;
  if (numericValue > 0) return 'text-emerald-600 dark:text-emerald-400';
  if (numericValue < 0) return 'text-rose-600 dark:text-rose-400';
  return 'text-slate-600 dark:text-slate-300';
}

export function formatMetricValue(value: number | null | undefined, metric: AiForecastMetric): string {
  if (value === null || value === undefined) return '-';
  return metric === 'units' ? formatInt(Math.round(value)) : formatAmount(value);
}

export function formatSignedAmount(value: number | null | undefined, metric: AiForecastMetric): string {
  if (value === null || value === undefined) return '-';
  return `${value > 0 ? '+' : ''}${formatMetricValue(value, metric)}`;
}

export function riskLabel(deltaPct: number | null): string {
  if (deltaPct === null) return 'Fara reper';
  if (deltaPct >= 3) return 'Peste ritm';
  if (deltaPct <= -5) return 'Risc';
  if (deltaPct < 0) return 'Sub ritm';
  return 'In ritm';
}

export function formatGeneratedAt(value: string | undefined): string {
  return formatIsoDateTime(value);
}

const NUMERIC_SORT_KEYS = new Set([
  'store_count',
  'forecast_sales',
  'expected_sales_to_date',
  'actual_sales',
  'delta_sales',
  'delta_pct',
]);

export function compareForecastValues(
  key: string,
  a: string | number | null | undefined,
  b: string | number | null | undefined,
): number {
  if (a === null || a === undefined) return b === null || b === undefined ? 0 : -1;
  if (b === null || b === undefined) return 1;
  if (NUMERIC_SORT_KEYS.has(key)) {
    const aNumber = Number(a);
    const bNumber = Number(b);
    if (Number.isNaN(aNumber)) return Number.isNaN(bNumber) ? 0 : -1;
    if (Number.isNaN(bNumber)) return 1;
    return aNumber - bNumber;
  }
  return String(a).localeCompare(String(b), 'ro-RO', { sensitivity: 'base' });
}
