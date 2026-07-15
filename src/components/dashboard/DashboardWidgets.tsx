import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { AgentStat, AsmStat, PeriodComparisonPoint, RegionalStat, StoreStat } from '../../api/types';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from '../../lib/filterValues';
import { formatAmount, formatCurrency, formatInt, formatPercent } from '../../lib/formatters';
import type { AppFilters } from '../MainLayout';
import { SortableTableHeader } from '../common/TableHeader';

type SortDirection = 'asc' | 'desc';
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
  | 'medie_produs';
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
  | 'prc_focus_acc_qty';
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
  | 'prc_focus_acc_qty';
type AsmSortKey =
  | 'asm'
  | 'regional'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'promo_qty'
  | 'incentive_qty'
  | 'qty_total'
  | 'nr_bonuri'
  | 'medie_zilnica'
  | 'medie_produs'
  | 'proc_bon2acc'
  | 'prc_focus_acc_qty';

type PerformanceTone = {
  label: string;
  cardClass: string;
  badgeClass: string;
};

const PIE_COLORS = ['#4f46e5', '#0f766e', '#d97706', '#dc2626', '#7c3aed', '#475569'];
const KPI_PIE_COLORS = ['#4f46e5', '#22c55e', '#f59e0b', '#ef4444', '#64748b'];

export function Metric({
  label,
  value,
  detail,
  emphasize = false,
  accent = 'slate',
  className = '',
}: {
  label: string;
  value: React.ReactNode;
  detail?: string;
  emphasize?: boolean;
  accent?: 'slate' | 'indigo';
  className?: string;
}) {
  const accentClasses =
    accent === 'indigo'
      ? 'bg-indigo-50/80 dark:bg-indigo-900/20'
      : 'bg-slate-50 dark:bg-slate-800/60';

  return (
    <div className={`rounded-2xl p-3 ${accentClasses} ${emphasize ? 'flex h-full flex-col justify-between' : ''} ${className}`}>
      <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`${emphasize ? 'mt-4 text-[2rem] leading-none' : 'mt-1 text-base leading-tight'} font-black`}>{value ?? '-'}</div>
      {detail ? <div className="mt-2 text-xs leading-relaxed text-slate-500">{detail}</div> : null}
    </div>
  );
}

export function KpiPerformanceCard({
  title,
  value,
  tone,
  chartData,
  dataKey,
  nameKey,
  formatValue,
  className = '',
}: {
  title: string;
  value: number | null;
  tone: PerformanceTone;
  chartData: Array<Record<string, string | number>>;
  dataKey: string;
  nameKey: string;
  formatValue: (value: number) => string;
  className?: string;
}) {
  return (
    <div className={`rounded-3xl border p-2.5 ${tone.cardClass} ${className}`}>
      <div className="mb-1 flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wide opacity-75">{title}</div>
          <div className="mt-0.5 text-[2rem] font-black leading-none">{formatPercent(value)}</div>
        </div>
        <div className="mt-1">
          <span className={`block h-3 w-3 rounded-full ${tone.badgeClass}`} />
        </div>
      </div>
      <DonutLegendChart
        data={chartData}
        dataKey={dataKey}
        nameKey={nameKey}
        colors={KPI_PIE_COLORS}
        valueFormatter={formatValue}
        centerLabel="TOTAL"
        centerValue={formatCompactDonutValue(sumChartValues(chartData, dataKey))}
        compact
      />
    </div>
  );
}

export function CompactPieSection({
  title,
  emptyLabel,
  pieData,
  dataKey,
  nameKey,
  valueFormatter,
  centerValue,
}: {
  title: string;
  emptyLabel: string;
  pieData: Array<Record<string, string | number>>;
  dataKey: string;
  nameKey: string;
  valueFormatter: (value: number) => string;
  centerValue: string;
}) {
  return (
    <div className="rounded-2xl bg-slate-50/80 p-3 dark:bg-slate-800/40">
      <div className="mb-3 text-sm font-bold tracking-wide text-slate-600 dark:text-slate-300">{title}</div>
      {pieData.length === 0 ? (
        <div className="rounded-2xl bg-white/70 p-4 text-xs font-semibold text-slate-500 dark:bg-slate-900/30">
          {emptyLabel}
        </div>
      ) : (
        <DonutLegendChart
          data={pieData}
          dataKey={dataKey}
          nameKey={nameKey}
          colors={PIE_COLORS}
          valueFormatter={valueFormatter}
          centerLabel="TOTAL"
          centerValue={centerValue}
          sideBySide
        />
      )}
    </div>
  );
}

