import {
  ArrowUpDown,
  ChevronDown,
  ChevronUp,
  RotateCcw,
} from 'lucide-react';
import {
  useMemo,
  useState,
  type MouseEvent,
  type ReactNode,
} from 'react';

import { ExportTableButton } from '../ExportTableButton';
import {
  applyDataGridModel,
  isDataGridFilterActive,
  moveColumnKey,
  nextDataGridSorts,
  normalizeColumnOrder,
  toggleColumnVisibility,
  visibleColumnKeys,
  type DataGridFilterValue,
  type DataGridFilters,
  type DataGridSort,
} from '../../lib/dataGrid';
import type { ExportColumn } from '../../lib/tableExport';
import {
  DataGridColumnMenu,
  DataGridFilterControl,
} from './DataGridControls';
import type { DataGridColumn } from './dataGridTypes';

export type { DataGridColumn, DataGridFilterConfig } from './dataGridTypes';

interface DataGridProps<Row, Key extends string> {
  title: string;
  icon?: ReactNode;
  subtitle?: ReactNode;
  rows: readonly Row[];
  columns: readonly DataGridColumn<Row, Key>[];
  initialSort?: readonly DataGridSort<Key>[];
  rowKey: (row: Row, index: number) => string;
  exportFilename: string;
  exportSheetName: string;
  emptyLabel?: string;
}

function exportCellValue(value: unknown): string | number | null | undefined {
  if (value === null || value === undefined) return value;
  return typeof value === 'string' || typeof value === 'number'
    ? value
    : String(value);
}

function useDataGridState<Row, Key extends string>({
  rows,
  columns,
  initialSort = [],
}: Pick<DataGridProps<Row, Key>, 'rows' | 'columns' | 'initialSort'>) {
  const allKeys = useMemo(() => columns.map((column) => column.key), [columns]);
  const columnMap = useMemo(
    () => new Map(columns.map((column) => [column.key, column] as const)),
    [columns],
  );
  const defaultAscKeys = useMemo(
    () => columns
      .filter((column) => column.defaultDirection === 'asc')
      .map((column) => column.key),
    [columns],
  );
  const [sorts, setSorts] = useState<DataGridSort<Key>[]>(
    () => initialSort.map((sort) => ({ ...sort })),
  );
  const [filters, setFilters] = useState<DataGridFilters<Key>>({});
  const [order, setOrder] = useState<Key[]>(() => [...allKeys]);
  const [hidden, setHidden] = useState<Key[]>([]);
  const normalizedOrder = normalizeColumnOrder(allKeys, order);
  const visibleKeys = visibleColumnKeys(allKeys, { order: normalizedOrder, hidden });
  const visibleColumns = visibleKeys
    .map((key) => columnMap.get(key))
    .filter((column): column is DataGridColumn<Row, Key> => column !== undefined);
  const viewRows = useMemo(
    () => applyDataGridModel(
      rows,
      filters,
      sorts,
      (row, key) => columnMap.get(key)?.value(row),
    ),
    [columnMap, filters, rows, sorts],
  );
  const activeFilterCount = (Object.values(filters) as Array<
    DataGridFilterValue | undefined
  >).filter(isDataGridFilterActive).length;
  const exportColumns = useMemo<ExportColumn<Row>[]>(
    () => visibleColumns.map((column) => ({
      header: column.exportHeader ?? column.label,
      value: column.exportValue
        ?? ((row) => exportCellValue(column.value(row))),
      format: column.exportFormat,
    })),
    [visibleColumns],
  );
  return {
    activeFilterCount,
    allKeys,
    columnMap,
    defaultAscKeys,
    exportColumns,
    filters,
    hidden,
    normalizedOrder,
    setFilters,
    setHidden,
    setOrder,
    setSorts,
    sorts,
    viewRows,
    visibleColumns,
  };
}

