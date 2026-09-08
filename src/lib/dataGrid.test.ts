import { describe, expect, it } from 'vitest';

import {
  applyDataGridModel,
  filterDataGridRows,
  isDataGridFilterActive,
  moveColumnKey,
  nextDataGridSorts,
  normalizeColumnOrder,
  sortDataGridRows,
  toggleColumnVisibility,
  visibleColumnKeys,
  type DataGridFilters,
} from './dataGrid';

type Key = 'name' | 'region' | 'sales' | 'score';
interface Row {
  id: string;
  name: string;
  region: string;
  sales: number | null;
  score: string;
}

const rows: Row[] = [
  { id: '1', name: 'Ștefan', region: 'Sud', sales: 100, score: '10,5%' },
  { id: '2', name: 'Ana', region: 'Nord', sales: 200, score: '9,5%' },
  { id: '3', name: 'Andrei', region: 'Nord', sales: 200, score: '10,5%' },
  { id: '4', name: 'Mihai', region: 'Sud', sales: null, score: 'N/A' },
];

const getValue = (row: Row, key: Key) => row[key];
const ids = (items: Row[]) => items.map((row) => row.id);
const filterRows = (filters: DataGridFilters<Key>) =>
  filterDataGridRows<Row, Key>(rows, filters, getValue);

describe('dataGrid model', () => {
  it('matches text without case or Romanian diacritics', () => {
    expect(ids(filterRows(
      { name: { kind: 'text', value: 'stef' } },
    ))).toEqual(['1']);
  });

  it('composes enum and numeric range filters and excludes missing numbers', () => {
    const filters: DataGridFilters<Key> = {
      region: { kind: 'enum', value: 'nord' },
      sales: { kind: 'number', min: 150, max: 200 },
    };

    expect(ids(filterRows(filters))).toEqual(['2', '3']);
    expect(ids(filterRows(
      { sales: { kind: 'number', min: null, max: 100 } },
    ))).toEqual(['1']);
  });

  it('accepts localized numeric strings and ignores empty or invalid ranges', () => {
    expect(ids(filterRows(
      { score: { kind: 'number', min: 10, max: 11 } },
    ))).toEqual(['1', '3']);
    expect(isDataGridFilterActive({ kind: 'number', min: Number.NaN, max: null })).toBe(false);
    expect(ids(filterRows(
      { sales: { kind: 'number', min: Number.NaN, max: null } },
    ))).toEqual(['1', '2', '3', '4']);
  });

  it('sorts by multiple columns and preserves input order for ties', () => {
    expect(ids(sortDataGridRows(
      rows,
      [
        { key: 'region', direction: 'asc' },
        { key: 'name', direction: 'asc' },
      ],
      getValue,
    ))).toEqual(['2', '3', '4', '1']);

    expect(ids(sortDataGridRows(
      rows,
      [{ key: 'sales', direction: 'desc' }],
      getValue,
    ))).toEqual(['2', '3', '1', '4']);
  });

  it('applies filters before sorting without mutating source rows', () => {
    const source = [...rows];
    const result = applyDataGridModel(
      source,
      { region: { kind: 'enum', value: 'Nord' } },
      [{ key: 'name', direction: 'desc' }],
      getValue,
    );

    expect(ids(result)).toEqual(['3', '2']);
    expect(source).toEqual(rows);
  });

  it('supports replacement and shift-style additive sort transitions', () => {
    expect(nextDataGridSorts([], 'name', { defaultAscKeys: ['name'] })).toEqual([
      { key: 'name', direction: 'asc' },
    ]);
    expect(nextDataGridSorts([{ key: 'name', direction: 'asc' }], 'name')).toEqual([
      { key: 'name', direction: 'desc' },
    ]);
    expect(nextDataGridSorts(
      [{ key: 'name', direction: 'asc' }],
      'sales',
      { append: true },
    )).toEqual([
      { key: 'name', direction: 'asc' },
      { key: 'sales', direction: 'desc' },
    ]);
    expect(nextDataGridSorts(
      [
        { key: 'name', direction: 'asc' },
        { key: 'sales', direction: 'desc' },
      ],
      'name',
      { append: true },
    )).toEqual([
      { key: 'name', direction: 'desc' },
      { key: 'sales', direction: 'desc' },
    ]);
    expect(nextDataGridSorts(
      [
        { key: 'name', direction: 'asc' },
        { key: 'sales', direction: 'desc' },
      ],
      'name',
    )).toEqual([
      { key: 'name', direction: 'desc' },
    ]);
  });

  it('normalizes column order and ignores unknown or duplicate keys', () => {
    expect(normalizeColumnOrder<Key>(
      ['name', 'region', 'sales'],
      ['sales', 'missing' as Key, 'sales'],
    )).toEqual(['sales', 'name', 'region']);
    expect(moveColumnKey<Key>(
      ['name', 'region', 'sales'],
      [],
      'region',
      -1,
    )).toEqual(['region', 'name', 'sales']);
    expect(moveColumnKey<Key>(
      ['name', 'region', 'sales'],
      [],
      'name',
      -1,
    )).toEqual(['name', 'region', 'sales']);
  });

  it('keeps at least one visible column and restores hidden columns', () => {
    expect(visibleColumnKeys<Key>(
      ['name', 'region', 'sales'],
      { order: ['sales'], hidden: ['region'] },
    )).toEqual(['sales', 'name']);
    expect(visibleColumnKeys<Key>(
      ['name', 'region'],
      { order: [], hidden: ['name', 'region'] },
    )).toEqual(['name']);
    expect(toggleColumnVisibility<Key>(['name'], [], 'name')).toEqual([]);
    expect(toggleColumnVisibility<Key>(['name', 'region'], ['region'], 'region')).toEqual([]);
    expect(toggleColumnVisibility<Key>(['name', 'region'], [], 'region')).toEqual(['region']);
  });
});
