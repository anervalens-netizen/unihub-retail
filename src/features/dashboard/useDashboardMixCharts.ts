import { useMemo } from 'react';
import type { BrandMixItem, CategoryMixItem, DailySalesPoint, DashboardSummary, ReceiptBucketItem } from '../../api/generated/runtime-types';

const CATEGORY_SHORT: Record<string, string> = {
  'Casti intraauriculare': 'Casti intraaur.',
  'Baterie Externa': 'Baterie Ext.',
  'Suport telescopic': 'Suport telesk.',
  'Suport auto': 'Suport auto',
};

interface UseDashboardMixChartsArgs {
  categoryMix: CategoryMixItem[];
  receiptBucketMix: ReceiptBucketItem[];
  focusSubcategoryMix: CategoryMixItem[];
  brandMix: BrandMixItem[];
  historyReceiptBucketMix: ReceiptBucketItem[];
  historyFocusSubcategoryMix: CategoryMixItem[];
  historyDailySales: DailySalesPoint[];
  historyCategoryMix: CategoryMixItem[];
  historyBrandMix: BrandMixItem[];
  historySummary: DashboardSummary | null;
  historyMonth: string;
  selectedHistoryMonths: string[];
}

/** Builds current/history distribution payloads without coupling them to the page controller. */
export function useDashboardMixCharts(args: UseDashboardMixChartsArgs) {
  const categoryMixChartData = useMemo(() => args.categoryMix.map((item) => ({
    category: item.category, sales_total: Number(item.sales_total), quantity_total: Number(item.quantity_total), share_pct: Number(item.share_pct ?? 0),
  })), [args.categoryMix]);
  const receiptBucketChartData = useMemo(() => args.receiptBucketMix.map((item) => ({
    bucket: item.bucket, receipt_count: Number(item.receipt_count), share_pct: Number(item.share_pct ?? 0),
  })), [args.receiptBucketMix]);
  const focusSubcategoryChartData = useMemo(() => args.focusSubcategoryMix.map((item) => ({
    category: CATEGORY_SHORT[item.category] ?? item.category, quantity_total: Number(item.quantity_total), share_pct: Number(item.share_pct ?? 0),
  })), [args.focusSubcategoryMix]);
  const historyReceiptBucketChartData = useMemo(() => args.historyReceiptBucketMix.map((item) => ({
    bucket: item.bucket, receipt_count: Number(item.receipt_count), share_pct: Number(item.share_pct ?? 0),
  })), [args.historyReceiptBucketMix]);
  const historyFocusSubcategoryChartData = useMemo(() => args.historyFocusSubcategoryMix.map((item) => ({
    category: CATEGORY_SHORT[item.category] ?? item.category, quantity_total: Number(item.quantity_total), share_pct: Number(item.share_pct ?? 0),
  })), [args.historyFocusSubcategoryMix]);
  const historyDailyChartData = useMemo(() => args.historyDailySales.map((item) => ({
    day: item.sale_date.slice(-2), sales: Number(item.total_sales), qty: Number(item.total_quantity), receipts: Number(item.receipt_count),
  })), [args.historyDailySales]);
  const historyCategoryMixChartData = useMemo(() => args.historyCategoryMix.map((item) => ({
    category: item.category, sales_total: Number(item.sales_total), quantity_total: Number(item.quantity_total), share_pct: Number(item.share_pct ?? 0),
  })), [args.historyCategoryMix]);
  const historyBrandMixChartData = useMemo(() => args.historyBrandMix.map((item) => ({
    brand: item.brand, sales_total: Number(item.sales_total), share_pct: Number(item.share_pct ?? 0),
  })), [args.historyBrandMix]);
  const brandMixChartData = useMemo(() => args.brandMix.map((item) => ({
    brand: item.brand, sales_total: Number(item.sales_total), share_pct: Number(item.share_pct ?? 0),
  })), [args.brandMix]);
  const historyStatusLabel = useMemo(() => {
    if (!args.historySummary) return '';
    if (args.selectedHistoryMonths.length > 1) return `${args.selectedHistoryMonths.length} luni agregate: ${args.selectedHistoryMonths.join(', ')}.`;
    return args.historySummary.is_month_final
      ? `Luna finala ${args.historyMonth}, inchisa la ${args.historySummary.last_sale_date ?? args.historyMonth}.`
      : `Luna ${args.historyMonth} este inca in actualizare pana in ziua ${args.historySummary.imported_day_of_month ?? '-'} din ${args.historySummary.days_in_month ?? '-'}.`;
  }, [args.historyMonth, args.historySummary, args.selectedHistoryMonths]);

  return {
    categoryMixChartData, receiptBucketChartData, focusSubcategoryChartData, historyReceiptBucketChartData,
    historyFocusSubcategoryChartData, historyDailyChartData, historyCategoryMixChartData, historyBrandMixChartData,
    brandMixChartData, historyStatusLabel,
  };
}
