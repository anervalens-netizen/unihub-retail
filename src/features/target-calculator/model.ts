import type { TargetRegionalSummary, TargetScenario, TargetScenarioRow } from '../../api/targetCalculator';import { formatCurrency, formatPercent } from '../../lib/formatters';import { formatMonthLabel } from '../../lib/dates';export function monthLabel(month: string): string {
  return formatMonthLabel(month);
}

export function shouldShowHistoricalTarget(period: { month: string }): boolean {
  return !period.month.startsWith('2024-');
}

export function sum(values: number[]): number {
  return Math.round(values.reduce((total, value) => total + value, 0) * 100) / 100;
}

export function percentChangeValue(newValue: number, baseValue: number): number | null {
  if (baseValue <= 0) return null;
  return Math.round(((newValue - baseValue) * 100 / baseValue) * 100) / 100;
}

export function formatOptionalCurrency(value: number | null): string {
  return value == null ? 'Necompletat' : formatCurrency(value);
}

export function formatSignedPercent(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value > 0 ? '+' : ''}${formatPercent(value)}`;
}

export function formatSignedPp(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value > 0 ? '+' : ''}${value.toFixed(1)} pp`;
}

export function formatTableNumber(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return Math.round(value).toLocaleString('ro-RO');
}

export function attainmentTone(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return 'text-slate-400';
  if (value < 90) return 'font-bold text-red-600 dark:text-red-400';
  if (value < 100) return 'font-bold text-orange-500 dark:text-orange-400';
  return 'font-bold text-emerald-600 dark:text-emerald-400';
}

export function profitabilityFlagLabel(flag: string): string {
  const labels: Record<string, string> = {
    PNL_INCOMPLETE: 'P&L incomplet',
    FORECAST_MISSING: 'forecast lipsă',
    TARGET_BELOW_BREAK_EVEN: 'target sub BE',
    FORECAST_BELOW_BREAK_EVEN: 'forecast sub BE',
    FORECAST_BELOW_TARGET: 'forecast sub target',
  };
  return labels[flag] ?? flagLabel(flag);
}

export function percentTone(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return 'text-slate-500 dark:text-slate-400';
  if (value > 0.01) return 'text-emerald-600 dark:text-emerald-400';
  if (value < -0.01) return 'text-red-600 dark:text-red-400';
  return 'text-slate-600 dark:text-slate-300';
}

export function flagLabel(flag: string): string {
  const labels: Record<string, string> = {
    NEW_STORE: 'nou',
    LOW_HISTORY: 'istoric redus',
    EXTREME_SEASONALITY: 'sez. extrema',
    FLOOR_APPLIED: 'floor',
    CAP_APPLIED: 'cap',
    SEASONALITY_CAPPED: 'sez. limitata',
    TREND_ADJUSTMENT_CAPPED: 'trend limitat',
  };
  return labels[flag] ?? flag.toLowerCase().replaceAll('_', ' ');
}

export function recalculateVisibleScenario(scenario: TargetScenario, rows: TargetScenarioRow[]): TargetScenario {
  const regional = new Map<string, TargetRegionalSummary>();
  rows.forEach((row) => {
    const item = regional.get(row.regional) ?? {
      regional: row.regional,
      store_count: 0,
      floor_total: 0,
      proposed_total: 0,
      final_total: 0,
      current_month: null,
      current_forecast_total: 0,
      proposed_growth_vs_current_pct: null,
      final_growth_vs_current_pct: null,
      last_year_base_month: null,
      last_year_target_month: null,
      last_year_base_total: 0,
      last_year_target_total: 0,
      last_year_growth_pct: null,
    };
    item.store_count += 1;
    item.floor_total += row.floor_target;
    item.proposed_total += row.proposed_target;
    item.final_total += row.final_target ?? 0;
    const currentPeriod = row.history.find((period) => period.role === 'floor_reference');
    item.current_month = row.calculation_details.current_month ?? currentPeriod?.month ?? item.current_month;
    item.current_forecast_total += Number(row.calculation_details.current_forecast ?? currentPeriod?.realized ?? 0);

    const lastYear = row.calculation_details.seasonality?.store_years?.find((period) => period.year_offset === 1);
    const basePeriod = row.history.find((period) => period.role === 'seasonality_base_y1');
    const targetPeriod = row.history.find((period) => period.role === 'seasonality_target_y1');
    item.last_year_base_month = lastYear?.base_month ?? basePeriod?.month ?? item.last_year_base_month;
    item.last_year_target_month = lastYear?.target_month ?? targetPeriod?.month ?? item.last_year_target_month;
    item.last_year_base_total += Number(lastYear?.base_value ?? basePeriod?.realized ?? 0);
    item.last_year_target_total += Number(lastYear?.target_value ?? targetPeriod?.realized ?? 0);
    regional.set(row.regional, item);
  });
  const regionalSummary = Array.from(regional.values()).map((item) => ({
    ...item,
    proposed_growth_vs_current_pct: percentChangeValue(item.proposed_total, item.current_forecast_total),
    final_growth_vs_current_pct: percentChangeValue(item.final_total, item.current_forecast_total),
    last_year_growth_pct: percentChangeValue(item.last_year_target_total, item.last_year_base_total),
  }));
  const finalTotal = sum(rows.map((row) => row.final_target ?? 0));
  return {
    ...scenario,
    rows,
    final_total: finalTotal,
    remaining_difference: Math.round((scenario.total_target - finalTotal) * 100) / 100,
    pending_final_count: rows.filter((row) => row.final_target == null).length,
    manual_adjustments_count: rows.filter((row) => row.final_target != null && Math.abs(row.final_target - row.proposed_target) > 0.01).length,
    regional_summary: regionalSummary.sort((left, right) => left.regional.localeCompare(right.regional)),
  };
}
