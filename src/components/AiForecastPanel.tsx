import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bot, Building2, CalendarRange, ChevronDown, Network, Search, Users, X } from 'lucide-react';
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getAiForecastCurrent, getAiForecastRolling12 } from '../api/aiForecast';
import type {
  AiForecastDailyPoint,
  AiForecastManagerRow,
  AiForecastMetric,
  AiForecastResponse,
  AiForecastRollingManagerRow,
  AiForecastRollingMonthlyPoint,
  AiForecastRollingResponse,
  AiForecastRollingStoreRow,
  AiForecastStoreRow,
} from '../api/types';
import { formatAmount, formatCurrency, formatInt, formatPercent } from '../lib/formatters';
import { buildScopedMonthQuery } from '../lib/filterQueries';
import { queryKeys } from '../lib/queryKeys';
import type { AppFilters } from './MainLayout';
import { ExportTableButton } from './ExportTableButton';
import FirmaBadge from './FirmaBadge';
import { ErrorCard, LoadingCard, Metric, SortableHeader } from './dashboard/DashboardWidgets';

interface AiForecastPanelProps {
  currentMonth: string;
  filters: AppFilters;
}

interface ForecastViewProps extends AiForecastPanelProps {
  metric: AiForecastMetric;
}

type ForecastDetailSelection =
  | { type: 'manager'; id: string; label: string }
  | { type: 'store'; id: string; label: string };
type ForecastSortDirection = 'asc' | 'desc';
type ForecastHorizonMode = 'current_month' | 'rolling_12m';
type ManagerSortKey = keyof Pick<
  AiForecastManagerRow,
  'manager' | 'store_count' | 'forecast_sales' | 'expected_sales_to_date' | 'actual_sales' | 'delta_sales' | 'delta_pct'
>;
type StoreSortKey = keyof Pick<
  AiForecastStoreRow,
  'locatie' | 'asm' | 'forecast_sales' | 'expected_sales_to_date' | 'actual_sales' | 'delta_sales' | 'delta_pct'
>;
type RollingMonthSortKey = keyof Pick<AiForecastRollingMonthlyPoint, 'forecast_month' | 'store_count' | 'forecast_sales' | 'actual_sales' | 'delta_sales' | 'delta_pct'>;
type RollingManagerSortKey = keyof Pick<AiForecastRollingManagerRow, 'manager' | 'store_count' | 'forecast_sales' | 'actual_sales' | 'delta_sales' | 'delta_pct'>;
type RollingStoreSortKey = keyof Pick<AiForecastRollingStoreRow, 'locatie' | 'asm' | 'forecast_sales' | 'actual_sales' | 'delta_sales' | 'delta_pct'>;
type ForecastSortKey = ManagerSortKey | StoreSortKey | RollingMonthSortKey | RollingManagerSortKey | RollingStoreSortKey;

interface DailyCurvePoint {
  day: string;
  date: string;
  isWeekend: boolean;
  forecastDaily: number;
  actualDaily: number | null;
  cumulativeForecast: number;
  cumulativeActual: number | null;
}

function deltaTone(value: number | null | undefined) {
  const numericValue = value ?? 0;
  if (numericValue > 0) return 'text-emerald-600 dark:text-emerald-400';
  if (numericValue < 0) return 'text-rose-600 dark:text-rose-400';
  return 'text-slate-600 dark:text-slate-300';
}

function formatMetricValue(value: number | null | undefined, metric: AiForecastMetric) {
  if (value === null || value === undefined) return '-';
  return metric === 'units' ? formatInt(Math.round(value)) : formatAmount(value);
}

function formatMetricExport(value: number | null | undefined, metric: AiForecastMetric) {
  if (value === null || value === undefined) return '-';
  return metric === 'units' ? formatInt(Math.round(value)) : formatCurrency(value);
}

