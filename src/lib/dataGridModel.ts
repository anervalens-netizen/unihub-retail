export type DataGridCellValue = string | number | boolean | Date | null | undefined;

export type DataGridSortDirection = 'asc' | 'desc';

export interface DataGridColumn<Row> {
  id: string;
  header: string;
  value: (row: Row) => DataGridCellValue;
  compare?: (left: DataGridCellValue, right: DataGridCellValue) => number;
  exportValue?: (row: Row) => DataGridCellValue;
  defaultVisible?: boolean;
}

export interface DataGridSortRule {
  columnId: string;
  direction: DataGridSortDirection;
}

export interface DataGridTextFilter {
  kind: 'text';
  columnId: string;
  value: string;
  mode?: 'contains' | 'startsWith' | 'equals';
}

export interface DataGridEnumFilter {
  kind: 'enum';
  columnId: string;
  values: readonly string[];
}

export interface DataGridNumberFilter {
  kind: 'number';
  columnId: string;
  min?: number;
  max?: number;
}

export type DataGridFilter =
  | DataGridTextFilter
  | DataGridEnumFilter
  | DataGridNumberFilter;

export interface DataGridColumnState {
  order?: readonly string[];
  hidden?: readonly string[];
}

export interface DataGridState {
  sort?: readonly DataGridSortRule[];
  filters?: readonly DataGridFilter[];
  columns?: DataGridColumnState;
}

export interface DataGridResult<Row> {
  rows: Row[];
  columns: DataGridColumn<Row>[];
}

export interface DataGridExport {
  headers: string[];
  rows: DataGridCellValue[][];
}

const ROMANIAN_LOCALE = 'ro-RO';

function normalizeText(value: DataGridCellValue): string {
  if (value === null || value === undefined) return '';
  if (value instanceof Date) return value.toISOString();
  return String(value).trim().toLocaleLowerCase(ROMANIAN_LOCALE);
}

export function parseDataGridNumber(value: DataGridCellValue): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string') return null;

  const compact = value
    .trim()
    .replace(/\s|\u00a0/g, '')
    .replace(/%$/, '');
  if (!compact) return null;

  const normalized = compact.includes(',')
    ? compact.replace(/\./g, '').replace(',', '.')
    : compact;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

export function compareDataGridValues(
  left: DataGridCellValue,
  right: DataGridCellValue,
): number {
  const leftMissing = left === null || left === undefined || left === '';
  const rightMissing = right === null || right === undefined || right === '';
  if (leftMissing || rightMissing) {
    if (leftMissing && rightMissing) return 0;
    return leftMissing ? 1 : -1;
  }

  if (left instanceof Date || right instanceof Date) {
    const leftTime = left instanceof Date ? left.getTime() : Date.parse(String(left));
    const rightTime = right instanceof Date ? right.getTime() : Date.parse(String(right));
    if (Number.isFinite(leftTime) && Number.isFinite(rightTime)) return leftTime - rightTime;
  }

  const leftNumber = parseDataGridNumber(left);
  const rightNumber = parseDataGridNumber(right);
  if (leftNumber !== null && rightNumber !== null) return leftNumber - rightNumber;

  return normalizeText(left).localeCompare(normalizeText(right), ROMANIAN_LOCALE, {
    numeric: true,
    sensitivity: 'base',
  });
}

function indexColumns<Row>(columns: readonly DataGridColumn<Row>[]): Map<string, DataGridColumn<Row>> {
  return new Map(columns.map((column) => [column.id, column]));
}

export function sortDataGridRows<Row>(
  rows: readonly Row[],
  columns: readonly DataGridColumn<Row>[],
  rules: readonly DataGridSortRule[] = [],
): Row[] {
  if (rules.length === 0) return [...rows];

  const columnsById = indexColumns(columns);
  const activeRules = rules.flatMap((rule) => {
    const column = columnsById.get(rule.columnId);
    return column ? [{ rule, column }] : [];
  });
  if (activeRules.length === 0) return [...rows];

  return rows
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      for (const { rule, column } of activeRules) {
        const comparison = (column.compare ?? compareDataGridValues)(
          column.value(left.row),
          column.value(right.row),
        );
        if (comparison !== 0) return rule.direction === 'asc' ? comparison : -comparison;
      }
      return left.index - right.index;
    })
    .map(({ row }) => row);
}

function matchesFilter<Row>(
  row: Row,
  column: DataGridColumn<Row>,
  filter: DataGridFilter,
): boolean {
  const value = column.value(row);

  if (filter.kind === 'text') {
    const expected = filter.value.trim().toLocaleLowerCase(ROMANIAN_LOCALE);
    if (!expected) return true;
    const actual = normalizeText(value);
    if (filter.mode === 'equals') return actual === expected;
    if (filter.mode === 'startsWith') return actual.startsWith(expected);
    return actual.includes(expected);
  }

  if (filter.kind === 'enum') {
    if (filter.values.length === 0) return true;
    const accepted = new Set(filter.values.map((item) => item.toLocaleLowerCase(ROMANIAN_LOCALE)));
    return accepted.has(normalizeText(value));
  }

  const numericValue = parseDataGridNumber(value);
  if (numericValue === null) return false;
  if (filter.min !== undefined && numericValue < filter.min) return false;
  if (filter.max !== undefined && numericValue > filter.max) return false;
  return true;
}

export function filterDataGridRows<Row>(
  rows: readonly Row[],
  columns: readonly DataGridColumn<Row>[],
  filters: readonly DataGridFilter[] = [],
): Row[] {
  if (filters.length === 0) return [...rows];

  const columnsById = indexColumns(columns);
  const activeFilters = filters.flatMap((filter) => {
    const column = columnsById.get(filter.columnId);
    return column ? [{ filter, column }] : [];
  });
  if (activeFilters.length === 0) return [...rows];

  return rows.filter((row) =>
    activeFilters.every(({ filter, column }) => matchesFilter(row, column, filter)),
  );
}

export function resolveDataGridColumns<Row>(
  columns: readonly DataGridColumn<Row>[],
  state: DataGridColumnState = {},
): DataGridColumn<Row>[] {
  const columnsById = indexColumns(columns);
  const hidden = new Set(state.hidden ?? []);
  const ordered: DataGridColumn<Row>[] = [];
  const included = new Set<string>();

  for (const id of state.order ?? []) {
    const column = columnsById.get(id);
    if (!column || hidden.has(id) || column.defaultVisible === false || included.has(id)) continue;
    ordered.push(column);
    included.add(id);
  }

  for (const column of columns) {
    if (hidden.has(column.id) || column.defaultVisible === false || included.has(column.id)) continue;
    ordered.push(column);
    included.add(column.id);
  }

  return ordered;
}

export function applyDataGridState<Row>(
  rows: readonly Row[],
  columns: readonly DataGridColumn<Row>[],
  state: DataGridState = {},
): DataGridResult<Row> {
  const filteredRows = filterDataGridRows(rows, columns, state.filters);
  return {
    rows: sortDataGridRows(filteredRows, columns, state.sort),
    columns: resolveDataGridColumns(columns, state.columns),
  };
}

export function buildDataGridExport<Row>(
  rows: readonly Row[],
  columns: readonly DataGridColumn<Row>[],
  state: DataGridState = {},
): DataGridExport {
  const result = applyDataGridState(rows, columns, state);
  return {
    headers: result.columns.map((column) => column.header),
    rows: result.rows.map((row) =>
      result.columns.map((column) => (column.exportValue ?? column.value)(row)),
    ),
  };
}
