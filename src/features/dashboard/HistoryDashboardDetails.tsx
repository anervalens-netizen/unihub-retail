import { Building2, CalendarRange, MapPin, PieChart as PieChartIcon } from 'lucide-react';
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { formatAmount, formatInt } from '../../lib/formatters';
import { BreakdownTable } from './BreakdownTable';
import { CompactPieSection, formatCompactAxisValue, formatCompactDonutValue, sumChartValues } from './DashboardWidgets';
import type { HistoryDashboardProps } from './HistoryDashboard';

type DetailProps = Pick<HistoryDashboardProps<string, string, string>,
  'selectionLabel' | 'historyDailyChartData' | 'historyCategoryMixChartData' | 'historyBrandMixChartData'>;

export function HistoryDetailCharts({ props, visible }: { props: DetailProps; visible: boolean }) {
  return <div className={`grid min-w-0 items-stretch gap-3 min-[1500px]:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)] ${!visible ? 'hidden lg:grid' : ''}`}>
    <div className="glass flex min-w-0 flex-col rounded-3xl p-3 sm:p-4">
      <div className="mb-2 flex items-center gap-2 sm:mb-3"><CalendarRange size={16} className="text-indigo-500" /><h3 className="text-sm font-bold">Evolutie zilnica pentru {props.selectionLabel}</h3></div>
      <div className="-mx-2 aspect-[16/6] min-h-56 max-h-72 w-auto rounded-xl bg-slate-50/80 p-0.5 sm:mx-0 sm:w-full sm:rounded-2xl sm:p-2 dark:bg-slate-800/40 min-[1500px]:aspect-auto min-[1500px]:min-h-[24rem] min-[1500px]:max-h-none min-[1500px]:flex-1">
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}><ComposedChart data={props.historyDailyChartData} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
          <XAxis dataKey="day" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="sales" width={38} tick={{ fontSize: 10 }} tickFormatter={formatCompactAxisValue} axisLine={false} tickLine={false} />
          <YAxis yAxisId="qty" width={30} orientation="right" tick={{ fontSize: 10 }} tickFormatter={formatCompactAxisValue} axisLine={false} tickLine={false} />
          <Tooltip formatter={(value: unknown, name: unknown) => String(name) === 'Vanzari' ? formatAmount(Number(value)) : formatInt(Number(value))} />
          <Legend /><Bar yAxisId="sales" dataKey="sales" name="Vanzari" fill="#4f46e5" radius={[8, 8, 0, 0]} /><Line yAxisId="qty" type="monotone" dataKey="qty" name="Cantitate" stroke="#f59e0b" strokeWidth={2} dot={false} />
        </ComposedChart></ResponsiveContainer>
      </div>
    </div>
    <div className="glass flex min-w-0 flex-col rounded-3xl p-3 sm:p-4">
      <div className="mb-2 flex items-center gap-2 sm:mb-3"><PieChartIcon size={16} className="text-indigo-500" /><h3 className="text-sm font-bold">Top categorii si branduri</h3></div>
      <div className="grid min-w-0 flex-1 gap-2 min-[1500px]:grid-rows-2">
        <CompactPieSection title="Top categorii" emptyLabel="Nu exista categorii disponibile pentru filtrarea curenta." pieData={props.historyCategoryMixChartData} dataKey="sales_total" nameKey="category" valueFormatter={formatAmount} centerValue={formatCompactDonutValue(sumChartValues(props.historyCategoryMixChartData, 'sales_total'))} compact />
        <CompactPieSection title="Branduri compatibile" emptyLabel="Nu exista date pentru brandurile urmarite." pieData={props.historyBrandMixChartData} dataKey="sales_total" nameKey="brand" valueFormatter={formatAmount} centerValue={formatCompactDonutValue(sumChartValues(props.historyBrandMixChartData, 'sales_total'))} compact />
      </div>
    </div>
  </div>;
}

