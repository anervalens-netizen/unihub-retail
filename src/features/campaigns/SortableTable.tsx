import type React from 'react';
import type { ExportColumn } from '../../lib/tableExport';
import { ExportTableButton } from '../../components/ExportTableButton';
import { SortableTableHeader, TableHeaderCell } from '../../components/common/TableHeader';
import { useSortable, type SortDirection } from '../../lib/useSortable';

interface ColDef<T> {
  key: keyof T | 'rank';
  label: string;
  align?: 'left' | 'right';
  sortable?: boolean;
  exportValue?: (row: T, index: number) => string | number | null | undefined;
  render: (row: T, index: number) => React.ReactNode;
}

export function SortableTable<T extends Record<string, unknown>>({
  rows,
  columns,
  defaultSortKey,
  defaultSortDir = 'desc',
  maxHeightClass = 'max-h-[360px]',
  exportFilename,
  exportSheetName,
  exportColumns,
}: {
  rows: T[];
  columns: ColDef<T>[];
  defaultSortKey: keyof T;
  defaultSortDir?: SortDirection;
  maxHeightClass?: string;
  exportFilename: string;
  exportSheetName: string;
  exportColumns?: ExportColumn<T>[];
}) {
  const {
    sorted,
    sortKey,
    direction: sortDir,
    handleSort: handleSortableSort,
  } = useSortable<T, keyof T>({
    rows,
    key: defaultSortKey,
    direction: defaultSortDir,
  });

  function handleSort(key: keyof T | 'rank') {
    if (key === 'rank') return;
    handleSortableSort(key as keyof T);
  }

  return (
    <div>
      <div className="mb-1 flex justify-end">
        <ExportTableButton<T>
          filename={exportFilename}
          sheetName={exportSheetName}
          rows={sorted}
          columns={exportColumns ?? columns.map((column): ExportColumn<T> => ({
            header: column.label,
            value: (row, index): string | number | null | undefined => {
              if (column.exportValue) return column.exportValue(row, index);
              if (column.key === 'rank') return index + 1;
              const value: unknown = row[column.key as keyof T];
              if (value === null || value === undefined) return null;
              if (typeof value === 'string' || typeof value === 'number') return value;
              return String(value);
            },
          }))}
        />
      </div>
      <div
        className={`${maxHeightClass} overflow-auto rounded-xl`}
        style={{ scrollbarWidth: 'thin', scrollbarColor: '#c7d2fe transparent' }}
      >
        <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            {columns.map((col) => (
              col.sortable !== false && col.key !== 'rank' ? (
                <SortableTableHeader
                  key={String(col.key)}
                  label={col.label}
                  active={sortKey === col.key}
                  direction={sortDir}
                  onClick={() => handleSort(col.key)}
                  align={col.align ?? 'left'}
                  className="sticky top-0 z-10 bg-indigo-50/90 backdrop-blur-sm dark:bg-indigo-950/70"
                />
              ) : (
                <TableHeaderCell
                  key={String(col.key)}
                  align={col.align ?? 'left'}
                  className="sticky top-0 z-10 bg-indigo-50/90 backdrop-blur-sm dark:bg-indigo-950/70"
                >
                  {col.label}
                </TableHeaderCell>
              )
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, index) => (
            <tr
              key={index}
              className={index % 2 === 0 ? 'bg-indigo-50/30 dark:bg-indigo-900/10' : ''}
            >
              {columns.map((col) => (
                <td
                  key={String(col.key)}
                  className={`px-2 py-1.5 ${col.align === 'right' ? 'text-right' : 'text-left'}`}
                >
                  {col.render(row, index)}
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
