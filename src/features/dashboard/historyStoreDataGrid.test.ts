import { describe, expect, it, vi } from 'vitest';

import type { StoreStat } from '../../api/generated/runtime-types';
import type { BreakdownColumn } from './BreakdownTable';
import {
  historyStoreDataGridColumns,
  historyStoreLegacyExportColumns,
} from './historyStoreDataGrid';

type Key =
  | 'locatie'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'qty_total';

const renderStore = vi.fn((row: StoreStat) => row.locatie);
const sourceColumns: BreakdownColumn<StoreStat, Key>[] = [
  {
    key: 'locatie',
    label: 'Magazin',
    render: renderStore,
    cellClassName: 'store-cell',
  },
  { key: 'target', label: 'Target', render: (row) => row.target },
  {
    key: 'total_vanzari',
    label: 'Vanzari',
    render: (row) => row.total_vanzari,
  },
  {
    key: 'proc_realizare_target',
    label: 'Procent',
    render: (row) => row.proc_realizare_target,
  },
  { key: 'qty_total', label: 'Cantitate', render: (row) => row.qty_total },
];

const row = {
  site_code: 'S1',
  firma: 'Mobiup',
  locatie: 'Promenada',
  target: 1000,
  total_vanzari: 900,
  proc_realizare_target: 90,
  qty_total: 12,
  nr_bonuri: 10,
  return_receipt_count: 1,
  nr_agenti: 2,
  zile_active: 5,
} as StoreStat;

describe('historyStoreDataGridColumns', () => {
  it('preserves Store renderers and adds typed filter/sort metadata', () => {
    const columns = historyStoreDataGridColumns(sourceColumns);

    expect(columns.map((column) => column.key)).toEqual([
      'locatie',
      'target',
      'total_vanzari',
      'proc_realizare_target',
      'qty_total',
    ]);
    expect(columns[0]).toMatchObject({
      filter: { kind: 'text', placeholder: 'Magazin' },
      defaultDirection: 'asc',
      hideable: false,
      cellClassName: 'store-cell',
    });
    expect(columns[0]?.render).toBe(renderStore);
    expect(columns[1]).toMatchObject({
      filter: { kind: 'number' },
      defaultDirection: 'desc',
      hideable: true,
      exportFormat: 'currency',
    });
    expect(columns[3]?.exportFormat).toBe('percentPoints');
    expect(columns[4]?.exportFormat).toBe('integer');
    expect(columns[0]?.value(row)).toBe('Promenada');
    expect(columns[2]?.value(row)).toBe(900);
  });

  it('reproduces the exact legacy Store export projection', () => {
    const exportColumns = historyStoreLegacyExportColumns();

    expect(exportColumns.map((column) => column.header)).toEqual([
      'Firma',
      'Magazin',
      'Target',
      'Vanzari',
      'Procent',
      'Cantitate',
      'Nr bonuri',
      'Retururi',
      'Agenti',
      'Zile active',
    ]);
    expect(exportColumns.map((column) => column.format)).toEqual([
      undefined,
      undefined,
      'currency',
      'currency',
      'percentPoints',
      'integer',
      'integer',
      'integer',
      'integer',
      'integer',
    ]);
    expect(exportColumns.map((column) => column.value(row))).toEqual([
      'Mobiup',
      'Promenada',
      1000,
      900,
      90,
      12,
      10,
      1,
      2,
      5,
    ]);
  });
});
