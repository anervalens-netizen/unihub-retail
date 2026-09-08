import { Building2, CalendarRange, MapPin, PieChart as PieChartIcon } from 'lucide-react';
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { ChartFrame } from '../../components/common/ChartFrame';
import { DataGrid } from '../../components/common/DataGrid';
import { formatAmount, formatInt } from '../../lib/formatters';
import { BreakdownTable } from './BreakdownTable';
import { CompactPieSection, formatCompactAxisValue, formatCompactDonutValue, sumChartValues } from './DashboardWidgets';
import type { HistoryDashboardProps } from './HistoryDashboard';
import { historyRegionalDataGridColumns } from './historyRegionalDataGrid';
import {
  historyStoreDataGridColumns,
  historyStoreLegacyExportColumns,
} from './historyStoreDataGrid';

type DetailProps = Pick<HistoryDashboardProps<string, string, string>,
  'selectionLabel' | 'historyDailyChartData' | 'historyCategoryMixChartData' | 'historyBrandMixChartData'>;

export function HistoryDetailCharts({ props, visible }: { props: DetailProps; visible: boolean }) {
  return <div className={`grid min-w-0 items-stretch gap-3 min-[1500px]:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)] ${!visible ? 'hidden lg:grid' : ''}`}>
    <ChartFrame
      title={<>Evolutie zilnica pentru {props.selectionLabel}</>}
      icon={<CalendarRange size={16} className="text-indigo-500" />}
      contentClassName="-mx-2 aspect-[16/6] min-h-56 max-h-72 w-auto rounded-xl bg-slate-50/80 p-0.5 sm:mx-0 sm:w-full sm:rounded-2xl sm:p-2 dark:bg-slate-800/40 min-[1500px]:aspect-auto min-[1500px]:min-h-[24rem] min-[1500px]:max-h-none min-[1500px]:flex-1"
      className="flex min-w-0 flex-col"
      compactMobile
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}><ComposedChart data={props.historyDailyChartData} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
        <XAxis dataKey="day" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis yAxisId="sales" width={38} tick={{ fontSize: 10 }} tickFormatter={formatCompactAxisValue} axisLine={false} tickLine={false} />
        <YAxis yAxisId="qty" width={30} orientation="right" tick={{ fontSize: 10 }} tickFormatter={formatCompactAxisValue} axisLine={false} tickLine={false} />
        <Tooltip formatter={(value: unknown, name: unknown) => String(name) === 'Vanzari' ? formatAmount(Number(value)) : formatInt(Number(value))} />
        <Legend /><Bar yAxisId="sales" dataKey="sales" name="Vanzari" fill="#4f46e5" radius={[8, 8, 0, 0]} /><Line yAxisId="qty" type="monotone" dataKey="qty" name="Cantitate" stroke="#f59e0b" strokeWidth={2} dot={false} />
      </ComposedChart></ResponsiveContainer>
    </ChartFrame>
    <ChartFrame
      title="Top categorii si branduri"
      icon={<PieChartIcon size={16} className="text-indigo-500" />}
      contentClassName="grid min-w-0 flex-1 gap-2 min-[1500px]:grid-rows-2"
      className="flex min-w-0 flex-col"
      compactMobile
    >
      <CompactPieSection title="Top categorii" emptyLabel="Nu exista categorii disponibile pentru filtrarea curenta." pieData={props.historyCategoryMixChartData} dataKey="sales_total" nameKey="category" valueFormatter={formatAmount} centerValue={formatCompactDonutValue(sumChartValues(props.historyCategoryMixChartData, 'sales_total'))} compact />
      <CompactPieSection title="Branduri compatibile" emptyLabel="Nu exista date pentru brandurile urmarite." pieData={props.historyBrandMixChartData} dataKey="sales_total" nameKey="brand" valueFormatter={formatAmount} centerValue={formatCompactDonutValue(sumChartValues(props.historyBrandMixChartData, 'sales_total'))} compact />
    </ChartFrame>
  </div>;
}

export function HistoryBreakdowns<RegionalKey extends string, StoreKey extends string, AgentKey extends string>({
  props, visible,
}: { props: HistoryDashboardProps<RegionalKey, StoreKey, AgentKey>; visible: boolean }) {
  const regionalGridColumns = historyRegionalDataGridColumns(props.regionalColumns);
  const storeGridColumns = historyStoreDataGridColumns(props.storeColumns);
  return <div className={!visible ? 'hidden lg:contents' : 'contents'}><div className="space-y-3">
    <div className="min-w-0"><DataGrid title="RM" icon={<MapPin size={16} className="text-indigo-500" />} subtitle="Filtre pe coloane · Shift+click pentru sortare multiplă" rows={props.regionals} columns={regionalGridColumns} initialSort={props.regionalGridSorts} onSortChange={props.onRegionalGridSortsChange} rowKey={(row) => row.regional} exportFilename={`hub_${props.selectionSlug}_istoric_rm`} exportSheetName="RM istoric" emptyLabel="Nu există regionali pentru filtrele selectate." /></div>
    <div className="min-w-0"><DataGrid title="Magazine" icon={<Building2 size={16} className="text-indigo-500" />} subtitle="Filtre pe coloane · Shift+click pentru sortare multiplă" rows={props.stores} columns={storeGridColumns} initialSort={props.storeGridSorts} onSortChange={props.onStoreGridSortsChange} rowKey={(row) => row.site_code} exportFilename={`hub_${props.selectionSlug}_istoric_magazine`} exportSheetName="Magazine istoric" exportColumns={historyStoreLegacyExportColumns()} emptyLabel="Nu există magazine pentru filtrele selectate." /></div>
    <BreakdownTable title="Agenti" subtitle={`Sortare: ${props.agentColumns.find((column) => column.key === props.agentSort.key)?.label} (${props.agentSort.direction}) · ${props.agents.length} agenti`} rows={props.sortedAgents} columns={props.agentColumns} sortKey={props.agentSort.key} sortDirection={props.agentSort.direction} onSort={props.onSortAgents} rowKey={(row) => `${row.agent}-${row.site_code}`} exportFilename={`hub_${props.selectionSlug}_istoric_agenti`} exportSheetName="Agenti istoric" exportColumns={[
      { header: 'Agent', value: (row) => row.agent }, { header: 'Firma', value: (row) => row.firma }, { header: 'Magazin', value: (row) => row.locatie }, { header: 'Target', value: (row) => row.target, format: 'currency' }, { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' }, { header: 'Procent', value: (row) => row.proc_realizare_target, format: 'percentPoints' }, { header: 'Cantitate', value: (row) => row.acc_qty_realizat, format: 'integer' }, { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' }, { header: 'Retururi', value: (row) => row.return_receipt_count, format: 'integer' }, { header: 'Zile lucrate', value: (row) => row.zile_lucrate, format: 'integer' }, { header: 'Medie zilnica', value: (row) => row.medie_zilnica, format: 'currency' }, { header: 'ProcBon2Acc', value: (row) => row.proc_bon2acc, format: 'percentPoints' }, { header: 'Focus%', value: (row) => row.prc_focus_acc_qty, format: 'percentPoints' },
    ]} />
  </div></div>;
}
