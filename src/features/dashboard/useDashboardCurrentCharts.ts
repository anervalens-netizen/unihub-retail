import { useMemo } from 'react';
import type {
  DailySalesPoint,
  DashboardSummary,
  MonthlyHistoryPoint,
  PeriodComparisonPayload,
  YearHistoryPoint,
} from '../../api/generated/runtime-types';
import type { HistoryPointView } from './HistoryDashboard';

interface UseDashboardCurrentChartsArgs {
  currentMonth: string;
  summary: DashboardSummary | null;
  dailySales: DailySalesPoint[];
  dailyLastYear: DailySalesPoint[];
  currentHistory: MonthlyHistoryPoint[];
  yearHistory: YearHistoryPoint[];
  kpiMetric: 'proc_bon2acc' | 'prc_focus_acc_qty' | 'total_receipts';
  historySummary: DashboardSummary | null;
  history: MonthlyHistoryPoint[];
  historyMonth: string;
  periodComparison: PeriodComparisonPayload | null;
}

/** Derives the current/history chart payloads independently of Dashboard UI state. */
export function useDashboardCurrentCharts({
  currentMonth,
  summary,
  dailySales,
  dailyLastYear,
  currentHistory,
  yearHistory,
  kpiMetric,
  historySummary,
  history,
  historyMonth,
  periodComparison,
}: UseDashboardCurrentChartsArgs) {
  const dailyChartData = useMemo(() => {
    const lastYearMap = new Map<string, number>();
    for (const item of dailyLastYear) lastYearMap.set(item.sale_date.slice(-2), Number(item.total_sales));
    const currentMap = new Map<string, { sales: number; qty: number; receipts: number }>();
    for (const item of dailySales) {
      currentMap.set(item.sale_date.slice(-2), {
        sales: Number(item.total_sales), qty: Number(item.total_quantity), receipts: Number(item.receipt_count),
      });
    }
    const currentDays = Array.from(currentMap.keys()).sort();
    const lastActualDay = currentDays.length > 0 ? (currentDays[currentDays.length - 1] ?? null) : null;
    const isFinal = summary?.is_month_final ?? false;
    const daysInMonth = summary?.days_in_month ?? 31;
    const allDays = new Set<string>([...currentMap.keys(), ...lastYearMap.keys()]);
    if (!isFinal) for (let d = 1; d <= daysInMonth; d += 1) allDays.add(String(d).padStart(2, '0'));
    let scalingRatio = 1;
    if (lastActualDay && lastYearMap.size > 0) {
      let currentSum = 0;
      let lastYearSum = 0;
      for (const day of currentDays) {
        currentSum += currentMap.get(day)!.sales;
        const lastYear = lastYearMap.get(day);
        if (lastYear !== undefined) lastYearSum += lastYear;
      }
      if (lastYearSum > 0) scalingRatio = currentSum / lastYearSum;
    }
    return Array.from(allDays).sort().map((day) => {
      const current = currentMap.get(day);
      const hasActual = current !== undefined;
      const isFuture = !hasActual && !isFinal && lastActualDay !== null && day > lastActualDay && lastYearMap.has(day);
      const isLastActual = day === lastActualDay && hasActual;
      return {
        day,
        sales: hasActual ? current!.sales : null,
        qty: hasActual ? current!.qty : null,
        receipts: hasActual ? current!.receipts : null,
        sales_last_year: lastYearMap.get(day) ?? null,
        sales_forecast: isFuture ? Math.round((lastYearMap.get(day) ?? 0) * scalingRatio) : isLastActual && !isFinal ? current!.sales : null,
      };
    });
  }, [dailyLastYear, dailySales, summary]);

  const currentHistoryChartData = useMemo(() => currentHistory.map((item, index) => {
    const isForecast = index === currentHistory.length - 1 && summary != null && !summary.is_month_final;
    const forecastSales = isForecast ? Number(summary!.forecast_sales ?? item.total_sales) : null;
    const target = Number(item.total_target);
    return {
      month: item.month.slice(2), sales: isForecast ? forecastSales! : Number(item.total_sales), target,
      progress: isForecast && forecastSales !== null && target > 0
        ? Math.round(forecastSales / target * 10000) / 100 : Number(item.target_progress_pct ?? 0),
      isForecast,
    };
  }), [currentHistory, summary]);
  const yearHistoryChartData = useMemo(() => yearHistory.map((point) => ({
    label: point.label, sales: Number(point.total_sales), target: Number(point.total_target),
    progress: point.total_target > 0 ? Math.round((Number(point.total_sales) / Number(point.total_target)) * 10000) / 100 : 0,
    isAggregate: point.is_aggregate,
  })), [yearHistory]);
  const kpiChartData = useMemo(() => currentHistory.map((item) => ({
    month: item.month.slice(2), value: kpiMetric === 'total_receipts' ? Number(item.total_receipts) : Number(item[kpiMetric] ?? 0),
  })), [currentHistory, kpiMetric]);
  const selectedHistoryPoint = useMemo<HistoryPointView | null>(() => {
    if (historySummary) return historySummary;
    return history.find((item) => item.month === historyMonth) ?? history[history.length - 1] ?? null;
  }, [history, historyMonth, historySummary]);
  const comparisonDeltas = useMemo(() => {
    if (!periodComparison) return null;
    const current = periodComparison.current;
    const previous = periodComparison.previous;
    const yearOverYear = periodComparison.year_over_year;
    const pct = (delta: number, base: number) => base > 0 ? Math.round(delta / base * 100) : null;
    const sales = Number(current.total_sales); const previousSales = Number(previous.total_sales); const yearSales = Number(yearOverYear.total_sales);
    const receipts = Number(current.total_receipts); const previousReceipts = Number(previous.total_receipts); const yearReceipts = Number(yearOverYear.total_receipts);
    const quantity = Number(current.total_quantity); const previousQuantity = Number(previous.total_quantity); const yearQuantity = Number(yearOverYear.total_quantity);
    return {
      previousSales: sales - previousSales, previousSalesPct: pct(sales - previousSales, previousSales),
      previousReceipts: receipts - previousReceipts, previousReceiptsPct: pct(receipts - previousReceipts, previousReceipts),
      previousQuantity: quantity - previousQuantity, previousQuantityPct: pct(quantity - previousQuantity, previousQuantity),
      yearSales: sales - yearSales, yearSalesPct: pct(sales - yearSales, yearSales),
      yearReceipts: receipts - yearReceipts, yearReceiptsPct: pct(receipts - yearReceipts, yearReceipts),
      yearQuantity: quantity - yearQuantity, yearQuantityPct: pct(quantity - yearQuantity, yearQuantity),
    };
  }, [periodComparison]);
  const currentStatusLabel = useMemo(() => {
    if (!summary) return '';
    return summary.is_month_final
      ? `Luna finala pentru ${currentMonth}, inchisa la ${summary.last_sale_date ?? currentMonth}.`
      : `Luna in curs ${currentMonth} este inca in actualizare pana in ziua ${summary.imported_day_of_month ?? '-'} din ${summary.days_in_month ?? '-'}.`;
  }, [currentMonth, summary]);

  return { dailyChartData, currentHistoryChartData, yearHistoryChartData, kpiChartData, selectedHistoryPoint, comparisonDeltas, currentStatusLabel };
}
