import type { AiForecastDailyPoint } from '../../api/types';
import { isIsoWeekendDate } from '../../lib/dates';

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
  return points.map((point) => {
    const hasActual = point.actual_sales > 0 || point.cumulative_actual > 0;
    return { day: point.forecast_date.slice(-2), date: point.forecast_date, isWeekend: isIsoWeekendDate(point.forecast_date), forecastDaily: point.forecast_sales, actualDaily: hasActual ? point.actual_sales : null, cumulativeForecast: point.cumulative_forecast, cumulativeActual: hasActual ? point.cumulative_actual : null };
  });
}

export function nextSortDirection(currentKey: string, nextKey: string, currentDirection: 'asc' | 'desc'): 'asc' | 'desc' {
  if (currentKey === nextKey) return currentDirection === 'asc' ? 'desc' : 'asc';
  return nextKey === 'manager' || nextKey === 'locatie' || nextKey === 'asm' || nextKey === 'forecast_month' ? 'asc' : 'desc';
}
