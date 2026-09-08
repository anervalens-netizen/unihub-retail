import { describe, expect, it } from 'vitest';

import type { RegionalStat } from '../../api/generated/runtime-types';
import type { BreakdownColumn } from './BreakdownTable';
import { historyRegionalDataGridColumns } from './historyRegionalDataGrid';

type Key = 'regional' | 'target' | 'proc_realizare_target' | 'qty_total';

const sourceColumns: BreakdownColumn<RegionalStat, Key>[] = [
  { key: 'regional', label: 'Regional', render: (row) => row.regional },
  { key: 'target', label: 'Target', render: (row) => row.target },
  {
    key: 'proc_realizare_target',
    label: '% Target',
    render: (row) => row.proc_realizare_target,
  },
  { key: 'qty_total', label: 'Cantitate', render: (row) => row.qty_total },
];

const row = {
  regional: 'București',
  target: 1000,
  proc_realizare_target: 95.5,
  qty_total: 12,
} as RegionalStat;

describe('historyRegionalDataGridColumns', () => {
  it('preserves display columns and adds typed filtering and sorting metadata', () => {
    const columns = historyRegionalDataGridColumns(sourceColumns);

    expect(columns.map((column) => column.key)).toEqual([
      'regional',
      'target',
      'proc_realizare_target',
      'qty_total',
    ]);
    expect(columns[0]).toMatchObject({
      filter: { kind: 'text', placeholder: 'Regional' },
      defaultDirection: 'asc',
      hideable: false,
      exportHeader: 'Regional',
    });
    expect(columns[1]).toMatchObject({
      filter: { kind: 'number' },
      defaultDirection: 'desc',
      hideable: true,
      exportFormat: 'currency',
    });
  });

  it('keeps raw values and the legacy export formats', () => {
    const columns = historyRegionalDataGridColumns(sourceColumns);

    expect(columns[0]?.value(row)).toBe('București');
    expect(columns[1]?.exportValue?.(row, 0)).toBe(1000);
    expect(columns[2]?.exportFormat).toBe('percentPoints');
    expect(columns[3]?.exportFormat).toBe('integer');
    expect(columns[3]?.render(row)).toBe(12);
  });
});
