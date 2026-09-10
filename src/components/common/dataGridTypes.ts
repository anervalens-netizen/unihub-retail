import type { ReactNode } from 'react';

import type { ExportColumn } from '../../lib/tableExport';

export type DataGridFilterConfig =
  | { kind: 'text'; placeholder?: string }
  | {
      kind: 'enum';
      options: readonly { value: string; label: string }[];
      allLabel?: string;
    }
  | { kind: 'number'; step?: number };

export interface DataGridColumn<Row, Key extends string> {
  key: Key;
  label: string;
  value: (row: Row) => unknown;
  searchValue?: (row: Row) => unknown;
  render: (row: Row) => ReactNode;
  filter?: DataGridFilterConfig;
  defaultDirection?: 'asc' | 'desc';
  headerClassName?: string;
  cellClassName?: string;
  hideable?: boolean;
  fixedLeft?: boolean;
  exportHeader?: string;
  exportValue?: ExportColumn<Row>['value'];
  exportFormat?: ExportColumn<Row>['format'];
}
