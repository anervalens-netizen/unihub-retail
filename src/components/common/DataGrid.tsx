import {
  ArrowUpDown,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  Search,
} from 'lucide-react';
import {
  useId,
  useMemo,
  useState,
  type MouseEvent,
  type ReactNode,
} from 'react';

import { ExportTableButton } from '../ExportTableButton';
import {
  applyDataGridModel,
  isDataGridFilterActive,
  isDataGridSearchActive,
  moveColumnKey,
  nextDataGridSorts,
  normalizeColumnOrder,
  searchDataGridRows,
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
  DataGridHiddenFilters,
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
  onSortChange?: (sorts: readonly DataGridSort<Key>[]) => void;
  rowKey: (row: Row, index: number) => string;
  exportFilename: string;
  exportSheetName: string;
  exportColumns?: ExportColumn<Row>[];
  emptyLabel?: string;
}

function exportCellValue(value: unknown): string | number | null | undefined {
  if (value === null || value === undefined) return value;
  return typeof value === 'string' || typeof value === 'number'
    ? value
    : String(value);
}

function dataGridColumnSearchValue<Row, Key extends string>(
  column: DataGridColumn<Row, Key>,
  row: Row,
): unknown {
  const raw = column.value(row);
  const displayed = column.searchValue?.(row);
  if (displayed === undefined || displayed === null) return raw;
  return `${String(raw ?? '')} ${String(displayed)}`;
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
  const [globalSearch, setGlobalSearch] = useState('');
  const [order, setOrder] = useState<Key[]>(() => [...allKeys]);
  const [hidden, setHidden] = useState<Key[]>([]);

  const normalizedOrder = useMemo(
    () => normalizeColumnOrder(allKeys, order),
    [allKeys, order],
  );
  const visibleKeys = useMemo(
    () => visibleColumnKeys(allKeys, {
      order: normalizedOrder,
      hidden,
    }),
    [allKeys, hidden, normalizedOrder],
  );
  const visibleColumns = useMemo(
    () => visibleKeys
      .map((key) => columnMap.get(key))
      .filter((column): column is DataGridColumn<Row, Key> => column !== undefined),
    [columnMap, visibleKeys],
  );
  const viewRows = useMemo(() => {
    const getValue = (row: Row, key: Key) => columnMap.get(key)?.value(row);
    const getSearchValue = (row: Row, key: Key) => {
      const column = columnMap.get(key);
      return column ? dataGridColumnSearchValue(column, row) : undefined;
    };
    const searchedRows = searchDataGridRows(
      rows,
      globalSearch,
      visibleKeys,
      getSearchValue,
    );
    return applyDataGridModel(
      searchedRows,
      filters,
      sorts,
      getValue,
    );
  }, [columnMap, filters, globalSearch, rows, sorts, visibleKeys]);
  const activeColumnFilterCount = (Object.values(filters) as Array<
    DataGridFilterValue | undefined
  >).filter(isDataGridFilterActive).length;
  const activeFilterCount = activeColumnFilterCount
    + (isDataGridSearchActive(globalSearch) ? 1 : 0);
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
    globalSearch,
    hidden,
    normalizedOrder,
    setFilters,
    setGlobalSearch,
    setHidden,
    setOrder,
    setSorts,
    sorts,
    viewRows,
    visibleColumns,
  };
}

function buildSortStatus<Row, Key extends string>(
  sorts: readonly DataGridSort<Key>[],
  columns: ReadonlyMap<Key, DataGridColumn<Row, Key>>,
): string {
  if (sorts.length === 0) return 'Nicio sortare activă.';
  return `Sortare activă: ${sorts.map((sort, index) => {
    const label = columns.get(sort.key)?.label ?? sort.key;
    const direction = sort.direction === 'asc' ? 'crescător' : 'descrescător';
    return `${index + 1}. ${label}, ${direction}`;
  }).join('; ')}.`;
}

