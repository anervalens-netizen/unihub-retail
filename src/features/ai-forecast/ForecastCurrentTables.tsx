import { useMemo, useState } from 'react';
import { Users, X } from 'lucide-react';
import type { AiForecastManagerRow, AiForecastMetric, AiForecastResponse, AiForecastStoreRow } from '../../api/generated/runtime-types';
import { formatInt, formatPercent } from '../../lib/formatters';
import { ExportTableButton } from '../../components/ExportTableButton';
import FirmaBadge from '../../components/FirmaBadge';
import { ErrorCard, LoadingCard, Metric } from '../../components/common/DataDisplay';
import { SortableTableHeader as SortableHeader } from '../../components/common/TableHeader';
import * as aiForecastModel from './model';
import { compareForecastValues, deltaTone, formatMetricValue, formatSignedAmount, nextSortDirection } from './model';
import { ForecastDailyCurveCard } from './ForecastCharts';
import type { ForecastDetailSelection } from './AiForecastPage';

type ForecastSortDirection = 'asc' | 'desc';
type ManagerSortKey = keyof Pick<AiForecastManagerRow, 'manager' | 'store_count' | 'forecast_sales' | 'expected_sales_to_date' | 'actual_sales' | 'delta_sales' | 'delta_pct'>;
type StoreSortKey = keyof Pick<AiForecastStoreRow, 'locatie' | 'asm' | 'forecast_sales' | 'expected_sales_to_date' | 'actual_sales' | 'delta_sales' | 'delta_pct'>;

export function ForecastManagerTable({
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
            { header: 'Magazine', value: (row) => row.store_count, format: 'integer' },
            { header: 'Forecast', value: (row) => row.forecast_sales, format: metric === 'units' ? 'integer' : 'currency' },
            { header: 'Asteptat la zi', value: (row) => row.expected_sales_to_date, format: metric === 'units' ? 'integer' : 'currency' },
            { header: 'Realizat', value: (row) => row.actual_sales, format: metric === 'units' ? 'integer' : 'currency' },
            { header: 'Delta', value: (row) => row.delta_sales, format: metric === 'units' ? 'integer' : 'currency' },
            { header: 'Delta %', value: (row) => row.delta_pct, format: 'percentPoints' },
          ]}
        />
      </div>
      <div className="space-y-2 lg:hidden">
        {sortedRows.map((row) => (
          <button type="button" key={`${row.manager}:mobile`} onClick={() => onSelect(row)} className="w-full rounded-2xl border border-slate-200/70 bg-white/70 p-3 text-left dark:border-slate-700/70 dark:bg-slate-900/30">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0"><p className="truncate text-sm font-bold text-indigo-600 dark:text-indigo-400">{row.manager}</p><p className="text-[11px] text-slate-500">{formatInt(row.store_count)} magazine</p></div>
              <div className={`shrink-0 text-right text-sm font-black tabular-nums ${deltaTone(row.delta_sales)}`}>{formatSignedAmount(row.delta_sales, metric)}<p className="text-[10px] font-medium text-slate-400">{formatPercent(row.delta_pct)}</p></div>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
              <div><p className="text-[10px] text-slate-400">Forecast</p><p className="font-bold tabular-nums">{formatMetricValue(row.forecast_sales, metric)}</p></div>
              <div className="text-center"><p className="text-[10px] text-slate-400">Așteptat</p><p className="font-bold tabular-nums">{formatMetricValue(row.expected_sales_to_date, metric)}</p></div>
              <div className="text-right"><p className="text-[10px] text-slate-400">Realizat</p><p className="font-bold tabular-nums">{formatMetricValue(row.actual_sales, metric)}</p></div>
            </div>
          </button>
        ))}
      </div>
      <div className="hidden overflow-auto rounded-2xl border border-slate-200/70 lg:block dark:border-slate-700/70">
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

export function ForecastStoreTable({
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
    <>
      <div className="max-h-[520px] space-y-2 overflow-auto lg:hidden">
        {sortedRows.map((row) => (
          <button type="button" key={`${row.site_code}:mobile`} onClick={() => onSelect(row)} className="w-full rounded-2xl border border-slate-200/70 bg-white/70 p-3 text-left dark:border-slate-700/70 dark:bg-slate-900/30">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0"><p className="flex min-w-0 items-center text-sm font-bold text-indigo-600 dark:text-indigo-400"><FirmaBadge firma={row.firma} /><span className="truncate">{row.locatie}</span></p><p className="truncate text-[11px] text-slate-500">{row.asm}</p></div>
              <div className={`shrink-0 text-right text-sm font-black tabular-nums ${deltaTone(row.delta_sales)}`}>{formatSignedAmount(row.delta_sales, metric)}<p className="text-[10px] font-medium text-slate-400">{formatPercent(row.delta_pct)}</p></div>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
              <div><p className="text-[10px] text-slate-400">Forecast</p><p className="font-bold tabular-nums">{formatMetricValue(row.forecast_sales, metric)}</p></div>
              <div className="text-center"><p className="text-[10px] text-slate-400">Așteptat</p><p className="font-bold tabular-nums">{formatMetricValue(row.expected_sales_to_date, metric)}</p></div>
              <div className="text-right"><p className="text-[10px] text-slate-400">Realizat</p><p className="font-bold tabular-nums">{formatMetricValue(row.actual_sales, metric)}</p></div>
            </div>
          </button>
        ))}
      </div>
    <div className="hidden max-h-[520px] overflow-auto rounded-2xl border border-slate-200/70 lg:block dark:border-slate-700/70">
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
    </>
  );
}

export function ForecastDetailDrawer({
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
  const dailyData = useMemo(() => (data ? aiForecastModel.buildDailyCurve(data.daily) : []), [data]);
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
