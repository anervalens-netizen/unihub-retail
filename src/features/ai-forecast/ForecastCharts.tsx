import { useMemo, useState } from 'react';
import { CalendarRange } from 'lucide-react';
import { Bar, CartesianGrid, Cell, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { AiForecastMetric, AiForecastRollingMonthlyPoint } from '../../api/generated/runtime-types';
import { formatPercent } from '../../lib/formatters';
import { formatMetricValue } from './model';

export interface DailyCurvePoint { day: string; date: string; isWeekend: boolean; forecastDaily: number; actualDaily: number | null; cumulativeForecast: number; cumulativeActual: number | null; }

type DailyCurveView = 'chart' | 'table';

export function RollingMonthlyChartCard({ data, metric }: { data: AiForecastRollingMonthlyPoint[]; metric: AiForecastMetric }) {
  const chartData = useMemo(
    () =>
      data.map((point) => ({
        ...point,
        label: point.forecast_month.slice(5),
      })),
    [data],
  );

  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3 flex items-center gap-2">
        <CalendarRange size={16} className="text-indigo-500" />
        <h3 className="text-sm font-bold">Forecast lunar</h3>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
            <XAxis dataKey="label" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip
              formatter={(value: unknown, name: unknown) => [formatMetricValue(Number(value), metric), String(name ?? '')]}
              labelFormatter={(_label, items) => {
                const point = items?.[0]?.payload as AiForecastRollingMonthlyPoint | undefined;
                return point?.forecast_month ?? '';
              }}
            />
            <Legend />
            <Bar dataKey="forecast_sales" name="Forecast" fill="#4f46e5" radius={[6, 6, 0, 0]} />
            <Line type="monotone" dataKey="actual_sales" name="Realizat" stroke="#059669" strokeWidth={2} dot={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function ForecastDailyCurveChart({ data, metric }: {
  data: DailyCurvePoint[];
  metric: AiForecastMetric;
}) {
  return (
    <div data-testid="forecast-daily-curve-chart" className="h-72">
      <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
        <ComposedChart data={data} barCategoryGap="45%" barGap="-100%">
          <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
          <XAxis dataKey="day" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="daily" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis
            yAxisId="cumulative"
            orientation="right"
            tick={{ fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            formatter={(value: unknown, name: unknown) => [formatMetricValue(Number(value), metric), String(name ?? '')]}
            labelFormatter={(_label, items) => {
              const point = items?.[0]?.payload as DailyCurvePoint | undefined;
              if (!point) return '';
              return `${point.date}${point.isWeekend ? ' · weekend' : ''}`;
            }}
          />
          <Legend />
          <Bar yAxisId="daily" dataKey="forecastDaily" name="Forecast zilnic" fillOpacity={0.72} radius={[6, 6, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.date} fill={entry.isWeekend ? '#f59e0b' : '#a5b4fc'} />
            ))}
          </Bar>
          <Bar yAxisId="daily" dataKey="actualDaily" name="Realizat zilnic" fill="#10b981" fillOpacity={0.88} radius={[6, 6, 0, 0]} />
          <Line yAxisId="cumulative" type="monotone" dataKey="cumulativeForecast" name="Forecast cumulat" stroke="#4f46e5" strokeWidth={2} dot={false} />
          <Line yAxisId="cumulative" type="monotone" dataKey="cumulativeActual" name="Realizat cumulat" stroke="#059669" strokeWidth={2} dot={false} connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function ForecastDailyCurveTable({ title, data, metric }: {
  title: string;
  data: DailyCurvePoint[];
  metric: AiForecastMetric;
}) {
  return (
    <div
      role="region"
      aria-label={`Date ${title}`}
      tabIndex={0}
      className="h-72 min-w-0 max-w-full overflow-auto rounded-2xl border border-slate-200/70 bg-white/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700/70 dark:bg-slate-900/30"
    >
      <table className="w-full min-w-[760px] text-left text-xs">
        <caption className="sr-only">{title}</caption>
        <thead className="sticky top-0 z-10 bg-slate-50 text-[11px] text-slate-500 dark:bg-slate-800/95">
          <tr>
            <th scope="col" className="px-3 py-2">Data</th>
            <th scope="col" className="px-3 py-2">Zi</th>
            <th scope="col" className="px-3 py-2">Tip zi</th>
            <th scope="col" className="px-3 py-2 text-right">Forecast zilnic</th>
            <th scope="col" className="px-3 py-2 text-right">Realizat zilnic</th>
            <th scope="col" className="px-3 py-2 text-right">Forecast cumulat</th>
            <th scope="col" className="px-3 py-2 text-right">Realizat cumulat</th>
          </tr>
        </thead>
        <tbody>
          {data.map((point) => (
            <tr key={point.date} className="border-t border-slate-100 dark:border-slate-800">
              <th scope="row" className="whitespace-nowrap px-3 py-2 font-medium">{point.date}</th>
              <td className="px-3 py-2">{point.day}</td>
              <td className="px-3 py-2">{point.isWeekend ? 'Weekend' : 'Lucratoare'}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(point.forecastDaily, metric)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(point.actualDaily, metric)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(point.cumulativeForecast, metric)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(point.cumulativeActual, metric)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ForecastDailyCurveCard({
  title,
  subtitle,
  data,
  metric,
}: {
  title: string;
  subtitle?: string;
  data: DailyCurvePoint[];
  metric: AiForecastMetric;
}) {
  const [view, setView] = useState<DailyCurveView>('chart');
  const weekendDays = data.filter((point) => point.isWeekend).length;
  const weekendForecast = data
    .filter((point) => point.isWeekend)
    .reduce((total, point) => total + point.forecastDaily, 0);
  const totalForecast = data.reduce((total, point) => total + point.forecastDaily, 0);
  const weekendShare = totalForecast > 0 ? (weekendForecast / totalForecast) * 100 : null;

  return (
    <div className="glass min-w-0 rounded-3xl p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <CalendarRange size={16} className="text-indigo-500" />
            <h3 className="text-sm font-bold">{title}</h3>
          </div>
          {subtitle && <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{subtitle}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          <select
            aria-label={`Vizualizare ${title}`}
            value={view}
            onChange={(event) => setView(event.target.value as DailyCurveView)}
            className="rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-bold text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
          >
            <option value="chart">Grafic</option>
            <option value="table">Tabel</option>
          </select>
          <div className="rounded-2xl bg-slate-100 px-3 py-2 text-right text-[11px] font-semibold text-slate-500 dark:bg-slate-800">
            <div>{weekendDays} zile weekend</div>
            <div className="text-slate-400">{formatPercent(weekendShare)} din forecast</div>
          </div>
        </div>
      </div>
      {view === 'chart'
        ? <ForecastDailyCurveChart data={data} metric={metric} />
        : <ForecastDailyCurveTable title={title} data={data} metric={metric} />}
    </div>
  );
}
