import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Building2,
  CalendarRange,
  ChevronDown,
  MapPin,
  PieChart as PieChartIcon,
  TrendingUp,
  Users,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getPerformanceDetail } from '../api/dashboard';
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
  PerformanceDetailResponse,
  ReceiptBucketItem,
  RegionalStat,
  StoreStat,
} from '../api/types';
import { formatAmount, formatCurrency, formatInt, formatPercent } from '../lib/formatters';
import { ExportTableButton } from './ExportTableButton';
import FirmaBadge from './FirmaBadge';
import type { AppFilters } from './MainLayout';
import { VisiteSubtab } from './VisiteSubtab';
import { AiForecastPanel } from './AiForecastPanel';
import { useSortable } from '../lib/useSortable';
import {
  CompactCurrency,
  CompactPieSection,
  DeltaCard,
  ErrorCard,
  KpiPerformanceCard,
  LoadingCard,
  Metric,
  PeriodTable,
  SortableHeader,
  describeFilterScope,
  formatCompactDonutValue,
  getAgentSortValue,
  getBon2AccTone,
  getFocusTone,
  getRegionalSortValue,
  getStoreSortValue,
  sumChartValues,
} from './dashboard/DashboardWidgets';
import { useDashboardData, type AggregatedDashboardDetails } from './dashboard/useDashboardData';
import { useAuth } from '../auth/AuthContext';
import { canAccessSalaries } from '../auth/permissions';
import {
  PerformanceDetailDrawer,
  type PerformanceSelection,
} from './dashboard/PerformanceDetailDrawer';

const HISTORY_START_YEAR = 2018;

interface DashboardProps {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
  initialSection?: DashboardSection;
  onSectionChange?: (section: DashboardSection) => void;
}

type DashboardSection = 'current' | 'history' | 'visits';
type StoreSortKey =
  | 'locatie'
  | 'site_code'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'forecast_target_pct'
  | 'incentive_qty'
  | 'qty_total'
  | 'nr_bonuri'
  | 'nr_agenti'
  | 'zile_active'
  | 'medie_zilnica'
  | 'medie_produs'
  | 'return_receipt_count';
type AgentSortKey =
  | 'locatie'
  | 'agent'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'promo_qty'
  | 'incentive_qty'
  | 'acc_qty_realizat'
  | 'nr_bonuri'
  | 'zile_lucrate'
  | 'medie_zilnica'
  | 'medie_produs'
  | 'proc_bon2acc'
  | 'prc_focus_acc_qty'
  | 'return_receipt_count';

type RegionalSortKey =
  | 'regional'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'forecast_target_pct'
  | 'promo_qty'
  | 'incentive_qty'
  | 'qty_total'
  | 'nr_bonuri'
  | 'medie_zilnica'
  | 'medie_produs'
  | 'proc_bon2acc'
  | 'prc_focus_acc_qty'
  | 'return_receipt_count';

const TABLE_MAX_HEIGHT_CLASS = 'max-h-[26rem]';
const HUB_TABLE_CLASS = 'w-max min-w-full table-auto border-collapse text-[10.5px]';
const COMPACT_TH_CLASS = 'px-1.5 py-1.5 align-bottom whitespace-normal text-[10px] leading-[1.05]';
const COMPACT_TD_CLASS = 'px-1.5 py-1 whitespace-nowrap align-middle leading-tight';
const COMPACT_NUM_TD_CLASS = `${COMPACT_TD_CLASS} text-right tabular-nums`;
const COMPACT_TEXT_TD_CLASS = `${COMPACT_TD_CLASS} text-left`;
const REGIONAL_TABLE_CLASS = HUB_TABLE_CLASS;
const STORE_TABLE_CLASS = HUB_TABLE_CLASS;
const AGENT_TABLE_CLASS = HUB_TABLE_CLASS;

const CATEGORY_SHORT: Record<string, string> = {
  'Casti intraauriculare': 'Casti intraaur.',
  'Baterie Externa': 'Baterie Ext.',
  'Suport telescopic': 'Suport telesk.',
  'Suport auto': 'Suport auto',
};

const STORE_COLUMNS: Array<{ key: StoreSortKey; label: string }> = [
  { key: 'locatie', label: 'Magazin' },
  { key: 'site_code', label: 'Firma' },
  { key: 'target', label: 'Target' },
  { key: 'total_vanzari', label: 'Vanzari' },
  { key: 'proc_realizare_target', label: 'Procent' },
  { key: 'forecast_target_pct', label: 'Forecast%' },
  { key: 'incentive_qty', label: 'Incentive' },
  { key: 'qty_total', label: 'Cantitate' },
  { key: 'medie_produs', label: 'Medie produs' },
  { key: 'nr_bonuri', label: 'Nr bonuri' },
  { key: 'return_receipt_count', label: 'Retururi' },
  { key: 'nr_agenti', label: 'Agenti' },
  { key: 'zile_active', label: 'Zile active' },
];

const AGENT_COLUMNS: Array<{ key: AgentSortKey; label: string }> = [
  { key: 'agent', label: 'Agent' },
  { key: 'locatie', label: 'Magazin' },
  { key: 'target', label: 'Target' },
  { key: 'total_vanzari', label: 'Vanzari' },
  { key: 'proc_realizare_target', label: 'Procent' },
  { key: 'promo_qty', label: 'Promo' },
  { key: 'incentive_qty', label: 'Incentive' },
  { key: 'acc_qty_realizat', label: 'Cantitate' },
  { key: 'medie_produs', label: 'Medie produs' },
  { key: 'nr_bonuri', label: 'Nr bonuri' },
  { key: 'return_receipt_count', label: 'Retururi' },
  { key: 'zile_lucrate', label: 'Zile lucrate' },
  { key: 'medie_zilnica', label: 'Medie zilnica' },
  { key: 'proc_bon2acc', label: 'ProcBon2Acc' },
  { key: 'prc_focus_acc_qty', label: 'Focus%' },
];

const REGIONAL_COLUMNS: Array<{ key: RegionalSortKey; label: string }> = [
  { key: 'regional', label: 'Regional' },
  { key: 'target', label: 'Target' },
  { key: 'total_vanzari', label: 'Vanzari' },
  { key: 'proc_realizare_target', label: 'Procent' },
  { key: 'forecast_target_pct', label: 'Forecast%' },
  { key: 'promo_qty', label: 'Promo' },
  { key: 'incentive_qty', label: 'Incentive' },
  { key: 'qty_total', label: 'Cantitate' },
  { key: 'medie_produs', label: 'Medie produs' },
  { key: 'nr_bonuri', label: 'Nr bonuri' },
  { key: 'proc_bon2acc', label: 'ProcBon2Acc' },
  { key: 'prc_focus_acc_qty', label: 'Focus%' },
];

const CURRENT_REGIONAL_COLUMNS = REGIONAL_COLUMNS.filter((c) => c.key !== 'promo_qty' && c.key !== 'incentive_qty');
const CURRENT_STORE_COLUMNS = STORE_COLUMNS.filter((c) => c.key !== 'site_code' && c.key !== 'incentive_qty');
const CURRENT_AGENT_COLUMNS = AGENT_COLUMNS.filter((c) => c.key !== 'promo_qty' && c.key !== 'incentive_qty');
const HIST_REGIONAL_COLUMNS = REGIONAL_COLUMNS.filter((c) => c.key !== 'promo_qty' && c.key !== 'incentive_qty' && c.key !== 'forecast_target_pct' && c.key !== 'medie_produs');
const HIST_STORE_COLUMNS = STORE_COLUMNS.filter((c) => c.key !== 'site_code' && c.key !== 'incentive_qty' && c.key !== 'forecast_target_pct' && c.key !== 'medie_produs');
const HIST_AGENT_COLUMNS = AGENT_COLUMNS.filter((c) => c.key !== 'promo_qty' && c.key !== 'incentive_qty' && c.key !== 'medie_produs');
const STORE_ASC_SORT_KEYS: StoreSortKey[] = ['locatie', 'site_code'];
const AGENT_ASC_SORT_KEYS: AgentSortKey[] = ['locatie', 'agent'];
const REGIONAL_ASC_SORT_KEYS: RegionalSortKey[] = ['regional'];

const round2 = (value: number): number => Math.round(value * 100) / 100;
const n = (value: number | null | undefined): number => Number(value ?? 0);
const pct = (value: number, base: number): number | null => (base > 0 ? round2((value * 100) / base) : null);
const sortMonthsAsc = (values: string[]): string[] => [...values].sort((a, b) => a.localeCompare(b));
const formatMonthSelectionLabel = (values: string[]): string =>
  values.length === 1 ? values[0] : `${values[0]} - ${values[values.length - 1]} (${values.length} luni)`;

function recalcMixShares<T extends { share_pct: number | null }>(
  rows: T[],
  total: number,
  getValue: (row: T) => number
): T[] {
  return rows.map((row) => ({ ...row, share_pct: pct(getValue(row), total) }));
}

function aggregateCategoryMix(rows: CategoryMixItem[][]): CategoryMixItem[] {
  const map = new Map<string, CategoryMixItem>();
  for (const group of rows) {
    for (const item of group) {
      const current = map.get(item.category) ?? {
        category: item.category,
        sales_total: 0,
        quantity_total: 0,
        share_pct: null,
      };
      current.sales_total += n(item.sales_total);
      current.quantity_total += n(item.quantity_total);
      map.set(item.category, current);
    }
  }
  const result = [...map.values()].sort((a, b) => n(b.sales_total) - n(a.sales_total));
  return recalcMixShares(result, result.reduce((sum, item) => sum + n(item.sales_total), 0), (item) => n(item.sales_total));
}

function aggregateFocusMix(rows: CategoryMixItem[][]): CategoryMixItem[] {
  const map = new Map<string, CategoryMixItem>();
  for (const group of rows) {
    for (const item of group) {
      const current = map.get(item.category) ?? {
        category: item.category,
        sales_total: 0,
        quantity_total: 0,
        share_pct: null,
      };
      current.sales_total += n(item.sales_total);
      current.quantity_total += n(item.quantity_total);
      map.set(item.category, current);
    }
  }
  const result = [...map.values()].sort((a, b) => n(b.quantity_total) - n(a.quantity_total));
  return recalcMixShares(result, result.reduce((sum, item) => sum + n(item.quantity_total), 0), (item) => n(item.quantity_total));
}

function aggregateBrandMix(rows: BrandMixItem[][]): BrandMixItem[] {
  const map = new Map<string, BrandMixItem>();
  for (const group of rows) {
    for (const item of group) {
      const current = map.get(item.brand) ?? {
        brand: item.brand,
        sales_total: 0,
        quantity_total: 0,
        share_pct: null,
      };
      current.sales_total += n(item.sales_total);
      current.quantity_total += n(item.quantity_total);
      map.set(item.brand, current);
    }
  }
  const result = [...map.values()].sort((a, b) => n(b.sales_total) - n(a.sales_total));
  return recalcMixShares(result, result.reduce((sum, item) => sum + n(item.sales_total), 0), (item) => n(item.sales_total));
}

