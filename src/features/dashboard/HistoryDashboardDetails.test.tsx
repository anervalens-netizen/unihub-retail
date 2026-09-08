// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('recharts', () => ({
  Bar: () => null,
  CartesianGrid: () => null,
  ComposedChart: ({ children }: { children?: unknown }) => children,
  Legend: () => null,
  Line: () => null,
  ResponsiveContainer: ({ children }: { children?: unknown }) => children,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

vi.mock('../../components/common/DataGrid', () => ({
  DataGrid: ({
    title,
    rows,
    columns,
    initialSort,
    onSortChange,
    exportColumns,
  }: {
    title: string;
    rows: unknown[];
    columns: Array<{ filter?: { kind: string } }>;
    initialSort: Array<{ key: string }>;
    onSortChange?: (sorts: Array<{ key: string; direction: 'asc' | 'desc' }>) => void;
    exportColumns?: Array<{ header: string }>;
  }) => (
    <div data-testid={`grid-${title}`}>
      <span data-testid={`grid-${title}-state`}>
        {rows.length}|{columns[0]?.filter?.kind}|{initialSort.map((sort) => sort.key).join(',')}
      </span>
      <span data-testid={`grid-${title}-export`}>
        {exportColumns?.map((column) => column.header).join('|') ?? 'derived'}
      </span>
      <button
        type="button"
        onClick={() => onSortChange?.(
          title === 'RM'
            ? [
                { key: 'regional', direction: 'asc' },
                { key: 'target', direction: 'desc' },
              ]
            : [
                { key: 'locatie', direction: 'asc' },
                { key: 'target', direction: 'desc' },
              ],
        )}
      >
        persist-{title}-sort
      </button>
    </div>
  ),
}));

vi.mock('./BreakdownTable', () => ({
  BreakdownTable: ({ title, rows }: { title: string; rows: unknown[] }) => (
    <div data-testid={`legacy-${title}`}>{rows.length}</div>
  ),
}));

vi.mock('./DashboardWidgets', () => ({
  CompactPieSection: () => null,
  formatCompactAxisValue: String,
  formatCompactDonutValue: String,
  sumChartValues: () => 0,
}));

import { HistoryBreakdowns } from './HistoryDashboardDetails';

const onRegionalGridSortsChange = vi.fn();
const onStoreGridSortsChange = vi.fn();

const props = {
  selectionSlug: '2026-08',
  regionals: [
    { regional: 'Nord', target: 100 },
    { regional: 'Sud', target: 200 },
  ],
  sortedRegionals: [{ regional: 'Sud', target: 200 }],
  regionalColumns: [
    { key: 'regional', label: 'Regional', render: (row: { regional: string }) => row.regional },
    { key: 'target', label: 'Target', render: (row: { target: number }) => row.target },
  ],
  regionalSort: { key: 'target', direction: 'desc' },
  onSortRegionals: vi.fn(),
  regionalGridSorts: [
    { key: 'target', direction: 'desc' },
    { key: 'regional', direction: 'asc' },
  ],
  onRegionalGridSortsChange,
  stores: [
    { site_code: 'S1', firma: 'Mobiup', locatie: 'Promenada', target: 100 },
    { site_code: 'S2', firma: 'Arsis', locatie: 'Baneasa', target: 200 },
  ],
  sortedStores: [{ site_code: 'S2', firma: 'Arsis', locatie: 'Baneasa', target: 200 }],
  storeColumns: [
    { key: 'locatie', label: 'Magazin', render: (row: { locatie: string }) => row.locatie },
    { key: 'target', label: 'Target', render: (row: { target: number }) => row.target },
  ],
  storeSort: { key: 'total_vanzari', direction: 'desc' },
  onSortStores: vi.fn(),
  storeGridSorts: [
    { key: 'total_vanzari', direction: 'desc' },
  ],
  onStoreGridSortsChange,
  agents: [{ agent: 'Ana', site_code: 'S1' }],
  sortedAgents: [{ agent: 'Ana', site_code: 'S1' }],
  agentColumns: [{ key: 'agent', label: 'Agent', render: () => 'Ana' }],
  agentSort: { key: 'agent', direction: 'asc' },
  onSortAgents: vi.fn(),
};

describe('HistoryBreakdowns V3 DataGrid consumers', () => {
  it('uses raw RM and Store rows, persists both sort chains and leaves Agenti legacy', () => {
    onRegionalGridSortsChange.mockClear();
    onStoreGridSortsChange.mockClear();
    render(<HistoryBreakdowns props={props as never} visible />);

    expect(screen.getByTestId('grid-RM-state')).toHaveTextContent('2|text|target,regional');
    expect(screen.getByTestId('grid-Magazine-state')).toHaveTextContent(
      '2|text|total_vanzari',
    );
    expect(screen.getByTestId('grid-RM-export')).toHaveTextContent('derived');
    expect(screen.getByTestId('grid-Magazine-export')).toHaveTextContent(
      'Firma|Magazin|Target|Vanzari|Procent|Cantitate|Nr bonuri|Retururi|Agenti|Zile active',
    );
    expect(screen.getByTestId('legacy-Agenti')).toHaveTextContent('1');
    expect(screen.queryByTestId('legacy-Magazine')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'persist-RM-sort' }));
    expect(onRegionalGridSortsChange).toHaveBeenCalledWith([
      { key: 'regional', direction: 'asc' },
      { key: 'target', direction: 'desc' },
    ]);

    fireEvent.click(screen.getByRole('button', { name: 'persist-Magazine-sort' }));
    expect(onStoreGridSortsChange).toHaveBeenCalledWith([
      { key: 'locatie', direction: 'asc' },
      { key: 'target', direction: 'desc' },
    ]);
  });
});
