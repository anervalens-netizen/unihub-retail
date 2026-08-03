import { Building2, CalendarRange, PieChart as PieChartIcon, Users } from 'lucide-react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { AgentStat, DashboardSummary, PeriodComparisonPayload, RegionalStat, StoreStat } from '../../api/types';
import type { AppFilters } from '../MainLayout';
import { AiForecastPanel } from '../AiForecastPanel';
import { SegmentedTabs } from '../common/SegmentedTabs';
import { formatAmount, formatInt, formatPercent } from '../../lib/formatters';
import { BreakdownTable, type BreakdownColumn } from './BreakdownTable';
import {
  CompactCurrency,
  CompactPieSection,
  DeltaCard,
  KpiPerformanceCard,
  Metric,
  PeriodTable,
  formatCompactDonutValue,
  getBon2AccTone,
  getFocusTone,
  sumChartValues,
} from './DashboardWidgets';

export type CurrentDashboardMode = 'overview' | 'forecast';

export interface ComparisonDeltas {
  previousSales: number;
  previousSalesPct: number | null;
  previousReceipts: number;
  previousReceiptsPct: number | null;
  previousQuantity: number;
  previousQuantityPct: number | null;
  yearSales: number;
  yearSalesPct: number | null;
  yearReceipts: number;
  yearReceiptsPct: number | null;
  yearQuantity: number;
  yearQuantityPct: number | null;
}

interface DailyChartPoint {
  day: string;
  sales: number | null;
  qty: number | null;
  receipts: number | null;
  sales_last_year: number | null;
  sales_forecast: number | null;
}

interface MixChartPoint extends Record<string, string | number> {
  sales_total: number;
  share_pct: number;
}

interface CategoryMixChartPoint extends MixChartPoint {
  category: string;
  quantity_total: number;
}

interface BrandMixChartPoint extends MixChartPoint {
  brand: string;
}

interface ReceiptBucketChartPoint extends Record<string, string | number> {
  bucket: string;
  receipt_count: number;
  share_pct: number;
}

interface FocusChartPoint extends Record<string, string | number> {
  category: string;
  quantity_total: number;
  share_pct: number;
}

interface SortState<Key extends string> {
  key: Key;
  direction: 'asc' | 'desc';
}

interface CurrentDashboardProps<RegionalKey extends string, StoreKey extends string, AgentKey extends string> {
  currentMonth: string;
  filters: AppFilters;
  mode: CurrentDashboardMode;
  onModeChange: (mode: CurrentDashboardMode) => void;
  statusLabel: string;
  summary: DashboardSummary;
  receiptBucketChartData: ReceiptBucketChartPoint[];
  focusSubcategoryChartData: FocusChartPoint[];
  periodComparison: PeriodComparisonPayload | null;
  comparisonDeltas: ComparisonDeltas | null;
  dailyChartData: DailyChartPoint[];
  categoryMixChartData: CategoryMixChartPoint[];
  brandMixChartData: BrandMixChartPoint[];
  filterScopeLabel: string;
  regionals: RegionalStat[];
  sortedRegionals: RegionalStat[];
  regionalColumns: BreakdownColumn<RegionalStat, RegionalKey>[];
  regionalSort: SortState<RegionalKey>;
  onSortRegionals: (key: RegionalKey) => void;
  stores: StoreStat[];
  sortedStores: StoreStat[];
  storeColumns: BreakdownColumn<StoreStat, StoreKey>[];
  storeSort: SortState<StoreKey>;
  onSortStores: (key: StoreKey) => void;
  agents: AgentStat[];
  sortedAgents: AgentStat[];
  agentColumns: BreakdownColumn<AgentStat, AgentKey>[];
  agentSort: SortState<AgentKey>;
  onSortAgents: (key: AgentKey) => void;
}

