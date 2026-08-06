import type {
  AgentStat,
  AsmStat,
  BrandMixItem,
  CategoryMixItem,
  DailySalesPoint,
  DashboardAllResponse,
  DashboardSummary,
  PeriodComparisonPayload,
  PeriodComparisonPoint,
  ReceiptBucketItem,
  RegionalStat,
  StoreStat,
} from '../../api/types';
import type { AggregatedDashboardDetails } from '../../components/dashboard/useDashboardData';

const round2 = (value: number): number => Math.round(value * 100) / 100;
const n = (value: number | null | undefined): number => Number(value ?? 0);
const pct = (value: number, base: number): number | null => (base > 0 ? round2((value * 100) / base) : null);

export const sortMonthsAsc = (values: string[]): string[] => [...values].sort((a, b) => a.localeCompare(b));
export const formatMonthSelectionLabel = (values: string[]): string =>
  values.length === 1 ? (values[0] ?? '') : `${values[0] ?? ''} - ${values[values.length - 1] ?? ''} (${values.length} luni)`;

export function getDefaultHistoryMonth(currentMonth: string, months: string[]): string {
  const latestAvailableClosedMonth = months
    .filter((month) => /^\d{4}-\d{2}$/.test(month) && month < currentMonth)
    .sort((a, b) => b.localeCompare(a))[0];
  if (latestAvailableClosedMonth) return latestAvailableClosedMonth;
  const [year, month] = currentMonth.split('-').map(Number);
  if (!year || !month) return currentMonth;
  const previous = new Date(Date.UTC(year, month - 2, 1));
  return `${previous.getUTCFullYear()}-${String(previous.getUTCMonth() + 1).padStart(2, '0')}`;
}

function recalcMixShares<T extends { share_pct: number | null }>(rows: T[], total: number, getValue: (row: T) => number): T[] {
  return rows.map((row) => ({ ...row, share_pct: pct(getValue(row), total) }));
}

function aggregateCategoryMix(rows: CategoryMixItem[][]): CategoryMixItem[] {
  const map = new Map<string, CategoryMixItem>();
  for (const group of rows) for (const item of group) {
    const current = map.get(item.category) ?? { category: item.category, sales_total: 0, quantity_total: 0, share_pct: null };
    current.sales_total += n(item.sales_total);
    current.quantity_total += n(item.quantity_total);
    map.set(item.category, current);
  }
  const result = [...map.values()].sort((a, b) => n(b.sales_total) - n(a.sales_total));
  return recalcMixShares(result, result.reduce((sum, item) => sum + n(item.sales_total), 0), (item) => n(item.sales_total));
}

function aggregateFocusMix(rows: CategoryMixItem[][]): CategoryMixItem[] {
  const map = new Map<string, CategoryMixItem>();
  for (const group of rows) for (const item of group) {
    const current = map.get(item.category) ?? { category: item.category, sales_total: 0, quantity_total: 0, share_pct: null };
    current.sales_total += n(item.sales_total);
    current.quantity_total += n(item.quantity_total);
    map.set(item.category, current);
  }
  const result = [...map.values()].sort((a, b) => n(b.quantity_total) - n(a.quantity_total));
  return recalcMixShares(result, result.reduce((sum, item) => sum + n(item.quantity_total), 0), (item) => n(item.quantity_total));
}

function aggregateBrandMix(rows: BrandMixItem[][]): BrandMixItem[] {
  const map = new Map<string, BrandMixItem>();
  for (const group of rows) for (const item of group) {
    const current = map.get(item.brand) ?? { brand: item.brand, sales_total: 0, quantity_total: 0, share_pct: null };
    current.sales_total += n(item.sales_total);
    current.quantity_total += n(item.quantity_total);
    map.set(item.brand, current);
  }
  const result = [...map.values()].sort((a, b) => n(b.sales_total) - n(a.sales_total));
  return recalcMixShares(result, result.reduce((sum, item) => sum + n(item.sales_total), 0), (item) => n(item.sales_total));
}

