import {
  compareSortableValues,
  initialSortDirection,
  normalizeSortableValue,
  type SortDirection,
} from './useSortable';

export interface DataGridSort<Key extends string> {
  key: Key;
  direction: SortDirection;
}

export type DataGridFilterValue =
  | { kind: 'text'; value: string }
  | { kind: 'enum'; value: string }
  | { kind: 'number'; min: number | null; max: number | null };

export type DataGridFilters<Key extends string> = Partial<
  Record<Key, DataGridFilterValue>
>;

export interface DataGridColumnState<Key extends string> {
  order: Key[];
  hidden: Key[];
}

type ValueGetter<Row, Key extends string> = (row: Row, key: Key) => unknown;

function normalizeFilterText(value: unknown): string {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('ro-RO')
    .trim();
}

function numericFilterValue(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const normalized = normalizeSortableValue(value);
  return typeof normalized === 'number' && Number.isFinite(normalized)
    ? normalized
    : null;
}

export function isDataGridFilterActive(filter: DataGridFilterValue | undefined): boolean {
  if (!filter) return false;
  if (filter.kind === 'number') {
    return (filter.min !== null && Number.isFinite(filter.min))
      || (filter.max !== null && Number.isFinite(filter.max));
  }
  return normalizeFilterText(filter.value) !== '';
}

function matchesDataGridFilter(value: unknown, filter: DataGridFilterValue): boolean {
  if (filter.kind === 'text') {
    return normalizeFilterText(value).includes(normalizeFilterText(filter.value));
  }
  if (filter.kind === 'enum') {
    return normalizeFilterText(value) === normalizeFilterText(filter.value);
  }
  const numeric = numericFilterValue(value);
  if (numeric === null) return false;
  const min = filter.min !== null && Number.isFinite(filter.min) ? filter.min : null;
  const max = filter.max !== null && Number.isFinite(filter.max) ? filter.max : null;
  if (min !== null && numeric < min) return false;
  if (max !== null && numeric > max) return false;
  return true;
}

export function filterDataGridRows<Row, Key extends string>(
  rows: readonly Row[],
  filters: DataGridFilters<Key>,
  getValue: ValueGetter<Row, Key>,
): Row[] {
  const activeFilters = (Object.entries(filters) as Array<
    [Key, DataGridFilterValue | undefined]
  >).filter((entry): entry is [Key, DataGridFilterValue] =>
    isDataGridFilterActive(entry[1]),
  );
  if (activeFilters.length === 0) return [...rows];
  return rows.filter((row) =>
    activeFilters.every(([key, filter]) => matchesDataGridFilter(getValue(row, key), filter)),
  );
}

export function sortDataGridRows<Row, Key extends string>(
  rows: readonly Row[],
  sorts: readonly DataGridSort<Key>[],
  getValue: ValueGetter<Row, Key>,
): Row[] {
  if (sorts.length === 0) return [...rows];
  return rows
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      for (const sort of sorts) {
        const factor = sort.direction === 'asc' ? 1 : -1;
        const result = compareSortableValues(
          getValue(left.row, sort.key),
          getValue(right.row, sort.key),
        );
        if (result !== 0) return result * factor;
      }
      return left.index - right.index;
    })
    .map((entry) => entry.row);
}

export function applyDataGridModel<Row, Key extends string>(
  rows: readonly Row[],
  filters: DataGridFilters<Key>,
  sorts: readonly DataGridSort<Key>[],
  getValue: ValueGetter<Row, Key>,
): Row[] {
  return sortDataGridRows(filterDataGridRows(rows, filters, getValue), sorts, getValue);
}

export function nextDataGridSorts<Key extends string>(
  current: readonly DataGridSort<Key>[],
  key: Key,
  options: {
    append?: boolean;
    defaultAscKeys?: readonly Key[];
  } = {},
): DataGridSort<Key>[] {
  const { append = false, defaultAscKeys = [] } = options;
  const existingIndex = current.findIndex((sort) => sort.key === key);
  if (!append) {
    const existing = existingIndex >= 0 ? current[existingIndex] : undefined;
    return [{
      key,
      direction: existing
        ? existing.direction === 'asc' ? 'desc' : 'asc'
        : initialSortDirection(key, defaultAscKeys),
    }];
  }
  if (existingIndex >= 0) {
    return current.map((sort, index) =>
      index === existingIndex
        ? { ...sort, direction: sort.direction === 'asc' ? 'desc' : 'asc' }
        : { ...sort },
    );
  }
  return [
    ...current,
    { key, direction: initialSortDirection(key, defaultAscKeys) },
  ];
}

export function normalizeColumnOrder<Key extends string>(
  allKeys: readonly Key[],
  requestedOrder: readonly Key[] = [],
): Key[] {
  const available = new Set(allKeys);
  const seen = new Set<Key>();
  const ordered: Key[] = [];
  for (const key of [...requestedOrder, ...allKeys]) {
    if (!available.has(key) || seen.has(key)) continue;
    seen.add(key);
    ordered.push(key);
  }
  return ordered;
}

export function visibleColumnKeys<Key extends string>(
  allKeys: readonly Key[],
  state: DataGridColumnState<Key>,
): Key[] {
  const hidden = new Set(state.hidden.filter((key) => allKeys.includes(key)));
  const ordered = normalizeColumnOrder(allKeys, state.order);
  const visible = ordered.filter((key) => !hidden.has(key));
  return visible.length > 0 ? visible : ordered.slice(0, 1);
}

export function toggleColumnVisibility<Key extends string>(
  allKeys: readonly Key[],
  hiddenKeys: readonly Key[],
  key: Key,
): Key[] {
  if (!allKeys.includes(key)) return hiddenKeys.filter((item) => allKeys.includes(item));
  const hidden = new Set(hiddenKeys.filter((item) => allKeys.includes(item)));
  if (hidden.has(key)) {
    hidden.delete(key);
    return allKeys.filter((item) => hidden.has(item));
  }
  if (allKeys.length - hidden.size <= 1) return allKeys.filter((item) => hidden.has(item));
  hidden.add(key);
  return allKeys.filter((item) => hidden.has(item));
}

export function moveColumnKey<Key extends string>(
  allKeys: readonly Key[],
  requestedOrder: readonly Key[],
  key: Key,
  offset: -1 | 1,
): Key[] {
  const order = normalizeColumnOrder(allKeys, requestedOrder);
  const index = order.indexOf(key);
  const nextIndex = index + offset;
  if (index < 0 || nextIndex < 0 || nextIndex >= order.length) return order;
  const next = [...order];
  const adjacent = next[nextIndex];
  if (adjacent === undefined) return order;
  next[index] = adjacent;
  next[nextIndex] = key;
  return next;
}
