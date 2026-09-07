import { describe, expect, it } from 'vitest';
import {
  applyDataGridState,
  buildDataGridExport,
  compareDataGridValues,
  filterDataGridRows,
  parseDataGridNumber,
  resolveDataGridColumns,
  sortDataGridRows,
  type DataGridColumn,
} from './dataGridModel';

type Row = {
  id: string;
  store: string;
  region: string | null;
  sales: number | string | null;
};

const rows: Row[] = [
  { id: 'a', store: 'Băneasa', region: 'Sud', sales: '1.250,5' },
  { id: 'b', store: 'Promenada', region: 'Nord', sales: 900 },
  { id: 'c', store: 'Mega Mall', region: 'Sud', sales: 900 },
  { id: 'd', store: 'Fără date', region: null, sales: null },
];

const columns: DataGridColumn<Row>[] = [
  { id: 'store', header: 'Magazin', value: (row) => row.store },
  { id: 'region', header: 'Regiune', value: (row) => row.region },
  { id: 'sales', header: 'Vânzări', value: (row) => row.sales },
  {
    id: 'id',
    header: 'ID',
    value: (row) => row.id,
    exportValue: (row) => `store:${row.id}`,
  },
];

describe('dataGridModel', () => {
  it('parses finite numbers and Romanian-formatted values', () => {
    expect(parseDataGridNumber(12.5)).toBe(12.5);
    expect(parseDataGridNumber('1.234,56')).toBe(1234.56);
    expect(parseDataGridNumber('87,5%')).toBe(87.5);
    expect(parseDataGridNumber('')).toBeNull();
    expect(parseDataGridNumber(Number.POSITIVE_INFINITY)).toBeNull();
  });

  it('compares numbers, dates and text while placing missing values last', () => {
    expect(compareDataGridValues('10,5', 9)).toBeGreaterThan(0);
    expect(compareDataGridValues(new Date('2026-01-01'), new Date('2026-02-01'))).toBeLessThan(0);
    expect(compareDataGridValues('Băneasa', 'Promenada')).toBeLessThan(0);
    expect(compareDataGridValues(null, 1)).toBeGreaterThan(0);
  });

  it('performs stable multi-column sorting and ignores stale column ids', () => {
    const result = sortDataGridRows(rows, columns, [
      { columnId: 'stale', direction: 'desc' },
      { columnId: 'sales', direction: 'desc' },
      { columnId: 'store', direction: 'asc' },
    ]);

    expect(result.map((row) => row.id)).toEqual(['a', 'c', 'b', 'd']);

    const tied = sortDataGridRows(
      [rows[1], rows[2]],
      columns,
      [{ columnId: 'sales', direction: 'asc' }],
    );
    expect(tied.map((row) => row.id)).toEqual(['b', 'c']);
  });

  it('composes text, enum and inclusive numeric filters', () => {
    const result = filterDataGridRows(rows, columns, [
      { kind: 'text', columnId: 'store', value: 'mall' },
      { kind: 'enum', columnId: 'region', values: ['SUD'] },
      { kind: 'number', columnId: 'sales', min: 900, max: 900 },
    ]);

    expect(result.map((row) => row.id)).toEqual(['c']);
  });

  it('keeps declared column order, ignores stale ids and hides requested columns', () => {
    const visible = resolveDataGridColumns(columns, {
      order: ['sales', 'missing', 'store'],
      hidden: ['region'],
    });

    expect(visible.map((column) => column.id)).toEqual(['sales', 'store', 'id']);
  });

  it('applies filters before sorting without mutating the source rows', () => {
    const source = [...rows];
    const result = applyDataGridState(rows, columns, {
      filters: [{ kind: 'enum', columnId: 'region', values: ['Sud'] }],
      sort: [{ columnId: 'store', direction: 'desc' }],
    });

    expect(result.rows.map((row) => row.id)).toEqual(['c', 'a']);
    expect(rows).toEqual(source);
  });

  it('exports exactly the filtered rows and visible ordered columns', () => {
    const result = buildDataGridExport(rows, columns, {
      filters: [{ kind: 'number', columnId: 'sales', min: 900 }],
      sort: [{ columnId: 'sales', direction: 'desc' }],
      columns: {
        order: ['id', 'store', 'sales'],
        hidden: ['region'],
      },
    });

    expect(result.headers).toEqual(['ID', 'Magazin', 'Vânzări']);
    expect(result.rows).toEqual([
      ['store:a', 'Băneasa', '1.250,5'],
      ['store:b', 'Promenada', 900],
      ['store:c', 'Mega Mall', 900],
    ]);
  });
});
