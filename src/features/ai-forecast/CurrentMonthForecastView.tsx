import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bot, Building2, ChevronDown, Network, Search } from 'lucide-react';
import { getAiForecastCurrent } from '../../api/aiForecast';
import type { AiForecastMetric } from '../../api/generated/runtime-types';
import { formatInt, formatPercent } from '../../lib/formatters';
import { buildScopedMonthQuery } from '../../lib/filterQueries';
import { queryKeys } from '../../lib/queryKeys';
import type { AppFilters } from '../../lib/appFilters';
import { ExportTableButton } from '../../components/ExportTableButton';
import { ErrorCard, LoadingCard, Metric } from '../../components/common/DataDisplay';
import * as aiForecastModel from './model';
import { deltaTone, formatGeneratedAt, formatMetricValue, formatSignedAmount, riskLabel } from './model';
import { ForecastDailyCurveCard } from './ForecastCharts';
import { ForecastDetailDrawer, ForecastManagerTable, ForecastStoreTable } from './ForecastCurrentTables';
import { ForecastDefinition, ForecastLine } from './ForecastPrimitives';

type ForecastDetailSelection =
  | { type: 'manager'; id: string; label: string }
  | { type: 'store'; id: string; label: string };

interface CurrentMonthForecastViewProps {
  currentMonth: string;
  filters: AppFilters;
  metric: AiForecastMetric;
}