function DataGridHead<Row, Key extends string>({
  columns,
  sorts,
  filters,
  onSort,
  onFilter,
}: {
  columns: readonly DataGridColumn<Row, Key>[];
  sorts: readonly DataGridSort<Key>[];
  filters: DataGridFilters<Key>;
  onSort: (key: Key, append: boolean) => void;
  onFilter: (key: Key, filter: DataGridFilterValue | undefined) => void;
}) {
  const hasFilters = columns.some((column) => column.filter !== undefined);
  return (
    <thead className="sticky top-0 z-10 bg-slate-50 text-slate-500 dark:bg-slate-800/95 dark:text-slate-300">
      <tr>
        {columns.map((column) => {
          const sortIndex = sorts.findIndex((sort) => sort.key === column.key);
          const sort = sortIndex >= 0 ? sorts[sortIndex] : undefined;
          const ariaSort: 'ascending' | 'descending' | undefined = sortIndex === 0
            ? sort?.direction === 'asc' ? 'ascending' : 'descending'
            : undefined;
          return (
            <th
              key={column.key}
              scope="col"
              aria-sort={ariaSort}
              data-testid={`data-grid-header-${column.key}`}
              className={`px-1.5 py-1.5 align-bottom text-[11px] font-bold leading-tight ${column.headerClassName ?? ''}`}
            >
              <button
                type="button"
                onClick={(event: MouseEvent<HTMLButtonElement>) =>
                  onSort(column.key, event.shiftKey)}
                aria-label={`SorteazÄƒ dupÄƒ ${column.label}`}
                title="Click pentru sortare; Shift+click pentru sortare multiplÄƒ"
                className="flex w-full min-w-0 items-center justify-between gap-1 rounded text-left hover:text-indigo-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:hover:text-indigo-300"
              >
                <span className="min-w-0 whitespace-normal break-words">{column.label}</span>
                <span className="inline-flex shrink-0 items-center gap-0.5" aria-hidden="true">
                  {sort ? (
                    sort.direction === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />
                  ) : (
                    <ArrowUpDown size={10} className="text-slate-300 dark:text-slate-600" />
                  )}
                  {sortIndex >= 0 && sorts.length > 1 && (
                    <span
                      data-testid={`data-grid-sort-priority-${column.key}`}
                      className="rounded bg-indigo-100 px-1 text-[9px] text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                    >
                      {sortIndex + 1}
                    </span>
                  )}
                </span>
              </button>
            </th>
          );
        })}
      </tr>
      {hasFilters && (
        <tr className="border-t border-slate-200/80 dark:border-slate-700">
          {columns.map((column) => (
            <th key={column.key} scope="col" className="px-1 py-1 align-top font-normal">
              <DataGridFilterControl
                column={column}
                filter={filters[column.key]}
                onChange={(filter) => onFilter(column.key, filter)}
              />
            </th>
          ))}
        </tr>
      )}
    </thead>
  );
}

