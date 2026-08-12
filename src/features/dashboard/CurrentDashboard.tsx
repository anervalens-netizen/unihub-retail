import type { AgentStat, DashboardSummary, PeriodComparisonPayload, RegionalStat, StoreStat } from '../../api/generated/runtime-types';
import type { AppFilters } from '../../lib/appFilters';
import { AiForecastPanel } from '../ai-forecast/AiForecastPage';
import { SegmentedTabs } from '../../components/common/SegmentedTabs';
import type { BreakdownColumn } from './BreakdownTable';
import { CurrentOverview } from './CurrentDashboardSections';

export type CurrentDashboardMode = 'overview' | 'forecast';
export interface ComparisonDeltas {
  previousSales: number; previousSalesPct: number | null;
  previousReceipts: number; previousReceiptsPct: number | null;
  previousQuantity: number; previousQuantityPct: number | null;
  yearSales: number; yearSalesPct: number | null;
  yearReceipts: number; yearReceiptsPct: number | null;
  yearQuantity: number; yearQuantityPct: number | null;
}
interface DailyChartPoint { day: string; sales: number | null; qty: number | null; receipts: number | null; sales_last_year: number | null; sales_forecast: number | null; }
interface MixChartPoint extends Record<string, string | number> { sales_total: number; share_pct: number; }
interface CategoryMixChartPoint extends MixChartPoint { category: string; quantity_total: number; }
interface BrandMixChartPoint extends MixChartPoint { brand: string; }
interface ReceiptBucketChartPoint extends Record<string, string | number> { bucket: string; receipt_count: number; share_pct: number; }
interface FocusChartPoint extends Record<string, string | number> { category: string; quantity_total: number; share_pct: number; }
interface SortState<Key extends string> { key: Key; direction: 'asc' | 'desc'; }

export interface CurrentDashboardProps<RegionalKey extends string, StoreKey extends string, AgentKey extends string> {
  currentMonth: string; filters: AppFilters; mode: CurrentDashboardMode;
  onModeChange: (mode: CurrentDashboardMode) => void; statusLabel: string;
  summary: DashboardSummary; receiptBucketChartData: ReceiptBucketChartPoint[];
  focusSubcategoryChartData: FocusChartPoint[]; periodComparison: PeriodComparisonPayload | null;
  comparisonDeltas: ComparisonDeltas | null; dailyChartData: DailyChartPoint[];
  categoryMixChartData: CategoryMixChartPoint[]; brandMixChartData: BrandMixChartPoint[];
  filterScopeLabel: string; regionals: RegionalStat[]; sortedRegionals: RegionalStat[];
  regionalColumns: BreakdownColumn<RegionalStat, RegionalKey>[]; regionalSort: SortState<RegionalKey>;
  onSortRegionals: (key: RegionalKey) => void; stores: StoreStat[]; sortedStores: StoreStat[];
  storeColumns: BreakdownColumn<StoreStat, StoreKey>[]; storeSort: SortState<StoreKey>;
  onSortStores: (key: StoreKey) => void; agents: AgentStat[]; sortedAgents: AgentStat[];
  agentColumns: BreakdownColumn<AgentStat, AgentKey>[]; agentSort: SortState<AgentKey>;
  onSortAgents: (key: AgentKey) => void;
}

export function CurrentDashboard<R extends string, S extends string, A extends string>(model: CurrentDashboardProps<R, S, A>) {
  return <>
    <SegmentedTabs ariaLabel="Mod analiză lună curentă" level="secondary" options={[{ value: 'overview', label: 'Overview' }, { value: 'forecast', label: 'AI Forecast' }]} value={model.mode} onChange={model.onModeChange} />
    {model.mode === 'forecast' ? <AiForecastPanel currentMonth={model.currentMonth} filters={model.filters} /> : <CurrentOverview model={model} />}
  </>;
}
