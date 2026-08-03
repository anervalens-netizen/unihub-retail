import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getPerformanceDetail, MAX_DASHBOARD_BATCH_MONTHS } from '../api/dashboard';
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
import { formatAmount, formatInt, formatPercent } from '../lib/formatters';
import FirmaBadge from './FirmaBadge';
import type { AppFilters } from './MainLayout';
import { useSortable } from '../lib/useSortable';
import {
  ErrorCard,
  LoadingCard,
  describeFilterScope,
  getAgentSortValue,
  getRegionalSortValue,
  getStoreSortValue,
} from './dashboard/DashboardWidgets';
import { useDashboardData, type AggregatedDashboardDetails } from './dashboard/useDashboardData';
import { useAuth } from '../auth/AuthContext';
import { canAccessSalaries } from '../auth/permissions';
import {
  PerformanceDetailDrawer,
  type PerformanceSelection,
} from './dashboard/PerformanceDetailDrawer';
import type { BreakdownColumn } from './dashboard/BreakdownTable';
import { CurrentDashboard } from './dashboard/CurrentDashboard';
import { HistoryDashboard } from './dashboard/HistoryDashboard';
import { SegmentedTabs, type SegmentedTabOption } from './common/SegmentedTabs';

const HISTORY_START_YEAR = 2018;
const VisiteSubtab = lazy(async () => {
  const module = await import('./VisiteSubtab');
  return { default: module.VisiteSubtab };
});

interface DashboardProps {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
  initialSection?: DashboardSection;
  onSectionChange?: (section: DashboardSection) => void;
}

type DashboardSection = 'current' | 'history' | 'visits';
const DASHBOARD_SECTIONS: SegmentedTabOption<DashboardSection>[] = [
  { value: 'current', label: 'Luna în curs' },
  { value: 'history', label: 'Istoric' },
  { value: 'visits', label: 'Vizite' },
];
type StoreSortKey =
  | 'locatie'
  | 'site_code'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'forecast_target_pct'
  | 'promo_qty'
  | 'incentive_qty'
  | 'qty_total'
  | 'nr_bonuri'
  | 'nr_agenti'
  | 'zile_active'
  | 'medie_zilnica'
  | 'medie_produs'
  | 'proc_bon2acc'
  | 'prc_focus_acc_qty'
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

const COMPACT_TD_CLASS = 'px-1.5 py-1 whitespace-nowrap align-middle leading-tight';
const COMPACT_NUM_TD_CLASS = `${COMPACT_TD_CLASS} text-right tabular-nums`;
const COMPACT_TEXT_TD_CLASS = `${COMPACT_TD_CLASS} text-left`;

function PromoMetric({ qty, discount }: { qty: number; discount: number }) {
  return (
    <span className="inline-flex flex-col items-end leading-[11px] lg:leading-tight">
      <span className="font-semibold">{formatInt(qty)} buc.</span>
      <span className="text-[10px] font-semibold text-amber-600 dark:text-amber-400">
        {formatAmount(discount)} RON
      </span>
    </span>
  );
}

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
  { key: 'promo_qty', label: 'Promo' },
  { key: 'incentive_qty', label: 'Incentive' },
  { key: 'qty_total', label: 'Cantitate' },
  { key: 'medie_produs', label: 'Medie produs' },
  { key: 'nr_bonuri', label: 'Nr bonuri' },
  { key: 'proc_bon2acc', label: 'ProcBon2Acc' },
  { key: 'prc_focus_acc_qty', label: 'Focus%' },
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
  { key: 'proc_bon2acc', label: 'ProcBon2Acc' },
  { key: 'prc_focus_acc_qty', label: 'Focus%' },
  { key: 'return_receipt_count', label: 'Retururi' },
  { key: 'zile_lucrate', label: 'Zile lucrate' },
  { key: 'medie_zilnica', label: 'Medie zilnica' },
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

