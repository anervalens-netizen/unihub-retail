import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bot, Building2, Network, Search } from 'lucide-react';
import { getAiForecastRolling12 } from '../../api/aiForecast';
import type { AiForecastMetric } from '../../api/generated/runtime-types';
import { formatInt, formatPercent } from '../../lib/formatters';
import { buildScopedMonthQuery } from '../../lib/filterQueries';
import { queryKeys } from '../../lib/queryKeys';
import type { AppFilters } from '../../lib/appFilters';
import { ExportTableButton } from '../../components/ExportTableButton';
import { ErrorCard, LoadingCard, Metric } from '../../components/common/DataDisplay';
import { deltaTone, formatGeneratedAt, formatMetricValue, formatSignedAmount } from './model';
import { RollingMonthlyChartCard } from './ForecastCharts';
import { ForecastLine } from './ForecastPrimitives';
import { RollingManagerTable, RollingStoreTable } from './ForecastRollingTables';

interface ForecastViewProps { currentMonth: string; filters: AppFilters; metric: AiForecastMetric; }

export function RollingForecastView({ currentMonth, filters, metric }: ForecastViewProps) {
  const [storeSearch, setStoreSearch] = useState('');
  const query = useMemo(() => {
    const scoped = buildScopedMonthQuery(currentMonth, filters);
    return {
      month: scoped.month,
      firma: scoped.firma,
      regional: scoped.regional,
      site_code: scoped.site_code,
      metric,
    };
  }, [currentMonth, filters, metric]);

  const rollingQuery = useQuery({
    queryKey: queryKeys.aiForecast.rolling12(currentMonth, query),
    queryFn: ({ signal }) => getAiForecastRolling12(query, signal),
    staleTime: 60_000,
  });

  const data = rollingQuery.data;
  const filteredStores = useMemo(() => {
    if (!data) return [];
    const needle = storeSearch.trim().toLocaleLowerCase('ro-RO');
    if (!needle) return data.stores;
    return data.stores.filter((store) => {
      const haystack = `${store.locatie} ${store.site_code} ${store.firma} ${store.asm}`.toLocaleLowerCase('ro-RO');
      return haystack.includes(needle);
    });
  }, [data, storeSearch]);

  if (rollingQuery.isPending) {
    return <LoadingCard label="Se incarca forecastul pe 12 luni..." />;
  }

  if (rollingQuery.isError || !data) {
    return (
      <ErrorCard
        message="Nu exista forecast AI pe urmatoarele 12 luni pentru metrica selectata."
        onRetry={() => void rollingQuery.refetch()}
      />
    );
  }

  const { summary, runs } = data;
  const modelRun = runs[0];
  const hasActual = summary.actual_sales !== null;

  return (
    <div className="space-y-3">
      <section className="glass rounded-3xl p-4">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Bot size={17} className="text-indigo-500" />
              <h3 className="text-sm font-bold">AI Forecast 12 luni — {summary.start_month} / {summary.end_month}</h3>
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
              Prognoza lunara pentru urmatoarele 12 luni, salvata offline pe magazine active si agregata pe structura curenta.
            </p>
          </div>
          <div className="grid w-full grid-cols-2 gap-2 rounded-2xl bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-300 sm:w-auto sm:grid-cols-3">
            <div><span className="block text-slate-400">Model</span>{modelRun?.model_mode ?? 'xreg + timesfm'}</div>
            <div><span className="block text-slate-400">Sursă</span>{summary.source_month}</div>
            <div><span className="block text-slate-400">Generat</span>{formatGeneratedAt(modelRun?.generated_at)}</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-6">
          <Metric label="Forecast 12 luni" value={formatMetricValue(summary.forecast_sales, metric)} className="p-2.5" />
          <Metric label="Realizat" value={formatMetricValue(summary.actual_sales, metric)} className="p-2.5" />
          <Metric
            label="Delta"
            value={formatSignedAmount(summary.delta_sales, metric)}
            className={`p-2.5 ${deltaTone(summary.delta_sales)}`}
          />
          <Metric label="Delta %" value={formatPercent(summary.delta_pct)} className={`p-2.5 ${deltaTone(summary.delta_sales)}`} />
          <Metric label="Magazine" value={formatInt(summary.store_count)} className="p-2.5" />
          <Metric label="Luni" value={formatInt(summary.month_count)} className="p-2.5" />
        </div>
        {!hasActual && (
          <p className="mt-3 text-[11px] text-slate-500 dark:text-slate-400">
            Nu exista inca realizat pentru lunile viitoare; delta va deveni relevanta dupa importurile lunare.
          </p>
        )}
      </section>

      <section className="grid gap-3 lg:grid-cols-[1.25fr_0.75fr]">
        <RollingMonthlyChartCard data={data.months} metric={metric} />
        <div className="glass rounded-3xl p-4">
          <div className="mb-3 flex items-center gap-2">
            <Network size={16} className="text-indigo-500" />
            <h3 className="text-sm font-bold">Retea</h3>
          </div>
          <div className="space-y-2 text-xs">
            <ForecastLine label="Model" value={modelRun?.model_name ?? '-'} />
            <ForecastLine label="Varianta" value={modelRun?.variant ?? '-'} />
            <ForecastLine label="Luna sursa" value={summary.source_month} />
            <ForecastLine label="Interval" value={`${summary.start_month} - ${summary.end_month}`} />
          </div>
        </div>
      </section>

      <RollingManagerTable rows={data.managers} metric={metric} />

      <section className="glass rounded-3xl p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Building2 size={16} className="text-indigo-500" />
              <h3 className="text-sm font-bold">Magazine</h3>
            </div>
            <p className="text-[11px] text-slate-500">
              {filteredStores.length} din {data.stores.length} magazine in forecast.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900">
              <Search size={14} className="text-slate-400" />
              <input
                value={storeSearch}
                onChange={(event) => setStoreSearch(event.target.value)}
                placeholder="Cauta magazin"
                className="w-40 bg-transparent outline-none"
              />
            </label>
            <ExportTableButton
              filename={`ai_forecast_rolling_12_${metric}_magazine`}
              sheetName="AI Forecast 12 luni"
              rows={filteredStores}
              columns={[
                { header: 'Firma', value: (row) => row.firma },
                { header: 'Magazin', value: (row) => row.locatie },
                { header: 'ASM', value: (row) => row.asm },
                { header: 'Forecast', value: (row) => row.forecast_sales, format: metric === 'units' ? 'integer' : 'currency' },
                { header: 'Realizat', value: (row) => row.actual_sales, format: metric === 'units' ? 'integer' : 'currency' },
                { header: 'Delta', value: (row) => row.delta_sales, format: metric === 'units' ? 'integer' : 'currency' },
                { header: 'Delta %', value: (row) => row.delta_pct, format: 'percentPoints' },
              ]}
            />
          </div>
        </div>
        <RollingStoreTable rows={filteredStores} metric={metric} />
      </section>
    </div>
  );
}
