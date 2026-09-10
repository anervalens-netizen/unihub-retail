// @vitest-environment jsdom

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../ExportTableButton', () => ({
  ExportTableButton: () => <output data-testid="export-probe" />,
}));

import { DataGrid, type DataGridColumn } from './DataGrid';

type Key = 'name' | 'region' | 'sales';

interface Row {
  id: string;
  name: string;
  region: string;
  sales: number;
}

const rows: Row[] = [
  { id: 'a', name: 'Ana', region: 'Sud', sales: 100 },
  { id: 'b', name: 'Mihai', region: 'Nord', sales: 200 },
];

function buildColumns(fixedLeft: boolean): DataGridColumn<Row, Key>[] {
  return [
    {
      key: 'name',
      label: 'Nume',
      value: (row) => row.name,
      render: (row) => row.name,
      filter: { kind: 'text' },
      hideable: true,
      fixedLeft,
    },
    {
      key: 'region',
      label: 'Regiune',
      value: (row) => row.region,
      render: (row) => row.region,
      filter: { kind: 'text' },
    },
    {
      key: 'sales',
      label: 'Vânzări',
      value: (row) => row.sales,
      render: (row) => row.sales,
      filter: { kind: 'number' },
    },
  ];
}

function renderGrid(fixedLeft: boolean) {
  return render(
    <DataGrid
      title="Test"
      rows={rows}
      columns={buildColumns(fixedLeft)}
      rowKey={(row) => row.id}
      exportFilename="test"
      exportSheetName="Test"
    />,
  );
}

function headerOrder(): string[] {
  return screen.getAllByTestId(/^data-grid-header-/).map(
    (header) => header.getAttribute('data-testid') ?? '',
  );
}

describe('DataGrid fixed-left identity column', () => {
  it('keeps the identity sticky, visible and first while other columns reorder behind it', () => {
    renderGrid(true);

    const identityHeader = screen.getByTestId('data-grid-header-name');
    const identityFilter = screen.getByTestId('data-grid-filter-cell-name');
    const firstRow = screen.getAllByTestId('data-grid-row')[0];
    const identityCell = within(firstRow).getAllByRole('cell')[0];

    expect(identityHeader).toHaveClass('sticky', 'left-0');
    expect(identityFilter).toHaveClass('sticky', 'left-0');
    expect(identityCell).toHaveClass('sticky', 'left-0');

    fireEvent.click(screen.getByText('Coloane', { exact: true }));
    expect(screen.getByRole('checkbox', { name: 'Afișează Nume' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Mută Nume la dreapta' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Mută Regiune la stânga' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Mută Vânzări la stânga' }));
    expect(headerOrder()).toEqual([
      'data-grid-header-name',
      'data-grid-header-sales',
      'data-grid-header-region',
    ]);
    expect(screen.getByRole('button', { name: 'Mută Vânzări la stânga' })).toBeDisabled();
  });

  it('preserves unrestricted left reordering when no fixed column is configured', () => {
    renderGrid(false);

    fireEvent.click(screen.getByText('Coloane', { exact: true }));
    const moveSalesLeft = screen.getByRole('button', { name: 'Mută Vânzări la stânga' });
    fireEvent.click(moveSalesLeft);
    fireEvent.click(moveSalesLeft);

    expect(headerOrder()).toEqual([
      'data-grid-header-sales',
      'data-grid-header-name',
      'data-grid-header-region',
    ]);
  });
});