const CURRENT_REGIONAL_COLUMNS = REGIONAL_COLUMNS.filter((c) => c.key !== 'incentive_qty');
const CURRENT_STORE_COLUMNS = STORE_COLUMNS.filter((c) => c.key !== 'site_code' && c.key !== 'incentive_qty');
const CURRENT_AGENT_COLUMNS = AGENT_COLUMNS.filter((c) => c.key !== 'incentive_qty');
const HIST_REGIONAL_COLUMNS = REGIONAL_COLUMNS.filter((c) => c.key !== 'promo_qty' && c.key !== 'incentive_qty' && c.key !== 'forecast_target_pct' && c.key !== 'medie_produs');
const HIST_STORE_COLUMNS = STORE_COLUMNS.filter((c) => c.key !== 'site_code' && c.key !== 'promo_qty' && c.key !== 'incentive_qty' && c.key !== 'forecast_target_pct' && c.key !== 'medie_produs');
const HIST_AGENT_COLUMNS = AGENT_COLUMNS.filter((c) => c.key !== 'promo_qty' && c.key !== 'incentive_qty' && c.key !== 'medie_produs');
const STORE_ASC_SORT_KEYS: StoreSortKey[] = ['locatie', 'site_code'];
const AGENT_ASC_SORT_KEYS: AgentSortKey[] = ['locatie', 'agent'];
const REGIONAL_ASC_SORT_KEYS: RegionalSortKey[] = ['regional'];

function regionalBreakdownColumns(
  columns: Array<{ key: RegionalSortKey; label: string }>,
  onOpen?: (selection: PerformanceSelection) => void,
): BreakdownColumn<RegionalStat, RegionalSortKey>[] {
  return columns.map((column, index) => ({
    ...column,
    headerClassName: index === 0 ? 'w-24 max-w-24' : 'max-w-[4.5rem]',
    cellClassName: column.key === 'regional'
      ? `max-w-24 truncate font-semibold ${COMPACT_TEXT_TD_CLASS}`
      : column.key === 'proc_realizare_target'
        ? `${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`
        : column.key === 'forecast_target_pct'
          ? `${COMPACT_NUM_TD_CLASS} font-bold text-slate-700 dark:text-slate-200`
          : COMPACT_NUM_TD_CLASS,
    render: (row) => {
      if (column.key === 'regional') {
        return onOpen ? (
          <button
            type="button"
            onClick={() => onOpen({ level: 'regional', key: row.regional })}
            className="max-w-full truncate text-left font-semibold text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300"
            title="Detalii performanta"
          >
            {row.regional}
          </button>
        ) : row.regional;
      }
      if (column.key === 'target' || column.key === 'total_vanzari' || column.key === 'medie_produs') {
        return formatAmount(row[column.key] ?? 0);
      }
      if (column.key === 'promo_qty') {
        return <PromoMetric qty={row.promo_qty} discount={row.promo_discount_value ?? 0} />;
      }
      if (column.key === 'proc_realizare_target' || column.key === 'forecast_target_pct' || column.key === 'proc_bon2acc' || column.key === 'prc_focus_acc_qty') {
        return formatPercent(row[column.key]);
      }
      return formatInt(row[column.key] ?? 0);
    },
  }));
}

function storeBreakdownColumns(
  columns: Array<{ key: StoreSortKey; label: string }>,
  onOpen?: (selection: PerformanceSelection) => void,
): BreakdownColumn<StoreStat, StoreSortKey>[] {
  return columns.map((column, index) => ({
    ...column,
    headerClassName: index === 0 ? 'w-32 max-w-32' : 'max-w-[4.5rem]',
    cellClassName: column.key === 'locatie'
      ? `max-w-32 truncate font-semibold ${COMPACT_TEXT_TD_CLASS}`
      : column.key === 'proc_realizare_target'
        ? `${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`
        : column.key === 'forecast_target_pct'
          ? `${COMPACT_NUM_TD_CLASS} font-bold text-slate-700 dark:text-slate-200`
          : column.key === 'return_receipt_count'
            ? `${COMPACT_NUM_TD_CLASS} font-bold text-rose-600 dark:text-rose-400`
            : COMPACT_NUM_TD_CLASS,
    render: (row) => {
      if (column.key === 'locatie') {
        const label = (
          <>
            <FirmaBadge firma={row.firma} />
            <span className="truncate">{row.locatie}</span>
          </>
        );
        return onOpen ? (
          <button
            type="button"
            onClick={() => onOpen({ level: 'store', key: row.site_code })}
            className="inline-flex min-w-0 max-w-full items-center text-left font-semibold text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300"
            title="Detalii performanta"
          >
            {label}
          </button>
        ) : <span className="inline-flex min-w-0 items-center">{label}</span>;
      }
      if (column.key === 'site_code') return row.firma;
      if (column.key === 'target' || column.key === 'total_vanzari' || column.key === 'medie_zilnica' || column.key === 'medie_produs') {
        return formatAmount(row[column.key] ?? 0);
      }
      if (column.key === 'promo_qty') {
        return <PromoMetric qty={row.promo_qty} discount={row.promo_discount_value ?? 0} />;
      }
      if (column.key === 'proc_realizare_target' || column.key === 'forecast_target_pct' || column.key === 'proc_bon2acc' || column.key === 'prc_focus_acc_qty') {
        return formatPercent(row[column.key]);
      }
      return formatInt(row[column.key] ?? 0);
    },
  }));
}

