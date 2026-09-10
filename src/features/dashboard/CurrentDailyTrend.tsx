import { CalendarRange } from 'lucide-react';
import { useState } from 'react';
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

import { ChartFrame } from '../../components/common/ChartFrame';
import { formatAmount } from '../../lib/formatters';
import type { CurrentDashboardProps } from './CurrentDashboard';
import { formatCompactAxisValue } from './DashboardWidgets';

type DailyChartData = CurrentDashboardProps<string, string, string>['dailyChartData'];
type DailyTrendView = 'chart' | 'table';

function formatDailyValue(value: number | null): string {
  return value === null ? '—' : formatAmount(value);
}

function DailyTrendChart({ data }: { data: DailyChartData }) {
  return (
    <div data-testid="current-daily-chart" className="h-full w-full">
      <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
        <ComposedChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
          <XAxis dataKey="day" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis
            yAxisId="sales"
            width={38}
            tick={{ fontSize: 10 }}
            tickFormatter={formatCompactAxisValue}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip formatter={(value: unknown) => formatAmount(Number(value))} />
          <Legend />
          <Bar
            yAxisId="sales"
            dataKey="sales"
            name="Vanzari"
            fill="#4f46e5"
            radius={[8, 8, 0, 0]}
          />
          <Line
            yAxisId="sales"
            type="monotone"
            dataKey="sales_last_year"
            name="Anul trecut"
            stroke="#10b981"
            strokeWidth={2}
            strokeDasharray="5 3"
            dot={false}
            connectNulls
          />
          <Line
            yAxisId="sales"
            type="monotone"
            dataKey="sales_forecast"
            name="Prognoza"
            stroke="#f59e0b"
            strokeWidth={2}
            strokeDasharray="3 3"
            dot={false}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function DailyTrendTable({ currentMonth, data }: {
  currentMonth: string;
  data: DailyChartData;
}) {
  return (
    <div
      role="region"
      aria-label={`Date evolutie zilnica ${currentMonth}`}
      tabIndex={0}
      className="h-full overflow-auto rounded-xl border border-slate-200 bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900/60"
    >
      <table className="w-full min-w-[520px] text-left text-xs">
        <caption className="sr-only">Evolutie zilnica pentru {currentMonth}</caption>
        <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
          <tr>
            <th scope="col" className="px-3 py-2">Ziua</th>
            <th scope="col" className="px-3 py-2 text-right">Vanzari</th>
            <th scope="col" className="px-3 py-2 text-right">Anul trecut</th>
            <th scope="col" className="px-3 py-2 text-right">Prognoza</th>
          </tr>
        </thead>
        <tbody>
          {data.map((point) => (
            <tr key={point.day} className="border-t border-slate-100 dark:border-slate-800">
              <th scope="row" className="px-3 py-2 font-medium">{point.day}</th>
              <td className="px-3 py-2 text-right tabular-nums">{formatDailyValue(point.sales)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatDailyValue(point.sales_last_year)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatDailyValue(point.sales_forecast)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CurrentDailyTrend({ currentMonth, data }: {
  currentMonth: string;
  data: DailyChartData;
}) {
  const [view, setView] = useState<DailyTrendView>('chart');
  const contentClassName = view === 'chart'
    ? '-mx-2 aspect-[16/6] min-h-56 max-h-72 w-auto rounded-xl bg-slate-50/80 p-0.5 sm:mx-0 sm:w-full sm:rounded-2xl sm:p-2 dark:bg-slate-800/40 min-[1500px]:aspect-auto min-[1500px]:min-h-[24rem] min-[1500px]:max-h-none min-[1500px]:flex-1'
    : 'min-h-56 max-h-72 min-w-0 overflow-hidden min-[1500px]:min-h-[24rem] min-[1500px]:max-h-none min-[1500px]:flex-1';

  return (
    <ChartFrame
      title={`Evolutie zilnica pentru ${currentMonth}`}
      icon={<CalendarRange size={16} className="text-indigo-500" />}
      controls={(
        <select
          aria-label="Vizualizare evolutie zilnica"
          value={view}
          onChange={(event) => setView(event.target.value as DailyTrendView)}
          className="shrink-0 rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-bold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
        >
          <option value="chart">Grafic</option>
          <option value="table">Tabel</option>
        </select>
      )}
      contentClassName={contentClassName}
      compactMobile
      headerAlign="start"
    >
      {view === 'chart'
        ? <DailyTrendChart data={data} />
        : <DailyTrendTable currentMonth={currentMonth} data={data} />}
    </ChartFrame>
  );
}
