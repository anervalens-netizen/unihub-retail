import { useMemo, useState } from 'react';
import { Users } from 'lucide-react';
import type { AiForecastMetric, AiForecastRollingManagerRow, AiForecastRollingStoreRow } from '../../api/generated/runtime-types';
import { formatInt, formatPercent } from '../../lib/formatters';
import { ExportTableButton } from '../../components/ExportTableButton';
import FirmaBadge from '../../components/FirmaBadge';
import { SortableTableHeader as SortableHeader } from '../../components/common/TableHeader';
import { compareForecastValues, deltaTone, formatMetricValue, formatSignedAmount, nextSortDirection } from './model';

type ForecastSortDirection = 'asc' | 'desc';
type RollingManagerSortKey = keyof Pick<AiForecastRollingManagerRow, 'manager' | 'store_count' | 'forecast_sales' | 'actual_sales' | 'delta_sales' | 'delta_pct'>;
type RollingStoreSortKey = keyof Pick<AiForecastRollingStoreRow, 'locatie' | 'asm' | 'forecast_sales' | 'actual_sales' | 'delta_sales' | 'delta_pct'>;

export function RollingManagerTable({ rows, metric }: { rows: AiForecastRollingManagerRow[]; metric: AiForecastMetric }) {
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
            { header: 'Magazine', value: (row) => row.store_count, format: 'integer' },
            { header: 'Forecast', value: (row) => row.forecast_sales, format: metric === 'units' ? 'integer' : 'currency' },
            { header: 'Realizat', value: (row) => row.actual_sales, format: metric === 'units' ? 'integer' : 'currency' },
            { header: 'Delta', value: (row) => row.delta_sales, format: metric === 'units' ? 'integer' : 'currency' },
            { header: 'Delta %', value: (row) => row.delta_pct, format: 'percentPoints' },
          ]}
        />
      </div>
      <div className="space-y-2 lg:hidden">
        {sortedRows.map((row) => (
          <article key={`${row.manager}:mobile`} className="rounded-2xl border border-slate-200/70 bg-white/70 p-3 dark:border-slate-700/70 dark:bg-slate-900/30">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0"><p className="truncate text-sm font-bold">{row.manager}</p><p className="text-[11px] text-slate-500">{formatInt(row.store_count)} magazine</p></div>
              <div className={`shrink-0 text-right text-sm font-black tabular-nums ${deltaTone(row.delta_sales)}`}>{formatSignedAmount(row.delta_sales, metric)}<p className="text-[10px] font-medium text-slate-400">{formatPercent(row.delta_pct)}</p></div>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
              <div><p className="text-[10px] text-slate-400">Forecast</p><p className="font-bold tabular-nums">{formatMetricValue(row.forecast_sales, metric)}</p></div>
              <div className="text-right"><p className="text-[10px] text-slate-400">Realizat</p><p className="font-bold tabular-nums">{formatMetricValue(row.actual_sales, metric)}</p></div>
            </div>
          </article>
        ))}
      </div>
      <div className="hidden overflow-auto rounded-2xl border border-slate-200/70 lg:block dark:border-slate-700/70">
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

export function RollingStoreTable({ rows, metric }: { rows: AiForecastRollingStoreRow[]; metric: AiForecastMetric }) {
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
    <>
      <div className="max-h-[520px] space-y-2 overflow-auto lg:hidden">
        {sortedRows.map((row) => (
          <article key={`${row.site_code}:mobile`} className="rounded-2xl border border-slate-200/70 bg-white/70 p-3 dark:border-slate-700/70 dark:bg-slate-900/30">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0"><p className="flex min-w-0 items-center text-sm font-bold"><FirmaBadge firma={row.firma} /><span className="truncate">{row.locatie}</span></p><p className="truncate text-[11px] text-slate-500">{row.asm}</p></div>
              <div className={`shrink-0 text-right text-sm font-black tabular-nums ${deltaTone(row.delta_sales)}`}>{formatSignedAmount(row.delta_sales, metric)}<p className="text-[10px] font-medium text-slate-400">{formatPercent(row.delta_pct)}</p></div>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
              <div><p className="text-[10px] text-slate-400">Forecast</p><p className="font-bold tabular-nums">{formatMetricValue(row.forecast_sales, metric)}</p></div>
              <div className="text-right"><p className="text-[10px] text-slate-400">Realizat</p><p className="font-bold tabular-nums">{formatMetricValue(row.actual_sales, metric)}</p></div>
            </div>
          </article>
        ))}
      </div>
    <div className="hidden max-h-[520px] overflow-auto rounded-2xl border border-slate-200/70 lg:block dark:border-slate-700/70">
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
    </>
  );
}
