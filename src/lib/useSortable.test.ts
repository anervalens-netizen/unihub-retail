import { describe, expect, it } from 'vitest';
import {
  compareSortableValues,
  initialSortDirection,
  nextSortState,
  normalizeSortableValue,
  sortRows,
} from './useSortable';

interface Row {
  name: string;
  sales: number | null;
  pct: string;
}

const rows: Row[] = [
  { name: 'Beta', sales: 20, pct: '10%' },
  { name: 'Alfa', sales: 40, pct: '8,5%' },
  { name: 'Gamma', sales: null, pct: '12%' },
];

describe('normalizeSortableValue', () => {
  it('normalizes romanian decimal strings and percent suffixes', () => {
    expect(normalizeSortableValue('1.234,5%')).toBe(1234.5);
    expect(normalizeSortableValue('8,5%')).toBe(8.5);
  });

  it('normalizes nullish values to negative infinity', () => {
    expect(normalizeSortableValue(null)).toBe(Number.NEGATIVE_INFINITY);
    expect(normalizeSortableValue(undefined)).toBe(Number.NEGATIVE_INFINITY);
  });
});

describe('sortRows', () => {
  it('sorts numeric values descending by default semantics', () => {
    expect(sortRows(rows, 'sales', 'desc').map((row) => row.name)).toEqual([
      'Alfa',
      'Beta',
      'Gamma',
    ]);
  });

  it('sorts numeric strings ascending', () => {
    expect(sortRows(rows, 'pct', 'asc').map((row) => row.name)).toEqual([
      'Alfa',
      'Beta',
      'Gamma',
    ]);
  });

  it('keeps stable order for equal values', () => {
    const stableRows = [
      { name: 'A', value: 10 },
      { name: 'B', value: 10 },
    ];
    expect(sortRows(stableRows, 'value', 'desc').map((row) => row.name)).toEqual([
      'A',
      'B',
    ]);
  });
});

describe('sort direction helpers', () => {
  it('uses default asc keys for first activation', () => {
    expect(initialSortDirection('name', ['name'])).toBe('asc');
    expect(initialSortDirection('sales', ['name'])).toBe('desc');
  });

  it('toggles current key and initializes new keys', () => {
    expect(nextSortState('sales', 'desc', 'sales')).toEqual({
      key: 'sales',
      direction: 'asc',
    });
    expect(nextSortState('sales', 'desc', 'name', ['name'])).toEqual({
      key: 'name',
      direction: 'asc',
    });
  });
});

describe('compareSortableValues', () => {
  it('compares strings with romanian locale semantics', () => {
    expect(compareSortableValues('alfa', 'beta')).toBeLessThan(0);
  });
});
