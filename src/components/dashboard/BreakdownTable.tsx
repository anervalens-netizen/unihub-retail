import type { ReactNode } from 'react';

import type { ExportColumn } from '../../lib/tableExport';
import { ExportTableButton } from '../ExportTableButton';
import { SortableHeader } from './DashboardWidgets';

export interface BreakdownColumn<Row, SortKey extends string> {
  key: SortKey;
  label: string;
  headerClassName?: string;
  cellClassName?: string | ((row: Row) => string);
  render: (row: Row) => ReactNode;
}

interface BreakdownTableProps<Row, SortKey extends string> {
  title: string;
  icon?: ReactNode;
  subtitle: string;
  rows: Row[];
  columns: BreakdownColumn<Row, SortKey>[];
  sortKey: SortKey;
  sortDirection: 'asc' | 'desc';
  onSort: (key: SortKey) => void;
  rowKey: (row: Row) => string;
  exportFilename: string;
  exportSheetName: string;
  exportColumns: ExportColumn<Row>[];
}

const TABLE_MAX_HEIGHT_CLASS = 'max-h-[26rem]';
const TABLE_CLASS = 'w-max min-w-full table-auto border-collapse text-xs lg:text-[13px]';
const HEADER_CLASS = 'px-2 py-1.5 align-bottom whitespace-normal text-[11px] leading-tight lg:text-xs';
const DEFAULT_CELL_CLASS = 'px-2 py-1.5 whitespace-nowrap align-middle leading-tight text-right tabular-nums';

export function BreakdownTable<Row, SortKey extends string>({
  title,
  icon,
  subtitle,
  rows,
  columns,
  sortKey,
  sortDirection,
  onSort,
  rowKey,
  exportFilename,
  exportSheetName,
  exportColumns,
}: BreakdownTableProps<Row, SortKey>) {
  return (
    <div className="glass rounded-3xl p-3">
      <div className="mb-2 flex min-h-10 items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            {icon}
            <h3 className="text-sm font-bold">{title}</h3>
          </div>
          <p className="text-[11px] text-slate-500">{subtitle}</p>
        </div>
        <ExportTableButton
          filename={exportFilename}
          sheetName={exportSheetName}
          rows={rows}
          columns={exportColumns}
        />
      </div>
      <div className={`overflow-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 ${TABLE_MAX_HEIGHT_CLASS}`}>
        <table className={TABLE_CLASS}>
          <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800/95">
            <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
              {columns.map((column) => (
                <SortableHeader
                  key={column.key}
                  label={column.label}
                  active={sortKey === column.key}
                  direction={sortDirection}
                  onClick={() => onSort(column.key)}
                  className={`${HEADER_CLASS} ${column.headerClassName ?? 'max-w-[4.5rem]'}`}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr
                key={rowKey(row)}
                className={index % 2 === 0 ? 'bg-white/70 dark:bg-slate-900/20' : 'bg-slate-50/70 dark:bg-slate-900/40'}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={
                      typeof column.cellClassName === 'function'
                        ? column.cellClassName(row)
                        : column.cellClassName ?? DEFAULT_CELL_CLASS
                    }
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
