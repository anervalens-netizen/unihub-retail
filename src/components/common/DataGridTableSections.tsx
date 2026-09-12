import {
  ArrowUpDown,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import type { CSSProperties, MouseEvent } from 'react';

import {
  type DataGridFilterValue,
  type DataGridFilters,
  type DataGridSort,
} from '../../lib/dataGrid';
import {
  DataGridFilterControl,
  DataGridResizeHandle,
} from './DataGridControls';
import type { DataGridColumn } from './dataGridTypes';

export type DataGridColumnWidths<Key extends string> = Partial<Record<Key, number>>;

function columnWidthStyle(width: number | undefined): CSSProperties | undefined {
  return width === undefined
    ? undefined
    : { width, minWidth: width, maxWidth: width };
}

export function DataGridHead<Row, Key extends string>({
  columns,
  sorts,
  filters,
  columnWidths,
  fixedLeftKey,
  onSort,
  onFilter,
  onResizeColumn,
  sortStatusId,
}: {
  columns: readonly DataGridColumn<Row, Key>[];
  sorts: readonly DataGridSort<Key>[];
  filters: DataGridFilters<Key>;
  columnWidths: DataGridColumnWidths<Key>;
  fixedLeftKey?: Key;
  onSort: (key: Key, append: boolean) => void;
  onFilter: (key: Key, filter: DataGridFilterValue | undefined) => void;
  onResizeColumn: (key: Key, width: number | undefined) => void;
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
          const width = columnWidths[column.key];
          const fixedLeft = column.key === fixedLeftKey;
          return (
            <th
              key={column.key}
              scope="col"
              aria-sort={ariaSort}
              data-testid={`data-grid-header-${column.key}`}
              style={columnWidthStyle(width)}
              className={`${fixedLeft ? 'sticky left-0 z-20 border-r border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800' : 'relative'} px-1.5 py-1.5 align-bottom text-[11px] font-bold leading-tight ${column.headerClassName ?? ''}`}
            >
              <button
                type="button"
                onClick={(event: MouseEvent<HTMLButtonElement>) =>
                  onSort(column.key, event.shiftKey)}
                aria-label={`Sortează după ${column.label}`}
                aria-describedby={sortStatusId}
                title="Click pentru sortare; Shift+click pentru sortare multiplă"
                className="flex w-full min-w-0 items-center justify-between gap-1 rounded pr-1 text-left hover:text-indigo-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:hover:text-indigo-300"
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
              <DataGridResizeHandle
                label={column.label}
                width={width}
                onResize={(nextWidth) => onResizeColumn(column.key, nextWidth)}
              />
            </th>
          );
        })}
      </tr>
      {hasFilters && (
        <tr className="border-t border-slate-200/80 dark:border-slate-700">
          {columns.map((column) => {
            const fixedLeft = column.key === fixedLeftKey;
            return (
              <td
                key={column.key}
                style={columnWidthStyle(columnWidths[column.key])}
                className={`${fixedLeft ? 'sticky left-0 z-20 border-r border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800' : ''} px-1 py-1 align-top`}
                data-testid={`data-grid-filter-cell-${column.key}`}
              >
                <DataGridFilterControl
                  column={column}
                  filter={filters[column.key]}
                  onChange={(filter) => onFilter(column.key, filter)}
                />
              </td>
            );
          })}
        </tr>
      )}
    </thead>
  );
}

export function DataGridBody<Row, Key extends string>({
  rows,
  columns,
  fixedLeftKey,
  rowKey,
  emptyLabel,
}: {
  rows: readonly Row[];
  columns: readonly DataGridColumn<Row, Key>[];
  fixedLeftKey?: Key;
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
          className="group border-t border-slate-100 odd:bg-slate-50/35 hover:bg-indigo-50/50 dark:border-slate-800 dark:odd:bg-slate-900/20 dark:hover:bg-indigo-950/20"
        >
          {columns.map((column) => {
            const fixedLeft = column.key === fixedLeftKey;
            const cellClassName = column.cellClassName
              ?? 'px-1.5 py-1 whitespace-nowrap align-middle leading-tight';
            return (
              <td
                key={column.key}
                className={`${cellClassName} ${fixedLeft ? 'sticky left-0 z-[5] border-r border-slate-200 bg-white group-hover:bg-indigo-50/50 dark:border-slate-700 dark:bg-slate-900 dark:group-hover:bg-indigo-950/20' : ''}`}
              >
                {column.render(row)}
              </td>
            );
          })}
        </tr>
      ))}
    </tbody>
  );
}