function aggregateReceiptBuckets(rows: ReceiptBucketItem[][]): ReceiptBucketItem[] {
  const order = ['1', '2', '3', '>3'];
  const map = new Map<string, ReceiptBucketItem>();
  for (const group of rows) {
    for (const item of group) {
      const current = map.get(item.bucket) ?? { bucket: item.bucket, receipt_count: 0, share_pct: null };
      current.receipt_count += n(item.receipt_count);
      map.set(item.bucket, current);
    }
  }
  const result = [...map.values()].sort((a, b) => order.indexOf(a.bucket) - order.indexOf(b.bucket));
  return recalcMixShares(result, result.reduce((sum, item) => sum + n(item.receipt_count), 0), (item) => n(item.receipt_count));
}

function aggregateDailySales(rows: DailySalesPoint[][]): DailySalesPoint[] {
  const map = new Map<string, DailySalesPoint>();
  for (const group of rows) {
    for (const item of group) {
      const day = item.sale_date.slice(-2);
      const current = map.get(day) ?? { sale_date: `zi-${day}`, total_sales: 0, total_quantity: 0, receipt_count: 0 };
      current.total_sales += n(item.total_sales);
      current.total_quantity += n(item.total_quantity);
      current.receipt_count += n(item.receipt_count);
      map.set(day, current);
    }
  }
  return [...map.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([, item]) => item);
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
    month: label,
    total_sales: round2(totalSales),
    total_target: round2(totalTarget),
    target_progress_pct: pct(totalSales, totalTarget),
    forecast_sales: round2(forecastSales),
    forecast_target_progress_pct: pct(forecastSales, totalTarget),
    total_quantity: totalQuantity,
    total_receipts: totalReceipts,
    proc_bon2acc: pct(
      summaries.reduce((sum, item) => sum + (n(item.proc_bon2acc) / 100) * n(item.total_receipts), 0),
      totalReceipts
    ),
    prc_focus_acc_qty: pct(
      summaries.reduce((sum, item) => sum + (n(item.prc_focus_acc_qty) / 100) * n(item.total_quantity), 0),
      totalQuantity
    ),
    total_stores: new Set(responses.flatMap((response) => response.stores.map((store) => store.site_code))).size,
    total_agents: new Set(responses.flatMap((response) => response.agents.map((agent) => `${agent.site_code}:${agent.agent}`))).size,
    working_days: workingDays,
    daily_average: workingDays > 0 ? round2(totalSales / workingDays) : null,
    medie_produs: totalQuantity > 0 ? round2(totalSales / totalQuantity) : null,
    is_month_final: summaries.every((item) => item.is_month_final),
    last_sale_date: summaries.map((item) => item.last_sale_date).filter(Boolean).sort().at(-1) ?? null,
    imported_day_of_month: null,
    days_in_month: summaries.reduce((sum, item) => sum + n(item.days_in_month), 0) || null,
    cartele_qty: summaries.reduce((sum, item) => sum + n(item.cartele_qty), 0),
  };
}

function aggregateRegionals(rows: RegionalStat[][]): RegionalStat[] {
  const map = new Map<string, RegionalStat>();
  const weighted = new Map<string, { bon2: number; focus: number }>();
  for (const group of rows) {
    for (const row of group) {
      const key = row.regional;
      const current = map.get(key) ?? { ...row, total_vanzari: 0, qty_total: 0, nr_bonuri: 0, nr_agenti: 0, zile_active: 0, target: 0, proc_realizare_target: null, forecast_target_pct: null, promo_qty: 0, incentive_qty: 0, medie_zilnica: null, medie_produs: null, proc_bon2acc: null, prc_focus_acc_qty: null, return_receipt_count: 0 };
      current.total_vanzari += n(row.total_vanzari);
      current.qty_total += n(row.qty_total);
      current.nr_bonuri += n(row.nr_bonuri);
      current.nr_agenti = Math.max(n(current.nr_agenti), n(row.nr_agenti));
      current.zile_active += n(row.zile_active);
      current.target += n(row.target);
      current.promo_qty += n(row.promo_qty);
      current.incentive_qty += n(row.incentive_qty);
      current.return_receipt_count = n(current.return_receipt_count) + n(row.return_receipt_count);
      const currentWeighted = weighted.get(key) ?? { bon2: 0, focus: 0 };
      currentWeighted.bon2 += (n(row.proc_bon2acc) / 100) * n(row.nr_bonuri);
      currentWeighted.focus += (n(row.prc_focus_acc_qty) / 100) * n(row.qty_total);
      weighted.set(key, currentWeighted);
      map.set(key, current);
    }
  }
  return [...map.entries()].map(([key, row]) => {
    const currentWeighted = weighted.get(key) ?? { bon2: 0, focus: 0 };
    return {
      ...row,
      total_vanzari: round2(row.total_vanzari),
      target: round2(row.target),
      proc_realizare_target: pct(row.total_vanzari, row.target),
      forecast_target_pct: null,
      medie_zilnica: row.zile_active > 0 ? round2(row.total_vanzari / row.zile_active) : null,
      medie_produs: row.qty_total > 0 ? round2(row.total_vanzari / row.qty_total) : null,
      proc_bon2acc: pct(currentWeighted.bon2, row.nr_bonuri),
      prc_focus_acc_qty: pct(currentWeighted.focus, row.qty_total),
    };
  });
}

function aggregateAsms(rows: AsmStat[][]): AsmStat[] {
  const map = new Map<string, AsmStat>();
  const weighted = new Map<string, { bon2: number; focus: number }>();
  for (const group of rows) {
    for (const row of group) {
      const key = `${row.regional}:${row.asm}`;
      const current = map.get(key) ?? { ...row, total_vanzari: 0, qty_total: 0, nr_bonuri: 0, nr_agenti: 0, zile_active: 0, target: 0, proc_realizare_target: null, promo_qty: 0, incentive_qty: 0, medie_zilnica: null, medie_produs: null, proc_bon2acc: null, prc_focus_acc_qty: null };
      current.total_vanzari += n(row.total_vanzari);
      current.qty_total += n(row.qty_total);
      current.nr_bonuri += n(row.nr_bonuri);
      current.nr_agenti = Math.max(n(current.nr_agenti), n(row.nr_agenti));
      current.zile_active += n(row.zile_active);
      current.target += n(row.target);
      current.promo_qty += n(row.promo_qty);
      current.incentive_qty += n(row.incentive_qty);
      const currentWeighted = weighted.get(key) ?? { bon2: 0, focus: 0 };
      currentWeighted.bon2 += (n(row.proc_bon2acc) / 100) * n(row.nr_bonuri);
      currentWeighted.focus += (n(row.prc_focus_acc_qty) / 100) * n(row.qty_total);
      weighted.set(key, currentWeighted);
      map.set(key, current);
    }
  }
  return [...map.entries()].map(([key, row]) => {
    const currentWeighted = weighted.get(key) ?? { bon2: 0, focus: 0 };
    return {
      ...row,
      total_vanzari: round2(row.total_vanzari),
      target: round2(row.target),
      proc_realizare_target: pct(row.total_vanzari, row.target),
      medie_zilnica: row.zile_active > 0 ? round2(row.total_vanzari / row.zile_active) : null,
      medie_produs: row.qty_total > 0 ? round2(row.total_vanzari / row.qty_total) : null,
      proc_bon2acc: pct(currentWeighted.bon2, row.nr_bonuri),
      prc_focus_acc_qty: pct(currentWeighted.focus, row.qty_total),
    };
  });
}

function aggregateStores(rows: StoreStat[][]): StoreStat[] {
  const map = new Map<string, StoreStat>();
  for (const group of rows) {
    for (const row of group) {
      const current = map.get(row.site_code) ?? { ...row, import_month: '', total_vanzari: 0, qty_total: 0, nr_bonuri: 0, nr_agenti: 0, zile_active: 0, target: 0, proc_realizare_target: null, forecast_target_pct: null, medie_produs: null, promo_qty: 0, incentive_qty: 0, return_receipt_count: 0 };
      current.total_vanzari += n(row.total_vanzari);
      current.qty_total = n(current.qty_total) + n(row.qty_total);
      current.nr_bonuri += n(row.nr_bonuri);
      current.nr_agenti = Math.max(n(current.nr_agenti), n(row.nr_agenti));
      current.zile_active += n(row.zile_active);
      current.target += n(row.target);
      current.promo_qty += n(row.promo_qty);
      current.incentive_qty += n(row.incentive_qty);
      current.return_receipt_count = n(current.return_receipt_count) + n(row.return_receipt_count);
      map.set(row.site_code, current);
    }
  }
  return [...map.values()].map((row) => ({
    ...row,
    total_vanzari: round2(row.total_vanzari),
    target: round2(row.target),
    proc_realizare_target: pct(row.total_vanzari, row.target),
    forecast_target_pct: null,
    medie_produs: n(row.qty_total) > 0 ? round2(row.total_vanzari / n(row.qty_total)) : null,
  }));
}

function aggregateAgents(rows: AgentStat[][]): AgentStat[] {
  const map = new Map<string, AgentStat>();
  for (const group of rows) {
    for (const row of group) {
      const key = `${row.site_code}:${row.agent}`;
      const current = map.get(key) ?? { ...row, import_month: '', acc_qty_realizat: 0, nr_bonuri: 0, nr_bon2acc: 0, proc_bon2acc: null, total_vanzari: 0, zile_lucrate: 0, medie_zilnica: null, medie_produs: null, acc_focus_qty: 0, prc_focus_acc_qty: null, target: 0, proc_realizare_target: null, promo_qty: 0, incentive_qty: 0, return_receipt_count: 0 };
      current.acc_qty_realizat += n(row.acc_qty_realizat);
      current.nr_bonuri += n(row.nr_bonuri);
      current.nr_bon2acc += n(row.nr_bon2acc);
      current.total_vanzari += n(row.total_vanzari);
      current.zile_lucrate += n(row.zile_lucrate);
      current.acc_focus_qty += n(row.acc_focus_qty);
      current.target = n(current.target) + n(row.target);
      current.promo_qty += n(row.promo_qty);
      current.incentive_qty += n(row.incentive_qty);
      current.return_receipt_count = n(current.return_receipt_count) + n(row.return_receipt_count);
      map.set(key, current);
    }
  }
  return [...map.values()].map((row) => ({
    ...row,
    total_vanzari: round2(row.total_vanzari),
    target: round2(n(row.target)),
    medie_zilnica: row.zile_lucrate > 0 ? round2(row.total_vanzari / row.zile_lucrate) : null,
    medie_produs: row.acc_qty_realizat > 0 ? round2(row.total_vanzari / row.acc_qty_realizat) : null,
    proc_bon2acc: pct(row.nr_bon2acc, row.nr_bonuri),
    prc_focus_acc_qty: pct(row.acc_focus_qty, row.acc_qty_realizat),
    proc_realizare_target: pct(row.total_vanzari, n(row.target)),
  }));
}

