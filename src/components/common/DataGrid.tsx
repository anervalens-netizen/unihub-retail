import {
  RotateCcw,
  Search,
} from 'lucide-react';
import {
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
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
  DataGridHiddenFilters,
} from './DataGridControls';
import {
  DataGridBody,
  DataGridHead,
  type DataGridColumnWidths,
} from './DataGridTableSections';
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

function useDataGridColumnWidths<Key extends string>() {
  const [columnWidths, setColumnWidths] = useState<DataGridColumnWidths<Key>>({});
  const setColumnWidth = (key: Key, width: number | undefined) => {
    setColumnWidths((current) => {
      if (width === undefined) {
        const next = { ...current };
        delete next[key];
        return next;
      }
      return { ...current, [key]: width };
    });
  };
  return {
    columnWidths,
    hasCustomWidths: Object.keys(columnWidths).length > 0,
    resetColumnWidths: () => setColumnWidths({}),
    setColumnWidth,
  };
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
  const fixedLeftKey = useMemo(
    () => columns.find((column) => column.fixedLeft)?.key,
    [columns],
  );
  const [sorts, setSorts] = useState<DataGridSort<Key>[]>(
    () => initialSort.map((sort) => ({ ...sort })),
  );
  const [filters, setFilters] = useState<DataGridFilters<Key>>({});
  const [globalSearch, setGlobalSearch] = useState('');
  const [order, setOrder] = useState<Key[]>(() => [...allKeys]);
  const [hidden, setHidden] = useState<Key[]>([]);
  const widthState = useDataGridColumnWidths<Key>();

  const normalizedOrder = useMemo(() => {
    const normalized = normalizeColumnOrder(allKeys, order);
    if (!fixedLeftKey || !normalized.includes(fixedLeftKey)) return normalized;
    return [fixedLeftKey, ...normalized.filter((key) => key !== fixedLeftKey)];
  }, [allKeys, fixedLeftKey, order]);
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

  const setFilter = (
    key: Key,
    filter: DataGridFilterValue | undefined,
  ) => {
    setFilters((current) => {
      const next = { ...current };
      if (isDataGridFilterActive(filter)) next[key] = filter;
      else delete next[key];
      return next;
    });
  };

  return {
    activeFilterCount,
    allKeys,
    columnMap,
    defaultAscKeys,
    exportColumns,
    filters,
    fixedLeftKey,
    globalSearch,
    hidden,
    normalizedOrder,
    setFilter,
    setFilters,
    setGlobalSearch,
    setHidden,
    setOrder,
    setSorts,
    sorts,
    viewRows,
    visibleColumns,
    hasVisibleCustomWidths: visibleKeys.some((key) => widthState.columnWidths[key] !== undefined),
    ...widthState,
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

function DataGridGlobalSearch({
  title,
  tableId,
  value,
  onChange,
  inputRef,
}: {
  title: string;
  tableId: string;
  value: string;
  onChange: (value: string) => void;
  inputRef?: RefObject<HTMLInputElement | null>;
}) {
  return (
    <div className="relative min-w-52 flex-1 sm:max-w-64 sm:flex-none">
      <Search
        size={12}
        aria-hidden="true"
        className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"
      />
      <input
        ref={inputRef ?? undefined}
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
  fixedLeftKey,
  onMove,
  onToggle,
  onResetColumns,
  hasCustomWidths,
  onResetWidths,
  exportFilename,
  exportSheetName,
  exportColumns,
  exportRows,
  searchInputRef,
  clearAllRef,
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
  fixedLeftKey?: Key;
  onMove: (key: Key, offset: -1 | 1) => void;
  onToggle: (key: Key) => void;
  onResetColumns: () => void;
  hasCustomWidths: boolean;
  onResetWidths: () => void;
  exportFilename: string;
  exportSheetName: string;
  exportColumns: ExportColumn<Row>[];
  exportRows: readonly Row[];
  searchInputRef?: RefObject<HTMLInputElement | null>;
  clearAllRef?: RefObject<HTMLButtonElement | null>;
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-1.5">
      {rowsLength > 0 && (
        <DataGridGlobalSearch
          title={title}
          tableId={tableId}
          value={search}
          onChange={onSearchChange}
          inputRef={searchInputRef}
        />
      )}
      {activeFilterCount > 0 && (
        <button
          ref={clearAllRef ?? undefined}
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
        fixedLeftKey={fixedLeftKey}
        onMove={onMove}
        onToggle={onToggle}
        onReset={onResetColumns}
        hasCustomWidths={hasCustomWidths}
        onResetWidths={onResetWidths}
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

function nextDataGridColumnOrder<Key extends string>(
  allKeys: readonly Key[],
  order: readonly Key[],
  fixedLeftKey: Key | undefined,
  key: Key,
  offset: -1 | 1,
): Key[] {
  const index = order.indexOf(key);
  const targetIndex = index + offset;
  if (
    index < 0
    || targetIndex < 0
    || targetIndex >= order.length
    || key === fixedLeftKey
    || order[targetIndex] === fixedLeftKey
  ) return [...order];
  return moveColumnKey(allKeys, order, key, offset);
}

function DataGridScrollTable<Row, Key extends string>({
  tableId,
  titleId,
  sortStatusId,
  columns,
  rows,
  sorts,
  filters,
  columnWidths,
  fixedLeftKey,
  hasVisibleCustomWidths,
  onSort,
  onFilter,
  onResizeColumn,
  rowKey,
  emptyLabel,
}: {
  tableId: string;
  titleId: string;
  sortStatusId: string;
  columns: readonly DataGridColumn<Row, Key>[];
  rows: readonly Row[];
  sorts: readonly DataGridSort<Key>[];
  filters: DataGridFilters<Key>;
  columnWidths: DataGridColumnWidths<Key>;
  fixedLeftKey?: Key;
  hasVisibleCustomWidths: boolean;
  onSort: (key: Key, append: boolean) => void;
  onFilter: (key: Key, filter: DataGridFilterValue | undefined) => void;
  onResizeColumn: (key: Key, width: number | undefined) => void;
  rowKey: (row: Row, index: number) => string;
  emptyLabel: string;
}) {
  return (
    <div className="max-h-[360px] overflow-auto rounded-b-2xl">
      <table
        id={tableId}
        className={`${hasVisibleCustomWidths ? 'w-max' : 'w-full min-w-max'} table-auto text-xs`}
        aria-labelledby={titleId}
      >
        <DataGridHead
          columns={columns}
          sorts={sorts}
          filters={filters}
          columnWidths={columnWidths}
          fixedLeftKey={fixedLeftKey}
          onSort={onSort}
          onFilter={onFilter}
          onResizeColumn={onResizeColumn}
          sortStatusId={sortStatusId}
        />
        <DataGridBody
          rows={rows}
          columns={columns}
          fixedLeftKey={fixedLeftKey}
          rowKey={rowKey}
          emptyLabel={emptyLabel}
        />
      </table>
    </div>
  );
}

export function DataGrid<Row, Key extends string>(props: DataGridProps<Row, Key>) {
  const state = useDataGridState(props);
  const titleId = useId();
  const tableId = useId();
  const sortStatusId = useId();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const clearAllRef = useRef<HTMLButtonElement>(null);
  const sortStatus = buildSortStatus(state.sorts, state.columnMap);

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
          fixedLeftKey={state.fixedLeftKey}
          onMove={(key, offset) => state.setOrder(nextDataGridColumnOrder(
            state.allKeys,
            state.normalizedOrder,
            state.fixedLeftKey,
            key,
            offset,
          ))}
          onToggle={(key) => {
            if (key === state.fixedLeftKey) return;
            state.setHidden((current) =>
              toggleColumnVisibility(state.allKeys, current, key));
          }}
          onResetColumns={() => {
            state.setOrder([...state.allKeys]);
            state.setHidden([]);
          }}
          hasCustomWidths={state.hasCustomWidths}
          onResetWidths={state.resetColumnWidths}
          exportFilename={props.exportFilename}
          exportSheetName={props.exportSheetName}
          exportColumns={props.exportColumns ?? state.exportColumns}
          exportRows={state.viewRows}
          searchInputRef={searchInputRef}
          clearAllRef={clearAllRef}
        />
      </div>

      <DataGridHiddenFilters
        columns={props.columns}
        hidden={state.hidden}
        filters={state.filters}
        tableId={tableId}
        searchInputRef={searchInputRef}
        clearAllRef={clearAllRef}
        onClear={(key) => state.setFilter(key, undefined)}
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

      <DataGridScrollTable
        tableId={tableId}
        titleId={titleId}
        sortStatusId={sortStatusId}
        columns={state.visibleColumns}
        rows={state.viewRows}
        sorts={state.sorts}
        filters={state.filters}
        columnWidths={state.columnWidths}
        fixedLeftKey={state.fixedLeftKey}
        hasVisibleCustomWidths={state.hasVisibleCustomWidths}
        onSort={updateSort}
        onFilter={state.setFilter}
        onResizeColumn={state.setColumnWidth}
        rowKey={props.rowKey}
        emptyLabel={props.emptyLabel ?? 'Nu există rezultate pentru filtrele selectate.'}
      />
    </section>
  );
}
