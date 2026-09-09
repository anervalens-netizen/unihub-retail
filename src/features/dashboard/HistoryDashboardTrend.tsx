import { useState } from 'react';

import { TrendingUp } from 'lucide-react';
import {
  Area, AreaChart, Bar, CartesianGrid, Cell, ComposedChart, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

import { ChartFrame } from '../../components/common/ChartFrame';
import { formatAmount, formatInt } from '../../lib/formatters';
import type { HistoryDashboardProps } from './HistoryDashboard';

type TrendProps = Pick<HistoryDashboardProps<string, string, string>,
  'currentSummary' | 'yearFilter' | 'onYearFilterChange' | 'availableYears'
  | 'currentHistoryLoading' | 'yearHistoryLoading' | 'currentHistoryChartData'
  | 'yearHistoryChartData' | 'kpiMetric' | 'onKpiMetricChange' | 'kpiChartData'>;

type KpiChartView = 'area' | 'line' | 'table';
type KpiTrendProps = Pick<TrendProps,
  'kpiMetric' | 'onKpiMetricChange' | 'kpiChartData' | 'currentHistoryLoading'>;

export function HistoryMonthlyTrend({ props, visible }: { props: TrendProps; visible: boolean }) {
  const loading = props.yearFilter === null ? props.currentHistoryLoading : props.yearHistoryLoading;
  const subtitle = props.yearFilter === null
    ? `Ultimele 13 luni finalizate${!props.currentSummary.is_month_final ? ' + previziune luna in curs' : ''}`
    : `Toate lunile disponibile — ${props.yearFilter}`;
  const empty = props.yearFilter !== null && props.yearHistoryChartData.length === 0;

  return (
    <ChartFrame
      title="Evolutie lunara"
      subtitle={subtitle}
      controls={(
        <select
          value={props.yearFilter ?? ''}
          onChange={(event) => props.onYearFilterChange(
            event.target.value === '' ? null : parseInt(event.target.value),
          )}
          className="rounded-xl border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
        >
          <option value="">Standard</option>
          {props.availableYears.map((year) => <option key={year} value={year}>{year}</option>)}
        </select>
      )}
      loading={loading}
      empty={empty}
      emptyLabel={`Nu exista date pentru ${props.yearFilter} cu filtrele curente.`}
      contentClassName="h-64"
      className={!visible ? 'hidden lg:block' : ''}
      headerAlign="start"
    >
      {props.yearFilter === null
        ? <CurrentHistoryChart props={props} />
        : <YearHistoryChart props={props} />}
    </ChartFrame>
  );
}

function CurrentHistoryChart({ props }: { props: TrendProps }) {
  return (
    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
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
    </ResponsiveContainer>
  );
}

function YearHistoryChart({ props }: { props: TrendProps }) {
  return (
    <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
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
    </ResponsiveContainer>
  );
}

function HistoryKpiDataTable({ data, seriesName, formatValue }: {
  data: TrendProps['kpiChartData'];
  seriesName: string;
  formatValue: (value: unknown) => string;
}) {
  if (data.length === 0) {
    return <p role="status" className="p-3 text-xs text-slate-500">Nu există date KPI pentru filtrele selectate.</p>;
  }

  return (
    <div
      role="region"
      aria-label="Date Trend KPI"
      tabIndex={0}
      className="h-full overflow-auto rounded-xl border border-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700"
    >
      <table className="w-full text-left text-xs">
        <caption className="sr-only">Trend KPI — {seriesName}</caption>
        <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
          <tr>
            <th scope="col" className="px-3 py-2">Luna</th>
            <th scope="col" className="px-3 py-2 text-right">{seriesName}</th>
          </tr>
        </thead>
        <tbody>
          {data.map((point) => (
            <tr key={point.month} className="border-t border-slate-100 dark:border-slate-800">
              <th scope="row" className="px-3 py-2 font-medium">{point.month}</th>
              <td className="px-3 py-2 text-right tabular-nums">{formatValue(point.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function HistoryKpiTrend({ props, visible }: { props: KpiTrendProps; visible: boolean }) {
  const [chartView, setChartView] = useState<KpiChartView>('area');
  const seriesName = props.kpiMetric === 'proc_bon2acc'
    ? 'ProcBon2Acc'
    : props.kpiMetric === 'prc_focus_acc_qty'
      ? 'PrcFocus/AccQtty'
      : 'Total bonuri';
  const formatKpiValue = (value: unknown) => props.kpiMetric === 'total_receipts'
    ? formatInt(Number(value))
    : `${Number(value).toFixed(1)}%`;

  return (
    <ChartFrame
      title="Trend KPI"
      icon={<TrendingUp size={16} className="text-indigo-500" />}
      controls={(
        <div className="flex flex-wrap items-center justify-end gap-1">
          {([
            { key: 'proc_bon2acc', label: 'Bon2Acc' },
            { key: 'prc_focus_acc_qty', label: 'Focus' },
            { key: 'total_receipts', label: 'Bonuri' },
          ] as const).map(({ key, label }) => (
            <button
              key={key}
              type="button"
              aria-pressed={props.kpiMetric === key}
              onClick={() => props.onKpiMetricChange(key)}
              className={`rounded-full px-2.5 py-1 text-[10px] font-bold transition-colors ${props.kpiMetric === key ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400'}`}
            >
              {label}
            </button>
          ))}
          <select
            aria-label="Tip grafic KPI"
            value={chartView}
            onChange={(event) => setChartView(event.target.value as KpiChartView)}
            className="shrink-0 rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-bold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
          >
            <option value="area">Arie</option>
            <option value="line">Linie</option>
            <option value="table">Tabel</option>
          </select>
        </div>
      )}
      loading={props.currentHistoryLoading}
      contentClassName="h-48"
      className={!visible ? 'hidden lg:block' : ''}
    >
      {chartView === 'table' ? (
        <HistoryKpiDataTable data={props.kpiChartData} seriesName={seriesName} formatValue={formatKpiValue} />
      ) : (
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
          {chartView === 'area' ? (
            <AreaChart data={props.kpiChartData}>
              <defs><linearGradient id="kpiTrendArea" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#4f46e5" stopOpacity={0.35} /><stop offset="95%" stopColor="#4f46e5" stopOpacity={0.03} /></linearGradient></defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip formatter={formatKpiValue} />
              <Area type="monotone" dataKey="value" name={seriesName} stroke="#4f46e5" fill="url(#kpiTrendArea)" strokeWidth={2} />
            </AreaChart>
          ) : (
            <LineChart data={props.kpiChartData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip formatter={formatKpiValue} />
              <Line type="monotone" dataKey="value" name={seriesName} stroke="#4f46e5" strokeWidth={2} dot={false} />
            </LineChart>
          )}
        </ResponsiveContainer>
      )}
    </ChartFrame>
  );
}