function agentBreakdownColumns(
  columns: Array<{ key: AgentSortKey; label: string }>,
  onOpen?: (selection: PerformanceSelection) => void,
): BreakdownColumn<AgentStat, AgentSortKey>[] {
  return columns.map((column, index) => ({
    ...column,
    headerClassName: index === 0 ? 'w-20 max-w-20' : index === 1 ? 'w-28 max-w-28' : 'max-w-[4.5rem]',
    cellClassName: column.key === 'agent'
      ? `max-w-20 truncate font-bold ${COMPACT_TEXT_TD_CLASS}`
      : column.key === 'locatie'
        ? `max-w-28 truncate text-slate-500 ${COMPACT_TEXT_TD_CLASS}`
        : column.key === 'total_vanzari'
          ? `${COMPACT_NUM_TD_CLASS} font-bold text-indigo-600`
          : column.key === 'return_receipt_count'
            ? `${COMPACT_NUM_TD_CLASS} font-bold text-rose-600 dark:text-rose-400`
            : COMPACT_NUM_TD_CLASS,
    render: (row) => {
      if (column.key === 'agent') {
        return onOpen ? (
          <button
            type="button"
            onClick={() => onOpen({ level: 'agent', key: row.agent, site_code: row.site_code })}
            className="max-w-full truncate text-left font-bold text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300"
            title="Detalii performanta"
          >
            {row.agent}
          </button>
        ) : row.agent;
      }
      if (column.key === 'locatie') return row.locatie;
      if (column.key === 'target' || column.key === 'total_vanzari' || column.key === 'medie_zilnica' || column.key === 'medie_produs') {
        return formatAmount(row[column.key] ?? 0);
      }
      if (column.key === 'promo_qty') {
        return <PromoMetric qty={row.promo_qty} discount={row.promo_discount_value ?? 0} />;
      }
      if (column.key === 'proc_realizare_target' || column.key === 'proc_bon2acc' || column.key === 'prc_focus_acc_qty') {
        return formatPercent(row[column.key]);
      }
      return formatInt(row[column.key] ?? 0);
    },
  }));
}

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
    last_sale_date: (() => {
      const dates = summaries.map((item) => item.last_sale_date).filter(Boolean).sort();
      return dates[dates.length - 1] ?? null;
    })(),
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
      const current = map.get(key) ?? { ...row, total_vanzari: 0, qty_total: 0, nr_bonuri: 0, nr_agenti: 0, zile_active: 0, target: 0, proc_realizare_target: null, forecast_target_pct: null, promo_qty: 0, promo_discount_value: 0, incentive_qty: 0, medie_zilnica: null, medie_produs: null, proc_bon2acc: null, prc_focus_acc_qty: null, return_receipt_count: 0 };
      current.total_vanzari += n(row.total_vanzari);
      current.qty_total += n(row.qty_total);
      current.nr_bonuri += n(row.nr_bonuri);
      current.nr_agenti = Math.max(n(current.nr_agenti), n(row.nr_agenti));
      current.zile_active += n(row.zile_active);
      current.target += n(row.target);
      current.promo_qty += n(row.promo_qty);
      current.promo_discount_value += n(row.promo_discount_value);
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
      const current = map.get(key) ?? { ...row, total_vanzari: 0, qty_total: 0, nr_bonuri: 0, nr_agenti: 0, zile_active: 0, target: 0, proc_realizare_target: null, promo_qty: 0, promo_discount_value: 0, incentive_qty: 0, medie_zilnica: null, medie_produs: null, proc_bon2acc: null, prc_focus_acc_qty: null };
      current.total_vanzari += n(row.total_vanzari);
      current.qty_total += n(row.qty_total);
      current.nr_bonuri += n(row.nr_bonuri);
      current.nr_agenti = Math.max(n(current.nr_agenti), n(row.nr_agenti));
      current.zile_active += n(row.zile_active);
      current.target += n(row.target);
      current.promo_qty += n(row.promo_qty);
      current.promo_discount_value += n(row.promo_discount_value);
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
  const weighted = new Map<string, { bon2: number; focus: number }>();
  for (const group of rows) {
    for (const row of group) {
      const current = map.get(row.site_code) ?? { ...row, import_month: '', total_vanzari: 0, qty_total: 0, nr_bonuri: 0, nr_agenti: 0, zile_active: 0, target: 0, proc_realizare_target: null, forecast_target_pct: null, medie_produs: null, promo_qty: 0, promo_discount_value: 0, incentive_qty: 0, return_receipt_count: 0, proc_bon2acc: null, prc_focus_acc_qty: null };
      current.total_vanzari += n(row.total_vanzari);
      current.qty_total = n(current.qty_total) + n(row.qty_total);
      current.nr_bonuri += n(row.nr_bonuri);
      current.nr_agenti = Math.max(n(current.nr_agenti), n(row.nr_agenti));
      current.zile_active += n(row.zile_active);
      current.target += n(row.target);
      current.promo_qty += n(row.promo_qty);
      current.promo_discount_value += n(row.promo_discount_value);
      current.incentive_qty += n(row.incentive_qty);
      current.return_receipt_count = n(current.return_receipt_count) + n(row.return_receipt_count);
      const currentWeighted = weighted.get(row.site_code) ?? { bon2: 0, focus: 0 };
      currentWeighted.bon2 += (n(row.proc_bon2acc) / 100) * n(row.nr_bonuri);
      currentWeighted.focus += (n(row.prc_focus_acc_qty) / 100) * n(row.qty_total);
      weighted.set(row.site_code, currentWeighted);
      map.set(row.site_code, current);
    }
  }
  return [...map.values()].map((row) => {
    const currentWeighted = weighted.get(row.site_code) ?? { bon2: 0, focus: 0 };
    return {
      ...row,
      total_vanzari: round2(row.total_vanzari),
      target: round2(row.target),
      proc_realizare_target: pct(row.total_vanzari, row.target),
      forecast_target_pct: null,
      medie_produs: n(row.qty_total) > 0 ? round2(row.total_vanzari / n(row.qty_total)) : null,
      proc_bon2acc: pct(currentWeighted.bon2, row.nr_bonuri),
      prc_focus_acc_qty: pct(currentWeighted.focus, n(row.qty_total)),
    };
  });
}