export function HistoryBreakdowns<RegionalKey extends string, StoreKey extends string, AgentKey extends string>({
  props, visible,
}: { props: HistoryDashboardProps<RegionalKey, StoreKey, AgentKey>; visible: boolean }) {
  return <div className={!visible ? 'hidden lg:contents' : 'contents'}><div className="space-y-3">
    <div className="min-w-0"><BreakdownTable title="RM" icon={<MapPin size={16} className="text-indigo-500" />} subtitle={`Sortare: ${props.regionalColumns.find((column) => column.key === props.regionalSort.key)?.label} (${props.regionalSort.direction}) · ${props.regionals.length} regionali`} rows={props.sortedRegionals} columns={props.regionalColumns} sortKey={props.regionalSort.key} sortDirection={props.regionalSort.direction} onSort={props.onSortRegionals} rowKey={(row) => row.regional} exportFilename={`hub_${props.selectionSlug}_istoric_rm`} exportSheetName="RM istoric" exportColumns={[
      { header: 'Regional', value: (row) => row.regional }, { header: 'Target', value: (row) => row.target, format: 'currency' }, { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' }, { header: 'Procent', value: (row) => row.proc_realizare_target, format: 'percentPoints' }, { header: 'Cantitate', value: (row) => row.qty_total, format: 'integer' }, { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' }, { header: 'ProcBon2Acc', value: (row) => row.proc_bon2acc, format: 'percentPoints' }, { header: 'Focus%', value: (row) => row.prc_focus_acc_qty, format: 'percentPoints' },
    ]} /></div>
    <div className="min-w-0"><BreakdownTable title="Magazine" icon={<Building2 size={16} className="text-indigo-500" />} subtitle={`Sortare: ${props.storeColumns.find((column) => column.key === props.storeSort.key)?.label} (${props.storeSort.direction}) · ${props.stores.length} magazine`} rows={props.sortedStores} columns={props.storeColumns} sortKey={props.storeSort.key} sortDirection={props.storeSort.direction} onSort={props.onSortStores} rowKey={(row) => row.site_code} exportFilename={`hub_${props.selectionSlug}_istoric_magazine`} exportSheetName="Magazine istoric" exportColumns={[
      { header: 'Firma', value: (row) => row.firma }, { header: 'Magazin', value: (row) => row.locatie }, { header: 'Target', value: (row) => row.target, format: 'currency' }, { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' }, { header: 'Procent', value: (row) => row.proc_realizare_target, format: 'percentPoints' }, { header: 'Cantitate', value: (row) => row.qty_total, format: 'integer' }, { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' }, { header: 'Retururi', value: (row) => row.return_receipt_count, format: 'integer' }, { header: 'Agenti', value: (row) => row.nr_agenti, format: 'integer' }, { header: 'Zile active', value: (row) => row.zile_active, format: 'integer' },
    ]} /></div>
    <BreakdownTable title="Agenti" subtitle={`Sortare: ${props.agentColumns.find((column) => column.key === props.agentSort.key)?.label} (${props.agentSort.direction}) · ${props.agents.length} agenti`} rows={props.sortedAgents} columns={props.agentColumns} sortKey={props.agentSort.key} sortDirection={props.agentSort.direction} onSort={props.onSortAgents} rowKey={(row) => `${row.agent}-${row.site_code}`} exportFilename={`hub_${props.selectionSlug}_istoric_agenti`} exportSheetName="Agenti istoric" exportColumns={[
      { header: 'Agent', value: (row) => row.agent }, { header: 'Firma', value: (row) => row.firma }, { header: 'Magazin', value: (row) => row.locatie }, { header: 'Target', value: (row) => row.target, format: 'currency' }, { header: 'Vanzari', value: (row) => row.total_vanzari, format: 'currency' }, { header: 'Procent', value: (row) => row.proc_realizare_target, format: 'percentPoints' }, { header: 'Cantitate', value: (row) => row.acc_qty_realizat, format: 'integer' }, { header: 'Nr bonuri', value: (row) => row.nr_bonuri, format: 'integer' }, { header: 'Retururi', value: (row) => row.return_receipt_count, format: 'integer' }, { header: 'Zile lucrate', value: (row) => row.zile_lucrate, format: 'integer' }, { header: 'Medie zilnica', value: (row) => row.medie_zilnica, format: 'currency' }, { header: 'ProcBon2Acc', value: (row) => row.proc_bon2acc, format: 'percentPoints' }, { header: 'Focus%', value: (row) => row.prc_focus_acc_qty, format: 'percentPoints' },
    ]} />
  </div></div>;
}