function aggregateReceiptBuckets(rows: ReceiptBucketItem[][]): ReceiptBucketItem[] {
  const order = ['1', '2', '3', '>3'];
  const map = new Map<string, ReceiptBucketItem>();
  for (const group of rows) for (const item of group) {
    const current = map.get(item.bucket) ?? { bucket: item.bucket, receipt_count: 0, share_pct: null };
    current.receipt_count += n(item.receipt_count);
    map.set(item.bucket, current);
  }
  const result = [...map.values()].sort((a, b) => order.indexOf(a.bucket) - order.indexOf(b.bucket));
  return recalcMixShares(result, result.reduce((sum, item) => sum + n(item.receipt_count), 0), (item) => n(item.receipt_count));
}

function aggregateDailySales(rows: DailySalesPoint[][]): DailySalesPoint[] {
  const map = new Map<string, DailySalesPoint>();
  for (const group of rows) for (const item of group) {
    const day = item.sale_date.slice(-2);
    const current = map.get(day) ?? { sale_date: `zi-${day}`, total_sales: 0, total_quantity: 0, receipt_count: 0 };
    current.total_sales += n(item.total_sales);
    current.total_quantity += n(item.total_quantity);
    current.receipt_count += n(item.receipt_count);
    map.set(day, current);
  }
  return [...map.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([, item]) => item);
}

function aggregateSummary(responses: DashboardAllResponse[], label: string): DashboardSummary {
  const summaries = responses.map((response) => response.summary);
  const totalSales = summaries.reduce((sum, item) => sum + n(item.total_sales), 0);
  const totalTarget = summaries.reduce((sum, item) => sum + n(item.total_target), 0);
  const totalQuantity = summaries.reduce((sum, item) => sum + n(item.total_quantity), 0);
  const totalReceipts = summaries.reduce((sum, item) => sum + n(item.total_receipts), 0);
  const workingDays = summaries.reduce((sum, item) => sum + n(item.working_days), 0);
  const forecastSales = summaries.reduce((sum, item) => sum + n(item.forecast_sales ?? item.total_sales), 0);
  return {
    month: label, total_sales: round2(totalSales), total_target: round2(totalTarget),
    target_progress_pct: pct(totalSales, totalTarget), forecast_sales: round2(forecastSales),
    forecast_target_progress_pct: pct(forecastSales, totalTarget), total_quantity: totalQuantity,
    total_receipts: totalReceipts,
    proc_bon2acc: pct(summaries.reduce((sum, item) => sum + (n(item.proc_bon2acc) / 100) * n(item.total_receipts), 0), totalReceipts),
    prc_focus_acc_qty: pct(summaries.reduce((sum, item) => sum + (n(item.prc_focus_acc_qty) / 100) * n(item.total_quantity), 0), totalQuantity),
    total_stores: new Set(responses.flatMap((response) => response.stores.map((store) => store.site_code))).size,
    total_agents: new Set(responses.flatMap((response) => response.agents.map((agent) => `${agent.site_code}:${agent.agent}`))).size,
    working_days: workingDays, daily_average: workingDays > 0 ? round2(totalSales / workingDays) : null,
    medie_produs: totalQuantity > 0 ? round2(totalSales / totalQuantity) : null,
    is_month_final: summaries.every((item) => item.is_month_final),
    last_sale_date: (() => { const dates = summaries.map((item) => item.last_sale_date).filter(Boolean).sort(); return dates[dates.length - 1] ?? null; })(),
    imported_day_of_month: null, days_in_month: summaries.reduce((sum, item) => sum + n(item.days_in_month), 0) || null,
    cartele_qty: summaries.reduce((sum, item) => sum + n(item.cartele_qty), 0),
  };
}