/** Current-month fetch, filter and detail orchestration. Presentation primitives stay shared. */
export function CurrentMonthForecastView({ currentMonth, filters, metric }: CurrentMonthForecastViewProps) {
  const [storeSearch, setStoreSearch] = useState('');
  const [detailSelection, setDetailSelection] = useState<ForecastDetailSelection | null>(null);
  const [methodOpen, setMethodOpen] = useState(false);
  const query = useMemo(() => {
    const scoped = buildScopedMonthQuery(currentMonth, filters);
    return { month: scoped.month, firma: scoped.firma, regional: scoped.regional, site_code: scoped.site_code, metric };
  }, [currentMonth, filters, metric]);
  const forecastQuery = useQuery({
    queryKey: queryKeys.aiForecast.current(currentMonth, query),
    queryFn: ({ signal }) => getAiForecastCurrent(query, signal),
    staleTime: 60_000,
  });
  const detailQuery = useQuery({
    queryKey: queryKeys.aiForecast.current(currentMonth, { ...query, detail_type: detailSelection?.type ?? null, detail_id: detailSelection?.id ?? null }),
    queryFn: ({ signal }) => {
      if (!detailSelection) throw new Error('Nu exista selectie.');
      return getAiForecastCurrent({ ...query, asm: detailSelection.type === 'manager' ? detailSelection.id : undefined, site_code: detailSelection.type === 'store' ? [detailSelection.id] : undefined }, signal);
    },
    enabled: detailSelection !== null,
    staleTime: 60_000,
  });
  const data = forecastQuery.data;
  const filteredStores = useMemo(() => {
    if (!data) return [];
    const needle = storeSearch.trim().toLocaleLowerCase('ro-RO');
    return needle ? data.stores.filter((store) => `${store.locatie} ${store.site_code} ${store.firma} ${store.asm}`.toLocaleLowerCase('ro-RO').includes(needle)) : data.stores;
  }, [data, storeSearch]);
  const dailyChartData = useMemo(() => (data ? aiForecastModel.buildDailyCurve(data.daily) : []), [data]);
  if (forecastQuery.isPending) return <LoadingCard label="Se incarca AI Forecast..." />;
  if (forecastQuery.isError || !data) return <ErrorCard message="Nu exista forecast AI salvat pentru luna curenta sau luna urmatoare." onRetry={() => void forecastQuery.refetch()} />;

  const { summary, run } = data;
  const statusText = summary.actual_last_date
    ? `Realizat importat pana la ${summary.actual_last_date}; comparatia foloseste forecastul cumulat pana in aceeasi zi.`
    : 'Nu exista inca vanzari importate pentru luna forecastata.';
  return (
    <div className="space-y-3">
      <section className="glass rounded-3xl p-4">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><div className="flex items-center gap-2"><Bot size={17} className="text-indigo-500" /><h3 className="text-sm font-bold">AI Forecast — {summary.forecast_month}</h3></div><p className="mt-1 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">{statusText}</p></div><div className="grid w-full grid-cols-2 gap-2 rounded-2xl bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-300 sm:w-auto sm:grid-cols-3"><div><span className="block text-slate-400">Model</span>{run.model_mode}</div><div><span className="block text-slate-400">Sursă</span>{summary.source_month}</div><div><span className="block text-slate-400">Generat</span>{formatGeneratedAt(run.generated_at)}</div></div></div>
        <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-6"><Metric label="Forecast luna" value={formatMetricValue(summary.forecast_sales, metric)} className="p-2.5" /><Metric label="Realizat" value={formatMetricValue(summary.actual_sales, metric)} className="p-2.5" /><Metric label="Asteptat la zi" value={formatMetricValue(summary.expected_sales_to_date, metric)} className="p-2.5" /><Metric label="Delta" value={formatSignedAmount(summary.delta_sales, metric)} className={`p-2.5 ${deltaTone(summary.delta_sales)}`} /><Metric label="Delta %" value={formatPercent(summary.delta_pct)} className={`p-2.5 ${deltaTone(summary.delta_sales)}`} /><Metric label="Magazine" value={formatInt(summary.store_count)} className="p-2.5" /></div>
        <div className="mt-4 rounded-2xl border border-slate-200/70 bg-slate-50/80 dark:border-slate-700/70 dark:bg-slate-800/50"><button type="button" onClick={() => setMethodOpen((open) => !open)} className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-xs font-bold text-slate-700 transition-colors hover:text-indigo-600 dark:text-slate-200 dark:hover:text-indigo-300" aria-expanded={methodOpen}><span>Cum functioneaza AI Forecast</span><ChevronDown size={15} className={`shrink-0 text-slate-400 transition-transform ${methodOpen ? 'rotate-180' : ''}`} /></button>{methodOpen && <div className="space-y-3 border-t border-slate-200/70 px-3 pb-3 pt-3 text-[11px] leading-relaxed text-slate-600 dark:border-slate-700/70 dark:text-slate-300"><p>Forecastul lunar este calculat in afara aplicatiei cu TimesFM 2.5 + XReg, pe istoricul lunar per magazin. Pentru magazinele prea noi se foloseste un fallback sezonier. In Hub salvam rezultatul si il comparam cu vanzarile importate la zi; modelul nu ruleaza in requesturile din browser.</p><div className="grid gap-2 md:grid-cols-2"><ForecastDefinition term="Forecast luna" description="Estimarea pentru intreaga luna forecastata." /><ForecastDefinition term="Asteptat la zi" description="Partea din forecast care ar fi trebuit realizata pana la ultima zi importata." /><ForecastDefinition term="Delta" description="Realizat minus asteptat la zi. Pozitiv inseamna peste ritm." /><ForecastDefinition term="Delta %" description="Delta raportata la asteptatul la zi." /><ForecastDefinition term="WAPE" description="Eroarea absoluta ponderata: suma erorilor absolute impartita la vanzarile reale." /><ForecastDefinition term="Bias" description="Directia erorii totale: pozitiv supraestimeaza, negativ subestimeaza." /><ForecastDefinition term="XReg" description="Regresori externi calendaristici folositi de model: luna, trimestru, zile in luna si sezonalitate." /><ForecastDefinition term="Fallback sezonier" description="Estimare pentru magazine noi, pe media ultimelor luni scalata cu sezonalitatea istorica." /></div></div>}</div>
      </section>
      <section className="grid gap-3 lg:grid-cols-[1.1fr_1fr]"><ForecastDailyCurveCard title="Curba zilnica forecast" subtitle="Profilul zilnic foloseste luna similara istorica, aliniata pe zilele saptamanii din calendarul curent; weekendurile sunt marcate separat." data={dailyChartData} metric={metric} /><div className="glass rounded-3xl p-4"><div className="mb-3 flex items-center gap-2"><Network size={16} className="text-indigo-500" /><h3 className="text-sm font-bold">Retea</h3></div><div className="space-y-2 text-xs"><ForecastLine label="Model" value={run.model_name} /><ForecastLine label="Varianta" value={run.variant} /><ForecastLine label="Luna sursa" value={summary.source_month} /><ForecastLine label="Zile monitorizate" value={`${summary.days_elapsed}/${summary.days_in_month}`} /><ForecastLine label="Status" value={riskLabel(summary.delta_pct)} valueClassName={deltaTone(summary.delta_sales)} /></div></div></section>
      <ForecastManagerTable rows={data.managers} metric={metric} onSelect={(row) => setDetailSelection({ type: 'manager', id: row.manager, label: row.manager })} />
      <section className="glass rounded-3xl p-4"><div className="mb-3 flex flex-wrap items-center justify-between gap-3"><div><div className="flex items-center gap-2"><Building2 size={16} className="text-indigo-500" /><h3 className="text-sm font-bold">Magazine</h3></div><p className="text-[11px] text-slate-500">{filteredStores.length} din {data.stores.length} magazine in forecast.</p></div><div className="flex flex-wrap items-center gap-2"><label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900"><Search size={14} className="text-slate-400" /><input value={storeSearch} onChange={(event) => setStoreSearch(event.target.value)} placeholder="Cauta magazin" className="w-40 bg-transparent outline-none" /></label><ExportTableButton filename={`ai_forecast_${summary.forecast_month}_magazine`} sheetName={`AI Forecast ${summary.forecast_month}`} rows={filteredStores} columns={[{ header: 'Firma', value: (row) => row.firma }, { header: 'Magazin', value: (row) => row.locatie }, { header: 'ASM', value: (row) => row.asm }, { header: 'Forecast', value: (row) => row.forecast_sales, format: metric === 'units' ? 'integer' : 'currency' }, { header: 'Asteptat la zi', value: (row) => row.expected_sales_to_date, format: metric === 'units' ? 'integer' : 'currency' }, { header: 'Realizat', value: (row) => row.actual_sales, format: metric === 'units' ? 'integer' : 'currency' }, { header: 'Delta', value: (row) => row.delta_sales, format: metric === 'units' ? 'integer' : 'currency' }, { header: 'Delta %', value: (row) => row.delta_pct, format: 'percentPoints' }]} /></div></div><ForecastStoreTable rows={filteredStores} metric={metric} onSelect={(row) => setDetailSelection({ type: 'store', id: row.site_code, label: row.locatie })} /></section>
      {detailSelection && <ForecastDetailDrawer title={detailSelection.label} type={detailSelection.type} data={detailQuery.data ?? null} metric={metric} isLoading={detailQuery.isPending} isError={detailQuery.isError} onClose={() => setDetailSelection(null)} onRetry={() => void detailQuery.refetch()} />}
    </div>
  );
}
