// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../components/ExportTableButton', () => ({
  ExportTableButton: () => <button type="button">Excel</button>,
}));

import { BreakdownTable, type BreakdownColumn } from './BreakdownTable';

interface Row {
  id: string;
  agent: string;
}

type SortKey = 'agent';

const rows: Row[] = [{ id: 'a', agent: 'Ana Popescu' }];
const columns: BreakdownColumn<Row, SortKey>[] = [{
  key: 'agent',
  label: 'Agent',
  render: (row) => row.agent,
}];

describe('BreakdownTable accessibility', () => {
  it('uses the visible heading as the table accessible name', () => {
    const onSort = vi.fn();

    render(
      <BreakdownTable
        title="Agenti"
        subtitle="Tabel legacy de control"
        rows={rows}
        columns={columns}
        sortKey="agent"
        sortDirection="asc"
        onSort={onSort}
        rowKey={(row) => row.id}
        exportFilename="agenti"
        exportSheetName="Agenti"
        exportColumns={[{ header: 'Agent', value: (row) => row.agent }]}
      />,
    );

    const heading = screen.getByRole('heading', { name: 'Agenti', level: 3 });
    const table = screen.getByRole('table', { name: 'Agenti' });

    expect(heading.id).not.toBe('');
    expect(table).toHaveAttribute('aria-labelledby', heading.id);
    expect(table).toContainElement(screen.getByText('Ana Popescu'));

    fireEvent.click(screen.getByRole('button', { name: 'Agent' }));
    expect(onSort).toHaveBeenCalledWith('agent');
  });
});