export function CurrentDashboard<RegionalKey extends string, StoreKey extends string, AgentKey extends string>({
  currentMonth,
  filters,
  mode,
  onModeChange,
  statusLabel,
  summary,
  receiptBucketChartData,
  focusSubcategoryChartData,
  periodComparison,
  comparisonDeltas,
  dailyChartData,
  categoryMixChartData,
  brandMixChartData,
  filterScopeLabel,
  regionals,
  sortedRegionals,
  regionalColumns,
  regionalSort,
  onSortRegionals,
  stores,
  sortedStores,
  storeColumns,
  storeSort,
  onSortStores,
  agents,
  sortedAgents,
  agentColumns,
  agentSort,
  onSortAgents,
}: CurrentDashboardProps<RegionalKey, StoreKey, AgentKey>) {
  return (
    <>
      <SegmentedTabs
        ariaLabel="Mod analiză lună curentă"
        className="glass"
        options={[
          { value: 'overview', label: 'Overview' },
          { value: 'forecast', label: 'AI Forecast' },
        ]}
        value={mode}
        onChange={onModeChange}
      />

      {mode === 'forecast' ? (
        <AiForecastPanel currentMonth={currentMonth} filters={filters} />
      ) : (
        <>
          <div className="glass space-y-4 rounded-3xl p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="truncate text-sm font-bold">Overview — {currentMonth}</h3>
                <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">{statusLabel}</p>
              </div>
              <span className="shrink-0 rounded-xl bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {summary.last_sale_date ?? '-'}
              </span>
            </div>

            <div className="grid gap-3 xl:grid-cols-12 xl:items-start">
              <div className="space-y-3 xl:col-span-7">
            <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/50">
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
              <div className="relative h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-indigo-200 dark:bg-indigo-700"
                  style={{ width: `${Math.min(Number(summary.forecast_target_progress_pct ?? 0), 100)}%` }}
                />
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-indigo-600"
                  style={{ width: `${Math.min(Number(summary.target_progress_pct ?? 0), 100)}%` }}
                />
              </div>
              <div className="mt-1.5 flex justify-between text-[10px] font-semibold">
                <span className="text-indigo-600">Actual {formatPercent(summary.target_progress_pct)}</span>
                <span className="text-slate-600 dark:text-slate-300">Forecast {formatPercent(summary.forecast_target_progress_pct)}</span>
              </div>
            </div>

            <div className="grid grid-cols-4 gap-2 lg:grid-cols-8">
              <Metric label="Bonuri" value={formatInt(summary.total_receipts)} className="p-2" />
              <Metric label="Accesorii nete" value={formatInt(summary.total_quantity)} className="p-2" />
              <Metric
                label="Magazine / Agenți"
                value={<span className="flex items-baseline gap-1.5"><span>{formatInt(summary.total_stores)}</span><span className="text-slate-300 dark:text-slate-600">/</span><span>{formatInt(summary.total_agents)}</span></span>}
                className="p-2"
              />
              <Metric label="Zile lucrate" value={formatInt(summary.working_days)} className="p-2" />
              <Metric label="Med. zilnica" value={formatAmount(summary.daily_average ?? 0)} className="p-2" />
              <Metric label="Medie produs" value={formatAmount(summary.medie_produs ?? 0)} className="p-2" />
              <Metric label="Val. medie bon" value={formatAmount(summary.total_receipts > 0 ? Number(summary.total_sales) / Number(summary.total_receipts) : 0)} className="p-2" />
              <Metric label="Cartele" value={formatInt(summary.cartele_qty ?? 0)} className="p-2" />
            </div>              </div>
            <div className="grid grid-cols-2 gap-2.5 xl:col-span-5">
              <KpiPerformanceCard
                title="Bonuri cu accesorii"
                value={summary.proc_bon2acc}
                tone={getBon2AccTone(Number(summary.proc_bon2acc ?? 0))}
                chartData={receiptBucketChartData}
                dataKey="receipt_count"
                nameKey="bucket"
                formatValue={formatInt}
              />
              <KpiPerformanceCard
                title="Pondere produse Focus"
                value={summary.prc_focus_acc_qty}
                tone={getFocusTone(Number(summary.prc_focus_acc_qty ?? 0))}
                chartData={focusSubcategoryChartData}
                dataKey="quantity_total"
                nameKey="category"
                formatValue={formatInt}
              />
            </div>

            </div>
          </div>

          <div className="glass min-w-0 overflow-hidden rounded-3xl p-4">
              <div className="mb-4 flex items-center gap-2">
                <CalendarRange size={16} className="text-indigo-500" />
                <h3 className="text-sm font-bold">Comparatie perioade</h3>
              </div>
              {!periodComparison || !comparisonDeltas ? (
                <div className="text-xs text-slate-500">Date indisponibile pentru comparatia de perioade.</div>
              ) : (
                <div className="grid gap-3 xl:grid-cols-12 xl:items-stretch">
                  <div className="min-w-0 xl:col-span-9">
                    <PeriodTable current={periodComparison.current} previous={periodComparison.previous} yoy={periodComparison.year_over_year} />
                  </div>
                  <div className="grid grid-cols-2 gap-3 xl:col-span-3 xl:grid-cols-1">
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

          <div className="grid items-start gap-3 lg:grid-cols-[1.2fr_1fr]">
            <div className="glass self-start rounded-3xl p-4">
              <div className="mb-3 flex items-center gap-2">
                <CalendarRange size={16} className="text-indigo-500" />
                <h3 className="text-sm font-bold">Evolutie zilnica pentru {currentMonth}</h3>
              </div>
              <div className="h-64 rounded-2xl bg-slate-50/80 p-2 dark:bg-slate-800/40">
                <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                  <ComposedChart data={dailyChartData}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                    <XAxis dataKey="day" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(value: number, _name: string) => formatAmount(value)} />
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

          <div className="space-y-3">
            <div className="min-w-0">
              <BreakdownTable
            title="RM — Regional Manager"
            icon={<Users size={16} className="text-indigo-500" />}
            subtitle={`Filtrare: ${filterScopeLabel} · Sortare: ${regionalColumns.find((column) => column.key === regionalSort.key)?.label} (${regionalSort.direction}) · ${regionals.length} regionale`}
            rows={sortedRegionals}
            columns={regionalColumns}
            sortKey={regionalSort.key}
            sortDirection={regionalSort.direction}
            onSort={onSortRegionals}
            rowKey={(row) => row.regional}
            exportFilename={`hub_${currentMonth}_rm`}
            exportSheetName={`RM ${currentMonth}`}
            exportColumns={[
              { header: 'Regional', value: (row) => row.regional },
              { header: 'Target', value: (row) => row.target, format: 'currency' },
              { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' },
              { header: 'Procent', value: (row) => row.proc_realizare_target, format: 'percentPoints' },
              { header: 'Forecast%', value: (row) => row.forecast_target_pct, format: 'percentPoints' },
              { header: 'Promo buc.', value: (row) => row.promo_qty, format: 'integer' },
              { header: 'Discount promo', value: (row) => row.promo_discount_value, format: 'currency' },
              { header: 'Cantitate', value: (row) => row.qty_total, format: 'integer' },
              { header: 'Medie produs', value: (row) => row.medie_produs, format: 'currency' },
              { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' },
              { header: 'ProcBon2Acc', value: (row) => row.proc_bon2acc, format: 'percentPoints' },
              { header: 'Focus%', value: (row) => row.prc_focus_acc_qty, format: 'percentPoints' },
            ]}
              />
            </div>
            <div className="min-w-0">
              <BreakdownTable
            title="Magazine"
            icon={<Building2 size={16} className="text-indigo-500" />}
            subtitle={`Filtrare: ${filterScopeLabel} · Sortare: ${storeColumns.find((column) => column.key === storeSort.key)?.label} (${storeSort.direction}) · ${stores.length} magazine`}
            rows={sortedStores}
            columns={storeColumns}
            sortKey={storeSort.key}
            sortDirection={storeSort.direction}
            onSort={onSortStores}
            rowKey={(row) => row.site_code}
            exportFilename={`hub_${currentMonth}_magazine`}
            exportSheetName={`Magazine ${currentMonth}`}
            exportColumns={[
              { header: 'Firma', value: (row) => row.firma },
              { header: 'Magazin', value: (row) => row.locatie },
              { header: 'Target', value: (row) => row.target, format: 'currency' },
              { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' },
              { header: 'Procent', value: (row) => row.proc_realizare_target, format: 'percentPoints' },
              { header: 'Forecast%', value: (row) => row.forecast_target_pct, format: 'percentPoints' },
              { header: 'Promo buc.', value: (row) => row.promo_qty, format: 'integer' },
              { header: 'Discount promo', value: (row) => row.promo_discount_value, format: 'currency' },
              { header: 'Cantitate', value: (row) => row.qty_total, format: 'integer' },
              { header: 'Medie produs', value: (row) => row.medie_produs, format: 'currency' },
              { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' },
              { header: 'ProcBon2Acc', value: (row) => row.proc_bon2acc, format: 'percentPoints' },
              { header: 'Focus%', value: (row) => row.prc_focus_acc_qty, format: 'percentPoints' },
              { header: 'Retururi', value: (row) => row.return_receipt_count, format: 'integer' },
              { header: 'Agenti', value: (row) => row.nr_agenti, format: 'integer' },
              { header: 'Zile active', value: (row) => row.zile_active, format: 'integer' },
            ]}
              />
            </div>
          <BreakdownTable
            title="Agenti - Toti agentii"
            subtitle={`Filtrare: ${filterScopeLabel} · Sortare: ${agentColumns.find((column) => column.key === agentSort.key)?.label} (${agentSort.direction}) · ${agents.length} agenti`}
            rows={sortedAgents}
            columns={agentColumns}
            sortKey={agentSort.key}
            sortDirection={agentSort.direction}
            onSort={onSortAgents}
            rowKey={(row) => `${row.agent}-${row.site_code}`}
            exportFilename={`hub_${currentMonth}_agenti`}
            exportSheetName={`Agenti ${currentMonth}`}
            exportColumns={[
              { header: 'Agent', value: (row) => row.agent },
              { header: 'Firma', value: (row) => row.firma },
              { header: 'Magazin', value: (row) => row.locatie },
              { header: 'Target', value: (row) => row.target, format: 'currency' },
              { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' },
              { header: 'Procent', value: (row) => row.proc_realizare_target, format: 'percentPoints' },
              { header: 'Promo buc.', value: (row) => row.promo_qty, format: 'integer' },
              { header: 'Discount promo', value: (row) => row.promo_discount_value, format: 'currency' },
              { header: 'Cantitate', value: (row) => row.acc_qty_realizat, format: 'integer' },
              { header: 'Medie produs', value: (row) => row.medie_produs, format: 'currency' },
              { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' },
              { header: 'ProcBon2Acc', value: (row) => row.proc_bon2acc, format: 'percentPoints' },
              { header: 'Focus%', value: (row) => row.prc_focus_acc_qty, format: 'percentPoints' },
              { header: 'Retururi', value: (row) => row.return_receipt_count, format: 'integer' },
              { header: 'Zile lucrate', value: (row) => row.zile_lucrate, format: 'integer' },
              { header: 'Medie zilnica', value: (row) => row.medie_zilnica, format: 'currency' },
            ]}
          />
          </div>
        </>
      )}
    </>
  );
}