function aggregatePeriodComparisons(rows: Array<PeriodComparisonPayload | null>): PeriodComparisonPayload | null {
  const valid = rows.filter((row): row is PeriodComparisonPayload => row !== null);
  if (valid.length === 0) return null;
  const aggregatePoint = (key: keyof PeriodComparisonPayload): PeriodComparisonPoint => {
    const points = valid.map((row) => row[key]);
    const totalSales = points.reduce((sum, item) => sum + n(item.total_sales), 0);
    const totalQuantity = points.reduce((sum, item) => sum + n(item.total_quantity), 0);
    const totalReceipts = points.reduce((sum, item) => sum + n(item.total_receipts), 0);
    const workingDays = points.reduce((sum, item) => sum + n(item.working_days), 0);
    return {
      ...points[0],
      label: points[0].label,
      month: valid.length > 1 ? 'agregat' : points[0].month,
      day_range: valid.length > 1 ? 'luni selectate' : points[0].day_range,
      total_sales: round2(totalSales),
      total_quantity: totalQuantity,
      total_receipts: totalReceipts,
      cartele_qty: points.reduce((sum, item) => sum + n(item.cartele_qty), 0),
      working_days: workingDays,
      daily_average: workingDays > 0 ? round2(totalSales / workingDays) : null,
      avg_receipt_value: totalReceipts > 0 ? round2(totalSales / totalReceipts) : null,
      medie_produs: totalQuantity > 0 ? round2(totalSales / totalQuantity) : null,
      proc_bon2acc: pct(points.reduce((sum, item) => sum + (n(item.proc_bon2acc) / 100) * n(item.total_receipts), 0), totalReceipts),
      prc_focus_acc_qty: pct(points.reduce((sum, item) => sum + (n(item.prc_focus_acc_qty) / 100) * n(item.total_quantity), 0), totalQuantity),
    };
  };
  return {
    current: aggregatePoint('current'),
    previous: aggregatePoint('previous'),
    year_over_year: aggregatePoint('year_over_year'),
  };
}

export function aggregateDashboardDetails(
  responses: DashboardAllResponse[],
  selectedMonths: string[]
): AggregatedDashboardDetails {
  const label = selectedMonths.length === 1 ? selectedMonths[0] : `${selectedMonths[0]} - ${selectedMonths[selectedMonths.length - 1]}`;
  const latest = responses[responses.length - 1];
  return {
    summary: aggregateSummary(responses, label),
    receiptBucketMix: aggregateReceiptBuckets(responses.map((response) => response.receipt_bucket_mix)),
    focusSubcategoryMix: aggregateFocusMix(responses.map((response) => response.focus_subcategory_mix)),
    dailySales: selectedMonths.length === 1 ? latest.daily : aggregateDailySales(responses.map((response) => response.daily)),
    dailyLastYear: selectedMonths.length === 1 ? (latest.daily_last_year ?? []) : [],
    categoryMix: aggregateCategoryMix(responses.map((response) => response.category_mix)),
    brandMix: aggregateBrandMix(responses.map((response) => response.brand_mix)),
    periodComparison: aggregatePeriodComparisons(responses.map((response) => response.period_comparison)),
    regionals: aggregateRegionals(responses.map((response) => response.regionals ?? [])),
    asms: aggregateAsms(responses.map((response) => response.asms ?? [])),
    stores: aggregateStores(responses.map((response) => response.stores ?? [])),
    agents: aggregateAgents(responses.map((response) => response.agents ?? [])),
  };
}

