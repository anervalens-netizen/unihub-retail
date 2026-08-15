import { TrendingUp } from 'lucide-react';
import {
  Area, AreaChart, Bar, CartesianGrid, Cell, ComposedChart, Legend, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

import { formatAmount, formatInt } from '../../lib/formatters';
import type { HistoryDashboardProps } from './HistoryDashboard';

type TrendProps = Pick<HistoryDashboardProps<string, string, string>,
  'currentSummary' | 'yearFilter' | 'onYearFilterChange' | 'availableYears'
  | 'currentHistoryLoading' | 'yearHistoryLoading' | 'currentHistoryChartData'
  | 'yearHistoryChartData' | 'kpiMetric' | 'onKpiMetricChange' | 'kpiChartData'>;

export function HistoryMonthlyTrend({ props, visible }: { props: TrendProps; visible: boolean }) {
  const loading = props.yearFilter === null ? props.currentHistoryLoading : props.yearHistoryLoading;
  return <div className={`glass rounded-3xl p-4 ${!visible ? 'hidden lg:block' : ''}`}>
    <div className="mb-3 flex items-start justify-between gap-2">
      <div>
        <h3 className="text-sm font-bold">Evolutie lunara</h3>
        <p className="text-[11px] text-slate-500">
          {props.yearFilter === null
            ? `Ultimele 13 luni finalizate${!props.currentSummary.is_month_final ? ' + previziune luna in curs' : ''}`
            : `Toate lunile disponibile — ${props.yearFilter}`}
        </p>
      </div>
      <select value={props.yearFilter ?? ''} onChange={(event) => props.onYearFilterChange(event.target.value === '' ? null : parseInt(event.target.value))} className="rounded-xl border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
        <option value="">Standard</option>
        {props.availableYears.map((year) => <option key={year} value={year}>{year}</option>)}
      </select>
    </div>
    {loading ? <div className="flex h-64 items-center justify-center text-xs text-slate-400">Se incarca...</div>
      : props.yearFilter === null ? <CurrentHistoryChart props={props} />
        : props.yearHistoryChartData.length === 0
          ? <div className="flex h-64 items-center justify-center text-xs text-slate-400">Nu exista date pentru {props.yearFilter} cu filtrele curente.</div>
          : <YearHistoryChart props={props} />}
  </div>;
}

function CurrentHistoryChart({ props }: { props: TrendProps }) {
  return <div className="h-64"><ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
    <ComposedChart data={props.currentHistoryChartData}>
      <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
      <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
      <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
      <YAxis yAxisId="progress" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
      <Tooltip formatter={(value: unknown, name: unknown) => String(name) === '% target' ? `${Number(value).toFixed(2)}%` : formatAmount(Number(value))} />
      <Legend />
      <Bar yAxisId="sales" dataKey="sales" name="Vanzari" radius={[8, 8, 0, 0]}>
        {props.currentHistoryChartData.map((entry, index) => <Cell key={index} fill={entry.isForecast ? '#a78bfa' : '#4f46e5'} />)}
      </Bar>
      <Line yAxisId="sales" type="monotone" dataKey="target" name="Target" stroke="#10b981" strokeWidth={2} dot={false} />
      <Line yAxisId="progress" type="monotone" dataKey="progress" name="% target" stroke="#f59e0b" strokeWidth={2} dot={false} />
    </ComposedChart>
  </ResponsiveContainer></div>;
}

function YearHistoryChart({ props }: { props: TrendProps }) {
  return <div className="h-64"><ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
    <ComposedChart data={props.yearHistoryChartData}>
      <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
      <XAxis dataKey="label" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
      <YAxis yAxisId="sales" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
      <YAxis yAxisId="progress" orientation="right" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
      <Tooltip formatter={(value: unknown, name: unknown) => String(name) === '% target' ? `${Number(value).toFixed(2)}%` : formatAmount(Number(value))} />
      <Legend />
      <Bar yAxisId="sales" dataKey="sales" name="Vanzari" radius={[8, 8, 0, 0]}>
        {props.yearHistoryChartData.map((entry, index) => <Cell key={index} fill={entry.isAggregate ? '#818cf8' : '#4f46e5'} />)}
      </Bar>
      {props.yearHistoryChartData.some((point) => point.target > 0) && <Line yAxisId="sales" type="monotone" dataKey="target" name="Target" stroke="#10b981" strokeWidth={2} dot={false} />}
      {props.yearHistoryChartData.some((point) => point.progress > 0) && <Line yAxisId="progress" type="monotone" dataKey="progress" name="% target" stroke="#f59e0b" strokeWidth={2} dot={false} />}
    </ComposedChart>
  </ResponsiveContainer></div>;
}

export function HistoryKpiTrend({ props, visible }: { props: TrendProps; visible: boolean }) {
  return <div className={`glass rounded-3xl p-4 ${!visible ? 'hidden lg:block' : ''}`}>
    <div className="mb-3 flex items-center justify-between gap-2">
      <div className="flex items-center gap-2"><TrendingUp size={16} className="text-indigo-500" /><h3 className="text-sm font-bold">Trend KPI</h3></div>
      <div className="flex gap-1">{([
        { key: 'proc_bon2acc', label: 'Bon2Acc' },
        { key: 'prc_focus_acc_qty', label: 'Focus' },
        { key: 'total_receipts', label: 'Bonuri' },
      ] as const).map(({ key, label }) => <button key={key} onClick={() => props.onKpiMetricChange(key)} className={`rounded-full px-2.5 py-1 text-[10px] font-bold transition-colors ${props.kpiMetric === key ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400'}`}>{label}</button>)}</div>
    </div>
    {props.currentHistoryLoading ? <div className="flex h-48 items-center justify-center text-xs text-slate-400">Se incarca...</div> : <div className="h-48">
      <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}><AreaChart data={props.kpiChartData}>
        <defs><linearGradient id="kpiTrendArea" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#4f46e5" stopOpacity={0.35} /><stop offset="95%" stopColor="#4f46e5" stopOpacity={0.03} /></linearGradient></defs>
        <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
        <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
        <Tooltip formatter={(value: unknown) => props.kpiMetric === 'total_receipts' ? formatInt(Number(value)) : `${Number(value).toFixed(1)}%`} />
        <Area type="monotone" dataKey="value" name={props.kpiMetric === 'proc_bon2acc' ? 'ProcBon2Acc' : props.kpiMetric === 'prc_focus_acc_qty' ? 'PrcFocus/AccQtty' : 'Total bonuri'} stroke="#4f46e5" fill="url(#kpiTrendArea)" strokeWidth={2} />
      </AreaChart></ResponsiveContainer>
    </div>}
  </div>;
}
