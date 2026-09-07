// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
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
    rows,
    columns,
    initialSort,
  }: {
    rows: unknown[];
    columns: Array<{ filter?: { kind: string } }>;
    initialSort: Array<{ key: string }>;
  }) => (
    <div data-testid="regional-grid">
      {rows.length}|{columns[0]?.filter?.kind}|{initialSort[0]?.key}
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
  stores: [{ site_code: 'S1' }],
  sortedStores: [{ site_code: 'S1' }],
  storeColumns: [{ key: 'locatie', label: 'Magazin', render: () => 'Magazin' }],
  storeSort: { key: 'locatie', direction: 'asc' },
  onSortStores: vi.fn(),
  agents: [{ agent: 'Ana', site_code: 'S1' }],
  sortedAgents: [{ agent: 'Ana', site_code: 'S1' }],
  agentColumns: [{ key: 'agent', label: 'Agent', render: () => 'Ana' }],
  agentSort: { key: 'agent', direction: 'asc' },
  onSortAgents: vi.fn(),
};

describe('HistoryBreakdowns V3 pilot', () => {
  it('uses raw regional rows in DataGrid and leaves other breakdowns unchanged', () => {
    render(<HistoryBreakdowns props={props as never} visible />);

    expect(screen.getByTestId('regional-grid')).toHaveTextContent('2|text|target');
    expect(screen.getByTestId('legacy-Magazine')).toHaveTextContent('1');
    expect(screen.getByTestId('legacy-Agenti')).toHaveTextContent('1');
  });
});
