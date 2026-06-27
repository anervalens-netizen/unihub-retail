import { useMemo, useState } from 'react';

export type SortDirection = 'asc' | 'desc';

type SortablePrimitive = string | number;

export function normalizeSortableValue(value: unknown): SortablePrimitive {
  if (value === null || value === undefined) return Number.NEGATIVE_INFINITY;
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : Number.NEGATIVE_INFINITY;
  }
  if (value instanceof Date) {
    const timestamp = value.getTime();
    return Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY;
  }
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (typeof value === 'string') {
    const trimmed = value.trim().replace('%', '');
    const normalized = trimmed.includes(',')
      ? trimmed.replace(/\./g, '').replace(',', '.')
      : trimmed;
    if (normalized !== '') {
      const numeric = Number(normalized);
      if (Number.isFinite(numeric)) return numeric;
    }
    return value.toLowerCase();
  }
  return String(value).toLowerCase();
}

export function compareSortableValues(left: unknown, right: unknown): number {
  const a = normalizeSortableValue(left);
  const b = normalizeSortableValue(right);
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), 'ro');
}

export function sortRows<T, K extends keyof T>(
  rows: readonly T[],
  key: K,
  direction: SortDirection,
  getValue: (row: T, key: K) => unknown = (row, rowKey) => row[rowKey],
): T[] {
  const factor = direction === 'asc' ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      const result =
        compareSortableValues(
          getValue(left.row, key),
          getValue(right.row, key),
        ) * factor;
      return result === 0 ? left.index - right.index : result;
    })
    .map((entry) => entry.row);
}

export function initialSortDirection<K>(
  key: K,
  defaultAscKeys: readonly K[] = [],
  fallback: SortDirection = 'desc',
): SortDirection {
  return defaultAscKeys.includes(key) ? 'asc' : fallback;
}

export function nextSortState<K>(
  currentKey: K,
  currentDirection: SortDirection,
  nextKey: K,
  defaultAscKeys: readonly K[] = [],
): { key: K; direction: SortDirection } {
  if (Object.is(currentKey, nextKey)) {
    return {
      key: currentKey,
      direction: currentDirection === 'asc' ? 'desc' : 'asc',
    };
  }
  return {
    key: nextKey,
    direction: initialSortDirection(nextKey, defaultAscKeys),
  };
}

export function useSortable<T, K extends keyof T>({
  rows,
  key,
  direction = 'desc',
  defaultAscKeys = [],
  getValue,
}: {
  rows: readonly T[];
  key: K;
  direction?: SortDirection;
  defaultAscKeys?: readonly K[];
  getValue?: (row: T, key: K) => unknown;
}) {
  const [sortKey, setSortKey] = useState<K>(key);
  const [sortDirection, setSortDirection] = useState<SortDirection>(
    initialSortDirection(key, defaultAscKeys, direction),
  );

  const sorted = useMemo(
    () => sortRows(rows, sortKey, sortDirection, getValue),
    [rows, sortKey, sortDirection, getValue],
  );

  function handleSort(nextKey: K) {
    const next = nextSortState(
      sortKey,
      sortDirection,
      nextKey,
      defaultAscKeys,
    );
    setSortKey(next.key);
    setSortDirection(next.direction);
  }

  return {
    sorted,
    sortKey,
    direction: sortDirection,
    setSortKey,
    setDirection: setSortDirection,
    handleSort,
  };
}
