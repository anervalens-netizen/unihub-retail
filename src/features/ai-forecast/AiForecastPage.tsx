import { useState } from 'react';
import type { AiForecastMetric } from '../../api/generated/runtime-types';
import type { AppFilters } from '../../lib/appFilters';
import { CurrentMonthForecastView } from './CurrentMonthForecastView';
import { RollingForecastView } from './RollingForecastView';
export { ForecastDailyCurveCard, RollingMonthlyChartCard } from './ForecastCharts';
export { ForecastDetailDrawer, ForecastManagerTable, ForecastStoreTable } from './ForecastCurrentTables';
export { RollingManagerTable, RollingStoreTable } from './ForecastRollingTables';

interface AiForecastPanelProps {
  currentMonth: string;
  filters: AppFilters;
}

export type ForecastDetailSelection =
  | { type: 'manager'; id: string; label: string }
  | { type: 'store'; id: string; label: string };
type ForecastHorizonMode = 'current_month' | 'rolling_12m';

export function AiForecastPanel({ currentMonth, filters }: AiForecastPanelProps) {
  const [horizonMode, setHorizonMode] = useState<ForecastHorizonMode>('current_month');
  const [metric, setMetric] = useState<AiForecastMetric>('sales_value');

  return (
    <div className="space-y-3">
      <ForecastModeControls
        horizonMode={horizonMode}
        metric={metric}
        onHorizonChange={setHorizonMode}
        onMetricChange={setMetric}
      />
      {horizonMode === 'current_month' ? (
        <CurrentMonthForecastView currentMonth={currentMonth} filters={filters} metric={metric} />
      ) : (
        <RollingForecastView currentMonth={currentMonth} filters={filters} metric={metric} />
      )}
    </div>
  );
}

function ForecastModeControls({
  horizonMode,
  metric,
  onHorizonChange,
  onMetricChange,
}: {
  horizonMode: ForecastHorizonMode;
  metric: AiForecastMetric;
  onHorizonChange: (mode: ForecastHorizonMode) => void;
  onMetricChange: (metric: AiForecastMetric) => void;
}) {
  return (
    <section className="glass rounded-3xl p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="rounded-2xl bg-slate-100 p-1 text-xs font-bold dark:bg-slate-800">
            <button
              type="button"
              onClick={() => onHorizonChange('current_month')}
              className={`min-h-11 rounded-xl px-3 py-2 transition-colors lg:min-h-0 lg:py-1.5 ${
                horizonMode === 'current_month'
                  ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-950 dark:text-indigo-300'
                  : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
              }`}
            >
              Luna curenta
            </button>
            <button
              type="button"
              onClick={() => onHorizonChange('rolling_12m')}
              className={`min-h-11 rounded-xl px-3 py-2 transition-colors lg:min-h-0 lg:py-1.5 ${
                horizonMode === 'rolling_12m'
                  ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-950 dark:text-indigo-300'
                  : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
              }`}
            >
              12 luni
            </button>
          </div>
          <div className="rounded-2xl bg-slate-100 p-1 text-xs font-bold dark:bg-slate-800">
            <button
              type="button"
              onClick={() => onMetricChange('sales_value')}
              className={`min-h-11 rounded-xl px-3 py-2 transition-colors lg:min-h-0 lg:py-1.5 ${
                metric === 'sales_value'
                  ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-950 dark:text-indigo-300'
                  : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
              }`}
            >
              Valoare
            </button>
            <button
              type="button"
              onClick={() => onMetricChange('units')}
              className={`min-h-11 rounded-xl px-3 py-2 transition-colors lg:min-h-0 lg:py-1.5 ${
                metric === 'units'
                  ? 'bg-white text-indigo-600 shadow-sm dark:bg-slate-950 dark:text-indigo-300'
                  : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
              }`}
            >
              Bucati
            </button>
          </div>
        </div>
        <div className="text-right text-[11px] font-semibold text-slate-500 dark:text-slate-400">
          {horizonMode === 'current_month' ? 'monitorizare la zi' : 'planificare lunara'} · {metric === 'units' ? 'volum vandut' : 'vanzari valorice'}
        </div>
      </div>
    </section>
  );
}