function DataGridHead<Row, Key extends string>({
  columns,
  sorts,
  filters,
  onSort,
  onFilter,
  sortStatusId,
}: {
  columns: readonly DataGridColumn<Row, Key>[];
  sorts: readonly DataGridSort<Key>[];
  filters: DataGridFilters<Key>;
  onSort: (key: Key, append: boolean) => void;
  onFilter: (key: Key, filter: DataGridFilterValue | undefined) => void;
  sortStatusId: string;
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
                aria-label={`Sortează după ${column.label}`}
                aria-describedby={sortStatusId}
                title="Click pentru sortare; Shift+click pentru sortare multiplă"
                className="flex w-full min-w-0 items-center justify-between gap-1 rounded text-left hover:text-indigo-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:hover:text-indigo-300"
              >
                <span className="min-w-0 whitespace-normal break-words">
                  {column.label}
                </span>
                <span
                  className="inline-flex shrink-0 items-center gap-0.5"
                  aria-hidden="true"
                >
                  {sort ? (
                    sort.direction === 'asc'
                      ? <ChevronUp size={11} />
                      : <ChevronDown size={11} />
                  ) : (
                    <ArrowUpDown
                      size={10}
                      className="text-slate-300 dark:text-slate-600"
                    />
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
            <td
              key={column.key}
              className="px-1 py-1 align-top"
              data-testid={`data-grid-filter-cell-${column.key}`}
            >
              <DataGridFilterControl
                column={column}
                filter={filters[column.key]}
                onChange={(filter) => onFilter(column.key, filter)}
              />
            </td>
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
          <td
            colSpan={columns.length}
            className="px-4 py-8 text-center text-sm font-semibold text-slate-500 dark:text-slate-400"
          >
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
            <td
              key={column.key}
              className={column.cellClassName ?? 'px-1.5 py-1 whitespace-nowrap align-middle leading-tight'}
            >
              {column.render(row)}
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

function DataGridGlobalSearch({
  title,
  tableId,
  value,
  onChange,
}: {
  title: string;
  tableId: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="relative min-w-52 flex-1 sm:max-w-64 sm:flex-none">
      <Search
        size={12}
        aria-hidden="true"
        className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"
      />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label={`Caută în coloanele afișate din ${title}`}
        aria-controls={tableId}
        placeholder="Caută în coloanele afișate"
        className="w-full rounded-lg border border-slate-200 bg-white py-1 pl-7 pr-2 text-[11px] font-semibold text-slate-700 outline-none placeholder:font-medium placeholder:text-slate-400 focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
    </div>
  );
}

function DataGridToolbar<Row, Key extends string>({
  title,
  rowsLength,
  tableId,
  search,
  activeFilterCount,
  onSearchChange,
  onClearFilters,
  columns,
  allKeys,
  order,
  hidden,
  onMove,
  onToggle,
  onResetColumns,
  exportFilename,
  exportSheetName,
  exportColumns,
  exportRows,
}: {
  title: string;
  rowsLength: number;
  tableId: string;
  search: string;
  activeFilterCount: number;
  onSearchChange: (value: string) => void;
  onClearFilters: () => void;
  columns: ReadonlyMap<Key, DataGridColumn<Row, Key>>;
  allKeys: readonly Key[];
  order: readonly Key[];
  hidden: readonly Key[];
  onMove: (key: Key, offset: -1 | 1) => void;
  onToggle: (key: Key) => void;
  onResetColumns: () => void;
  exportFilename: string;
  exportSheetName: string;
  exportColumns: ExportColumn<Row>[];
  exportRows: readonly Row[];
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-1.5">
      {rowsLength > 0 && (
        <DataGridGlobalSearch
          title={title}
          tableId={tableId}
          value={search}
          onChange={onSearchChange}
        />
      )}
      {activeFilterCount > 0 && (
        <button
          type="button"
          onClick={onClearFilters}
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-bold text-slate-600 hover:border-indigo-200 hover:text-indigo-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
        >
          <RotateCcw size={12} />
          Șterge filtrele ({activeFilterCount})
        </button>
      )}
      <DataGridColumnMenu
        columns={columns}
        allKeys={allKeys}
        order={order}
        hidden={hidden}
        onMove={onMove}
        onToggle={onToggle}
        onReset={onResetColumns}
      />
      <ExportTableButton
        filename={exportFilename}
        sheetName={exportSheetName}
        columns={exportColumns}
        rows={exportRows}
      />
    </div>
  );
}

export function DataGrid<Row, Key extends string>(props: DataGridProps<Row, Key>) {
  const state = useDataGridState(props);
  const titleId = useId();
  const tableId = useId();
  const sortStatusId = useId();
  const sortStatus = buildSortStatus(state.sorts, state.columnMap);

  const setFilter = (
    key: Key,
    filter: DataGridFilterValue | undefined,
  ) => {
    state.setFilters((current) => {
      const next = { ...current };
      if (isDataGridFilterActive(filter)) next[key] = filter;
      else delete next[key];
      return next;
    });
  };

  const updateSort = (key: Key, append: boolean) => {
    const next = nextDataGridSorts(state.sorts, key, {
      append,
      defaultAscKeys: state.defaultAscKeys,
    });
    state.setSorts(next);
    props.onSortChange?.(next);
  };

  const clearFilters = () => {
    state.setFilters({});
    state.setGlobalSearch('');
  };

  const resultLabel = state.viewRows.length === props.rows.length
    ? `${props.rows.length} înregistrări`
    : `${state.viewRows.length} din ${props.rows.length} înregistrări`;

  return (
    <section
      aria-labelledby={titleId}
      className="rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900/70"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-2 dark:border-slate-800">
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-bold text-slate-800 dark:text-slate-100">
            {props.icon}
            <h3 id={titleId}>{props.title}</h3>
          </div>
          <div className="mt-0.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
            {props.subtitle}{props.subtitle ? ' · ' : ''}{resultLabel}
          </div>
        </div>
        <DataGridToolbar
          title={props.title}
          rowsLength={props.rows.length}
          tableId={tableId}
          search={state.globalSearch}
          activeFilterCount={state.activeFilterCount}
          onSearchChange={state.setGlobalSearch}
          onClearFilters={clearFilters}
          columns={state.columnMap}
          allKeys={state.allKeys}
          order={state.normalizedOrder}
          hidden={state.hidden}
          onMove={(key, offset) => state.setOrder((current) =>
            moveColumnKey(state.allKeys, current, key, offset))}
          onToggle={(key) => state.setHidden((current) =>
            toggleColumnVisibility(state.allKeys, current, key))}
          onResetColumns={() => {
            state.setOrder([...state.allKeys]);
            state.setHidden([]);
          }}
          exportFilename={props.exportFilename}
          exportSheetName={props.exportSheetName}
          exportColumns={props.exportColumns ?? state.exportColumns}
          exportRows={state.viewRows}
        />
      </div>

      <DataGridHiddenFilters
        columns={props.columns}
        hidden={state.hidden}
        filters={state.filters}
        tableId={tableId}
        onClear={(key) => setFilter(key, undefined)}
      />

      <p
        id={sortStatusId}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {sortStatus}
      </p>

      <div className="max-h-[360px] overflow-auto rounded-b-2xl">
        <table
          id={tableId}
          className="w-full min-w-max table-auto text-xs"
          aria-labelledby={titleId}
        >
          <DataGridHead
            columns={state.visibleColumns}
            sorts={state.sorts}
            filters={state.filters}
            onSort={updateSort}
            onFilter={setFilter}
            sortStatusId={sortStatusId}
          />
          <DataGridBody
            rows={state.viewRows}
            columns={state.visibleColumns}
            rowKey={props.rowKey}
            emptyLabel={props.emptyLabel ?? 'Nu există rezultate pentru filtrele selectate.'}
          />
        </table>
      </div>
    </section>
  );
}
