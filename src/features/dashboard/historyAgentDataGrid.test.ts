import { describe, expect, it, vi } from 'vitest';

import type { AgentStat } from '../../api/generated/runtime-types';
import type { BreakdownColumn } from './BreakdownTable';
import {
  historyAgentDataGridColumns,
  historyAgentLegacyExportColumns,
} from './historyAgentDataGrid';

type Key =
  | 'agent'
  | 'locatie'
  | 'target'
  | 'total_vanzari'
  | 'proc_realizare_target'
  | 'acc_qty_realizat'
  | 'medie_zilnica';

const renderAgent = vi.fn((row: AgentStat) => row.agent);
const sourceColumns: BreakdownColumn<AgentStat, Key>[] = [
  {
    key: 'agent',
    label: 'Agent',
    render: renderAgent,
    cellClassName: 'agent-cell',
  },
  { key: 'locatie', label: 'Magazin', render: (row) => row.locatie },
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
  {
    key: 'acc_qty_realizat',
    label: 'Cantitate',
    render: (row) => row.acc_qty_realizat,
  },
  {
    key: 'medie_zilnica',
    label: 'Medie zilnica',
    render: (row) => row.zile_lucrate > 0
      ? row.total_vanzari / row.zile_lucrate
      : 0,
  },
];

const row = {
  agent: 'Ana Popescu',
  site_code: 'S1',
  firma: 'Mobiup',
  locatie: 'Promenada',
  target: 1000,
  total_vanzari: 900,
  proc_realizare_target: 90,
  acc_qty_realizat: 12,
  nr_bonuri: 10,
  return_receipt_count: 1,
  zile_lucrate: 5,
  medie_zilnica: 999,
  proc_bon2acc: 40,
  prc_focus_acc_qty: 25,
} as AgentStat;

describe('historyAgentDataGridColumns', () => {
  it('preserves Agent renderers and adds typed filter/sort metadata', () => {
    const columns = historyAgentDataGridColumns(sourceColumns);

    expect(columns.map((column) => column.key)).toEqual([
      'agent',
      'locatie',
      'target',
      'total_vanzari',
      'proc_realizare_target',
      'acc_qty_realizat',
      'medie_zilnica',
    ]);
    expect(columns[0]).toMatchObject({
      filter: { kind: 'text', placeholder: 'Agent' },
      defaultDirection: 'asc',
      hideable: false,
      cellClassName: 'agent-cell',
    });
    expect(columns[0]?.render).toBe(renderAgent);
    expect(columns[1]).toMatchObject({
      filter: { kind: 'text', placeholder: 'Magazin' },
      defaultDirection: 'asc',
      hideable: true,
    });
    expect(columns[2]).toMatchObject({
      filter: { kind: 'number' },
      defaultDirection: 'desc',
      exportFormat: 'currency',
    });
    expect(columns[4]?.exportFormat).toBe('percentPoints');
    expect(columns[5]?.exportFormat).toBe('integer');
    expect(columns[0]?.value(row)).toBe('Ana Popescu');
    expect(columns[1]?.value(row)).toBe('Promenada');
  });

  it('uses the displayed daily-average calculation for sorting/filter/search', () => {
    const columns = historyAgentDataGridColumns(sourceColumns);
    const dailyAverage = columns.find((column) => column.key === 'medie_zilnica');

    expect(dailyAverage?.value(row)).toBe(180);
    expect(dailyAverage?.searchValue?.(row)).toBe('180');
    expect(dailyAverage?.value({ ...row, zile_lucrate: 0 } as AgentStat)).toBe(0);
    expect(columns[2]?.searchValue?.(row)).toBe('1.000');
    expect(columns[3]?.searchValue?.(row)).toBe('900');
    expect(columns[4]?.searchValue?.(row)).toBe('90.00%');
    expect(columns[5]?.searchValue?.(row)).toBe('12');
  });

  it('reproduces the exact legacy Agent export projection and raw export values', () => {
    const exportColumns = historyAgentLegacyExportColumns();

    expect(exportColumns.map((column) => column.header)).toEqual([
      'Agent',
      'Firma',
      'Magazin',
      'Target',
      'Vanzari',
      'Procent',
      'Cantitate',
      'Nr bonuri',
      'Retururi',
      'Zile lucrate',
      'Medie zilnica',
      'ProcBon2Acc',
      'Focus%',
    ]);
    expect(exportColumns.map((column) => column.format)).toEqual([
      undefined,
      undefined,
      undefined,
      'currency',
      'currency',
      'percentPoints',
      'integer',
      'integer',
      'integer',
      'integer',
      'currency',
      'percentPoints',
      'percentPoints',
    ]);
    expect(exportColumns.map((column) => column.value(row, 0))).toEqual([
      'Ana Popescu',
      'Mobiup',
      'Promenada',
      1000,
      900,
      90,
      12,
      10,
      1,
      5,
      999,
      40,
      25,
    ]);
  });
});