function DonutLegendChart({
  data,
  dataKey,
  nameKey,
  colors,
  valueFormatter,
  centerLabel,
  centerValue,
  compact = false,
  sideBySide = false,
}: {
  data: Array<Record<string, string | number>>;
  dataKey: string;
  nameKey: string;
  colors: string[];
  valueFormatter: (value: number) => string;
  centerLabel: string;
  centerValue: string;
  compact?: boolean;
  sideBySide?: boolean;
}) {
  const legendRows = data.slice(0, 6);
  const layoutClass = sideBySide
    ? 'grid-cols-[minmax(0,180px)_minmax(0,1fr)]'
    : compact
      ? 'lg:grid-cols-[minmax(0,160px)_minmax(0,1fr)]'
      : 'lg:grid-cols-[minmax(0,190px)_minmax(0,1fr)]';

  return (
    <div className={`grid gap-1.5 ${layoutClass} items-center`}>
      <div className={`mx-auto w-full ${compact ? 'h-36 max-w-45' : 'h-48 max-w-55'}`}>
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
          <PieChart>
            <Pie
              data={data}
              dataKey={dataKey}
              nameKey={nameKey}
              innerRadius={compact ? 40 : 46}
              outerRadius={compact ? 66 : 78}
              paddingAngle={2}
              stroke="transparent"
            >
              {data.map((entry, index) => (
                <Cell key={`${entry[nameKey]}-${index}`} fill={colors[index % colors.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(value: number) => valueFormatter(Number(value))} />
            <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle">
              <tspan x="50%" dy="-0.9em" className={`fill-slate-500 font-bold uppercase tracking-wide ${compact ? 'text-[10px]' : 'text-[11px]'}`}>
                {centerLabel}
              </tspan>
              <tspan x="50%" dy="1.2em" className={`fill-slate-900 font-black dark:fill-slate-100 ${compact ? 'text-[18px]' : 'text-[20px]'}`}>
                {centerValue}
              </tspan>
            </text>
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className={sideBySide ? 'space-y-0' : compact ? 'space-y-0.5' : 'space-y-2'}>
        {legendRows.map((item, index) => (
          <div
            key={`${String(item[nameKey])}-${index}`}
            className={`flex items-center justify-between gap-2 text-xs dark:bg-slate-900/30 ${
              sideBySide
                ? 'border-b border-slate-200/70 py-2 last:border-b-0'
                : compact
                  ? 'rounded-2xl bg-white/70 px-2.5 py-0.5'
                  : 'rounded-2xl bg-white/70 px-3 py-2'
            }`}
          >
            <div className="flex min-w-0 items-center gap-2">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: colors[index % colors.length] }}
              />
              <span className="text-[11px] font-semibold text-slate-500">
                {formatPercent(Number(item.share_pct ?? 0))}
              </span>
              <span className="font-bold">{valueFormatter(Number(item[dataKey] ?? 0))}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PeriodTable({
  current,
  previous,
  yoy,
}: {
  current: PeriodComparisonPoint;
  previous: PeriodComparisonPoint;
  yoy: PeriodComparisonPoint;
}) {
  const points = [current, previous, yoy];
  const rows: { label: string; fn: (p: PeriodComparisonPoint) => string }[] = [
    { label: 'Vanzari',      fn: (p) => formatAmount(p.total_sales) },
    { label: 'Cantitate',    fn: (p) => formatInt(p.total_quantity) },
    { label: 'Bonuri',       fn: (p) => formatInt(p.total_receipts) },
    { label: 'Zile',         fn: (p) => formatInt(p.working_days) },
    { label: 'Med. zilnica', fn: (p) => formatAmount(p.daily_average ?? 0) },
    { label: 'Med. produs',  fn: (p) => formatAmount(p.medie_produs ?? 0) },
    { label: 'Med. bon',     fn: (p) => formatAmount(p.avg_receipt_value ?? 0) },
    { label: 'Bon2Acc',      fn: (p) => formatPercent(p.proc_bon2acc) },
    { label: 'Focus/Acc',    fn: (p) => formatPercent(p.prc_focus_acc_qty) },
    { label: 'Cartele',      fn: (p) => formatInt(p.cartele_qty ?? 0) },
  ];

  return (
    <div className="w-full overflow-hidden rounded-2xl bg-slate-50 dark:bg-slate-800/50">
      <table className="w-full table-fixed text-[11px]">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-700">
            <th className="py-2 pl-3 pr-2 text-left font-semibold text-slate-400 w-[22%]" />
            {points.map((p) => (
              <th key={p.label} className="py-2 px-2 text-center w-[26%]">
                <div className="font-bold text-slate-700 dark:text-slate-200">{p.label}</div>
                <div className="text-[10px] font-normal text-slate-400">{p.month}</div>
                <div className="text-[10px] font-normal text-slate-400">{p.day_range}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={row.label}
              className={i % 2 === 0 ? 'bg-white/60 dark:bg-slate-900/20' : ''}
            >
              <td className="py-1.5 pl-3 pr-2 text-slate-500 font-medium truncate">{row.label}</td>
              {points.map((p) => (
                <td key={p.label} className="py-1.5 px-3 text-center font-semibold text-slate-700 dark:text-slate-200 tabular-nums">
                  {row.fn(p)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function deltaBadgeClass(positive: boolean) {
  return positive
    ? 'bg-emerald-600/20 text-emerald-800 dark:bg-emerald-400/20 dark:text-emerald-200'
    : 'bg-rose-600/20 text-rose-800 dark:bg-rose-400/20 dark:text-rose-200';
}

function DeltaPctBadge({ pct, positive }: { pct: number; positive: boolean }) {
  return (
    <span className={`shrink-0 inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold ${deltaBadgeClass(positive)}`}>
      {pct > 0 ? '+' : ''}{pct}%
    </span>
  );
}

export function DeltaCard({
  title,
  salesDelta,
  salesPct,
  receiptsDelta,
  receiptsPct,
  quantityDelta,
  quantityPct,
}: {
  title: string;
  salesDelta: number;
  salesPct?: number | null;
  receiptsDelta: number;
  receiptsPct?: number | null;
  quantityDelta: number;
  quantityPct?: number | null;
}) {
  const salesPositive = salesDelta >= 0;
  const receiptsPositive = receiptsDelta >= 0;
  const quantityPositive = quantityDelta >= 0;
  const tone = salesPositive
    ? 'border-emerald-200 bg-emerald-50/80 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-300'
    : 'border-rose-200 bg-rose-50/80 text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-300';

  return (
    <div className={`rounded-2xl border p-3 ${tone}`}>
      <div className="mb-3 text-[11px] font-bold uppercase tracking-wide">{title}</div>
      <div className="space-y-2">
        <div>
          <div className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide">
            <span className="text-base font-normal leading-none">Δ</span>
            <span className="opacity-60">vanzari</span>
          </div>
          <div className="mt-1 flex items-center gap-2 min-w-0">
            <span className="text-base font-black tabular-nums truncate">{formatDeltaCurrency(salesDelta)}</span>
            {salesPct != null && <DeltaPctBadge pct={salesPct} positive={salesPositive} />}
          </div>
        </div>
        <div>
          <div className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide">
            <span className="text-base font-normal leading-none">Δ</span>
            <span className="opacity-60">bonuri</span>
          </div>
          <div className="mt-1 flex items-center gap-2 min-w-0">
            <span className="text-base font-black tabular-nums truncate">{formatDeltaInt(receiptsDelta)}</span>
            {receiptsPct != null && <DeltaPctBadge pct={receiptsPct} positive={receiptsPositive} />}
          </div>
        </div>
        <div>
          <div className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide">
            <span className="text-base font-normal leading-none">Δ</span>
            <span className="opacity-60">cantitate</span>
          </div>
          <div className="mt-1 flex items-center gap-2 min-w-0">
            <span className="text-base font-black tabular-nums truncate">{formatDeltaInt(quantityDelta)}</span>
            {quantityPct != null && <DeltaPctBadge pct={quantityPct} positive={quantityPositive} />}
          </div>
        </div>
      </div>
    </div>
  );
}

export function SortableHeader({
  label,
  active,
  direction,
  onClick,
  className = '',
  title,
  align = 'left',
}: {
  label: string;
  active: boolean;
  direction: SortDirection;
  onClick: () => void;
  className?: string;
  title?: string;
  align?: 'left' | 'right';
}) {
  return (
    <SortableTableHeader
      label={label}
      active={active}
      direction={direction}
      onClick={onClick}
      className={className}
      title={title}
      align={align}
    />
  );
}

function formatDeltaCurrency(value: number) {
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${formatAmount(value)}`;
}

function formatDeltaInt(value: number) {
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${formatInt(value)}`;
}

export function CompactCurrency({ value }: { value: number }) {
  const formatted = formatCurrency(value);
  const amount = formatted.replace(/\s[A-Z]{3}$/, '');

  return <span>{amount}</span>;
}

export function getAgentSortValue(agent: AgentStat, key: AgentSortKey): number {
  const value = agent[key];
  if (value === null || value === undefined) {
    return Number.NEGATIVE_INFINITY;
  }
  const num = Number(value);
  return Number.isNaN(num) ? Number.NEGATIVE_INFINITY : num;
}

export function getStoreDailyAverage(store: StoreStat): number {
  if (!store.zile_active) {
    return 0;
  }
  return Number(store.total_vanzari) / Number(store.zile_active);
}

export function getStoreSortValue(store: StoreStat, key: StoreSortKey): number {
  if (key === 'medie_zilnica') {
    return getStoreDailyAverage(store);
  }
  const value = store[key];
  if (value === null || value === undefined) {
    return Number.NEGATIVE_INFINITY;
  }
  const num = Number(value);
  return Number.isNaN(num) ? Number.NEGATIVE_INFINITY : num;
}

export function getRegionalSortValue(regional: RegionalStat, key: RegionalSortKey): number {
  const value = regional[key];
  if (value === null || value === undefined) {
    return Number.NEGATIVE_INFINITY;
  }
  const num = Number(value);
  return Number.isNaN(num) ? Number.NEGATIVE_INFINITY : num;
}

export function getAsmSortValue(asm: AsmStat, key: AsmSortKey): number {
  const value = asm[key];
  if (value === null || value === undefined) {
    return Number.NEGATIVE_INFINITY;
  }
  const num = Number(value);
  return Number.isNaN(num) ? Number.NEGATIVE_INFINITY : num;
}

export function sumChartValues(rows: Array<Record<string, string | number>>, key: string): number {
  return rows.reduce((total, row) => total + Number(row[key] ?? 0), 0);
}

export function formatCompactDonutValue(value: number): string {
  return new Intl.NumberFormat('ro-RO', {
    notation: 'compact',
    maximumFractionDigits: value >= 1000000 ? 1 : 0,
  }).format(value);
}

export function describeFilterScope(filters: AppFilters): string {
  if (filters.agent !== ALL_SCOPE) {
    const agents = filters.agent.split(',').filter(Boolean);
    return agents.length > 1 ? `${agents.length} agenti selectati` : `Agent ${filters.agent}`;
  }
  if (filters.magazin !== ALL_STORES) {
    const stores = filters.magazin.split(',').filter(Boolean);
    return stores.length > 1 ? `${stores.length} magazine selectate` : `Magazin ${filters.magazin}`;
  }
  if (filters.rm !== ALL_SCOPE) {
    return `Regional ${filters.rm}`;
  }
  if (filters.firma !== ALL_FIRMS) {
    return `Firma ${filters.firma}`;
  }
  return 'Toata selectia activa';
}

export function getBon2AccTone(value: number): PerformanceTone {
  if (value >= 31) {
    return {
      label: 'Foarte bun',
      cardClass: 'border-emerald-200 bg-emerald-50/80 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-200',
      badgeClass: 'bg-emerald-500 dark:bg-emerald-400',
    };
  }
  if (value >= 30) {
    return {
      label: 'Solid',
      cardClass: 'border-lime-200 bg-lime-50/80 text-lime-800 dark:border-lime-900/40 dark:bg-lime-950/20 dark:text-lime-200',
      badgeClass: 'bg-lime-500 dark:bg-lime-400',
    };
  }
  if (value >= 28) {
    return {
      label: 'Atentie',
      cardClass: 'border-amber-200 bg-amber-50/80 text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200',
      badgeClass: 'bg-amber-500 dark:bg-amber-400',
    };
  }
  return {
    label: 'Critic',
    cardClass: 'border-rose-200 bg-rose-50/80 text-rose-800 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200',
    badgeClass: 'bg-rose-500 dark:bg-rose-400',
  };
}

export function getFocusTone(value: number): PerformanceTone {
  if (value >= 8) {
    return {
      label: 'Foarte bun',
      cardClass: 'border-emerald-200 bg-emerald-50/80 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-200',
      badgeClass: 'bg-emerald-500 dark:bg-emerald-400',
    };
  }
  if (value >= 7) {
    return {
      label: 'In target',
      cardClass: 'border-lime-200 bg-lime-50/80 text-lime-800 dark:border-lime-900/40 dark:bg-lime-950/20 dark:text-lime-200',
      badgeClass: 'bg-lime-500 dark:bg-lime-400',
    };
  }
  if (value >= 6) {
    return {
      label: 'Sub tinta',
      cardClass: 'border-amber-200 bg-amber-50/80 text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200',
      badgeClass: 'bg-amber-500 dark:bg-amber-400',
    };
  }
  return {
    label: 'Critic',
    cardClass: 'border-rose-200 bg-rose-50/80 text-rose-800 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200',
    badgeClass: 'bg-rose-500 dark:bg-rose-400',
  };
}

export function LoadingCard({ label }: { label: string }) {
  return (
    <div className="glass flex flex-col items-center justify-center gap-3 rounded-3xl p-8">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-200 border-t-indigo-600" />
      <div className="text-sm font-medium text-slate-500">{label}</div>
    </div>
  );
}

export function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="glass flex flex-col items-center gap-4 rounded-3xl p-6">
      <div className="flex items-center gap-2 text-amber-600">
        <AlertCircle className="h-5 w-5" />
        <span className="text-sm font-medium">{message}</span>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-indigo-700"
      >
        <RefreshCw className="h-4 w-4" />
        Reincearca
      </button>
    </div>
  );
}