function aggregateAgents(rows: AgentStat[][]): AgentStat[] {
  const map = new Map<string, AgentStat>();
  for (const group of rows) {
    for (const row of group) {
      const key = `${row.site_code}:${row.agent}`;
      const current = map.get(key) ?? { ...row, import_month: '', acc_qty_realizat: 0, nr_bonuri: 0, nr_bon2acc: 0, proc_bon2acc: null, total_vanzari: 0, zile_lucrate: 0, medie_zilnica: null, medie_produs: null, acc_focus_qty: 0, prc_focus_acc_qty: null, target: 0, proc_realizare_target: null, promo_qty: 0, promo_discount_value: 0, incentive_qty: 0, return_receipt_count: 0 };
      current.acc_qty_realizat += n(row.acc_qty_realizat);
      current.nr_bonuri += n(row.nr_bonuri);
      current.nr_bon2acc += n(row.nr_bon2acc);
      current.total_vanzari += n(row.total_vanzari);
      current.zile_lucrate += n(row.zile_lucrate);
      current.acc_focus_qty += n(row.acc_focus_qty);
      current.target = n(current.target) + n(row.target);
      current.promo_qty += n(row.promo_qty);
      current.promo_discount_value += n(row.promo_discount_value);
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
    if (!isSelected && draftSelectedHistoryMonths.length >= MAX_DASHBOARD_BATCH_MONTHS) {
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

  const handleApplyHistoryPreset = useCallback((count: number) => {
    const selected = sortMonthsAsc(months.slice(0, Math.min(count, MAX_DASHBOARD_BATCH_MONTHS)));
    if (selected.length === 0) return;
    setDraftHistoryMonths(selected);
    setHistoryMonths(selected);
    setHistoryMonth(selected[selected.length - 1] ?? currentMonth);
    historyMonthDropdownRef.current?.removeAttribute('open');
  }, [currentMonth, months]);

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
    <div className="space-y-3 p-3 pb-24 pt-2 lg:space-y-4 lg:px-6 lg:py-3 lg:pb-6 xl:px-8">
      <SegmentedTabs<DashboardSection>
        ariaLabel="Secțiuni Sales Hub"
        className="glass"
        options={DASHBOARD_SECTIONS}
        value={activeSection}
        onChange={setActiveSection}
      />

      {activeSection === 'visits' ? (
        <Suspense fallback={<LoadingCard label="Se incarca modulul Vizite..." />}>
          <VisiteSubtab currentMonth={currentMonth} months={months} />
        </Suspense>
      ) : loading ? (
        <LoadingCard label="Se incarca luna in curs..." />
      ) : error || !summary ? (
        <ErrorCard
          message={error ?? 'Datele pentru luna in curs nu au putut fi incarcate.'}
          onRetry={refetchCurrentData}
        />
      ) : activeSection === 'current' ? (
        <CurrentDashboard
          currentMonth={currentMonth}
          filters={filters}
          mode={currentMode}
          onModeChange={setCurrentMode}
          statusLabel={currentStatusLabel}
          summary={summary}
          receiptBucketChartData={receiptBucketChartData}
          focusSubcategoryChartData={focusSubcategoryChartData}
          periodComparison={periodComparison}
          comparisonDeltas={comparisonDeltas}
          dailyChartData={dailyChartData}
          categoryMixChartData={categoryMixChartData}
          brandMixChartData={brandMixChartData}
          filterScopeLabel={filterScopeLabel}
          regionals={regionals}
          sortedRegionals={sortedRegionals}
          regionalColumns={regionalBreakdownColumns(regionalColumnsVisible, openPerformanceDetail)}
          regionalSort={regionalSort}
          onSortRegionals={handleSortRegionals}
          stores={stores}
          sortedStores={sortedStores}
          storeColumns={storeBreakdownColumns(storeColumnsVisible, openPerformanceDetail)}
          storeSort={storeSort}
          onSortStores={handleSortStores}
          agents={agents}
          sortedAgents={sortedAgents}
          agentColumns={agentBreakdownColumns(agentColumnsVisible, openPerformanceDetail)}
          agentSort={agentSort}
          onSortAgents={handleSortAgents}
        />
      ) : (
        <HistoryDashboard
          loading={historyLoading}
          error={historyError}
          onRetry={refetchHistoryData}
          selectedPoint={selectedHistoryPoint}
          currentSummary={summary}
          historySummary={historySummary}
          yearFilter={historyYearFilter}
          onYearFilterChange={setHistoryYearFilter}
          availableYears={availableYears}
          currentHistoryLoading={currentHistoryLoading}
          yearHistoryLoading={yearHistoryLoading}
          currentHistoryChartData={currentHistoryChartData}
          yearHistoryChartData={yearHistoryChartData}
          kpiMetric={kpiMetric}
          onKpiMetricChange={setKpiMetric}
          kpiChartData={kpiChartData}
          includeClosedStores={includeClosedStores}
          onIncludeClosedStoresChange={setIncludeClosedStores}
          dropdownRef={historyMonthDropdownRef}
          onDropdownToggle={handleHistoryDropdownToggle}
          dropdownOpen={historyMonthDropdownOpen}
          draftSelectionLabel={draftHistorySelectionLabel}
          selectionLabel={historySelectionLabel}
          months={months}
          draftSelectedMonths={draftSelectedHistoryMonths}
          onToggleMonth={handleToggleHistoryMonth}
          onApplyMonths={handleApplyHistoryMonths}
          onApplyPreset={handleApplyHistoryPreset}
          historyStatusLabel={historyStatusLabel}
          historyReceiptBucketChartData={historyReceiptBucketChartData}
          historyFocusSubcategoryChartData={historyFocusSubcategoryChartData}
          historyDailyChartData={historyDailyChartData}
          historyCategoryMixChartData={historyCategoryMixChartData}
          historyBrandMixChartData={historyBrandMixChartData}
          selectionSlug={historySelectionSlug}
          regionals={historyRegionals}
          sortedRegionals={sortedHistoryRegionals}
          regionalColumns={regionalBreakdownColumns(HIST_REGIONAL_COLUMNS)}
          regionalSort={historyRegionalSort}
          onSortRegionals={handleSortHistoryRegionals}
          stores={historyStores}
          sortedStores={sortedHistoryStores}
          storeColumns={storeBreakdownColumns(HIST_STORE_COLUMNS)}
          storeSort={historyStoreSort}
          onSortStores={handleSortHistoryStores}
          agents={historyAgents}
          sortedAgents={sortedHistoryAgents}
          agentColumns={agentBreakdownColumns(HIST_AGENT_COLUMNS)}
          agentSort={historyAgentSort}
          onSortAgents={handleSortHistoryAgents}
        />
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