function DataGridBody<Row, Key extends string>({
  rows,
  columns,
  rowKey,
  emptyLabel,
}: {
  rows: readonly Row[];
  columns: readonly DataGridColumn<Row, Key>[];
  rowKey: (row: Row, index: number) => string;
  emptyLabel: string;
}) {
  if (rows.length === 0) {
    return (
      <tbody>
        <tr>
          <td colSpan={columns.length} className="px-4 py-8 text-center text-sm font-semibold text-slate-500 dark:text-slate-400">
            {emptyLabel}
          </td>
        </tr>
      </tbody>
    );
  }
  return (
    <tbody data-testid="data-grid-body">
      {rows.map((row, index) => (
        <tr
          key={rowKey(row, index)}
          data-testid="data-grid-row"
          className="border-t border-slate-100 odd:bg-slate-50/35 hover:bg-indigo-50/50 dark:border-slate-800 dark:odd:bg-slate-900/20 dark:hover:bg-indigo-950/20"
        >
          {columns.map((column) => (
            <td key={column.key} className={column.cellClassName ?? 'px-1.5 py-1 whitespace-nowrap align-middle leading-tight'}>
              {column.render(row)}
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

export function DataGrid<Row, Key extends string>(props: DataGridProps<Row, Key>) {
  const state = useDataGridState(props);
  const setFilter = (key: Key, filter: DataGridFilterValue | undefined) => {
    state.setFilters((current) => {
      const next = { ...current };
      if (isDataGridFilterActive(filter)) next[key] = filter;
      else delete next[key];
      return next;
    });
  };
  const resultLabel = state.viewRows.length === props.rows.length
    ? `${props.rows.length} Ã®nregistrÄƒri`
    : `${state.viewRows.length} din ${props.rows.length} Ã®nregistrÄƒri`;
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-2 dark:border-slate-800">
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-bold text-slate-800 dark:text-slate-100">
            {props.icon}
            <span>{props.title}</span>
          </div>
          <div className="mt-0.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
            {props.subtitle}{props.subtitle ? ' Â· ' : ''}{resultLabel}
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          {state.activeFilterCount > 0 && (
            <button
              type="button"
              onClick={() => state.setFilters({})}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-bold text-slate-600 hover:border-indigo-200 hover:text-indigo-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              <RotateCcw size={12} />
              È˜terge filtrele ({state.activeFilterCount})
            </button>
          )}
          <DataGridColumnMenu
            columns={state.columnMap}
            allKeys={state.allKeys}
            order={state.normalizedOrder}
            hidden={state.hidden}
            onMove={(key, offset) => state.setOrder((current) =>
              moveColumnKey(state.allKeys, current, key, offset))}
            onToggle={(key) => state.setHidden((current) =>
              toggleColumnVisibility(state.allKeys, current, key))}
            onReset={() => {
              state.setOrder([...state.allKeys]);
              state.setHidden([]);
            }}
          />
          <ExportTableButton
            filename={props.exportFilename}
            sheetName={props.exportSheetName}
            columns={state.exportColumns}
            rows={state.viewRows}
          />
        </div>
      </div>
      <div className="max-h-[360px] overflow-auto">
        <table classNamYOHÈµ™Õ±°µ¥¸µÜµµ…àÑ…‰±”µ…ÕÑ¼Ñ•áÐµáÌˆ…É¥„µ±…‰•°õíÁÉ½ÁÌ¹Ñ¥Ñ±•ôø(€€€€€€€€€€ñ…Ñ…É¥‘!•…(€€€€€€€€€€€½±Õµ¹ÌõíÍÑ…Ñ”¹Ù¥Í¥‰±•½±Õµ¹Íô(€€€€€€€€€€€Í½ÉÑÌõíÍÑ…Ñ”¹Í½ÉÑÍô(€€€€€€€€€€€™¥±Ñ•ÉÌõíÍÑ…Ñ”¹™¥±Ñ•ÉÍô(€€€€€€€€€€€½¹M½ÉÐõì¡­•ä°…ÁÁ•¹¤€ôøÍÑ…Ñ”¹Í•ÑM½ÉÑÌ ¡ÕÉÉ•¹Ð¤€ôø(€€€€€€€€€€€€€¹•áÑ…Ñ…É¥‘M½ÉÑÌ¡ÕÉÉ•¹Ð°­•ä°ì(€€€€€€€€€€€€€€€…ÁÁ•¹°(€€€€€€€€€€€€€€€‘•™…Õ±ÑÍ-•åÌèÍÑ…Ñ”¹‘•™…Õ±ÑÍ-•åÌ°(€€€€€€€€€€€€€ô¤¥ô(€€€€€€€€€€€½¹¥±Ñ•ÈõíÍ•Ñ¥±Ñ•Éô(€€€€€€€€€€¼ø(€€€€€€€€€€ñ…Ñ…É¥‘	½‘ä(€€€€€€€€€€€É½ÝÌõíÍÑ…Ñ”¹Ù¥•ÝI½ÝÍô(€€€€€€€€€€€½±Õµ¹ÌõíÍÑ…Ñ”¹Ù¥Í¥‰±•½±Õµ¹Íô(€€€€€€€€€€€É½Ý-•äõíÁÉ½ÁÌ¹É½Ý-•åô(€€€€€€€€€€€•µÁÑå1…‰•°õíÁÉ½ÁÌ¹•µÁÑå1…‰•°€üü€9Ô•á¥ÍÓÉ•éÕ±Ñ…Ñ”Á•¹ÑÉÔ™¥±ÑÉ•±”Í•±•Ñ…Ñ”¸ô(€€€€€€€€€€¼ø(€€€€€€€€ð½Ñ…‰±”ø(€€€€€€ð½‘¥Øø(€€€€ð½Í•Ñ¥½¸ø(€€¤ì)ô(