function aggregateRegionals(rows: RegionalStat[][]): RegionalStat[] {
  const map = new Map<string, RegionalStat>();
  const weighted = new Map<string, { bon2: number; focus: number }>();
  for (const group of rows) for (const row of group) {
    const key = row.regional;
    const current = map.get(key) ?? { ...row, total_vanzari: 0, qty_total: 0, nr_bonuri: 0, nr_agenti: 0, zile_active: 0, target: 0, proc_realizare_target: null, forecast_target_pct: null, promo_qty: 0, promo_discount_value: 0, incentive_qty: 0, medie_zilnica: null, medie_produs: null, proc_bon2acc: null, prc_focus_acc_qty: null, return_receipt_count: 0 };
    current.total_vanzari += n(row.total_vanzari); current.qty_total += n(row.qty_total); current.nr_bonuri += n(row.nr_bonuri);
    current.nr_agenti = Math.max(n(current.nr_agenti), n(row.nr_agenti)); current.zile_active += n(row.zile_active); current.target += n(row.target);
    current.promo_qty += n(row.promo_qty); current.promo_discount_value = n(current.promo_discount_value) + n(row.promo_discount_value); current.incentive_qty += n(row.incentive_qty); current.return_receipt_count = n(current.return_receipt_count) + n(row.return_receipt_count);
    const currentWeighted = weighted.get(key) ?? { bon2: 0, focus: 0 }; currentWeighted.bon2 += (n(row.proc_bon2acc) / 100) * n(row.nr_bonuri); currentWeighted.focus += (n(row.prc_focus_acc_qty) / 100) * n(row.qty_total); weighted.set(key, currentWeighted); map.set(key, current);
  }
  return [...map.entries()].map(([key, row]) => { const currentWeighted = weighted.get(key) ?? { bon2: 0, focus: 0 }; return { ...row, total_vanzari: round2(row.total_vanzari), target: round2(row.target), proc_realizare_target: pct(row.total_vanzari, row.target), forecast_target_pct: null, medie_zilnica: row.zile_active > 0 ? round2(row.total_vanzari / row.zile_active) : null, medie_produs: row.qty_total > 0 ? round2(row.total_vanzari / row.qty_total) : null, proc_bon2acc: pct(currentWeighted.bon2, row.nr_bonuri), prc_focus_acc_qty: pct(currentWeighted.focus, row.qty_total) }; });
}

function aggregateAsms(rows: AsmStat[][]): AsmStat[] {
  const map = new Map<string, AsmStat>(); const weighted = new Map<string, { bon2: number; focus: number }>();
  for (const group of rows) for (const row of group) { const key = `${row.regional}:${row.asm}`; const current = map.get(key) ?? { ...row, total_vanzari: 0, qty_total: 0, nr_bonuri: 0, nr_agenti: 0, zile_active: 0, target: 0, proc_realizare_target: null, promo_qty: 0, promo_discount_value: 0, incentive_qty: 0, medie_zilnica: null, medie_produs: null, proc_bon2acc: null, prc_focus_acc_qty: null }; current.total_vanzari += n(row.total_vanzari); current.qty_total += n(row.qty_total); current.nr_bonuri += n(row.nr_bonuri); current.nr_agenti = Math.max(n(current.nr_agenti), n(row.nr_agenti)); current.zile_active += n(row.zile_active); current.target += n(row.target); current.promo_qty += n(row.promo_qty); current.promo_discount_value = n(current.promo_discount_value) + n(row.promo_discount_value); current.incentive_qty += n(row.incentive_qty); const currentWeighted = weighted.get(key) ?? { bon2: 0, focus: 0 }; currentWeighted.bon2 += (n(row.proc_bon2acc) / 100) * n(row.nr_bonuri); currentWeighted.focus += (n(row.prc_focus_acc_qty) / 100) * n(row.qty_total); weighted.set(key, currentWeighted); map.set(key, current); }
  return [...map.entries()].map(([key, row]) => { const currentWeighted = weighted.get(key) ?? { bon2: 0, focus: 0 }; return { ...row, total_vanzari: round2(row.total_vanzari), target: round2(row.target), proc_realizare_target: pct(row.total_vanzari, row.target), medie_zilnica: row.zile_active > 0 ? round2(row.total_vanzari / row.zile_active) : null, medie_produs: row.qty_total > 0 ? round2(row.total_vanzari / row.qty_total) : null, proc_bon2acc: pct(currentWeighted.bon2, row.nr_bonuri), prc_focus_acc_qty: pct(currentWeighted.focus, row.qty_total) }; });
}