export function Dashboard({ currentMonth, months, filters, initialSection = 'current', onSectionChange }: DashboardProps) {
  const { user } = useAuth();
  const canViewSalaries = canAccessSalaries(user?.profile);
  const [activeSection, setActiveSection] = useState<DashboardSection>(initialSection);
  const [currentMode, setCurrentMode] = useState<'overview' | 'forecast'>('overview');
  const [historyMonth, setHistoryMonth] = useState(currentMonth);
  const [historyMonths, setHistoryMonths] = useState<string[]>([currentMonth]);
  const [draftHistoryMonths, setDraftHistoryMonths] = useState<string[]>([currentMonth]);
  const [historyMonthDropdownOpen, setHistoryMonthDropdownOpen] = useState(false);
  const [historyYearFilter, setHistoryYearFilter] = useState<number | null>(null);
  const [kpiMetric, setKpiMetric] = useState<'proc_bon2acc' | 'prc_focus_acc_qty' | 'total_receipts'>('proc_bon2acc');
  const [includeClosedStores, setIncludeClosedStores] = useState(false);
  const [performanceSelection, setPerformanceSelection] = useState<PerformanceSelection | null>(null);
  const [performanceDetail, setPerformanceDetail] = useState<PerformanceDetailResponse | null>(null);
  const [performanceLoading, setPerformanceLoading] = useState(false);
  const [performanceError, setPerformanceError] = useState('');
  const historyMonthDropdownRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    setHistoryMonth((previous) => (months.includes(previous) ? previous : currentMonth));
    setHistoryMonths((previous) => {
      const valid = previous.filter((month) => months.includes(month));
      return valid.length > 0 ? valid : [currentMonth];
    });
    setDraftHistoryMonths((previous) => {
      const valid = previous.filter((month) => months.includes(month));
      return valid.length > 0 ? valid : [currentMonth];
    });
  }, [months, currentMonth]);

  useEffect(() => {
    setActiveSection(initialSection);
  }, [initialSection]);

  const selectedHistoryMonths = useMemo(() => {
    const valid = historyMonths.filter((month) => months.includes(month));
    return sortMonthsAsc(valid.length > 0 ? valid : [historyMonth]);
  }, [historyMonth, historyMonths, months]);
  const historySelectionLabel = useMemo(
    () => formatMonthSelectionLabel(selectedHistoryMonths),
    [selectedHistoryMonths]
  );
  const historySelectionSlug = useMemo(
    () => selectedHistoryMonths.join('_'),
    [selectedHistoryMonths]
  );
  const draftSelectedHistoryMonths = useMemo(() => {
    const valid = draftHistoryMonths.filter((month) => months.includes(month));
    return sortMonthsAsc(valid.length > 0 ? valid : selectedHistoryMonths);
  }, [draftHistoryMonths, months, selectedHistoryMonths]);
  const draftHistorySelectionLabel = useMemo(
    () => formatMonthSelectionLabel(draftSelectedHistoryMonths),
    [draftSelectedHistoryMonths]
  );
  const {
    summary,
    agents,
    stores,
    dailySales,
    dailyLastYear,
    periodComparison,
    categoryMix,
    receiptBucketMix,
    focusSubcategoryMix,
    brandMix,
    regionals,
    currentHistory,
    currentHistoryLoading,
    yearHistory,
    yearHistoryLoading,
    history,
    historySummary,
    historyReceiptBucketMix,
    historyFocusSubcategoryMix,
    historyDailySales,
    historyCategoryMix,
    historyBrandMix,
    historyRegionals,
    historyStores,
    historyAgents,
    loading,
    error,
    historyLoading,
    historyError,
    refetchCurrentData,
    refetchHistoryData,
  } = useDashboardData({
    currentMonth,
    filters,
    historyMonth,
    selectedHistoryMonths,
    includeClosedStores,
    activeSection,
    historyYearFilter,
    aggregateDetails: aggregateDashboardDetails,
  });

  useEffect(() => {
    onSectionChange?.(activeSection);
  }, [activeSection, onSectionChange]);

  useEffect(() => {
    if (!performanceSelection) {
      setPerformanceDetail(null);
      setPerformanceError('');
      setPerformanceLoading(false);
      return undefined;
    }
    let cancelled = false;
    setPerformanceLoading(true);
    setPerformanceError('');
    getPerformanceDetail({
      month: currentMonth,
      level: performanceSelection.level,
      key: performanceSelection.key,
      firma: filters.firma,
      site_code: performanceSelection.site_code,
      current_scope: true,
      include_closed_stores: false,
    })
      .then((data) => {
        if (cancelled) return;
        setPerformanceDetail(data);
      })
      .catch((errorValue: unknown) => {
        if (cancelled) return;
        const message = errorValue instanceof Error ? errorValue.message.replace(/^API error: \d+\s*-?\s*/i, '') : '';
        setPerformanceError(message || 'Detaliul nu a putut fi incarcat.');
        setPerformanceDetail(null);
      })
      .finally(() => {
        if (!cancelled) setPerformanceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [currentMonth, filters.firma, performanceSelection]);

  const availableYears = useMemo(() => {
    const cy = parseInt(currentMonth.slice(0, 4));
    return Array.from({ length: cy - HISTORY_START_YEAR + 1 }, (_, i) => HISTORY_START_YEAR + i);
  }, [currentMonth]);

  const dailyChartData = useMemo(() => {
    const lastYearMap = new Map<string, number>();
    for (const item of dailyLastYear) {
      lastYearMap.set(item.sale_date.slice(-2), Number(item.total_sales));
    }
    const currentMap = new Map<string, { sales: number; qty: number; receipts: number }>();
    for (const item of dailySales) {
      currentMap.set(item.sale_date.slice(-2), {
        sales: Number(item.total_sales),
        qty: Number(item.total_quantity),
        receipts: Number(item.receipt_count),
      });
    }

    const currentDays = Array.from(currentMap.keys()).sort();
    const lastActualDay = currentDays.length > 0 ? currentDays[currentDays.length - 1] : null;

    const isFinal = summary?.is_month_final ?? false;
    const daysInMonth = summary?.days_in_month ?? 31;

    const allDays = new Set<string>([...currentMap.keys(), ...lastYearMap.keys()]);
    if (!isFinal) {
      for (let d = 1; d <= daysInMonth; d++) {
        allDays.add(String(d).padStart(2, '0'));
      }
    }

    let scalingRatio = 1;
    if (lastActualDay && lastYearMap.size > 0) {
      let currentSum = 0;
      let lastYearSum = 0;
      for (const day of currentDays) {
        currentSum += currentMap.get(day)!.sales;
        const ly = lastYearMap.get(day);
        if (ly !== undefined) lastYearSum += ly;
      }
      if (lastYearSum > 0) scalingRatio = currentSum / lastYearSum;
    }

    return Array.from(allDays)
      .sort()
      .map((day) => {
        const current = currentMap.get(day);
        const hasActual = current !== undefined;
        const isFuture = !hasActual && !isFinal && lastActualDay !== null && day > lastActualDay && lastYearMap.has(day);
        const isLastActual = day === lastActualDay && hasActual;
        const forecast = isFuture
          ? Math.round((lastYearMap.get(day) ?? 0) * scalingRatio)
          : isLastActual && !isFinal
            ? current!.sales
            : null;
        return {
          day,
          sales: hasActual ? current!.sales : null,
          qty: hasActual ? current!.qty : null,
          receipts: hasActual ? current!.receipts ?? null : null,
          sales_last_year: lastYearMap.get(day) ?? null,
          sales_forecast: forecast,
        };
      });
  }, [dailySales, dailyLastYear, summary]);

  // Card 1 data — always anchored to currentMonth; last bar shows forecast if month not final
  const currentHistoryChartData = useMemo(() => {
    return currentHistory.map((item, idx) => {
      const isLast = idx === currentHistory.length - 1;
      const isForecast = isLast && summary != null && !summary.is_month_final;
      const forecastSales = isForecast ? Number(summary!.forecast_sales ?? item.total_sales) : null;
      const target = Number(item.total_target);
      const progress = isForecast && forecastSales != null && target > 0
        ? Math.round(forecastSales / target * 10000) / 100
        : Number(item.target_progress_pct ?? 0);
      return {
        month: item.month.slice(2),
        sales: isForecast ? forecastSales! : Number(item.total_sales),
        target,
        progress,
        isForecast,
      };
    });
  }, [currentHistory, summary]);

  const yearHistoryChartData = useMemo(
    () =>
      yearHistory.map((pt) => ({
        label: pt.label,
        sales: Number(pt.total_sales),
        target: Number(pt.total_target),
        progress: pt.total_target > 0
          ? Math.round((Number(pt.total_sales) / Number(pt.total_target)) * 100 * 100) / 100
          : 0,
        isAggregate: pt.is_aggregate,
      })),
    [yearHistory]
  );

  // KPI trend data for new Card 2
  const kpiChartData = useMemo(
    () =>
      currentHistory.map((item) => ({
        month: item.month.slice(2),
        value:
          kpiMetric === 'total_receipts'
            ? Number(item.total_receipts)
            : Number(item[kpiMetric] ?? 0),
      })),
    [currentHistory, kpiMetric]
  );

  const selectedHistoryPoint = useMemo(
    () => {
      if (historySummary) {
        return {
          month: historySummary.month,
          total_sales: historySummary.total_sales,
          total_target: historySummary.total_target,
          target_progress_pct: historySummary.target_progress_pct,
          total_quantity: historySummary.total_quantity,
          total_receipts: historySummary.total_receipts,
          proc_bon2acc: historySummary.proc_bon2acc,
          prc_focus_acc_qty: historySummary.prc_focus_acc_qty,
          total_stores: historySummary.total_stores,
          total_agents: historySummary.total_agents,
          working_days: historySummary.working_days,
          daily_average: historySummary.daily_average,
          medie_produs: historySummary.medie_produs,
        };
      }
      return history.find((item) => item.month === historyMonth) ?? history[history.length - 1] ?? null;
    },
    [history, historyMonth, historySummary]
  );

  const comparisonDeltas = useMemo(() => {
    if (!periodComparison) return null;
    const current = Number(periodComparison.current.total_sales);
    const previous = Number(periodComparison.previous.total_sales);
    const yearOverYear = Number(periodComparison.year_over_year.total_sales);
    const currentReceipts = Number(periodComparison.current.total_receipts);
    const previousReceipts = Number(periodComparison.previous.total_receipts);
    const yearOverYearReceipts = Number(periodComparison.year_over_year.total_receipts);
    const currentQuantity = Number(periodComparison.current.total_quantity);
    const previousQuantity = Number(periodComparison.previous.total_quantity);
    const yearOverYearQuantity = Number(periodComparison.year_over_year.total_quantity);
    const pct = (delta: number, base: number) => base > 0 ? Math.round((delta / base) * 100) : null;

    return {
      previousSales: current - previous,
      previousSalesPct: pct(current - previous, previous),
      previousReceipts: currentReceipts - previousReceipts,
      previousReceiptsPct: pct(currentReceipts - previousReceipts, previousReceipts),
      previousQuantity: currentQuantity - previousQuantity,
      previousQuantityPct: pct(currentQuantity - previousQuantity, previousQuantity),
      yearSales: current - yearOverYear,
      yearSalesPct: pct(current - yearOverYear, yearOverYear),
      yearReceipts: currentReceipts - yearOverYearReceipts,
      yearReceiptsPct: pct(currentReceipts - yearOverYearReceipts, yearOverYearReceipts),
      yearQuantity: currentQuantity - yearOverYearQuantity,
      yearQuantityPct: pct(currentQuantity - yearOverYearQuantity, yearOverYearQuantity),
    };
  }, [periodComparison]);

  const currentStatusLabel = useMemo(() => {
    if (!summary) return '';
    if (summary.is_month_final) {
      return `Luna finala pentru ${currentMonth}, inchisa la ${summary.last_sale_date ?? currentMonth}.`;
    }
    return `Luna in curs ${currentMonth} este inca in actualizare pana in ziua ${summary.imported_day_of_month ?? '-'} din ${summary.days_in_month ?? '-'}.`;
  }, [summary, currentMonth]);

  const handleToggleHistoryMonth = useCallback((month: string) => {
    const isSelected = draftSelectedHistoryMonths.includes(month);
    if (isSelected && draftSelectedHistoryMonths.length === 1) {
      return;
    }
    const next = isSelected
      ? draftSelectedHistoryMonths.filter((item) => item !== month)
      : [...draftSelectedHistoryMonths, month];
    setDraftHistoryMonths(sortMonthsAsc(next));
  }, [draftSelectedHistoryMonths]);

  const handleApplyHistoryMonths = useCallback(() => {
    const sorted = sortMonthsAsc(draftSelectedHistoryMonths);
    setHistoryMonths(sorted);
    setHistoryMonth(sorted[sorted.length - 1] ?? currentMonth);
    historyMonthDropdownRef.current?.removeAttribute('open');
  }, [currentMonth, draftSelectedHistoryMonths]);

  const handleHistoryDropdownToggle = useCallback(() => {
    const isOpen = Boolean(historyMonthDropdownRef.current?.open);
    setHistoryMonthDropdownOpen(isOpen);
    if (isOpen) {
      setDraftHistoryMonths(selectedHistoryMonths);
    }
  }, [selectedHistoryMonths]);

  const categoryMixChartData = useMemo(
    () =>
      categoryMix.map((item) => ({
        category: item.category,
        sales_total: Number(item.sales_total),
        quantity_total: Number(item.quantity_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [categoryMix]
  );

  const receiptBucketChartData = useMemo(
    () =>
      receiptBucketMix.map((item) => ({
        bucket: item.bucket,
        receipt_count: Number(item.receipt_count),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [receiptBucketMix]
  );

  const focusSubcategoryChartData = useMemo(
    () =>
      focusSubcategoryMix.map((item) => ({
        category: CATEGORY_SHORT[item.category] ?? item.category,
        quantity_total: Number(item.quantity_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [focusSubcategoryMix]
  );

  const historyReceiptBucketChartData = useMemo(
    () =>
      historyReceiptBucketMix.map((item) => ({
        bucket: item.bucket,
        receipt_count: Number(item.receipt_count),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [historyReceiptBucketMix]
  );

  const historyFocusSubcategoryChartData = useMemo(
    () =>
      historyFocusSubcategoryMix.map((item) => ({
        category: CATEGORY_SHORT[item.category] ?? item.category,
        quantity_total: Number(item.quantity_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [historyFocusSubcategoryMix]
  );

  const historyStatusLabel = useMemo(() => {
    if (!historySummary) return '';
    if (selectedHistoryMonths.length > 1) {
      return `${selectedHistoryMonths.length} luni agregate: ${selectedHistoryMonths.join(', ')}.`;
    }
    if (historySummary.is_month_final) {
      return `Luna finala ${historyMonth}, inchisa la ${historySummary.last_sale_date ?? historyMonth}.`;
    }
    return `Luna ${historyMonth} este inca in actualizare pana in ziua ${historySummary.imported_day_of_month ?? '-'} din ${historySummary.days_in_month ?? '-'}.`;
  }, [historySummary, historyMonth, selectedHistoryMonths]);

  const historyDailyChartData = useMemo(
    () =>
      historyDailySales.map((item) => ({
        day: item.sale_date.slice(-2),
        sales: Number(item.total_sales),
        qty: Number(item.total_quantity),
        receipts: Number(item.receipt_count),
      })),
    [historyDailySales]
  );

  const historyCategoryMixChartData = useMemo(
    () =>
      historyCategoryMix.map((item) => ({
        category: item.category,
        sales_total: Number(item.sales_total),
        quantity_total: Number(item.quantity_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [historyCategoryMix]
  );

  const historyBrandMixChartData = useMemo(
    () =>
      historyBrandMix.map((item) => ({
        brand: item.brand,
        sales_total: Number(item.sales_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [historyBrandMix]
  );

  const brandMixChartData = useMemo(
    () =>
      brandMix.map((item) => ({
        brand: item.brand,
        sales_total: Number(item.sales_total),
        share_pct: Number(item.share_pct ?? 0),
      })),
    [brandMix]
  );

  const currentStoreSort = useSortable<StoreStat, StoreSortKey>({
    rows: stores,
    key: 'proc_realizare_target',
    defaultAscKeys: STORE_ASC_SORT_KEYS,
    getValue: getStoreSortValue,
  });
  const currentAgentSort = useSortable<AgentStat, AgentSortKey>({
    rows: agents,
    key: 'total_vanzari',
    defaultAscKeys: AGENT_ASC_SORT_KEYS,
    getValue: getAgentSortValue,
  });
  const currentRegionalSort = useSortable<RegionalStat, RegionalSortKey>({
    rows: regionals,
    key: 'total_vanzari',
    defaultAscKeys: REGIONAL_ASC_SORT_KEYS,
    getValue: getRegionalSortValue,
  });
  const historicalRegionalSort = useSortable<RegionalStat, RegionalSortKey>({
    rows: historyRegionals,
    key: 'total_vanzari',
    defaultAscKeys: REGIONAL_ASC_SORT_KEYS,
    getValue: getRegionalSortValue,
  });
  const historicalStoreSort = useSortable<StoreStat, StoreSortKey>({
    rows: historyStores,
    key: 'total_vanzari',
    defaultAscKeys: STORE_ASC_SORT_KEYS,
    getValue: getStoreSortValue,
  });
  const historicalAgentSort = useSortable<AgentStat, AgentSortKey>({
    rows: historyAgents,
    key: 'total_vanzari',
    defaultAscKeys: AGENT_ASC_SORT_KEYS,
    getValue: getAgentSortValue,
  });

  const storeSort = useMemo(
    () => ({ key: currentStoreSort.sortKey, direction: currentStoreSort.direction }),
    [currentStoreSort.direction, currentStoreSort.sortKey]
  );
  const agentSort = useMemo(
    () => ({ key: currentAgentSort.sortKey, direction: currentAgentSort.direction }),
    [currentAgentSort.direction, currentAgentSort.sortKey]
  );
  const regionalSort = useMemo(
    () => ({ key: currentRegionalSort.sortKey, direction: currentRegionalSort.direction }),
    [currentRegionalSort.direction, currentRegionalSort.sortKey]
  );
  const historyRegionalSort = useMemo(
    () => ({ key: historicalRegionalSort.sortKey, direction: historicalRegionalSort.direction }),
    [historicalRegionalSort.direction, historicalRegionalSort.sortKey]
  );
  const historyStoreSort = useMemo(
    () => ({ key: historicalStoreSort.sortKey, direction: historicalStoreSort.direction }),
    [historicalStoreSort.direction, historicalStoreSort.sortKey]
  );
  const historyAgentSort = useMemo(
    () => ({ key: historicalAgentSort.sortKey, direction: historicalAgentSort.direction }),
    [historicalAgentSort.direction, historicalAgentSort.sortKey]
  );

  const sortedStores = currentStoreSort.sorted;
  const sortedAgents = currentAgentSort.sorted;
  const sortedRegionals = currentRegionalSort.sorted;
  const sortedHistoryRegionals = historicalRegionalSort.sorted;
  const sortedHistoryStores = historicalStoreSort.sorted;
  const sortedHistoryAgents = historicalAgentSort.sorted;
  const handleSortStores = currentStoreSort.handleSort;
  const handleSortAgents = currentAgentSort.handleSort;
  const handleSortRegionals = currentRegionalSort.handleSort;
  const handleSortHistoryRegionals = historicalRegionalSort.handleSort;
  const handleSortHistoryStores = historicalStoreSort.handleSort;
  const handleSortHistoryAgents = historicalAgentSort.handleSort;

  const filterScopeLabel = useMemo(() => describeFilterScope(filters), [filters]);

  const regionalColumnsVisible = CURRENT_REGIONAL_COLUMNS;
  const storeColumnsVisible = CURRENT_STORE_COLUMNS;
  const agentColumnsVisible = CURRENT_AGENT_COLUMNS;
  const openPerformanceDetail = (selection: PerformanceSelection) => {
    setPerformanceSelection(selection);
  };

  return (
    <div className="space-y-3 p-3 pb-24 lg:pb-6 pt-2">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Sales Hub</h1>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Luna in curs este fixata pe {currentMonth}, iar istoricul se analizeaza separat.
        </p>
      </div>

      <div className="glass flex rounded-2xl p-1">
        <button
          onClick={() => setActiveSection('current')}
          className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
            activeSection === 'current'
              ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
              : 'text-slate-500'
          }`}
        >
          Luna in curs
        </button>
        <button
          onClick={() => setActiveSection('history')}
          className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
            activeSection === 'history'
              ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
              : 'text-slate-500'
          }`}
        >
          Istoric
        </button>
        <button
          onClick={() => setActiveSection('visits')}
          className={`flex-1 flex items-center justify-center gap-1 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
            activeSection === 'visits'
              ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
              : 'text-slate-500'
          }`}
        >
          <MapPin size={11} />
          Vizite
        </button>
      </div>

      {activeSection === 'visits' ? (
        <VisiteSubtab currentMonth={currentMonth} />
      ) : loading ? (
        <LoadingCard label="Se incarca luna in curs..." />
      ) : error || !summary ? (
        <ErrorCard
          message={error ?? 'Datele pentru luna in curs nu au putut fi incarcate.'}
          onRetry={refetchCurrentData}
        />
      ) : activeSection === 'current' ? (
        <>
          <div className="glass flex rounded-2xl p-1">
            <button
              type="button"
              onClick={() => setCurrentMode('overview')}
              className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
                currentMode === 'overview'
                  ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
                  : 'text-slate-500'
              }`}
            >
              Overview
            </button>
            <button
              type="button"
              onClick={() => setCurrentMode('forecast')}
              className={`flex-1 rounded-xl px-3 py-2 text-xs font-bold transition-all ${
                currentMode === 'forecast'
                  ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400'
                  : 'text-slate-500'
              }`}
            >
              AI Forecast
            </button>
          </div>

          {currentMode === 'forecast' ? (
            <AiForecastPanel currentMonth={currentMonth} filters={filters} />
          ) : (
            <>
              <div className="glass rounded-3xl p-4 space-y-4">

                {/* 1. Header compact */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold truncate">Overview — {currentMonth}</h3>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">{currentStatusLabel}</p>
                  </div>
                  <span className="shrink-0 rounded-xl bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {summary.last_sale_date ?? '-'}
                  </span>
                </div>

            {/* 2. Bloc financiar cu bara de progres */}
            <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
              {/* Cele trei valori */}
              <div className="mb-3 grid grid-cols-3 gap-2 text-center">
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Target</div>
                  <div className="mt-0.5 text-[13px] font-bold text-slate-600 dark:text-slate-300">
                    <CompactCurrency value={Number(summary.total_target)} />
                  </div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Realizat</div>
                  <div className="mt-0.5 text-[13px] font-bold text-slate-800 dark:text-slate-100">
                    <CompactCurrency value={Number(summary.total_sales)} />
                  </div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">Previziune</div>
                  <div className="mt-0.5 text-[13px] font-bold text-indigo-600 dark:text-indigo-400">
                    <CompactCurrency value={Number(summary.forecast_sales ?? summary.total_sales)} />
                  </div>
                </div>
              </div>

              {/* Bara duala actual + forecast */}
              <div className="relative h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                {/* Forecast (fundal) */}
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-indigo-200 dark:bg-indigo-700"
                  style={{ width: `${Math.min(Number(summary.forecast_target_progress_pct ?? 0), 100)}%` }}
                />
                {/* Actual (prim-plan) */}
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-indigo-600"
                  style={{ width: `${Math.min(Number(summary.target_progress_pct ?? 0), 100)}%` }}
                />
              </div>
              <div className="mt-1.5 flex justify-between text-[10px] font-semibold">
                <span className="text-indigo-600">
                  Actual {formatPercent(summary.target_progress_pct)}
                </span>
                <span className="text-slate-600 dark:text-slate-300">
                  Forecast {formatPercent(summary.forecast_target_progress_pct)}
                </span>
              </div>
            </div>

            {/* 3. KPI-uri cheie */}
            <div className="grid grid-cols-2 gap-2.5">
              <KpiPerformanceCard
                title="ProcBon2Acc"
                value={summary.proc_bon2acc}
                tone={getBon2AccTone(Number(summary.proc_bon2acc ?? 0))}
                chartData={receiptBucketChartData}
                dataKey="receipt_count"
                nameKey="bucket"
                formatValue={formatInt}
              />
              <KpiPerformanceCard
                title="PrcFocus/AccQtty"
                value={summary.prc_focus_acc_qty}
                tone={getFocusTone(Number(summary.prc_focus_acc_qty ?? 0))}
                chartData={focusSubcategoryChartData}
                dataKey="quantity_total"
                nameKey="category"
                formatValue={formatInt}
              />
            </div>

            {/* 4. Metrici operationale */}
            <div className="grid grid-cols-4 gap-2 lg:grid-cols-8">
              <Metric label="Bonuri" value={formatInt(summary.total_receipts)} className="p-2" />
              <Metric label="Accesorii" value={formatInt(summary.total_quantity)} className="p-2" />
              <Metric
                label="Magazine / Agenți"
                value={
                  <span className="flex items-baseline gap-1.5">
                    <span>{formatInt(summary.total_stores)}</span>
                    <span className="text-slate-300 dark:text-slate-600">/</span>
                    <span>{formatInt(summary.total_agents)}</span>
                  </span>
                }
                className="p-2"
              />
              <Metric label="Zile lucrate" value={formatInt(summary.working_days)} className="p-2" />
              <Metric label="Med. zilnica" value={formatAmount(summary.daily_average ?? 0)} className="p-2" />
              <Metric label="Medie produs" value={formatAmount(summary.medie_produs ?? 0)} className="p-2" />
              <Metric
                label="Val. medie bon"
                value={formatAmount(
                  summary.total_receipts > 0
                    ? Number(summary.total_sales) / Number(summary.total_receipts)
                    : 0
                )}
                className="p-2"
              />
              <Metric
                label="Cartele"
                value={formatInt(summary.cartele_qty ?? 0)}
                className="p-2"
              />
            </div>

          </div>

          <div className="grid gap-3">
            <div className="glass rounded-3xl p-4 overflow-hidden min-w-0">
              <div className="mb-4 flex items-center gap-2">
                <CalendarRange size={16} className="text-indigo-500" />
                <h3 className="text-sm font-bold">Comparatie perioade</h3>
              </div>
              {!periodComparison || !comparisonDeltas ? (
                <div className="text-xs text-slate-500">
                  Date indisponibile pentru comparatia de perioade.
                </div>
              ) : (
                <div className="space-y-3">
                  <PeriodTable
                    current={periodComparison.current}
                    previous={periodComparison.previous}
                    yoy={periodComparison.year_over_year}
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <DeltaCard
                      title="Vs luna trecuta"
                      salesDelta={comparisonDeltas.previousSales}
                      salesPct={comparisonDeltas.previousSalesPct}
                      receiptsDelta={comparisonDeltas.previousReceipts}
                      receiptsPct={comparisonDeltas.previousReceiptsPct}
                      quantityDelta={comparisonDeltas.previousQuantity}
                      quantityPct={comparisonDeltas.previousQuantityPct}
                    />
                    <DeltaCard
                      title="Vs anul trecut"
                      salesDelta={comparisonDeltas.yearSales}
                      salesPct={comparisonDeltas.yearSalesPct}
                      receiptsDelta={comparisonDeltas.yearReceipts}
                      receiptsPct={comparisonDeltas.yearReceiptsPct}
                      quantityDelta={comparisonDeltas.yearQuantity}
                      quantityPct={comparisonDeltas.yearQuantityPct}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr]">
            <div className="glass rounded-3xl p-4">
              <div className="mb-3 flex items-center gap-2">
                <CalendarRange size={16} className="text-indigo-500" />
                <h3 className="text-sm font-bold">Evolutie zilnica pentru {currentMonth}</h3>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                  <ComposedChart data={dailyChartData}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                    <XAxis dataKey="day" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      formatter={(value: number, _name: string) => formatAmount(value)}
                    />
                    <Legend />
                    <Bar yAxisId="sales" dataKey="sales" name="Vanzari" fill="#4f46e5" radius={[8, 8, 0, 0]} />
                    <Line yAxisId="sales" type="monotone" dataKey="sales_last_year" name="Anul trecut" stroke="#10b981" strokeWidth={2} strokeDasharray="5 3" dot={false} connectNulls />
                    <Line yAxisId="sales" type="monotone" dataKey="sales_forecast" name="Prognoza" stroke="#f59e0b" strokeWidth={2} strokeDasharray="3 3" dot={false} connectNulls />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="glass rounded-3xl p-4">
              <div className="mb-3 flex items-center gap-2">
                <PieChartIcon size={16} className="text-indigo-500" />
                <h3 className="text-sm font-bold">Top categorii si branduri</h3>
              </div>
              <div className="space-y-4">
                <CompactPieSection
                  title="Top categorii"
                  emptyLabel="Nu exista categorii disponibile pentru filtrarea curenta."
                  pieData={categoryMixChartData}
                  dataKey="sales_total"
                  nameKey="category"
                  valueFormatter={formatAmount}
                  centerValue={formatCompactDonutValue(sumChartValues(categoryMixChartData, 'sales_total'))}
                />
                <CompactPieSection
                  title="Branduri compatibile"
                  emptyLabel="Nu exista date pentru brandurile urmarite."
                  pieData={brandMixChartData}
                  dataKey="sales_total"
                  nameKey="brand"
                  valueFormatter={formatAmount}
                  centerValue={formatCompactDonutValue(sumChartValues(brandMixChartData, 'sales_total'))}
                />
              </div>
            </div>
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <Users size={16} className="text-indigo-500" />
                  <h3 className="text-sm font-bold">RM — Regional Manager</h3>
                </div>
                <p className="text-[11px] text-slate-500">
                  Filtrare: {filterScopeLabel} · Sortare: {regionalColumnsVisible.find((column) => column.key === regionalSort.key)?.label} ({regionalSort.direction}) · {regionals.length} regionale
                </p>
              </div>
              <ExportTableButton
                filename={`hub_${currentMonth}_rm`}
                sheetName={`RM ${currentMonth}`}
                rows={sortedRegionals}
                columns={[
                  { header: 'Regional', value: (row) => row.regional },
                  { header: 'Target', value: (row) => formatCurrency(row.target) },
                  { header: 'Vanzari', value: (row) => formatCurrency(row.total_vanzari) },
                  { header: 'Procent', value: (row) => formatPercent(row.proc_realizare_target) },
                  { header: 'Forecast%', value: (row) => formatPercent(row.forecast_target_pct) },
                  { header: 'Cantitate', value: (row) => formatInt(row.qty_total) },
                  { header: 'Medie produs', value: (row) => formatCurrency(row.medie_produs ?? 0) },
                  { header: 'Nr bonuri', value: (row) => formatInt(row.nr_bonuri) },
                  { header: 'ProcBon2Acc', value: (row) => formatPercent(row.proc_bon2acc) },
                  { header: 'Focus%', value: (row) => formatPercent(row.prc_focus_acc_qty) },
                ]}
              />
            </div>
            <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
              <table className={REGIONAL_TABLE_CLASS}>
                <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                  <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {regionalColumnsVisible.map((column, i) => (
                      <React.Fragment key={column.key}>
                        <SortableHeader
                          label={column.label}
                          active={regionalSort.key === column.key}
                          direction={regionalSort.direction}
                          onClick={() => handleSortRegionals(column.key)}
                          className={`${COMPACT_TH_CLASS} ${i === 0 ? 'w-24 max-w-24' : 'max-w-[4.5rem]'}`}
                        />
                      </React.Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedRegionals.map((regional, index) => (
                    <tr
                      key={regional.regional}
                      className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                    >
                      <td className={`max-w-24 truncate font-semibold ${COMPACT_TEXT_TD_CLASS}`}>
                        <button
                          type="button"
                          onClick={() => openPerformanceDetail({ level: 'regional', key: regional.regional })}
                          className="max-w-full truncate text-left font-semibold text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300"
                          title="Detalii performanta"
                        >
                          {regional.regional}
                        </button>
                      </td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(regional.target)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(regional.total_vanzari)}</td>
                      <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`}>{formatPercent(regional.proc_realizare_target)}</td>
                      <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-slate-700 dark:text-slate-200`}>{formatPercent(regional.forecast_target_pct)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatInt(regional.qty_total)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(regional.medie_produs ?? 0)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatInt(regional.nr_bonuri)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatPercent(regional.proc_bon2acc)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatPercent(regional.prc_focus_acc_qty)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <Building2 size={16} className="text-indigo-500" />
                  <h3 className="text-sm font-bold">Magazine</h3>
                </div>
                <p className="text-[11px] text-slate-500">
                  Filtrare: {filterScopeLabel} · Sortare: {storeColumnsVisible.find((column) => column.key === storeSort.key)?.label} ({storeSort.direction}) · {stores.length} magazine
                </p>
              </div>
              <ExportTableButton
                filename={`hub_${currentMonth}_magazine`}
                sheetName={`Magazine ${currentMonth}`}
                rows={sortedStores}
                columns={[
                  { header: 'Firma', value: (row) => row.firma },
                  { header: 'Magazin', value: (row) => row.locatie },
                  { header: 'Target', value: (row) => formatCurrency(row.target) },
                  { header: 'Vanzari', value: (row) => formatCurrency(row.total_vanzari) },
                  { header: 'Procent', value: (row) => formatPercent(row.proc_realizare_target) },
                  { header: 'Forecast%', value: (row) => formatPercent(row.forecast_target_pct) },
                  { header: 'Cantitate', value: (row) => formatInt(row.qty_total ?? 0) },
                  { header: 'Medie produs', value: (row) => formatCurrency(row.medie_produs ?? 0) },
                  { header: 'Nr bonuri', value: (row) => formatInt(row.nr_bonuri) },
                  { header: 'Retururi', value: (row) => formatInt(row.return_receipt_count) },
                  { header: 'Agenti', value: (row) => formatInt(row.nr_agenti) },
                  { header: 'Zile active', value: (row) => formatInt(row.zile_active) },
                ]}
              />
            </div>
            <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
              <table className={STORE_TABLE_CLASS}>
                <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                  <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {storeColumnsVisible.map((column, i) => (
                      <React.Fragment key={column.key}>
                        <SortableHeader
                          label={column.label}
                          active={storeSort.key === column.key}
                          direction={storeSort.direction}
                          onClick={() => handleSortStores(column.key)}
                          className={`${COMPACT_TH_CLASS} ${i === 0 ? 'w-32 max-w-32' : 'max-w-[4.5rem]'}`}
                        />
                      </React.Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedStores.map((store, index) => (
                    <tr
                      key={store.site_code}
                      className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                    >
                      <td className={`max-w-32 truncate font-semibold ${COMPACT_TEXT_TD_CLASS}`}>
                        <button
                          type="button"
                          onClick={() => openPerformanceDetail({ level: 'store', key: store.site_code })}
                          className="inline-flex min-w-0 max-w-full items-center text-left font-semibold text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300"
                          title="Detalii performanta"
                        >
                          <FirmaBadge firma={store.firma} />
                          <span className="truncate">{store.locatie}</span>
                        </button>
                      </td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(store.target)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(store.total_vanzari)}</td>
                      <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`}>{formatPercent(store.proc_realizare_target)}</td>
                      <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-slate-700 dark:text-slate-200`}>{formatPercent(store.forecast_target_pct)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatInt(store.qty_total ?? 0)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(store.medie_produs ?? 0)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatInt(store.nr_bonuri)}</td>
                      <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-rose-600 dark:text-rose-400`}>{formatInt(store.return_receipt_count)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatInt(store.nr_agenti)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatInt(store.zile_active)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="glass rounded-3xl p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold">Agenti - Toti agentii</h3>
                  <p className="text-[11px] text-slate-500">
                    Filtrare: {filterScopeLabel} · Sortare: {agentColumnsVisible.find((column) => column.key === agentSort.key)?.label} ({agentSort.direction}) · {agents.length} agenti
                  </p>
                </div>
                <ExportTableButton
                  filename={`hub_${currentMonth}_agenti`}
                  sheetName={`Agenti ${currentMonth}`}
                  rows={sortedAgents}
                  columns={[
                    { header: 'Agent', value: (row) => row.agent },
                    { header: 'Firma', value: (row) => row.firma },
                    { header: 'Magazin', value: (row) => row.locatie },
                    { header: 'Target', value: (row) => formatCurrency(row.target ?? 0) },
                    { header: 'Vanzari', value: (row) => formatCurrency(row.total_vanzari) },
                    { header: 'Procent', value: (row) => formatPercent(row.proc_realizare_target) },
                    { header: 'Cantitate', value: (row) => formatInt(row.acc_qty_realizat) },
                    { header: 'Medie produs', value: (row) => formatCurrency(row.medie_produs ?? 0) },
                    { header: 'Nr bonuri', value: (row) => formatInt(row.nr_bonuri) },
                    { header: 'Retururi', value: (row) => formatInt(row.return_receipt_count) },
                    { header: 'Zile lucrate', value: (row) => formatInt(row.zile_lucrate) },
                    { header: 'Medie zilnica', value: (row) => formatCurrency(row.medie_zilnica ?? 0) },
                    { header: 'ProcBon2Acc', value: (row) => formatPercent(row.proc_bon2acc) },
                    { header: 'Focus%', value: (row) => formatPercent(row.prc_focus_acc_qty) },
                  ]}
                />
              </div>
            <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
              <table className={AGENT_TABLE_CLASS}>
                <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                  <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {agentColumnsVisible.map((column, i) => (
                      <React.Fragment key={column.key}>
                        <SortableHeader
                          label={column.label}
                          active={agentSort.key === column.key}
                          direction={agentSort.direction}
                          onClick={() => handleSortAgents(column.key)}
                          className={`${COMPACT_TH_CLASS} ${i === 0 ? 'w-20 max-w-20' : i === 1 ? 'w-28 max-w-28' : 'max-w-[4.5rem]'}`}
                        />
                      </React.Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedAgents.map((agentRow, index) => (
                    <tr
                      key={`${agentRow.agent}-${agentRow.site_code}`}
                      className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                    >
                      <td className={`max-w-20 truncate font-bold ${COMPACT_TEXT_TD_CLASS}`}>
                        <button
                          type="button"
                          onClick={() => openPerformanceDetail({ level: 'agent', key: agentRow.agent, site_code: agentRow.site_code })}
                          className="max-w-full truncate text-left font-bold text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300"
                          title="Detalii performanta"
                        >
                          {agentRow.agent}
                        </button>
                      </td>
                      <td className={`max-w-28 truncate text-slate-500 ${COMPACT_TEXT_TD_CLASS}`}>{agentRow.locatie}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(agentRow.target ?? 0)}</td>
                      <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`}>{formatAmount(agentRow.total_vanzari)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatPercent(agentRow.proc_realizare_target)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatInt(agentRow.acc_qty_realizat)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(agentRow.medie_produs ?? 0)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatInt(agentRow.nr_bonuri)}</td>
                      <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-rose-600 dark:text-rose-400`}>{formatInt(agentRow.return_receipt_count)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatInt(agentRow.zile_lucrate)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(agentRow.medie_zilnica ?? 0)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatPercent(agentRow.proc_bon2acc)}</td>
                      <td className={COMPACT_NUM_TD_CLASS}>{formatPercent(agentRow.prc_focus_acc_qty)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
            </>
          )}
        </>
      ) : (
        <>
          {historyLoading ? (
            <LoadingCard label="Se incarca istoricul..." />
          ) : historyError ? (
            <ErrorCard message={historyError} onRetry={refetchHistoryData} />
          ) : !selectedHistoryPoint ? (
            <ErrorCard message="Nu exista valori istorice pentru luna selectata." onRetry={refetchHistoryData} />
          ) : (
            <>
              {/* Card 1 — Evolutie lunara (independent de historyMonth) */}
              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-bold">Evolutie lunara</h3>
                    <p className="text-[11px] text-slate-500">
                      {historyYearFilter === null
                        ? `Ultimele 13 luni finalizate${summary && !summary.is_month_final ? ' + previziune luna in curs' : ''}`
                        : `Toate lunile disponibile — ${historyYearFilter}`}
                    </p>
                  </div>
                  <select
                    value={historyYearFilter ?? ''}
                    onChange={(e) => setHistoryYearFilter(e.target.value === '' ? null : parseInt(e.target.value))}
                    className="rounded-xl border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                  >
                    <option value="">Standard</option>
                    {availableYears.map((yr) => (
                      <option key={yr} value={yr}>{yr}</option>
                    ))}
                  </select>
                </div>
                {(historyYearFilter === null ? currentHistoryLoading : yearHistoryLoading) ? (
                  <div className="flex h-64 items-center justify-center text-xs text-slate-400">Se incarca...</div>
                ) : historyYearFilter === null ? (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                      <ComposedChart data={currentHistoryChartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                        <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="progress" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip formatter={(value: number, name: string) => (name === '% target' ? `${value.toFixed(2)}%` : formatAmount(value))} />
                        <Legend />
                        <Bar yAxisId="sales" dataKey="sales" name="Vanzari" radius={[8, 8, 0, 0]}>
                          {currentHistoryChartData.map((entry, index) => (
                            <Cell key={index} fill={entry.isForecast ? '#a78bfa' : '#4f46e5'} />
                          ))}
                        </Bar>
                        <Line yAxisId="sales" type="monotone" dataKey="target" name="Target" stroke="#10b981" strokeWidth={2} dot={false} />
                        <Line yAxisId="progress" type="monotone" dataKey="progress" name="% target" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                ) : yearHistoryChartData.length === 0 ? (
                  <div className="flex h-64 items-center justify-center text-xs text-slate-400">
                    Nu exista date pentru {historyYearFilter} cu filtrele curente.
                  </div>
                ) : (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                      <ComposedChart data={yearHistoryChartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                        <XAxis dataKey="label" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="progress" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip formatter={(value: number, name: string) => (name === '% target' ? `${value.toFixed(2)}%` : formatAmount(value))} />
                        <Legend />
                        <Bar yAxisId="sales" dataKey="sales" name="Vanzari" radius={[8, 8, 0, 0]}>
                          {yearHistoryChartData.map((entry, index) => (
                            <Cell key={index} fill={entry.isAggregate ? '#818cf8' : '#4f46e5'} />
                          ))}
                        </Bar>
                        {yearHistoryChartData.some((p) => p.target > 0) && (
                          <Line yAxisId="sales" type="monotone" dataKey="target" name="Target" stroke="#10b981" strokeWidth={2} dot={false} />
                        )}
                        {yearHistoryChartData.some((p) => p.progress > 0) && (
                          <Line yAxisId="progress" type="monotone" dataKey="progress" name="% target" stroke="#f59e0b" strokeWidth={2} dot={false} />
                        )}
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>

              {/* Card 2 — Trend KPI (inlocuieste area chart duplicat) */}
              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <TrendingUp size={16} className="text-indigo-500" />
                    <h3 className="text-sm font-bold">Trend KPI</h3>
                  </div>
                  <div className="flex gap-1">
                    {([
                      { key: 'proc_bon2acc', label: 'Bon2Acc' },
                      { key: 'prc_focus_acc_qty', label: 'Focus' },
                      { key: 'total_receipts', label: 'Bonuri' },
                    ] as const).map(({ key, label }) => (
                      <button
                        key={key}
                        onClick={() => setKpiMetric(key)}
                        className={`rounded-full px-2.5 py-1 text-[10px] font-bold transition-colors ${
                          kpiMetric === key
                            ? 'bg-indigo-600 text-white'
                            : 'bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                {currentHistoryLoading ? (
                  <div className="flex h-48 items-center justify-center text-xs text-slate-400">Se incarca...</div>
                ) : (
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                      <AreaChart data={kpiChartData}>
                        <defs>
                          <linearGradient id="kpiTrendArea" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.35} />
                            <stop offset="95%" stopColor="#4f46e5" stopOpacity={0.03} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                        <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip
                          formatter={(value: number) =>
                            kpiMetric === 'total_receipts' ? formatInt(value) : `${value.toFixed(1)}%`
                          }
                        />
                        <Area type="monotone" dataKey="value" name={kpiMetric === 'proc_bon2acc' ? 'ProcBon2Acc' : kpiMetric === 'prc_focus_acc_qty' ? 'PrcFocus/AccQtty' : 'Total bonuri'} stroke="#4f46e5" fill="url(#kpiTrendArea)" strokeWidth={2} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>

              <div className="glass relative z-50 rounded-3xl p-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold">Luni analizate</h3>
                    <p className="text-[11px] text-slate-500">
                      Bifeaza una sau mai multe luni; rezultatele de mai jos se agrega automat
                    </p>
                  </div>
                  <div className="flex flex-wrap items-start gap-2">
                    <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                      <input
                        type="checkbox"
                        checked={includeClosedStores}
                        onChange={(event) => setIncludeClosedStores(event.target.checked)}
                        className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      Include magazine inchise
                    </label>
                    <details ref={historyMonthDropdownRef} onToggle={handleHistoryDropdownToggle} className="group relative z-50">
                      <summary className="flex min-w-60 cursor-pointer list-none items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold outline-none transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700">
                        <span className="truncate">
                          {historyMonthDropdownOpen ? draftHistorySelectionLabel : historySelectionLabel}
                        </span>
                        <ChevronDown size={14} className="shrink-0 text-slate-400 transition-transform group-open:rotate-180" />
                      </summary>
                      <div className="absolute right-0 z-[100] mt-2 w-64 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-700 dark:bg-slate-900">
                        <div className="max-h-72 overflow-auto pr-1">
                          {months.map((month) => {
                            const checked = draftSelectedHistoryMonths.includes(month);
                            return (
                              <label
                                key={month}
                                className={`flex cursor-pointer items-center gap-2 rounded-xl px-2.5 py-2 text-xs font-semibold transition-colors ${
                                  checked
                                    ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300'
                                    : 'text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800'
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => handleToggleHistoryMonth(month)}
                                  className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                                />
                                <span>{month}</span>
                              </label>
                            );
                          })}
                        </div>
                        <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2 dark:border-slate-800">
                          <span className="text-[10px] font-semibold text-slate-400">
                            {draftSelectedHistoryMonths.length} selectate
                          </span>
                          <button
                            type="button"
                            onClick={handleApplyHistoryMonths}
                            className="rounded-xl bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white shadow-sm transition-colors hover:bg-indigo-700"
                          >
                            OK
                          </button>
                        </div>
                      </div>
                    </details>
                  </div>
                </div>
              </div>

              {/* Overview card — mirrors the first card from Luna in curs */}
              <div className="glass rounded-3xl p-4 space-y-4">
                {/* 1. Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold truncate">Overview — {historySelectionLabel}</h3>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">{historyStatusLabel}</p>
                  </div>
                  <span className="shrink-0 rounded-xl bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {historySummary?.last_sale_date ?? '-'}
                  </span>
                </div>

                {/* 2. Financial block with progress bar */}
                <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
                  <div className="mb-3 grid grid-cols-3 gap-2 text-center">
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Target</div>
                      <div className="mt-0.5 text-[13px] font-bold text-slate-600 dark:text-slate-300">
                        <CompactCurrency value={Number(historySummary?.total_target ?? selectedHistoryPoint.total_target)} />
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Realizat</div>
                      <div className="mt-0.5 text-[13px] font-bold text-slate-800 dark:text-slate-100">
                        <CompactCurrency value={Number(historySummary?.total_sales ?? selectedHistoryPoint.total_sales)} />
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">
                        {historySummary?.is_month_final === false ? 'Previziune' : 'Realizat %'}
                      </div>
                      <div className="mt-0.5 text-[13px] font-bold text-indigo-600 dark:text-indigo-400">
                        {historySummary?.is_month_final === false
                          ? <CompactCurrency value={Number(historySummary?.forecast_sales ?? historySummary?.total_sales ?? selectedHistoryPoint.total_sales)} />
                          : formatPercent(historySummary?.target_progress_pct ?? selectedHistoryPoint.target_progress_pct)
                        }
                      </div>
                    </div>
                  </div>

                  {/* Dual progress bar */}
                  <div className="relative h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                    {historySummary?.is_month_final === false && (
                      <div
                        className="absolute inset-y-0 left-0 rounded-full bg-indigo-200 dark:bg-indigo-700"
                        style={{ width: `${Math.min(Number(historySummary?.forecast_target_progress_pct ?? 0), 100)}%` }}
                      />
                    )}
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-indigo-600"
                      style={{ width: `${Math.min(Number(historySummary?.target_progress_pct ?? selectedHistoryPoint.target_progress_pct ?? 0), 100)}%` }}
                    />
                  </div>
                  <div className="mt-1.5 flex justify-between text-[10px] font-semibold">
                    <span className="text-indigo-600">
                      Actual {formatPercent(historySummary?.target_progress_pct ?? selectedHistoryPoint.target_progress_pct)}
                    </span>
                    {historySummary?.is_month_final === false && (
                      <span className="text-slate-600 dark:text-slate-300">
                        Forecast {formatPercent(historySummary?.forecast_target_progress_pct)}
                      </span>
                    )}
                  </div>
                </div>

                {/* 3. KPI performance cards */}
                <div className="grid grid-cols-2 gap-2.5">
                  <KpiPerformanceCard
                    title="ProcBon2Acc"
                    value={historySummary?.proc_bon2acc ?? selectedHistoryPoint.proc_bon2acc}
                    tone={getBon2AccTone(Number(historySummary?.proc_bon2acc ?? selectedHistoryPoint.proc_bon2acc ?? 0))}
                    chartData={historyReceiptBucketChartData}
                    dataKey="receipt_count"
                    nameKey="bucket"
                    formatValue={formatInt}
                  />
                  <KpiPerformanceCard
                    title="PrcFocus/AccQtty"
                    value={historySummary?.prc_focus_acc_qty ?? selectedHistoryPoint.prc_focus_acc_qty}
                    tone={getFocusTone(Number(historySummary?.prc_focus_acc_qty ?? selectedHistoryPoint.prc_focus_acc_qty ?? 0))}
                    chartData={historyFocusSubcategoryChartData}
                    dataKey="quantity_total"
                    nameKey="category"
                    formatValue={formatInt}
                  />
                </div>

                {/* 4. Operational metrics */}
                <div className="grid grid-cols-4 gap-2 lg:grid-cols-8">
                  <Metric label="Bonuri" value={formatInt(historySummary?.total_receipts ?? selectedHistoryPoint.total_receipts)} className="p-2" />
                  <Metric label="Accesorii" value={formatInt(historySummary?.total_quantity ?? selectedHistoryPoint.total_quantity)} className="p-2" />
                  <Metric
                    label="Magazine / Agenți"
                    value={
                      <span className="flex items-baseline gap-1.5">
                        <span>{formatInt(historySummary?.total_stores ?? selectedHistoryPoint.total_stores)}</span>
                        <span className="text-slate-300 dark:text-slate-600">/</span>
                        <span>{formatInt(historySummary?.total_agents ?? selectedHistoryPoint.total_agents)}</span>
                      </span>
                    }
                    className="p-2"
                  />
                  <Metric label="Zile lucrate" value={formatInt(historySummary?.working_days ?? selectedHistoryPoint.working_days)} className="p-2" />
                  <Metric label="Med. zilnica" value={formatAmount(historySummary?.daily_average ?? selectedHistoryPoint.daily_average ?? 0)} className="p-2" />
                  <Metric label="Medie produs" value={formatAmount(historySummary?.medie_produs ?? selectedHistoryPoint.medie_produs ?? 0)} className="p-2" />
                  <Metric
                    label="Val. medie bon"
                    value={formatAmount(
                      (historySummary?.total_receipts ?? selectedHistoryPoint.total_receipts) > 0
                        ? Number(historySummary?.total_sales ?? selectedHistoryPoint.total_sales) / Number(historySummary?.total_receipts ?? selectedHistoryPoint.total_receipts)
                        : 0
                    )}
                    className="p-2"
                  />
                  <Metric
                    label="Cartele"
                    value={formatInt(historySummary?.cartele_qty ?? 0)}
                    className="p-2"
                  />
                </div>
              </div>

              {/* Evolutie zilnica + Top categorii si branduri */}
              <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr]">
                <div className="glass rounded-3xl p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <CalendarRange size={16} className="text-indigo-500" />
                    <h3 className="text-sm font-bold">Evolutie zilnica pentru {historySelectionLabel}</h3>
                  </div>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                      <ComposedChart data={historyDailyChartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                        <XAxis dataKey="day" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis yAxisId="qty" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip
                          formatter={(value: number, name: string) =>
                            name === 'Vanzari' ? formatAmount(value) : formatInt(value)
                          }
                        />
                        <Legend />
                        <Bar yAxisId="sales" dataKey="sales" name="Vanzari" fill="#4f46e5" radius={[8, 8, 0, 0]} />
                        <Line yAxisId="qty" type="monotone" dataKey="qty" name="Cantitate" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="glass rounded-3xl p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <PieChartIcon size={16} className="text-indigo-500" />
                    <h3 className="text-sm font-bold">Top categorii si branduri</h3>
                  </div>
                  <div className="space-y-4">
                    <CompactPieSection
                      title="Top categorii"
                      emptyLabel="Nu exista categorii disponibile pentru filtrarea curenta."
                      pieData={historyCategoryMixChartData}
                      dataKey="sales_total"
                      nameKey="category"
                      valueFormatter={formatAmount}
                      centerValue={formatCompactDonutValue(sumChartValues(historyCategoryMixChartData, 'sales_total'))}
                    />
                    <CompactPieSection
                      title="Branduri compatibile"
                      emptyLabel="Nu exista date pentru brandurile urmarite."
                      pieData={historyBrandMixChartData}
                      dataKey="sales_total"
                      nameKey="brand"
                      valueFormatter={formatAmount}
                      centerValue={formatCompactDonutValue(sumChartValues(historyBrandMixChartData, 'sales_total'))}
                    />
                  </div>
                </div>
              </div>

              {/* Breakdown tables — RM / Magazine / Agenti */}
              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <MapPin size={16} className="text-indigo-500" />
                      <h3 className="text-sm font-bold">RM</h3>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Sortare: {HIST_REGIONAL_COLUMNS.find((c) => c.key === historyRegionalSort.key)?.label} ({historyRegionalSort.direction}) · {historyRegionals.length} regionali
                    </p>
                  </div>
                  <ExportTableButton
                    filename={`hub_${historySelectionSlug}_istoric_rm`}
                    sheetName={`RM istoric`}
                    rows={sortedHistoryRegionals}
                    columns={[
                      { header: 'Regional', value: (row) => row.regional },
                      { header: 'Target', value: (row) => formatCurrency(row.target) },
                      { header: 'Vanzari', value: (row) => formatCurrency(row.total_vanzari) },
                      { header: 'Procent', value: (row) => formatPercent(row.proc_realizare_target) },
                      { header: 'Cantitate', value: (row) => formatInt(row.qty_total) },
                      { header: 'Nr bonuri', value: (row) => formatInt(row.nr_bonuri) },
                      { header: 'ProcBon2Acc', value: (row) => formatPercent(row.proc_bon2acc) },
                      { header: 'Focus%', value: (row) => formatPercent(row.prc_focus_acc_qty) },
                    ]}
                  />
                </div>
                <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
                  <table className={REGIONAL_TABLE_CLASS}>
                    <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                      <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                        {HIST_REGIONAL_COLUMNS.map((column, i) => (
                          <React.Fragment key={column.key}>
                            <SortableHeader
                              label={column.label}
                              active={historyRegionalSort.key === column.key}
                              direction={historyRegionalSort.direction}
                              onClick={() => handleSortHistoryRegionals(column.key)}
                              className={`${COMPACT_TH_CLASS} ${i === 0 ? 'w-24 max-w-24' : 'max-w-[4.5rem]'}`}
                            />
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedHistoryRegionals.map((row, index) => (
                        <tr
                          key={row.regional}
                          className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                        >
                          <td className={`max-w-24 truncate font-semibold ${COMPACT_TEXT_TD_CLASS}`}>{row.regional}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(row.target)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(row.total_vanzari)}</td>
                          <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`}>{formatPercent(row.proc_realizare_target)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatInt(row.qty_total)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatInt(row.nr_bonuri)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatPercent(row.proc_bon2acc)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatPercent(row.prc_focus_acc_qty)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <Building2 size={16} className="text-indigo-500" />
                      <h3 className="text-sm font-bold">Magazine</h3>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Sortare: {HIST_STORE_COLUMNS.find((c) => c.key === historyStoreSort.key)?.label} ({historyStoreSort.direction}) · {historyStores.length} magazine
                    </p>
                  </div>
                  <ExportTableButton
                    filename={`hub_${historySelectionSlug}_istoric_magazine`}
                    sheetName={`Magazine istoric`}
                    rows={sortedHistoryStores}
                    columns={[
                      { header: 'Firma', value: (row) => row.firma },
                      { header: 'Magazin', value: (row) => row.locatie },
                      { header: 'Target', value: (row) => formatCurrency(row.target) },
                      { header: 'Vanzari', value: (row) => formatCurrency(row.total_vanzari) },
                      { header: 'Procent', value: (row) => formatPercent(row.proc_realizare_target) },
                      { header: 'Cantitate', value: (row) => formatInt(row.qty_total ?? 0) },
                      { header: 'Nr bonuri', value: (row) => formatInt(row.nr_bonuri) },
                      { header: 'Retururi', value: (row) => formatInt(row.return_receipt_count) },
                      { header: 'Agenti', value: (row) => formatInt(row.nr_agenti) },
                      { header: 'Zile active', value: (row) => formatInt(row.zile_active) },
                    ]}
                  />
                </div>
                <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
                  <table className={STORE_TABLE_CLASS}>
                    <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                      <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                        {HIST_STORE_COLUMNS.map((column, i) => (
                          <React.Fragment key={column.key}>
                            <SortableHeader
                              label={column.label}
                              active={historyStoreSort.key === column.key}
                              direction={historyStoreSort.direction}
                              onClick={() => handleSortHistoryStores(column.key)}
                              className={`${COMPACT_TH_CLASS} ${i === 0 ? 'w-32 max-w-32' : 'max-w-[4.5rem]'}`}
                            />
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedHistoryStores.map((store, index) => (
                        <tr
                          key={store.site_code}
                          className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                        >
                          <td className={`max-w-32 truncate font-semibold ${COMPACT_TEXT_TD_CLASS}`}>
                            <span className="inline-flex min-w-0 items-center">
                              <FirmaBadge firma={store.firma} />
                              <span className="truncate">{store.locatie}</span>
                            </span>
                          </td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(store.target)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(store.total_vanzari)}</td>
                          <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`}>{formatPercent(store.proc_realizare_target)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatInt(store.qty_total ?? 0)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatInt(store.nr_bonuri)}</td>
                          <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-rose-600 dark:text-rose-400`}>{formatInt(store.return_receipt_count)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatInt(store.nr_agenti)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatInt(store.zile_active)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="glass rounded-3xl p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold">Agenti</h3>
                    <p className="text-[11px] text-slate-500">
                      Sortare: {HIST_AGENT_COLUMNS.find((c) => c.key === historyAgentSort.key)?.label} ({historyAgentSort.direction}) · {historyAgents.length} agenti
                    </p>
                  </div>
                  <ExportTableButton
                    filename={`hub_${historySelectionSlug}_istoric_agenti`}
                    sheetName={`Agenti istoric`}
                    rows={sortedHistoryAgents}
                    columns={[
                      { header: 'Agent', value: (row) => row.agent },
                      { header: 'Firma', value: (row) => row.firma },
                      { header: 'Magazin', value: (row) => row.locatie },
                      { header: 'Target', value: (row) => formatCurrency(row.target ?? 0) },
                      { header: 'Vanzari', value: (row) => formatCurrency(row.total_vanzari) },
                      { header: 'Procent', value: (row) => formatPercent(row.proc_realizare_target) },
                      { header: 'Cantitate', value: (row) => formatInt(row.acc_qty_realizat) },
                      { header: 'Nr bonuri', value: (row) => formatInt(row.nr_bonuri) },
                      { header: 'Retururi', value: (row) => formatInt(row.return_receipt_count) },
                      { header: 'Zile lucrate', value: (row) => formatInt(row.zile_lucrate) },
                      { header: 'Medie zilnica', value: (row) => formatCurrency(row.medie_zilnica ?? 0) },
                      { header: 'ProcBon2Acc', value: (row) => formatPercent(row.proc_bon2acc) },
                      { header: 'Focus%', value: (row) => formatPercent(row.prc_focus_acc_qty) },
                    ]}
                  />
                </div>
                <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
                  <table className={AGENT_TABLE_CLASS}>
                    <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
                      <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                        {HIST_AGENT_COLUMNS.map((column, i) => (
                          <React.Fragment key={column.key}>
                            <SortableHeader
                              label={column.label}
                              active={historyAgentSort.key === column.key}
                              direction={historyAgentSort.direction}
                              onClick={() => handleSortHistoryAgents(column.key)}
                              className={`${COMPACT_TH_CLASS} ${i === 0 ? 'w-20 max-w-20' : i === 1 ? 'w-28 max-w-28' : 'max-w-[4.5rem]'}`}
                            />
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedHistoryAgents.map((agentRow, index) => (
                        <tr
                          key={`${agentRow.agent}-${agentRow.site_code}`}
                          className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
                        >
                          <td className={`max-w-20 truncate font-bold ${COMPACT_TEXT_TD_CLASS}`}>{agentRow.agent}</td>
                          <td className={`max-w-28 truncate text-slate-500 ${COMPACT_TEXT_TD_CLASS}`}>{agentRow.locatie}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(agentRow.target ?? 0)}</td>
                          <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`}>{formatAmount(agentRow.total_vanzari)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatPercent(agentRow.proc_realizare_target)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatInt(agentRow.acc_qty_realizat)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatInt(agentRow.nr_bonuri)}</td>
                          <td className={`${COMPACT_NUM_TD_CLASS} font-bold text-rose-600 dark:text-rose-400`}>{formatInt(agentRow.return_receipt_count)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatInt(agentRow.zile_lucrate)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatAmount(agentRow.medie_zilnica ?? 0)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatPercent(agentRow.proc_bon2acc)}</td>
                          <td className={COMPACT_NUM_TD_CLASS}>{formatPercent(agentRow.prc_focus_acc_qty)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </>
      )}
      <PerformanceDetailDrawer
        open={performanceSelection !== null}
        selection={performanceSelection}
        detail={performanceDetail}
        loading={performanceLoading}
        error={performanceError}
        canViewSalaries={canViewSalaries}
        onClose={() => setPerformanceSelection(null)}
      />
    </div>
  );
}