function formatSignedAmount(value: number | null | undefined, metric: AiForecastMetric) {
  if (value === null || value === undefined) return '-';
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${formatMetricValue(value, metric)}`;
}

function riskLabel(deltaPct: number | null) {
  if (deltaPct === null) return 'Fara reper';
  if (deltaPct >= 3) return 'Peste ritm';
  if (deltaPct <= -5) return 'Risc';
  if (deltaPct < 0) return 'Sub ritm';
  return 'In ritm';
}

function isWeekendDate(value: string) {
  const day = new Date(`${value}T00:00:00`).getDay();
  return day === 0 || day === 6;
}

function buildDailyCurve(points: AiForecastDailyPoint[]): DailyCurvePoint[] {
  return points.map((point) => {
    const hasActual = point.actual_sales > 0 || point.cumulative_actual > 0;
    return {
      day: point.forecast_date.slice(-2),
      date: point.forecast_date,
      isWeekend: isWeekendDate(point.forecast_date),
      forecastDaily: point.forecast_sales,
      actualDaily: hasActual ? point.actual_sales : null,
      cumulativeForecast: point.cumulative_forecast,
      cumulativeActual: hasActual ? point.cumulative_actual : null,
    };
  });
}

const NUMERIC_SORT_KEYS = new Set<ForecastSortKey>([
  'store_count',
  'forecast_sales',
  'expected_sales_to_date',
  'actual_sales',
  'delta_sales',
  'delta_pct',
]);

function compareForecastValues(
  key: ForecastSortKey,
  a: string | number | null | undefined,
  b: string | number | null | undefined
) {
  if (a === null || a === undefined) return b === null || b === undefined ? 0 : -1;
  if (b === null || b === undefined) return 1;
  if (NUMERIC_SORT_KEYS.has(key)) {
    const aNumber = Number(a);
    const bNumber = Number(b);
    if (Number.isNaN(aNumber)) return Number.isNaN(bNumber) ? 0 : -1;
    if (Number.isNaN(bNumber)) return 1;
    return aNumber - bNumber;
  }
  return String(a).localeCompare(String(b), 'ro-RO', { sensitivity: 'base' });
}

function nextSortDirection(currentKey: string, nextKey: string, currentDirection: ForecastSortDirection) {
  if (currentKey === nextKey) return currentDirection === 'asc' ? 'desc' : 'asc';
  return nextKey === 'manager' || nextKey === 'locatie' || nextKey === 'asm' || nextKey === 'forecast_month' ? 'asc' : 'desc';
}

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

function CurrentMonthForecastView({ currentMonth, filters, metric }: ForecastViewProps) {
  const [storeSearch, setStoreSearch] = useState('');
  const [detailSelection, setDetailSelection] = useState<ForecastDetailSelection | null>(null);
  const [methodOpen, setMethodOpen] = useState(false);
  const query = useMemo(() => {
    const scoped = buildScopedMonthQuery(currentMonth, filters);
    return {
      month: scoped.month,
      firma: scoped.firma,
      regional: scoped.regional,
      asm: scoped.asm,
      site_code: scoped.site_code,
      metric,
    };
  }, [currentMonth, filters, metric]);

  const forecastQuery = useQuery({
    queryKey: queryKeys.aiForecast.current(currentMonth, query),
    queryFn: () => getAiForecastCurrent(query),
    staleTime: 60_000,
  });

  const detailQuery = useQuery({
    queryKey: queryKeys.aiForecast.current(currentMonth, {
      ...query,
      detail_type: detailSelection?.type ?? null,
      detail_id: detailSelection?.id ?? null,
    }),
    queryFn: () => {
      if (!detailSelection) throw new Error('Nu exista selectie.');
      return getAiForecastCurrent({
        ...query,
        asm: detailSelection.type === 'manager' ? detailSelection.id : query.asm,
        site_code: detailSelection.type === 'store' ? detailSelection.id : undefined,
      });
    },
    enabled: detailSelection !== null,
    staleTime: 60_000,
  });

  const data = forecastQuery.data;
  const filteredStores = useMemo(() => {
    if (!data) return [];
    const needle = storeSearch.trim().toLocaleLowerCase('ro-RO');
    if (!needle) return data.stores;
    return data.stores.filter((store) => {
      const haystack = `${store.locatie} ${store.site_code} ${store.firma} ${store.asm}`.toLocaleLowerCase('ro-RO');
      return haystack.includes(needle);
    });
  }, [data, storeSearch]);

  const dailyChartData = useMemo(() => (data ? buildDailyCurve(data.daily) : []), [data]);

  if (forecastQuery.isPending) {
    return <LoadingCard label="Se incarca AI Forecast..." />;
  }

  if (forecastQuery.isError || !data) {
    return (
      <ErrorCard
        message="Nu exista forecast AI salvat pentru luna curenta sau luna urmatoare."
        onRetry={() => void forecastQuery.refetch()}
      />
    );
  }

  const { summary, run } = data;
  const statusText = summary.actual_last_date
    ? `Realizat importat pana la ${summary.actual_last_date}; comparatia foloseste forecastul cumulat pana in aceeasi zi.`
    : 'Nu exista inca vanzari importate pentru luna forecastata.';

  return (
    <div className="space-y-3">
      <section className="glass rounded-3xl p-4">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Bot size={17} className="text-indigo-500" />
              <h3 className="text-sm font-bold">AI Forecast — {summary.forecast_month}</h3>
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
              {statusText}
            </p>
          </div>
          <div className="rounded-2xl bg-slate-100 px-3 py-2 text-right text-[11px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-300">
            <div>{run.model_mode}</div>
            <div className="text-slate-400">sursa {summary.source_month}</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-6">
          <Metric label="Forecast luna" value={formatMetricValue(summary.forecast_sales, metric)} className="p-2.5" />
          <Metric label="Realizat" value={formatMetricValue(summary.actual_sales, metric)} className="p-2.5" />
          <Metric label="Asteptat la zi" value={formatMetricValue(summary.expected_sales_to_date, metric)} className="p-2.5" />
          <Metric
            label="Delta"
            value={formatSignedAmount(summary.delta_sales, metric)}
            className={`p-2.5 ${deltaTone(summary.delta_sales)}`}
          />
          <Metric label="Delta %" value={formatPercent(summary.delta_pct)} className={`p-2.5 ${deltaTone(summary.delta_sales)}`} />
          <Metric label="Magazine" value={formatInt(summary.store_count)} className="p-2.5" />
        </div>

        <div className="mt-4 rounded-2xl border border-slate-200/70 bg-slate-50/80 dark:border-slate-700/70 dark:bg-slate-800/50">
          <button
            type="button"
            onClick={() => setMethodOpen((open) => !open)}
            className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-xs font-bold text-slate-700 transition-colors hover:text-indigo-600 dark:text-slate-200 dark:hover:text-indigo-300"
            aria-expanded={methodOpen}
          >
            <span>Cum functioneaza AI Forecast</span>
            <ChevronDown
              size={15}
              className={`shrink-0 text-slate-400 transition-transform ${methodOpen ? 'rotate-180' : ''}`}
            />
          </button>
          {methodOpen && (
            <div className="space-y-3 border-t border-slate-200/70 px-3 pb-3 pt-3 text-[11px] leading-relaxed text-slate-600 dark:border-slate-700/70 dark:text-slate-300">
              <p>
                Forecastul lunar este calculat in afara aplicatiei cu TimesFM 2.5 + XReg, pe istoricul lunar per magazin.
                Pentru magazinele prea noi se foloseste un fallback sezonier. In Hub salvam rezultatul si il comparam cu
                vanzarile importate la zi; modelul nu ruleaza in requesturile din browser.
              </p>
              <div className="grid gap-2 md:grid-cols-2">
                <ForecastDefinition term="Forecast luna" description="Estimarea pentru intreaga luna forecastata." />
                <ForecastDefinition term="Asteptat la zi" description="Partea din forecast care ar fi trebuit realizata pana la ultima zi importata." />
                <ForecastDefinition term="Delta" description="Realizat minus asteptat la zi. Pozitiv inseamna peste ritm." />
                <ForecastDefinition term="Delta %" description="Delta raportata la asteptatul la zi." />
                <ForecastDefinition term="WAPE" description="Eroarea absoluta ponderata: suma erorilor absolute impartita la vanzarile reale." />
                <ForecastDefinition term="Bias" description="Directia erorii totale: pozitiv supraestimeaza, negativ subestimeaza." />
                <ForecastDefinition term="XReg" description="Regresori externi calendaristici folositi de model: luna, trimestru, zile in luna si sezonalitate." />
                <ForecastDefinition term="Fallback sezonier" description="Estimare pentru magazine noi, pe media ultimelor luni scalata cu sezonalitatea istorica." />
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-[1.1fr_1fr]">
        <ForecastDailyCurveCard
          title="Curba zilnica forecast"
          subtitle="Profilul zilnic foloseste luna similara istorica, aliniata pe zilele saptamanii din calendarul curent; weekendurile sunt marcate separat."
          data={dailyChartData}
          metric={metric}
        />

        <div className="glass rounded-3xl p-4">
          <div className="mb-3 flex items-center gap-2">
            <Network size={16} className="text-indigo-500" />
            <h3 className="text-sm font-bold">Retea</h3>
          </div>
          <div className="space-y-2 text-xs">
            <ForecastLine label="Model" value={run.model_name} />
            <ForecastLine label="Varianta" value={run.variant} />
            <ForecastLine label="Luna sursa" value={summary.source_month} />
            <ForecastLine label="Zile monitorizate" value={`${summary.days_elapsed}/${summary.days_in_month}`} />
            <ForecastLine label="Status" value={riskLabel(summary.delta_pct)} valueClassName={deltaTone(summary.delta_sales)} />
          </div>
        </div>
      </section>

      <ForecastManagerTable
        rows={data.managers}
        metric={metric}
        onSelect={(row) => setDetailSelection({ type: 'manager', id: row.manager, label: row.manager })}
      />

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
              filename={`ai_forecast_${summary.forecast_month}_magazine`}
              sheetName={`AI Forecast ${summary.forecast_month}`}
              rows={filteredStores}
              columns={[
                { header: 'Firma', value: (row) => row.firma },
                { header: 'Magazin', value: (row) => row.locatie },
                { header: 'ASM', value: (row) => row.asm },
                { header: 'Forecast', value: (row) => formatMetricExport(row.forecast_sales, metric) },
                { header: 'Asteptat la zi', value: (row) => formatMetricExport(row.expected_sales_to_date, metric) },
                { header: 'Realizat', value: (row) => formatMetricExport(row.actual_sales, metric) },
                { header: 'Delta', value: (row) => formatMetricExport(row.delta_sales, metric) },
                { header: 'Delta %', value: (row) => formatPercent(row.delta_pct) },
              ]}
            />
          </div>
        </div>
        <ForecastStoreTable
          rows={filteredStores}
          metric={metric}
          onSelect={(row) => setDetailSelection({ type: 'store', id: row.site_code, label: row.locatie })}
        />
      </section>

      {detailSelection && (
        <ForecastDetailDrawer
          title={detailSelection.label}
          type={detailSelection.type}
          data={detailQuery.data ?? null}
          metric={metric}
          isLoading={detailQuery.isPending}
          isError={detailQuery.isError}
          onClose={() => setDetailSelection(null)}
          onRetry={() => void detailQuery.refetch()}
        />
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
              className={`rounded-xl px-3 py-1.5 transition-colors ${
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
              className={`rounded-xl px-3 py-1.5 transition-colors ${
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
              className={`rounded-xl px-3 py-1.5 transition-colors ${
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
              className={`rounded-xl px-3 py-1.5 transition-colors ${
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

function RollingForecastView({ currentMonth, filters, metric }: ForecastViewProps) {
  const [storeSearch, setStoreSearch] = useState('');
  const query = useMemo(() => {
    const scoped = buildScopedMonthQuery(currentMonth, filters);
    return {
      month: scoped.month,
      firma: scoped.firma,
      regional: scoped.regional,
      asm: scoped.asm,
      site_code: scoped.site_code,
      metric,
    };
  }, [currentMonth, filters, metric]);

  const rollingQuery = useQuery({
    queryKey: queryKeys.aiForecast.rolling12(currentMonth, query),
    queryFn: () => getAiForecastRolling12(query),
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
          <div className="rounded-2xl bg-slate-100 px-3 py-2 text-right text-[11px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-300">
            <div>{modelRun?.model_mode ?? 'xreg + timesfm'}</div>
            <div className="text-slate-400">sursa {summary.source_month}</div>
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
                { header: 'Forecast', value: (row) => formatMetricExport(row.forecast_sales, metric) },
                { header: 'Realizat', value: (row) => formatMetricExport(row.actual_sales, metric) },
                { header: 'Delta', value: (row) => formatMetricExport(row.delta_sales, metric) },
                { header: 'Delta %', value: (row) => formatPercent(row.delta_pct) },
              ]}
            />
          </div>
        </div>
        <RollingStoreTable rows={filteredStores} metric={metric} />
      </section>
    </div>
  );
}

function ForecastDefinition({ term, description }: { term: string; description: string }) {
  return (
    <div className="rounded-xl bg-white px-3 py-2 dark:bg-slate-900/60">
      <span className="font-bold text-slate-800 dark:text-slate-100">{term}: </span>
      <span>{description}</span>
    </div>
  );
}

function RollingMonthlyChartCard({ data, metric }: { data: AiForecastRollingMonthlyPoint[]; metric: AiForecastMetric }) {
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
              formatter={(value: number, name: string) => [formatMetricValue(value, metric), name]}
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

function RollingManagerTable({ rows, metric }: { rows: AiForecastRollingManagerRow[]; metric: AiForecastMetric }) {
  const [sortKey, setSortKey] = useState<RollingManagerSortKey>('forecast_sales');
  const [sortDirection, setSortDirection] = useState<ForecastSortDirection>('desc');
  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => {
      const result = compareForecastValues(sortKey, a[sortKey], b[sortKey]);
      const directed = sortDirection === 'asc' ? result : -result;
      return directed || a.manager.localeCompare(b.manager, 'ro-RO', { sensitivity: 'base' });
    });
  }, [rows, sortDirection, sortKey]);
  const handleSort = (key: RollingManagerSortKey) => {
    setSortDirection((direction) => nextSortDirection(sortKey, key, direction));
    setSortKey(key);
  };

  return (
    <section className="glass rounded-3xl p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Users size={16} className="text-indigo-500" />
            <h3 className="text-sm font-bold">RM / ASM</h3>
          </div>
          <p className="text-[11px] text-slate-500">Total pe cele 12 luni forecastate.</p>
        </div>
        <ExportTableButton
          filename={`ai_forecast_rolling_12_${metric}_rm`}
          sheetName="AI Forecast 12 luni RM"
          rows={sortedRows}
          columns={[
            { header: 'Manager', value: (row) => row.manager },
            { header: 'Magazine', value: (row) => formatInt(row.store_count) },
            { header: 'Forecast', value: (row) => formatMetricExport(row.forecast_sales, metric) },
            { header: 'Realizat', value: (row) => formatMetricExport(row.actual_sales, metric) },
            { header: 'Delta', value: (row) => formatMetricExport(row.delta_sales, metric) },
            { header: 'Delta %', value: (row) => formatPercent(row.delta_pct) },
          ]}
        />
      </div>
      <div className="overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70">
        <table className="w-full min-w-[680px] text-sm">
          <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500 dark:bg-slate-800/95">
            <tr>
              <SortableHeader label="Manager" active={sortKey === 'manager'} direction={sortDirection} onClick={() => handleSort('manager')} className="px-3 py-2" />
              <SortableHeader label="Magazine" active={sortKey === 'store_count'} direction={sortDirection} onClick={() => handleSort('store_count')} className="px-3 py-2 text-right" align="right" />
              <SortableHeader label="Forecast" active={sortKey === 'forecast_sales'} direction={sortDirection} onClick={() => handleSort('forecast_sales')} className="px-3 py-2 text-right" align="right" />
              <SortableHeader label="Realizat" active={sortKey === 'actual_sales'} direction={sortDirection} onClick={() => handleSort('actual_sales')} className="px-3 py-2 text-right" align="right" />
              <SortableHeader label="Delta" active={sortKey === 'delta_sales'} direction={sortDirection} onClick={() => handleSort('delta_sales')} className="px-3 py-2 text-right" align="right" />
              <SortableHeader label="Delta %" active={sortKey === 'delta_pct'} direction={sortDirection} onClick={() => handleSort('delta_pct')} className="px-3 py-2 text-right" align="right" />
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, index) => (
              <tr key={row.manager} className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}>
                <td className="px-3 py-2 font-semibold text-slate-700 dark:text-slate-200">{row.manager}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatInt(row.store_count)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(row.forecast_sales, metric)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(row.actual_sales, metric)}</td>
                <td className={`px-3 py-2 text-right font-bold tabular-nums ${deltaTone(row.delta_sales)}`}>{formatSignedAmount(row.delta_sales, metric)}</td>
                <td className={`px-3 py-2 text-right font-semibold tabular-nums ${deltaTone(row.delta_sales)}`}>
                  {formatPercent(row.delta_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RollingStoreTable({ rows, metric }: { rows: AiForecastRollingStoreRow[]; metric: AiForecastMetric }) {
  const [sortKey, setSortKey] = useState<RollingStoreSortKey>('forecast_sales');
  const [sortDirection, setSortDirection] = useState<ForecastSortDirection>('desc');
  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => {
      const result = compareForecastValues(sortKey, a[sortKey], b[sortKey]);
      const directed = sortDirection === 'asc' ? result : -result;
      return directed || a.locatie.localeCompare(b.locatie, 'ro-RO', { sensitivity: 'base' });
    });
  }, [rows, sortDirection, sortKey]);
  const handleSort = (key: RollingStoreSortKey) => {
    setSortDirection((direction) => nextSortDirection(sortKey, key, direction));
    setSortKey(key);
  };

  return (
    <div className="max-h-[520px] overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70">
      <table className="w-full min-w-[780px] text-sm">
        <thead className="sticky top-0 z-10 bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500 dark:bg-slate-800/95">
          <tr>
            <SortableHeader label="Magazin" active={sortKey === 'locatie'} direction={sortDirection} onClick={() => handleSort('locatie')} className="px-3 py-2" />
            <SortableHeader label="ASM" active={sortKey === 'asm'} direction={sortDirection} onClick={() => handleSort('asm')} className="px-3 py-2" />
            <SortableHeader label="Forecast" active={sortKey === 'forecast_sales'} direction={sortDirection} onClick={() => handleSort('forecast_sales')} className="px-3 py-2 text-right" align="right" />
            <SortableHeader label="Realizat" active={sortKey === 'actual_sales'} direction={sortDirection} onClick={() => handleSort('actual_sales')} className="px-3 py-2 text-right" align="right" />
            <SortableHeader label="Delta" active={sortKey === 'delta_sales'} direction={sortDirection} onClick={() => handleSort('delta_sales')} className="px-3 py-2 text-right" align="right" />
            <SortableHeader label="Delta %" active={sortKey === 'delta_pct'} direction={sortDirection} onClick={() => handleSort('delta_pct')} className="px-3 py-2 text-right" align="right" />
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, index) => (
            <tr key={row.site_code} className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}>
              <td className="px-3 py-2">
                <span className="inline-flex min-w-0 items-center">
                  <FirmaBadge firma={row.firma} />
                  <span className="truncate font-semibold text-slate-700 dark:text-slate-200">{row.locatie}</span>
                </span>
              </td>
              <td className="px-3 py-2 text-slate-500">{row.asm}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(row.forecast_sales, metric)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(row.actual_sales, metric)}</td>
              <td className={`px-3 py-2 text-right font-bold tabular-nums ${deltaTone(row.delta_sales)}`}>{formatSignedAmount(row.delta_sales, metric)}</td>
              <td className={`px-3 py-2 text-right font-semibold tabular-nums ${deltaTone(row.delta_sales)}`}>
                {formatPercent(row.delta_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ForecastDailyCurveCard({
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
  const weekendDays = data.filter((point) => point.isWeekend).length;
  const weekendForecast = data
    .filter((point) => point.isWeekend)
    .reduce((total, point) => total + point.forecastDaily, 0);
  const totalForecast = data.reduce((total, point) => total + point.forecastDaily, 0);
  const weekendShare = totalForecast > 0 ? (weekendForecast / totalForecast) * 100 : null;

  return (
    <div className="glass rounded-3xl p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <CalendarRange size={16} className="text-indigo-500" />
            <h3 className="text-sm font-bold">{title}</h3>
          </div>
          {subtitle && <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{subtitle}</p>}
        </div>
        <div className="shrink-0 rounded-2xl bg-slate-100 px-3 py-2 text-right text-[11px] font-semibold text-slate-500 dark:bg-slate-800">
          <div>{weekendDays} zile weekend</div>
          <div className="text-slate-400">{formatPercent(weekendShare)} din forecast</div>
        </div>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
          <ComposedChart data={data}>
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
              formatter={(value: number, name: string) => [formatMetricValue(value, metric), name]}
              labelFormatter={(_label, items) => {
                const point = items?.[0]?.payload as DailyCurvePoint | undefined;
                if (!point) return '';
                return `${point.date}${point.isWeekend ? ' · weekend' : ''}`;
              }}
            />
            <Legend />
            <Bar yAxisId="daily" dataKey="forecastDaily" name="Profil zilnic" radius={[6, 6, 0, 0]}>
              {data.map((entry) => (
                <Cell key={entry.date} fill={entry.isWeekend ? '#f59e0b' : '#a5b4fc'} />
              ))}
            </Bar>
            <Bar yAxisId="daily" dataKey="actualDaily" name="Realizat zilnic" fill="#10b981" radius={[6, 6, 0, 0]} />
            <Line yAxisId="daily" type="monotone" dataKey="forecastDaily" name="Forecast zilnic" stroke="#334155" strokeWidth={2} dot={false} />
            <Line yAxisId="cumulative" type="monotone" dataKey="cumulativeForecast" name="Forecast cumulat" stroke="#4f46e5" strokeWidth={2} dot={false} />
            <Line yAxisId="cumulative" type="monotone" dataKey="cumulativeActual" name="Realizat cumulat" stroke="#059669" strokeWidth={2} dot={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function ForecastLine({ label, value, valueClassName = '' }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-2xl bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
      <span className="text-slate-500">{label}</span>
      <span className={`text-right font-bold text-slate-700 dark:text-slate-200 ${valueClassName}`}>{value}</span>
    </div>
  );
}

function ForecastManagerTable({
  rows,
  metric,
  onSelect,
}: {
  rows: AiForecastManagerRow[];
  metric: AiForecastMetric;
  onSelect: (row: AiForecastManagerRow) => void;
}) {
  const [sortKey, setSortKey] = useState<ManagerSortKey>('forecast_sales');
  const [sortDirection, setSortDirection] = useState<ForecastSortDirection>('desc');
  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => {
      const result = compareForecastValues(sortKey, a[sortKey], b[sortKey]);
      const directed = sortDirection === 'asc' ? result : -result;
      return directed || a.manager.localeCompare(b.manager, 'ro-RO', { sensitivity: 'base' });
    });
  }, [rows, sortDirection, sortKey]);
  const handleSort = (key: ManagerSortKey) => {
    setSortDirection((direction) => nextSortDirection(sortKey, key, direction));
    setSortKey(key);
  };

  return (
    <section className="glass rounded-3xl p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Users size={16} className="text-indigo-500" />
            <h3 className="text-sm font-bold">RM / ASM</h3>
          </div>
          <p className="text-[11px] text-slate-500">Managerii sunt ordonati dupa forecastul lunar.</p>
        </div>
        <ExportTableButton
          filename="ai_forecast_rm"
          sheetName="AI Forecast RM"
          rows={sortedRows}
          columns={[
            { header: 'Manager', value: (row) => row.manager },
            { header: 'Magazine', value: (row) => formatInt(row.store_count) },
            { header: 'Forecast', value: (row) => formatMetricExport(row.forecast_sales, metric) },
            { header: 'Asteptat la zi', value: (row) => formatMetricExport(row.expected_sales_to_date, metric) },
            { header: 'Realizat', value: (row) => formatMetricExport(row.actual_sales, metric) },
            { header: 'Delta', value: (row) => formatMetricExport(row.delta_sales, metric) },
            { header: 'Delta %', value: (row) => formatPercent(row.delta_pct) },
          ]}
        />
      </div>
      <div className="overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500 dark:bg-slate-800/95">
            <tr>
              <SortableHeader label="Manager" active={sortKey === 'manager'} direction={sortDirection} onClick={() => handleSort('manager')} className="px-3 py-2" />
              <SortableHeader label="Magazine" active={sortKey === 'store_count'} direction={sortDirection} onClick={() => handleSort('store_count')} className="px-3 py-2 text-right" align="right" />
              <SortableHeader label="Forecast" active={sortKey === 'forecast_sales'} direction={sortDirection} onClick={() => handleSort('forecast_sales')} className="px-3 py-2 text-right" align="right" />
              <SortableHeader label="Asteptat" active={sortKey === 'expected_sales_to_date'} direction={sortDirection} onClick={() => handleSort('expected_sales_to_date')} className="px-3 py-2 text-right" align="right" />
              <SortableHeader label="Realizat" active={sortKey === 'actual_sales'} direction={sortDirection} onClick={() => handleSort('actual_sales')} className="px-3 py-2 text-right" align="right" />
              <SortableHeader label="Delta" active={sortKey === 'delta_sales'} direction={sortDirection} onClick={() => handleSort('delta_sales')} className="px-3 py-2 text-right" align="right" />
              <SortableHeader label="Delta %" active={sortKey === 'delta_pct'} direction={sortDirection} onClick={() => handleSort('delta_pct')} className="px-3 py-2 text-right" align="right" />
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, index) => (
              <tr key={row.manager} className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}>
                <td className="px-3 py-2">
                  <button
                    type="button"
                    onClick={() => onSelect(row)}
                    className="font-semibold text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-400"
                  >
                    {row.manager}
                  </button>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{formatInt(row.store_count)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(row.forecast_sales, metric)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(row.expected_sales_to_date, metric)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(row.actual_sales, metric)}</td>
                <td className={`px-3 py-2 text-right font-bold tabular-nums ${deltaTone(row.delta_sales)}`}>{formatSignedAmount(row.delta_sales, metric)}</td>
                <td className={`px-3 py-2 text-right font-semibold tabular-nums ${deltaTone(row.delta_sales)}`}>
                  {formatPercent(row.delta_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ForecastStoreTable({
  rows,
  metric,
  onSelect,
}: {
  rows: AiForecastStoreRow[];
  metric: AiForecastMetric;
  onSelect: (row: AiForecastStoreRow) => void;
}) {
  const [sortKey, setSortKey] = useState<StoreSortKey>('forecast_sales');
  const [sortDirection, setSortDirection] = useState<ForecastSortDirection>('desc');
  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => {
      const result = compareForecastValues(sortKey, a[sortKey], b[sortKey]);
      const directed = sortDirection === 'asc' ? result : -result;
      return directed || a.locatie.localeCompare(b.locatie, 'ro-RO', { sensitivity: 'base' });
    });
  }, [rows, sortDirection, sortKey]);
  const handleSort = (key: StoreSortKey) => {
    setSortDirection((direction) => nextSortDirection(sortKey, key, direction));
    setSortKey(key);
  };

  return (
    <div className="max-h-[520px] overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70">
      <table className="w-full min-w-[900px] text-sm">
        <thead className="sticky top-0 z-10 bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500 dark:bg-slate-800/95">
          <tr>
            <SortableHeader label="Magazin" active={sortKey === 'locatie'} direction={sortDirection} onClick={() => handleSort('locatie')} className="px-3 py-2" />
            <SortableHeader label="ASM" active={sortKey === 'asm'} direction={sortDirection} onClick={() => handleSort('asm')} className="px-3 py-2" />
            <SortableHeader label="Forecast" active={sortKey === 'forecast_sales'} direction={sortDirection} onClick={() => handleSort('forecast_sales')} className="px-3 py-2 text-right" align="right" />
            <SortableHeader label="Asteptat" active={sortKey === 'expected_sales_to_date'} direction={sortDirection} onClick={() => handleSort('expected_sales_to_date')} className="px-3 py-2 text-right" align="right" />
            <SortableHeader label="Realizat" active={sortKey === 'actual_sales'} direction={sortDirection} onClick={() => handleSort('actual_sales')} className="px-3 py-2 text-right" align="right" />
            <SortableHeader label="Delta" active={sortKey === 'delta_sales'} direction={sortDirection} onClick={() => handleSort('delta_sales')} className="px-3 py-2 text-right" align="right" />
            <SortableHeader label="Delta %" active={sortKey === 'delta_pct'} direction={sortDirection} onClick={() => handleSort('delta_pct')} className="px-3 py-2 text-right" align="right" />
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, index) => (
            <tr key={row.site_code} className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}>
              <td className="px-3 py-2">
                <span className="inline-flex min-w-0 items-center">
                  <FirmaBadge firma={row.firma} />
                  <button
                    type="button"
                    onClick={() => onSelect(row)}
                    className="truncate font-semibold text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-400"
                  >
                    {row.locatie}
                  </button>
                </span>
              </td>
              <td className="px-3 py-2 text-slate-500">{row.asm}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(row.forecast_sales, metric)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(row.expected_sales_to_date, metric)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatMetricValue(row.actual_sales, metric)}</td>
              <td className={`px-3 py-2 text-right font-bold tabular-nums ${deltaTone(row.delta_sales)}`}>
                {formatSignedAmount(row.delta_sales, metric)}
              </td>
              <td className={`px-3 py-2 text-right font-semibold tabular-nums ${deltaTone(row.delta_sales)}`}>
                {formatPercent(row.delta_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ForecastDetailDrawer({
  title,
  type,
  data,
  metric,
  isLoading,
  isError,
  onClose,
  onRetry,
}: {
  title: string;
  type: ForecastDetailSelection['type'];
  data: AiForecastResponse | null;
  metric: AiForecastMetric;
  isLoading: boolean;
  isError: boolean;
  onClose: () => void;
  onRetry: () => void;
}) {
  const dailyData = useMemo(() => (data ? buildDailyCurve(data.daily) : []), [data]);
  const label = type === 'manager' ? 'RM / ASM' : 'Magazin';

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm">
      <div className="flex h-full w-full max-w-4xl flex-col overflow-y-auto bg-white shadow-2xl dark:bg-slate-950">
        <div className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-slate-100 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950">
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">{label}</p>
            <h3 className="truncate text-base font-bold text-slate-900 dark:text-slate-100">{title}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
            aria-label="Inchide"
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3 p-4">
          {isLoading ? (
            <LoadingCard label="Se incarca detaliul forecast..." />
          ) : isError || !data ? (
            <ErrorCard message="Detaliul forecast nu a putut fi incarcat." onRetry={onRetry} />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-5">
                <Metric label="Forecast luna" value={formatMetricValue(data.summary.forecast_sales, metric)} className="p-2.5" />
                <Metric label="Realizat" value={formatMetricValue(data.summary.actual_sales, metric)} className="p-2.5" />
                <Metric label="Asteptat la zi" value={formatMetricValue(data.summary.expected_sales_to_date, metric)} className="p-2.5" />
                <Metric
                  label="Delta"
                  value={formatSignedAmount(data.summary.delta_sales, metric)}
                  className={`p-2.5 ${deltaTone(data.summary.delta_sales)}`}
                />
                <Metric label="Delta %" value={formatPercent(data.summary.delta_pct)} className={`p-2.5 ${deltaTone(data.summary.delta_sales)}`} />
              </div>
              <ForecastDailyCurveCard
                title={`Curba zilnica — ${data.summary.forecast_month}`}
                subtitle="Profilul zilnic este aliniat pe zilele saptamanii din calendarul curent; barele portocalii sunt weekend."
                data={dailyData}
                metric={metric}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