function aggregateStores(rows: StoreStat[][]): StoreStat[] {
  const map = new Map<string, StoreStat>(); const weighted = new Map<string, { bon2: number; focus: number }>();
  for (const group of rows) for (const row of group) { const current = map.get(row.site_code) ?? { ...row, import_month: '', total_vanzari: 0, qty_total: 0, nr_bonuri: 0, nr_agenti: 0, zile_active: 0, target: 0, proc_realizare_target: null, forecast_target_pct: null, medie_produs: null, promo_qty: 0, promo_discount_value: 0, incentive_qty: 0, return_receipt_count: 0, proc_bon2acc: null, prc_focus_acc_qty: null }; current.total_vanzari += n(row.total_vanzari); current.qty_total = n(current.qty_total) + n(row.qty_total); current.nr_bonuri += n(row.nr_bonuri); current.nr_agenti = Math.max(n(current.nr_agenti), n(row.nr_agenti)); current.zile_active += n(row.zile_active); current.target += n(row.target); current.promo_qty += n(row.promo_qty); current.promo_discount_value = n(current.promo_discount_value) + n(row.promo_discount_value); current.incentive_qty += n(row.incentive_qty); current.return_receipt_count = n(current.return_receipt_count) + n(row.return_receipt_count); const currentWeighted = weighted.get(row.site_code) ?? { bon2: 0, focus: 0 }; currentWeighted.bon2 += (n(row.proc_bon2acc) / 100) * n(row.nr_bonuri); currentWeighted.focus += (n(row.prc_focus_acc_qty) / 100) * n(row.qty_total); weighted.set(row.site_code, currentWeighted); map.set(row.site_code, current); }
  return [...map.values()].map((row) => { const currentWeighted = weighted.get(row.site_code) ?? { bon2: 0, focus: 0 }; return { ...row, total_vanzari: round2(row.total_vanzari), target: round2(row.target), proc_realizare_target: pct(row.total_vanzari, row.target), forecast_target_pct: null, medie_produs: n(row.qty_total) > 0 ? round2(row.total_vanzari / n(row.qty_total)) : null, proc_bon2acc: pct(currentWeighted.bon2, row.nr_bonuri), prc_focus_acc_qty: pct(currentWeighted.focus, n(row.qty_total)) }; });
}

function aggregateAgents(rows: AgentStat[][]): AgentStat[] {
  const map = new Map<string, AgentStat>();
  for (const group of rows) for (const row of group) { const key = `${row.site_code}:${row.agent}`; const current = map.get(key) ?? { ...row, import_month: '', acc_qty_realizat: 0, nr_bonuri: 0, nr_bon2acc: 0, proc_bon2acc: null, total_vanzari: 0, zile_lucrate: 0, medie_zilnica: null, medie_produs: null, acc_focus_qty: 0, prc_focus_acc_qty: null, target: 0, proc_realizare_target: null, promo_qty: 0, promo_discount_value: 0, incentive_qty: 0, return_receipt_count: 0 }; current.acc_qty_realizat += n(row.acc_qty_realizat); current.nr_bonuri += n(row.nr_bonuri); current.nr_bon2acc += n(row.nr_bon2acc); current.total_vanzari += n(row.total_vanzari); current.zile_lucrate += n(row.zile_lucrate); current.acc_focus_qty += n(row.acc_focus_qty); current.target = n(current.target) + n(row.target); current.promo_qty += n(row.promo_qty); current.promo_discount_value = n(current.promo_discount_value) + n(row.promo_discount_value); current.incentive_qty += n(row.incentive_qty); current.return_receipt_count = n(current.return_receipt_count) + n(row.return_receipt_count); map.set(key, current); }
  return [...map.values()].map((row) => ({ ...row, total_vanzari: round2(row.total_vanzari), target: round2(n(row.target)), medie_zilnica: row.zile_lucrate > 0 ? round2(row.total_vanzari / row.zile_lucrate) : null, medie_produs: row.acc_qty_realizat > 0 ? round2(row.total_vanzari / row.acc_qty_realizat) : null, proc_bon2acc: pct(row.nr_bon2acc, row.nr_bonuri), prc_focus_acc_qty: pct(row.acc_focus_qty, row.acc_qty_realizat), proc_realizare_target: pct(row.total_vanzari, n(row.target)) }));
}

