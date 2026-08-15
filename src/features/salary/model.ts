import type { CSSProperties } from 'react';
import type { SalaryComparisonPoint, SalaryTrendMonth } from '../../api/salarii';
import { formatMonthSpanLabel } from '../../lib/dates';

export type SortDir = 'asc' | 'desc';
export interface SortState<K extends string> { key: K; dir: SortDir }
export type SummarySort = 'locatie' | 'company_name' | 'agent_count' | 'total_salary' | 'avg_salary' | 'total_sales' | 'ratio';
export type TrendSort = 'month' | 'total_salary' | 'total_sales' | 'avg_salary' | 'ratio';

export const COMPANY_COLORS: Record<string, string> = { Mobicell: 'text-indigo-500', Mobiup: 'text-emerald-500' };
export const RATIO_HELP_TEXT = '% = Salarii / Vanzari. Culoarea compara procentul cu media ponderata a randurilor afisate.';
export const PAGE_SIZE = 50;

export function toggleSort<K extends string>(previous: SortState<K>, key: K): SortState<K> { return previous.key === key ? { key, dir: previous.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }; }
export function formatMonthSpan(span?: [number, number, number, number] | null): string { return formatMonthSpanLabel(span); }
export function formatCurrency(value: unknown): string { const number = typeof value === 'string' ? parseFloat(value) : value; return typeof number === 'number' && !Number.isNaN(number) ? number.toLocaleString('ro-RO', { maximumFractionDigits: 0 }) : '0'; }
export function formatCompactCurrency(value: unknown): string { const number = typeof value === 'string' ? parseFloat(value) : value; return typeof number === 'number' && !Number.isNaN(number) ? number.toLocaleString('ro-RO', { notation: 'compact', maximumFractionDigits: 1 }) : '0'; }
export function salarySalesRatio(totalSalary: number, totalSales: number): number { return totalSales > 0 ? (totalSalary / totalSales) * 100 : 0; }
export function weightedRatioAverage(rows: Array<{ total_salary: number; total_sales: number }>): number { const totals = rows.reduce((result, row) => ({ salary: result.salary + (row.total_salary || 0), sales: result.sales + (row.total_sales || 0) }), { salary: 0, sales: 0 }); return salarySalesRatio(totals.salary, totals.sales); }
export function ratioToneStyle(ratio: number, average: number): CSSProperties {
  if (!Number.isFinite(ratio) || !Number.isFinite(average) || average <= 0 || Math.abs(ratio - average) <= 0.35) return { color: 'hsl(45 88% 38%)' };
  const deviation = ratio - average;
  const intensity = Math.min(Math.abs(deviation) / Math.max(average * 0.6, 8), 1);
  const hue = deviation > 0 ? 45 - 45 * intensity : 45 + 95 * intensity;
  return { color: `hsl(${hue.toFixed(0)} 78% ${(38 - 6 * intensity).toFixed(0)}%)` };
}
export function sortSummary(rows: SalaryComparisonPoint[], sort: SortState<SummarySort>) { return [...rows].sort((left, right) => { const value = sort.key === 'locatie' ? (left.locatie ?? left.site_code ?? 'UNAVAILABLE').localeCompare(right.locatie ?? right.site_code ?? 'UNAVAILABLE') : sort.key === 'company_name' ? left.company_name.localeCompare(right.company_name) : Number(left[sort.key]) - Number(right[sort.key]); return sort.dir === 'asc' ? value : -value; }); }
export function sortTrend(rows: SalaryTrendMonth[], sort: SortState<TrendSort>) { return [...rows].sort((left, right) => { const value = sort.key === 'month' ? left.month.localeCompare(right.month) : sort.key === 'ratio' ? salarySalesRatio(left.total_salary, left.total_sales) - salarySalesRatio(right.total_salary, right.total_sales) : Number(left[sort.key]) - Number(right[sort.key]); return sort.dir === 'asc' ? value : -value; }); }
export function summaryMonthOptions(span?: [number, number, number, number] | null): string[] { if (!span) return []; const [minYear, minMonth, maxYear, maxMonth] = span; const months: string[] = []; for (let year = maxYear; year >= minYear; year -= 1) for (let month = year === maxYear ? maxMonth : 12; month >= (year === minYear ? minMonth : 1); month -= 1) months.push(`${year}-${String(month).padStart(2, '0')}`); return months; }