function aggregatePeriodComparisons(rows: Array<PeriodComparisonPayload | null>): PeriodComparisonPayload | null {
  const valid = rows.filter((row): row is PeriodComparisonPayload => row !== null);
  if (valid.length === 0) return null;
  const aggregatePoint = (key: keyof PeriodComparisonPayload): PeriodComparisonPoint => { const points = valid.map((row) => row[key]); const totalSales = points.reduce((sum, item) => sum + n(item.total_sales), 0); const totalQuantity = points.reduce((sum, item) => sum + n(item.total_quantity), 0); const totalReceipts = points.reduce((sum, item) => sum + n(item.total_receipts), 0); const workingDays = points.reduce((sum, item) => sum + n(item.working_days), 0); const firstPoint = points[0]; if (!firstPoint) throw new Error(`Missing period comparison point for ${key}`); return { ...firstPoint, month: valid.length > 1 ? 'agregat' : firstPoint.month, day_range: valid.length > 1 ? 'luni selectate' : firstPoint.day_range, total_sales: round2(totalSales), total_quantity: totalQuantity, total_receipts: totalReceipts, cartele_qty: points.reduce((sum, item) => sum + n(item.cartele_qty), 0), working_days: workingDays, daily_average: workingDays > 0 ? round2(totalSales / workingDays) : null, avg_receipt_value: totalReceipts > 0 ? round2(totalSales / totalReceipts) : null, medie_produs: totalQuantity > 0 ? round2(totalSales / totalQuantity) : null, proc_bon2acc: pct(points.reduce((sum, item) => sum + (n(item.proc_bon2acc) / 100) * n(item.total_receipts), 0), totalReceipts), prc_focus_acc_qty: pct(points.reduce((sum, item) => sum + (n(item.prc_focus_acc_qty) / 100) * n(item.total_quantity), 0), totalQuantity) }; };
  return { current: aggregatePoint('current'), previous: aggregatePoint('previous'), year_over_year: aggregatePoint('year_over_year') };
}

export function aggregateDashboardDetails(responses: DashboardAllResponse[], selectedMonths: string[]): AggregatedDashboardDetails {
  const label = selectedMonths.length === 1 ? (selectedMonths[0] ?? '') : `${selectedMonths[0] ?? ''} - ${selectedMonths[selectedMonths.length - 1] ?? ''}`;
  const latest = responses[responses.length - 1];
  if (!latest) throw new Error('Dashboard aggregation requires at least one response');
  return { summary: aggregateSummary(responses, label), receiptBucketMix: aggregateReceiptBuckets(responses.map((response) => response.receipt_bucket_mix)), focusSubcategoryMix: aggregateFocusMix(responses.map((response) => response.focus_subcategory_mix)), dailySales: selectedMonths.length === 1 ? latest.daily : aggregateDailySales(responses.map((response) => response.daily)), dailyLastYear: selectedMonths.length === 1 ? (latest.daily_last_year ?? []) : [], categoryMix: aggregateCategoryMix(responses.map((response) => response.category_mix)), brandMix: aggregateBrandMix(responses.map((response) => response.brand_mix)), periodComparison: aggregatePeriodComparisons(responses.map((response) => response.period_comparison)), regionals: aggregateRegionals(responses.map((response) => response.regionals ?? [])), asms: aggregateAsms(responses.map((response) => response.asms ?? [])), stores: aggregateStores(responses.map((response) => response.stores ?? [])), agents: aggregateAgents(responses.map((response) => response.agents ?? [])) };
}
